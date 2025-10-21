import streamlit as st
import pandas as pd

def initialize_session_state():
    """Initialize all session state variables"""
    from helpers import init_activity_log, init_error_system
    
    # Authentication state - public by default
    if 'auth_level' not in st.session_state:
        st.session_state.auth_level = 'public'
    
    if 'show_patient_form' not in st.session_state:
        st.session_state.show_patient_form = False
    if 'show_visit_form' not in st.session_state:
        st.session_state.show_visit_form = False
    if 'show_study_event_form' not in st.session_state:
        st.session_state.show_study_event_form = False
    if 'any_dialog_open' not in st.session_state:
        st.session_state.any_dialog_open = False
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

# Application constants
APP_TITLE = "Clinical Trial Calendar Generator"
APP_VERSION = "v1.1"
APP_SUBTITLE = "Initial Release"

# Default profit sharing weights
DEFAULT_LIST_WEIGHT = 35
DEFAULT_WORK_WEIGHT = 35  
DEFAULT_RECRUITMENT_WEIGHT = 30

# Fixed list sizes for profit sharing
ASHFIELDS_LIST_SIZE = 28500
KILTEARN_LIST_SIZE = 12500
