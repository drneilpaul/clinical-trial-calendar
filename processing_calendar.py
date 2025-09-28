import pandas as pd
import streamlit as st
from datetime import timedelta
from helpers import (safe_string_conversion, standardize_visit_columns, validate_required_columns, 
                    get_financial_year_start_year, is_financial_year_end)

# Import from our new modules
from visit_processor import process_study_events, detect_screen_failures
from patient_processor import process_single_patient
from calendar_builder import build_calendar_dataframe, fill_calendar_with_visits

def build_calendar(patients_df, trials_df, actual_visits_df=None):
    """Enhanced calendar builder with study events support - Main orchestrator function"""
    
    # Clean columns
    patients_df.columns = patients_df.columns.str.strip()
    trials_df.columns = trials_df.columns.str.strip()
    if actual_visits_df is not None:
        actual_visits_df.columns = actual_visits_df.columns.str.strip()

    # Validate required columns
    validate_required_columns(patients_df, {"PatientID", "Study", "StartDate"}, "Patients file")
    validate_required_columns(trials_df, {"Study", "Day", "VisitName"}, "Trials file")

    # Standardize visit columns
    trials_df = standardize_visit_columns(trials_df)
    if actual_visits_df is not None:
        validate_required_columns(actual_visits_df, {"PatientID", "Study", "VisitName", "ActualDate"}, "Actual visits file")
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
    if visits_df.empty:
        raise ValueError("No visits generated. Check that Patient 'Study' matches Trial 'Study' values and StartDate is populated.")

    # Build processing messages
    processing_messages = build_processing_messages(processing_stats, unmatched_visits)

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
    
    if not pd.api.types.is_datetime64_any_dtype(actual_visits_df["ActualDate"]):
        actual_visits_df["ActualDate"] = pd.to_datetime(actual_visits_df["ActualDate"], dayfirst=True, errors="coerce")
    
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
    # Normalize column names
    column_mapping = {
        'Income': 'Payment',
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
            (trials_df['VisitType'] == 'patient') |
            (pd.isna(trials_df['VisitType']))
        ]
        
        study_event_templates = trials_df[
            trials_df['VisitType'].isin(['siv', 'monitor'])
        ]
    else:
        patient_visits = trials_df.copy()
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
    
    for _, patient in patients_df.iterrows():
        patient_id = str(patient["PatientID"])
        study = str(patient["Study"])
        
        visit_records, actual_visits_used, unmatched_visits, screen_fail_exclusions, out_of_window_visits, processing_messages, patient_needs_recalc = process_single_patient(
            patient, patient_visits, screen_failures, actual_visits_df
        )
        
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
    # Calculate monthly totals
    calendar_df["MonthPeriod"] = calendar_df["Date"].dt.to_period("M")
    monthly_totals = calendar_df.groupby("MonthPeriod")["Daily Total"].sum()
    calendar_df["IsMonthEnd"] = calendar_df["Date"] == calendar_df["Date"] + pd.offsets.MonthEnd(0)
    calendar_df["Monthly Total"] = calendar_df.apply(
        lambda r: monthly_totals.get(r["MonthPeriod"], 0.0) if r["IsMonthEnd"] else pd.NA, axis=1
    )

    # Calculate financial year totals
    calendar_df["FYStart"] = calendar_df["Date"].apply(get_financial_year_start_year)
    fy_totals = calendar_df.groupby("FYStart")["Daily Total"].sum()
    calendar_df["IsFYE"] = calendar_df["Date"].apply(is_financial_year_end)
    calendar_df["FY Total"] = calendar_df.apply(
        lambda r: fy_totals.get(r["FYStart"], 0.0) if r["IsFYE"] else pd.NA, axis=1
    )
    
    return calendar_df
