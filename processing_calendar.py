import pandas as pd
import streamlit as st
from datetime import timedelta
from helpers import (safe_string_conversion, standardize_visit_columns, validate_required_columns, 
                    get_financial_year_start_year, is_financial_year_end, log_activity)
from payment_handler import normalize_payment_column, validate_payment_data

# Import from our new modules
from visit_processor import process_study_events, detect_screen_failures
from patient_processor import process_single_patient
from calendar_builder import build_calendar_dataframe, fill_calendar_with_visits

def build_calendar(patients_df, trials_df, actual_visits_df=None):
    """Enhanced calendar builder with study events support - Main orchestrator function"""
    
    # Clean columns - ensure they are strings before using .str accessor
    patients_df.columns = [str(col).strip() for col in patients_df.columns]
    trials_df.columns = [str(col).strip() for col in trials_df.columns]
    if actual_visits_df is not None:
        actual_visits_df.columns = [str(col).strip() for col in actual_visits_df.columns]

    # Add missing columns with defaults before validation
    # Patients: Add optional columns if missing
    if 'Site' not in patients_df.columns:
        patients_df['Site'] = ''
    if 'PatientPractice' not in patients_df.columns:
        patients_df['PatientPractice'] = ''
    if 'OriginSite' not in patients_df.columns:
        patients_df['OriginSite'] = ''
    
    # Trials: Add optional columns if missing
    if 'SiteforVisit' not in trials_df.columns:
        trials_df['SiteforVisit'] = 'Default Site'
    if 'Payment' not in trials_df.columns:
        trials_df['Payment'] = 0
    if 'ToleranceBefore' not in trials_df.columns:
        trials_df['ToleranceBefore'] = 0
    if 'ToleranceAfter' not in trials_df.columns:
        trials_df['ToleranceAfter'] = 0
    
    # Validate required columns
    validate_required_columns(patients_df, {"PatientID", "Study", "StartDate"}, "Patients file")
    validate_required_columns(trials_df, {"Study", "Day", "VisitName"}, "Trials file")

    # Standardize visit columns
    trials_df = standardize_visit_columns(trials_df)
    if actual_visits_df is not None:
        # Debug: Log actual columns before processing
        log_activity(f"Actual visits columns before processing: {list(actual_visits_df.columns)}", level='info')
        log_activity(f"Actual visits shape: {actual_visits_df.shape}", level='info')
        
        # Add missing columns with defaults before validation
        if 'VisitType' not in actual_visits_df.columns:
            actual_visits_df['VisitType'] = 'patient'
        if 'Status' not in actual_visits_df.columns:
            actual_visits_df['Status'] = 'completed'
        if 'Notes' not in actual_visits_df.columns:
            actual_visits_df['Notes'] = ''
        
        # Debug: Log columns after adding defaults
        log_activity(f"Actual visits columns after adding defaults: {list(actual_visits_df.columns)}", level='info')
        
        # Check for required columns with more detailed error message
        required_columns = {"PatientID", "Study", "VisitName", "ActualDate"}
        missing_columns = required_columns - set(actual_visits_df.columns)
        if missing_columns:
            log_activity(f"Missing required columns: {missing_columns}", level='error')
            log_activity(f"Available columns: {list(actual_visits_df.columns)}", level='error')
            raise ValueError(f"Actual visits file missing required columns: {', '.join(missing_columns)}")
        
        actual_visits_df = standardize_visit_columns(actual_visits_df)

    # Check for SiteforVisit column
    if "SiteforVisit" not in trials_df.columns:
        trials_df["SiteforVisit"] = "Default Site"

    # Prepare actual visits data
    unmatched_visits = []
    screen_failures = {}
    
    if actual_visits_df is not None:
        actual_visits_df = prepare_actual_visits_data(actual_visits_df)
        screen_failures, screen_fail_unmatched = detect_screen_failures(actual_visits_df, trials_df)
        unmatched_visits.extend(screen_fail_unmatched)

    # Prepare other data
    trials_df = prepare_trials_data(trials_df)
    patients_df = prepare_patients_data(patients_df, trials_df)
    
    # Validate studies
    validate_study_structure(patients_df, trials_df)

    # Separate visit types
    patient_visits, study_event_templates = separate_visit_types(trials_df)

    # Process all visits
    visit_records = []
    
    # Process study events first
    if not study_event_templates.empty:
        visit_records.extend(process_study_events(study_event_templates, actual_visits_df))
    
    # Process patient visits
    processing_stats = process_all_patients(
        patients_df, patient_visits, screen_failures, actual_visits_df
    )
    
    visit_records.extend(processing_stats['visit_records'])
    
    # Create visits DataFrame
    visits_df = pd.DataFrame(visit_records)
    log_activity(f"Created visits DataFrame with {len(visits_df)} records", level='info')
    if not visits_df.empty:
        log_activity(f"Visits date range: {visits_df['Date'].min()} to {visits_df['Date'].max()}", level='info')
    if visits_df.empty:
        raise ValueError("No visits generated. Check that Patient 'Study' matches Trial 'Study' values and StartDate is populated.")
    
    # Check for duplicate visits (same patient, study, date, visit)
    if 'PatientID' in visits_df.columns and 'Study' in visits_df.columns and 'Date' in visits_df.columns and 'Visit' in visits_df.columns:
        duplicate_mask = visits_df.duplicated(subset=['PatientID', 'Study', 'Date', 'Visit'], keep='first')
        if duplicate_mask.any():
            duplicate_count = duplicate_mask.sum()
            log_activity(f"Removed {duplicate_count} duplicate visits", level='info')
            visits_df = visits_df[~duplicate_mask].reset_index(drop=True)
    
    # Check for duplicate indices in visits DataFrame
    if not visits_df.index.is_unique:
        log_activity(f"Reset duplicate indices in visits DataFrame", level='info')
        visits_df = visits_df.reset_index(drop=True)

    # Build processing messages
    processing_messages = build_processing_messages(processing_stats, unmatched_visits)

    # DEBUG: Check visits_df state before building calendar
    log_activity(f"Building calendar with {len(visits_df)} visits", level='info')
    
    # Build calendar dataframe
    calendar_df, site_column_mapping, unique_visit_sites = build_calendar_dataframe(visits_df, patients_df)
    
    # Fill calendar with visits
    calendar_df = fill_calendar_with_visits(calendar_df, visits_df, trials_df)

    # Calculate financial totals
    calendar_df = calculate_financial_totals(calendar_df)

    # Build stats
    stats = {
        "total_visits": len([v for v in visit_records if not v.get('IsActual', False) and v['Visit'] not in ['-', '+'] and not v.get('IsStudyEvent', False)]),
        "total_income": visits_df["Payment"].sum(),
        "messages": processing_messages,
        "out_of_window_visits": processing_stats['out_of_window_visits']
    }

    return visits_df, calendar_df, stats, processing_messages, site_column_mapping, unique_visit_sites

def prepare_actual_visits_data(actual_visits_df):
    """Prepare actual visits data with proper data types"""
    actual_visits_df["PatientID"] = safe_string_conversion(actual_visits_df["PatientID"])
    actual_visits_df["Study"] = safe_string_conversion(actual_visits_df["Study"])
    actual_visits_df["VisitName"] = safe_string_conversion(actual_visits_df["VisitName"])
    
    
    # Check if dates are already parsed (from database) or need parsing (from file upload)
    if not pd.api.types.is_datetime64_any_dtype(actual_visits_df["ActualDate"]):
        # Parse dates with UK format preference (D/M/Y) - no fallback to M/D/Y
        actual_visits_df["ActualDate"] = pd.to_datetime(actual_visits_df["ActualDate"], dayfirst=True, errors="coerce")
        
        # Check for any dates that failed to parse
        nat_count = actual_visits_df["ActualDate"].isna().sum()
        if nat_count > 0:
            log_activity(f"⚠️ {nat_count} dates failed to parse with D/M/Y format. Please check your date format.", level='warning')
            # Log some examples of failed dates for debugging
            failed_dates = actual_visits_df[actual_visits_df["ActualDate"].isna()]["ActualDate"].head(5).tolist()
            if failed_dates:
                log_activity(f"Examples of failed dates: {failed_dates}", level='warning')
    
    if "Notes" not in actual_visits_df.columns:
        actual_visits_df["Notes"] = ""
    else:
        actual_visits_df["Notes"] = safe_string_conversion(actual_visits_df["Notes"], "")
    
    if "VisitType" not in actual_visits_df.columns:
        actual_visits_df["VisitType"] = "patient"
    
    if "Status" not in actual_visits_df.columns:
        actual_visits_df["Status"] = "completed"

    actual_visits_df["VisitKey"] = (
        safe_string_conversion(actual_visits_df["PatientID"]) + "_" +
        safe_string_conversion(actual_visits_df["Study"]) + "_" +
        safe_string_conversion(actual_visits_df["VisitName"])
    )
    
    return actual_visits_df

def prepare_trials_data(trials_df):
    """Prepare trials data with proper data types and column mapping"""
    # Use centralized payment column handling
    trials_df = normalize_payment_column(trials_df, 'Payment')
    
    # Validate payment data
    payment_validation = validate_payment_data(trials_df, 'Payment')
    if not payment_validation['valid']:
        for issue in payment_validation['issues']:
            log_activity(f"Payment data issue: {issue}", level='warning')
    
    # Normalize other column names
    column_mapping = {
        'Tolerance Before': 'ToleranceBefore',
        'Tolerance After': 'ToleranceAfter'
    }
    trials_df = trials_df.rename(columns=column_mapping)

    # Process data types
    trials_df["Study"] = safe_string_conversion(trials_df["Study"])
    trials_df["VisitName"] = safe_string_conversion(trials_df["VisitName"])
    trials_df["SiteforVisit"] = safe_string_conversion(trials_df["SiteforVisit"])
    
    try:
        trials_df["Day"] = pd.to_numeric(trials_df["Day"], errors='coerce').fillna(1).astype(int)
    except:
        st.error("Invalid 'Day' values in trials file. Days must be numeric.")
        raise ValueError("Invalid Day column in trials file")
    
    return trials_df

def prepare_patients_data(patients_df, trials_df):
    """Prepare patients data with proper data types and site mapping"""
    # Process data types
    patients_df["PatientID"] = safe_string_conversion(patients_df["PatientID"])
    patients_df["Study"] = safe_string_conversion(patients_df["Study"])
    
    if not pd.api.types.is_datetime64_any_dtype(patients_df["StartDate"]):
        patients_df["StartDate"] = pd.to_datetime(patients_df["StartDate"], dayfirst=True, errors="coerce")

    # Check for patient origin site column
    patient_origin_col = None
    possible_origin_cols = ['PatientSite', 'OriginSite', 'Practice', 'PatientPractice', 'HomeSite', 'Site']
    for col in possible_origin_cols:
        if col in patients_df.columns:
            patient_origin_col = col
            break
    
    if patient_origin_col:
        patients_df['OriginSite'] = safe_string_conversion(patients_df[patient_origin_col], "Unknown Origin")
    else:
        patients_df['OriginSite'] = "Unknown Origin"

    # Create patient-site mapping
    if patient_origin_col:
        patients_df['Site'] = patients_df['OriginSite']
    else:
        patient_site_mapping = {}
        for _, patient in patients_df.iterrows():
            study = patient["Study"]
            patient_id = patient["PatientID"]
            
            study_sites = trials_df[trials_df["Study"] == study]["SiteforVisit"].unique()
            if len(study_sites) > 0:
                patient_site_mapping[patient_id] = study_sites[0]
            else:
                patient_site_mapping[patient_id] = f"{study}_Site"
        
        patients_df['Site'] = patients_df['PatientID'].map(patient_site_mapping).fillna("Unknown Site")
    
    return patients_df

def validate_study_structure(patients_df, trials_df):
    """Validate that each study has proper Day 1 baseline"""
    for study in patients_df["Study"].unique():
        study_visits = trials_df[trials_df["Study"] == study]
        day_1_visits = study_visits[study_visits["Day"] == 1]
        
        if len(day_1_visits) == 0:
            raise ValueError(f"Study {study} has no Day 1 visit defined. Day 1 is required as baseline.")
        elif len(day_1_visits) > 1:
            visit_names = day_1_visits["VisitName"].tolist()
            raise ValueError(f"Study {study} has multiple Day 1 visits: {visit_names}. Only one Day 1 visit allowed.")

def separate_visit_types(trials_df):
    """Separate patient visits from study events"""
    if 'VisitType' in trials_df.columns:
        patient_visits = trials_df[
            ((trials_df['VisitType'] == 'patient') |
            (pd.isna(trials_df['VisitType']))) &
            (trials_df['Day'] > 0)  # Exclude Day 0 visits from scheduling
        ]
        
        study_event_templates = trials_df[
            trials_df['VisitType'].isin(['siv', 'monitor'])
        ]
    else:
        patient_visits = trials_df[trials_df['Day'] > 0].copy()  # Exclude Day 0 visits from scheduling
        study_event_templates = pd.DataFrame()
    
    return patient_visits, study_event_templates

def process_all_patients(patients_df, patient_visits, screen_failures, actual_visits_df):
    """Process visits for all patients"""
    all_visit_records = []
    total_actual_visits_used = 0
    all_unmatched_visits = []
    total_screen_fail_exclusions = 0
    all_out_of_window_visits = []
    all_processing_messages = []
    recalculated_patients = []
    patients_with_no_visits = []
    
    # Process patients and generate visits
    
    for _, patient in patients_df.iterrows():
        patient_id = str(patient["PatientID"])
        study = str(patient["Study"])
        
        visit_records, actual_visits_used, unmatched_visits, screen_fail_exclusions, out_of_window_visits, processing_messages, patient_needs_recalc = process_single_patient(
            patient, patient_visits, screen_failures, actual_visits_df
        )
        
        # Debug: Log actual visits used for this patient
        if actual_visits_used > 0:
            log_activity(f"DEBUG: Patient {patient_id} used {actual_visits_used} actual visits", level='info')
        
        if not visit_records and len(patient_visits[patient_visits["Study"] == study]) == 0:
            patients_with_no_visits.append(f"{patient_id} (Study: {study})")
            continue
        
        all_visit_records.extend(visit_records)
        total_actual_visits_used += actual_visits_used
        all_unmatched_visits.extend(unmatched_visits)
        total_screen_fail_exclusions += screen_fail_exclusions
        all_out_of_window_visits.extend(out_of_window_visits)
        all_processing_messages.extend(processing_messages)
        
        if patient_needs_recalc:
            recalculated_patients.append(f"{patient_id} ({study})")
    
    if len(all_visit_records) > 0:
        log_activity(f"✅ Generated {len(all_visit_records)} visit records from {len(patients_df)} patients", level='info')
    if len(patients_with_no_visits) > 0:
        log_activity(f"⚠️ {len(patients_with_no_visits)} patients have no visits scheduled", level='warning')
    
    return {
        'visit_records': all_visit_records,
        'actual_visits_used': total_actual_visits_used,
        'unmatched_visits': all_unmatched_visits,
        'screen_fail_exclusions': total_screen_fail_exclusions,
        'out_of_window_visits': all_out_of_window_visits,
        'processing_messages': all_processing_messages,
        'recalculated_patients': recalculated_patients,
        'patients_with_no_visits': patients_with_no_visits
    }

def build_processing_messages(processing_stats, unmatched_visits):
    """Build the final processing messages"""
    processing_messages = []
    
    # Add unmatched visits from screen failure detection
    for unmatched in unmatched_visits:
        processing_messages.append(f"⚠️ {unmatched}")
    
    # Add unmatched visits from patient processing
    for unmatched in processing_stats['unmatched_visits']:
        processing_messages.append(f"⚠️ {unmatched}")

    # Add patient processing messages
    processing_messages.extend(processing_stats['processing_messages'])
    
    # Add summary statistics
    if processing_stats['patients_with_no_visits']:
        processing_messages.append(f"⚠️ {len(processing_stats['patients_with_no_visits'])} patient(s) skipped due to missing study definitions: {', '.join(processing_stats['patients_with_no_visits'])}")
        
    if processing_stats['recalculated_patients']:
        processing_messages.append(f"📅 Recalculated visit schedules for {len(processing_stats['recalculated_patients'])} patient(s) based on actual Day 1 baseline: {', '.join(processing_stats['recalculated_patients'])}")

    if processing_stats['out_of_window_visits']:
        processing_messages.append(f"🔴 {len(processing_stats['out_of_window_visits'])} visit(s) occurred outside tolerance windows (marked as OUT OF PROTOCOL)")

    if processing_stats['actual_visits_used'] > 0:
        processing_messages.append(f"✅ {processing_stats['actual_visits_used']} actual visits matched and used in calendar")

    if processing_stats['screen_fail_exclusions'] > 0:
        processing_messages.append(f"⚠️ {processing_stats['screen_fail_exclusions']} visits were excluded because they occur after screen failure dates")
    
    return processing_messages

def calculate_financial_totals(calendar_df):
    """Calculate monthly and financial year totals"""
    # Calculate monthly totals - cumulative within each month
    calendar_df["MonthPeriod"] = calendar_df["Date"].dt.to_period("M")
    calendar_df["Monthly Total"] = 0.0
    
    for month in calendar_df["MonthPeriod"].unique():
        month_mask = calendar_df["MonthPeriod"] == month
        month_data = calendar_df[month_mask].copy()
        month_data = month_data.sort_values("Date")
        month_data["Monthly Total"] = month_data["Daily Total"].cumsum()
        calendar_df.loc[month_mask, "Monthly Total"] = month_data["Monthly Total"].values

    # Calculate financial year totals - cumulative within each financial year
    calendar_df["FYStart"] = calendar_df["Date"].apply(get_financial_year_start_year)
    calendar_df["FY Total"] = 0.0
    
    for fy_year in calendar_df["FYStart"].unique():
        if pd.isna(fy_year):
            continue
        fy_mask = calendar_df["FYStart"] == fy_year
        fy_data = calendar_df[fy_mask].copy()
        fy_data = fy_data.sort_values("Date")
        fy_data["FY Total"] = fy_data["Daily Total"].cumsum()
        calendar_df.loc[fy_mask, "FY Total"] = fy_data["FY Total"].values
    
    return calendar_df
