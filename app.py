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
import database as db
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

def check_and_refresh_data():
    """Check if data refresh is needed and reload from database"""
    if st.session_state.get('data_refresh_needed', False):
        if st.session_state.get('use_database', False):
            try:
                st.session_state.patients_df = db.fetch_all_patients()
                st.session_state.trials_df = db.fetch_all_trial_schedules()
                st.session_state.actual_visits_df = db.fetch_all_actual_visits()
                
                log_activity("Data refreshed from database", level='success')
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
    
    # File uploaders
    if st.session_state.get('database_available', False):
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
                                        st.session_state.use_database = True
                                        st.session_state.overwrite_patients_confirmed = False
                                        st.session_state.data_refresh_needed = True
                                        st.session_state.overwrite_in_progress = False
                                        st.rerun()
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
                                        st.session_state.use_database = True
                                        st.session_state.overwrite_trials_confirmed = False
                                        st.session_state.data_refresh_needed = True
                                        st.session_state.overwrite_in_progress = False
                                        st.rerun()
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
                                        st.session_state.use_database = True
                                        st.session_state.overwrite_visits_confirmed = False
                                        st.session_state.data_refresh_needed = True
                                        st.session_state.overwrite_in_progress = False
                                        st.rerun()
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
        st.sidebar.caption("Upload your data files to get started")
        
        trials_file = st.sidebar.file_uploader("Upload Trials File", type=['csv', 'xls', 'xlsx'])
        patients_file = st.sidebar.file_uploader("Upload Patients File", type=['csv', 'xls', 'xlsx'])
        actual_visits_file = st.sidebar.file_uploader("Upload Actual Visits File (Optional)", type=['csv', 'xls', 'xlsx'])
    
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
    
    # Database Operations
    if st.session_state.get('database_available', False):
        st.sidebar.divider()
        with st.sidebar.expander("🔧 Database Operations & Debug", expanded=False):
            st.caption("Database management and debugging tools")
            
            if st.button("🧪 Test DB Connection", use_container_width=True):
                try:
                    if db.test_database_connection():
                        st.success("✅ Database connected and tables found")
                    else:
                        st.error(f"❌ Database issue: {st.session_state.get('database_status', 'Unknown')}")
                except Exception as e:
                    st.error(f"❌ Database test failed: {e}")
            
            st.divider()
            
            if st.button("🔍 Check All Database Tables", use_container_width=True):
                st.session_state.show_database_contents = True
                st.rerun()
            
            st.divider()
            
            if st.button("🔄 Refresh App Data", use_container_width=True):
                if 'patients_df' in st.session_state:
                    del st.session_state['patients_df']
                if 'trials_df' in st.session_state:
                    del st.session_state['trials_df']
                if 'actual_visits_df' in st.session_state:
                    del st.session_state['actual_visits_df']
                
                st.session_state.data_refresh_needed = True
                st.success("Data refresh triggered!")
                st.rerun()
            
            st.divider()
            
            st.session_state.show_debug_info = st.checkbox("Show Debug Info", value=st.session_state.get('show_debug_info', False))
            
            st.divider()
            
            if st.button("📦 Download DB Backup", use_container_width=True):
                backup_zip = db.create_backup_zip()
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
            
            if st.button("❌ Close Database View", use_container_width=True):
                st.session_state.show_database_contents = False
                st.rerun()
                
        except Exception as e:
            st.error(f"Error fetching database contents: {e}")
        
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
        show_download_sections()

        try:
            visits_df, calendar_df, stats, messages, site_column_mapping, unique_visit_sites, patients_df = build_calendar(
                patients_df, trials_df, actual_visits_df
            )
            
            screen_failures = extract_screen_failures(actual_visits_df)

            display_processing_messages(messages)
            
            display_calendar(calendar_df, site_column_mapping, unique_visit_sites)
            
            show_legend(actual_visits_df)
            
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
            - **Notes** - Visit notes (use 'ScreenFail' to mark failures)
            - **VisitType** - patient/siv/monitor (defaults to patient)
            - **Status** - completed/proposed/cancelled (defaults to completed)
            """)
        
        st.markdown("---")
        
        st.markdown("""
        **Tips:**
        - Use CSV or Excel (.xlsx) files
        - Dates should be in UK format: DD/MM/YYYY (e.g., 31/12/2024)
        - PatientID, Study, and VisitName columns must match exactly between files
        - Each study must have exactly one Day 1 visit (baseline reference point)
        - Use 'ScreenFail' in the Notes column to automatically exclude future visits
        - For study events (SIV/Monitor): use empty Day field in Trials file, manage via Actual Visits
        """)

if __name__ == "__main__":
    main()
