import streamlit as st
from helpers import load_file, normalize_columns, parse_dates_column
from processing_calendar import build_calendar
from display_components import (
    show_legend, display_calendar,
    display_site_statistics,
    display_download_buttons
)
from modal_forms import handle_patient_modal, handle_visit_modal, show_download_sections
from data_analysis import (
    extract_screen_failures, prepare_financial_data,
    display_site_wise_statistics, display_monthly_analysis_by_site,
    display_processing_messages
)
from config import initialize_session_state, get_file_structure_info, APP_TITLE, APP_VERSION, APP_SUBTITLE

def extract_site_summary(patients_df, screen_failures=None):
    """Extract site summary statistics from patients dataframe"""
    if patients_df.empty:
        return pd.DataFrame()
    
    # Group by site and count patients
    site_summary = patients_df.groupby('Site').agg({
        'PatientID': 'count',
        'Study': lambda x: ', '.join(x.unique())
    }).rename(columns={'PatientID': 'Patient_Count', 'Study': 'Studies'})
    
    site_summary = site_summary.reset_index()
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

    # Data type conversion
    patients_df["PatientID"] = patients_df["PatientID"].astype(str)
    if "VisitNo" in trials_df.columns:
        trials_df["VisitNo"] = trials_df["VisitNo"].astype(str)
    if actual_visits_df is not None and "VisitNo" in actual_visits_df.columns:
        actual_visits_df["VisitNo"] = actual_visits_df["VisitNo"].astype(str)

    # Check missing studies
    missing_studies = set(patients_df["Study"].astype(str)) - set(trials_df["Study"].astype(str))
    if missing_studies:
        st.error(f"Missing Study Definitions: {missing_studies}")
        st.stop()

    return patients_df, trials_df, actual_visits_df

def setup_file_uploaders():
    """Setup file uploaders and store in session state"""
    st.sidebar.header("Upload Data Files")
    patients_file = st.sidebar.file_uploader("Upload Patients File", type=['csv', 'xls', 'xlsx'])
    trials_file = st.sidebar.file_uploader("Upload Trials File", type=['csv', 'xls', 'xlsx'])
    actual_visits_file = st.sidebar.file_uploader("Upload Actual Visits File (Optional)", type=['csv', 'xls', 'xlsx'])
    
    # Store in session state
    st.session_state.patients_file = patients_file
    st.session_state.trials_file = trials_file
    st.session_state.actual_visits_file = actual_visits_file
    
    return patients_file, trials_file, actual_visits_file

def display_action_buttons():
    """Display action buttons for adding patients and recording visits"""
    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        if st.button("Add New Patient", use_container_width=True):
            st.session_state.show_patient_form = True
    with col2:
        if st.button("Record Visit", use_container_width=True):
            st.session_state.show_visit_form = True

def main():
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    st.title(APP_TITLE)
    st.caption(f"{APP_VERSION} | {APP_SUBTITLE}")

    # Initialize session state
    initialize_session_state()

    # Setup file uploaders
    patients_file, trials_file, actual_visits_file = setup_file_uploaders()

    # File structure information
    with st.sidebar.expander("Required File Structure"):
        st.markdown(get_file_structure_info())

    if patients_file and trials_file:
        # Display action buttons
        display_action_buttons()
        
        # Handle modals and downloads
        handle_patient_modal()
        handle_visit_modal()
        show_download_sections()

        try:
            # Load and process files
            patients_df = normalize_columns(load_file(patients_file))
            trials_df = normalize_columns(load_file(trials_file))
            actual_visits_df = normalize_columns(load_file(actual_visits_file)) if actual_visits_file else None

            # Process dates and validation
            patients_df, trials_df, actual_visits_df = process_dates_and_validation(
                patients_df, trials_df, actual_visits_df
            )

            # Build calendar
            visits_df, calendar_df, stats, messages, site_column_mapping, unique_sites = build_calendar(
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
            display_calendar(calendar_df, site_column_mapping, unique_sites)
            
            # REMOVED: display_financial_analysis(stats, visits_df)
            
            # REMOVED: Quarterly profit sharing section
            # financial_df = prepare_financial_data(visits_df)
            # if not financial_df.empty:
            #     display_quarterly_profit_sharing(financial_df, patients_df)

            # Site statistics and analysis
            display_site_wise_statistics(visits_df, patients_df, unique_sites, screen_failures)
            # REMOVED: display_monthly_analysis_by_site(visits_df) - contains line charts

            # Download options
            display_download_buttons(calendar_df, site_column_mapping, unique_sites)

        except Exception as e:
            st.error(f"Error processing files: {e}")
            st.exception(e)

    else:
        st.info("Please upload both Patients and Trials files to get started.")
        st.markdown(get_file_structure_info())

if __name__ == "__main__":
    main()
