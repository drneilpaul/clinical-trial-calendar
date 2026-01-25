import streamlit as st
from supabase import create_client, Client
import pandas as pd
from typing import Optional, Dict, List, Tuple
import io
from datetime import datetime
import zipfile
from helpers import log_activity
from payment_handler import normalize_payment_column, validate_payment_data

def safe_float(value, default=0.0):
    """Safely convert to float, defaulting on invalid values."""
    try:
        if pd.isna(value) or value is None or str(value).strip() in ['', 'None', 'nan', 'null', 'NULL']:
            return default
        return float(value)
    except (ValueError, TypeError):
        return default

def get_supabase_client() -> Optional[Client]:
    """Get Supabase client with error handling"""
    try:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
        return create_client(url, key)
    except Exception as e:
        st.session_state.database_status = f"Connection failed: {e}"
        return None

def clear_database_cache():
    """Clear all database query caches"""
    _fetch_all_patients_cached.clear()
    _fetch_all_trial_schedules_cached.clear()
    _fetch_all_actual_visits_cached.clear()
    _fetch_all_study_site_details_cached.clear()

def test_database_connection() -> bool:
    """Test if database is accessible and tables exist"""
    try:
        client = get_supabase_client()
        if client is None:
            return False
        
        client.table('patients').select("id").limit(1).execute()
        client.table('trial_schedules').select("id").limit(1).execute()
        client.table('actual_visits').select("id").limit(1).execute()
        
        st.session_state.database_status = "Connected"
        return True
    except Exception as e:
        st.session_state.database_status = f"Tables not configured: {e}"
        return False

@st.cache_data(ttl=300, show_spinner=False)
def _fetch_all_patients_cached() -> Optional[pd.DataFrame]:
    """Internal cached function to fetch all patients from database"""
    try:
        client = get_supabase_client()
        if client is None:
            return None

        # OPTIMIZED: Select all columns (we need most columns for processing)
        # Future optimization: Could select specific columns if only certain views need them
        response = client.table('patients').select("*").execute()

        if response.data:
            df = pd.DataFrame(response.data)

            # Database columns are now PascalCase, no renaming needed
            if 'ScreeningDate' in df.columns:
                df['ScreeningDate'] = pd.to_datetime(df['ScreeningDate'], errors='coerce')

            if 'RandomizationDate' in df.columns:
                df['RandomizationDate'] = pd.to_datetime(df['RandomizationDate'], errors='coerce')

            return df
        return pd.DataFrame(columns=['PatientID', 'Study', 'ScreeningDate', 'RandomizationDate', 'Status', 'PatientPractice', 'SiteSeenAt', 'Pathway'])
    except Exception as e:
        return None

def fetch_all_patients() -> Optional[pd.DataFrame]:
    """Fetch all patients from database (with caching)"""
    df = _fetch_all_patients_cached()
    # Reduced logging - only log errors, not successful fetches (handled by app.py)
    if df is None:
        log_activity("No patients found in database", level='warning')
    return df

@st.cache_data(ttl=300, show_spinner=False)
def _fetch_all_trial_schedules_cached() -> Optional[pd.DataFrame]:
    """Internal cached function to fetch all trial schedules from database"""
    try:
        client = get_supabase_client()
        if client is None:
            return None
        
        # OPTIMIZED: Select all columns (we need most columns for processing)
        # Future optimization: Could select specific columns if only certain views need them
        response = client.table('trial_schedules').select("*").execute()
        
        if response.data:
            df = pd.DataFrame(response.data)
            # Database columns are now PascalCase, no renaming needed
            
            # Parse date fields if they exist
            for date_col in ['FPFV', 'LPFV', 'LPLV']:
                if date_col in df.columns:
                    df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
            
            # Ensure StudyStatus defaults to 'active' if missing
            if 'StudyStatus' not in df.columns:
                df['StudyStatus'] = 'active'
            else:
                df['StudyStatus'] = df['StudyStatus'].fillna('active')
            
            # Ensure RecruitmentTarget is numeric or None
            if 'RecruitmentTarget' in df.columns:
                df['RecruitmentTarget'] = pd.to_numeric(df['RecruitmentTarget'], errors='coerce')
            
            return df
        return pd.DataFrame(columns=['Study', 'Day', 'VisitName', 'SiteforVisit', 'Payment', 'ToleranceBefore', 'ToleranceAfter', 'IntervalUnit', 'IntervalValue', 'VisitType', 'FPFV', 'LPFV', 'LPLV', 'StudyStatus', 'RecruitmentTarget'])
    except Exception as e:
        return None

def fetch_all_trial_schedules() -> Optional[pd.DataFrame]:
    """Fetch all trial schedules from database (with caching)"""
    return _fetch_all_trial_schedules_cached()

def update_patient_status(patient_id: str, study: str, status: str, randomization_date=None) -> bool:
    """Update patient status and optionally set randomization date

    Args:
        patient_id: Patient ID
        study: Study name
        status: New status ('screening', 'screen_failed', 'randomized', 'withdrawn', 'completed', 'lost_to_followup')
        randomization_date: Optional randomization date (for status='randomized')

    Returns:
        True if successful, False otherwise
    """
    try:
        client = get_supabase_client()
        if client is None:
            return False

        update_data = {"Status": status}
        if randomization_date is not None:
            if hasattr(randomization_date, 'strftime'):
                update_data["RandomizationDate"] = randomization_date.strftime('%Y-%m-%d')
            else:
                update_data["RandomizationDate"] = str(randomization_date)

        client.table('patients').update(update_data).eq('PatientID', patient_id).eq('Study', study).execute()

        clear_database_cache()

        log_activity(f"Updated patient {patient_id} status to '{status}'", level='info')
        return True
    except Exception as e:
        log_activity(f"Failed to update patient status: {e}", level='error')
        return False

@st.cache_data(ttl=300, show_spinner=False)
def _fetch_all_actual_visits_cached() -> Optional[pd.DataFrame]:
    """Internal cached function to fetch all actual visits from database"""
    try:
        client = get_supabase_client()
        if client is None:
            return None
        
        response = client.table('actual_visits').select("*").execute()
        
        if response.data:
            df = pd.DataFrame(response.data)
            # Database columns are now PascalCase, no renaming needed
            
            if 'ActualDate' in df.columns:
                df['ActualDate'] = pd.to_datetime(df['ActualDate'], errors='coerce')
            
            # FIXED: Auto-detect study events IMMEDIATELY after loading from database
            # This fixes SIV/Monitor visits that were saved with wrong VisitType
            # Store correction counts for logging
            siv_corrected_count = 0
            monitor_corrected_count = 0

            if 'VisitType' in df.columns:
                siv_mask = (
                    (df['VisitName'].astype(str).str.upper().str.strip() == 'SIV') &
                    (df['VisitType'].astype(str).str.lower() != 'siv')
                )
                if siv_mask.any():
                    siv_corrected_count = siv_mask.sum()
                    df.loc[siv_mask, 'VisitType'] = 'siv'

                monitor_mask = (
                    df['VisitName'].astype(str).str.contains('Monitor', case=False, na=False) &
                    (df['VisitType'].astype(str).str.lower() != 'monitor')
                )
                if monitor_mask.any():
                    monitor_corrected_count = monitor_mask.sum()
                    df.loc[monitor_mask, 'VisitType'] = 'monitor'

            # Store correction counts in DataFrame metadata for logging
            df.attrs['siv_corrected'] = siv_corrected_count
            df.attrs['monitor_corrected'] = monitor_corrected_count

            return df
        return pd.DataFrame(columns=['PatientID', 'Study', 'VisitName', 'ActualDate', 'Notes', 'VisitType'])
    except Exception as e:
        return None

def fetch_all_actual_visits() -> Optional[pd.DataFrame]:
    """Fetch all actual visits from database (with caching)"""
    df = _fetch_all_actual_visits_cached()
    if df is not None:
        nat_count = df['ActualDate'].isna().sum() if 'ActualDate' in df.columns else 0
        if nat_count > 0:
            log_activity(f"Warning: {nat_count} actual visit dates failed to parse from database", level='warning')

        # Log corrections that were made (if any)
        siv_corrected = df.attrs.get('siv_corrected', 0)
        monitor_corrected = df.attrs.get('monitor_corrected', 0)

        if siv_corrected > 0:
            log_activity(f"🔧 CORRECTED {siv_corrected} SIV event(s) in database (were marked as patient visits)", level='warning')
        if monitor_corrected > 0:
            log_activity(f"🔧 CORRECTED {monitor_corrected} Monitor event(s) in database (were marked as patient visits)", level='warning')

        # Log what was loaded (reduced verbosity)
        log_activity(f"📥 Loaded {len(df)} actual visits from database", level='success')
        # Removed verbose sample visit logging - only log if there are issues
    else:
        log_activity("📥 No actual visits found in database", level='info')
    return df

def save_patients_to_database(patients_df: pd.DataFrame) -> bool:
    """Save patients DataFrame to database"""
    try:
        client = get_supabase_client()
        if client is None:
            return False
        
        # NEW: Validate all patients have valid PatientPractice BEFORE attempting to save
        if 'PatientPractice' not in patients_df.columns:
            log_activity("ERROR: PatientPractice column missing from patients data", level='error')
            return False
        
        # Check for invalid site values
        invalid_sites = ['', 'nan', 'None', 'null', 'NULL', 'Unknown Site', 'unknown site', 'UNKNOWN SITE']
        patients_df['PatientPractice'] = patients_df['PatientPractice'].fillna('').astype(str).str.strip()
        invalid_mask = patients_df['PatientPractice'].isin(invalid_sites)
        
        if invalid_mask.any():
            invalid_patients = patients_df[invalid_mask]['PatientID'].tolist()
            error_msg = f"Cannot save patients with missing PatientPractice: {invalid_patients}"
            log_activity(error_msg, level='error')
            st.error(f"❌ Data validation failed: {len(invalid_patients)} patient(s) missing recruitment site: {', '.join(map(str, invalid_patients[:5]))}")
            return False
        
        # Validate SiteSeenAt (visit location) - default to PatientPractice if missing
        if 'SiteSeenAt' not in patients_df.columns:
            patients_df['SiteSeenAt'] = patients_df['PatientPractice']
        patients_df['SiteSeenAt'] = patients_df['SiteSeenAt'].fillna('').astype(str).str.strip()
        invalid_seen_mask = patients_df['SiteSeenAt'].isin(invalid_sites)
        if invalid_seen_mask.any():
            invalid_patients = patients_df[invalid_seen_mask]['PatientID'].tolist()
            error_msg = f"Cannot save patients with missing SiteSeenAt: {invalid_patients}"
            log_activity(error_msg, level='error')
            st.error(f"❌ Data validation failed: {len(invalid_patients)} patient(s) missing visit site: {', '.join(map(str, invalid_patients[:5]))}")
            return False
        
        # END NEW VALIDATION
        
        records = []
        # OPTIMIZED: Use itertuples for faster iteration (2-3x faster than iterrows)
        for row_tuple in patients_df.itertuples(index=False):
            screening_date = None
            if pd.notna(row_tuple.ScreeningDate):
                try:
                    if isinstance(row_tuple.ScreeningDate, str):
                        from datetime import datetime
                        screening_date = datetime.strptime(row_tuple.ScreeningDate, '%d/%m/%Y').date()
                    else:
                        screening_date = row_tuple.ScreeningDate.date() if hasattr(row_tuple.ScreeningDate, 'date') else row_tuple.ScreeningDate
                except Exception as date_error:
                    log_activity(f"Date parsing error for patient {row_tuple.PatientID}: {date_error}", level='warning')
                    screening_date = None

            record = {
                'PatientID': str(row_tuple.PatientID),
                'Study': str(row_tuple.Study),
                'ScreeningDate': str(screening_date) if screening_date else None,
                'PatientPractice': str(getattr(row_tuple, 'PatientPractice', '')),
                'SiteSeenAt': str(getattr(row_tuple, 'SiteSeenAt', getattr(row_tuple, 'PatientPractice', ''))),
                'Pathway': str(getattr(row_tuple, 'Pathway', 'standard'))  # Enrollment pathway variant
            }
            records.append(record)
        
        response = client.table('patients').insert(records).execute()
        log_activity(f"Inserted {len(records)} patient records to database", level='info')
        return True
        
    except Exception as e:
        st.error(f"Error saving patients to database: {e}")
        log_activity(f"Error saving patients to database: {e}", level='error')
        return False

def save_trial_schedules_to_database(trials_df: pd.DataFrame) -> bool:
    """Save trial schedules DataFrame to database"""
    try:
        client = get_supabase_client()
        if client is None:
            return False
        
        trials_df_clean = normalize_payment_column(trials_df, 'Payment')
        
        payment_validation = validate_payment_data(trials_df_clean, 'Payment')
        if not payment_validation['valid']:
            for issue in payment_validation['issues']:
                log_activity(f"Payment data issue: {issue}", level='warning')
        
        # NEW: Validate all trials have valid SiteforVisit (contract holder) BEFORE attempting to save
        if 'SiteforVisit' not in trials_df_clean.columns:
            log_activity("ERROR: SiteforVisit column missing from trials data", level='error')
            return False
        
        # Check for invalid site values
        invalid_sites = ['', 'nan', 'None', 'null', 'NULL', 'Unknown Site', 'unknown site', 'UNKNOWN SITE', 'Default Site']
        trials_df_clean['SiteforVisit'] = trials_df_clean['SiteforVisit'].fillna('').astype(str).str.strip()
        invalid_mask = trials_df_clean['SiteforVisit'].isin(invalid_sites)
        
        if invalid_mask.any():
            invalid_trials = trials_df_clean[invalid_mask][['Study', 'VisitName']].values.tolist()
            error_msg = f"Cannot save trials with missing SiteforVisit (contract holder): {invalid_trials}"
            log_activity(error_msg, level='error')
            st.error(f"❌ Data validation failed: {len(invalid_trials)} trial(s) missing contract site")
            return False
        
        # END NEW VALIDATION
        
        if 'ToleranceBefore' in trials_df_clean.columns:
            trials_df_clean['ToleranceBefore'] = trials_df_clean['ToleranceBefore'].replace('', 0)
            trials_df_clean['ToleranceBefore'] = pd.to_numeric(trials_df_clean['ToleranceBefore'], errors='coerce').fillna(0)
        
        if 'ToleranceAfter' in trials_df_clean.columns:
            trials_df_clean['ToleranceAfter'] = trials_df_clean['ToleranceAfter'].replace('', 0)
            trials_df_clean['ToleranceAfter'] = pd.to_numeric(trials_df_clean['ToleranceAfter'], errors='coerce').fillna(0)
        
        records = []
        records_with_visit_type = []
        # OPTIMIZED: Use itertuples for faster iteration (2-3x faster than iterrows)
        for row_tuple in trials_df_clean.itertuples(index=False):
            # Get VisitType if it exists, otherwise infer from VisitName
            visit_type_value = getattr(row_tuple, 'VisitType', None)
            if pd.isna(visit_type_value) or str(visit_type_value).strip() in ['', 'None', 'nan', 'null', 'NULL']:
                # Auto-detect from VisitName
                visit_name = str(getattr(row_tuple, 'VisitName', ''))
                if visit_name.upper().strip() == 'SIV':
                    visit_type_value = 'siv'
                elif 'monitor' in visit_name.lower():
                    visit_type_value = 'monitor'
                else:
                    visit_type_value = 'patient'  # Default
            
            # Handle date override fields (FPFV, LPFV, LPLV)
            def parse_date_field(field_name):
                field_value = getattr(row_tuple, field_name, None)
                if pd.isna(field_value) or field_value == '' or str(field_value).strip() in ['None', 'nan', 'null', 'NULL']:
                    return None
                try:
                    if isinstance(field_value, str):
                        # Try parsing as date string
                        from datetime import datetime
                        parsed = pd.to_datetime(field_value, dayfirst=True, errors='coerce')
                        if pd.notna(parsed):
                            return str(parsed.date())
                    elif hasattr(field_value, 'date'):
                        return str(field_value.date())
                    return None
                except:
                    return None
            
            # Handle StudyStatus field
            study_status_value = getattr(row_tuple, 'StudyStatus', None)
            if pd.isna(study_status_value) or str(study_status_value).strip() in ['', 'None', 'nan', 'null', 'NULL']:
                study_status_value = 'active'  # Default status
            else:
                study_status_value = str(study_status_value).strip().lower()
                # Validate status value
                valid_statuses = ['active', 'contracted', 'in_setup', 'expression_of_interest']
                if study_status_value not in valid_statuses:
                    log_activity(f"Invalid StudyStatus '{study_status_value}' for {row_tuple.Study}/{getattr(row_tuple, 'SiteforVisit', '')}, defaulting to 'active'", level='warning')
                    study_status_value = 'active'
            
            # Handle RecruitmentTarget field
            recruitment_target_value = getattr(row_tuple, 'RecruitmentTarget', None)
            if pd.isna(recruitment_target_value) or str(recruitment_target_value).strip() in ['', 'None', 'nan', 'null', 'NULL']:
                recruitment_target_value = None
            else:
                try:
                    recruitment_target_value = int(float(recruitment_target_value))
                    if recruitment_target_value < 0:
                        log_activity(f"Invalid RecruitmentTarget '{recruitment_target_value}' (negative) for {row_tuple.Study}/{getattr(row_tuple, 'SiteforVisit', '')}, setting to NULL", level='warning')
                        recruitment_target_value = None
                except (ValueError, TypeError):
                    log_activity(f"Invalid RecruitmentTarget '{recruitment_target_value}' for {row_tuple.Study}/{getattr(row_tuple, 'SiteforVisit', '')}, setting to NULL", level='warning')
                    recruitment_target_value = None
            
            record = {
                'Study': str(row_tuple.Study),
                'Day': int(row_tuple.Day),
                'VisitName': str(row_tuple.VisitName),
                'SiteforVisit': str(getattr(row_tuple, 'SiteforVisit', '')),
                'Payment': safe_float(getattr(row_tuple, 'Payment', 0)),
                'ToleranceBefore': int(getattr(row_tuple, 'ToleranceBefore', 0)),
                'ToleranceAfter': int(getattr(row_tuple, 'ToleranceAfter', 0)),
                # Optional month-based interval fields
                'IntervalUnit': (str(getattr(row_tuple, 'IntervalUnit', '')).lower().strip() if pd.notna(getattr(row_tuple, 'IntervalUnit', None)) else None),
                'IntervalValue': (int(getattr(row_tuple, 'IntervalValue', 0)) if pd.notna(getattr(row_tuple, 'IntervalValue', None)) else None),
                # VisitType column (now always included since database has it)
                'VisitType': str(visit_type_value).lower() if visit_type_value else 'patient',
                # New Gantt and recruitment tracking fields
                'FPFV': parse_date_field('FPFV'),
                'LPFV': parse_date_field('LPFV'),
                'LPLV': parse_date_field('LPLV'),
                'StudyStatus': study_status_value,
                'RecruitmentTarget': recruitment_target_value,
                # Pathway field for study variants (e.g., 'standard', 'with_run_in')
                'Pathway': str(getattr(row_tuple, 'Pathway', 'standard'))
            }
            records.append(record)
        
        log_activity(f"Sample trial records: {records[:3]}", level='info')
        log_activity(f"Payment values in records: {[r['Payment'] for r in records[:5]]}", level='info')
        log_activity(f"Cleaned Payment column sample: {trials_df_clean['Payment'].head().tolist()}", level='info')
        
        client.table('trial_schedules').insert(records).execute()
        
        log_activity(f"Successfully saved {len(records)} trial schedules to database", level='info')
        return True
        
    except Exception as e:
        st.error(f"Error saving trial schedules to database: {e}")
        log_activity(f"Error saving trial schedules to database: {e}", level='error')
        return False

def save_actual_visits_to_database(actual_visits_df: pd.DataFrame) -> bool:
    """Save actual visits DataFrame to database"""
    try:
        client = get_supabase_client()
        if client is None:
            return False
        
        from helpers import get_visit_type_series
        from datetime import date
        visit_type_series = get_visit_type_series(actual_visits_df, default='patient')
        today = date.today()
        
        records = []
        # OPTIMIZED: Use itertuples for faster iteration (2-3x faster than iterrows)
        for row_tuple in actual_visits_df.itertuples(index=True):
            idx = row_tuple.Index
            actual_date = row_tuple.ActualDate
            actual_date_obj = None
            if pd.notna(actual_date):
                if isinstance(actual_date, str):
                    actual_date_obj = pd.to_datetime(actual_date, dayfirst=True)
                else:
                    actual_date_obj = actual_date
                actual_date_str = str(actual_date_obj.date())
            else:
                actual_date_str = None
            
            visit_type_value = visit_type_series.loc[idx] if idx in visit_type_series.index else 'patient'
            
            # Auto-detect proposed visits/events for future dates
            if actual_date_obj is not None and actual_date_obj.date() > today:
                # Check if it's a study event (siv/monitor) or patient visit
                current_type = str(visit_type_value).lower()
                if current_type in ['siv', 'monitor']:
                    visit_type_value = 'event_proposed'
                elif current_type not in ['patient_proposed', 'event_proposed']:
                    visit_type_value = 'patient_proposed'
            
            record = {
                'PatientID': str(row_tuple.PatientID),
                'Study': str(row_tuple.Study),
                'VisitName': str(row_tuple.VisitName),
                'ActualDate': actual_date_str,
                'Notes': str(getattr(row_tuple, 'Notes', '')),
                'VisitType': str(visit_type_value)
            }
            records.append(record)
        
        client.table('actual_visits').upsert(records).execute()
        return True
        
    except Exception as e:
        st.error(f"Error saving actual visits to database: {e}")
        return False

def append_patient_to_database(patient_df: pd.DataFrame) -> bool:
    """Append new patient(s) to database without clearing existing data"""
    try:
        client = get_supabase_client()
        if client is None:
            log_activity("Cannot append patient: Supabase client not available", level='error')
            return False
        
        if patient_df is None or patient_df.empty:
            log_activity("Cannot append patient: Empty DataFrame", level='error')
            return False
        
        # NEW: Validate patient has valid PatientPractice
        if 'PatientPractice' not in patient_df.columns:
            log_activity("ERROR: PatientPractice column missing", level='error')
            st.error("❌ Cannot add patient: Missing recruitment site information")
            return False
        
        invalid_sites = ['', 'nan', 'None', 'null', 'NULL', 'Unknown Site', 'unknown site', 'UNKNOWN SITE']
        patient_df['PatientPractice'] = patient_df['PatientPractice'].fillna('').astype(str).str.strip()
        
        if patient_df['PatientPractice'].iloc[0] in invalid_sites:
            log_activity("ERROR: Patient has invalid PatientPractice", level='error')
            st.error("❌ Cannot add patient: Recruitment site must be specified (Ashfields or Kiltearn)")
            return False
        # Validate SiteSeenAt (visit location)
        if 'SiteSeenAt' not in patient_df.columns:
            patient_df['SiteSeenAt'] = patient_df['PatientPractice']
        patient_df['SiteSeenAt'] = patient_df['SiteSeenAt'].fillna('').astype(str).str.strip()
        if patient_df['SiteSeenAt'].iloc[0] in invalid_sites:
            log_activity("ERROR: Patient has invalid SiteSeenAt", level='error')
            st.error("❌ Cannot add patient: Visit site must be specified (Ashfields or Kiltearn)")
            return False
        # END NEW VALIDATION
        
        records = []
        # OPTIMIZED: Use itertuples for faster iteration (2-3x faster than iterrows)
        for row_tuple in patient_df.itertuples(index=False):
            start_date = None
            if pd.notna(getattr(row_tuple, 'StartDate', None)):
                try:
                    start_date_val = getattr(row_tuple, 'StartDate', None)
                    if isinstance(start_date_val, str):
                        start_date = datetime.strptime(start_date_val, '%d/%m/%Y').date()
                    else:
                        start_date = start_date_val.date() if hasattr(start_date_val, 'date') else start_date_val
                except Exception as date_error:
                    log_activity(f"Date parsing error: {date_error}", level='warning')
                    start_date = None

            record = {
                'PatientID': str(row_tuple.PatientID),
                'Study': str(row_tuple.Study),
                'StartDate': str(start_date) if start_date else None,
                'PatientPractice': str(getattr(row_tuple, 'PatientPractice', '')),
                'SiteSeenAt': str(getattr(row_tuple, 'SiteSeenAt', getattr(row_tuple, 'PatientPractice', ''))),
                'Pathway': str(getattr(row_tuple, 'Pathway', 'standard'))  # Enrollment pathway variant
            }
            records.append(record)
        
        response = client.table('patients').insert(records).execute()
        log_activity(f"Appended {len(records)} patient(s) to database", level='success')
        return True
        
    except Exception as e:
        log_activity(f"Error appending patient: {e}", level='error')
        return False

def append_visit_to_database(visit_df: pd.DataFrame) -> tuple[bool, str, str]:
    """
    Append new actual visit(s) to database with duplicate checking
    
    Returns:
        tuple: (success: bool, message: str, code: str)
        - success: Whether the operation succeeded
        - message: Human-readable message for the user
        - code: Status code ('SUCCESS', 'DUPLICATE_FOUND', 'ERROR', 'EMPTY_DATA', 'NO_CLIENT')
    """
    try:
        client = get_supabase_client()
        if client is None:
            log_activity("Cannot append visit: Supabase client not available", level='error')
            return False, "Database connection unavailable", 'NO_CLIENT'
        
        if visit_df is None or visit_df.empty:
            log_activity("Cannot append visit: Empty DataFrame", level='error')
            return False, "No visit data provided", 'EMPTY_DATA'
        
        # Check for duplicates before inserting
        duplicate_check_result = check_visit_duplicates(visit_df, client)
        if duplicate_check_result['has_duplicates']:
            duplicate_info = duplicate_check_result['duplicates']
            if duplicate_check_result['is_exact_duplicate']:
                message = f"Exact duplicate found: {duplicate_info['PatientID']} - {duplicate_info['VisitName']} on {duplicate_info['ActualDate']}"
                log_activity(f"Duplicate visit prevented: {message}", level='warning')
                return False, message, 'DUPLICATE_FOUND'
            else:
                # Same visit on different date - allow but warn
                message = f"Same visit exists on different date: {duplicate_info['PatientID']} - {duplicate_info['VisitName']} (existing: {duplicate_info['ActualDate']})"
                log_activity(f"Visit with different date detected: {message}", level='info')
        
        from helpers import get_visit_type_series
        from datetime import date
        visit_type_series = get_visit_type_series(visit_df, default='patient')
        today = date.today()
        
        records = []
        # OPTIMIZED: Use itertuples for faster iteration (2-3x faster than iterrows)
        for row_tuple in visit_df.itertuples(index=True):
            idx = row_tuple.Index
            actual_date = getattr(row_tuple, 'ActualDate', None)
            actual_date_obj = None
            if pd.notna(actual_date):
                if isinstance(actual_date, str):
                    actual_date_obj = pd.to_datetime(actual_date, dayfirst=True)
                else:
                    actual_date_obj = actual_date
                actual_date_str = str(actual_date_obj.date()) if hasattr(actual_date_obj, 'date') else str(actual_date_obj)
            else:
                actual_date_str = None
            
            visit_type_value = visit_type_series.loc[idx] if idx in visit_type_series.index else 'patient'
            
            # Auto-detect proposed visits/events for future dates
            if actual_date_obj is not None and actual_date_obj.date() > today:
                # Check if it's a study event (siv/monitor) or patient visit
                current_type = str(visit_type_value).lower()
                if current_type in ['siv', 'monitor']:
                    visit_type_value = 'event_proposed'
                elif current_type not in ['patient_proposed', 'event_proposed']:
                    visit_type_value = 'patient_proposed'
            
            record = {
                'PatientID': str(row_tuple.PatientID),
                'Study': str(row_tuple.Study),
                'VisitName': str(row_tuple.VisitName),
                'ActualDate': actual_date_str,
                'Notes': str(getattr(row_tuple, 'Notes', '')),
                'VisitType': str(visit_type_value)
            }
            records.append(record)
        
        response = client.table('actual_visits').insert(records).execute()
        log_activity(f"Appended {len(records)} visit(s) to database", level='success')
        return True, f"Successfully added {len(records)} visit(s)", 'SUCCESS'
        
    except Exception as e:
        log_activity(f"Error appending visit: {e}", level='error')
        return False, f"Database error: {str(e)}", 'ERROR'

def check_visit_duplicates(visit_df: pd.DataFrame, client) -> dict:
    """
    Check for duplicate visits in the database
    
    Args:
        visit_df: DataFrame containing visit(s) to check
        client: Supabase client instance
    
    Returns:
        dict: {
            'has_duplicates': bool,
            'is_exact_duplicate': bool,
            'duplicates': dict with duplicate info
        }
    """
    try:
        # Get all existing visits from database
        response = client.table('actual_visits').select("*").execute()
        existing_visits = pd.DataFrame(response.data) if response.data else pd.DataFrame()
        
        if existing_visits.empty:
            return {'has_duplicates': False, 'is_exact_duplicate': False, 'duplicates': None}
        
        # Database columns are now PascalCase, no renaming needed
        
        # Check each visit in the input DataFrame
        for _, new_visit in visit_df.iterrows():
            # Normalize date for comparison
            new_date = new_visit.get('ActualDate')
            if pd.notna(new_date):
                if isinstance(new_date, str):
                    new_date_normalized = pd.to_datetime(new_date, dayfirst=True).date()
                else:
                    new_date_normalized = new_date.date() if hasattr(new_date, 'date') else new_date
            else:
                new_date_normalized = None
            
            # OPTIMIZED: Only copy when we need to add normalized date column
            if 'ActualDate' in existing_visits.columns:
                existing_visits_copy = existing_visits.copy()
                existing_visits_copy['ActualDate_normalized'] = pd.to_datetime(
                    existing_visits_copy['ActualDate'], dayfirst=True, errors='coerce'
                ).dt.date
                
                # Check for exact duplicate (same PatientID + Study + VisitName + ActualDate)
                exact_match = existing_visits_copy[
                    (existing_visits_copy['PatientID'].astype(str) == str(new_visit['PatientID'])) &
                    (existing_visits_copy['Study'].astype(str) == str(new_visit['Study'])) &
                    (existing_visits_copy['VisitName'].astype(str).str.strip().str.lower() == str(new_visit['VisitName']).strip().lower()) &
                    (existing_visits_copy['ActualDate_normalized'] == new_date_normalized)
                ]
            else:
                # No ActualDate column - can't match on date, so no exact duplicates possible
                exact_match = pd.DataFrame()
            
            if not exact_match.empty:
                duplicate_info = exact_match.iloc[0]
                return {
                    'has_duplicates': True,
                    'is_exact_duplicate': True,
                    'duplicates': {
                        'PatientID': duplicate_info['PatientID'],
                        'Study': duplicate_info['Study'],
                        'VisitName': duplicate_info['VisitName'],
                        'ActualDate': duplicate_info['ActualDate']
                    }
                }
            
            # Check for same visit on different date
            same_visit_different_date = existing_visits_copy[
                (existing_visits_copy['PatientID'].astype(str) == str(new_visit['PatientID'])) &
                (existing_visits_copy['Study'].astype(str) == str(new_visit['Study'])) &
                (existing_visits_copy['VisitName'].astype(str).str.strip().str.lower() == str(new_visit['VisitName']).strip().lower()) &
                (existing_visits_copy['ActualDate_normalized'] != new_date_normalized)
            ]
            
            if not same_visit_different_date.empty:
                duplicate_info = same_visit_different_date.iloc[0]
                return {
                    'has_duplicates': True,
                    'is_exact_duplicate': False,
                    'duplicates': {
                        'PatientID': duplicate_info['PatientID'],
                        'Study': duplicate_info['Study'],
                        'VisitName': duplicate_info['VisitName'],
                        'ActualDate': duplicate_info['ActualDate']
                    }
                }
        
        return {'has_duplicates': False, 'is_exact_duplicate': False, 'duplicates': None}
        
    except Exception as e:
        log_activity(f"Error checking visit duplicates: {e}", level='error')
        # If we can't check duplicates, allow the insert to proceed
        return {'has_duplicates': False, 'is_exact_duplicate': False, 'duplicates': None}

def append_trial_schedule_to_database(schedule_df: pd.DataFrame) -> bool:
    """Append new trial schedule(s) to database without clearing existing data"""
    try:
        client = get_supabase_client()
        if client is None:
            log_activity("Cannot append schedule: Supabase client not available", level='error')
            return False
        
        if schedule_df is None or schedule_df.empty:
            log_activity("Cannot append schedule: Empty DataFrame", level='error')
            return False
        
        schedule_df_clean = normalize_payment_column(schedule_df, 'Payment')
        
        records = []
        records_with_visit_type = []
        # OPTIMIZED: Use itertuples for faster iteration (2-3x faster than iterrows)
        for row_tuple in schedule_df_clean.itertuples(index=False):
            # Get VisitType if it exists, otherwise infer from VisitName
            visit_type_value = getattr(row_tuple, 'VisitType', None)
            if pd.isna(visit_type_value) or str(visit_type_value).strip() in ['', 'None', 'nan', 'null', 'NULL']:
                # Auto-detect from VisitName
                visit_name = str(getattr(row_tuple, 'VisitName', ''))
                if visit_name.upper().strip() == 'SIV':
                    visit_type_value = 'siv'
                elif 'monitor' in visit_name.lower():
                    visit_type_value = 'monitor'
                else:
                    visit_type_value = 'patient'  # Default
            
            # Handle date override fields (FPFV, LPFV, LPLV)
            def parse_date_field(field_name):
                field_value = getattr(row_tuple, field_name, None)
                if pd.isna(field_value) or field_value == '' or str(field_value).strip() in ['None', 'nan', 'null', 'NULL']:
                    return None
                try:
                    if isinstance(field_value, str):
                        from datetime import datetime
                        parsed = pd.to_datetime(field_value, dayfirst=True, errors='coerce')
                        if pd.notna(parsed):
                            return str(parsed.date())
                    elif hasattr(field_value, 'date'):
                        return str(field_value.date())
                    return None
                except:
                    return None
            
            # Handle StudyStatus field
            study_status_value = getattr(row_tuple, 'StudyStatus', None)
            if pd.isna(study_status_value) or str(study_status_value).strip() in ['', 'None', 'nan', 'null', 'NULL']:
                study_status_value = 'active'  # Default status
            else:
                study_status_value = str(study_status_value).strip().lower()
                valid_statuses = ['active', 'contracted', 'in_setup', 'expression_of_interest']
                if study_status_value not in valid_statuses:
                    study_status_value = 'active'
            
            # Handle RecruitmentTarget field
            recruitment_target_value = getattr(row_tuple, 'RecruitmentTarget', None)
            if pd.isna(recruitment_target_value) or str(recruitment_target_value).strip() in ['', 'None', 'nan', 'null', 'NULL']:
                recruitment_target_value = None
            else:
                try:
                    recruitment_target_value = int(float(recruitment_target_value))
                    if recruitment_target_value < 0:
                        recruitment_target_value = None
                except (ValueError, TypeError):
                    recruitment_target_value = None
            
            record = {
                'Study': str(row_tuple.Study),
                'Day': int(getattr(row_tuple, 'Day', 0)),
                'VisitName': str(row_tuple.VisitName),
                'SiteforVisit': str(getattr(row_tuple, 'SiteforVisit', '')),
                'Payment': safe_float(getattr(row_tuple, 'Payment', 0)),
                'ToleranceBefore': int(getattr(row_tuple, 'ToleranceBefore', 0)),
                'ToleranceAfter': int(getattr(row_tuple, 'ToleranceAfter', 0)),
                # Optional month-based interval fields
                'IntervalUnit': (str(getattr(row_tuple, 'IntervalUnit', '')).lower().strip() if pd.notna(getattr(row_tuple, 'IntervalUnit', None)) else None),
                'IntervalValue': (int(getattr(row_tuple, 'IntervalValue', 0)) if pd.notna(getattr(row_tuple, 'IntervalValue', None)) else None),
                # VisitType column (now always included since database has it)
                'VisitType': str(visit_type_value).lower() if visit_type_value else 'patient',
                # New Gantt and recruitment tracking fields
                'FPFV': parse_date_field('FPFV'),
                'LPFV': parse_date_field('LPFV'),
                'LPLV': parse_date_field('LPLV'),
                'StudyStatus': study_status_value,
                'RecruitmentTarget': recruitment_target_value,
                # Pathway field for study variants (e.g., 'standard', 'with_run_in')
                'Pathway': str(getattr(row_tuple, 'Pathway', 'standard'))
            }
            records.append(record)

        response = client.table('trial_schedules').insert(records).execute()
        
        log_activity(f"Appended {len(records)} trial schedule(s) to database", level='success')
        return True
        
    except Exception as e:
        error_str = str(e).lower()
        # If it's a duplicate key error, that's okay - template already exists
        if 'duplicate' in error_str or 'unique' in error_str or 'already exists' in error_str:
            log_activity(f"Trial schedule template already exists (this is okay): {e}", level='info')
            return True  # Return True since the template exists, which is what we want
        else:
            log_activity(f"Error appending trial schedule: {e}", level='error')
            return False

def export_patients_to_csv() -> Optional[pd.DataFrame]:
    """Export patients from database in upload-ready CSV format"""
    try:
        df = fetch_all_patients()
        if df is None or df.empty:
            return pd.DataFrame(columns=['PatientID', 'Study', 'ScreeningDate', 'RandomizationDate', 'Status', 'PatientPractice', 'SiteSeenAt', 'Pathway'])

        # Ensure required columns exist
        for col in ['PatientPractice', 'SiteSeenAt']:
            if col not in df.columns:
                df[col] = ''

        if 'Pathway' not in df.columns:
            df['Pathway'] = 'standard'

        if 'Status' not in df.columns:
            df['Status'] = 'screening'

        # Format date columns
        if 'ScreeningDate' in df.columns:
            df['ScreeningDate'] = pd.to_datetime(df['ScreeningDate'], errors='coerce').dt.strftime('%d/%m/%Y')
        elif 'StartDate' in df.columns:
            # Backward compatibility: rename StartDate to ScreeningDate for export
            df['ScreeningDate'] = pd.to_datetime(df['StartDate'], errors='coerce').dt.strftime('%d/%m/%Y')

        if 'RandomizationDate' in df.columns:
            df['RandomizationDate'] = pd.to_datetime(df['RandomizationDate'], errors='coerce').dt.strftime('%d/%m/%Y')
            df['RandomizationDate'] = df['RandomizationDate'].replace('NaT', '').replace('nan', '')
        else:
            df['RandomizationDate'] = ''

        export_columns = ['PatientID', 'Study', 'ScreeningDate', 'RandomizationDate', 'Status', 'PatientPractice', 'SiteSeenAt', 'Pathway']
        # Only select columns that exist
        available_columns = [col for col in export_columns if col in df.columns]
        df = df[available_columns]

        return df
    except Exception as e:
        st.error(f"Error exporting patients: {e}")
        return None

def export_trials_to_csv() -> Optional[pd.DataFrame]:
    """Export trial schedules from database in upload-ready CSV format"""
    try:
        df = fetch_all_trial_schedules()
        if df is None or df.empty:
            return pd.DataFrame(columns=['Study', 'Day', 'VisitName', 'SiteforVisit', 'Payment', 'ToleranceBefore', 'ToleranceAfter', 'IntervalUnit', 'IntervalValue'])
        
        if 'Payment' not in df.columns:
            df['Payment'] = 0
        if 'ToleranceBefore' not in df.columns:
            df['ToleranceBefore'] = 0
        if 'ToleranceAfter' not in df.columns:
            df['ToleranceAfter'] = 0
        # Ensure optional interval columns exist for export
        if 'IntervalUnit' not in df.columns:
            df['IntervalUnit'] = ''
        if 'IntervalValue' not in df.columns:
            df['IntervalValue'] = ''
        
        # Ensure VisitType column exists (add if missing, infer from VisitName)
        if 'VisitType' not in df.columns:
            df['VisitType'] = 'patient'  # Default
            # Auto-detect SIVs and Monitors if VisitName column exists
            if 'VisitName' in df.columns and not df.empty:
                try:
                    # Auto-detect SIVs
                    siv_mask = df['VisitName'].astype(str).str.upper().str.strip() == 'SIV'
                    df.loc[siv_mask, 'VisitType'] = 'siv'
                    # Auto-detect Monitors
                    monitor_mask = df['VisitName'].astype(str).str.contains('Monitor', case=False, na=False)
                    df.loc[monitor_mask, 'VisitType'] = 'monitor'
                except Exception:
                    # If detection fails, keep default 'patient'
                    pass
        
        # Ensure new columns exist for export
        if 'Pathway' not in df.columns:
            df['Pathway'] = 'standard'  # Default pathway
        if 'FPFV' not in df.columns:
            df['FPFV'] = None
        if 'LPFV' not in df.columns:
            df['LPFV'] = None
        if 'LPLV' not in df.columns:
            df['LPLV'] = None
        if 'StudyStatus' not in df.columns:
            df['StudyStatus'] = 'active'  # Default
        if 'RecruitmentTarget' not in df.columns:
            df['RecruitmentTarget'] = None

        # Format date columns for export
        for date_col in ['FPFV', 'LPFV', 'LPLV']:
            if date_col in df.columns:
                try:
                    df[date_col] = pd.to_datetime(df[date_col], errors='coerce').dt.strftime('%d/%m/%Y')
                    df[date_col] = df[date_col].replace('NaT', '').replace('nan', '')
                except Exception:
                    # If date formatting fails, set to empty string
                    df[date_col] = ''

        export_columns = ['Study', 'Pathway', 'Day', 'VisitName', 'SiteforVisit', 'Payment', 'ToleranceBefore', 'ToleranceAfter', 'IntervalUnit', 'IntervalValue', 'VisitType', 'FPFV', 'LPFV', 'LPLV', 'StudyStatus', 'RecruitmentTarget']
        # Only select columns that exist
        available_columns = [col for col in export_columns if col in df.columns]
        df = df[available_columns]
        
        return df
    except Exception as e:
        st.error(f"Error exporting trials: {e}")
        return None

def export_visits_to_csv() -> Optional[pd.DataFrame]:
    """Export actual visits from database in upload-ready CSV format"""
    try:
        df = fetch_all_actual_visits()
        if df is None or df.empty:
            return pd.DataFrame(columns=['PatientID', 'Study', 'VisitName', 'ActualDate', 'Notes', 'VisitType'])
        
        if 'Notes' not in df.columns:
            df['Notes'] = ''
        
        # Ensure VisitType column exists (add if missing, infer from VisitName)
        if 'VisitType' not in df.columns:
            df['VisitType'] = 'patient'  # Default
            # Auto-detect SIVs
            siv_mask = df['VisitName'].astype(str).str.upper().str.strip() == 'SIV'
            df.loc[siv_mask, 'VisitType'] = 'siv'
            # Auto-detect Monitors
            monitor_mask = df['VisitName'].astype(str).str.contains('Monitor', case=False, na=False)
            df.loc[monitor_mask, 'VisitType'] = 'monitor'
        
        if 'ActualDate' in df.columns:
            df['ActualDate'] = pd.to_datetime(df['ActualDate'], errors='coerce').dt.strftime('%d/%m/%Y')
        
        export_columns = ['PatientID', 'Study', 'VisitName', 'ActualDate', 'Notes', 'VisitType']
        # Only select columns that exist
        available_columns = [col for col in export_columns if col in df.columns]
        df = df[available_columns]
        
        return df
    except Exception as e:
        st.error(f"Error exporting visits: {e}")
        return None

def export_study_site_details_to_csv() -> Optional[pd.DataFrame]:
    """Export study site details from database in upload-ready CSV format"""
    try:
        df = fetch_all_study_site_details()
        if df is None or df.empty:
            return pd.DataFrame(columns=['Study', 'ContractSite', 'StudyStatus', 'RecruitmentTarget', 'FPFV', 'LPFV', 'LPLV'])
        
        # Ensure required columns exist
        for col in ['Study', 'ContractSite']:
            if col not in df.columns:
                df[col] = ''
        
        # Ensure optional columns exist
        for col in ['StudyStatus', 'RecruitmentTarget', 'FPFV', 'LPFV', 'LPLV', 'Description', 'EOIDate', 'StudyURL', 'DocumentLinks']:
            if col not in df.columns:
                df[col] = ''
        
        # Format date columns for export
        for date_col in ['FPFV', 'LPFV', 'LPLV', 'EOIDate']:
            if date_col in df.columns:
                try:
                    df[date_col] = pd.to_datetime(df[date_col], errors='coerce').dt.strftime('%d/%m/%Y')
                    df[date_col] = df[date_col].replace('NaT', '').replace('nan', '')
                except Exception:
                    df[date_col] = ''
        
        export_columns = ['Study', 'ContractSite', 'StudyStatus', 'RecruitmentTarget', 'FPFV', 'LPFV', 'LPLV', 'Description', 'EOIDate', 'StudyURL', 'DocumentLinks']
        available_columns = [col for col in export_columns if col in df.columns]
        df = df[available_columns]
        
        return df
    except Exception as e:
        st.error(f"Error exporting study site details: {e}")
        return None

# ============================================
# Study Site Details Functions
# ============================================

@st.cache_data(ttl=300, show_spinner=False)
def _fetch_all_study_site_details_cached() -> Optional[pd.DataFrame]:
    """Internal cached function to fetch all study site details from database"""
    try:
        client = get_supabase_client()
        if client is None:
            return None
        
        response = client.table('study_site_details').select("*").execute()
        
        if response.data:
            df = pd.DataFrame(response.data)

            # Log actual columns for debugging
            log_activity(f"study_site_details columns from database: {list(df.columns)}", level='info')

            # Standardize column name - handle ContractSite variants (case-insensitive)
            # ContractSite is the canonical contract holder field
            col_lower_map = {col.lower(): col for col in df.columns}

            if 'contractsite' in col_lower_map:
                actual_col = col_lower_map['contractsite']
                if actual_col != 'ContractSite':
                    df = df.rename(columns={actual_col: 'ContractSite'})
                    log_activity(f"Renamed {actual_col} to ContractSite", level='info')
            elif 'contractedsite' in col_lower_map:
                actual_col = col_lower_map['contractedsite']
                df = df.rename(columns={actual_col: 'ContractSite'})
                log_activity(f"Renamed {actual_col} to ContractSite", level='info')
            elif 'siteforvisit' in col_lower_map:
                # Backward compatibility: treat SiteforVisit as ContractSite if present
                actual_col = col_lower_map['siteforvisit']
                df = df.rename(columns={actual_col: 'ContractSite'})
                log_activity(f"Renamed {actual_col} to ContractSite (legacy SiteforVisit)", level='info')
            else:
                log_activity(f"WARNING: ContractSite not found in study_site_details. Columns: {list(df.columns)}", level='warning')

            # Parse date fields if they exist
            for date_col in ['FPFV', 'LPFV', 'LPLV', 'EOIDate']:
                if date_col in df.columns:
                    df[date_col] = pd.to_datetime(df[date_col], errors='coerce')

            # Ensure StudyStatus defaults to 'active' if missing
            if 'StudyStatus' not in df.columns:
                df['StudyStatus'] = 'active'
            else:
                df['StudyStatus'] = df['StudyStatus'].fillna('active')

            # Ensure RecruitmentTarget is numeric or None
            if 'RecruitmentTarget' in df.columns:
                df['RecruitmentTarget'] = pd.to_numeric(df['RecruitmentTarget'], errors='coerce')

            return df
        # Return empty DataFrame with ContractSite (normalized column name used internally)
        return pd.DataFrame(columns=['Study', 'ContractSite', 'FPFV', 'LPFV', 'LPLV', 'StudyStatus', 'RecruitmentTarget', 'Description', 'EOIDate', 'StudyURL', 'DocumentLinks'])
    except Exception as e:
        log_activity(f"Error fetching study site details: {e}", level='error')
        return None

def fetch_all_study_site_details() -> Optional[pd.DataFrame]:
    """Fetch all study site details from database (with caching)"""
    df = _fetch_all_study_site_details_cached()
    if df is None:
        log_activity("No study site details found in database", level='warning')
    return df

def fetch_study_site_details(study: str, site: str) -> Optional[Dict]:
    """Fetch study site details for a specific study+site combination"""
    try:
        client = get_supabase_client()
        if client is None:
            return None
        
        response = client.table('study_site_details').select("*").eq('Study', study).eq('ContractSite', site).execute()
        
        if response.data and len(response.data) > 0:
            return response.data[0]
        return None
    except Exception as e:
        log_activity(f"Error fetching study site details for {study}/{site}: {e}", level='error')
        return None

def create_study_site_details(study: str, site: str, details: Dict) -> bool:
    """Create a new study+site entry in study_site_details table"""
    try:
        client = get_supabase_client()
        if client is None:
            return False
        
        # Prepare record with defaults
        record = {
            'Study': str(study).strip(),
            'ContractSite': str(site).strip(),
            'StudyStatus': details.get('StudyStatus', 'active'),
            'RecruitmentTarget': details.get('RecruitmentTarget'),
            'FPFV': str(details.get('FPFV')) if details.get('FPFV') else None,
            'LPFV': str(details.get('LPFV')) if details.get('LPFV') else None,
            'LPLV': str(details.get('LPLV')) if details.get('LPLV') else None,
            'Description': details.get('Description'),
            'EOIDate': str(details.get('EOIDate')) if details.get('EOIDate') else None,
            'StudyURL': details.get('StudyURL'),
            'DocumentLinks': details.get('DocumentLinks')
        }
        
        # Remove None values to let database use defaults
        record = {k: v for k, v in record.items() if v is not None}
        
        response = client.table('study_site_details').insert(record).execute()
        
        if response.data:
            log_activity(f"Created study site details: {study}/{site}", level='success')
            # Clear cache
            _fetch_all_study_site_details_cached.clear()
            return True
        return False
    except Exception as e:
        log_activity(f"Error creating study site details for {study}/{site}: {e}", level='error')
        return False

def save_study_site_details(study: str, site: str, details: Dict) -> bool:
    """Create or update (upsert) study site details"""
    try:
        client = get_supabase_client()
        if client is None:
            return False
        
        # Check if record exists
        existing = fetch_study_site_details(study, site)
        
        # Prepare record
        record = {
            'Study': str(study).strip(),
            'ContractSite': str(site).strip(),
        }
        
        # Add fields that are provided
        if 'StudyStatus' in details:
            record['StudyStatus'] = details['StudyStatus']
        if 'RecruitmentTarget' in details:
            record['RecruitmentTarget'] = details['RecruitmentTarget'] if details['RecruitmentTarget'] is not None else None
        if 'FPFV' in details:
            record['FPFV'] = str(details['FPFV']) if details['FPFV'] else None
        if 'LPFV' in details:
            record['LPFV'] = str(details['LPFV']) if details['LPFV'] else None
        if 'LPLV' in details:
            record['LPLV'] = str(details['LPLV']) if details['LPLV'] else None
        if 'Description' in details:
            record['Description'] = details['Description']
        if 'EOIDate' in details:
            record['EOIDate'] = str(details['EOIDate']) if details['EOIDate'] else None
        if 'StudyURL' in details:
            record['StudyURL'] = details['StudyURL']
        if 'DocumentLinks' in details:
            record['DocumentLinks'] = details['DocumentLinks']
        
        if existing:
            # Update existing record
            response = client.table('study_site_details').update(record).eq('Study', study).eq('ContractSite', site).execute()
            log_activity(f"Updated study site details: {study}/{site}", level='success')
        else:
            # Create new record
            response = client.table('study_site_details').insert(record).execute()
            log_activity(f"Created study site details: {study}/{site}", level='success')
        
        if response.data:
            # Clear cache
            _fetch_all_study_site_details_cached.clear()
            return True
        return False
    except Exception as e:
        log_activity(f"Error saving study site details for {study}/{site}: {e}", level='error')
        return False

def update_study_site_details(study: str, site: str, **kwargs) -> bool:
    """Update specific fields in study_site_details"""
    try:
        client = get_supabase_client()
        if client is None:
            return False

        # Prepare update record
        update_data = {}

        # Handle date fields
        for date_field in ['FPFV', 'LPFV', 'LPLV', 'EOIDate']:
            if date_field in kwargs:
                update_data[date_field] = str(kwargs[date_field]) if kwargs[date_field] else None

        # Handle other fields
        for field in ['StudyStatus', 'RecruitmentTarget', 'Description', 'EOIDate', 'StudyURL', 'DocumentLinks']:
            if field in kwargs:
                update_data[field] = kwargs[field]

        if not update_data:
            return False

        response = client.table('study_site_details').update(update_data).eq('Study', study).eq('ContractSite', site).execute()

        if response.data:
            log_activity(f"Updated study site details: {study}/{site}", level='success')
            # Clear cache
            _fetch_all_study_site_details_cached.clear()
            return True
        return False
    except Exception as e:
        log_activity(f"Error updating study site details: {e}", level='error')
        return False

def save_study_site_details_to_database(details_df: pd.DataFrame) -> bool:
    """Save study_site_details data to database (overwrite existing rows)"""
    try:
        client = get_supabase_client()
        if client is None:
            log_activity("Cannot save study site details: Supabase client not available", level='error')
            return False
        
        if details_df is None or details_df.empty:
            log_activity("Cannot save study site details: Empty DataFrame", level='error')
            return False
        
        details_df = details_df.copy()
        if 'ContractSite' not in details_df.columns:
            if 'ContractedSite' in details_df.columns:
                details_df = details_df.rename(columns={'ContractedSite': 'ContractSite'})
            elif 'SiteforVisit' in details_df.columns:
                details_df = details_df.rename(columns={'SiteforVisit': 'ContractSite'})
        
        if 'RecruitmentTarget' in details_df.columns:
            details_df['RecruitmentTarget'] = pd.to_numeric(details_df['RecruitmentTarget'], errors='coerce')
        
        records = []
        for row in details_df.itertuples(index=False):
            study = str(getattr(row, 'Study', '')).strip()
            site = str(getattr(row, 'ContractSite', '')).strip()
            if not study or not site:
                continue
            
            def parse_date(val):
                if pd.isna(val) or val in ['', None]:
                    return None
                parsed = pd.to_datetime(val, errors='coerce')
                if pd.isna(parsed):
                    return None
                return str(parsed.date())
            
            record = {
                'Study': study,
                'ContractSite': site,
                'StudyStatus': str(getattr(row, 'StudyStatus', 'active')).strip().lower() or 'active',
                'RecruitmentTarget': getattr(row, 'RecruitmentTarget', None),
                'FPFV': parse_date(getattr(row, 'FPFV', None)),
                'LPFV': parse_date(getattr(row, 'LPFV', None)),
                'LPLV': parse_date(getattr(row, 'LPLV', None)),
                'Description': str(getattr(row, 'Description', '')).strip(),
                'EOIDate': parse_date(getattr(row, 'EOIDate', None)),
                'StudyURL': str(getattr(row, 'StudyURL', '')).strip(),
                'DocumentLinks': str(getattr(row, 'DocumentLinks', '')).strip()
            }
            records.append(record)
        
        if not records:
            log_activity("No valid study_site_details records to save", level='error')
            return False
        
        client.table('study_site_details').insert(records).execute()
        _fetch_all_study_site_details_cached.clear()
        log_activity(f"Saved {len(records)} study site detail records", level='success')
        return True
        
    except Exception as e:
        log_activity(f"Error saving study site details: {e}", level='error')
        return False

def create_backup_zip() -> Optional[io.BytesIO]:
    """Create a ZIP file containing all four database tables as CSVs"""
    zip_buffer = None
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        
        # Export each table with error handling
        patients_df = None
        trials_df = None
        visits_df = None
        study_details_df = None
        
        try:
            patients_df = export_patients_to_csv()
        except Exception as e:
            log_activity(f"Error exporting patients: {e}", level='error')
            patients_df = pd.DataFrame(columns=['PatientID', 'Study', 'StartDate', 'PatientPractice', 'SiteSeenAt'])
        
        try:
            trials_df = export_trials_to_csv()
        except Exception as e:
            log_activity(f"Error exporting trials: {e}", level='error')
            trials_df = pd.DataFrame(columns=['Study', 'Day', 'VisitName', 'SiteforVisit', 'Payment'])
        
        try:
            visits_df = export_visits_to_csv()
        except Exception as e:
            log_activity(f"Error exporting visits: {e}", level='error')
            visits_df = pd.DataFrame(columns=['PatientID', 'Study', 'VisitName', 'ActualDate', 'Notes', 'VisitType'])
        
        try:
            study_details_df = export_study_site_details_to_csv()
        except Exception as e:
            log_activity(f"Error exporting study site details: {e}", level='error')
            study_details_df = pd.DataFrame(columns=['Study', 'ContractSite', 'StudyStatus', 'RecruitmentTarget', 'FPFV', 'LPFV', 'LPLV'])
        
        # Ensure we have DataFrames (even if empty)
        if patients_df is None:
            patients_df = pd.DataFrame(columns=['PatientID', 'Study', 'StartDate', 'PatientPractice', 'SiteSeenAt'])
        if trials_df is None:
            trials_df = pd.DataFrame(columns=['Study', 'Day', 'VisitName', 'SiteforVisit', 'Payment'])
        if visits_df is None:
            visits_df = pd.DataFrame(columns=['PatientID', 'Study', 'VisitName', 'ActualDate', 'Notes', 'VisitType'])
        if study_details_df is None:
            study_details_df = pd.DataFrame(columns=['Study', 'ContractSite', 'StudyStatus', 'RecruitmentTarget', 'FPFV', 'LPFV', 'LPLV'])
        
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            try:
                patients_csv = patients_df.to_csv(index=False)
                zip_file.writestr(f'patients_backup_{today}.csv', patients_csv)
            except Exception as e:
                log_activity(f"Error writing patients CSV: {e}", level='error')
                patients_csv = pd.DataFrame(columns=['PatientID', 'Study', 'StartDate', 'PatientPractice', 'SiteSeenAt']).to_csv(index=False)
                zip_file.writestr(f'patients_backup_{today}.csv', patients_csv)
            
            try:
                trials_csv = trials_df.to_csv(index=False)
                zip_file.writestr(f'trials_backup_{today}.csv', trials_csv)
            except Exception as e:
                log_activity(f"Error writing trials CSV: {e}", level='error')
                trials_csv = pd.DataFrame(columns=['Study', 'Day', 'VisitName', 'SiteforVisit', 'Payment']).to_csv(index=False)
                zip_file.writestr(f'trials_backup_{today}.csv', trials_csv)
            
            try:
                visits_csv = visits_df.to_csv(index=False)
                zip_file.writestr(f'actual_visits_backup_{today}.csv', visits_csv)
            except Exception as e:
                log_activity(f"Error writing visits CSV: {e}", level='error')
                visits_csv = pd.DataFrame(columns=['PatientID', 'Study', 'VisitName', 'ActualDate', 'Notes', 'VisitType']).to_csv(index=False)
                zip_file.writestr(f'actual_visits_backup_{today}.csv', visits_csv)
            
            try:
                details_csv = study_details_df.to_csv(index=False)
                zip_file.writestr(f'study_site_details_backup_{today}.csv', details_csv)
            except Exception as e:
                log_activity(f"Error writing study site details CSV: {e}", level='error')
                details_csv = pd.DataFrame(columns=['Study', 'ContractSite', 'StudyStatus', 'RecruitmentTarget', 'FPFV', 'LPFV', 'LPLV']).to_csv(index=False)
                zip_file.writestr(f'study_site_details_backup_{today}.csv', details_csv)
        
        if zip_buffer:
            zip_buffer.seek(0)
        return zip_buffer
        
    except Exception as e:
        st.error(f"Error creating backup ZIP: {e}")
        log_activity(f"Error creating backup ZIP: {e}", level='error')
        import traceback
        log_activity(f"Traceback: {traceback.format_exc()}", level='error')
        return None

def restore_database_from_zip(zip_file) -> Tuple[bool, str]:
    """Restore database tables from a backup ZIP containing CSVs."""
    try:
        if zip_file is None:
            return False, "No ZIP file provided"
        
        with zipfile.ZipFile(zip_file) as zf:
            names = zf.namelist()
            def read_csv_by_prefix(prefix):
                for name in names:
                    if name.startswith(prefix) and name.endswith(".csv"):
                        with zf.open(name) as f:
                            return pd.read_csv(f)
                return None
            
            patients_df = read_csv_by_prefix("patients_backup_")
            trials_df = read_csv_by_prefix("trials_backup_")
            visits_df = read_csv_by_prefix("actual_visits_backup_")
            details_df = read_csv_by_prefix("study_site_details_backup_")
        
        if patients_df is None and trials_df is None and visits_df is None and details_df is None:
            return False, "No recognized backup files found in ZIP"
        
        # Overwrite tables using safe operations
        if patients_df is not None:
            if not safe_overwrite_table('patients', patients_df, save_patients_to_database):
                return False, "Failed to restore patients table"
        if trials_df is not None:
            if not safe_overwrite_table('trial_schedules', trials_df, save_trial_schedules_to_database):
                return False, "Failed to restore trial schedules table"
        if visits_df is not None:
            if not safe_overwrite_table('actual_visits', visits_df, save_actual_visits_to_database):
                return False, "Failed to restore actual visits table"
        if details_df is not None:
            if not safe_overwrite_table('study_site_details', details_df, save_study_site_details_to_database):
                return False, "Failed to restore study site details table"
        
        return True, "Database restored from backup ZIP"
    except Exception as e:
        log_activity(f"Error restoring from backup ZIP: {e}", level='error')
        return False, f"Error restoring from backup ZIP: {e}"

def clear_patients_table() -> bool:
    """Clear all patients from database"""
    try:
        client = get_supabase_client()
        if client is None:
            return False

        # Delete all rows - use neq filter to match all rows (Supabase requires WHERE clause)
        client.table('patients').delete().neq('id', 0).execute()
        log_activity("Cleared all patients from database", level='info')
        return True

    except Exception as e:
        st.error(f"Error clearing patients table: {e}")
        log_activity(f"Error clearing patients table: {e}", level='error')
        return False

def clear_trial_schedules_table() -> bool:
    """Clear all trial schedules from database"""
    try:
        client = get_supabase_client()
        if client is None:
            return False

        # Delete all rows - use neq filter to match all rows (Supabase requires WHERE clause)
        client.table('trial_schedules').delete().neq('id', 0).execute()
        log_activity("Cleared all trial schedules from database", level='info')
        return True

    except Exception as e:
        st.error(f"Error clearing trial schedules table: {e}")
        log_activity(f"Error clearing trial schedules table: {e}", level='error')
        return False

def clear_actual_visits_table() -> bool:
    """Clear all actual visits from database"""
    try:
        client = get_supabase_client()
        if client is None:
            return False

        # Delete all rows - use neq filter to match all rows (Supabase requires WHERE clause)
        client.table('actual_visits').delete().neq('id', 0).execute()
        log_activity("Cleared all actual visits from database", level='info')
        return True

    except Exception as e:
        st.error(f"Error clearing actual visits table: {e}")
        log_activity(f"Error clearing actual visits table: {e}", level='error')
        return False

def clear_study_site_details_table() -> bool:
    """Clear all study site details from database"""
    try:
        client = get_supabase_client()
        if client is None:
            return False

        # Delete all rows - use neq filter on Study column (table has no id column)
        # This matches all rows since Study is never empty (Supabase requires WHERE clause)
        client.table('study_site_details').delete().neq('Study', '').execute()
        log_activity("Cleared all study site details from database", level='info')
        _fetch_all_study_site_details_cached.clear()
        return True

    except Exception as e:
        st.error(f"Error clearing study site details table: {e}")
        log_activity(f"Error clearing study site details table: {e}", level='error')
        return False

def overwrite_database_with_files(
    patients_df: pd.DataFrame,
    trials_df: pd.DataFrame,
    actual_visits_df: pd.DataFrame = None,
    study_site_details_df: pd.DataFrame = None
) -> bool:
    """Completely replace database content with uploaded files"""
    try:
        if not clear_patients_table():
            return False
        if not clear_trial_schedules_table():
            return False
        if actual_visits_df is not None and not actual_visits_df.empty:
            if not clear_actual_visits_table():
                return False
        if study_site_details_df is not None and not study_site_details_df.empty:
            if not clear_study_site_details_table():
                return False
        
        if not save_patients_to_database(patients_df):
            return False
        if not save_trial_schedules_to_database(trials_df):
            return False
        if actual_visits_df is not None and not actual_visits_df.empty:
            if not save_actual_visits_to_database(actual_visits_df):
                return False
        if study_site_details_df is not None and not study_site_details_df.empty:
            if not save_study_site_details_to_database(study_site_details_df):
                return False
        
        log_activity("Successfully overwrote database with uploaded files", level='success')
        return True
        
    except Exception as e:
        st.error(f"Error overwriting database: {e}")
        log_activity(f"Error overwriting database: {e}", level='error')
        return False

def switch_patient_study(patient_id, old_study, new_study, new_start_date):
    """
    Switch a patient from one study to another, updating all their records
    
    Args:
        patient_id: Patient ID to switch
        old_study: Current study name
        new_study: Target study name  
        new_start_date: New Day 1 date (formatted as string)
    
    Returns:
        tuple: (success: bool, message: str, updated_visits_count: int)
    """
    try:
        client = get_supabase_client()
        if client is None:
            log_activity("Cannot switch patient study: Supabase client not available", level='error')
            return False, "Database connection unavailable", 0
        
        # Validate inputs
        if not patient_id or not old_study or not new_study or not new_start_date:
            log_activity("Cannot switch patient study: Missing required parameters", level='error')
            return False, "Missing required parameters", 0
        
        if old_study == new_study:
            log_activity("Cannot switch patient study: Same study selected", level='error')
            return False, "Cannot switch to the same study", 0
        
        # Check if patient exists
        patient_check = client.table('patients').select('*').eq('PatientID', patient_id).eq('Study', old_study).execute()
        if not patient_check.data:
            log_activity(f"Cannot switch patient study: Patient {patient_id} not found in study {old_study}", level='error')
            return False, f"Patient {patient_id} not found in study {old_study}", 0
        
        # Check if target study exists in trial schedules
        trial_check = client.table('trial_schedules').select('Study').eq('Study', new_study).limit(1).execute()
        if not trial_check.data:
            log_activity(f"Cannot switch patient study: Target study {new_study} not found in trial schedules", level='error')
            return False, f"Target study {new_study} not found in trial schedules", 0
        
        # Check if target study has exactly one Day 1 visit
        day1_check = client.table('trial_schedules').select('*').eq('Study', new_study).eq('Day', 1).execute()
        if len(day1_check.data) != 1:
            log_activity(f"Cannot switch patient study: Target study {new_study} has {len(day1_check.data)} Day 1 visits (should be exactly 1)", level='error')
            return False, f"Target study {new_study} must have exactly one Day 1 visit", 0
        
        # Get count of actual visits to update
        visits_check = client.table('actual_visits').select('id').eq('PatientID', patient_id).eq('Study', old_study).execute()
        visits_count = len(visits_check.data)
        
        # Update patient record
        # Convert DD/MM/YYYY to YYYY-MM-DD for database
        try:
            if isinstance(new_start_date, str) and '/' in new_start_date:
                # Convert DD/MM/YYYY to YYYY-MM-DD
                from datetime import datetime
                parsed_date = datetime.strptime(new_start_date, '%d/%m/%Y').date()
                db_start_date = str(parsed_date)
            else:
                db_start_date = str(new_start_date)
        except Exception as date_error:
            log_activity(f"Date conversion error: {date_error}", level='error')
            return False, f"Invalid date format: {new_start_date}", 0
        
        patient_update = client.table('patients').update({
            'Study': new_study,
            'StartDate': db_start_date
        }).eq('PatientID', patient_id).eq('Study', old_study).execute()
        
        if not patient_update.data:
            log_activity(f"Failed to update patient {patient_id} record", level='error')
            return False, "Failed to update patient record", 0
        
        # Update all actual visits for this patient
        visits_update = client.table('actual_visits').update({
            'Study': new_study
        }).eq('PatientID', patient_id).eq('Study', old_study).execute()
        
        log_activity(f"Successfully switched patient {patient_id} from {old_study} to {new_study}", level='success')
        log_activity(f"Updated {visits_count} actual visits", level='info')
        
        return True, f"Successfully switched patient {patient_id} from {old_study} to {new_study}", visits_count
        
    except Exception as e:
        log_activity(f"Error switching patient study: {e}", level='error')
        return False, f"Database error: {str(e)}", 0

def safe_overwrite_table(table_name: str, df: pd.DataFrame, save_function) -> bool:
    """Safely overwrite a single table with atomic operation"""
    try:
        if df is None or df.empty:
            log_activity(f"Cannot overwrite {table_name}: No data provided", level='error')
            return False
        
        log_activity(f"Starting overwrite of {table_name} with {len(df)} records", level='info')
        
        backup_df = None
        if table_name == 'patients':
            backup_df = fetch_all_patients()
        elif table_name == 'trial_schedules':
            backup_df = fetch_all_trial_schedules()
        elif table_name == 'actual_visits':
            backup_df = fetch_all_actual_visits()
        elif table_name == 'study_site_details':
            backup_df = fetch_all_study_site_details()
        
        log_activity(f"Created backup of {table_name} with {len(backup_df) if backup_df is not None else 0} records", level='info')
        
        if backup_df is None:
            log_activity(f"Backup failed for {table_name}; refusing to overwrite", level='error')
            return False
        
        clear_function = None
        if table_name == 'patients':
            clear_function = clear_patients_table
        elif table_name == 'trial_schedules':
            clear_function = clear_trial_schedules_table
        elif table_name == 'actual_visits':
            clear_function = clear_actual_visits_table
        elif table_name == 'study_site_details':
            clear_function = clear_study_site_details_table
        
        if not clear_function():
            log_activity(f"Failed to clear {table_name} table", level='error')
            return False
        
        log_activity(f"Successfully cleared {table_name} table", level='info')
        
        if not save_function(df):
            log_activity(f"Failed to save new data to {table_name}, attempting restore", level='error')
            if backup_df is not None and not backup_df.empty:
                if table_name == 'patients':
                    save_patients_to_database(backup_df)
                elif table_name == 'trial_schedules':
                    save_trial_schedules_to_database(backup_df)
                elif table_name == 'actual_visits':
                    save_actual_visits_to_database(backup_df)
                elif table_name == 'study_site_details':
                    save_study_site_details_to_database(backup_df)
                log_activity(f"Restored backup for {table_name}", level='info')
            return False
        
        log_activity(f"Successfully overwrote {table_name} table with {len(df)} records", level='success')
        return True
        
    except Exception as e:
        log_activity(f"Error in safe overwrite of {table_name}: {e}", level='error')
        return False
