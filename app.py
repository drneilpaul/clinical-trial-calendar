import streamlit as st
import pandas as pd
from datetime import datetime
from helpers import (
    load_file, normalize_columns, parse_dates_column, 
    standardize_visit_columns, safe_string_conversion_series, 
    load_file_with_defaults, init_error_system, display_error_log_section,
    log_activity, display_activity_log_sidebar, trigger_data_refresh
)
from file_validation import validate_file_upload, get_validation_summary, FileValidationError
import database as db
from processing_calendar import build_calendar, clear_build_calendar_cache
from database import clear_database_cache
from display_components import (
    show_legend, display_calendar, display_site_statistics,
    display_download_buttons, display_monthly_income_tables,
    display_quarterly_profit_sharing_tables, display_income_realization_analysis,
    display_site_income_by_fy, display_study_income_summary,
    render_calendar_start_selector, apply_calendar_start_filter
)
from modal_forms import handle_patient_modal, handle_visit_modal, handle_study_event_modal, show_download_sections
try:
    from modal_forms import handle_switch_patient_modal
    SWITCH_PATIENT_AVAILABLE = True
except ImportError as e:
    print(f"Switch patient modal not available: {e}")
    SWITCH_PATIENT_AVAILABLE = False
from data_analysis import (
    extract_screen_failures, extract_withdrawals, display_site_wise_statistics, display_processing_messages
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

def check_and_refresh_data():
    """Check if data refresh is needed and reload from database"""
    if st.session_state.get('data_refresh_needed', False):
        try:
            if st.session_state.get('use_database', False):
                st.session_state.patients_df = db.fetch_all_patients()
                st.session_state.trials_df = db.fetch_all_trial_schedules()
                st.session_state.actual_visits_df = db.fetch_all_actual_visits()

                log_activity("Data refreshed from database", level='success')

            clear_build_calendar_cache()
            clear_database_cache()
            st.session_state.calendar_cache_buster = st.session_state.get('calendar_cache_buster', 0) + 1
            st.session_state.data_refresh_needed = False
        except Exception as e:
            st.error(f"Error refreshing data: {e}")
            log_activity(f"Error refreshing data: {e}", level='error')

def setup_file_uploaders():
    """Setup file uploaders and store in session state"""
    
    st.sidebar.header("Data Source")
    
    # Database toggle
    if st.session_state.get('database_available', False):
        st.sidebar.success("Database Connected")
        use_database = st.sidebar.checkbox(
            "Load from Database", 
            value=True,
            help="Load existing data from database instead of files"
        )
        st.session_state.use_database = use_database
    else:
        st.session_state.use_database = False
        if st.session_state.get('database_status'):
            st.sidebar.info(f"Database: {st.session_state.database_status}")
    
    st.sidebar.divider()
    
    # Authentication - Login/Logout widget
    if st.session_state.get('auth_level') != 'admin':
        with st.sidebar.expander("🔐 Admin Login", expanded=False):
            st.caption("Login to add/edit data and view financial reports")
            password = st.text_input("Password", type="password", key="admin_password_input")
            if st.button("Login", width="stretch"):
                if password == st.secrets.get("admin_password", ""):
                    st.session_state.auth_level = 'admin'
                    log_activity("Admin user logged in", level='success')
                    st.success("✅ Logged in as admin")
                    st.rerun()
                else:
                    st.error("❌ Incorrect password")
                    log_activity("Failed login attempt", level='warning')
    else:
        st.sidebar.success("✅ Admin Mode")
        if st.sidebar.button("🚪 Logout", width="stretch"):
            st.session_state.auth_level = 'public'
            log_activity("Admin user logged out", level='info')
            st.rerun()
    
    st.sidebar.divider()
    
    # File uploaders - Admin only
    # Initialize to None first
    trials_file = None
    patients_file = None
    actual_visits_file = None
    
    if st.session_state.get('database_available', False):
        if st.session_state.get('auth_level') == 'admin':
            with st.sidebar.expander("📁 File Upload Options", expanded=True):
                st.caption("Use these if you want to upload new files instead of using database")
                
                trials_file = st.file_uploader("Upload Trials File", type=['csv', 'xls', 'xlsx'])
                patients_file = st.file_uploader("Upload Patients File", type=['csv', 'xls', 'xlsx'])
                actual_visits_file = st.file_uploader("Upload Actual Visits File (Optional)", type=['csv', 'xls', 'xlsx'])
            
            # Selective overwrite buttons
            if patients_file or trials_file or actual_visits_file:
                st.divider()
                st.caption("🔄 **Selective Database Overwrite** - Replace specific tables")
                
                # Patients overwrite
                if patients_file:
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        if st.session_state.get('overwrite_in_progress', False):
                            st.button("🔄 Overwrite Patients Table", help="Another overwrite operation in progress", disabled=True)
                        elif st.button("🔄 Overwrite Patients Table", help="Replace only patients in database"):
                            if st.session_state.get('overwrite_patients_confirmed', False):
                                try:
                                    st.session_state.overwrite_in_progress = True
                                    
                                    patients_df, validation_messages = validate_file_upload(patients_file, 'patients')
                                    
                                    if patients_df is None:
                                        st.error("❌ File validation failed!")
                                        for msg in validation_messages:
                                            st.error(f"  • {msg}")
                                        st.session_state.overwrite_patients_confirmed = False
                                        st.session_state.overwrite_in_progress = False
                                        st.rerun()
                                        return
                                    
                                    validation_summary = get_validation_summary(
                                        [msg for msg in validation_messages if msg.startswith('❌')],
                                        [msg for msg in validation_messages if msg.startswith('⚠️')]
                                    )
                                    st.markdown(validation_summary)
                                    
                                    if db.safe_overwrite_table('patients', patients_df, db.save_patients_to_database):
                                        st.success("✅ Patients table overwritten successfully!")
                                        
                                        # === ADD THIS ===
                                        # Run validation after overwrite
                                        from database_validator import run_startup_validation
                                        validation_results = run_startup_validation(
                                            patients_df, 
                                            db.fetch_all_trial_schedules(), 
                                            db.fetch_all_actual_visits()
                                        )
                                        st.session_state.validation_results = validation_results
                                        # === END ADDITION ===
                                        
                                        st.session_state.use_database = True
                                        st.session_state.overwrite_patients_confirmed = False
                                        trigger_data_refresh()
                                        st.session_state.overwrite_in_progress = False
                                    else:
                                        st.error("❌ Failed to overwrite patients table")
                                        st.session_state.overwrite_patients_confirmed = False
                                        st.session_state.overwrite_in_progress = False
                                except Exception as e:
                                    st.error(f"❌ Error processing patients file: {e}")
                                    log_activity(f"Error processing patients file: {e}", level='error')
                                    st.session_state.overwrite_patients_confirmed = False
                                    st.session_state.overwrite_in_progress = False
                            else:
                                st.session_state.overwrite_patients_confirmed = True
                                st.warning("⚠️ Click again to confirm overwrite")
                    with col2:
                        if st.button("❌ Cancel", help="Cancel patients overwrite", key="cancel_patients"):
                            st.session_state.overwrite_patients_confirmed = False
                            st.rerun()
                
                # Trials overwrite
                if trials_file:
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        if st.session_state.get('overwrite_in_progress', False):
                            st.button("🔄 Overwrite Trials Table", help="Another overwrite operation in progress", disabled=True)
                        elif st.button("🔄 Overwrite Trials Table", help="Replace only trial schedules in database"):
                            if st.session_state.get('overwrite_trials_confirmed', False):
                                try:
                                    st.session_state.overwrite_in_progress = True
                                    
                                    trials_df, validation_messages = validate_file_upload(trials_file, 'trials')
                                    
                                    if trials_df is None:
                                        st.error("❌ File validation failed!")
                                        for msg in validation_messages:
                                            st.error(f"  • {msg}")
                                        st.session_state.overwrite_trials_confirmed = False
                                        st.session_state.overwrite_in_progress = False
                                        st.rerun()
                                        return
                                    
                                    validation_summary = get_validation_summary(
                                        [msg for msg in validation_messages if msg.startswith('❌')],
                                        [msg for msg in validation_messages if msg.startswith('⚠️')]
                                    )
                                    st.markdown(validation_summary)
                                    
                                    if db.safe_overwrite_table('trial_schedules', trials_df, db.save_trial_schedules_to_database):
                                        st.success("✅ Trials table overwritten successfully!")
                                        
                                        # === ADD THIS ===
                                        # Run validation after overwrite
                                        from database_validator import run_startup_validation
                                        validation_results = run_startup_validation(
                                            db.fetch_all_patients(), 
                                            trials_df, 
                                            db.fetch_all_actual_visits()
                                        )
                                        st.session_state.validation_results = validation_results
                                        # === END ADDITION ===
                                        
                                        st.session_state.use_database = True
                                        st.session_state.overwrite_trials_confirmed = False
                                        trigger_data_refresh()
                                        st.session_state.overwrite_in_progress = False
                                    else:
                                        st.error("❌ Failed to overwrite trials table")
                                        st.session_state.overwrite_trials_confirmed = False
                                        st.session_state.overwrite_in_progress = False
                                except Exception as e:
                                    st.error(f"❌ Error processing trials file: {e}")
                                    log_activity(f"Error processing trials file: {e}", level='error')
                                    st.session_state.overwrite_trials_confirmed = False
                                    st.session_state.overwrite_in_progress = False
                            else:
                                st.session_state.overwrite_trials_confirmed = True
                                st.warning("⚠️ Click again to confirm overwrite")
                    with col2:
                        if st.button("❌ Cancel", help="Cancel trials overwrite", key="cancel_trials"):
                            st.session_state.overwrite_trials_confirmed = False
                            st.rerun()
                
                # Visits overwrite
                if actual_visits_file:
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        if st.session_state.get('overwrite_in_progress', False):
                            st.button("🔄 Overwrite Visits Table", help="Another overwrite operation in progress", disabled=True)
                        elif st.button("🔄 Overwrite Visits Table", help="Replace only actual visits in database"):
                            if st.session_state.get('overwrite_visits_confirmed', False):
                                try:
                                    st.session_state.overwrite_in_progress = True
                                    
                                    actual_visits_df, validation_messages = validate_file_upload(actual_visits_file, 'visits')
                                    
                                    if actual_visits_df is None:
                                        st.error("❌ File validation failed!")
                                        for msg in validation_messages:
                                            st.error(f"  • {msg}")
                                        st.session_state.overwrite_visits_confirmed = False
                                        st.session_state.overwrite_in_progress = False
                                        st.rerun()
                                        return
                                    
                                    validation_summary = get_validation_summary(
                                        [msg for msg in validation_messages if msg.startswith('❌')],
                                        [msg for msg in validation_messages if msg.startswith('⚠️')]
                                    )
                                    st.markdown(validation_summary)
                                    
                                    if db.safe_overwrite_table('actual_visits', actual_visits_df, db.save_actual_visits_to_database):
                                        st.success("✅ Visits table overwritten successfully!")
                                        
                                        # === ADD THIS ===
                                        # Run validation after overwrite
                                        from database_validator import run_startup_validation
                                        validation_results = run_startup_validation(
                                            db.fetch_all_patients(), 
                                            db.fetch_all_trial_schedules(), 
                                            actual_visits_df
                                        )
                                        st.session_state.validation_results = validation_results
                                        # === END ADDITION ===
                                        
                                        st.session_state.use_database = True
                                        st.session_state.overwrite_visits_confirmed = False
                                        trigger_data_refresh()
                                        st.session_state.overwrite_in_progress = False
                                    else:
                                        st.error("❌ Failed to overwrite visits table")
                                        st.session_state.overwrite_visits_confirmed = False
                                        st.session_state.overwrite_in_progress = False
                                except Exception as e:
                                    st.error(f"❌ Error processing visits file: {e}")
                                    log_activity(f"Error processing visits file: {e}", level='error')
                                    st.session_state.overwrite_visits_confirmed = False
                                    st.session_state.overwrite_in_progress = False
                            else:
                                st.session_state.overwrite_visits_confirmed = True
                                st.warning("⚠️ Click again to confirm overwrite")
                    with col2:
                        if st.button("❌ Cancel", help="Cancel visits overwrite", key="cancel_visits"):
                            st.session_state.overwrite_visits_confirmed = False
                            st.rerun()
        else:
            st.sidebar.info("🔒 Admin login required to upload files")
    else:
        if st.session_state.get('auth_level') == 'admin':
            st.sidebar.caption("Upload your data files to get started")
            
            trials_file = st.sidebar.file_uploader("Upload Trials File", type=['csv', 'xls', 'xlsx'])
            patients_file = st.sidebar.file_uploader("Upload Patients File", type=['csv', 'xls', 'xlsx'])
            actual_visits_file = st.sidebar.file_uploader("Upload Actual Visits File (Optional)", type=['csv', 'xls', 'xlsx'])
        else:
            st.sidebar.info("🔒 Admin login required to upload files")
    
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
    
    # Database Operations - Admin only
    if st.session_state.get('database_available', False):
        st.sidebar.divider()
        if st.session_state.get('auth_level') == 'admin':
            with st.sidebar.expander("🔧 Database Operations & Debug", expanded=False):
                st.caption("Database management and debugging tools")
                
                if st.button("🧪 Test DB Connection", width="stretch"):
                    try:
                        if db.test_database_connection():
                            st.success("✅ Database connected and tables found")
                        else:
                            st.error(f"❌ Database issue: {st.session_state.get('database_status', 'Unknown')}")
                    except Exception as e:
                        st.error(f"❌ Database test failed: {e}")
                
                st.divider()
                
                if st.button("🔍 Check All Database Tables", width="stretch"):
                    st.session_state.show_database_contents = True
                    st.rerun()
                
                st.divider()
                
                if st.button("🔄 Refresh App Data", width="stretch"):
                    # Clear all cached data
                    if 'patients_df' in st.session_state:
                        del st.session_state['patients_df']
                    if 'trials_df' in st.session_state:
                        del st.session_state['trials_df']
                    if 'actual_visits_df' in st.session_state:
                        del st.session_state['actual_visits_df']
                    
                    # Clear validation results to force re-run
                    if 'validation_results' in st.session_state:
                        del st.session_state['validation_results']
                    if 'validation_run' in st.session_state:
                        del st.session_state['validation_run']
                    
                    st.session_state.data_refresh_needed = True
                    log_activity("🔄 Manual data refresh triggered - clearing all caches", level='info')
                    st.success("✅ Data refresh triggered! Reloading from database...")
                    st.rerun()
                
                st.divider()
                
                st.session_state.show_debug_info = st.checkbox("Show Debug Info", value=st.session_state.get('show_debug_info', False))
                
                st.divider()
                
                if st.button("📦 Download DB Backup", width="stretch"):
                    backup_zip = db.create_backup_zip()
                    if backup_zip:
                        st.download_button(
                            "💾 Download Database Backup (ZIP)",
                            data=backup_zip.getvalue(),
                            file_name=f"database_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                            mime="application/zip",
                            width="stretch"
                        )
                        log_activity("Database backup created successfully", level='success')
                    else:
                        log_activity("Failed to create database backup", level='error')
                
                st.divider()
                
                if SWITCH_PATIENT_AVAILABLE and st.button("🔄 Switch Patient Study", width="stretch"):
                    st.session_state.show_switch_patient_form = True
                    st.rerun()
        else:
            st.sidebar.info("🔒 Admin login required for database operations")
    
    st.sidebar.divider()
    
    # Add button to show validation details in sidebar
    if st.session_state.get('validation_results') and not st.session_state.get('show_validation_details', False):
        if st.sidebar.button("🔍 Show Validation Details"):
            st.session_state.show_validation_details = True
            st.rerun()
    
    display_activity_log_sidebar()
    
    return patients_file, trials_file, actual_visits_file

def display_action_buttons():
    """Enhanced action buttons with authentication check"""
    if st.session_state.get('auth_level') != 'admin':
        st.info("🔒 Login as admin to add/edit patients, visits, and study events")
        return
    
    col1, col2, col3 = st.columns([1, 1, 1])
    
    with col1:
        if st.button("➕ Add New Patient", width="stretch",
                     help="Add a new patient to the calendar"):
            st.session_state.show_patient_form = True
    
    with col2:
        if st.button("📝 Record Patient Visit", width="stretch",
                     help="Record visits for specific patients (Screening, Randomisation, V1-V21, V1.1, Unscheduled)"):
            st.session_state.show_visit_form = True
    
    with col3:
        if st.button("📅 Record Site Event", width="stretch",
                     help="Record site-wide events (SIV, Monitor, Closeout) - not patient-specific"):
            st.session_state.show_study_event_form = True

def main():
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    st.title(APP_TITLE)
    st.caption(f"{APP_VERSION} | {APP_SUBTITLE}")

    initialize_session_state()
    
    # Check database availability
    if 'database_available' not in st.session_state:
        st.session_state.database_available = db.test_database_connection()
    
    # Check and refresh data if needed
    check_and_refresh_data()
    
    # === ADD THIS SECTION ===
    # Run startup validation if using database
    if st.session_state.get('use_database', False) and st.session_state.get('database_available', False):
        # Only run validation once per session or after data refresh
        if st.session_state.get('data_refresh_needed', False) or 'validation_run' not in st.session_state:
            try:
                from database_validator import run_startup_validation
                
                # Load data for validation
                patients_df = db.fetch_all_patients()
                trials_df = db.fetch_all_trial_schedules()
                actual_visits_df = db.fetch_all_actual_visits()
                
                # Run validation
                validation_results = run_startup_validation(patients_df, trials_df, actual_visits_df)
                
                # Store results in session state
                st.session_state.validation_results = validation_results
                st.session_state.validation_run = True
                
                # Display validation summary in UI
                if validation_results['error_count'] > 0:
                    st.error(
                        f"⚠️ **Database Validation Found {validation_results['error_count']} Error(s)**\n\n"
                        f"Check the Activity Log in the sidebar for details."
                    )
                elif validation_results['warning_count'] > 0:
                    st.warning(
                        f"⚠️ **Database Validation Found {validation_results['warning_count']} Warning(s)**\n\n"
                        f"Check the Activity Log in the sidebar for details."
                    )
                else:
                    st.success("✅ Database validation passed - all data looks good!")
                    
            except Exception as e:
                st.error(f"Error during database validation: {e}")
                log_activity(f"Validation error: {e}", level='error')
    # === END ADDITION ===
    
    # Database Contents Display
    if st.session_state.get('show_database_contents', False):
        st.markdown("---")
        st.subheader("📊 Database Contents")
        
        try:
            patients_db = db.fetch_all_patients()
            trials_db = db.fetch_all_trial_schedules()
            visits_db = db.fetch_all_actual_visits()
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Patients", len(patients_db) if patients_db is not None else 0)
            
            with col2:
                st.metric("Trials", len(trials_db) if trials_db is not None else 0)
            
            with col3:
                st.metric("Actual Visits", len(visits_db) if visits_db is not None else 0)
            
            if patients_db is not None and not patients_db.empty:
                st.subheader("👥 Patients Table")
                st.dataframe(patients_db, width="stretch", height=300)
            else:
                st.info("No patients found")
            
            if trials_db is not None and not trials_db.empty:
                st.subheader("🧪 Trials Table")
                st.dataframe(trials_db, width="stretch", height=300)
            else:
                st.info("No trials found")
            
            if visits_db is not None and not visits_db.empty:
                st.subheader("📅 Actual Visits Table")
                st.dataframe(visits_db, width="stretch", height=300)
            else:
                st.info("No actual visits found")
            
            if st.button("❌ Close Database View", width="stretch"):
                st.session_state.show_database_contents = False
                trigger_data_refresh()
                st.rerun()
                
        except Exception as e:
            st.error(f"Error fetching database contents: {e}")
        
        st.markdown("---")
    
    # Validation Results Display (optional - shows detailed results in UI)
    if st.session_state.get('validation_results') and st.session_state.get('show_validation_details', False):
        st.markdown("---")
        st.subheader("🔍 Database Validation Results")
        
        results = st.session_state.validation_results
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Errors", results['error_count'], 
                     delta="Critical" if results['error_count'] > 0 else None,
                     delta_color="inverse")
        with col2:
            st.metric("Warnings", results['warning_count'],
                     delta="Review" if results['warning_count'] > 0 else None,
                     delta_color="off")
        with col3:
            st.metric("Info Checks", len(results['info']))
        
        if results['errors']:
            with st.expander("❌ Errors (Must Fix)", expanded=True):
                for error in results['errors']:
                    st.error(error)
        
        if results['warnings']:
            with st.expander("⚠️ Warnings (Should Review)", expanded=False):
                for warning in results['warnings']:
                    st.warning(warning)
        
        if results['info']:
            with st.expander("✅ Info & Success Messages", expanded=False):
                for info in results['info']:
                    st.info(info)
        
        if st.button("❌ Close Validation Details"):
            st.session_state.show_validation_details = False
            st.rerun()
        
        st.markdown("---")
    
    patients_file, trials_file, actual_visits_file = setup_file_uploaders()

    # Show action buttons if we have either database mode OR file uploads
    use_database = st.session_state.get('use_database', False)
    has_files = patients_file and trials_file
    
    if use_database or has_files:
        display_action_buttons()

        # Load data based on mode
        if use_database:
            if st.session_state.get('data_refresh_needed', False):
                log_activity("Refreshing data from database...", level='info')
                st.session_state.data_refresh_needed = False
            else:
                log_activity("Loading data from database...", level='info')
            
            patients_df = db.fetch_all_patients()
            trials_df = db.fetch_all_trial_schedules()
            actual_visits_df = db.fetch_all_actual_visits()
            
            if patients_df is None or trials_df is None:
                st.error("Failed to load from database. Please upload files instead.")
                st.session_state.use_database = False
                st.stop()
            
            log_activity(f"Loaded {len(patients_df)} patients, {len(trials_df)} trials from database", level='info')
            
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
        else:
            # File processing
            try:
                init_error_system()
                
                patients_df, patients_validation = validate_file_upload(patients_file, 'patients')
                if patients_df is None:
                    st.error("❌ Patients file validation failed!")
                    for msg in patients_validation:
                        st.error(f"  • {msg}")
                    st.stop()
                
                # Block processing if validation found errors
                if any(msg.startswith('❌') for msg in patients_validation):
                    st.error("❌ Patients file has validation errors - processing stopped")
                    st.stop()
                
                trials_df, trials_validation = validate_file_upload(trials_file, 'trials')
                if trials_df is None:
                    st.error("❌ Trials file validation failed!")
                    for msg in trials_validation:
                        st.error(f"  • {msg}")
                    st.stop()
                
                # Block processing if validation found errors
                if any(msg.startswith('❌') for msg in trials_validation):
                    st.error("❌ Trials file has validation errors - processing stopped")
                    st.stop()
                
                actual_visits_df = None
                if actual_visits_file:
                    actual_visits_df, visits_validation = validate_file_upload(actual_visits_file, 'visits')
                    if actual_visits_df is None:
                        st.error("❌ Visits file validation failed!")
                        for msg in visits_validation:
                            st.error(f"  • {msg}")
                        st.stop()
                    
                    # Block processing if validation found errors
                    if any(msg.startswith('❌') for msg in visits_validation):
                        st.error("❌ Visits file has validation errors - processing stopped")
                        st.stop()
                
                st.markdown("**📋 File Validation Results:**")
                
                patients_summary = get_validation_summary(
                    [msg for msg in patients_validation if msg.startswith('❌')],
                    [msg for msg in patients_validation if msg.startswith('⚠️')]
                )
                st.markdown(f"**Patients:** {patients_summary}")
                
                trials_summary = get_validation_summary(
                    [msg for msg in trials_validation if msg.startswith('❌')],
                    [msg for msg in trials_validation if msg.startswith('⚠️')]
                )
                st.markdown(f"**Trials:** {trials_summary}")
                
                if actual_visits_df is not None:
                    visits_summary = get_validation_summary(
                        [msg for msg in visits_validation if msg.startswith('❌')],
                        [msg for msg in visits_validation if msg.startswith('⚠️')]
                    )
                    st.markdown(f"**Visits:** {visits_summary}")
                
                missing_studies = set(patients_df["Study"]) - set(trials_df["Study"])
                if missing_studies:
                    st.error(f"❌ Missing Study Definitions: {missing_studies}")
                    st.stop()

                for study in patients_df["Study"].unique():
                    study_visits = trials_df[trials_df["Study"] == study]
                    day_1_visits = study_visits[study_visits["Day"] == 1]
                    
                    if len(day_1_visits) == 0:
                        st.error(f"❌ Study {study} has no Day 1 visit defined. Day 1 is required as baseline.")
                        st.stop()
                    elif len(day_1_visits) > 1:
                        visit_names = day_1_visits["VisitName"].tolist()
                        st.error(f"❌ Study {study} has multiple Day 1 visits: {visit_names}. Only one Day 1 visit allowed.")
                        st.stop()
                
            except Exception as e:
                st.error(f"Error processing files: {str(e)}")
                st.stop()
        
        # Handle modals
        handle_patient_modal()
        handle_visit_modal()
        handle_study_event_modal()
        if SWITCH_PATIENT_AVAILABLE:
            handle_switch_patient_modal()
        show_download_sections()

        try:
            hide_inactive = st.session_state.get('hide_inactive_patients', False)
            cache_buster = st.session_state.get('calendar_cache_buster', 0)
            visits_df, calendar_df, stats, messages, site_column_mapping, unique_visit_sites, patients_df = build_calendar(
                patients_df=patients_df, 
                trials_df=trials_df, 
                actual_visits_df=actual_visits_df, 
                cache_buster=cache_buster, 
                hide_inactive=hide_inactive
            )
            
            screen_failures = extract_screen_failures(actual_visits_df)
            withdrawals = extract_withdrawals(actual_visits_df)

            display_processing_messages(messages)
            
            # Calendar range selector
            calendar_filter_option = render_calendar_start_selector()
            calendar_start_date = calendar_filter_option.get("start")
            calendar_df_filtered = apply_calendar_start_filter(calendar_df, calendar_start_date)
            visits_df_filtered = apply_calendar_start_filter(visits_df, calendar_start_date)

            available_sites = sorted([site for site in unique_visit_sites])
            available_studies = []
            if 'Study' in visits_df_filtered.columns:
                available_studies = sorted(visits_df_filtered['Study'].dropna().astype(str).unique().tolist())

            # Build combined site/study selector
            site_field = None
            for candidate in ['SiteofVisit', 'VisitSite', 'Site', 'OriginSite', 'Practice']:
                if candidate in visits_df_filtered.columns:
                    site_field = candidate
                    break

            site_label_fallback = 'Unknown Site'
            combo_options = {}
            if available_studies:
                if site_field is None:
                    temp_df = visits_df_filtered[['Study']].dropna(subset=['Study']).copy()
                    temp_df['__site'] = site_label_fallback
                    site_field = '__site'
                else:
                    temp_df = visits_df_filtered[[site_field, 'Study']].dropna(subset=['Study']).copy()
                temp_df[site_field] = temp_df[site_field].astype(str).str.strip().replace({'nan': site_label_fallback})
                temp_df['Study'] = temp_df['Study'].astype(str).str.strip()
                temp_df = temp_df.drop_duplicates()

                signature = tuple(sorted((row[site_field], row['Study']) for _, row in temp_df.iterrows()))
                cached_signature = st.session_state.get('calendar_combo_signature')
                if signature != cached_signature:
                    combo_options = {}
                    for _, row in temp_df.iterrows():
                        site_value = row[site_field] if site_field in row else site_label_fallback
                        label = f"{site_value} • {row['Study']}"
                        combo_options[label] = {
                            'site': site_value,
                            'study': row['Study']
                        }
                    st.session_state['calendar_combo_options'] = combo_options
                    st.session_state['calendar_combo_signature'] = signature
                else:
                    cached_options = st.session_state.get('calendar_combo_options')
                    if cached_options is None:
                        combo_options = {}
                        for _, row in temp_df.iterrows():
                            site_value = row[site_field] if site_field in row else site_label_fallback
                            label = f"{site_value} • {row['Study']}"
                            combo_options[label] = {
                                'site': site_value,
                                'study': row['Study']
                            }
                        st.session_state['calendar_combo_options'] = combo_options
                    else:
                        combo_options = cached_options

            # Calendar display options
            col_options = st.columns([1, 1, 1, 3])
            with col_options[0]:
                prev_hide_inactive = st.session_state.get('hide_inactive_patients', False)
                hide_inactive = st.checkbox(
                    "Hide inactive patients",
                    value=prev_hide_inactive,
                    help="Hide patients who have withdrawn, screen failed, or finished all visits",
                    key="hide_inactive_checkbox"
                )
                # Check if value changed and clear cache if so
                if hide_inactive != prev_hide_inactive:
                    clear_build_calendar_cache()
                    st.session_state.calendar_cache_buster = st.session_state.get('calendar_cache_buster', 0) + 1
                    st.session_state.hide_inactive_patients = hide_inactive
                    st.rerun()
                else:
                    st.session_state.hide_inactive_patients = hide_inactive
            with col_options[1]:
                prev_compact_mode = st.session_state.get('compact_calendar_mode', False)
                compact_mode = st.checkbox(
                    "Compact view",
                    value=prev_compact_mode,
                    help="Narrow columns with vertical headers and icons",
                    key="compact_mode_checkbox"
                )
                # Check if value changed and trigger rerun
                if compact_mode != prev_compact_mode:
                    st.session_state.compact_calendar_mode = compact_mode
                    st.rerun()
                else:
                    st.session_state.compact_calendar_mode = compact_mode
            with col_options[2]:
                if st.button("Scroll to Today", key="scroll_calendar_today", help="Re-center the calendar on today's date."):
                    st.session_state.scroll_to_today = True
                    st.rerun()
            with col_options[3]:
                combo_labels = list(combo_options.keys())
                default_selection = combo_labels.copy()
                initial_selection = st.session_state.get('calendar_site_study_filter', default_selection)
                if initial_selection:
                    initial_selection = [label for label in initial_selection if label in combo_labels]
                if not initial_selection:
                    initial_selection = default_selection
                selected_labels = st.multiselect(
                    "Sites & Studies",
                    options=combo_labels,
                    default=initial_selection,
                    help="Filter calendar data by site/study combination."
                ) if combo_labels else []
                if combo_labels:
                    st.session_state['calendar_site_study_filter'] = selected_labels

            if not selected_labels and combo_labels:
                selected_labels = combo_labels

            selected_meta = [combo_options[label] for label in selected_labels if label in combo_options]
            selected_studies = {item['study'] for item in selected_meta}
            selected_sites = {item['site'] for item in selected_meta}

            effective_studies = selected_studies if selected_studies else available_studies
            effective_sites = selected_sites if selected_sites else available_sites

            if effective_studies and 'Study' in visits_df_filtered.columns:
                visits_df_filtered = visits_df_filtered[visits_df_filtered['Study'].isin(effective_studies)]
            if effective_sites and site_field and site_field in visits_df_filtered.columns:
                visits_df_filtered = visits_df_filtered[visits_df_filtered[site_field].isin(effective_sites)]

            # Filter site column mapping to match selections
            filtered_site_column_mapping = {}
            for site, site_data in site_column_mapping.items():
                if effective_sites and site not in effective_sites:
                    continue

                patient_info = site_data.get('patient_info', [])
                events_col = site_data.get('events_column')

                filtered_patient_info = []
                filtered_columns = []

                for info in patient_info:
                    study_name = str(info.get('study', '')).strip()
                    if effective_studies and study_name not in effective_studies:
                        continue
                    filtered_columns.append(info.get('col_id'))
                    filtered_patient_info.append(info)

                if events_col:
                    filtered_columns.append(events_col)

                if filtered_columns:
                    filtered_site_column_mapping[site] = {
                        **site_data,
                        'columns': filtered_columns,
                        'patient_info': filtered_patient_info,
                        'events_column': events_col
                    }

            # Ensure we always have at least one site mapping to display
            if not filtered_site_column_mapping:
                filtered_site_column_mapping = site_column_mapping

            allowed_columns = set()
            base_columns = [col for col in ['Date', 'Day'] if col in calendar_df_filtered.columns]
            allowed_columns.update(base_columns)
            for site_data in filtered_site_column_mapping.values():
                site_columns = site_data.get('columns', [])
                allowed_columns.update(site_columns)

            keep_columns = [col for col in calendar_df_filtered.columns if col in allowed_columns]
            if keep_columns:
                calendar_df_filtered = calendar_df_filtered[keep_columns]

            filtered_unique_visit_sites = [site for site in unique_visit_sites if site in filtered_site_column_mapping]
            if not filtered_unique_visit_sites:
                filtered_unique_visit_sites = unique_visit_sites

            if calendar_start_date is not None:
                st.caption(f"Showing visits from {calendar_start_date.strftime('%d/%m/%Y')} onwards ({calendar_filter_option.get('label')}).")
            else:
                st.caption("Showing all recorded visits.")

            # Public - Always show
            compact_mode = st.session_state.get('compact_calendar_mode', False)
            hide_inactive_status = "enabled" if st.session_state.get('hide_inactive_patients', False) else "disabled"
            compact_status = "enabled" if compact_mode else "disabled"
            if hide_inactive_status == "enabled" or compact_status == "enabled":
                st.caption(f"📊 Display options: Hide inactive = {hide_inactive_status}, Compact mode = {compact_status}")
            display_calendar(calendar_df_filtered, filtered_site_column_mapping, filtered_unique_visit_sites, compact_mode=compact_mode)
            
            show_legend(actual_visits_df)
            
            site_summary_df = extract_site_summary(patients_df, screen_failures)
            if not site_summary_df.empty and effective_sites:
                site_column_candidates = [col for col in ['Site', 'Visit Site', 'VisitSite'] if col in site_summary_df.columns]
                if site_column_candidates:
                    site_summary_df = site_summary_df[site_summary_df[site_column_candidates[0]].isin(effective_sites)]
            if not site_summary_df.empty:
                display_site_statistics(site_summary_df)
            
            # Admin only - Financial reports
            if st.session_state.get('auth_level') == 'admin':
                display_monthly_income_tables(visits_df_filtered)
                
                financial_df = prepare_financial_data(visits_df_filtered)
                if not financial_df.empty:
                    display_quarterly_profit_sharing_tables(financial_df, patients_df)

                display_income_realization_analysis(visits_df_filtered, trials_df, patients_df)

                display_site_income_by_fy(visits_df_filtered, trials_df)
                
                # By-study income summary (current FY by default)
                display_study_income_summary(visits_df_filtered)

                # Site-wise statistics (includes financial data)
                display_site_wise_statistics(visits_df_filtered, patients_df, filtered_unique_visit_sites, screen_failures, withdrawals)
            else:
                st.info("🔒 Login as admin to view financial reports and income analysis")

            display_download_buttons(
                calendar_df_filtered,
                filtered_site_column_mapping,
                filtered_unique_visit_sites,
                patients_df,
                visits_df_filtered,
                trials_df,
                actual_visits_df
            )

            display_error_log_section()

        except Exception as e:
            st.error(f"Error processing files: {e}")
            st.exception(e)

    else:
        st.info("Please upload both Patients and Trials files to get started.")
        
        st.subheader("Required File Structure")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("""
            **Patients File**
            
            Required columns:
            - **PatientID** - Unique patient identifier
            - **Study** - Study name/code
            - **StartDate** - Patient enrollment date (DD/MM/YYYY)
            
            Optional columns:
            - **Site** / **PatientPractice** - Patient's home practice
            - **PatientSite** / **OriginSite** - Alternative site columns
            """)
        
        with col2:
            st.markdown("""
            **Trials File**
            
            Required columns:
            - **Study** - Study name/code (must match Patients file)
            - **Day** - Visit day number (Day 1 = baseline)
            - **VisitName** - Visit identifier
            - **SiteforVisit** - Where visit takes place
            
            Optional columns:
            - **Payment** / **Income** - Visit payment amount
            - **ToleranceBefore** - Days before visit allowed
            - **ToleranceAfter** - Days after visit allowed
            - **VisitType** - patient/siv/monitor for study events
            """)
        
        with col3:
            st.markdown("""
            **Actual Visits File** *(Optional)*
            
            Required columns:
            - **PatientID** - Must match Patients file
            - **Study** - Must match Study files
            - **VisitName** - Must match Trials file
            - **ActualDate** - When visit actually occurred
            
            Optional columns:
            - **Notes** - Visit notes (use 'ScreenFail' to mark failures, 'Withdrawn' to mark withdrawals)
            - **VisitType** - patient/siv/monitor (defaults to patient)
            
            Note: If a study event (siv/monitor) is in Actual Visits, it happened (completed).
            Both 'ScreenFail' and 'Withdrawn' in Notes will stop all future scheduled visits for that patient.
            """)
        
        st.markdown("---")
        
        st.markdown("""
        **Tips:**
        - Use CSV or Excel (.xlsx) files
        - Dates should be in UK format: DD/MM/YYYY (e.g., 31/12/2024)
        - PatientID, Study, and VisitName columns must match exactly between files
        - Each study must have exactly one Day 1 visit (baseline reference point)
        - Use 'ScreenFail' in the Notes column to automatically exclude future visits (screen failure)
        - Use 'Withdrawn' in the Notes column to automatically exclude future visits (patient withdrawal)
        - For study events (SIV/Monitor): use empty Day field in Trials file, manage via Actual Visits
        """)

if __name__ == "__main__":
    main()
