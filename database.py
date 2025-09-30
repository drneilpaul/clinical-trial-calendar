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
    """
    Get Supabase client with error handling
    Returns None if connection fails
    """
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
        
        # Try to query each table
        client.table('patients').select("id").limit(1).execute()
        client.table('trial_schedules').select("id").limit(1).execute()
        client.table('actual_visits').select("id").limit(1).execute()
        
        st.session_state.database_status = "Connected"
        return True
    except Exception as e:
        st.session_state.database_status = f"Tables not configured: {e}"
        return False

# READ FUNCTIONS
def fetch_all_patients() -> Optional[pd.DataFrame]:
    """Fetch all patients from database"""
    try:
        client = get_supabase_client()
        if client is None:
            return None
        
        response = client.table('patients').select("*").execute()
        
        if response.data:
            df = pd.DataFrame(response.data)
            # Rename columns to match file format
            df = df.rename(columns={
                'patient_id': 'PatientID',
                'study': 'Study',
                'start_date': 'StartDate',
                'site': 'Site',
                'patient_practice': 'PatientPractice',
                'origin_site': 'OriginSite'
            })
            
            # Convert StartDate to datetime format for calendar processing
            if 'StartDate' in df.columns:
                df['StartDate'] = pd.to_datetime(df['StartDate'], errors='coerce')
            
            log_activity(f"Fetched {len(df)} patients from database", level='info')
            return df
        log_activity("No patients found in database", level='info')
        # Return empty DataFrame with proper column structure
        return pd.DataFrame(columns=['PatientID', 'Study', 'StartDate', 'Site', 'PatientPractice', 'OriginSite'])
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
        # Return empty DataFrame with proper column structure
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
            
            # Debug: Log raw database data
            log_activity(f"Raw database actual visits: {len(df)} records", level='info')
            if len(df) > 0:
                log_activity(f"Sample raw data: {df.head(3).to_dict('records')}", level='info')
                log_activity(f"ActualDate column types: {df['actual_date'].apply(type).value_counts().to_dict()}", level='info')
            
            df = df.rename(columns={
                'patient_id': 'PatientID',
                'study': 'Study',
                'visit_name': 'VisitName',
                'actual_date': 'ActualDate',
                'notes': 'Notes'
            })
            
            # Debug: Log after column renaming
            log_activity(f"After column renaming: {df.columns.tolist()}", level='info')
            log_activity(f"ActualDate sample values: {df['ActualDate'].head().tolist()}", level='info')
            
            return df
        # Return empty DataFrame with proper column structure
        return pd.DataFrame(columns=['PatientID', 'Study', 'VisitName', 'ActualDate', 'Notes'])
    except Exception as e:
        st.error(f"Error fetching actual visits: {e}")
        return None

# WRITE FUNCTIONS
def save_patients_to_database(patients_df: pd.DataFrame) -> bool:
    """Save patients DataFrame to database"""
    try:
        client = get_supabase_client()
        if client is None:
            return False
        
        records = []
        for _, row in patients_df.iterrows():
            # Handle date parsing more robustly
            start_date = None
            if pd.notna(row['StartDate']):
                try:
                    if isinstance(row['StartDate'], str):
                        # Try parsing string date
                        from datetime import datetime
                        start_date = datetime.strptime(row['StartDate'], '%d/%m/%Y').date()
                    else:
                        # Already a datetime/date object
                        start_date = row['StartDate'].date() if hasattr(row['StartDate'], 'date') else row['StartDate']
                except Exception as date_error:
                    log_activity(f"Date parsing error for patient {row['PatientID']}: {date_error}", level='warning')
                    start_date = None
            
            record = {
                'patient_id': str(row['PatientID']),
                'study': str(row['Study']),
                'start_date': str(start_date) if start_date else None,
                'site': str(row.get('Site', '')),
                'patient_practice': str(row.get('PatientPractice', '')),
                'origin_site': str(row.get('OriginSite', ''))
            }
            records.append(record)
        
        # Use insert instead of upsert for fresh data
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
        
        # Use centralized payment column handling
        trials_df_clean = normalize_payment_column(trials_df, 'Payment')
        
        # Validate payment data
        payment_validation = validate_payment_data(trials_df_clean, 'Payment')
        if not payment_validation['valid']:
            for issue in payment_validation['issues']:
                log_activity(f"Payment data issue: {issue}", level='warning')
        
        # Clean ToleranceBefore column
        if 'ToleranceBefore' in trials_df_clean.columns:
            trials_df_clean['ToleranceBefore'] = trials_df_clean['ToleranceBefore'].replace('', 0)
            trials_df_clean['ToleranceBefore'] = pd.to_numeric(trials_df_clean['ToleranceBefore'], errors='coerce').fillna(0)
        
        # Clean ToleranceAfter column
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
        
        # Debug: Log sample records
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
            # Ensure ActualDate is a datetime object before calling .date()
            actual_date = row['ActualDate']
            if pd.notna(actual_date):
                if isinstance(actual_date, str):
                    actual_date = pd.to_datetime(actual_date)
                actual_date_str = str(actual_date.date())
            else:
                actual_date_str = None
                
            record = {
                'patient_id': str(row['PatientID']),
                'study': str(row['Study']),
                'visit_name': str(row['VisitName']),
                'actual_date': actual_date_str,
                'notes': str(row.get('Notes', ''))
            }
            records.append(record)
        
        client.table('actual_visits').upsert(records).execute()
        return True
        
    except Exception as e:
        st.error(f"Error saving actual visits to database: {e}")
        return False

# EXPORT FUNCTIONS FOR BACKUP
def export_patients_to_csv() -> Optional[pd.DataFrame]:
    """Export patients from database in upload-ready CSV format"""
    try:
        df = fetch_all_patients()
        if df is None or df.empty:
            # Return empty DataFrame with proper headers
            return pd.DataFrame(columns=['PatientID', 'Study', 'StartDate', 'Site', 'PatientPractice', 'OriginSite'])
        
        # Ensure all expected columns exist
        for col in ['PatientPractice', 'OriginSite']:
            if col not in df.columns:
                df[col] = ''
        
        # Format dates as DD/MM/YYYY
        if 'StartDate' in df.columns:
            df['StartDate'] = pd.to_datetime(df['StartDate']).dt.strftime('%d/%m/%Y')
        
        # Select and order columns to match upload format
        export_columns = ['PatientID', 'Study', 'StartDate', 'Site', 'PatientPractice', 'OriginSite']
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
        
        # Ensure all expected columns exist with proper defaults
        if 'Payment' not in df.columns:
            df['Payment'] = 0
        if 'ToleranceBefore' not in df.columns:
            df['ToleranceBefore'] = 0
        if 'ToleranceAfter' not in df.columns:
            df['ToleranceAfter'] = 0
        
        # Select and order columns to match upload format
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
        
        # Ensure Notes column exists
        if 'Notes' not in df.columns:
            df['Notes'] = ''
        
        # Format dates as DD/MM/YYYY
        if 'ActualDate' in df.columns:
            df['ActualDate'] = pd.to_datetime(df['ActualDate']).dt.strftime('%d/%m/%Y')
        
        # Select and order columns to match upload format
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
        
        # Export all tables
        patients_df = export_patients_to_csv()
        trials_df = export_trials_to_csv()
        visits_df = export_visits_to_csv()
        
        if patients_df is None or trials_df is None or visits_df is None:
            st.error("Failed to export one or more tables")
            return None
        
        # Create ZIP file in memory
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # Add patients CSV
            patients_csv = patients_df.to_csv(index=False)
            zip_file.writestr(f'patients_backup_{today}.csv', patients_csv)
            
            # Add trials CSV
            trials_csv = trials_df.to_csv(index=False)
            zip_file.writestr(f'trials_backup_{today}.csv', trials_csv)
            
            # Add visits CSV
            visits_csv = visits_df.to_csv(index=False)
            zip_file.writestr(f'actual_visits_backup_{today}.csv', visits_csv)
        
        zip_buffer.seek(0)
        return zip_buffer
        
    except Exception as e:
        st.error(f"Error creating backup ZIP: {e}")
        return None

# DATABASE OVERWRITE FUNCTIONS
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
        # Clear all tables first
        if not clear_patients_table():
            return False
        if not clear_trial_schedules_table():
            return False
        if actual_visits_df is not None and not actual_visits_df.empty:
            if not clear_actual_visits_table():
                return False
        
        # Save new data
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
        # Validate data first
        if df is None or df.empty:
            log_activity(f"Cannot overwrite {table_name}: No data provided", level='error')
            return False
        
        log_activity(f"Starting overwrite of {table_name} with {len(df)} records", level='info')
        
        # Create backup first
        backup_df = None
        if table_name == 'patients':
            backup_df = fetch_all_patients()
        elif table_name == 'trial_schedules':
            backup_df = fetch_all_trial_schedules()
        elif table_name == 'actual_visits':
            backup_df = fetch_all_actual_visits()
        
        log_activity(f"Created backup of {table_name} with {len(backup_df) if backup_df is not None else 0} records", level='info')
        
        # Clear table
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
        
        # Save new data
        if not save_function(df):
            log_activity(f"Failed to save new data to {table_name}, attempting restore", level='error')
            # Attempt to restore backup
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
