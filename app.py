import streamlit as st
import pandas as pd
from helpers import load_file, normalize_columns, parse_dates_column
from processing_calendar import build_calendar

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

    # Simple file uploaders
    patients_file = st.sidebar.file_uploader("Upload Patients File", type=['csv', 'xls', 'xlsx'])
    trials_file = st.sidebar.file_uploader("Upload Trials File", type=['csv', 'xls', 'xlsx'])
    actual_visits_file = st.sidebar.file_uploader("Upload Actual Visits File (Optional)", type=['csv', 'xls', 'xlsx'])

    if not (patients_file and trials_file):
        st.info("Please upload both Patients and Trials files to get started.")
        return

    try:
        # Load files
        patients_df = normalize_columns(load_file(patients_file))
        trials_df = normalize_columns(load_file(trials_file))
        actual_visits_df = normalize_columns(load_file(actual_visits_file)) if actual_visits_file else None

        # Robust date parsing
        patients_df, failed_patients = parse_dates_column(patients_df, "StartDate")
        if failed_patients:
            st.error(f"Unparseable StartDate values in Patients file: {failed_patients}")

        if actual_visits_df is not None:
            actual_visits_df, failed_actuals = parse_dates_column(actual_visits_df, "ActualDate")
            if failed_actuals:
                st.error(f"Unparseable ActualDate values in Actual Visits file: {failed_actuals}")

        # Convert data types
        patients_df["PatientID"] = patients_df["PatientID"].astype(str)
        if "VisitNo" in trials_df.columns:
            trials_df["VisitNo"] = trials_df["VisitNo"].astype(str)
        if actual_visits_df is not None and "VisitNo" in actual_visits_df.columns:
            actual_visits_df["VisitNo"] = actual_visits_df["VisitNo"].astype(str)

        # Check for missing studies
        missing_studies = set(patients_df["Study"].astype(str)) - set(trials_df["Study"].astype(str))
        if missing_studies:
            st.error(f"❌ Missing Study Definitions: {missing_studies}. Calendar cannot be generated.")
            st.stop()

        # Build calendar
        visits_df, calendar_df, stats, messages, site_column_mapping, unique_sites = build_calendar(
            patients_df, trials_df, actual_visits_df
        )
        
        # Show basic results
        st.success("Calendar generated successfully!")
        
        # Show processing messages
        if messages:
            with st.expander("📋 View Processing Log", expanded=False):
                for message in messages:
                    st.write(message)

        # Display basic calendar
        st.subheader("Generated Visit Calendar")
        st.dataframe(calendar_df, use_container_width=True)
        
        # Basic statistics
        st.subheader("Statistics")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total Visits", stats.get("total_visits", 0))
        with col2:
            st.metric("Total Income", f"£{stats.get('total_income', 0):,.2f}")

        # Site summary
        site_summary_df = extract_site_summary(patients_df, {})
        if not site_summary_df.empty:
            st.subheader("Site Summary")
            st.dataframe(site_summary_df, use_container_width=True)

        # Basic download
        import io
        buf = io.BytesIO()
        calendar_df.to_excel(buf, index=False)
        st.download_button(
            "💾 Download Calendar Excel", 
            data=buf.getvalue(), 
            file_name="VisitCalendar.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
            
    except Exception as e:
        st.error(f"Error processing files: {e}")
        st.exception(e)

if __name__ == "__main__":
    main()
