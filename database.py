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

def fetch_all_patients() -> Optional[pd.DataFrame]:
    """Fetch all patients from database"""
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
            
            log_activity(f"Fetched {len(df)} patients from database", level='info')
            return df
        log_activity("No patients found in database", level='info')
        return pd.DataFrame(columns=['PatientID', 'Study', 'StartDate', 'PatientPractice'])
    except Exception as e:
        st.error(f"Error fetching patients: {e}")
        return None

def fetch_all_trial_schedules() -> Optional[pd.DataFrame]:
    """Fetch all trial schedules from database"""
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
                'tolerance_after': 'ToleranceAfter'
            })
            return df
        return pd.DataFrame(columns=['Study', 'Day', 'VisitName', 'SiteforVisit', 'Payment', 'ToleranceBefore', 'ToleranceAfter'])
    except Exception as e:
        st.error(f"Error fetching trial schedules: {e}")
        return None

def fetch_all_actual_visits() -> Optional[pd.DataFrame]:
    """Fetch all actual visits from database"""
    try:
        client = get_supabase_client()
        if client is None:
            return None
        
        response = client.table('actual_visits').select("*").execute()
        
        if response.data:
            df = pd.DataFrame(response.data)
            
            df = df.rename(columns={
                'patient_id': 'PatientID',
                'study': 'Study',
                'visit_name': 'VisitName',
                'actual_date': 'ActualDate',
                'notes': 'Notes',
                'visit_type': 'VisitType'
            })
            
            if 'ActualDate' in df.columns:
                df['ActualDate'] = pd.to_datetime(df['ActualDate'], errors='coerce')
                
                nat_count = df['ActualDate'].isna().sum()
                if nat_count > 0:
                    log_activity(f"Warning: {nat_count} actual visit dates failed to parse from database", level='warning')
            
            return df
        return pd.DataFrame(columns=['PatientID', 'Study', 'VisitName', 'ActualDate', 'Notes', 'VisitType'])
    except Exception as e:
        st.error(f"Error fetching actual visits: {e}")
        return None

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
        for _, row in patients_df.iterrows():
            start_date = None
            if pd.notna(row['StartDate']):
                try:
                    if isinstance(row['StartDate'], str):
                        from datetime import datetime
                        start_date = datetime.strptime(row['StartDate'], '%d/%m/%Y').date()
                    else:
                        start_date = row['StartDate'].date() if hasattr(row['StartDate'], 'date') else row['StartDate']
                except Exception as date_error:
                    log_activity(f"Date parsing error for patient {row['PatientID']}: {date_error}", level='warning')
                    start_date = None
            
            record = {
                'patient_id': str(row['PatientID']),
                'study': str(row['Study']),
                'start_date': str(start_date) if start_date else None,
                'patient_practice': str(row.get('PatientPractice', ''))
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
        for _, row in trials_df_clean.iterrows():
            record = {
                'study': str(row['Study']),
                'day': int(row['Day']),
                'visit_name': str(row['VisitName']),
                'site_for_visit': str(row.get('SiteforVisit', '')),
                'payment': float(row.get('Payment', 0)),
                'tolerance_before': int(row.get('ToleranceBefore', 0)),
                'tolerance_after': int(row.get('ToleranceAfter', 0))
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
        
        records = []
        for _, row in actual_visits_df.iterrows():
            actual_date = row['ActualDate']
            if pd.notna(actual_date):
                if isinstance(actual_date, str):
                    actual_date = pd.to_datetime(actual_date, dayfirst=True)
                actual_date_str = str(actual_date.date())
            else:
                actual_date_str = None
                
            record = {
                'patient_id': str(row['PatientID']),
                'study': str(row['Study']),
                'visit_name': str(row['VisitName']),
                'actual_date': actual_date_str,
                'notes': str(row.get('Notes', '')),
                'visit_type': str(row.get('VisitType', 'patient'))
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
        for _, row in patient_df.iterrows():
            start_date = None
            if pd.notna(row.get('StartDate')):
                try:
                    if isinstance(row['StartDate'], str):
                        start_date = datetime.strptime(row['StartDate'], '%d/%m/%Y').date()
                    else:
                        start_date = row['StartDate'].date() if hasattr(row['StartDate'], 'date') else row['StartDate']
                except Exception as date_error:
                    log_activity(f"Date parsing error: {date_error}", level='warning')
                    start_date = None
            
            record = {
                'patient_id': str(row['PatientID']),
                'study': str(row['Study']),
                'start_date': str(start_date) if start_date else None,
                'patient_practice': str(row.get('PatientPractice', ''))
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
        
        records = []
        for _, row in visit_df.iterrows():
            actual_date = row.get('ActualDate')
            if pd.notna(actual_date):
                if isinstance(actual_date, str):
                    actual_date = pd.to_datetime(actual_date, dayfirst=True)
                actual_date_str = str(actual_date.date()) if hasattr(actual_date, 'date') else str(actual_date)
            else:
                actual_date_str = None
            
            record = {
                'patient_id': str(row['PatientID']),
                'study': str(row['Study']),
                'visit_name': str(row['VisitName']),
                'actual_date': actual_date_str,
                'notes': str(row.get('Notes', '')),
                'visit_type': str(row.get('VisitType', 'patient'))
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
        for _, row in schedule_df_clean.iterrows():
            record = {
                'study': str(row['Study']),
                'day': int(row.get('Day', 0)),
                'visit_name': str(row['VisitName']),
                'site_for_visit': str(row.get('SiteforVisit', '')),
                'payment': float(row.get('Payment', 0)),
                'tolerance_before': int(row.get('ToleranceBefore', 0)),
                'tolerance_after': int(row.get('ToleranceAfter', 0))
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
            return pd.DataFrame(columns=['Study', 'Day', 'VisitName', 'SiteforVisit', 'Payment', 'ToleranceBefore', 'ToleranceAfter'])
        
        if 'Payment' not in df.columns:
            df['Payment'] = 0
        if 'ToleranceBefore' not in df.columns:
            df['ToleranceBefore'] = 0
        if 'ToleranceAfter' not in df.columns:
            df['ToleranceAfter'] = 0
        
        export_columns = ['Study', 'Day', 'VisitName', 'SiteforVisit', 'Payment', 'ToleranceBefore', 'ToleranceAfter']
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
