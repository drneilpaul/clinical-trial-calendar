import streamlit as st
import pandas as pd
import io
from datetime import date, timedelta
from helpers import load_file, normalize_columns, parse_dates_column
from processing_calendar import build_calendar
from display_components import (
    show_legend, display_calendar, display_financial_tables,
    display_site_statistics, display_quarterly_profit_sharing, 
    display_download_buttons, display_site_wise_monthly_analysis,
    display_monthly_analysis_by_site
)

# Initialize session state variables
if 'show_patient_form' not in st.session_state:
    st.session_state.show_patient_form = False
if 'show_visit_form' not in st.session_state:
    st.session_state.show_visit_form = False
if 'patient_added' not in st.session_state:
    st.session_state.patient_added = False
if 'visit_added' not in st.session_state:
    st.session_state.visit_added = False

def extract_site_summary(patients_df, screen_failures=None):
    """Extract site summary statistics from patients dataframe"""
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

def patient_entry_modal():
    """Modal dialog for adding new patients"""
    @st.dialog("Add New Patient")
    def patient_entry_form():
        # Load existing data for validation
        patients_file = st.session_state.get('patients_file')
        trials_file = st.session_state.get('trials_file')
        
        if not patients_file or not trials_file:
            st.error("Files not available")
            return
            
        existing_patients = load_file(patients_file)
        existing_patients.columns = existing_patients.columns.str.strip()
        
        existing_trials = load_file(trials_file)
        existing_trials.columns = existing_trials.columns.str.strip()
        
        # Get available studies and sites
        available_studies = sorted(existing_trials["Study"].unique().tolist())
        
        # Get existing patient practices/sites
        patient_origin_col = None
        possible_origin_cols = ['PatientSite', 'OriginSite', 'Practice', 'PatientPractice', 'HomeSite', 'Site']
        for col in possible_origin_cols:
            if col in existing_patients.columns:
                patient_origin_col = col
                break
        
        if patient_origin_col:
            existing_sites = sorted(existing_patients[patient_origin_col].dropna().unique().tolist())
        else:
            existing_sites = ["Ashfields", "Kiltearn"]

        # Form fields
        new_patient_id = st.text_input("Patient ID", help="Enter unique patient identifier")
        new_study = st.selectbox("Study", options=available_studies, help="Select study from trials file")
        new_start_date = st.date_input("Start Date", help="Patient study start date")
        
        if patient_origin_col:
            new_site = st.selectbox(f"{patient_origin_col}", options=existing_sites + ["Add New..."], 
                                  help="Select patient origin site")
            if new_site == "Add New...":
                new_site = st.text_input("New Site Name", help="Enter new site name")
        else:
            new_site = st.text_input("Patient Site", help="Enter patient origin site")
        
        # Validation
        validation_errors = []
        
        if new_patient_id:
            if new_patient_id in existing_patients["PatientID"].astype(str).values:
                validation_errors.append(f"Patient ID '{new_patient_id}' already exists")
            
            if not new_patient_id.replace("-", "").replace("_", "").isalnum():
                validation_errors.append("Patient ID should contain only letters, numbers, hyphens, or underscores")
        
        if new_study and new_study not in available_studies:
            validation_errors.append(f"Study '{new_study}' not found in trials file")
            
        if new_start_date:
            if new_start_date > date.today():
                validation_errors.append("Start date is in the future")
            elif (date.today() - new_start_date).days > 365*3:
                validation_errors.append("Start date is more than 3 years ago")
        
        # Show validation results
        if validation_errors:
            st.error("Please fix the following issues:")
            for error in validation_errors:
                st.write(f"• {error}")
        elif new_patient_id and new_study and new_start_date and new_site:
            st.success("Patient data is valid")
            
            # Show preview
            st.write("**Preview of new patient:**")
            preview_data = {
                "PatientID": [new_patient_id],
                "Study": [new_study], 
                "StartDate": [new_start_date.strftime('%Y-%m-%d')],
                (patient_origin_col or "PatientPractice"): [new_site]
            }
            preview_df = pd.DataFrame(preview_data)
            st.dataframe(preview_df, use_container_width=True)
        
        # Action buttons
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Add Patient", 
                        disabled=bool(validation_errors) or not all([new_patient_id, new_study, new_start_date, new_site]),
                        use_container_width=True):
                
                # Match existing data types
                processed_patient_id = new_patient_id
                existing_patient_ids = existing_patients["PatientID"]
                
                if existing_patient_ids.dtype in ['int64', 'float64'] or all(pd.to_numeric(existing_patient_ids, errors='coerce').notna()):
                    try:
                        processed_patient_id = int(new_patient_id) if new_patient_id.isdigit() else float(new_patient_id)
                    except:
                        processed_patient_id = new_patient_id
                
                # Create new patient record
                new_patient_data = {
                    "PatientID": processed_patient_id,
                    "Study": new_study,
                    "StartDate": new_start_date,
                }
                
                if patient_origin_col:
                    new_patient_data[patient_origin_col] = new_site
                else:
                    new_patient_data["PatientPractice"] = new_site
                
                # Add other columns with appropriate default values
                for col in existing_patients.columns:
                    if col not in new_patient_data:
                        if len(existing_patients[col].dropna()) > 0:
                            sample_value = existing_patients[col].dropna().iloc[0]
                            if isinstance(sample_value, (int, float)):
                                new_patient_data[col] = 0 if isinstance(sample_value, int) else 0.0
                            else:
                                new_patient_data[col] = ""
                        else:
                            new_patient_data[col] = ""
                
                # Add to existing dataframe
                new_row_df = pd.DataFrame([new_patient_data])
                updated_patients_df = pd.concat([existing_patients, new_row_df], ignore_index=True)
                
                # Create download
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    updated_patients_df.to_excel(writer, index=False, sheet_name="Patients")
                
                # Store in session state for download
                st.session_state.updated_patients_file = output.getvalue()
                st.session_state.updated_filename = f"Patients_Updated_{new_start_date.strftime('%Y%m%d')}.xlsx"
                st.session_state.patient_added = True
                st.session_state.show_patient_form = False
                
                st.success(f"Patient {new_patient_id} added successfully!")
                st.rerun()
        
        with col2:
            if st.button("Cancel", use_container_width=True):
                st.session_state.show_patient_form = False
                st.rerun()
    
    patient_entry_form()

def visit_entry_modal():
    """Modal dialog for recording visits"""
    @st.dialog("Record Visit")
    def visit_entry_form():
        # Load existing data
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
        
        # Load existing actual visits if file exists
        existing_visits = pd.DataFrame()
        if actual_visits_file:
            existing_visits = load_file(actual_visits_file)
            existing_visits.columns = existing_visits.columns.str.strip()
        
        # Get available patients and studies
        patient_options = []
        for _, patient in existing_patients.iterrows():
            patient_options.append(f"{patient['PatientID']} ({patient['Study']})")
        
        # Form fields
        selected_patient = st.selectbox("Select Patient", options=patient_options, help="Choose patient who attended visit")
        
        if selected_patient:
            # Extract patient ID and study from selection
            patient_info = selected_patient.split(" (")
            patient_id = patient_info[0]
            study = patient_info[1].rstrip(")")
            
            # Get available visits for this study
            study_visits = existing_trials[existing_trials["Study"] == study]
            visit_options = []
            for _, visit in study_visits.iterrows():
                visit_options.append(f"Visit {visit['VisitNo']} (Day {visit['Day']})")
            
            selected_visit = st.selectbox("Visit Number", options=visit_options, help="Select which visit was completed")
            
            if selected_visit:
                # Extract visit number
                visit_no = selected_visit.split(" ")[1].split(" ")[0]
                
                visit_date = st.date_input("Visit Date", help="Date the visit was completed")
                
                # Get payment amount from trials data
                visit_payment = existing_trials[
                    (existing_trials["Study"] == study) & 
                    (existing_trials["VisitNo"].astype(str) == visit_no)
                ]
                default_payment = visit_payment["Payment"].iloc[0] if len(visit_payment) > 0 and "Payment" in visit_payment.columns else 0
                
                actual_payment = st.number_input("Payment Amount", value=float(default_payment), min_value=0.0, help="Payment for this visit")
                
                notes = st.text_area("Notes (Optional)", help="Any notes about the visit. Use 'ScreenFail' to stop future visits")
                
                # Validation
                validation_errors = []
                
                if visit_date > date.today():
                    validation_errors.append("Visit date cannot be in the future")
                
                # Check if visit already recorded
                if len(existing_visits) > 0:
                    duplicate_visit = existing_visits[
                        (existing_visits["PatientID"].astype(str) == str(patient_id)) &
                        (existing_visits["Study"] == study) &
                        (existing_visits["VisitNo"].astype(str) == visit_no)
                    ]
                    if len(duplicate_visit) > 0:
                        validation_errors.append(f"Visit {visit_no} for patient {patient_id} already recorded")
                
                # Show validation results
                if validation_errors:
                    st.error("Please fix the following issues:")
                    for error in validation_errors:
                        st.write(f"• {error}")
                elif visit_date:
                    st.success("Visit data is valid")
                    
                    # Show preview
                    st.write("**Preview of visit record:**")
                    preview_data = {
                        "PatientID": [patient_id],
                        "Study": [study],
                        "VisitNo": [visit_no],
                        "ActualDate": [visit_date.strftime('%Y-%m-%d')],
                        "ActualPayment": [actual_payment],
                        "Notes": [notes or ""]
                    }
                    preview_df = pd.DataFrame(preview_data)
                    st.dataframe(preview_df, use_container_width=True)
                
                # Action buttons
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("✅ Record Visit", 
                                disabled=bool(validation_errors) or not visit_date,
                                use_container_width=True):
                        
                        # Match data types from existing visits file
                        processed_patient_id = patient_id
                        processed_visit_no = visit_no
                        
                        if len(existing_visits) > 0:
                            # Match PatientID data type
                            if existing_visits["PatientID"].dtype in ['int64', 'float64']:
                                try:
                                    processed_patient_id = int(patient_id) if str(patient_id).isdigit() else float(patient_id)
                                except:
                                    processed_patient_id = patient_id
                            
                            # Match VisitNo data type
                            if existing_visits["VisitNo"].dtype in ['int64', 'float64']:
                                try:
                                    processed_visit_no = int(visit_no)
                                except:
                                    processed_visit_no = visit_no
                        
                        # Create new visit record
                        new_visit_data = {
                            "PatientID": processed_patient_id,
                            "Study": study,
                            "VisitNo": processed_visit_no,
                            "ActualDate": visit_date,
                            "ActualPayment": actual_payment,
                            "Notes": notes or ""
                        }
                        
                        # Add to existing visits or create new dataframe
                        if len(existing_visits) > 0:
                            new_visit_df = pd.DataFrame([new_visit_data])
                            updated_visits_df = pd.concat([existing_visits, new_visit_df], ignore_index=True)
                        else:
                            updated_visits_df = pd.DataFrame([new_visit_data])
                        
                        # Create download
                        output = io.BytesIO()
                        with pd.ExcelWriter(output, engine='openpyxl') as writer:
                            updated_visits_df.to_excel(writer, index=False, sheet_name="ActualVisits")
                        
                        # Store in session state for download
                        st.session_state.updated_visits_file = output.getvalue()
                        st.session_state.updated_visits_filename = f"ActualVisits_Updated_{visit_date.strftime('%Y%m%d')}.xlsx"
                        st.session_state.visit_added = True
                        st.session_state.show_visit_form = False
                        
                        st.success(f"Visit {visit_no} for patient {patient_id} recorded successfully!")
                        st.rerun()
                
                with col2:
                    if st.button("❌ Cancel", use_container_width=True):
                        st.session_state.show_visit_form = False
                        st.rerun()
    
    visit_entry_form()

def main():
    st.set_page_config(page_title="Clinical Trial Calendar Generator", layout="wide")
    st.title("🏥 Clinical Trial Calendar Generator")
    st.caption("v2.2.2 | Fixed: Date formatting for weekends, month ends, and financial year ends")

    st.sidebar.header("📁 Upload Data Files")
    patients_file
