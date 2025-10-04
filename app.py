import streamlit as st
import pandas as pd
from datetime import datetime
from helpers import (
    load_file, normalize_columns, parse_dates_column, 
    standardize_visit_columns, safe_string_conversion_series, 
    load_file_with_defaults, init_error_system, display_error_log_section,
    log_activity, display_activity_log_sidebar
)
from file_validation import validate_file_upload, get_validation_summary, FileValidationError
import database  # NEW - Supabase integration
from processing_calendar import build_calendar
from display_components import (
    show_legend, display_calendar, display_site_statistics,
    display_download_buttons, display_monthly_income_tables,
    display_quarterly_profit_sharing_tables, display_income_realization_analysis
)
from modal_forms import handle_patient_modal, handle_visit_modal, handle_study_event_modal, show_download_sections
from data_analysis import (
    extract_screen_failures, display_site_wise_statistics, display_processing_messages
)
from calculations import prepare_financial_data
from config import initialize_session_state, get_file_structure_info, APP_TITLE, APP_VERSION, APP_SUBTITLE

def extract_site_summary(patients_df, screen_failures=None):
    """Extract site summary statistics from patients dataframe with robust site detection"""
    if patients_df.empty:
        return pd.DataFrame()

    df = patients_df.copy()
    site_col = None
    for candidate in ['Site', 'PatientPractice', 'PatientSite', 'OriginSite', 'Practice', 'HomeSite']:
        if candidate in df.columns:
            site_col = candidate
            break
    if site_col is None:
        df['__Site'] = 'Unknown Site'
        site_col = '__Site'

    df[site_col] = df[site_col].astype(str).str.strip().replace({'nan': 'Unknown Site'})

    site_summary = df.groupby(site_col).agg({
        'PatientID': 'count',
        'Study': lambda x: ', '.join(sorted(map(str, x.unique())))
    }).rename(columns={'PatientID': 'Patient_Count', 'Study': 'Studies'})

    site_summary = site_summary.reset_index()
    site_summary = site_summary.rename(columns={site_col: 'Site'})
    return site_summary

def process_dates_and_validation(patients_df, trials_df, actual_visits_df):
    """Handle date parsing and basic validation"""
    patients_df, failed_patients = parse_dates_column(patients_df, "StartDate")
    if failed_patients:
        st.error(f"Unparseable StartDate values: {failed_patients}")

    if actual_visits_df is not None:
        actual_visits_df, failed_actuals = parse_dates_column(actual_visits_df, "ActualDate")
        if failed_actuals:
            st.error(f"Unparseable ActualDate values: {failed_actuals}")

    patients_df["PatientID"] = safe_string_conversion_series(patients_df["PatientID"])
    patients_df["Study"] = safe_string_conversion_series(patients_df["Study"])
    
    trials_df = standardize_visit_columns(trials_df)
    trials_df["Study"] = safe_string_conversion_series(trials_df["Study"])
    
    if actual_visits_df is not None:
        actual_visits_df = standardize_visit_columns(actual_visits_df)
        actual_visits_df["PatientID"] = safe_string_conversion_series(actual_visits_df["PatientID"])
        actual_visits_df["Study"] = safe_string_conversion_series(actual_visits_df["Study"])

    missing_studies = set(patients_df["Study"]) - set(trials_df["Study"])
    if missing_studies:
        st.error(f"Missing Study Definitions: {missing_studies}")
        st.stop()

    for study in patients_df["Study"].unique():
        study_visits = trials_df[trials_df["Study"] == study]
        day_1_visits = study_visits[study_visits["Day"] == 1]
        
        if len(day_1_visits) == 0:
            st.error(f"Study {study} has no Day 1 visit defined. Day 1 is required as baseline.")
            st.stop()
        elif len(day_1_visits) > 1:
            visit_names = day_1_visits["VisitName"].tolist()
            st.error(f"Study {study} has multiple Day 1 visits: {visit_names}. Only one Day 1 visit allowed.")
            st.stop()

    return patients_df, trials_df, actual_visits_df

def setup_file_uploaders():
    """Setup file uploaders and store in session state"""
    
    # Initialize variables first
    trials_file = None
    patients_file = None
    actual_visits_file = None
    
    # Database connection status
    if st.session_state.get('database_available', False):
        st.sidebar.success("🟢 Database Connected")
        st.session_state.use_database = True
        
        # Database mode - show file uploaders in expander
        st.sidebar.divider()
        with st.sidebar.expander("📁 Bulk Data Management", expanded=False):
            st.caption("Upload files to replace database data or work with data when database unavailable")
            
            trials_file = st.file_uploader("Upload Trials File", type=['csv', 'xls', 'xlsx'])
            patients_file = st.file_uploader("Upload Patients File", type=['csv', 'xls', 'xlsx'])
            actual_visits_file = st.file_uploader("Upload Actual Visits File (Optional)", type=['csv', 'xls', 'xlsx'])
    else:
        st.sidebar.error("🔴 Database Unavailable")
        st.sidebar.warning("📁 File Upload Mode Available")
        st.sidebar.info("Upload files to work with data, or check database connection")
        st.session_state.use_database = False
        
        # File mode - show file uploaders directly in sidebar
        st.sidebar.divider()
        st.sidebar.subheader("📁 File Upload")
        st.sidebar.caption("Upload files to work with data")
        
        trials_file = st.sidebar.file_uploader("Upload Trials File", type=['csv', 'xls', 'xlsx'])
        patients_file = st.sidebar.file_uploader("Upload Patients File", type=['csv', 'xls', 'xlsx'])
        actual_visits_file = st.sidebar.file_uploader("Upload Actual Visits File (Optional)", type=['csv', 'xls', 'xlsx'])
    
    # Selective overwrite buttons - one for each uploaded file (works for both modes)
    if patients_file or trials_file or actual_visits_file:
        st.sidebar.divider()
        st.sidebar.caption("🔄 **Selective Database Overwrite** - Replace specific tables")
        
        # Patients overwrite
        if patients_file:
            col1, col2 = st.sidebar.columns([3, 1])
            with col1:
                # Pre-validate file structure before showing button
                validation_result = None
                validation_messages = []
                if patients_file:
                    try:
                        # Quick validation check (structure only, not full processing)
                        temp_df, temp_messages = validate_file_upload(patients_file, 'patients')
                        validation_result = temp_df is not None
                        validation_messages = temp_messages
                    except Exception as e:
                        validation_result = False
                        validation_messages = [f"❌ File validation error: {e}"]
                
                # Check if any other overwrite operation is in progress
                if st.session_state.get('overwrite_in_progress', False):
                    st.button("🔄 Overwrite Patients Table", help="Another overwrite operation in progress", disabled=True)
                elif not patients_file:
                    st.button("🔄 Overwrite Patients Table", help="No patients file uploaded", disabled=True)
                elif not validation_result:
                    st.button("🔄 Overwrite Patients Table", help="File validation failed", disabled=True)
                    # Show validation errors prominently
                    st.error("❌ **File validation failed!** Cannot overwrite patients table.")
                    for msg in validation_messages:
                        st.error(f"  • {msg}")
                elif st.button("🔄 Overwrite Patients Table", help="Replace only patients in database"):
                    if st.session_state.get('overwrite_patients_confirmed', False):
                        # Set mutex to prevent other overwrite operations
                        st.session_state.overwrite_in_progress = True
                        st.session_state.overwrite_lock_timestamp = datetime.now()
                        try:
                            # File already validated, proceed with processing
                            patients_df, validation_messages = validate_file_upload(patients_file, 'patients')
                            
                            # Show validation summary (already validated, but show for transparency)
                            if validation_messages:
                                validation_summary = get_validation_summary(
                                    [msg for msg in validation_messages if msg.startswith('❌')],
                                    [msg for msg in validation_messages if msg.startswith('⚠️')]
                                )
                                st.markdown(validation_summary)
                            
                            # Check database availability before overwrite
                            if not st.session_state.get('database_available', False):
                                st.error("❌ Database not available for overwrite operation")
                                return
                            
                            # Use safe overwrite
                            if database.safe_overwrite_table('patients', patients_df, database.save_patients_to_database):
                                st.success("✅ Patients table overwritten successfully!")
                                st.session_state.use_database = True
                                st.session_state.overwrite_patients_confirmed = False
                                # Force refresh of data
                                st.session_state.data_refresh_needed = True
                                st.cache_data.clear()  # Clear cache to get fresh data
                                st.session_state.overwrite_in_progress = False
                                st.session_state.overwrite_lock_timestamp = None
                                st.rerun()
                            else:
                                st.error("❌ Failed to overwrite patients table")
                                st.session_state.overwrite_patients_confirmed = False
                                st.session_state.overwrite_in_progress = False
                                st.session_state.overwrite_lock_timestamp = None
                        except Exception as e:
                            st.error(f"❌ Error processing patients file: {e}")
                            log_activity(f"Error processing patients file: {e}", level='error')
                            st.session_state.overwrite_patients_confirmed = False
                        finally:
                            # Always ensure mutex is released
                            st.session_state.overwrite_in_progress = False
                            st.session_state.overwrite_lock_timestamp = None
                    else:
                        st.session_state.overwrite_patients_confirmed = True
                        st.warning("⚠️ Click again to confirm overwrite")
            with col2:
                if st.button("❌ Cancel Patients", help="Cancel patients overwrite"):
                    st.session_state.overwrite_patients_confirmed = False
                    st.rerun()
        
        # Trials overwrite
        if trials_file:
            col1, col2 = st.sidebar.columns([3, 1])
            with col1:
                # Pre-validate file structure before showing button
                validation_result = None
                validation_messages = []
                if trials_file:
                    try:
                        # Quick validation check (structure only, not full processing)
                        temp_df, temp_messages = validate_file_upload(trials_file, 'trials')
                        validation_result = temp_df is not None
                        validation_messages = temp_messages
                    except Exception as e:
                        validation_result = False
                        validation_messages = [f"❌ File validation error: {e}"]
                
                # Check if any other overwrite operation is in progress
                if st.session_state.get('overwrite_in_progress', False):
                    st.button("🔄 Overwrite Trials Table", help="Another overwrite operation in progress", disabled=True)
                elif not trials_file:
                    st.button("🔄 Overwrite Trials Table", help="No trials file uploaded", disabled=True)
                elif not validation_result:
                    st.button("🔄 Overwrite Trials Table", help="File validation failed", disabled=True)
                    # Show validation errors prominently
                    st.error("❌ **File validation failed!** Cannot overwrite trials table.")
                    for msg in validation_messages:
                        st.error(f"  • {msg}")
                elif st.button("🔄 Overwrite Trials Table", help="Replace only trial schedules in database"):
                    if st.session_state.get('overwrite_trials_confirmed', False):
                        # Set mutex to prevent other overwrite operations
                        st.session_state.overwrite_in_progress = True
                        st.session_state.overwrite_lock_timestamp = datetime.now()
                        try:
                            # File already validated, proceed with processing
                            trials_df, validation_messages = validate_file_upload(trials_file, 'trials')
                            
                            # Show validation summary (already validated, but show for transparency)
                            if validation_messages:
                                validation_summary = get_validation_summary(
                                    [msg for msg in validation_messages if msg.startswith('❌')],
                                    [msg for msg in validation_messages if msg.startswith('⚠️')]
                                )
                                st.markdown(validation_summary)
                            
                            # Check database availability before overwrite
                            if not st.session_state.get('database_available', False):
                                st.error("❌ Database not available for overwrite operation")
                                return
                            
                            # Use safe overwrite
                            if database.safe_overwrite_table('trial_schedules', trials_df, database.save_trial_schedules_to_database):
                                st.success("✅ Trials table overwritten successfully!")
                                st.session_state.use_database = True
                                st.session_state.overwrite_trials_confirmed = False
                                # Force refresh of data
                                st.session_state.data_refresh_needed = True
                                st.cache_data.clear()  # Clear cache to get fresh data
                                st.session_state.overwrite_in_progress = False
                                st.session_state.overwrite_lock_timestamp = None
                                st.rerun()
                            else:
                                st.error("❌ Failed to overwrite trials table")
                                st.session_state.overwrite_trials_confirmed = False
                                st.session_state.overwrite_in_progress = False
                                st.session_state.overwrite_lock_timestamp = None
                        except Exception as e:
                            st.error(f"❌ Error processing trials file: {e}")
                            log_activity(f"Error processing trials file: {e}", level='error')
                            st.session_state.overwrite_trials_confirmed = False
                        finally:
                            # Always ensure mutex is released
                            st.session_state.overwrite_in_progress = False
                            st.session_state.overwrite_lock_timestamp = None
                    else:
                        st.session_state.overwrite_trials_confirmed = True
                        st.warning("⚠️ Click again to confirm overwrite")
            with col2:
                if st.button("❌ Cancel Trials", help="Cancel trials overwrite"):
                    st.session_state.overwrite_trials_confirmed = False
                    st.rerun()
        
        # Visits overwrite
        if actual_visits_file:
            col1, col2 = st.sidebar.columns([3, 1])
            with col1:
                # Pre-validate file structure before showing button
                validation_result = None
                validation_messages = []
                if actual_visits_file:
                    try:
                        # Quick validation check (structure only, not full processing)
                        temp_df, temp_messages = validate_file_upload(actual_visits_file, 'visits')
                        validation_result = temp_df is not None
                        validation_messages = temp_messages
                    except Exception as e:
                        validation_result = False
                        validation_messages = [f"❌ File validation error: {e}"]
                
                # Check if any other overwrite operation is in progress
                if st.session_state.get('overwrite_in_progress', False):
                    st.button("🔄 Overwrite Visits Table", help="Another overwrite operation in progress", disabled=True)
                elif not actual_visits_file:
                    st.button("🔄 Overwrite Visits Table", help="No visits file uploaded", disabled=True)
                elif not validation_result:
                    st.button("🔄 Overwrite Visits Table", help="File validation failed", disabled=True)
                    # Show validation errors prominently
                    st.error("❌ **File validation failed!** Cannot overwrite visits table.")
                    for msg in validation_messages:
                        st.error(f"  • {msg}")
                elif st.button("🔄 Overwrite Visits Table", help="Replace only actual visits in database"):
                    if st.session_state.get('overwrite_visits_confirmed', False):
                        try:
                            # Set mutex to prevent other overwrite operations
                            st.session_state.overwrite_in_progress = True
                            st.session_state.overwrite_lock_timestamp = datetime.now()
                            
                            # File already validated, proceed with processing
                            actual_visits_df, validation_messages = validate_file_upload(actual_visits_file, 'visits')
                            
                            # Show validation summary (already validated, but show for transparency)
                            if validation_messages:
                                validation_summary = get_validation_summary(
                                    [msg for msg in validation_messages if msg.startswith('❌')],
                                    [msg for msg in validation_messages if msg.startswith('⚠️')]
                                )
                                st.markdown(validation_summary)
                            
                            # Check database availability before overwrite
                            if not st.session_state.get('database_available', False):
                                st.error("❌ Database not available for overwrite operation")
                                return
                            
                            # Use safe overwrite
                            if database.safe_overwrite_table('actual_visits', actual_visits_df, database.save_actual_visits_to_database):
                                st.success("✅ Visits table overwritten successfully!")
                                st.session_state.use_database = True
                                st.session_state.overwrite_visits_confirmed = False
                                # Force refresh of data
                                st.session_state.data_refresh_needed = True
                                st.cache_data.clear()  # Clear cache to get fresh data
                                st.session_state.overwrite_in_progress = False
                                st.session_state.overwrite_lock_timestamp = None
                                st.rerun()
                            else:
                                st.error("❌ Failed to overwrite visits table")
                                st.session_state.overwrite_visits_confirmed = False
                                st.session_state.overwrite_in_progress = False
                                st.session_state.overwrite_lock_timestamp = None
                        except Exception as e:
                            st.error(f"❌ Error processing visits file: {e}")
                            log_activity(f"Error processing visits file: {e}", level='error')
                            st.session_state.overwrite_visits_confirmed = False
                        finally:
                            # Always ensure mutex is released
                            st.session_state.overwrite_in_progress = False
                            st.session_state.overwrite_lock_timestamp = None
                    else:
                        st.session_state.overwrite_visits_confirmed = True
                        st.warning("⚠️ Click again to confirm overwrite")
            with col2:
                if st.button("❌ Cancel Visits", help="Cancel visits overwrite"):
                    st.session_state.overwrite_visits_confirmed = False
                    st.rerun()
    
    # Log file uploads
    if trials_file and 'last_trials_file' not in st.session_state:
        st.session_state.last_trials_file = trials_file.name
        log_activity(f"Uploaded trials file: {trials_file.name}", level='info')
    
    if patients_file and 'last_patients_file' not in st.session_state:
        st.session_state.last_patients_file = patients_file.name
        log_activity(f"Uploaded patients file: {patients_file.name}", level='info')
    
    if actual_visits_file and 'last_visits_file' not in st.session_state:
        st.session_state.last_visits_file = actual_visits_file.name
        log_activity(f"Uploaded actual visits file: {actual_visits_file.name}", level='info')
    
    st.session_state.patients_file = patients_file
    st.session_state.trials_file = trials_file
    st.session_state.actual_visits_file = actual_visits_file
    
    # Database Operations and Debug Section
    if st.session_state.get('database_available', False):
        st.sidebar.divider()
        with st.sidebar.expander("🔧 Database Operations & Debug", expanded=False):
            st.caption("Database management and debugging tools")
            
            # Test DB Connection
            if st.button("🧪 Test DB Connection", use_container_width=True):
                try:
                    if database.test_database_connection():
                        st.success("✅ Database connected and tables found")
                    else:
                        st.error(f"❌ Database issue: {st.session_state.get('database_status', 'Unknown')}")
                except Exception as e:
                    st.error(f"❌ Database test failed: {e}")
            
            st.divider()
            
            # Database Contents Check
            if st.button("🔍 Check All Database Tables", use_container_width=True):
                st.session_state.show_database_contents = True
                st.rerun()
            
            st.divider()
            
            # Refresh App Data
            if st.button("🔄 Refresh App Data", use_container_width=True):
                # Clear any cached data
                if 'patients_df' in st.session_state:
                    del st.session_state['patients_df']
                if 'trials_df' in st.session_state:
                    del st.session_state['trials_df']
                if 'actual_visits_df' in st.session_state:
                    del st.session_state['actual_visits_df']
                
                st.session_state.data_refresh_needed = True
                st.cache_data.clear()  # Clear cache to get fresh data
                st.success("Data refresh triggered!")
                st.rerun()
            
            st.divider()
            
            # Debug Toggle
            st.session_state.show_debug_info = st.checkbox("Show Debug Info", value=st.session_state.get('show_debug_info', False))
            
            st.divider()
            
            # Database Backup
            if st.button("📦 Download DB Backup", use_container_width=True):
                backup_zip = database.create_backup_zip()
                if backup_zip:
                    st.download_button(
                        "💾 Download Database Backup (ZIP)",
                        data=backup_zip.getvalue(),
                        file_name=f"database_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                        mime="application/zip",
                        use_container_width=True
                    )
                    log_activity("Database backup created successfully", level='success')
                else:
                    log_activity("Failed to create database backup", level='error')
            
            st.divider()
            
            # Save to Database buttons (when not using database data)
            st.caption("Save uploaded data to database:")
            if st.button("💾 Save Patients to DB", use_container_width=True):
                # This will be handled in the main area when files are uploaded
                st.info("Upload files first to save to database")
            
            if st.button("💾 Save Trials to DB", use_container_width=True):
                st.info("Upload files first to save to database")
            
            if st.button("💾 Save Visits to DB", use_container_width=True):
                st.info("Upload files first to save to database")
    
    # Display activity log at bottom of sidebar
    st.sidebar.divider()
    display_activity_log_sidebar()
    
    return patients_file, trials_file, actual_visits_file

def display_action_buttons():
    """Enhanced action buttons with study events"""
    col1, col2, col3 = st.columns([1, 1, 1])
    
    with col1:
        if st.button("Add New Patient", use_container_width=True):
            st.session_state.show_patient_form = True
    
    with col2:
        if st.button("Record Patient Visit", use_container_width=True):
            st.session_state.show_visit_form = True
    
    with col3:
        if st.button("Manage Study Events", use_container_width=True):
            st.session_state.show_study_event_form = True

def _cleanup_stale_mutex_locks():
    """Clean up stale mutex locks from overwrite operations that are >5 minutes old"""
    try:
        current_time = datetime.now()
        
        # Check if overwrite operation is in progress
        if st.session_state.get('overwrite_in_progress', False):
            # Get the timestamp when the lock was acquired
            lock_timestamp = st.session_state.get('overwrite_lock_timestamp', None)
            
            if lock_timestamp is None:
                # No timestamp - assume stale and reset
                log_activity("🔄 Resetting stale overwrite lock (no timestamp found)", level='warning')
                st.session_state.overwrite_in_progress = False
                st.session_state.overwrite_lock_timestamp = None
            else:
                # Calculate time difference
                time_diff = current_time - lock_timestamp
                if time_diff.total_seconds() > 300:  # 5 minutes = 300 seconds
                    # Lock is stale - reset it
                    log_activity(f"🔄 Resetting stale overwrite lock (age: {time_diff.total_seconds():.0f} seconds)", level='warning')
                    st.session_state.overwrite_in_progress = False
                    st.session_state.overwrite_lock_timestamp = None
                else:
                    # Lock is still valid
                    if st.session_state.get('show_debug_info', False):
                        log_activity(f"🔒 Overwrite lock is active (age: {time_diff.total_seconds():.0f} seconds)", level='info')
    except Exception as e:
        # If cleanup fails, log it but don't crash the app
        log_activity(f"⚠️ Error during mutex cleanup: {e}", level='warning')
        # Reset the lock to be safe
        st.session_state.overwrite_in_progress = False
        st.session_state.overwrite_lock_timestamp = None

def main():
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    st.title(APP_TITLE)
    st.caption(f"{APP_VERSION} | {APP_SUBTITLE}")

    initialize_session_state()
    
    # Cleanup stale mutex locks (overwrite operations >5 minutes old)
    _cleanup_stale_mutex_locks()
    
    # NEW - Check database availability
    if 'database_available' not in st.session_state:
        st.session_state.database_available = database.test_database_connection()
    
    # Database Contents Display (if requested)
    if st.session_state.get('show_database_contents', False):
        st.markdown("---")
        st.subheader("📊 Database Contents")
        
        try:
            patients_db = database.fetch_all_patients()
            trials_db = database.fetch_all_trial_schedules()
            visits_db = database.fetch_all_actual_visits()
            
            # Show metrics in a row
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Patients", len(patients_db) if patients_db is not None else 0)
            
            with col2:
                st.metric("Trials", len(trials_db) if trials_db is not None else 0)
            
            with col3:
                st.metric("Actual Visits", len(visits_db) if visits_db is not None else 0)
            
            # Show full scrollable tables
            if patients_db is not None and not patients_db.empty:
                st.subheader("👥 Patients Table")
                st.dataframe(patients_db, use_container_width=True, height=300)
            else:
                st.info("No patients found")
            
            if trials_db is not None and not trials_db.empty:
                st.subheader("🧪 Trials Table")
                st.dataframe(trials_db, use_container_width=True, height=300)
            else:
                st.info("No trials found")
            
            if visits_db is not None and not visits_db.empty:
                st.subheader("📅 Actual Visits Table")
                st.dataframe(visits_db, use_container_width=True, height=300)
            else:
                st.info("No actual visits found")
            
            # Close button
            if st.button("❌ Close Database View", use_container_width=True):
                st.session_state.show_database_contents = False
                st.rerun()
                
        except Exception as e:
            st.error(f"Error fetching database contents: {e}")
        
        st.markdown("---")
        
    patients_file, trials_file, actual_visits_file = setup_file_uploaders()

    # Always show action buttons (database-first)
    display_action_buttons()

    # Load data - prioritize files over database
    try:
        # Check if files are uploaded
        patients_file = st.session_state.get('patients_file')
        trials_file = st.session_state.get('trials_file')
        actual_visits_file = st.session_state.get('actual_visits_file')
        
        if patients_file and trials_file:
            # Load from uploaded files
            log_activity("Loading data from uploaded files...", level='info')
            
            # Validate and load patients file
            patients_df, patient_messages = validate_file_upload(patients_file, 'patients')
            if patients_df is None:
                st.error("❌ Patients file validation failed!")
                for msg in patient_messages:
                    st.error(f"  • {msg}")
                st.stop()
            
            # Validate and load trials file
            trials_df, trial_messages = validate_file_upload(trials_file, 'trials')
            if trials_df is None:
                st.error("❌ Trials file validation failed!")
                for msg in trial_messages:
                    st.error(f"  • {msg}")
                st.stop()
            
            # Load actual visits file (optional)
            actual_visits_df = pd.DataFrame()  # Default to empty DataFrame
            if actual_visits_file:
                actual_visits_df, visit_messages = validate_file_upload(actual_visits_file, 'visits')
                if actual_visits_df is None:
                    st.warning("⚠️ Actual visits file validation failed - continuing without actual visits")
                    actual_visits_df = pd.DataFrame()
                else:
                    log_activity(f"Loaded {len(actual_visits_df)} actual visits from file", level='info')
            
            # Log what we loaded from files
            log_activity(f"Loaded {len(patients_df)} patients, {len(trials_df)} trials from files", level='info')
            
        else:
            # Load from database
            if st.session_state.get('data_refresh_needed', False):
                log_activity("Refreshing data from database...", level='info')
                st.session_state.data_refresh_needed = False
            else:
                log_activity("Loading data from database...", level='info')
            
            patients_df = database.fetch_all_patients()
            trials_df = database.fetch_all_trial_schedules()
            actual_visits_df = database.fetch_all_actual_visits()
            
            if patients_df is None or trials_df is None:
                st.error("Failed to load from database. Please check database connection.")
                st.stop()
            
            # Log what we loaded from database
            log_activity(f"Loaded {len(patients_df)} patients, {len(trials_df)} trials from database", level='info')
        
        # Debug: Show what we're actually working with
        if st.session_state.get('show_debug_info', False):
            st.write("**Data Summary:**")
            st.write(f"Patients: {len(patients_df)} | Trials: {len(trials_df)} | Actual Visits: {len(actual_visits_df) if actual_visits_df is not None else 0}")
            
            if 'Payment' in trials_df.columns:
                payment_count = (trials_df['Payment'] > 0).sum()
                st.write(f"Trials with payments: {payment_count}/{len(trials_df)}")
            else:
                st.write("❌ No Payment column in trials")
            
            if not patients_df.empty and 'StartDate' in patients_df.columns:
                st.write(f"Patient date range: {patients_df['StartDate'].min().strftime('%Y-%m-%d')} to {patients_df['StartDate'].max().strftime('%Y-%m-%d')}")
                st.write(f"Studies: {', '.join(patients_df['Study'].unique())}")
        
    except Exception as e:
        st.error(f"Error loading data: {e}")
        log_activity(f"Error loading data: {e}", level='error')
        st.stop()
    
    # Handle modal forms
    handle_patient_modal()
    handle_visit_modal()
    handle_study_event_modal()
    show_download_sections()

    try:
        visits_df, calendar_df, stats, messages, site_column_mapping, unique_visit_sites = build_calendar(
            patients_df, trials_df, actual_visits_df
        )
        
        screen_failures = extract_screen_failures(actual_visits_df)

        display_processing_messages(messages)
        
        # 1. CALENDAR (moved to top)
        display_calendar(calendar_df, site_column_mapping, unique_visit_sites)
        
        # 2. LEGEND (right after calendar)
        show_legend(actual_visits_df)
        
        # 3. SITE SUMMARY (after legend)
        site_summary_df = extract_site_summary(patients_df, screen_failures)
        if not site_summary_df.empty:
            display_site_statistics(site_summary_df)
        
        display_monthly_income_tables(visits_df)
        
        financial_df = prepare_financial_data(visits_df)
        if not financial_df.empty:
            display_quarterly_profit_sharing_tables(financial_df, patients_df)

        display_income_realization_analysis(visits_df, trials_df, patients_df)

        display_site_wise_statistics(visits_df, patients_df, unique_visit_sites, screen_failures)

        display_download_buttons(calendar_df, site_column_mapping, unique_visit_sites, patients_df, actual_visits_df)

        # Show error log if any issues occurred
        display_error_log_section()

    except Exception as e:
        st.error(f"Error processing files: {e}")
        st.exception(e)

# Streamlit apps don't need a main() function - code executes at module level