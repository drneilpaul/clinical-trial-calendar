import streamlit as st
import pandas as pd
import io
from datetime import date
from helpers import load_file

def handle_patient_modal():
    """Handle patient entry modal"""
    if st.session_state.get('show_patient_form', False):
        try:
            patient_entry_modal()
        except AttributeError:
            st.error("Modal dialogs require Streamlit 1.28+")
            st.session_state.show_patient_form = False

def handle_visit_modal():
    """Handle visit entry modal"""
    if st.session_state.get('show_visit_form', False):
        try:
            visit_entry_modal()
        except AttributeError:
            st.error("Modal dialogs require Streamlit 1.28+")
            st.session_state.show_visit_form = False

def show_download_sections():
    """Show download sections for added patients/visits"""
    if st.session_state.get('patient_added', False):
        show_patient_download()
    
    if st.session_state.get('visit_added', False):
        show_visit_download()

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

def show_patient_download():
    """Show patient download section"""
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

def show_visit_download():
    """Show visit download section"""
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
