import streamlit as st
import pandas as pd
import os
from database_service import db_service

def initialize_session_state():
    """Initialize all session state variables"""
    if 'show_patient_form' not in st.session_state:
        st.session_state.show_patient_form = False
    if 'show_visit_form' not in st.session_state:
        st.session_state.show_visit_form = False
    if 'patient_added' not in st.session_state:
        st.session_state.patient_added = False
    if 'visit_added' not in st.session_state:
        st.session_state.visit_added = False
    if 'list_weight' not in st.session_state:
        st.session_state.list_weight = 35
    if 'work_weight' not in st.session_state:
        st.session_state.work_weight = 35
    if 'recruitment_weight' not in st.session_state:
        st.session_state.recruitment_weight = 30
    if 'show_weights_form' not in st.session_state:
        st.session_state.show_weights_form = False
    if 'use_database' not in st.session_state:
        st.session_state.use_database = False
    if 'database_connected' not in st.session_state:
        st.session_state.database_connected = False
    if 'supabase_url' not in st.session_state:
        st.session_state.supabase_url = ""
    if 'supabase_key' not in st.session_state:
        st.session_state.supabase_key = ""
    if 'user_email' not in st.session_state:
        st.session_state.user_email = ""

def get_file_structure_info():
    """Return file structure information as markdown"""
    return """
    **Patients File:**
    - PatientID, Study, StartDate
    - Site/PatientPractice (optional - for patient origin)
    
    **Trials File:**
    - Study, Day, VisitName, SiteforVisit
    - Income/Payment, ToleranceBefore, ToleranceAfter (optional)
    
    **Actual Visits File (Optional):**
    - PatientID, Study, VisitName, ActualDate
    - ActualPayment, Notes (optional)
    - Use 'ScreenFail' in Notes to stop future visits
    """

def setup_database_connection():
    """Setup database connection in sidebar"""
    st.sidebar.header("Database Connection")
    
    # Mode selection
    use_database = st.sidebar.radio(
        "Data Source",
        ["Upload Files", "Supabase Database"],
        help="Choose between file upload mode or database mode"
    )
    
    st.session_state.use_database = (use_database == "Supabase Database")
    
    if st.session_state.use_database:
        # Database configuration
        st.sidebar.subheader("Database Settings")
        
        # Load from environment if available
        default_url = os.getenv('SUPABASE_URL', st.session_state.supabase_url)
        default_key = os.getenv('SUPABASE_ANON_KEY', st.session_state.supabase_key)
        default_email = os.getenv('USER_EMAIL', st.session_state.user_email)
        
        url = st.sidebar.text_input(
            "Supabase URL",
            value=default_url,
            type="password",
            help="Your Supabase project URL"
        )
        
        key = st.sidebar.text_input(
            "Supabase Anon Key",
            value=default_key,
            type="password",
            help="Your Supabase anon/public key"
        )
        
        email = st.sidebar.text_input(
            "User Email",
            value=default_email,
            help="Your email for database access"
        )
        
        # Store in session state
        st.session_state.supabase_url = url
        st.session_state.supabase_key = key
        st.session_state.user_email = email
        
        # Connect button
        if st.sidebar.button("Connect to Database", use_container_width=True):
            if url and key:
                with st.spinner("Connecting to database..."):
                    success = db_service.connect(url, key, email)
                    st.session_state.database_connected = success
                    
                if success:
                    st.sidebar.success("✅ Connected to database!")
                else:
                    st.sidebar.error("❌ Failed to connect to database")
            else:
                st.sidebar.error("Please provide URL and Key")
        
        # Connection status
        if st.session_state.database_connected:
            st.sidebar.success("🟢 Database Connected")
            
            # Disconnect button
            if st.sidebar.button("Disconnect", use_container_width=True):
                db_service.connected = False
                st.session_state.database_connected = False
                st.rerun()
        else:
            st.sidebar.warning("🔴 Database Disconnected")
    
    return use_database == "Supabase Database"

def load_data_from_source():
    """Load data from either files or database based on current mode"""
    if st.session_state.use_database and st.session_state.database_connected:
        # Load from database
        patients_df = db_service.load_patients()
        trials_df = db_service.load_trials()
        actual_visits_df = db_service.load_actual_visits()
        
        return patients_df, trials_df, actual_visits_df, None, None, None
    else:
        # Load from files (existing logic)
        patients_file = st.session_state.get('patients_file')
        trials_file = st.session_state.get('trials_file')
        actual_visits_file = st.session_state.get('actual_visits_file')
        
        if patients_file and trials_file:
            from helpers import load_file, normalize_columns, load_file_with_defaults
            
            patients_df = normalize_columns(load_file(patients_file))
            trials_df = normalize_columns(load_file(trials_file))
            actual_visits_df = None
            
            if actual_visits_file:
                actual_visits_df = normalize_columns(load_file_with_defaults(
                    actual_visits_file,
                    {'VisitType': 'patient', 'Status': 'completed'}
                ))
            
            return patients_df, trials_df, actual_visits_df, patients_file, trials_file, actual_visits_file
        
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), None, None, None

# Application constants
APP_TITLE = "Clinical Trial Calendar Generator"
APP_VERSION = "v2.5.0"
APP_SUBTITLE = "Enhanced Version - Database & File Support"

# Default profit sharing weights
DEFAULT_LIST_WEIGHT = 35
DEFAULT_WORK_WEIGHT = 35  
DEFAULT_RECRUITMENT_WEIGHT = 30

# Fixed list sizes for profit sharing
ASHFIELDS_LIST_SIZE = 28500
KILTEARN_LIST_SIZE = 12500