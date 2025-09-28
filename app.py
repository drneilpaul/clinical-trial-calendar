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
    # Determine the most appropriate site column
    site_col = None
    for candidate in ['Site', 'PatientPractice', 'PatientSite', 'OriginSite', 'Practice', 'HomeSite']:
        if candidate in df.columns:
            site_col = candidate
            break
    if site_col is None:
        # Fallback: mark as Unknown Site
        df['__Site'] = 'Unknown Site'
        site_col = '__Site'

    # Ensure string types
    df[site_col] = df[site_col].astype(str).str.strip().replace({'nan': 'Unknown Site'})

    # Group by resolved site and count patients
    site_summary = df.groupby(site_col).agg({
        'PatientID': 'count',
        'Study': lambda x: ', '.join(sorted(map(str, x.unique())))
    }).rename(columns={'PatientID': 'Patient_Count', 'Study': 'Studies'})

    site_summary = site_summary.reset_index()
    site_summary = site_summary.rename(columns={site_col: 'Site'})
    return site_summary

def process_dates_and_validation(patients_df, trials_df, actual_visits_df):
    """Handle date parsing and basic validation"""
    # Date parsing
    patients_df, failed_patients = parse_dates_column(patients_df, "StartDate")
    if failed_patients:
        st.error(f"Unparseable StartDate values: {failed_patients}")

    if actual_visits_df is not None:
        actual_visits_df, failed_actuals = parse_dates_column(actual_visits_df, "ActualDate")
        if failed_actuals:
            st.error(f"Unparseable ActualDate values: {failed_actuals}")

    # Data type conversion - ensure consistent string types using Series-safe function
    patients_df["PatientID"] = safe_string_conversion_series(patients_df["PatientID"])
    patients_df["Study"] = safe_string_conversion_series(patients_df["Study"])
    
    # Standardize visit columns (VisitName only - no VisitNo support)
    trials_df = standardize_visit_columns(trials_df)
    trials_df["Study"] = safe_string_conversion_series(trials_df["Study"])
    
    if actual_visits_df is not None:
        actual_visits_df = standardize_visit_columns(actual_visits_df)
        actual_visits_df["PatientID"] = safe_string_conversion_series(actual_visits_df["PatientID"])
        actual_visits_df["Study"] = safe_string_conversion_series(actual_visits_df["Study"])

    # Check missing studies
    missing_studies = set(patients_df["Study"]) - set(trials_df["Study"])
    if missing_studies:
        st.error(f"Missing Study Definitions: {missing_studies}")
        st.stop()

    # Validate Day 1 baseline exists for each study
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
    
    # Store in session state
    st.session_state.patients_file = patients_file
    st.session_state.trials_file = trials_file
    st.session_state.actual_visits_file = actual_visits_file
    
    return patients_file, trials_file, actual_visits_file

def display_action_buttons():
    """Enhanced action buttons with study events"""
    col1, col2, col3 = st.columns([1, 1, 1])
    
    with col1:
        if st.button("Add New Patient", use_container_width=True):
            st.session_state.show_patient_form = True
    
    with col2:
        if st.button("Record Patient Visit", use_container_width=True):
            # Check if actual visits file is loaded before showing form
            actual_visits_file = st.session_state.get('actual_visits_file')
            if actual_visits_file:
                st.session_state.show_visit_form = True
            else:
                st.error("Please upload an Actual Visits file before recording visits")
    
    with col3:
        if st.button("Manage Study Events", use_container_width=True):
            st.session_state.show_study_event_form = True

def show_download_sections():
    """Enhanced download sections including study events"""
    if st.session_state.get('patient_added', False):
        show_patient_download()
    
    if st.session_state.get('visit_added', False):
        show_visit_download()
    
    if st.session_state.get('event_added', False) or st.session_state.get('event_updated', False):
        show_event_download()

def show_patient_download():
    """Show patient download section"""
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        filename = st.session_state.get('updated_filename', 'Patients_Updated.xlsx')
        file_data = st.session_state.get('updated_patients_file')
        
        if file_data:
            # Determine MIME type
            mime_type = ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" 
                        if filename.endswith('.xlsx') else "text/csv")
            
            st.download_button(
                "Download Updated Patients File",
                data=file_data,
                file_name=filename,
                mime=mime_type,
                use_container_width=True
            )
        
        if st.button("Done", use_container_width=True):
            st.session_state.patient_added = False
            st.rerun()
    st.info("Patient added! Download and re-upload to see changes.")
    st.divider()

def show_visit_download():
    """Show visit download section"""
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        filename = st.session_state.get('updated_visits_filename', 'ActualVisits_Updated.xlsx')
        file_data = st.session_state.get('updated_visits_file')
        
        if file_data:
            # Determine MIME type
            mime_type = ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" 
                        if filename.endswith('.xlsx') else "text/csv")
            
            st.download_button(
                "Download Updated Visits File",
                data=file_data,
                file_name=filename,
                mime=mime_type,
                use_container_width=True
            )
        
        if st.button("Done", use_container_width=True):
            st.session_state.visit_added = False
            st.rerun()
    st.info("Visit recorded! Download and re-upload to see changes.")
    st.divider()

def show_event_download():
    """Show event download section"""
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        filename = st.session_state.get('updated_events_filename', 'ActualVisits_Updated.xlsx')
        file_data = st.session_state.get('updated_events_file')
        
        if file_data:
            mime_type = ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" 
                        if filename.endswith('.xlsx') else "text/csv")
            
            st.download_button(
                "Download Updated Events File",
                data=file_data,
                file_name=filename,
                mime=mime_type,
                use_container_width=True
            )
        
        if st.button("Done", use_container_width=True):
            st.session_state.event_added = False
            st.session_state.event_updated = False
            st.rerun()
    st.info("Study event updated! Download and re-upload to see changes.")
    st.divider()

def main():
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    st.title(APP_TITLE)
    st.caption(f"{APP_VERSION} | {APP_SUBTITLE}")

    # Initialize session state
    initialize_session_state()

    # Setup file uploaders
    patients_file, trials_file, actual_visits_file = setup_file_uploaders()

    if patients_file and trials_file:
        # Display action buttons
        display_action_buttons()
        
        # Handle modals and downloads
        handle_patient_modal()
        handle_visit_modal()
        handle_study_event_modal()
        show_download_sections()

        try:
            # Load and process files with enhanced defaults for new columns
            patients_df = normalize_columns(load_file(patients_file))
            trials_df = normalize_columns(load_file(trials_file))
            actual_visits_df = None
            if actual_visits_file:
                actual_visits_df = normalize_columns(load_file_with_defaults(
                    actual_visits_file,
                    {'VisitType': 'patient', 'Status': 'completed'}
                ))

            # Process dates and validation
            patients_df, trials_df, actual_visits_df = process_dates_and_validation(
                patients_df, trials_df, actual_visits_df
            )

            # Build calendar - now returns unique_visit_sites instead of unique_sites
            visits_df, calendar_df, stats, messages, site_column_mapping, unique_visit_sites = build_calendar(
                patients_df, trials_df, actual_visits_df
            )
            
            # Extract screen failures
            screen_failures = extract_screen_failures(actual_visits_df)

            # Display processing messages
            display_processing_messages(messages)

            # Main displays
            site_summary_df = extract_site_summary(patients_df, screen_failures)
            if not site_summary_df.empty:
                display_site_statistics(site_summary_df)

            show_legend(actual_visits_df)
            # Updated to use unique_visit_sites instead of unique_sites
            display_calendar(calendar_df, site_column_mapping, unique_visit_sites)
            
            # Monthly Income Tables and Ratio Calculations (NO CHARTS)
            display_monthly_income_tables(visits_df)
            
            # Quarterly Profit Sharing Tables and Calculations (NO CHARTS)
            financial_df = prepare_financial_data(visits_df)
            if not financial_df.empty:
                display_quarterly_profit_sharing_tables(financial_df, patients_df)

            # Income Realization Analysis
            display_income_realization_analysis(visits_df, trials_df, patients_df)

            # Site statistics and analysis - use unique_visit_sites for consistency
            display_site_wise_statistics(visits_df, patients_df, unique_visit_sites, screen_failures)

            # Download options - use unique_visit_sites 
            display_download_buttons(calendar_df, site_column_mapping, unique_visit_sites)
            
            # Verification figures for testing
            display_verification_figures(visits_df, calendar_df, financial_df, patients_df)

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
        
        st.markdown("---")
        
        st.markdown("""
        **Getting Started:**
        1. Upload your Trials file and Patients file using the sidebar
        2. Optionally upload Actual Visits file to track completed visits
        3. Use the 'Add New Patient', 'Record Patient Visit', and 'Manage Study Events' buttons
        4. Download the generated calendar with financial analysis
        """)

if __name__ == "__main__":
    main()
