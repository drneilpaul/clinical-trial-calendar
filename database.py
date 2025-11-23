import streamlit as st
from supabase import create_client, Client
import pandas as pd
from typing import Optional, Dict, List
import io
from datetime import datetime
import zipfile
from helpers import log_activity
from payment_handler import normalize_payment_column, validate_payment_data

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
        
        response = client.table('patients').select("*").execute()
        
        if response.data:
            df = pd.DataFrame(response.data)
            df = df.rename(columns={
                'patient_id': 'PatientID',
                'study': 'Study',
                'start_date': 'StartDate',
                'patient_practice': 'PatientPractice'
            })
            
            if 'StartDate' in df.columns:
                df['StartDate'] = pd.to_datetime(df['StartDate'], errors='coerce')
            
            return df
        return pd.DataFrame(columns=['PatientID', 'Study', 'StartDate', 'PatientPractice'])
    except Exception as e:
        return None

def fetch_all_patients() -> Optional[pd.DataFrame]:
    """Fetch all patients from database (with caching)"""
    df = _fetch_all_patients_cached()
    if df is not None:
        log_activity(f"Fetched {len(df)} patients from database", level='info')
    else:
        log_activity("No patients found in database", level='info')
    return df

@st.cache_data(ttl=300, show_spinner=False)
def _fetch_all_trial_schedules_cached() -> Optional[pd.DataFrame]:
    """Internal cached function to fetch all trial schedules from database"""
    try:
        client = get_supabase_client()
        if client is None:
            return None
        
        response = client.table('trial_schedules').select("*").execute()
        
        if response.data:
            df = pd.DataFrame(response.data)
            df = df.rename(columns={
                'study': 'Study',
                'day': 'Day',
                'visit_name': 'VisitName',
                'site_for_visit': 'SiteforVisit',
                'payment': 'Payment',
                'tolerance_before': 'ToleranceBefore',
                'tolerance_after': 'ToleranceAfter',
                # Optional columns for month-based intervals
                'interval_unit': 'IntervalUnit',
                'interval_value': 'IntervalValue'
            })
            return df
        return pd.DataFrame(columns=['Study', 'Day', 'VisitName', 'SiteforVisit', 'Payment', 'ToleranceBefore', 'ToleranceAfter', 'IntervalUnit', 'IntervalValue'])
    except Exception as e:
        return None

def fetch_all_trial_schedules() -> Optional[pd.DataFrame]:
    """Fetch all trial schedules from database (with caching)"""
    return _fetch_all_trial_schedules_cached()

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
            
            rename_map = {
                'patient_id': 'PatientID',
                'study': 'Study',
                'visit_name': 'VisitName',
                'actual_date': 'ActualDate',
                'notes': 'Notes',
            }
            if 'visit_type' in df.columns:
                rename_map['visit_type'] = 'VisitType'
            df = df.rename(columns=rename_map)
            
            if 'ActualDate' in df.columns:
                df['ActualDate'] = pd.to_datetime(df['ActualDate'], errors='coerce')
            
            # FIXED: Auto-detect study events IMMEDIATELY after loading from database
            # This fixes SIV/Monitor visits that were saved with wrong VisitType
            if 'VisitType' in df.columns:
                siv_mask = (
                    (df['VisitName'].astype(str).str.upper().str.strip() == 'SIV') &
                    (df['VisitType'].astype(str).str.lower() != 'siv')
                )
                if siv_mask.any():
                    df.loc[siv_mask, 'VisitType'] = 'siv'
                
                monitor_mask = (
                    df['VisitName'].astype(str).str.contains('Monitor', case=False, na=False) &
                    (df['VisitType'].astype(str).str.lower() != 'monitor')
                )
                if monitor_mask.any():
                    df.loc[monitor_mask, 'VisitType'] = 'monitor'
            
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
        
        # Check for corrected visit types
        if 'VisitType' in df.columns:
            siv_corrected = ((df['VisitName'].astype(str).str.upper().str.strip() == 'SIV') & 
                           (df['VisitType'].astype(str).str.lower() == 'siv')).sum()
            monitor_corrected = ((df['VisitName'].astype(str).str.contains('Monitor', case=False, na=False)) & 
                               (df['VisitType'].astype(str).str.lower() == 'monitor')).sum()
            if siv_corrected > 0:
                log_activity(f"🔧 CORRECTED {siv_corrected} SIV event(s) in database (were marked as patient visits)", level='warning')
            if monitor_corrected > 0:
                log_activity(f"🔧 CORRECTED {monitor_corrected} Monitor event(s) in database (were marked as patient visits)", level='warning')
        
        # Log what was loaded
        log_activity(f"📥 Loaded {len(df)} actual visits from database", level='success')
        if not df.empty:
            # Show breakdown by visit type
            if 'VisitType' in df.columns:
                visit_types = df['VisitType'].value_counts().to_dict()
                log_activity(f"   Visit types: {visit_types}", level='info')
            # Show some sample visits for debugging
            for idx, row in df.head(3).iterrows():
                log_activity(f"   Sample: {row['PatientID']} - {row['VisitName']} (Type: {row.get('VisitType', 'unknown')}) ({row['ActualDate'].strftime('%Y-%m-%d') if pd.notna(row['ActualDate']) else 'No date'})", level='info')
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
        
        # END NEW VALIDATION
        
        records = []
        # OPTIMIZED: Use itertuples for faster iteration (2-3x faster than iterrows)
        for row_tuple in patients_df.itertuples(index=False):
            start_date = None
            if pd.notna(row_tuple.StartDate):
                try:
                    if isinstance(row_tuple.StartDate, str):
                        from datetime import datetime
                        start_date = datetime.strptime(row_tuple.StartDate, '%d/%m/%Y').date()
                    else:
                        start_date = row_tuple.StartDate.date() if hasattr(row_tuple.StartDate, 'date') else row_tuple.StartDate
                except Exception as date_error:
                    log_activity(f"Date parsing error for patient {row_tuple.PatientID}: {date_error}", level='warning')
                    start_date = None
            
            record = {
                'patient_id': str(row_tuple.PatientID),
                'study': str(row_tuple.Study),
                'start_date': str(start_date) if start_date else None,
                'patient_practice': str(getattr(row_tuple, 'PatientPractice', ''))
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
        
        # NEW: Validate all trials have valid SiteforVisit BEFORE attempting to save
        if 'SiteforVisit' not in trials_df_clean.columns:
            log_activity("ERROR: SiteforVisit column missing from trials data", level='error')
            return False
        
        # Check for invalid site values
        invalid_sites = ['', 'nan', 'None', 'null', 'NULL', 'Unknown Site', 'unknown site', 'UNKNOWN SITE', 'Default Site']
        trials_df_clean['SiteforVisit'] = trials_df_clean['SiteforVisit'].fillna('').astype(str).str.strip()
        invalid_mask = trials_df_clean['SiteforVisit'].isin(invalid_sites)
        
        if invalid_mask.any():
            invalid_trials = trials_df_clean[invalid_mask][['Study', 'VisitName']].values.tolist()
            error_msg = f"Cannot save trials with missing SiteforVisit: {invalid_trials}"
            log_activity(error_msg, level='error')
            st.error(f"❌ Data validation failed: {len(invalid_trials)} trial(s) missing visit site")
            return False
        
        # END NEW VALIDATION
        
        if 'ToleranceBefore' in trials_df_clean.columns:
            trials_df_clean['ToleranceBefore'] = trials_df_clean['ToleranceBefore'].replace('', 0)
            trials_df_clean['ToleranceBefore'] = pd.to_numeric(trials_df_clean['ToleranceBefore'], errors='coerce').fillna(0)
        
        if 'ToleranceAfter' in trials_df_clean.columns:
            trials_df_clean['ToleranceAfter'] = trials_df_clean['ToleranceAfter'].replace('', 0)
            trials_df_clean['ToleranceAfter'] = pd.to_numeric(trials_df_clean['ToleranceAfter'], errors='coerce').fillna(0)
        
        records = []
        # OPTIMIZED: Use itertuples for faster iteration (2-3x faster than iterrows)
        for row_tuple in trials_df_clean.itertuples(index=False):
            record = {
                'study': str(row_tuple.Study),
                'day': int(row_tuple.Day),
                'visit_name': str(row_tuple.VisitName),
                'site_for_visit': str(getattr(row_tuple, 'SiteforVisit', '')),
                'payment': float(getattr(row_tuple, 'Payment', 0)),
                'tolerance_before': int(getattr(row_tuple, 'ToleranceBefore', 0)),
                'tolerance_after': int(getattr(row_tuple, 'ToleranceAfter', 0)),
                # Optional month-based interval fields
                'interval_unit': (str(getattr(row_tuple, 'IntervalUnit', '')).lower().strip() if pd.notna(getattr(row_tuple, 'IntervalUnit', None)) else None),
                'interval_value': (int(getattr(row_tuple, 'IntervalValue', 0)) if pd.notna(getattr(row_tuple, 'IntervalValue', None)) else None)
            }
            records.append(record)
        
        log_activity(f"Sample trial records: {records[:3]}", level='info')
        log_activity(f"Payment values in records: {[r['payment'] for r in records[:5]]}", level='info')
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
        visit_type_series = get_visit_type_series(actual_visits_df, default='patient')
        
        records = []
        # OPTIMIZED: Use itertuples for faster iteration (2-3x faster than iterrows)
        for row_tuple in actual_visits_df.itertuples(index=True):
            idx = row_tuple.Index
            actual_date = row_tuple.ActualDate
            if pd.notna(actual_date):
                if isinstance(actual_date, str):
                    actual_date = pd.to_datetime(actual_date, dayfirst=True)
                actual_date_str = str(actual_date.date())
            else:
                actual_date_str = None
            
            visit_type_value = visit_type_series.loc[idx] if idx in visit_type_series.index else 'patient'
                
            record = {
                'patient_id': str(row_tuple.PatientID),
                'study': str(row_tuple.Study),
                'visit_name': str(row_tuple.VisitName),
                'actual_date': actual_date_str,
                'notes': str(getattr(row_tuple, 'Notes', '')),
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
                'patient_id': str(row_tuple.PatientID),
                'study': str(row_tuple.Study),
                'start_date': str(start_date) if start_date else None,
                'patient_practice': str(getattr(row_tuple, 'PatientPractice', ''))
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
                message = f"Exact duplicate found: {duplicate_info['patient_id']} - {duplicate_info['visit_name']} on {duplicate_info['actual_date']}"
                log_activity(f"Duplicate visit prevented: {message}", level='warning')
                return False, message, 'DUPLICATE_FOUND'
            else:
                # Same visit on different date - allow but warn
                message = f"Same visit exists on different date: {duplicate_info['patient_id']} - {duplicate_info['visit_name']} (existing: {duplicate_info['actual_date']})"
                log_activity(f"Visit with different date detected: {message}", level='info')
        
        from helpers import get_visit_type_series
        visit_type_series = get_visit_type_series(visit_df, default='patient')
        
        records = []
        # OPTIMIZED: Use itertuples for faster iteration (2-3x faster than iterrows)
        for row_tuple in visit_df.itertuples(index=True):
            idx = row_tuple.Index
            actual_date = getattr(row_tuple, 'ActualDate', None)
            if pd.notna(actual_date):
                if isinstance(actual_date, str):
                    actual_date = pd.to_datetime(actual_date, dayfirst=True)
                actual_date_str = str(actual_date.date()) if hasattr(actual_date, 'date') else str(actual_date)
            else:
                actual_date_str = None
            
            visit_type_value = visit_type_series.loc[idx] if idx in visit_type_series.index else 'patient'
            
            record = {
                'patient_id': str(row_tuple.PatientID),
                'study': str(row_tuple.Study),
                'visit_name': str(row_tuple.VisitName),
                'actual_date': actual_date_str,
                'notes': str(getattr(row_tuple, 'Notes', '')),
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
        
        # Normalize column names to match our format
        existing_visits = existing_visits.rename(columns={
            'patient_id': 'PatientID',
            'study': 'Study', 
            'visit_name': 'VisitName',
            'actual_date': 'ActualDate'
        })
        
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
            
            # Normalize existing dates
            existing_visits_copy = existing_visits.copy()
            if 'ActualDate' in existing_visits_copy.columns:
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
            
            if not exact_match.empty:
                duplicate_info = exact_match.iloc[0]
                return {
                    'has_duplicates': True,
                    'is_exact_duplicate': True,
                    'duplicates': {
                        'patient_id': duplicate_info['PatientID'],
                        'study': duplicate_info['Study'],
                        'visit_name': duplicate_info['VisitName'],
                        'actual_date': duplicate_info['ActualDate']
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
                        'patient_id': duplicate_info['PatientID'],
                        'study': duplicate_info['Study'],
                        'visit_name': duplicate_info['VisitName'],
                        'actual_date': duplicate_info['ActualDate']
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
        # OPTIMIZED: Use itertuples for faster iteration (2-3x faster than iterrows)
        for row_tuple in schedule_df_clean.itertuples(index=False):
            record = {
                'study': str(row_tuple.Study),
                'day': int(getattr(row_tuple, 'Day', 0)),
                'visit_name': str(row_tuple.VisitName),
                'site_for_visit': str(getattr(row_tuple, 'SiteforVisit', '')),
                'payment': float(getattr(row_tuple, 'Payment', 0)),
                'tolerance_before': int(getattr(row_tuple, 'ToleranceBefore', 0)),
                'tolerance_after': int(getattr(row_tuple, 'ToleranceAfter', 0)),
                # Optional month-based interval fields
                'interval_unit': (str(getattr(row_tuple, 'IntervalUnit', '')).lower().strip() if pd.notna(getattr(row_tuple, 'IntervalUnit', None)) else None),
                'interval_value': (int(getattr(row_tuple, 'IntervalValue', 0)) if pd.notna(getattr(row_tuple, 'IntervalValue', None)) else None)
            }
            records.append(record)
        
        response = client.table('trial_schedules').insert(records).execute()
        log_activity(f"Appended {len(records)} trial schedule(s) to database", level='success')
        return True
        
    except Exception as e:
        log_activity(f"Error appending trial schedule: {e}", level='error')
        return False

def export_patients_to_csv() -> Optional[pd.DataFrame]:
    """Export patients from database in upload-ready CSV format"""
    try:
        df = fetch_all_patients()
        if df is None or df.empty:
            return pd.DataFrame(columns=['PatientID', 'Study', 'StartDate', 'PatientPractice'])
        
        for col in ['PatientPractice']:
            if col not in df.columns:
                df[col] = ''
        
        if 'StartDate' in df.columns:
            df['StartDate'] = pd.to_datetime(df['StartDate']).dt.strftime('%d/%m/%Y')
        
        export_columns = ['PatientID', 'Study', 'StartDate', 'PatientPractice']
        df = df[export_columns]
        
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
        
        export_columns = ['Study', 'Day', 'VisitName', 'SiteforVisit', 'Payment', 'ToleranceBefore', 'ToleranceAfter', 'IntervalUnit', 'IntervalValue']
        df = df[export_columns]
        
        return df
    except Exception as e:
        st.error(f"Error exporting trials: {e}")
        return None

def export_visits_to_csv() -> Optional[pd.DataFrame]:
    """Export actual visits from database in upload-ready CSV format"""
    try:
        df = fetch_all_actual_visits()
        if df is None or df.empty:
            return pd.DataFrame(columns=['PatientID', 'Study', 'VisitName', 'ActualDate', 'Notes'])
        
        if 'Notes' not in df.columns:
            df['Notes'] = ''
        
        if 'ActualDate' in df.columns:
            df['ActualDate'] = pd.to_datetime(df['ActualDate'], errors='coerce').dt.strftime('%d/%m/%Y')
        
        export_columns = ['PatientID', 'Study', 'VisitName', 'ActualDate', 'Notes']
        df = df[export_columns]
        
        return df
    except Exception as e:
        st.error(f"Error exporting visits: {e}")
        return None

def create_backup_zip() -> Optional[io.BytesIO]:
    """Create a ZIP file containing all three database tables as CSVs"""
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        
        patients_df = export_patients_to_csv()
        trials_df = export_trials_to_csv()
        visits_df = export_visits_to_csv()
        
        if patients_df is None or trials_df is None or visits_df is None:
            st.error("Failed to export one or more tables")
            return None
        
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            patients_csv = patients_df.to_csv(index=False)
            zip_file.writestr(f'patients_backup_{today}.csv', patients_csv)
            
            trials_csv = trials_df.to_csv(index=False)
            zip_file.writestr(f'trials_backup_{today}.csv', trials_csv)
            
            visits_csv = visits_df.to_csv(index=False)
            zip_file.writestr(f'actual_visits_backup_{today}.csv', visits_csv)
        
        zip_buffer.seek(0)
        return zip_buffer
        
    except Exception as e:
        st.error(f"Error creating backup ZIP: {e}")
        return None

def clear_patients_table() -> bool:
    """Clear all patients from database"""
    try:
        client = get_supabase_client()
        if client is None:
            return False
        
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
        
        client.table('actual_visits').delete().neq('id', 0).execute()
        log_activity("Cleared all actual visits from database", level='info')
        return True
        
    except Exception as e:
        st.error(f"Error clearing actual visits table: {e}")
        log_activity(f"Error clearing actual visits table: {e}", level='error')
        return False

def overwrite_database_with_files(patients_df: pd.DataFrame, trials_df: pd.DataFrame, actual_visits_df: pd.DataFrame = None) -> bool:
    """Completely replace database content with uploaded files"""
    try:
        if not clear_patients_table():
            return False
        if not clear_trial_schedules_table():
            return False
        if actual_visits_df is not None and not actual_visits_df.empty:
            if not clear_actual_visits_table():
                return False
        
        if not save_patients_to_database(patients_df):
            return False
        if not save_trial_schedules_to_database(trials_df):
            return False
        if actual_visits_df is not None and not actual_visits_df.empty:
            if not save_actual_visits_to_database(actual_visits_df):
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
        patient_check = client.table('patients').select('*').eq('patient_id', patient_id).eq('study', old_study).execute()
        if not patient_check.data:
            log_activity(f"Cannot switch patient study: Patient {patient_id} not found in study {old_study}", level='error')
            return False, f"Patient {patient_id} not found in study {old_study}", 0
        
        # Check if target study exists in trial schedules
        trial_check = client.table('trial_schedules').select('study').eq('study', new_study).limit(1).execute()
        if not trial_check.data:
            log_activity(f"Cannot switch patient study: Target study {new_study} not found in trial schedules", level='error')
            return False, f"Target study {new_study} not found in trial schedules", 0
        
        # Check if target study has exactly one Day 1 visit
        day1_check = client.table('trial_schedules').select('*').eq('study', new_study).eq('day', 1).execute()
        if len(day1_check.data) != 1:
            log_activity(f"Cannot switch patient study: Target study {new_study} has {len(day1_check.data)} Day 1 visits (should be exactly 1)", level='error')
            return False, f"Target study {new_study} must have exactly one Day 1 visit", 0
        
        # Get count of actual visits to update
        visits_check = client.table('actual_visits').select('id').eq('patient_id', patient_id).eq('study', old_study).execute()
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
            'study': new_study,
            'start_date': db_start_date
        }).eq('patient_id', patient_id).eq('study', old_study).execute()
        
        if not patient_update.data:
            log_activity(f"Failed to update patient {patient_id} record", level='error')
            return False, "Failed to update patient record", 0
        
        # Update all actual visits for this patient
        visits_update = client.table('actual_visits').update({
            'study': new_study
        }).eq('patient_id', patient_id).eq('study', old_study).execute()
        
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
        
        log_activity(f"Created backup of {table_name} with {len(backup_df) if backup_df is not None else 0} records", level='info')
        
        clear_function = None
        if table_name == 'patients':
            clear_function = clear_patients_table
        elif table_name == 'trial_schedules':
            clear_function = clear_trial_schedules_table
        elif table_name == 'actual_visits':
            clear_function = clear_actual_visits_table
        
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
                log_activity(f"Restored backup for {table_name}", level='info')
            return False
        
        log_activity(f"Successfully overwrote {table_name} table with {len(df)} records", level='success')
        return True
        
    except Exception as e:
        log_activity(f"Error in safe overwrite of {table_name}: {e}", level='error')
        return False
