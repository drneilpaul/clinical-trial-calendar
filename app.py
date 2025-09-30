import streamlit as st
import pandas as pd
from typing import Optional, Dict, Any, Tuple
import logging
from datetime import datetime

# Import our modules with error handling
try:
    from processing_calendar import build_calendar, validate_calendar_data
    from helpers import (
        load_file_safe, display_messages_section, clear_messages, 
        has_critical_errors, add_error, add_warning, add_info,
        init_error_system, safe_string_conversion
    )
    from modal_forms import show_manual_entry_modal
    from config import get_file_structure_info
except ImportError as e:
    st.error(f"Failed to import required modules: {e}")
    st.stop()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Page configuration
st.set_page_config(
    page_title="Clinical Trial Calendar Generator",
    page_icon="📅",
    layout="wide",
    initial_sidebar_state="expanded"
)

def init_session_state():
    """Initialize session state with proper error handling system"""
    try:
        init_error_system()
        
        # File upload state
        if 'patients_file' not in st.session_state:
            st.session_state.patients_file = None
        if 'trials_file' not in st.session_state:
            st.session_state.trials_file = None
        if 'actual_visits_file' not in st.session_state:
            st.session_state.actual_visits_file = None
        
        # Processing state
        if 'calendar_generated' not in st.session_state:
            st.session_state.calendar_generated = False
        if 'last_result' not in st.session_state:
            st.session_state.last_result = None
        if 'data_validated' not in st.session_state:
            st.session_state.data_validated = False
            
    except Exception as e:
        st.error(f"Failed to initialize session state: {e}")
        logger.error(f"Session state initialization failed: {e}")

def validate_uploaded_file(uploaded_file, file_type: str, required_columns: list) -> Tuple[bool, Optional[pd.DataFrame]]:
    """
    Validate uploaded file and return success status and DataFrame
    
    Args:
        uploaded_file: Streamlit uploaded file object
        file_type: Description of file type for error messages
        required_columns: List of required column names
        
    Returns:
        Tuple of (success: bool, dataframe: Optional[pd.DataFrame])
    """
    if uploaded_file is None:
        add_error(f"{file_type} file is required")
        return False, None
    
    try:
        # Load file with error handling
        df = load_file_safe(uploaded_file)
        if df is None:
            add_error(f"Failed to load {file_type} file")
            return False, None
            
        if df.empty:
            add_error(f"{file_type} file is empty")
            return False, None
        
        # Check required columns
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            add_error(f"{file_type} file missing required columns: {', '.join(missing_columns)}")
            add_info(f"Available columns: {', '.join(df.columns.tolist())}")
            return False, None
        
        # Log successful validation
        add_info(f"{file_type} file validated successfully ({len(df)} rows)")
        return True, df
        
    except Exception as e:
        add_error(f"Error validating {file_type} file: {str(e)}")
        logger.error(f"File validation error for {file_type}: {e}")
        return False, None

def setup_file_uploaders() -> Dict[str, Any]:
    """
    Setup file uploaders with comprehensive validation
    
    Returns:
        Dictionary with validation results and DataFrames
    """
    st.sidebar.header("📁 Upload Files")
    
    # Clear previous validation state when new files uploaded
    if st.sidebar.button("🔄 Clear All Files"):
        for key in ['patients_file', 'trials_file', 'actual_visits_file']:
            if key in st.session_state:
                st.session_state[key] = None
        st.session_state.data_validated = False
        clear_messages()
        st.rerun()
    
    result = {
        'files_valid': False,
        'patients_df': None,
        'trials_df': None, 
        'actual_visits_df': None
    }
    
    # Patients file uploader
    patients_file = st.sidebar.file_uploader(
        "Upload Patients File",
        type=['csv', 'xlsx'],
        help="Required columns: PatientID, Study, StartDate",
        key="patients_uploader"
    )
    
    # Trials file uploader
    trials_file = st.sidebar.file_uploader(
        "Upload Trials File", 
        type=['csv', 'xlsx'],
        help="Required columns: Study, Day, VisitName",
        key="trials_uploader"
    )
    
    # Actual visits file uploader (optional)
    actual_visits_file = st.sidebar.file_uploader(
        "Upload Actual Visits File (Optional)",
        type=['csv', 'xlsx'],
        help="Required columns: PatientID, Study, VisitName, ActualDate",
        key="actual_visits_uploader"
    )
    
    # Validate required files
    patients_valid, patients_df = validate_uploaded_file(
        patients_file, "Patients", ['PatientID', 'Study', 'StartDate']
    )
    
    trials_valid, trials_df = validate_uploaded_file(
        trials_file, "Trials", ['Study', 'Day', 'VisitName']
    )
    
    # Validate optional actual visits file
    actual_visits_df = None
    if actual_visits_file is not None:
        actual_visits_valid, actual_visits_df = validate_uploaded_file(
            actual_visits_file, "Actual Visits", ['PatientID', 'Study', 'VisitName', 'ActualDate']
        )
        if not actual_visits_valid:
            add_warning("Actual visits file has validation issues - proceeding without it")
            actual_visits_df = None
    
    # Update result
    result.update({
        'files_valid': patients_valid and trials_valid,
        'patients_df': patients_df,
        'trials_df': trials_df,
        'actual_visits_df': actual_visits_df
    })
    
    return result

def process_calendar_with_error_collection(patients_df: pd.DataFrame, 
                                         trials_df: pd.DataFrame, 
                                         actual_visits_df: Optional[pd.DataFrame] = None) -> Optional[pd.DataFrame]:
    """
    Process calendar generation with comprehensive error collection
    
    Args:
        patients_df: Validated patients DataFrame
        trials_df: Validated trials DataFrame  
        actual_visits_df: Optional actual visits DataFrame
        
    Returns:
        Generated calendar DataFrame or None if critical errors occurred
    """
    try:
        add_info("Starting calendar generation...")
        
        # Pre-processing validation
        if not validate_calendar_data(patients_df, trials_df):
            add_error("Data validation failed - cannot proceed with calendar generation")
            return None
        
        # Generate calendar with error handling
        calendar_result = build_calendar(
            patients_df=patients_df,
            trials_df=trials_df,
            actual_visits_df=actual_visits_df
        )
        
        if calendar_result is None:
            add_error("Calendar generation failed - check error messages above")
            return None
            
        if calendar_result.empty:
            add_warning("Calendar generation produced empty result")
            return None
            
        add_info(f"Calendar generated successfully with {len(calendar_result)} visit records")
        return calendar_result
        
    except Exception as e:
        add_error(f"Unexpected error during calendar generation: {str(e)}")
        logger.error(f"Calendar processing error: {e}")
        return None

def display_calendar_results(calendar_df: pd.DataFrame):
    """
    Display calendar results with interactive features
    
    Args:
        calendar_df: Generated calendar DataFrame
    """
    try:
        st.header("📅 Generated Calendar")
        
        # Summary statistics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Visits", len(calendar_df))
        
        with col2:
            unique_patients = calendar_df['PatientID'].nunique() if 'PatientID' in calendar_df.columns else 0
            st.metric("Patients", unique_patients)
        
        with col3:
            unique_studies = calendar_df['Study'].nunique() if 'Study' in calendar_df.columns else 0
            st.metric("Studies", unique_studies)
            
        with col4:
            # Count overdue visits if ActualDate column exists
            if 'ActualDate' in calendar_df.columns and 'PlannedDate' in calendar_df.columns:
                today = datetime.now().date()
                overdue = len(calendar_df[
                    (calendar_df['ActualDate'].isna()) & 
                    (pd.to_datetime(calendar_df['PlannedDate']).dt.date < today)
                ])
                st.metric("Overdue Visits", overdue)
        
        # Display options
        st.subheader("Display Options")
        
        col1, col2 = st.columns(2)
        with col1:
            show_all = st.checkbox("Show all visits", value=True)
            if not show_all:
                max_rows = st.number_input("Max rows to display", min_value=10, max_value=1000, value=100)
                calendar_display = calendar_df.head(max_rows)
            else:
                calendar_display = calendar_df
                
        with col2:
            if st.button("📥 Download Calendar CSV"):
                csv = calendar_display.to_csv(index=False)
                st.download_button(
                    label="Download CSV file",
                    data=csv,
                    file_name=f"clinical_trial_calendar_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime='text/csv'
                )
        
        # Display the calendar
        st.dataframe(
            calendar_display,
            use_container_width=True,
            height=400
        )
        
    except Exception as e:
        add_error(f"Error displaying calendar results: {str(e)}")
        logger.error(f"Display error: {e}")

def main():
    """Main application function with comprehensive error handling"""
    try:
        # Initialize session state
        init_session_state()
        
        # App header
        st.title("🏥 Clinical Trial Calendar Generator")
        st.markdown("Generate comprehensive visit calendars for clinical trials with advanced error handling")
        
        # Setup file uploads and validation
        upload_result = setup_file_uploaders()
        
        # Always show processing messages section
        st.header("📊 Processing Messages")
        display_messages_section()
        
        # Process files if valid
        if upload_result['files_valid']:
            st.success("✅ All required files validated successfully")
            
            # Show process button
            if st.button("🚀 Generate Calendar", type="primary"):
                clear_messages()  # Clear previous messages
                
                # Process with error collection
                calendar_result = process_calendar_with_error_collection(
                    upload_result['patients_df'],
                    upload_result['trials_df'], 
                    upload_result['actual_visits_df']
                )
                
                # Store result in session state
                st.session_state.last_result = calendar_result
                st.session_state.calendar_generated = True
                
                # Refresh to show new messages
                st.rerun()
        
        # Display results if available
        if st.session_state.get('calendar_generated') and st.session_state.get('last_result') is not None:
            if not has_critical_errors():
                display_calendar_results(st.session_state.last_result)
            else:
                st.warning("⚠️ Calendar generated with errors - please review messages above")
                if st.checkbox("Show calendar despite errors"):
                    display_calendar_results(st.session_state.last_result)
        
        # Show manual entry option
        st.sidebar.markdown("---")
        if st.sidebar.button("✏️ Manual Entry"):
            show_manual_entry_modal()
        
        # Show file structure help
        with st.expander("📋 File Structure Requirements"):
            st.markdown(get_file_structure_info())
            
    except Exception as e:
        st.error(f"Critical application error: {str(e)}")
        logger.critical(f"Main application error: {e}")
        st.stop()

if __name__ == "__main__":
    main()
