import streamlit as st
import pandas as pd
from helpers import load_file, normalize_columns, parse_dates_column, standardize_visit_columns, safe_string_conversion_series, load_file_with_defaults
from processing_calendar import build_calendar
from display_components import (
    show_legend, display_calendar, display_site_statistics,
    display_download_buttons, display_monthly_income_tables,
    display_quarterly_profit_sharing_tables, display_income_realization_analysis,
    display_verification_figures
)
# Import modal forms
from modal_forms_cloud import handle_patient_modal, handle_visit_modal, handle_study_event_modal, show_download_sections
from data_analysis import (
    extract_screen_failures, display_site_wise_statistics, display_processing_messages
)
from calculations import prepare_financial_data
from config import initialize_session_state, get_file_structure_info, APP_TITLE, APP_VERSION, APP_SUBTITLE, setup_database_connection, load_data_from_source

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
    st.sidebar.header("Upload Data Files")
    trials_file = st.sidebar.file_uploader("Upload Trials File", type=['csv', 'xls', 'xlsx'])
    patients_file = st.sidebar.file_uploader("Upload Patients File", type=['csv', 'xls', 'xlsx'])
    actual_visits_file = st.sidebar.file_uploader("Upload Actual Visits File (Optional)", type=['csv', 'xls', 'xlsx'])
    
    st.session_state.patients_file = patients_file
    st.session_state.trials_file = trials_file
    st.session_state.actual_visits_file = actual_visits_file
    
    return patients_file, trials_file, actual_visits_file

def display_action_buttons():
    """Enhanced action buttons with study events"""
    col1, col2, col3 = st.columns([1, 1, 1])
    
    # Check if we have data source available
    has_data_source = False
    if st.session_state.use_database and st.session_state.database_connected:
        has_data_source = True
    elif st.session_state.get('patients_file') and st.session_state.get('trials_file'):
        has_data_source = True
    
    with col1:
        if st.button("Add New Patient", use_container_width=True, disabled=not has_data_source):
            if has_data_source:
                st.session_state.show_patient_form = True
            else:
                st.error("Please connect to database or upload files first")
    
    with col2:
        if st.button("Record Patient Visit", use_container_width=True, disabled=not has_data_source):
            if has_data_source:
                if st.session_state.use_database and st.session_state.database_connected:
                    # Database mode - always available
                    st.session_state.show_visit_form = True
                else:
                    # File mode - need actual visits file
                    actual_visits_file = st.session_state.get('actual_visits_file')
                    if actual_visits_file:
                        st.session_state.show_visit_form = True
                    else:
                        st.error("Please upload an Actual Visits file or use database mode")
            else:
                st.error("Please connect to database or upload files first")
    
    with col3:
        if st.button("Manage Study Events", use_container_width=True, disabled=not has_data_source):
            if has_data_source:
                st.session_state.show_study_event_form = True
            else:
                st.error("Please connect to database or upload files first")

def main():
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    st.title(APP_TITLE)
    st.caption(f"{APP_VERSION} | {APP_SUBTITLE}")

    initialize_session_state()
    
    # Setup database connection (returns True if using database)
    use_database = setup_database_connection()
    
    # Setup file uploaders (only show if not using database)
    if not use_database:
        patients_file, trials_file, actual_visits_file = setup_file_uploaders()
    else:
        patients_file, trials_file, actual_visits_file = None, None, None

    # Load data from appropriate source
    patients_df, trials_df, actual_visits_df, _, _, _ = load_data_from_source()
    
    # Check if we have required data
    has_required_data = (not patients_df.empty and not trials_df.empty)
    
    if has_required_data:
        display_action_buttons()
        
        handle_patient_modal()
        handle_visit_modal()
        handle_study_event_modal()
        
        # Only show download sections in file mode
        if not use_database:
            show_download_sections()

        try:
            # Process dates and validation
            patients_df, trials_df, actual_visits_df = process_dates_and_validation(
                patients_df, trials_df, actual_visits_df
            )

            visits_df, calendar_df, stats, messages, site_column_mapping, unique_visit_sites = build_calendar(
                patients_df, trials_df, actual_visits_df
            )
            
            screen_failures = extract_screen_failures(actual_visits_df)

            display_processing_messages(messages)

            site_summary_df = extract_site_summary(patients_df, screen_failures)
            if not site_summary_df.empty:
                display_site_statistics(site_summary_df)

            show_legend(actual_visits_df)
            display_calendar(calendar_df, site_column_mapping, unique_visit_sites)
            
            display_monthly_income_tables(visits_df)
            
            financial_df = prepare_financial_data(visits_df)
            if not financial_df.empty:
                display_quarterly_profit_sharing_tables(financial_df, patients_df)

            display_income_realization_analysis(visits_df, trials_df, patients_df)

            display_site_wise_statistics(visits_df, patients_df, unique_visit_sites, screen_failures)

            # Only show download buttons in file mode
            if not use_database:
                display_download_buttons(calendar_df, site_column_mapping, unique_visit_sites)
            
            display_verification_figures(visits_df, calendar_df, financial_df, patients_df)

        except Exception as e:
            st.error(f"Error processing data: {e}")
            st.exception(e)

    else:
        if use_database:
            if st.session_state.database_connected:
                st.info("Database connected but no data found. Add some patients and trials to get started.")
            else:
                st.info("Please connect to the database to load data.")
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
