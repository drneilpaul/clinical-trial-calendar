import streamlit as st
from supabase import create_client, Client
import pandas as pd
from typing import Optional, Dict, List
import io
from datetime import datetime
import zipfile

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
                'site': 'Site'
            })
            return df
        return pd.DataFrame()
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
        return pd.DataFrame()
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
                'notes': 'Notes'
            })
            return df
        return pd.DataFrame()
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
            record = {
                'patient_id': str(row['PatientID']),
                'study': str(row['Study']),
                'start_date': str(row['StartDate'].date()) if pd.notna(row['StartDate']) else None,
                'site': str(row.get('Site', '')),
                'patient_practice': str(row.get('PatientPractice', '')),
                'origin_site': str(row.get('OriginSite', ''))
            }
            records.append(record)
        
        # Upsert (insert or update)
        client.table('patients').upsert(records).execute()
        return True
        
    except Exception as e:
        st.error(f"Error saving patients to database: {e}")
        return False

def save_trial_schedules_to_database(trials_df: pd.DataFrame) -> bool:
    """Save trial schedules DataFrame to database"""
    try:
        client = get_supabase_client()
        if client is None:
            return False
        
        records = []
        for _, row in trials_df.iterrows():
            record = {
                'study': str(row['Study']),
                'day': int(row['Day']),
                'visit_name': str(row['VisitName']),
                'site_for_visit': str(row.get('SiteforVisit', '')),
                'payment': float(row.get('Payment', 0)) if pd.notna(row.get('Payment')) else 0,
                'tolerance_before': int(row.get('ToleranceBefore', 0)) if pd.notna(row.get('ToleranceBefore')) else 0,
                'tolerance_after': int(row.get('ToleranceAfter', 0)) if pd.notna(row.get('ToleranceAfter')) else 0
            }
            records.append(record)
        
        client.table('trial_schedules').upsert(records).execute()
        return True
        
    except Exception as e:
        st.error(f"Error saving trial schedules to database: {e}")
        return False

def save_actual_visits_to_database(actual_visits_df: pd.DataFrame) -> bool:
    """Save actual visits DataFrame to database"""
    try:
        client = get_supabase_client()
        if client is None:
            return False
        
        records = []
        for _, row in actual_visits_df.iterrows():
            record = {
                'patient_id': str(row['PatientID']),
                'study': str(row['Study']),
                'visit_name': str(row['VisitName']),
                'actual_date': str(row['ActualDate'].date()) if pd.notna(row['ActualDate']) else None,
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
