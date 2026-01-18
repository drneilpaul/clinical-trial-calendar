import pandas as pd
import streamlit as st
from datetime import timedelta
from helpers import (safe_string_conversion, standardize_visit_columns, validate_required_columns, 
                    get_financial_year_start_year, is_financial_year_end, log_activity, get_visit_type_series)
from payment_handler import normalize_payment_column, validate_payment_data

# Import from our new modules
from visit_processor import process_study_events, detect_screen_failures, detect_withdrawals, detect_patient_stoppages
from patient_processor import process_single_patient
from calendar_builder import build_calendar_dataframe, fill_calendar_with_visits
from profiling import timeit

# Dynamic processing debug flag - checks debug level at runtime
def _get_processing_debug():
    """Get PROCESSING_DEBUG flag value based on current debug level"""
    try:
        from config import should_log_debug
        return should_log_debug()
    except:
        return False

@timeit
def _build_calendar_impl(patients_df, trials_df, actual_visits_df=None, hide_inactive=False):
    """Enhanced calendar builder with study events support - Main orchestrator function"""
    
    # Clean columns - ensure they are strings before using .str accessor
    patients_df.columns = [str(col).strip() for col in patients_df.columns]
    trials_df.columns = [str(col).strip() for col in trials_df.columns]
    if actual_visits_df is not None:
        actual_visits_df.columns = [str(col).strip() for col in actual_visits_df.columns]

    # CHANGED: Remove the section that adds default columns silently
    # The validation layer now ensures these columns exist with valid data
    
    # Validate required columns - this will now fail fast if missing
    validate_required_columns(patients_df, {"PatientID", "Study", "StartDate", "PatientPractice"}, "Patients file")
    validate_required_columns(trials_df, {"Study", "Day", "VisitName", "SiteforVisit"}, "Trials file")

    # Standardize visit columns
    trials_df = standardize_visit_columns(trials_df)
    if actual_visits_df is not None:
        if _get_processing_debug():
            log_activity(f"Actual visits columns before processing: {list(actual_visits_df.columns)}", level='info')
            log_activity(f"Actual visits shape: {actual_visits_df.shape}", level='info')
        
        # Add missing columns with defaults before validation
        if 'VisitType' not in actual_visits_df.columns:
            actual_visits_df['VisitType'] = 'patient'
        
        # FIXED: Always run auto-detection, even if VisitType column exists
        # This fixes study events that were incorrectly saved with VisitType='patient'
        # If VisitName is 'SIV' or contains 'SIV', it's a site initiation visit
        siv_mask = (
            (actual_visits_df['VisitName'].astype(str).str.upper().str.strip() == 'SIV') &
            (actual_visits_df['VisitType'].astype(str).str.lower() != 'siv')  # Only fix if not already 'siv'
        )
        actual_visits_df.loc[siv_mask, 'VisitType'] = 'siv'
        
        # If VisitName contains 'Monitor' or 'Monitoring', it's a monitoring visit
        monitor_mask = (
            actual_visits_df['VisitName'].astype(str).str.contains('Monitor', case=False, na=False) &
            (actual_visits_df['VisitType'].astype(str).str.lower() != 'monitor')  # Only fix if not already 'monitor'
        )
        actual_visits_df.loc[monitor_mask, 'VisitType'] = 'monitor'
        
        # Log detected study events
        siv_count = siv_mask.sum()
        monitor_count = monitor_mask.sum()
        if siv_count > 0:
            log_activity(f"🔧 Corrected {siv_count} SIV event(s) from VisitName (were incorrectly marked as patient visits)", level='warning')
        if monitor_count > 0:
            log_activity(f"🔧 Corrected {monitor_count} Monitor event(s) from VisitName (were incorrectly marked as patient visits)", level='warning')
        
        if 'Notes' not in actual_visits_df.columns:
            actual_visits_df['Notes'] = ''
        
        if _get_processing_debug():
            log_activity(f"Actual visits columns after adding defaults: {list(actual_visits_df.columns)}", level='info')
        
        # Check for required columns with more detailed error message
        required_columns = {"PatientID", "Study", "VisitName", "ActualDate"}
        missing_columns = required_columns - set(actual_visits_df.columns)
        if missing_columns:
            log_activity(f"Missing required columns: {missing_columns}", level='error')
            log_activity(f"Available columns: {list(actual_visits_df.columns)}", level='error')
            raise ValueError(f"Actual visits file missing required columns: {', '.join(missing_columns)}")
        
        actual_visits_df = standardize_visit_columns(actual_visits_df)

    # REMOVED: SiteforVisit default handling - validation layer now ensures valid data

    # Prepare actual visits data
    unmatched_visits = []
    screen_failures = {}
    withdrawals = {}
    stoppages = {}  # Combined screen failures, withdrawals, and deaths
    
    if actual_visits_df is not None:
        actual_visits_df = prepare_actual_visits_data(actual_visits_df)
        screen_failures, screen_fail_unmatched = detect_screen_failures(actual_visits_df, trials_df)
        withdrawals, withdrawal_unmatched = detect_withdrawals(actual_visits_df, trials_df)
        stoppages, stoppage_unmatched = detect_patient_stoppages(actual_visits_df, trials_df)
        unmatched_visits.extend(screen_fail_unmatched)
        unmatched_visits.extend(withdrawal_unmatched)

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
    
    # Process patient visits (using stoppages which includes both screen failures and withdrawals)
    processing_stats = process_all_patients(
        patients_df, patient_visits, stoppages, actual_visits_df
    )
    
    visit_records.extend(processing_stats['visit_records'])
    
    # Create visits DataFrame
    visits_df = pd.DataFrame(visit_records)
    if _get_processing_debug():
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
        if _get_processing_debug():
            log_activity(f"Reset duplicate indices in visits DataFrame", level='info')
        visits_df = visits_df.reset_index(drop=True)

    # Build processing messages
    processing_messages = build_processing_messages(processing_stats, unmatched_visits)

    # DEBUG: Check visits_df state before building calendar
    if _get_processing_debug():
        log_activity(f"Building calendar with {len(visits_df)} visits", level='info')
    
    # Build calendar dataframe
    calendar_df, site_column_mapping, unique_visit_sites = build_calendar_dataframe(visits_df, patients_df, hide_inactive, actual_visits_df)
    
    # Fill calendar with visits
    calendar_df = fill_calendar_with_visits(calendar_df, visits_df, trials_df)

    # Calculate financial totals
    calendar_df = calculate_financial_totals(calendar_df)

    # Build stats
    stats = {
        "total_visits": len([v for v in visit_records if not v.get('IsActual', False) and v['Visit'] not in ['-', '+'] and not v.get('IsStudyEvent', False)]),
        "total_income": pd.to_numeric(visits_df.get("Payment", 0), errors="coerce").fillna(0).sum(),
        "messages": processing_messages,
        "out_of_window_visits": processing_stats['out_of_window_visits']
    }

    # DEBUG: Log visits_df SiteofVisit values to trace Kiltearn issue
    if not visits_df.empty and 'SiteofVisit' in visits_df.columns:
        site_values = visits_df['SiteofVisit'].dropna().unique()
        if _get_processing_debug():
            log_activity(f"🔍 DEBUG: visits_df SiteofVisit values: {list(site_values)}", level='info')
            
            # Count visits by site
            site_counts = visits_df['SiteofVisit'].value_counts()
            log_activity(f"🔍 DEBUG: visits by site: {dict(site_counts)}", level='info')
            
            # If Kiltearn is present, find the specific visits
            if 'Kiltearn' in site_values:
                kiltearn_visits = visits_df[visits_df['SiteofVisit'] == 'Kiltearn']
                if _get_processing_debug():
                    for idx, visit in kiltearn_visits.iterrows():
                        log_activity(f"🔍 DEBUG: Kiltearn visit - PatientID: {visit.get('PatientID')}, Visit: {visit.get('Visit')}, Date: {visit.get('Date')}", level='warning')

    return visits_df, calendar_df, stats, processing_messages, site_column_mapping, unique_visit_sites, patients_df


@st.cache_data(show_spinner=False)
@timeit
def _build_calendar_cached(patients_df, trials_df, actual_visits_df, cache_buster, hide_inactive):
    """Cached wrapper around the core calendar builder."""
    return _build_calendar_impl(patients_df, trials_df, actual_visits_df, hide_inactive)


def build_calendar(patients_df, trials_df, actual_visits_df=None, cache_buster=None, hide_inactive=False):
    """Public calendar builder with caching support."""
    if cache_buster is None:
        cache_buster = st.session_state.get('calendar_cache_buster', 0)
    return _build_calendar_cached(patients_df, trials_df, actual_visits_df, cache_buster, hide_inactive)


def clear_build_calendar_cache():
    """Clear cached calendar data."""
    clear_fn = getattr(_build_calendar_cached, "clear", None)
    if callable(clear_fn):
        clear_fn()
        return
    cache_clear_fn = getattr(_build_calendar_cached, "cache_clear", None)
    if callable(cache_clear_fn):
        cache_clear_fn()
        return
    # Fallback: clear all data caches if per-function clear is unavailable
    try:
        if hasattr(st.cache_data, "clear"):
            st.cache_data.clear()
    except Exception:
        pass

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
    
    # FIXED: Normalize all dates to consistent format for calendar matching
    # Convert to date-only timestamps to avoid timezone/time comparison issues
    actual_visits_df["ActualDate"] = pd.to_datetime(actual_visits_df["ActualDate"]).dt.normalize()
    if _get_processing_debug():
        log_activity(f"Normalized {len(actual_visits_df)} actual visit dates to date-only timestamps", level='info')
    
    if "Notes" not in actual_visits_df.columns:
        actual_visits_df["Notes"] = ""
    else:
        actual_visits_df["Notes"] = safe_string_conversion(actual_visits_df["Notes"], "")
    
    if "VisitType" not in actual_visits_df.columns:
        actual_visits_df["VisitType"] = "patient"
    

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
    
    # NEW: Validate SiteforVisit before processing
    if 'SiteforVisit' not in trials_df.columns:
        error_msg = "❌ DATA INTEGRITY ERROR: SiteforVisit column is missing from trials data. "
        error_msg += "All trial visits must specify the contract holder. "
        error_msg += "This should have been caught by validation - please check your data files."
        log_activity(error_msg, level='error')
        raise ValueError(error_msg)
    
    trials_df["SiteforVisit"] = safe_string_conversion(trials_df["SiteforVisit"], "")
    
    # Check for invalid values
    invalid_sites = ['', 'nan', 'None', 'null', 'NULL', 'Unknown Site', 'unknown site', 'UNKNOWN SITE', 'Default Site']
    invalid_mask = trials_df['SiteforVisit'].isin(invalid_sites)
    
    if invalid_mask.any():
        # Create error message without assuming Day column exists yet
        invalid_count = invalid_mask.sum()
        invalid_studies = trials_df[invalid_mask]['Study'].unique()[:5]
        error_msg = f"❌ DATA INTEGRITY ERROR: {invalid_count} trial visit(s) have invalid SiteforVisit. "
        error_msg += f"Affected studies: {', '.join(map(str, invalid_studies))}"
        if len(trials_df[invalid_mask]['Study'].unique()) > 5:
            error_msg += f" and {len(trials_df[invalid_mask]['Study'].unique()) - 5} more"
        error_msg += ". All visits must specify the contract holder (Ashfields, Kiltearn, etc)."
        log_activity(error_msg, level='error')
        raise ValueError(error_msg)
    # END NEW VALIDATION
    
    try:
        trials_df["Day"] = pd.to_numeric(trials_df["Day"], errors='coerce').fillna(1).astype(int)
    except:
        st.error("Invalid 'Day' values in trials file. Days must be numeric.")
        raise ValueError("Invalid Day column in trials file")

    # Optional interval-based scheduling columns
    try:
        if 'IntervalUnit' in trials_df.columns:
            trials_df['IntervalUnit'] = trials_df['IntervalUnit'].astype(str).str.strip().str.lower()
            # Normalize common variants; keep only 'month' or 'day'
            valid_units = {'month', 'day', '', 'nan', 'none'}
            invalid_mask = ~trials_df['IntervalUnit'].isin(valid_units)
            if invalid_mask.any():
                log_activity(f"Unsupported IntervalUnit values found and ignored: {trials_df.loc[invalid_mask, 'IntervalUnit'].unique().tolist()}", level='warning')
                trials_df.loc[invalid_mask, 'IntervalUnit'] = ''
        if 'IntervalValue' in trials_df.columns:
            # Coerce to integers when possible
            trials_df['IntervalValue'] = pd.to_numeric(trials_df['IntervalValue'], errors='coerce')
            # Leave NaN for rows where it's not applicable; handled downstream
    except Exception as e:
        log_activity(f"Interval parsing warning: {e}", level='warning')
    
    return trials_df

def prepare_patients_data(patients_df, trials_df):
    """Prepare patients data with proper data types and site mapping"""
    # Process data types
    patients_df["PatientID"] = safe_string_conversion(patients_df["PatientID"])
    patients_df["Study"] = safe_string_conversion(patients_df["Study"])
    
    if not pd.api.types.is_datetime64_any_dtype(patients_df["StartDate"]):
        patients_df["StartDate"] = pd.to_datetime(patients_df["StartDate"], dayfirst=True, errors="coerce")

    if _get_processing_debug():
        log_activity(f"Patients columns: {list(patients_df.columns)}", level='info')
        log_activity(f"Trials columns: {list(trials_df.columns)}", level='info')
        if 'SiteforVisit' in trials_df.columns:
            log_activity(f"SiteforVisit values: {trials_df['SiteforVisit'].unique()}", level='info')
    elif 'SiteforVisit' not in trials_df.columns:
        log_activity("No SiteforVisit column in trials data", level='warning')

    # Clean up redundant columns - remove Site and OriginSite if they exist
    # The real source of truth should be PatientPractice
    if 'Site' in patients_df.columns:
        if _get_processing_debug():
            log_activity("Removing redundant 'Site' column", level='info')
        patients_df = patients_df.drop('Site', axis=1)
    
    if 'OriginSite' in patients_df.columns:
        if _get_processing_debug():
            log_activity("Removing redundant 'OriginSite' column", level='info')
        patients_df = patients_df.drop('OriginSite', axis=1)
    
    # CHANGED: Raise error instead of silently defaulting to 'Unknown Site'
    if 'PatientPractice' not in patients_df.columns:
        error_msg = "❌ DATA INTEGRITY ERROR: PatientPractice column is missing from patients data. "
        error_msg += "All patients must have a recruitment site (Ashfields or Kiltearn). "
        error_msg += "This should have been caught by validation - please check your data files."
        log_activity(error_msg, level='error')
        raise ValueError(error_msg)
    
    # Validate that all patients have valid PatientPractice values
    patients_df['PatientPractice'] = safe_string_conversion(patients_df['PatientPractice'], "")
    
    # Check for invalid values
    invalid_sites = ['', 'nan', 'None', 'null', 'NULL', 'Unknown Site', 'unknown site', 'UNKNOWN SITE']
    invalid_mask = patients_df['PatientPractice'].isin(invalid_sites)
    
    if invalid_mask.any():
        invalid_patients = patients_df[invalid_mask]['PatientID'].tolist()
        error_msg = f"❌ DATA INTEGRITY ERROR: {len(invalid_patients)} patient(s) have invalid PatientPractice. "
        error_msg += f"Invalid patients: {', '.join(map(str, invalid_patients[:10]))}"
        if len(invalid_patients) > 10:
            error_msg += f" and {len(invalid_patients) - 10} more"
        error_msg += ". All patients must have recruitment site (Ashfields or Kiltearn)."
        log_activity(error_msg, level='error')
        raise ValueError(error_msg)
    
    if _get_processing_debug():
        log_activity(f"PatientPractice values: {patients_df['PatientPractice'].unique()}", level='info')

    # Ensure SiteSeenAt exists (visit location). Default to PatientPractice if missing.
    if 'SiteSeenAt' not in patients_df.columns:
        log_activity("SiteSeenAt missing in patients data; defaulting to PatientPractice", level='warning')
        patients_df['SiteSeenAt'] = patients_df['PatientPractice']
    else:
        patients_df['SiteSeenAt'] = safe_string_conversion(patients_df['SiteSeenAt'], "")
        invalid_sites = ['', 'nan', 'None', 'null', 'NULL', 'Unknown Site', 'unknown site', 'UNKNOWN SITE']
        invalid_mask = patients_df['SiteSeenAt'].isin(invalid_sites)
        if invalid_mask.any():
            invalid_patients = patients_df[invalid_mask]['PatientID'].tolist()
            error_msg = f"❌ DATA INTEGRITY ERROR: {len(invalid_patients)} patient(s) have invalid SiteSeenAt. "
            error_msg += f"Invalid patients: {', '.join(map(str, invalid_patients[:10]))}"
            if len(invalid_patients) > 10:
                error_msg += f" and {len(invalid_patients) - 10} more"
            error_msg += ". All patients must have visit site (SiteSeenAt)."
            log_activity(error_msg, level='error')
            raise ValueError(error_msg)
    
    return patients_df

def validate_study_structure(patients_df, trials_df):
    """Validate that each study has proper Day 1 baseline"""
    # OPTIMIZED: Use groupby to process all studies at once (2-3x faster than loop)
    # Only validate studies that have patients
    studies_to_validate = patients_df["Study"].unique()
    study_groups = trials_df[trials_df["Study"].isin(studies_to_validate)].groupby("Study")
    
    for study, study_visits in study_groups:
        day_1_visits = study_visits[study_visits["Day"] == 1]
        
        if len(day_1_visits) == 0:
            raise ValueError(f"Study {study} has no Day 1 visit defined. Day 1 is required as baseline.")
        elif len(day_1_visits) > 1:
            visit_names = day_1_visits["VisitName"].tolist()
            raise ValueError(f"Study {study} has multiple Day 1 visits: {visit_names}. Only one Day 1 visit allowed.")

def separate_visit_types(trials_df):
    """Separate patient visits from study events"""
    from helpers import get_visit_type_series
    
    # Ensure VisitType column exists and fill None values (add it if missing, infer from VisitName)
    visit_type_col = None
    if 'VisitType' in trials_df.columns:
        visit_type_col = 'VisitType'
    elif 'visit_type' in trials_df.columns:
        visit_type_col = 'visit_type'
    elif 'visitType' in trials_df.columns:
        visit_type_col = 'visitType'
    
    if visit_type_col is None:
        # Column doesn't exist - create it
        trials_df = trials_df.copy()
        trials_df['VisitType'] = 'patient'  # Default to patient
        
        # Auto-detect SIVs
        siv_mask = trials_df['VisitName'].astype(str).str.upper().str.strip() == 'SIV'
        trials_df.loc[siv_mask, 'VisitType'] = 'siv'
        
        # Auto-detect Monitors
        monitor_mask = trials_df['VisitName'].astype(str).str.contains('Monitor', case=False, na=False)
        trials_df.loc[monitor_mask, 'VisitType'] = 'monitor'
    else:
        # Column exists but may have None values - fill them
        trials_df = trials_df.copy()
        # Fill None/null/empty values with 'patient' default
        none_mask = (
            trials_df[visit_type_col].isna() |
            (trials_df[visit_type_col].astype(str).str.strip().isin(['', 'None', 'nan', 'null', 'NULL']))
        )
        trials_df.loc[none_mask, visit_type_col] = 'patient'
        
        # Auto-detect SIVs from VisitName (even if VisitType is set to patient)
        siv_mask = (
            (trials_df['VisitName'].astype(str).str.upper().str.strip() == 'SIV') &
            (trials_df[visit_type_col].astype(str).str.lower() != 'siv')
        )
        trials_df.loc[siv_mask, visit_type_col] = 'siv'
        
        # Auto-detect Monitors from VisitName
        monitor_mask = (
            trials_df['VisitName'].astype(str).str.contains('Monitor', case=False, na=False) &
            (~trials_df[visit_type_col].astype(str).str.lower().isin(['monitor']))
        )
        trials_df.loc[monitor_mask, visit_type_col] = 'monitor'
    
    visit_types = get_visit_type_series(trials_df, default='patient')
    patient_mask = visit_types.isin(['patient', 'extra'])
    patient_visits = trials_df[patient_mask].copy()
    
    study_event_templates = trials_df[visit_types.isin(['siv', 'monitor'])].copy()
    
    # Ensure VisitType is in the resulting dataframes for matching
    if 'VisitType' not in patient_visits.columns:
        patient_visits['VisitType'] = get_visit_type_series(patient_visits, default='patient')
    if 'VisitType' not in study_event_templates.columns and not study_event_templates.empty:
        study_event_templates['VisitType'] = get_visit_type_series(study_event_templates, default='patient')
    
    return patient_visits, study_event_templates

@timeit
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
    
    # OPTIMIZED: Process patients and generate visits using itertuples (faster than iterrows)
    # itertuples() is 2-3x faster than iterrows() because it returns namedtuples instead of Series
    
    for patient_tuple in patients_df.itertuples():
        patient_id = str(patient_tuple.PatientID)
        study = str(patient_tuple.Study)
        
        # Convert tuple to dict-like object for process_single_patient compatibility
        patient = {
            "PatientID": patient_tuple.PatientID,
            "Study": patient_tuple.Study,
            "StartDate": patient_tuple.StartDate,
            "PatientPractice": getattr(patient_tuple, 'PatientPractice', ''),
            "SiteSeenAt": getattr(patient_tuple, 'SiteSeenAt', None)
        }
        
        visit_records, actual_visits_used, unmatched_visits, screen_fail_exclusions, out_of_window_visits, processing_messages, patient_needs_recalc = process_single_patient(
            patient, patient_visits, screen_failures, actual_visits_df
        )
        
        if _get_processing_debug():
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
    
    if _get_processing_debug():
        log_activity(f"✅ Generated {len(all_visit_records)} visit records from {len(patients_df)} patients", level='info')
    if patients_with_no_visits:
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
        processing_messages.append(f"⚠️ {processing_stats['screen_fail_exclusions']} visits were excluded because they occur after screen failure or withdrawal dates")
    
    return processing_messages

@timeit
def calculate_financial_totals(calendar_df):
    """
    Calculate monthly and financial year totals using vectorized operations.
    
    OPTIMIZATION: Uses groupby().cumsum() instead of loops (2-3x faster)
    CRITICAL: Must sort by Date before cumsum to ensure correct cumulative totals
    """
    # Add period columns
    calendar_df["MonthPeriod"] = calendar_df["Date"].dt.to_period("M")
    
    # CRITICAL: Sort by date BEFORE cumsum operations
    # Without this, cumulative totals will be incorrect
    calendar_df = calendar_df.sort_values("Date").reset_index(drop=True)
    
    # Calculate monthly cumulative totals using vectorized groupby
    # This replaces the month loop (2-3x faster)
    calendar_df["Monthly Total"] = (
        calendar_df.groupby("MonthPeriod", observed=True)["Daily Total"]
        .cumsum()
        .fillna(0.0)
    )
    
    # Calculate financial year totals - cumulative within each financial year
    from helpers import get_financial_year_start_year_for_series
    calendar_df["FYStart"] = get_financial_year_start_year_for_series(calendar_df["Date"])
    
    # Calculate FY cumulative totals using vectorized groupby
    # This replaces the FY loop (2-3x faster)
    calendar_df["FY Total"] = (
        calendar_df.groupby("FYStart", observed=True)["Daily Total"]
        .cumsum()
        .fillna(0.0)
    )
    
    return calendar_df
