import streamlit as st
import pandas as pd
import io
from datetime import date, datetime, timedelta
from helpers import load_file, log_activity

def calculate_day_1_date(entered_date, study, trial_schedule_df):
    """
    Calculate Day 1 date from screening date based on trial schedule.
    
    Args:
        entered_date: The date entered by user (screening date)
        study: Selected study name
        trial_schedule_df: Trial schedule DataFrame
    
    Returns:
        tuple: (adjusted_date, offset_days, screening_day_found)
    """
    # Filter trial schedule for selected study
    study_visits = trial_schedule_df[trial_schedule_df['Study'] == study].copy()
    
    if study_visits.empty:
        return entered_date, 0, False
    
    # Find screening visits (negative day numbers)
    screening_visits = study_visits[study_visits['Day'] < 1]
    
    if screening_visits.empty:
        # No screening visits defined - use entered date as-is
        return entered_date, 0, False
    
    # Get the earliest screening day (most negative)
    screening_day = screening_visits['Day'].min()
    
    # Calculate offset: Day 1 - Screening Day
    # e.g., if screening is Day -23, offset = 1 - (-23) = 24
    offset_days = int(1 - screening_day)
    
    # Calculate adjusted date
    # Convert date to datetime for timedelta operations
    if isinstance(entered_date, date) and not isinstance(entered_date, datetime):
        entered_datetime = datetime.combine(entered_date, datetime.min.time())
    else:
        entered_datetime = entered_date
    
    adjusted_date = entered_datetime + timedelta(days=offset_days)
    
    # Return as date object for consistency with input
    if isinstance(entered_date, date) and not isinstance(entered_date, datetime):
        adjusted_date = adjusted_date.date()
    
    return adjusted_date, offset_days, True

def handle_patient_modal():
    """Handle patient entry modal"""
    if st.session_state.get('show_patient_form', False) and not st.session_state.get('any_dialog_open', False):
        try:
            st.session_state.any_dialog_open = True
            patient_entry_modal()
        except AttributeError:
            st.error("Modal dialogs require Streamlit 1.28+")
            st.session_state.show_patient_form = False
        except Exception as e:
            st.error(f"Error opening patient form: {e}")
            st.session_state.show_patient_form = False
        finally:
            st.session_state.any_dialog_open = False

def handle_visit_modal():
    """Handle visit entry modal"""
    if st.session_state.get('show_visit_form', False) and not st.session_state.get('any_dialog_open', False):
        try:
            st.session_state.any_dialog_open = True
            visit_entry_modal()
        except AttributeError:
            st.error("Modal dialogs require Streamlit 1.28+")
            st.session_state.show_visit_form = False
        except Exception as e:
            st.error(f"Error opening visit form: {e}")
            st.session_state.show_visit_form = False
        finally:
            st.session_state.any_dialog_open = False

def handle_study_event_modal():
    """Handle study event entry modal"""
    if st.session_state.get('show_study_event_form', False) and not st.session_state.get('any_dialog_open', False):
        try:
            st.session_state.any_dialog_open = True
            study_event_entry_modal()
        except AttributeError:
            st.error("Modal dialogs require Streamlit 1.28+")
            st.session_state.show_study_event_form = False
        except Exception as e:
            st.error(f"Error opening study event form: {e}")
            st.session_state.show_study_event_form = False
        finally:
            st.session_state.any_dialog_open = False

def show_download_sections():
    """Show download sections for added patients/visits"""
    if st.session_state.get('new_patient_data'):
        st.success("✅ New patient added successfully!")
        _show_patient_download()
        
    if st.session_state.get('new_visit_data'):
        st.success("✅ New visit recorded successfully!")
        _show_visit_download()
    
    if st.session_state.get('new_study_event_data'):
        st.success("✅ Study event added successfully!")
        _show_study_event_download()

def _show_patient_download():
    """Display download section for new patient"""
    patient_data = st.session_state.new_patient_data
    
    st.subheader("📥 Download New Patient Data")
    
    df = pd.DataFrame([patient_data])
    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer, index=False)
    
    col1, col2 = st.columns([3, 1])
    with col1:
        st.info(f"Patient ID: {patient_data['PatientID']} | Study: {patient_data['Study']}")
    with col2:
        st.download_button(
            label="⬇️ Download CSV",
            data=csv_buffer.getvalue(),
            file_name=f"new_patient_{patient_data['PatientID']}.csv",
            mime="text/csv",
            key="download_patient"
        )
    
    if st.button("✖ Clear", key="clear_patient"):
        del st.session_state.new_patient_data
        st.rerun()

def _show_visit_download():
    """Display download section for new visit"""
    visit_data = st.session_state.new_visit_data
    
    st.subheader("📥 Download New Visit Data")
    
    df = pd.DataFrame([visit_data])
    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer, index=False)
    
    col1, col2 = st.columns([3, 1])
    with col1:
        st.info(f"Patient: {visit_data['PatientID']} | Visit: {visit_data['VisitName']} | Date: {visit_data['ActualDate']}")
    with col2:
        st.download_button(
            label="⬇️ Download CSV",
            data=csv_buffer.getvalue(),
            file_name=f"new_visit_{visit_data['PatientID']}_{visit_data['VisitName']}.csv",
            mime="text/csv",
            key="download_visit"
        )
    
    if st.button("✖ Clear", key="clear_visit"):
        del st.session_state.new_visit_data
        st.rerun()

def _show_study_event_download():
    """Display download section for new study event"""
    event_data = st.session_state.new_study_event_data
    
    st.subheader("📥 Download New Study Event Data")
    
    df = pd.DataFrame([event_data])
    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer, index=False)
    
    col1, col2 = st.columns([3, 1])
    with col1:
        st.info(f"Study: {event_data['Study']} | Visit: {event_data['VisitName']} | Day: {event_data['Day']}")
    with col2:
        st.download_button(
            label="⬇️ Download CSV",
            data=csv_buffer.getvalue(),
            file_name=f"new_study_event_{event_data['Study']}_{event_data['VisitName']}.csv",
            mime="text/csv",
            key="download_study_event"
        )
    
    if st.button("✖ Clear", key="clear_study_event"):
        del st.session_state.new_study_event_data
        st.rerun()

@st.dialog("➕ Add New Patient", width="large")
def patient_entry_modal():
    """Modal dialog for adding new patients"""
    
    # Check if we're using database
    load_from_database = st.session_state.get('use_database', False)
    
    st.markdown("### Enter New Patient Information")
    
    # Load required data based on mode
    if load_from_database:
        import database as db
        patients_df = db.fetch_all_patients()
        trial_schedule_df = db.fetch_all_trial_schedules()
    else:
        patients_file = st.session_state.get('patients_file')
        trials_file = st.session_state.get('trials_file')
        
        if not patients_file or not trials_file:
            st.error("Files not available. Please upload files first.")
            if st.button("Close"):
                st.session_state.show_patient_form = False
                st.rerun()
            return
        
        patients_df = load_file(patients_file)
        trial_schedule_df = load_file(trials_file)
    
    if patients_df is None or patients_df.empty or trial_schedule_df is None or trial_schedule_df.empty:
        st.error("Unable to load required data files. Please check Patients and TrialSchedule files.")
        if st.button("Close"):
            st.session_state.show_patient_form = False
            st.rerun()
        return
    
    # Get unique studies from trial schedule
    available_studies = sorted(trial_schedule_df['Study'].unique().tolist())
    
    # Form inputs
    col1, col2 = st.columns(2)
    
    with col1:
        new_patient_id = st.text_input(
            "Patient ID*",
            help="Enter a unique patient identifier"
        )
        
        selected_study = st.selectbox(
            "Study*",
            options=available_studies,
            help="Select the study this patient is enrolled in"
        )
    
    with col2:
        # Check if selected study has screening visits
        has_screening_visits = False
        if selected_study:
            study_visits = trial_schedule_df[trial_schedule_df['Study'] == selected_study]
            screening_visits = study_visits[study_visits['Day'] < 1]
            has_screening_visits = not screening_visits.empty
        
        # Date type selection - only show screening option if screening visits exist
        if has_screening_visits:
            date_type = st.radio(
                "Date Type*",
                ["Screening Date", "Randomization Date (Day 1)"],
                help="Screening = pre-study visit, Randomization = study start (Day 1)"
            )
        else:
            # No screening visits - only show randomization option
            date_type = "Randomization Date (Day 1)"
            st.info("ℹ️ **This study has no screening visits defined.** Date will be used as Day 1 baseline.")
            st.write("**Date Type:** Randomization Date (Day 1)")
        
        start_date = st.date_input(
            "Start Date*",
            value=date.today(),
            format="DD/MM/YYYY",
            help="Enter the actual date of the visit selected above"
        )
        
        recruitment_site = st.selectbox(
            "Recruited By*",
            options=["Ashfields", "Kiltearn"],
            help="Which practice recruited this patient?"
        )
    
    # Show calculated information
    if selected_study and start_date:
        # Calculate Day 1 date if screening is selected
        if date_type == "Screening Date" and has_screening_visits:
            adjusted_date, offset_days, screening_found = calculate_day_1_date(
                start_date, selected_study, trial_schedule_df
            )
            
            if screening_found:
                st.info(f"📅 **Calculated Day 1 Date:** {adjusted_date.strftime('%d/%m/%Y')} "
                       f"(Screening + {offset_days} days)")
            else:
                st.warning("⚠️ **No screening visits defined** for this study. "
                          "Date will be used as Day 1 baseline.")
                adjusted_date = start_date
        else:
            # Randomization Date or no screening visits
            adjusted_date = start_date
            st.info(f"📅 **Day 1 Date:** {adjusted_date.strftime('%d/%m/%Y')}")
    else:
        adjusted_date = start_date
    
    # Validation and submission
    col_submit, col_cancel = st.columns([1, 1])
    
    with col_submit:
        if st.button("➕ Add Patient", type="primary", width='stretch'):
            # Validate required fields
            if not new_patient_id or not selected_study:
                st.error("Please fill in all required fields (Patient ID and Study)")
                return
            
            # Check for duplicate patient ID
            if new_patient_id in patients_df['PatientID'].values:
                st.error(f"Patient ID '{new_patient_id}' already exists!")
                return
            
            # Calculate the final date to use as baseline
            if date_type == "Screening Date" and has_screening_visits:
                final_date, offset_days, screening_found = calculate_day_1_date(
                    start_date, selected_study, trial_schedule_df
                )
                if not screening_found:
                    final_date = start_date
            else:
                # Randomization Date or no screening visits
                final_date = start_date
            
            # Format the final date
            formatted_date = final_date.strftime('%d/%m/%Y')
            
            # Create new patient data
            new_patient = {
                'PatientID': new_patient_id,
                'Study': selected_study,
                'StartDate': formatted_date,
                'Site': recruitment_site,  # Which practice recruited them
                # OriginSite column removed - using PatientPractice only
                'PatientPractice': recruitment_site  # Same value, for compatibility
            }
            
            # Handle database or file mode
            if load_from_database:
                try:
                    import database as db
                    # Convert dict to DataFrame
                    patient_df = pd.DataFrame([new_patient])
                    success = db.append_patient_to_database(patient_df)
                    
                    if success:
                        st.success(f"Patient {new_patient_id} added to database successfully!")
                        log_activity(f"Added patient {new_patient_id} to database", level='success')
                        
                        # Trigger data refresh
                        st.session_state.data_refresh_needed = True
                        st.session_state.show_patient_form = False
                        st.rerun()
                    else:
                        st.error(f"Failed to add patient to database")
                        log_activity(f"Failed to add patient {new_patient_id}", level='error')
                        
                except Exception as e:
                    st.error(f"Database error: {str(e)}")
                    log_activity(f"Database error adding patient: {str(e)}", level='error')
            else:
                # File mode - update session state and offer download
                st.session_state.new_patient_data = new_patient
                log_activity(f"Created new patient record for {new_patient_id}", level='success')
                st.session_state.show_patient_form = False
                st.rerun()
    
    with col_cancel:
        if st.button("✖ Cancel", width='stretch'):
            st.session_state.show_patient_form = False
            st.rerun()

@st.dialog("📝 Record Visit", width="large")
def visit_entry_modal():
    """Modal dialog for recording patient visits"""
    
    # Check if we're using database
    load_from_database = st.session_state.get('use_database', False)
    
    st.markdown("### Record Patient Visit")
    
    # Load required data based on mode
    if load_from_database:
        import database as db
        patients_df = db.fetch_all_patients()
        trial_schedule_df = db.fetch_all_trial_schedules()
        visits_df = db.fetch_all_actual_visits()
    else:
        patients_file = st.session_state.get('patients_file')
        trials_file = st.session_state.get('trials_file')
        actual_visits_file = st.session_state.get('actual_visits_file')
        
        if not patients_file or not trials_file:
            st.error("Files not available. Please upload files first.")
            if st.button("Close"):
                st.session_state.show_visit_form = False
                st.rerun()
            return
        
        patients_df = load_file(patients_file)
        trial_schedule_df = load_file(trials_file)
        visits_df = load_file(actual_visits_file) if actual_visits_file else pd.DataFrame()
    
    if patients_df is None or patients_df.empty or trial_schedule_df is None or trial_schedule_df.empty:
        st.error("Unable to load required data files.")
        if st.button("Close"):
            st.session_state.show_visit_form = False
            st.rerun()
        return
    
    # Create patient selection options
    patient_options = [
        f"{row['PatientID']} ({row['Study']})"
        for _, row in patients_df.iterrows()
    ]
    
    if not patient_options:
        st.warning("No patients available. Please add a patient first.")
        if st.button("Close"):
            st.session_state.show_visit_form = False
            st.rerun()
        return
    
    # Form inputs
    col1, col2 = st.columns(2)
    
    with col1:
        selected_patient_display = st.selectbox(
            "Select Patient*",
            options=patient_options,
            help="Choose the patient for this visit"
        )
        
        # Extract patient ID from display string
        selected_patient_id = selected_patient_display.split(' (')[0]
        
        # Get patient's study
        patient_study = patients_df[patients_df['PatientID'] == selected_patient_id]['Study'].iloc[0]
        
        # Filter visits for this study
        study_visits = trial_schedule_df[trial_schedule_df['Study'] == patient_study].copy()
        
        # Create visit options with day information
        visit_options = [
            f"{row['VisitName']} (Day {row['Day']})"
            for _, row in study_visits.iterrows()
        ]
        
        selected_visit_display = st.selectbox(
            "Visit*",
            options=visit_options,
            help="Select the visit type"
        )
        
        # Extract visit name
        selected_visit_name = selected_visit_display.split(' (Day')[0]
    
    with col2:
        visit_date = st.date_input(
            "Visit Date*",
            value=date.today(),
            format="DD/MM/YYYY",
            help="Actual date of the visit"
        )
        
        notes = st.text_area(
            "Notes (Optional)",
            help="Any additional notes about this visit",
            height=100
        )
    
    # Validation and submission
    col_submit, col_cancel = st.columns([1, 1])
    
    with col_submit:
        if st.button("📝 Record Visit", type="primary", width='stretch'):
            # Format the visit date
            formatted_date = visit_date.strftime('%d/%m/%Y')
            
            # Get visit details from trial schedule
            visit_details = study_visits[study_visits['VisitName'] == selected_visit_name].iloc[0]
            
            # Create new visit data
            new_visit = {
                'PatientID': selected_patient_id,
                'Study': patient_study,
                'VisitName': selected_visit_name,
                'ActualDate': formatted_date,
                'Day': int(visit_details['Day']),
                'Notes': notes if notes else ''
            }
            
            # Handle database or file mode
            if load_from_database:
                try:
                    import database as db
                    # Convert dict to DataFrame
                    visit_df = pd.DataFrame([new_visit])
                    success = db.append_visit_to_database(visit_df)
                    
                    if success:
                        st.success(f"Visit recorded successfully for patient {selected_patient_id}!")
                        log_activity(f"Recorded visit {selected_visit_name} for patient {selected_patient_id}", level='success')
                        
                        # Trigger data refresh
                        st.session_state.data_refresh_needed = True
                        st.session_state.show_visit_form = False
                        st.rerun()
                    else:
                        st.error(f"Failed to record visit to database")
                        log_activity(f"Failed to record visit", level='error')
                        
                except Exception as e:
                    st.error(f"Database error: {str(e)}")
                    log_activity(f"Database error recording visit: {str(e)}", level='error')
            else:
                # File mode - update session state and offer download
                st.session_state.new_visit_data = new_visit
                log_activity(f"Created new visit record for {selected_patient_id}", level='success')
                st.session_state.show_visit_form = False
                st.rerun()
    
    with col_cancel:
        if st.button("✖ Cancel", width='stretch'):
            st.session_state.show_visit_form = False
            st.rerun()

@st.dialog("📅 Add Study Event", width="large")
def study_event_entry_modal():
    """Modal dialog for adding new study events to trial schedule"""
    
    # Check if we're using database
    load_from_database = st.session_state.get('use_database', False)
    
    st.markdown("### Add New Study Event to Trial Schedule")
    
    # Load required data based on mode
    if load_from_database:
        import database as db
        trial_schedule_df = db.fetch_all_trial_schedules()
    else:
        trials_file = st.session_state.get('trials_file')
        
        if not trials_file:
            st.error("Trials file not available. Please upload files first.")
            if st.button("Close"):
                st.session_state.show_study_event_form = False
                st.rerun()
            return
        
        trial_schedule_df = load_file(trials_file)
    
    if trial_schedule_df is None or trial_schedule_df.empty:
        st.error("Unable to load Trial Schedule data.")
        if st.button("Close"):
            st.session_state.show_study_event_form = False
            st.rerun()
        return
    
    # Get unique studies
    available_studies = sorted(trial_schedule_df['Study'].unique().tolist())
    
    # Form inputs
    col1, col2 = st.columns(2)
    
    with col1:
        selected_study = st.selectbox(
            "Study*",
            options=available_studies,
            help="Select the study for this event"
        )
        
        visit_name = st.text_input(
            "Visit Name*",
            help="Enter the name of the visit/event (e.g., 'Follow-up 1')"
        )
    
    with col2:
        day = st.number_input(
            "Day*",
            min_value=-365,
            max_value=365,
            value=0,
            help="Day relative to study start (negative for screening, positive for follow-up)"
        )
        
        event_type = st.selectbox(
            "Event Type",
            options=["Visit", "Assessment", "Follow-up", "Screening", "Other"],
            help="Optional: Type of event"
        )
    
    notes = st.text_area(
        "Notes (Optional)",
        help="Any additional information about this event",
        height=80
    )
    
    # Validation and submission
    col_submit, col_cancel = st.columns([1, 1])
    
    with col_submit:
        if st.button("📅 Add Event", type="primary", width='stretch'):
            # Validate required fields
            if not visit_name or not selected_study:
                st.error("Please fill in all required fields (Study and Visit Name)")
                return
            
            # Check for duplicate event
            existing_events = trial_schedule_df[
                (trial_schedule_df['Study'] == selected_study) &
                (trial_schedule_df['VisitName'] == visit_name)
            ]
            
            if not existing_events.empty:
                st.error(f"Event '{visit_name}' already exists for study '{selected_study}'!")
                return
            
            # Create new study event data
            new_event = {
                'Study': selected_study,
                'VisitName': visit_name,
                'Day': int(day),
                'EventType': event_type,
                'Notes': notes if notes else ''
            }
            
            # Handle database or file mode
            if load_from_database:
                try:
                    import database as db
                    # Convert dict to DataFrame
                    event_df = pd.DataFrame([new_event])
                    success = db.append_trial_schedule_to_database(event_df)
                    
                    if success:
                        st.success(f"Study event '{visit_name}' added successfully!")
                        log_activity(f"Added study event {visit_name} to {selected_study}", level='success')
                        
                        # Trigger data refresh
                        st.session_state.data_refresh_needed = True
                        st.session_state.show_study_event_form = False
                        st.rerun()
                    else:
                        st.error(f"Failed to add study event to database")
                        log_activity(f"Failed to add study event", level='error')
                        
                except Exception as e:
                    st.error(f"Database error: {str(e)}")
                    log_activity(f"Database error adding study event: {str(e)}", level='error')
            else:
                # File mode - update session state and offer download
                st.session_state.new_study_event_data = new_event
                log_activity(f"Created new study event {visit_name} for {selected_study}", level='success')
                st.session_state.show_study_event_form = False
                st.rerun()
    
    with col_cancel:
        if st.button("✖ Cancel", width='stretch'):
            st.session_state.show_study_event_form = False
            st.rerun()

def open_patient_form():
    """Helper function to open patient entry form"""
    st.session_state.show_patient_form = True

def open_visit_form():
    """Helper function to open visit entry form"""
    st.session_state.show_visit_form = True

def open_study_event_form():
    """Helper function to open study event entry form"""
    st.session_state.show_study_event_form = True
