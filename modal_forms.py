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
    
    # Duplicate checking logic
    def check_for_duplicates(patient_id, study, visit_name, actual_date, visits_df):
        """
        Check for duplicate visits based on PatientID + Study + VisitName + ActualDate
        
        Returns:
            tuple: (is_exact_duplicate, is_same_visit_different_date, existing_visit_info)
        """
        if visits_df is None or visits_df.empty:
            return False, False, None
        
        # Normalize date for comparison
        try:
            if isinstance(actual_date, str):
                normalized_date = pd.to_datetime(actual_date, dayfirst=True).date()
            else:
                normalized_date = actual_date.date() if hasattr(actual_date, 'date') else actual_date
        except:
            normalized_date = actual_date
        
        # Normalize existing dates in visits_df for comparison
        visits_df_copy = visits_df.copy()
        if 'ActualDate' in visits_df_copy.columns:
            visits_df_copy['ActualDate_normalized'] = pd.to_datetime(visits_df_copy['ActualDate'], dayfirst=True, errors='coerce').dt.date
        
        # Check for exact duplicate (same PatientID + Study + VisitName + ActualDate)
        exact_match = visits_df_copy[
            (visits_df_copy['PatientID'].astype(str) == str(patient_id)) &
            (visits_df_copy['Study'].astype(str) == str(study)) &
            (visits_df_copy['VisitName'].astype(str).str.strip().str.lower() == str(visit_name).strip().lower()) &
            (visits_df_copy['ActualDate_normalized'] == normalized_date)
        ]
        
        if not exact_match.empty:
            return True, False, exact_match.iloc[0]
        
        # Check for same visit on different date (same PatientID + Study + VisitName, different ActualDate)
        same_visit_different_date = visits_df_copy[
            (visits_df_copy['PatientID'].astype(str) == str(patient_id)) &
            (visits_df_copy['Study'].astype(str) == str(study)) &
            (visits_df_copy['VisitName'].astype(str).str.strip().str.lower() == str(visit_name).strip().lower()) &
            (visits_df_copy['ActualDate_normalized'] != normalized_date)
        ]
        
        if not same_visit_different_date.empty:
            return False, True, same_visit_different_date.iloc[0]
        
        return False, False, None

    # Validation and submission
    col_submit, col_cancel = st.columns([1, 1])
    
    with col_submit:
        if st.button("📝 Record Visit", type="primary", width='stretch'):
            # Format the visit date
            formatted_date = visit_date.strftime('%d/%m/%Y')
            
            # Check for duplicates before proceeding
            is_exact_duplicate, is_same_visit_different_date, existing_visit = check_for_duplicates(
                selected_patient_id, patient_study, selected_visit_name, formatted_date, visits_df
            )
            
            if is_exact_duplicate:
                st.error(f"❌ **Duplicate Visit Detected!**\n\n"
                        f"This exact visit already exists:\n"
                        f"- **Patient:** {existing_visit['PatientID']}\n"
                        f"- **Study:** {existing_visit['Study']}\n"
                        f"- **Visit:** {existing_visit['VisitName']}\n"
                        f"- **Date:** {existing_visit['ActualDate']}\n\n"
                        f"Please check your data and try again with a different date or visit.")
                return
            
            if is_same_visit_different_date:
                st.warning(f"⚠️ **Same Visit on Different Date Detected**\n\n"
                          f"This visit already exists on a different date:\n"
                          f"- **Patient:** {existing_visit['PatientID']}\n"
                          f"- **Study:** {existing_visit['Study']}\n"
                          f"- **Visit:** {existing_visit['VisitName']}\n"
                          f"- **Existing Date:** {existing_visit['ActualDate']}\n"
                          f"- **New Date:** {formatted_date}\n\n"
                          f"This might be legitimate (e.g., rescheduled visit).")
                
                # Add Force Add option
                col_force, col_cancel_force = st.columns([1, 1])
                with col_force:
                    force_add = st.button("✅ Force Add Visit", type="secondary", help="Add this visit even though a similar one exists")
                with col_cancel_force:
                    cancel_add = st.button("❌ Cancel", type="secondary")
                
                if cancel_add:
                    return
                elif not force_add:
                    return
            
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
                    success, message, code = db.append_visit_to_database(visit_df)
                    
                    if success:
                        st.success(f"Visit recorded successfully for patient {selected_patient_id}!")
                        log_activity(f"Recorded visit {selected_visit_name} for patient {selected_patient_id}", level='success')
                        
                        # Trigger data refresh
                        st.session_state.data_refresh_needed = True
                        st.session_state.show_visit_form = False
                        st.rerun()
                    else:
                        # Handle different error types
                        if code == 'DUPLICATE_FOUND':
                            st.error(f"❌ **Duplicate Visit Detected!**\n\n{message}\n\nPlease check your data and try again with a different date or visit.")
                        elif code == 'EMPTY_DATA':
                            st.error(f"❌ **No Data Provided**\n\n{message}")
                        elif code == 'NO_CLIENT':
                            st.error(f"❌ **Database Connection Error**\n\n{message}")
                        else:
                            st.error(f"❌ **Database Error**\n\n{message}")
                        log_activity(f"Failed to record visit: {message}", level='error')
                        
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

@st.dialog("📅 Record Study Event", width="large")
def study_event_entry_modal():
    """Modal dialog for recording actual SIV/Monitor events"""
    
    # Check if we're using database
    load_from_database = st.session_state.get('use_database', False)
    
    st.markdown("### Record Study Event (SIV/Monitor)")
    
    # Load required data based on mode
    if load_from_database:
        import database as db
        trial_schedule_df = db.fetch_all_trial_schedules()
        visits_df = db.fetch_all_actual_visits()
    else:
        trials_file = st.session_state.get('trials_file')
        actual_visits_file = st.session_state.get('actual_visits_file')
        
        if not trials_file:
            st.error("Trials file not available. Please upload files first.")
            if st.button("Close"):
                st.session_state.show_study_event_form = False
                st.rerun()
            return
        
        trial_schedule_df = load_file(trials_file)
        visits_df = load_file(actual_visits_file) if actual_visits_file else pd.DataFrame()
    
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
        
        event_type = st.selectbox(
            "Event Type*",
            options=["SIV", "Monitor"],
            help="Site Initiation Visit or Monitoring Visit"
        )
        
        event_name = st.text_input(
            "Event Name*",
            help="Enter the name of the event (e.g., 'Site Initiation Visit', 'Monitoring Visit 1')"
        )
    
    with col2:
        event_date = st.date_input(
            "Event Date*",
            value=date.today(),
            format="DD/MM/YYYY",
            help="Actual date when the event occurred"
        )
        
        status = st.selectbox(
            "Status*",
            options=["Completed", "Proposed", "Cancelled"],
            help="Status of the event"
        )
        
        site = st.selectbox(
            "Site*",
            options=["Ashfields", "Kiltearn"],
            help="Which site hosted this event"
        )
    
    notes = st.text_area(
        "Notes (Optional)",
        help="Any additional information about this event",
        height=80
    )
    
    # Duplicate checking logic for study events
    def check_study_event_duplicates(study, event_name, event_date, visits_df):
        """
        Check for duplicate study events based on Study + EventName + EventDate
        
        Returns:
            tuple: (is_exact_duplicate, existing_event_info)
        """
        if visits_df is None or visits_df.empty:
            return False, None
        
        # Normalize date for comparison
        try:
            if isinstance(event_date, str):
                normalized_date = pd.to_datetime(event_date, dayfirst=True).date()
            else:
                normalized_date = event_date.date() if hasattr(event_date, 'date') else event_date
        except:
            normalized_date = event_date
        
        # Normalize existing dates in visits_df for comparison
        visits_df_copy = visits_df.copy()
        if 'ActualDate' in visits_df_copy.columns:
            visits_df_copy['ActualDate_normalized'] = pd.to_datetime(visits_df_copy['ActualDate'], dayfirst=True, errors='coerce').dt.date
        
        # Check for exact duplicate (same Study + EventName + EventDate)
        # Only check study events (VisitType in ['siv', 'monitor'])
        study_events = visits_df_copy[
            visits_df_copy.get('VisitType', 'patient').isin(['siv', 'monitor'])
        ]
        
        exact_match = study_events[
            (study_events['Study'].astype(str) == str(study)) &
            (study_events['VisitName'].astype(str).str.strip().str.lower() == str(event_name).strip().lower()) &
            (study_events['ActualDate_normalized'] == normalized_date)
        ]
        
        if not exact_match.empty:
            return True, exact_match.iloc[0]
        
        return False, None
    
    # Validation and submission
    col_submit, col_cancel = st.columns([1, 1])
    
    with col_submit:
        if st.button("📅 Record Event", type="primary", width='stretch'):
            # Validate required fields
            if not event_name or not selected_study:
                st.error("Please fill in all required fields (Study and Event Name)")
                return
            
            # Format the event date
            formatted_date = event_date.strftime('%d/%m/%Y')
            
            # Check for duplicates before proceeding
            is_exact_duplicate, existing_event = check_study_event_duplicates(
                selected_study, event_name, formatted_date, visits_df
            )
            
            if is_exact_duplicate:
                st.error(f"❌ **Duplicate Event Detected!**\n\n"
                        f"This exact event already exists:\n"
                        f"- **Study:** {existing_event['Study']}\n"
                        f"- **Event:** {existing_event['VisitName']}\n"
                        f"- **Date:** {existing_event['ActualDate']}\n\n"
                        f"Please check your data and try again with a different date or event name.")
                return
            
            # Create pseudo-patient ID based on event type
            visit_type = event_type.lower()
            pseudo_patient_id = f"{event_type.upper()}_{selected_study}"
            
            # Create new study event data
            new_event = {
                'PatientID': pseudo_patient_id,
                'Study': selected_study,
                'VisitName': event_name,
                'ActualDate': formatted_date,
                'VisitType': visit_type,
                'Status': status.lower(),
                'Notes': notes if notes else ''
            }
            
            # Handle database or file mode
            if load_from_database:
                try:
                    import database as db
                    # Convert dict to DataFrame
                    event_df = pd.DataFrame([new_event])
                    success, message, code = db.append_visit_to_database(event_df)
                    
                    if success:
                        st.success(f"Study event '{event_name}' recorded successfully!")
                        log_activity(f"Recorded study event {event_name} for {selected_study}", level='success')
                        
                        # Trigger data refresh
                        st.session_state.data_refresh_needed = True
                        st.session_state.show_study_event_form = False
                        st.rerun()
                    else:
                        # Handle different error types
                        if code == 'DUPLICATE_FOUND':
                            st.error(f"❌ **Duplicate Event Detected!**\n\n{message}\n\nPlease check your data and try again.")
                        elif code == 'EMPTY_DATA':
                            st.error(f"❌ **No Data Provided**\n\n{message}")
                        elif code == 'NO_CLIENT':
                            st.error(f"❌ **Database Connection Error**\n\n{message}")
                        else:
                            st.error(f"❌ **Database Error**\n\n{message}")
                        log_activity(f"Failed to record study event: {message}", level='error')
                        
                except Exception as e:
                    st.error(f"Database error: {str(e)}")
                    log_activity(f"Database error recording study event: {str(e)}", level='error')
            else:
                # File mode - update session state and offer download
                st.session_state.new_study_event_data = new_event
                log_activity(f"Created new study event {event_name} for {selected_study}", level='success')
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
