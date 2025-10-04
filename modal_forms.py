import streamlit as st
import pandas as pd
import io
from datetime import date
from helpers import load_file, log_activity
import database as db

def handle_patient_modal():
    """Handle patient entry modal with compatibility check"""
    if st.session_state.get('show_patient_form', False):
        try:
            if hasattr(st, 'dialog'):
                patient_entry_modal()
            else:
                st.error("Modal dialogs require Streamlit 1.28+. Please upgrade Streamlit or use the form below.")
                patient_entry_inline_form()
        except Exception as e:
            st.error(f"Error displaying patient form: {e}")
            st.session_state.show_patient_form = False

def handle_visit_modal():
    """Handle visit entry modal with compatibility check"""
    if st.session_state.get('show_visit_form', False):
        try:
            if hasattr(st, 'dialog'):
                visit_entry_modal()
            else:
                st.error("Modal dialogs require Streamlit 1.28+. Please upgrade Streamlit or use the form below.")
                visit_entry_inline_form()
        except Exception as e:
            st.error(f"Error displaying visit form: {e}")
            st.session_state.show_visit_form = False

def handle_study_event_modal():
    """Handle study event management modal"""
    if st.session_state.get('show_study_event_form', False):
        try:
            if hasattr(st, 'dialog'):
                study_event_management_modal()
            else:
                st.error("Modal dialogs require Streamlit 1.28+")
                study_event_management_inline()
        except Exception as e:
            st.error(f"Error displaying study event form: {e}")
            st.session_state.show_study_event_form = False

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
        _render_patient_form(is_modal=True)
    
    patient_form()

def patient_entry_inline_form():
    """Inline form for adding patients (fallback)"""
    st.subheader("Add New Patient")
    _render_patient_form(is_modal=False)

def _render_patient_form(is_modal=True):
    """Render the patient form content - WORKS WITH BOTH DATABASE AND FILE MODES"""
    
    # Check mode
    use_database = st.session_state.get('use_database', False)
    
    # Load existing data based on mode
    if use_database:
        try:
            existing_patients = db.fetch_all_patients()
            existing_trials = db.fetch_all_trial_schedules()
            
            if existing_patients is None or existing_trials is None:
                st.error("Could not load data from database")
                return
        except Exception as e:
            st.error(f"Error loading from database: {e}")
            return
    else:
        # File mode
        patients_file = st.session_state.get('patients_file')
        trials_file = st.session_state.get('trials_file')
        
        if not patients_file or not trials_file:
            st.error("Files not available")
            return
        
        try:
            existing_patients = load_file(patients_file)
            existing_trials = load_file(trials_file)
            
            if existing_patients is None or existing_patients.empty:
                st.error("Could not load patients file or file is empty")
                return
            
            if existing_trials is None or existing_trials.empty:
                st.error("Could not load trials file or file is empty")
                return
                
            existing_patients.columns = [str(col).strip() for col in existing_patients.columns]
            existing_trials.columns = [str(col).strip() for col in existing_trials.columns]
        except Exception as e:
            st.error(f"Error loading files: {e}")
            return
    
    # Get available studies
    available_studies = sorted([str(s) for s in existing_trials["Study"].unique().tolist() if pd.notna(s)])
    
    # Main form fields
    new_patient_id = st.text_input("Patient ID")
    new_study = st.selectbox("Study", options=available_studies)
    
    # Date input
    col1, col2 = st.columns([1, 2])
    with col1:
        st.write("**Start Date:**")
    with col2:
        new_start_date = st.date_input("", value=date.today(), format="DD/MM/YYYY", key="patient_start_date")
    
    # Get existing sites
    patient_origin_col = None
    possible_origin_cols = ['PatientSite', 'OriginSite', 'Practice', 'PatientPractice', 'HomeSite', 'Site']
    for col in possible_origin_cols:
        if col in existing_patients.columns:
            patient_origin_col = col
            break
    
    # Site selection
    if patient_origin_col:
        existing_sites = sorted([str(s) for s in existing_patients[patient_origin_col].dropna().unique().tolist() if str(s) != 'nan'])
        if not existing_sites:
            existing_sites = ["Ashfields", "Kiltearn"]
        
        new_site = st.selectbox(f"Patient Site ({patient_origin_col})", options=existing_sites + ["Add New..."])
        if new_site == "Add New...":
            new_site = st.text_input("Enter New Site Name")
    else:
        st.info("No patient site column found in your data. Will use 'PatientPractice' column.")
        new_site = st.text_input("Patient Site", value="Ashfields")
        patient_origin_col = "PatientPractice"
    
    # Validation
    validation_errors = []
    if new_patient_id and str(new_patient_id) in existing_patients["PatientID"].astype(str).values:
        validation_errors.append("Patient ID already exists")
    if new_start_date and new_start_date > date.today():
        validation_errors.append("Start date cannot be in future")
    if not new_patient_id:
        validation_errors.append("Patient ID is required")
    if not new_study:
        validation_errors.append("Study selection is required")
    if not new_site or new_site == "Add New...":
        validation_errors.append("Site selection is required")
    
    # Validate study has Day 1 visit
    if new_study:
        study_visits = existing_trials[existing_trials["Study"] == new_study]
        day_1_visits = study_visits[study_visits["Day"] == 1]
        if len(day_1_visits) == 0:
            validation_errors.append(f"Study {new_study} has no Day 1 visit defined")
        elif len(day_1_visits) > 1:
            validation_errors.append(f"Study {new_study} has multiple Day 1 visits - only one allowed")
    
    if validation_errors:
        for error in validation_errors:
            st.error(error)
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Add Patient", disabled=bool(validation_errors), use_container_width=True):
            # Create new patient record
            new_patient_data = {
                "PatientID": str(new_patient_id),
                "Study": str(new_study),
                "StartDate": new_start_date,
            }
            
            if patient_origin_col:
                new_patient_data[patient_origin_col] = str(new_site)
            else:
                new_patient_data["PatientPractice"] = str(new_site)
            
            # Add other columns with safe defaults
            for col in existing_patients.columns:
                if col not in new_patient_data:
                    new_patient_data[col] = ""
            
            new_row_df = pd.DataFrame([new_patient_data])
            
            # Save based on mode
            if use_database:
                # DATABASE MODE - Direct append
                success = db.append_patient_to_database(new_row_df)
                
                if success:
                    st.success(f"✅ Patient {new_patient_id} added to database!")
                    st.session_state.data_refresh_needed = True
                    st.session_state.show_patient_form = False
                    log_activity(f"Added patient {new_patient_id} to study {new_study} in database", level='success')
                    st.rerun()
                else:
                    st.error("Failed to add patient to database")
            else:
                # FILE MODE - Create download
                updated_patients_df = pd.concat([existing_patients, new_row_df], ignore_index=True)
                
                output = io.BytesIO()
                try:
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        updated_patients_df.to_excel(writer, index=False, sheet_name="Patients")
                except ImportError:
                    updated_patients_df.to_csv(output, index=False)
                
                st.session_state.updated_patients_file = output.getvalue()
                st.session_state.updated_filename = f"Patients_Updated_{new_start_date.strftime('%Y%m%d')}.xlsx"
                st.session_state.patient_added = True
                st.session_state.show_patient_form = False
                
                st.toast(f"Added patient {new_patient_id} to study {new_study}", icon="✅")
                log_activity(f"Added patient {new_patient_id} to study {new_study}", level='success')
                st.rerun()
    
    with col2:
        if st.button("Cancel", use_container_width=True):
            st.session_state.show_patient_form = False
            st.rerun()

def visit_entry_modal():
    """Modal for recording visits"""
    @st.dialog("Record Visit")
    def visit_form():
        _render_visit_form(is_modal=True)
    
    visit_form()

def visit_entry_inline_form():
    """Inline form for recording visits (fallback)"""
    st.subheader("Record Visit")
    _render_visit_form(is_modal=False)

def _render_visit_form(is_modal=True):
    """Render the visit form content - WORKS WITH BOTH DATABASE AND FILE MODES"""
    
    # Check mode
    use_database = st.session_state.get('use_database', False)
    
    # Load data based on mode
    if use_database:
        try:
            existing_patients = db.fetch_all_patients()
            existing_trials = db.fetch_all_trial_schedules()
            existing_visits = db.fetch_all_actual_visits()
            
            if existing_patients is None or existing_trials is None:
                st.error("Could not load data from database")
                return
            
            if existing_visits is None:
                existing_visits = pd.DataFrame()
        except Exception as e:
            st.error(f"Error loading from database: {e}")
            return
    else:
        # File mode
        patients_file = st.session_state.get('patients_file')
        trials_file = st.session_state.get('trials_file')
        actual_visits_file = st.session_state.get('actual_visits_file')
        
        if not patients_file or not trials_file:
            st.error("Files not available")
            return
        
        try:
            existing_patients = load_file(patients_file)
            existing_trials = load_file(trials_file)
            
            if existing_patients is None or existing_patients.empty:
                st.error("Could not load patients file or file is empty")
                return
            
            if existing_trials is None or existing_trials.empty:
                st.error("Could not load trials file or file is empty")
                return
                
            existing_patients.columns = [str(col).strip() for col in existing_patients.columns]
            existing_trials.columns = [str(col).strip() for col in existing_trials.columns]
            
            # Load existing visits
            existing_visits = pd.DataFrame()
            if actual_visits_file:
                existing_visits = load_file(actual_visits_file)
                existing_visits.columns = [str(col).strip() for col in existing_visits.columns]
        except Exception as e:
            st.error(f"Error loading files: {e}")
            return
    
    # Patient selection
    patient_options = []
    for _, patient in existing_patients.iterrows():
        patient_id = str(patient['PatientID'])
        study = str(patient['Study'])
        patient_options.append(f"{patient_id} ({study})")
    
    if not patient_options:
        st.error("No patients available")
        return
    
    selected_patient = st.selectbox("Select Patient", options=patient_options)
    
    if selected_patient:
        # Extract patient ID and study
        try:
            patient_info = selected_patient.split(" (")
            patient_id = patient_info[0]
            study = patient_info[1].rstrip(")")
        except (IndexError, AttributeError):
            st.error("Error parsing patient selection")
            return
        
        # Get available visits for this study
        study_visits = existing_trials[existing_trials["Study"] == study].sort_values('Day')
        visit_options = []
        for _, visit in study_visits.iterrows():
            day = visit['Day']
            visit_name = str(visit['VisitName'])
            visit_options.append(f"{visit_name} (Day {day})")
        
        if not visit_options:
            st.error(f"No visits defined for study {study}")
            return
        
        selected_visit = st.selectbox("Visit", options=visit_options)
        
        if selected_visit:
            # Extract visit name
            try:
                visit_name = selected_visit.split(" (Day ")[0]
            except (IndexError, AttributeError):
                visit_name = selected_visit
            
            # UK date format
            visit_date = st.date_input("Visit Date", format="DD/MM/YYYY")
            
            # Notes only - no payment field
            notes = st.text_area("Notes (Optional)", help="Use 'ScreenFail' to mark screen failures")
            
            # Validation
            validation_errors = []
            if visit_date > date.today():
                validation_errors.append("Visit date cannot be in future")
            
            # Check for duplicates
            if len(existing_visits) > 0:
                duplicate_visit = existing_visits[
                    (existing_visits["PatientID"].astype(str) == str(patient_id)) &
                    (existing_visits["Study"] == study) &
                    (existing_visits["VisitName"].astype(str) == str(visit_name))
                ]
                if len(duplicate_visit) > 0:
                    validation_errors.append(f"Visit '{visit_name}' for patient {patient_id} already recorded")
            
            if validation_errors:
                for error in validation_errors:
                    st.error(error)
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Record Visit", disabled=bool(validation_errors), use_container_width=True):
                    # Create new visit record
                    new_visit_data = {
                        "PatientID": str(patient_id),
                        "Study": str(study),
                        "VisitName": str(visit_name),
                        "ActualDate": visit_date,
                        "Notes": str(notes or "")
                    }
                    
                    new_visit_df = pd.DataFrame([new_visit_data])
                    
                    # Save based on mode
                    if use_database:
                        # DATABASE MODE - Direct append
                        success = db.append_visit_to_database(new_visit_df)
                        
                        if success:
                            st.success(f"✅ Visit {visit_name} recorded for {patient_id}!")
                            st.session_state.data_refresh_needed = True
                            st.session_state.show_visit_form = False
                            log_activity(f"Recorded visit {visit_name} for patient {patient_id} in database", level='success')
                            st.rerun()
                        else:
                            st.error("Failed to record visit in database")
                    else:
                        # FILE MODE - Create download
                        if len(existing_visits) > 0:
                            updated_visits_df = pd.concat([existing_visits, new_visit_df], ignore_index=True)
                        else:
                            # Create new visits file with proper columns
                            columns = ["PatientID", "Study", "VisitName", "ActualDate", "Notes"]
                            updated_visits_df = pd.DataFrame([new_visit_data])
                            for col in columns:
                                if col not in updated_visits_df.columns:
                                    updated_visits_df[col] = ""
                        
                        output = io.BytesIO()
                        try:
                            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                                updated_visits_df.to_excel(writer, index=False, sheet_name="ActualVisits")
                        except ImportError:
                            updated_visits_df.to_csv(output, index=False)
                        
                        st.session_state.updated_visits_file = output.getvalue()
                        st.session_state.updated_visits_filename = f"ActualVisits_Updated_{visit_date.strftime('%Y%m%d')}.xlsx"
                        st.session_state.visit_added = True
                        st.session_state.show_visit_form = False
                        
                        st.toast(f"Recorded visit {visit_name} for patient {patient_id}", icon="✅")
                        log_activity(f"Recorded visit {visit_name} for patient {patient_id}", level='success')
                        st.rerun()
            
            with col2:
                if st.button("Cancel", use_container_width=True):
                    st.session_state.show_visit_form = False
                    st.rerun()

def study_event_management_modal():
    """Modal for managing study events"""
    @st.dialog("Study Event Management")
    def study_event_form():
        _render_study_event_form(is_modal=True)
    
    study_event_form()

def study_event_management_inline():
    """Inline study event management (fallback)"""
    st.subheader("Study Event Management")
    _render_study_event_form(is_modal=False)

def _render_study_event_form(is_modal=True):
    """Form for managing study events (SIV, Monitor) - SIMPLIFIED VERSION"""
    st.info("Study event management coming soon. For now, please manage study events through file uploads.")
    
    if st.button("Close", use_container_width=True):
        st.session_state.show_study_event_form = False
        st.rerun()

def show_patient_download():
    """Show patient download section (FILE MODE ONLY)"""
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        filename = st.session_state.get('updated_filename', 'Patients_Updated.xlsx')
        file_data = st.session_state.get('updated_patients_file')
        
        if file_data:
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
    """Show visit download section (FILE MODE ONLY)"""
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        filename = st.session_state.get('updated_visits_filename', 'ActualVisits_Updated.xlsx')
        file_data = st.session_state.get('updated_visits_file')
        
        if file_data:
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
