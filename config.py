import streamlit as st
import pandas as pd

def initialize_session_state():
    """Initialize all session state variables"""
    from helpers import init_activity_log, init_error_system
    
    # Authentication state - public by default
    if 'auth_level' not in st.session_state:
        st.session_state.auth_level = 'public'
    
    # Debug level - default to STANDARD
    if 'debug_level' not in st.session_state:
        st.session_state.debug_level = DEBUG_STANDARD
    
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
    if 'calendar_cache_buster' not in st.session_state:
        st.session_state.calendar_cache_buster = 0
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
    - Use 'ScreenFail' in Notes to stop future visits (screen failure)
    - Use 'Withdrawn' in Notes to stop future visits (patient withdrawal)
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

# =============================================================================
# DEBUG SYSTEM CONFIGURATION
# =============================================================================

# Debug level constants
DEBUG_OFF = 0
DEBUG_ERRORS = 1
DEBUG_STANDARD = 2
DEBUG_VERBOSE = 3
DEBUG_DEBUG = 4

def get_debug_level():
    """Get current debug level from session state, defaulting to STANDARD"""
    try:
        return st.session_state.get('debug_level', DEBUG_STANDARD)
    except:
        # Fallback if streamlit not available (e.g., in tests)
        return DEBUG_STANDARD

def should_log_debug():
    """Check if detailed debug logging should occur (level >= DEBUG)"""
    return get_debug_level() >= DEBUG_DEBUG

def should_log_info():
    """Check if info level logging should occur (level >= VERBOSE)"""
    return get_debug_level() >= DEBUG_VERBOSE

def should_log_warning():
    """Check if warning level logging should occur (level >= STANDARD)"""
    return get_debug_level() >= DEBUG_STANDARD

def should_log_error():
    """Check if error level logging should occur (level >= ERRORS)"""
    return get_debug_level() >= DEBUG_ERRORS

def should_show_debug_ui():
    """Check if debug UI elements should be visible (level >= VERBOSE)"""
    return get_debug_level() >= DEBUG_VERBOSE
