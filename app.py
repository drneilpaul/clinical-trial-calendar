import streamlit as st
import pandas as pd
import io
from datetime import date
import re
import streamlit.components.v1 as components

# Import helper functions
from helpers import load_file, normalize_columns, parse_dates_column
from processing_calendar import build_calendar
from display_components import (
    show_legend, 
    display_calendar, 
    display_financial_analysis,
    display_site_statistics, 
    display_quarterly_profit_sharing,
    display_download_buttons
)

# Initialize session state
if 'show_patient_form' not in st.session_state:
    st.session_state.show_patient_form = False
if 'show_visit_form' not in st.session_state:
    st.session_state.show_visit_form = False
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

def patient_entry_modal():
    """Modal for adding patients"""
    @st.dialog("Add New Patient")
    def patient_form():
        patients_file = st.session_state.get('patients_file')
        trials_file = st.session_state.get('trials_file')
        
        if not patients_file or not trials_file:
            st.error("Files not available")
            return
        
        existing_patients = load_file(patients_file)
        existing_patients.columns = existing_patients.columns.str.strip()
        existing_trials = load_file(trials_file)
        existing_trials.columns = existing_trials.columns.str.strip()
        
        available_studies = sorted(existing_trials["Study"].unique().tolist())
        
        # Get existing sites
        patient_origin_col = None
        possible_origin_cols = ['PatientSite', 'OriginSite', 'Practice', 'PatientPractice', 'HomeSite', 'Site']
        for col in possible_origin_cols:
            if col in existing_patients.columns:
                patient_origin_col = col
                break
        
        existing_sites = sorted(existing_patients[patient_origin_col].dropna().unique().tolist()) if patient_origin_col else ["Ashfields", "Kiltearn"]
        
        new_patient_id = st.text_input("Patient ID")
        new_study = st.selectbox("Study", options=available_studies)
        new_start_date = st.date_input("Start Date")
        
        if patient_origin_col:
            new_site = st.selectbox(f"{patient_origin_col}", options=existing_sites + ["Add New..."])
            if new_site == "Add New...":
                new_site = st.text_input("New Site Name")
        else:
            new_site = st.text_input("Patient Site")
        
        # Validation
        validation_errors = []
        if new_patient_id and new_patient_id in existing_patients["PatientID"].astype(str).values:
            validation_errors.append("Patient ID already exists")
        if new_start_date and new_start_date > date.today():
            validation_errors.append("Start date cannot be in future")
        
        if validation_errors:
            for error in validation_errors:
                st.error(error)
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Add Patient", disabled=bool(validation_errors), use_container_width=True):
                # Create new patient record
                new_patient_data = {
                    "PatientID": new_patient_id,
                    "Study": new_study,
                    "StartDate": new_start_date,
                }
                
                if patient_origin_col:
                    new_patient_data[patient_origin_col] = new_site
                else:
                    new_patient_data["PatientPractice"] = new_site
                
                # Add other columns
                for col in existing_patients.columns:
                    if col not in new_patient_data:
                        new_patient_data[col] = ""
                
                new_row_df = pd.DataFrame([new_patient_data])
                updated_patients_df = pd.concat([existing_patients, new_row_df], ignore_index=True)
                
                # Create download
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    updated_patients_df.to_excel(writer, index=False, sheet_name="Patients")
                
                st.session_state.updated_patients_file = output.getvalue()
                st.session_state.updated_filename = f"Patients_Updated_{new_start_date.strftime('%Y%m%d')}.xlsx"
                st.session_state.patient_added = True
                st.session_state.show_patient_form = False
                
                st.success("Patient added successfully!")
                st.rerun()
        
        with col2:
            if st.button("Cancel", use_container_width=True):
                st.session_state.show_patient_form = False
                st.rerun()
    
    patient_form()

def visit_entry_modal():
    """Modal for recording visits"""
    @st.dialog("Record Visit")
    def visit_form():
        patients_file = st.session_state.get('patients_file')
        trials_file = st.session_state.get('trials_file')
        actual_visits_file = st.session_state.get('actual_visits_file')
        
        if not patients_file or not trials_file:
            st.error("Files not available")
            return
        
        existing_patients = load_file(patients_file)
        existing_patients.columns = existing_patients.columns.str.strip()
        existing_trials = load_file(trials_file)
        existing_trials.columns = existing_trials.columns.str.strip()
        
        # Load existing visits
        existing_visits = pd.DataFrame()
        if actual_visits_file:
            existing_visits = load_file(actual_visits_file)
            existing_visits.columns = existing_visits.columns.str.strip()
        
        # Patient selection
        patient_options = []
        for _, patient in existing_patients.iterrows():
            patient_options.append(f"{patient['PatientID']} ({patient['Study']})")
        
        selected_patient = st.selectbox("Select Patient", options=patient_options)
        
        if selected_patient:
            # Extract patient ID and study
            patient_info = selected_patient.split(" (")
            patient_id = patient_info[0]
            study = patient_info[1].rstrip(")")
            
            # Get available visits for this study
            study_visits = existing_trials[existing_trials["Study"] == study]
            visit_options = []
            for _, visit in study_visits.iterrows():
                visit_options.append(f"Visit {visit['VisitNo']} (Day {visit['Day']})")
            
            selected_visit = st.selectbox("Visit Number", options=visit_options)
            
            if selected_visit:
                visit_no = selected_visit.split(" ")[1].split(" ")[0]
                visit_date = st.date_input("Visit Date")
                
                # Get default payment
                visit_payment = existing_trials[
                    (existing_trials["Study"] == study) & 
                    (existing_trials["VisitNo"].astype(str) == visit_no)
                ]
                default_payment = visit_payment["Payment"].iloc[0] if len(visit_payment) > 0 and "Payment" in visit_payment.columns else 0
                
                actual_payment = st.number_input("Payment Amount", value=float(default_payment), min_value=0.0)
                notes = st.text_area("Notes (Optional)", help="Use 'ScreenFail' to stop future visits")
                
                # Validation
                validation_errors = []
                if visit_date > date.today():
                    validation_errors.append("Visit date cannot be in future")
                
                # Check for duplicates
                if len(existing_visits) > 0:
                    duplicate_visit = existing_visits[
                        (existing_visits["PatientID"].astype(str) == str(patient_id)) &
                        (existing_visits["Study"] == study) &
                        (existing_visits["VisitNo"].astype(str) == visit_no)
                    ]
                    if len(duplicate_visit) > 0:
                        validation_errors.append(f"Visit {visit_no} for patient {patient_id} already recorded")
                
                if validation_errors:
                    for error in validation_errors:
                        st.error(error)
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Record Visit", disabled=bool(validation_errors), use_container_width=True):
                        # Create new visit record
                        new_visit_data = {
                            "PatientID": patient_id,
                            "Study": study,
                            "VisitNo": visit_no,
                            "ActualDate": visit_date,
                            "ActualPayment": actual_payment,
                            "Notes": notes or ""
                        }
                        
                        if len(existing_visits) > 0:
                            new_visit_df = pd.DataFrame([new_visit_data])
                            updated_visits_df = pd.concat([existing_visits, new_visit_df], ignore_index=True)
                        else:
                            updated_visits_df = pd.DataFrame([new_visit_data])
                        
                        # Create download
                        output = io.BytesIO()
                        with pd.ExcelWriter(output, engine='openpyxl') as writer:
                            updated_visits_df.to_excel(writer, index=False, sheet_name="ActualVisits")
                        
                        st.session_state.updated_visits_file = output.getvalue()
                        st.session_state.updated_visits_filename = f"ActualVisits_Updated_{visit_date.strftime('%Y%m%d')}.xlsx"
                        st.session_state.visit_added = True
                        st.session_state.show_visit_form = False
                        
                        st.success("Visit recorded successfully!")
                        st.rerun()
                
                with col2:
                    if st.button("Cancel", use_container_width=True):
                        st.session_state.show_visit_form = False
                        st.rerun()
    
    visit_form()

def extract_site_summary(patients_df, screen_failures=None):
    """Extract site summary statistics"""
    if patients_df.empty:
        return pd.DataFrame()
    
    unique_sites = sorted(patients_df["Site"].unique())
    site_summary_data = []
    
    for site in unique_sites:
        site_patients = patients_df[patients_df["Site"] == site]
        site_studies = site_patients["Study"].unique()
        
        site_screen_fails = 0
        if screen_failures:
            for _, patient in site_patients.iterrows():
                patient_study_key = f"{patient['PatientID']}_{patient['Study']}"
                if patient_study_key in screen_failures:
                    site_screen_fails += 1
        
        site_summary_data.append({
            "Site": site,
            "Patients": len(site_patients),
            "Screen Failures": site_screen_fails,
            "Active Patients": len(site_patients) - site_screen_fails,
            "Studies": ", ".join(sorted(site_studies))
        })
    
    return pd.DataFrame(site_summary_data)

def main():
    st.set_page_config(page_title="Clinical Trial Calendar Generator", layout="wide")
    st.title("Clinical Trial Calendar Generator")
    st.caption("v2.2.2 | Modular Architecture with Enhanced Features")

    # File uploaders
    st.sidebar.header("Upload Data Files")
    patients_file = st.sidebar.file_uploader("Upload Patients File", type=['csv', 'xls', 'xlsx'])
    trials_file = st.sidebar.file_uploader("Upload Trials File", type=['csv', 'xls', 'xlsx'])
    actual_visits_file = st.sidebar.file_uploader("Upload Actual Visits File (Optional)", type=['csv', 'xls', 'xlsx'])
    
    # Store in session state
    st.session_state.patients_file = patients_file
    st.session_state.trials_file = trials_file
    st.session_state.actual_visits_file = actual_visits_file

    # File structure information
    with st.sidebar.expander("Required File Structure"):
        st.markdown("""
        **Patients File:**
        - PatientID, Study, StartDate
        - Site/PatientPractice (optional)
        
        **Trials File:**
        - Study, Day, VisitNo, SiteforVisit
        - Payment, ToleranceBefore, ToleranceAfter
        
        **Actual Visits File:**
        - PatientID, Study, VisitNo, ActualDate
        - ActualPayment, Notes (optional)
        - Use 'ScreenFail' in Notes to exclude future visits
        """)

    if patients_file and trials_file:
        # Action buttons
        col1, col2, col3 = st.columns([1, 1, 1])
        with col1:
            if st.button("Add New Patient", use_container_width=True):
                st.session_state.show_patient_form = True
        with col2:
            if st.button("Record Visit", use_container_width=True):
                st.session_state.show_visit_form = True
        
        # Modal dialogs
        if st.session_state.get('show_patient_form', False):
            try:
                patient_entry_modal()
            except AttributeError:
                st.error("Modal dialogs require Streamlit 1.28+")
                st.session_state.show_patient_form = False
        
        if st.session_state.get('show_visit_form', False):
            try:
                visit_entry_modal()
            except AttributeError:
                st.error("Modal dialogs require Streamlit 1.28+")
                st.session_state.show_visit_form = False
        
        # Download buttons for added data
        if st.session_state.get('patient_added', False):
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                st.download_button(
                    "Download Updated Patients File",
                    data=st.session_state.updated_patients_file,
                    file_name=st.session_state.updated_filename,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
                if st.button("Done", use_container_width=True):
                    st.session_state.patient_added = False
                    st.rerun()
            st.info("Patient added! Download and re-upload to see changes.")
            st.divider()
        
        if st.session_state.get('visit_added', False):
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                st.download_button(
                    "Download Updated Visits File",
                    data=st.session_state.updated_visits_file,
                    file_name=st.session_state.updated_visits_filename,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
                if st.button("Done", use_container_width=True):
                    st.session_state.visit_added = False
                    st.rerun()
            st.info("Visit recorded! Download and re-upload to see changes.")
            st.divider()

        try:
            # Load and process files
            patients_df = normalize_columns(load_file(patients_file))
            trials_df = normalize_columns(load_file(trials_file))
            actual_visits_df = normalize_columns(load_file(actual_visits_file)) if actual_visits_file else None

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

            # Build calendar
            visits_df, calendar_df, stats, messages, site_column_mapping, unique_sites = build_calendar(
                patients_df, trials_df, actual_visits_df
            )
            
            # Extract screen failures
            screen_failures = {}
            if actual_visits_df is not None:
                screen_fail_visits = actual_visits_df[
                    actual_visits_df["Notes"].str.contains("ScreenFail", case=False, na=False)
                ]
                for _, visit in screen_fail_visits.iterrows():
                    patient_study_key = f"{visit['PatientID']}_{visit['Study']}"
                    screen_fail_date = visit['ActualDate']
                    if patient_study_key not in screen_failures or screen_fail_date < screen_failures[patient_study_key]:
                        screen_failures[patient_study_key] = screen_fail_date

            # Display processing messages
            if messages:
                with st.expander("Processing Log", expanded=False):
                    for message in messages:
                        st.write(message)

            # Site summary
            site_summary_df = extract_site_summary(patients_df, screen_failures)
            if not site_summary_df.empty:
                display_site_statistics(site_summary_df)

            # Main displays
            show_legend(actual_visits_df)
            display_calendar(calendar_df, site_column_mapping, unique_sites)
            display_financial_analysis(stats, visits_df)
            
            # Quarterly profit sharing
            financial_df = visits_df[
                (visits_df['Visit'].str.startswith("✅")) |
                (visits_df['Visit'].str.startswith("❌ Screen Fail")) |
                (visits_df['Visit'].str.contains('Visit', na=False) & (~visits_df.get('IsActual', False)))
            ].copy()
            
            if not financial_df.empty:
                # Add time columns for profit sharing
                financial_df['Quarter'] = financial_df['Date'].dt.quarter
                financial_df['Year'] = financial_df['Date'].dt.year
                financial_df['QuarterYear'] = financial_df['Year'].astype(str) + '-Q' + financial_df['Quarter'].astype(str)
                financial_df['FinancialYear'] = financial_df['Date'].apply(
                    lambda d: f"{d.year}-{d.year+1}" if d.month >= 4 else f"{d.year-1}-{d.year}"
                )
                
                display_quarterly_profit_sharing(financial_df, patients_df)

            # Site-wise monthly statistics
            st.subheader("Site-wise Statistics by Month")
            
            # Add month-year and financial year columns to visits_df
            visits_df['MonthYear'] = visits_df['Date'].dt.to_period('M')
            visits_df['FinancialYear'] = visits_df['Date'].apply(
                lambda d: f"{d.year}-{d.year+1}" if d.month >= 4 else f"{d.year-1}-{d.year}"
            )
            
            # Get the full date range for comprehensive monthly analysis
            min_date = visits_df['Date'].min()
            max_date = visits_df['Date'].max()
            all_months = pd.period_range(start=min_date, end=max_date, freq='M')
            
            monthly_site_stats = []
            
            # Process each month in the full range
            for month in all_months:
                month_visits = visits_df[visits_df['MonthYear'] == month]
                
                # Get financial year for this month
                sample_date = month.start_time
                fy = f"{sample_date.year}-{sample_date.year+1}" if sample_date.month >= 4 else f"{sample_date.year-1}-{sample_date.year}"
                
                for site in unique_sites:
                    # Get all patients from this site
                    site_patients = patients_df[patients_df["Site"] == site]
                    
                    # Get visits for patients from this site in this month
                    site_patient_ids = site_patients['PatientID'].unique()
                    site_visits = month_visits[month_visits["PatientID"].isin(site_patient_ids)]
                    
                    # Filter relevant visits (exclude tolerance periods)
                    relevant_visits = site_visits[
                        (site_visits["Visit"].str.startswith("✅")) | 
                        (site_visits["Visit"].str.startswith("❌ Screen Fail")) | 
                        (site_visits["Visit"].str.contains("Visit", na=False))
                    ]
                    
                    # Calculate metrics
                    site_income = relevant_visits["Payment"].sum()
                    completed_visits = len(relevant_visits[relevant_visits["Visit"].str.startswith("✅")])
                    screen_fail_visits = len(relevant_visits[relevant_visits["Visit"].str.startswith("❌ Screen Fail")])
                    total_visits = len(relevant_visits)
                    pending_visits = total_visits - completed_visits - screen_fail_visits
                    
                    # Count new patients recruited this month
                    month_start = month.start_time
                    month_end = month.end_time
                    
                    new_patients_this_month = len(site_patients[
                        (site_patients['StartDate'] >= month_start) & 
                        (site_patients['StartDate'] <= month_end)
                    ])
                    
                    # Only add rows where there's actual activity
                    if total_visits > 0 or new_patients_this_month > 0 or site_income > 0:
                        monthly_site_stats.append({
                            'Period': str(month),
                            'Financial Year': fy,
                            'Type': 'Month',
                            'Site': site,
                            'New Patients': new_patients_this_month,
                            'Completed Visits': completed_visits,
                            'Screen Fail Visits': screen_fail_visits,
                            'Pending Visits': pending_visits,
                            'Total Visits': total_visits,
                            'Income': f"£{site_income:,.2f}"
                        })
            
            # Add financial year summaries
            financial_years = sorted(visits_df['FinancialYear'].unique())
            for fy in financial_years:
                fy_visits = visits_df[visits_df['FinancialYear'] == fy]
                
                for site in unique_sites:
                    site_patients = patients_df[patients_df["Site"] == site]
                    site_patient_ids = site_patients['PatientID'].unique()
                    site_visits = fy_visits[fy_visits["PatientID"].isin(site_patient_ids)]
                    
                    relevant_visits = site_visits[
                        (site_visits["Visit"].str.startswith("✅")) | 
                        (site_visits["Visit"].str.startswith("❌ Screen Fail")) | 
                        (site_visits["Visit"].str.contains("Visit", na=False))
                    ]
                    
                    # Calculate annual metrics
                    site_income = relevant_visits["Payment"].sum()
                    completed_visits = len(relevant_visits[relevant_visits["Visit"].str.startswith("✅")])
                    screen_fail_visits = len(relevant_visits[relevant_visits["Visit"].str.startswith("❌ Screen Fail")])
                    total_visits = len(relevant_visits)
                    pending_visits = total_visits - completed_visits - screen_fail_visits
                    
                    # Count patients recruited in this financial year
                    fy_start_year = int(fy.split('-')[0])
                    fy_start = pd.Timestamp(f"{fy_start_year}-04-01")
                    fy_end = pd.Timestamp(f"{fy_start_year + 1}-03-31")
                    
                    fy_new_patients = len(site_patients[
                        (site_patients['StartDate'] >= fy_start) & 
                        (site_patients['StartDate'] <= fy_end)
                    ])
                    
                    # Count screen failures for this financial year
                    site_screen_fails = 0
                    for _, patient in site_patients.iterrows():
                        patient_study_key = f"{patient['PatientID']}_{patient['Study']}"
                        if patient_study_key in screen_failures:
                            screen_fail_date = screen_failures[patient_study_key]
                            if fy_start <= screen_fail_date <= fy_end:
                                site_screen_fails += 1
                    
                    active_patients = fy_new_patients - site_screen_fails
                    
                    monthly_site_stats.append({
                        'Period': f"FY {fy}",
                        'Financial Year': fy,
                        'Type': 'Financial Year',
                        'Site': site,
                        'New Patients': f"{fy_new_patients} ({max(0, active_patients)} active)",
                        'Completed Visits': completed_visits,
                        'Screen Fail Visits': screen_fail_visits,
                        'Pending Visits': pending_visits,
                        'Total Visits': total_visits,
                        'Income': f"£{site_income:,.2f}"
                    })
            
            if monthly_site_stats:
                # Sort and display by site
                monthly_site_stats.sort(key=lambda x: (x['Financial Year'], x['Type'] == 'Financial Year', x['Period'], x['Site']))
                
                for site in unique_sites:
                    st.write(f"**{site} Practice**")
                    
                    site_data = [stat for stat in monthly_site_stats if stat['Site'] == site]
                    if site_data:
                        site_df = pd.DataFrame(site_data)
                        display_df = site_df.drop('Site', axis=1)
                        
                        def highlight_fy_rows(row):
                            if row['Type'] == 'Financial Year':
                                return ['background-color: #e6f3ff; font-weight: bold'] * len(row)
                            else:
                                return [''] * len(row)
                        
                        styled_site_df = display_df.style.apply(highlight_fy_rows, axis=1)
                        st.dataframe(styled_site_df, use_container_width=True)
                        st.write("")
                    else:
                        st.write("No activity recorded for this site")
                        st.write("")
                
                st.info("""
                **Site Statistics Notes:**
                - **Blue highlighted rows** = Financial Year totals (April to March)
                - **New Patients** = Patients recruited in that period (based on StartDate)
                - **Income** = Clinical trial income generated from visits
                - Only months/periods with activity are shown
                - Financial year rows show annual totals and active patient counts
                """)

            # Monthly analysis by site
            st.subheader("Monthly Analysis by Site")
            
            # Filter only actual visits and main scheduled visits
            analysis_visits = visits_df[
                (visits_df['Visit'].str.startswith("✅")) |
                (visits_df['Visit'].str.startswith("❌ Screen Fail")) |
                (visits_df['Visit'].str.contains('Visit', na=False) & (~visits_df.get('IsActual', False)))
            ]
            
            if not analysis_visits.empty:
                # Analysis by Visit Location
                st.write("**Analysis by Visit Location (Where visits occur)**")
                visits_by_site_month = analysis_visits.groupby(['SiteofVisit', 'MonthYear']).size().reset_index(name='Visits')
                
                if not visits_by_site_month.empty:
                    visits_pivot = visits_by_site_month.pivot(index='MonthYear', columns='SiteofVisit', values='Visits').fillna(0)
                    visits_pivot['Total_Visits'] = visits_pivot.sum(axis=1)
                    visit_sites = [col for col in visits_pivot.columns if col != 'Total_Visits']
                    for site in visit_sites:
                        visits_pivot[f'{site}_Ratio'] = (visits_pivot[site] / visits_pivot['Total_Visits'] * 100).round(1)
                    
                    # Count unique patients by visit site per month
                    patients_by_visit_site_month = analysis_visits.groupby(['SiteofVisit', 'MonthYear'])['PatientID'].nunique().reset_index(name='Patients')
                    patients_visit_pivot = patients_by_visit_site_month.pivot(index='MonthYear', columns='SiteofVisit', values='Patients').fillna(0)
                    patients_visit_pivot['Total_Patients'] = patients_visit_pivot.sum(axis=1)
                    for site in visit_sites:
                        if site in patients_visit_pivot.columns:
                            patients_visit_pivot[f'{site}_Ratio'] = (patients_visit_pivot[site] / patients_visit_pivot['Total_Patients'] * 100).round(1)
                    
                    # Analysis by Patient Origin
                    st.write("**Analysis by Patient Origin (Where patients come from)**")
                    patients_by_origin_month = analysis_visits.groupby(['PatientOrigin', 'MonthYear'])['PatientID'].nunique().reset_index(name='Patients')
                    patients_origin_pivot = patients_by_origin_month.pivot(index='MonthYear', columns='PatientOrigin', values='Patients').fillna(0)
                    patients_origin_pivot['Total_Patients'] = patients_origin_pivot.sum(axis=1)
                    origin_sites = [col for col in patients_origin_pivot.columns if col != 'Total_Patients']
                    for site in origin_sites:
                        patients_origin_pivot[f'{site}_Ratio'] = (patients_origin_pivot[site] / patients_origin_pivot['Total_Patients'] * 100).round(1)
                    
                    # Display tables
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write("**Monthly Visits by Visit Site**")
                        visits_display = visits_pivot.copy()
                        visits_display.index = visits_display.index.astype(str)
                        
                        # Reorder columns
                        display_cols = []
                        for site in sorted(visit_sites):
                            display_cols.append(site)
                        for site in sorted(visit_sites):
                            ratio_col = f'{site}_Ratio'
                            if ratio_col in visits_display.columns:
                                display_cols.append(ratio_col)
                        display_cols.append('Total_Visits')
                        
                        visits_display = visits_display[display_cols]
                        st.dataframe(visits_display, use_container_width=True)
                    
                    with col2:
                        st.write("**Monthly Patients by Visit Site**")
                        patients_visit_display = patients_visit_pivot.copy()
                        patients_visit_display.index = patients_visit_display.index.astype(str)
                        
                        # Reorder columns
                        display_cols = []
                        for site in sorted(visit_sites):
                            if site in patients_visit_display.columns:
                                display_cols.append(site)
                        for site in sorted(visit_sites):
                            ratio_col = f'{site}_Ratio'
                            if ratio_col in patients_visit_display.columns:
                                display_cols.append(ratio_col)
                        display_cols.append('Total_Patients')
                        
                        patients_visit_display = patients_visit_display[display_cols]
                        st.dataframe(patients_visit_display, use_container_width=True)
                    
                    # Patient Origin Analysis
                    st.write("**Monthly Patients by Origin Site (Where patients come from)**")
                    patients_origin_display = patients_origin_pivot.copy()
                    patients_origin_display.index = patients_origin_display.index.astype(str)
                    
                    # Reorder columns
                    display_cols = []
                    for site in sorted(origin_sites):
                        display_cols.append(site)
                    for site in sorted(origin_sites):
                        ratio_col = f'{site}_Ratio'
                        if ratio_col in patients_origin_display.columns:
                            display_cols.append(ratio_col)
                    display_cols.append('Total_Patients')
                    
                    patients_origin_display = patients_origin_display[display_cols]
                    st.dataframe(patients_origin_display, use_container_width=True)
                    
                    # Cross-tabulation: Origin vs Visit Site
                    st.write("**Cross-Analysis: Patient Origin vs Visit Site**")
                    cross_tab = analysis_visits.groupby(['PatientOrigin', 'SiteofVisit'])['PatientID'].nunique().reset_index(name='Patients')
                    cross_pivot = cross_tab.pivot(index='PatientOrigin', columns='SiteofVisit', values='Patients').fillna(0)
                    cross_pivot['Total'] = cross_pivot.sum(axis=1)
                    
                    # Add row percentages
                    for col in cross_pivot.columns:
                        if col != 'Total':
                            cross_pivot[f'{col}_%'] = (cross_pivot[col] / cross_pivot['Total'] * 100).round(1)
                    
                    st.dataframe(cross_pivot, use_container_width=True)
                    
                    # Charts
                    st.subheader("Monthly Trends")
                    
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        st.write("**Visits by Visit Site**")
                        if not visits_pivot.empty:
                            chart_data = visits_pivot[[col for col in visits_pivot.columns if not col.endswith('_Ratio') and col != 'Total_Visits']]
                            chart_data.index = chart_data.index.astype(str)
                            st.bar_chart(chart_data)
                    
                    with col2:
                        st.write("**Patients by Visit Site**") 
                        if not patients_visit_pivot.empty:
                            chart_data = patients_visit_pivot[[col for col in patients_visit_pivot.columns if not col.endswith('_Ratio') and col != 'Total_Patients']]
                            chart_data.index = chart_data.index.astype(str)
                            st.bar_chart(chart_data)
                    
                    with col3:
                        st.write("**Patients by Origin Site**")
                        if not patients_origin_pivot.empty:
                            chart_data = patients_origin_pivot[[col for col in patients_origin_pivot.columns if not col.endswith('_Ratio') and col != 'Total_Patients']]
                            chart_data.index = chart_data.index.astype(str)
                            st.bar_chart(chart_data)

            # Download options
            display_download_buttons(calendar_df, site_column_mapping, unique_sites)

        except Exception as e:
            st.error(f"Error processing files: {e}")
            st.exception(e)

    else:
        st.info("Please upload both Patients and Trials files to get started.")
        
        st.markdown("""
        ### Expected File Structure:
        
        **Patients File:**
        - PatientID, Study, StartDate
        - Site/PatientPractice (optional - for patient origin)
        
        **Trials File:**
        - Study, Day, VisitNo, SiteforVisit
        - Income/Payment, ToleranceBefore, ToleranceAfter (optional)
        
        **Actual Visits File (Optional):**
        - PatientID, Study, VisitNo, ActualDate
        - ActualPayment, Notes (optional)
        - Use 'ScreenFail' in Notes to stop future visits
        """)

if __name__ == "__main__":
    main()
