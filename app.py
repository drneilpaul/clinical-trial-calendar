import streamlit as st
import pandas as pd
from helpers import load_file, normalize_columns, parse_dates_column
from ui_patient_entry import patient_entry_form
from ui_visit_entry import visit_entry_form
from processing_calendar import build_calendar
from display_components import (
    show_legend, display_calendar, display_financial_tables,
    display_site_statistics, display_download_buttons
)

def extract_site_summary(patients_df, additional_data=None):
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

def main():
    st.set_page_config(page_title="Clinical Trial Calendar Generator", layout="wide")
    st.title("🏥 Clinical Trial Calendar Generator")

    mode = st.sidebar.radio("Navigation", ["View Calendar", "Add Patient", "Record Visit"])
    patients_file = st.sidebar.file_uploader("Upload Patients File", type=['csv', 'xls', 'xlsx'], key="patients")
    trials_file = st.sidebar.file_uploader("Upload Trials File", type=['csv', 'xls', 'xlsx'], key="trials")
    actual_visits_file = st.sidebar.file_uploader("Upload Actual Visits File (Optional)", type=['csv', 'xls', 'xlsx'], key="actual_visits")

    if mode == "Add Patient":
        if patients_file and trials_file:
            patient_entry_form(patients_file, trials_file)
        else:
            st.warning("Upload both Patients and Trials files to add a new patient.")
    elif mode == "Record Visit":
        if patients_file and trials_file:
            visit_entry_form(patients_file, trials_file, actual_visits_file)
        else:
            st.warning("Upload both Patients and Trials files to record a visit.")
    elif mode == "View Calendar":
        if not (patients_file and trials_file):
            st.info("Please upload both Patients and Trials files to get started.")
            return

        try:
            patients_df = normalize_columns(load_file(patients_file))
            trials_df = normalize_columns(load_file(trials_file))
            actual_visits_df = normalize_columns(load_file(actual_visits_file)) if actual_visits_file else None

            # Robust date parsing, alert user if rows fail
            patients_df, failed_patients = parse_dates_column(patients_df, "StartDate")
            if failed_patients:
                st.error(f"Unparseable StartDate values in Patients file: {failed_patients}")

            if actual_visits_df is not None:
                actual_visits_df, failed_actuals = parse_dates_column(actual_visits_df, "ActualDate")
                if failed_actuals:
                    st.error(f"Unparseable ActualDate values in Actual Visits file: {failed_actuals}")

            # All PatientID and VisitNo as strings
            patients_df["PatientID"] = patients_df["PatientID"].astype(str)
            if "VisitNo" in trials_df.columns:
                trials_df["VisitNo"] = trials_df["VisitNo"].astype(str)
            if actual_visits_df is not None and "VisitNo" in actual_visits_df.columns:
                actual_visits_df["VisitNo"] = actual_visits_df["VisitNo"].astype(str)

            # Check for missing studies before calendar generation
            missing_studies = set(patients_df["Study"].astype(str)) - set(trials_df["Study"].astype(str))
            if missing_studies:
                st.error(f"❌ Missing Study Definitions: {missing_studies}. Calendar cannot be generated.")
                st.stop()

            visits_df, calendar_df, stats, messages, site_column_mapping, unique_sites = build_calendar(
                patients_df, trials_df, actual_visits_df
            )
            
            # Show processing messages
            if messages:
                with st.expander("📋 View Processing Log", expanded=False):
                    for message in messages:
                        st.write(message)
                    
                    # Show out of window visits detail if any
                    if stats.get("out_of_window_visits") and len(stats.get("out_of_window_visits", [])) > 0:
                        st.write("**Out-of-Window Visit Details:**")
                        oow_df = pd.DataFrame(stats.get("out_of_window_visits", []))
                        st.dataframe(oow_df, use_container_width=True)

            site_summary_df = extract_site_summary(patients_df, {})
            show_legend(actual_visits_df)
            display_calendar(calendar_df, site_column_mapping, unique_sites, stats.get("out_of_window_visits"))
            display_financial_tables(stats, visits_df)
            display_site_statistics(site_summary_df)
            display_download_buttons(calendar_df)
            
        except Exception as e:
            st.error(f"Error processing files: {e}")
            st.exception(e)

if __name__ == "__main__":
    main()
