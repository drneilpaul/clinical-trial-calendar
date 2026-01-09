import streamlit as st
import pandas as pd
import io
from datetime import date, datetime, timedelta
from helpers import load_file, log_activity, get_visit_type_series, trigger_data_refresh
import database as db

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

def handle_switch_patient_modal():
    """Handle switch patient study modal"""
    if st.session_state.get('show_switch_patient_form', False) and not st.session_state.get('any_dialog_open', False):
        try:
            st.session_state.any_dialog_open = True
            switch_patient_study_modal()
        except AttributeError:
            st.error("Modal dialogs require Streamlit 1.28+")
            st.session_state.show_switch_patient_form = False
        except Exception as e:
            st.error(f"Error opening switch patient form: {e}")
            st.session_state.show_switch_patient_form = False
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
    
    if isinstance(visit_data, list):
        visit_records = visit_data
    else:
        visit_records = [visit_data]
    
    df = pd.DataFrame(visit_records)
    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer, index=False)
    
    col1, col2 = st.columns([3, 1])
    with col1:
        primary_visit = visit_records[0]
        extras_summary = [
            record['VisitName']
            for record in visit_records[1:]
            if record.get('VisitType') == 'extra'
        ]
        info_text = (
            f"Patient: {primary_visit['PatientID']} | Visit: {primary_visit['VisitName']} "
            f"| Date: {primary_visit['ActualDate']}"
        )
        if extras_summary:
            info_text += f" | Extras: {', '.join(extras_summary)}"
        st.info(info_text)
    with col2:
        st.download_button(
            label="⬇️ Download CSV",
            data=csv_buffer.getvalue(),
            file_name=f"new_visit_{visit_records[0]['PatientID']}_{visit_records[0]['VisitName']}.csv",
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
        st.markdown("**Patient ID***")
        new_patient_id = st.text_input(
            "Patient ID*",
            help="Enter a unique patient identifier",
            label_visibility="collapsed"
        )
        
        st.markdown("**Study***")
        selected_study = st.selectbox(
            "Study*",
            options=available_studies,
            help="Select the study this patient is enrolled in",
            label_visibility="collapsed"
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
        
        st.markdown("**Recruited By***")
        recruitment_site = st.selectbox(
            "Recruited By*",
            options=["Ashfields", "Kiltearn"],
            help="Which practice recruited this patient?",
            label_visibility="collapsed"
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
                        trigger_data_refresh()
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

@st.dialog("📝 Record Patient Visit", width="large")
def visit_entry_modal():
    """Modal dialog for recording patient visits"""
    
    # Check if we're using database
    load_from_database = st.session_state.get('use_database', False)
    
    st.markdown("### Record Patient Visit")
    st.caption("ℹ️ **Patient Visits**: Includes all scheduled visits (V1-V21, Screening, Randomisation) and Day 0 visits (Unscheduled, V1.1, Extra Visits). These appear in the patient's column on the calendar.")
    
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
    
    # OPTIMIZED: Use itertuples for faster iteration (2-3x faster than iterrows)
    patient_options = [
        f"{row.PatientID} ({row.Study})"
        for row in patients_df.itertuples(index=False)
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
        st.markdown("**Select Patient***")
        selected_patient_display = st.selectbox(
            "Select Patient*",
            options=patient_options,
            help="Choose the patient for this visit",
            label_visibility="collapsed"
        )
        
        # Extract patient ID from display string
        selected_patient_id = selected_patient_display.split(' (')[0]
        
        # Get patient's study
        patient_study = patients_df[patients_df['PatientID'] == selected_patient_id]['Study'].iloc[0]
        
        # Filter visits for this study
        study_visits = trial_schedule_df[trial_schedule_df['Study'] == patient_study].copy()
        
        if study_visits.empty:
            st.error(f"No visits defined for study {patient_study}.")
            if st.button("Close"):
                st.session_state.show_visit_form = False
                st.rerun()
            return
        
        # Normalize visit types for easier filtering
        visit_type_series = get_visit_type_series(study_visits, default='patient')
        study_visits = study_visits.assign(_VisitType=visit_type_series)
        
        # Split primary visits (scheduled patient visits) and optional extras
        primary_visits_df = study_visits[~study_visits['_VisitType'].isin(['siv', 'monitor', 'extra'])].copy()
        extras_df = study_visits[study_visits['_VisitType'] == 'extra'].copy()
        
        primary_visits_df = primary_visits_df.sort_values(by=['Day', 'VisitName']).reset_index(drop=True)
        extras_df = extras_df.sort_values(by=['VisitName']).reset_index(drop=True)
        
        # Determine which visits already have actual records
        if visits_df is not None and not visits_df.empty:
            patient_actuals_existing = visits_df[
                (visits_df['PatientID'].astype(str) == selected_patient_id) &
                (visits_df['Study'].astype(str) == patient_study)
            ].copy()
            patient_actuals_existing['_VisitType'] = get_visit_type_series(
                patient_actuals_existing, default='patient'
            )
        else:
            patient_actuals_existing = pd.DataFrame(columns=['VisitName', '_VisitType'])
        
        completed_visit_names = set(
            patient_actuals_existing.loc[
                patient_actuals_existing['_VisitType'].isin(['patient', '']),
                'VisitName'
            ].astype(str).str.strip().str.lower()
        )
        extras_completed_names = set(
            patient_actuals_existing.loc[
                patient_actuals_existing['_VisitType'] == 'extra',
                'VisitName'
            ].astype(str).str.strip().str.lower()
        )
        
        pending_visits_df = primary_visits_df[
            ~primary_visits_df['VisitName'].astype(str).str.strip().str.lower().isin(completed_visit_names)
        ].copy()
        
        if pending_visits_df.empty and not primary_visits_df.empty:
            st.info("ℹ️ All scheduled visits have recorded actuals. Showing full visit list.")
            selection_visits_df = primary_visits_df.copy()
        else:
            selection_visits_df = pending_visits_df.reset_index(drop=True)
        
        if selection_visits_df.empty:
            st.error("No visits available to record for this patient.")
            if st.button("Close"):
                st.session_state.show_visit_form = False
                st.rerun()
            return
        
        visit_choice_records = []
        # OPTIMIZED: Use itertuples for faster iteration (2-3x faster than iterrows)
        for visit_row in selection_visits_df.itertuples(index=False):
            visit_name = str(visit_row.VisitName)
            visit_day = getattr(visit_row, 'Day', '')
            label = f"{visit_name} (Day {visit_day})"
            if visit_name.strip().lower() in completed_visit_names:
                label += " – already recorded"
            visit_choice_records.append(
                {
                    "label": label,
                    "value": visit_name,
                    "day": visit_day
                }
            )
        
        visit_choice_indices = list(range(len(visit_choice_records)))
        default_index = 0
        
        st.markdown("**Visit***")
        selected_visit_index = st.selectbox(
            "Visit*",
            options=visit_choice_indices,
            index=default_index if default_index < len(visit_choice_indices) else 0,
            format_func=lambda idx: visit_choice_records[idx]["label"],
            help="Select the visit to record",
            label_visibility="collapsed"
        )
        selected_visit_name = visit_choice_records[selected_visit_index]["value"]
        
        # Extras selection – optional Day 0 add-ons
        selected_extra_names = []
        available_extras_df = extras_df[
            ~extras_df['VisitName'].astype(str).str.strip().str.lower().isin(extras_completed_names)
        ].copy()
        
        if not extras_df.empty:
            st.markdown("**Optional extras**")
            if available_extras_df.empty:
                st.caption("All extras have already been recorded for this patient.")
            else:
                extra_options = list(available_extras_df['VisitName'])
                extra_label_map = {}
                # OPTIMIZED: Use itertuples for faster iteration (2-3x faster than iterrows)
                for extra_row in available_extras_df.itertuples(index=False):
                    extra_name = str(extra_row.VisitName)
                    payment = getattr(extra_row, 'Payment', 0)
                    try:
                        payment_value = float(payment)
                        payment_text = f"+£{payment_value:,.2f}" if payment_value else "+£0.00"
                    except (TypeError, ValueError):
                        payment_text = "+£0.00"
                    extra_label_map[extra_name] = f"{extra_name} ({payment_text})"
                
                selected_extra_names = st.multiselect(
                    "Extras performed (optional)",
                    options=extra_options,
                    format_func=lambda name: extra_label_map.get(name, name),
                    help="Tick any additional activities completed at the same visit"
                )
    
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
        withdrawn_flag = st.checkbox(
            "Withdrawn – stop future visits",
            help="Tick to mark the patient as withdrawn. This will stop all future scheduled visits.")
        
        died_flag = st.checkbox(
            "Has Died – stop future visits",
            help="Tick to mark the patient as deceased. This will stop all future scheduled visits (Day >= 1). Day 0 extras after death still count.")
    
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
            # Validate that SIV/Monitor aren't being recorded as patient visits
            if selected_visit_name.upper() in ['SIV'] or 'MONITOR' in selected_visit_name.upper():
                st.error("⚠️ **SIV and Monitor are site-wide events, not patient visits.**\n\n"
                         "Please use the **'Record Site Event'** button instead.\n\n"
                         "This button is for patient-specific visits only.")
                return
            
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
            
            primary_visit_type = str(visit_details.get('VisitType', 'patient')).strip().lower()
            if primary_visit_type in ['', 'nan', 'none']:
                primary_visit_type = 'patient'
            
            # Auto-detect proposed visit if date is in the future
            from datetime import date
            today = date.today()
            visit_date_obj = visit_date if isinstance(visit_date, date) else pd.to_datetime(visit_date).date()
            is_future_date = visit_date_obj > today
            
            # Set VisitType to patient_proposed if future date (unless already a special type)
            if is_future_date and primary_visit_type == 'patient':
                primary_visit_type = 'patient_proposed'
                st.info(f"📅 This visit will be marked as **Proposed** since the date ({formatted_date}) is in the future.")
            
            # Ensure Notes includes 'Withdrawn' if checkbox selected
            final_notes = notes if notes else ''
            if withdrawn_flag and 'Withdrawn' not in final_notes:
                final_notes = (final_notes + ('; ' if final_notes else '') + 'Withdrawn').strip()
            
            # Ensure Notes includes 'Died' if checkbox selected
            if died_flag and 'Died' not in final_notes:
                final_notes = (final_notes + ('; ' if final_notes else '') + 'Died').strip()

            # Create new visit data
            new_visit = {
                'PatientID': selected_patient_id,
                'Study': patient_study,
                'VisitName': selected_visit_name,
                'ActualDate': formatted_date,
                'Day': int(visit_details.get('Day', 0)),
                'Notes': final_notes,
                'VisitType': primary_visit_type
            }
            
            # Build extra visit records (if any selected)
            extra_visits_data = []
            for extra_name in selected_extra_names:
                extra_row_match = extras_df[extras_df['VisitName'] == extra_name]
                if extra_row_match.empty:
                    continue
                extra_row = extra_row_match.iloc[0]
                
                is_dup_extra, is_same_extra_diff, existing_extra = check_for_duplicates(
                    selected_patient_id, patient_study, extra_name, formatted_date, visits_df
                )
                
                if is_dup_extra:
                    st.warning(
                        f"Extra '{extra_name}' already exists on {existing_extra['ActualDate']} - skipping duplicate."
                    )
                    continue
                if is_same_extra_diff:
                    st.warning(
                        f"Extra '{extra_name}' already exists on a different date "
                        f"({existing_extra['ActualDate']}). Skipping duplicate entry."
                    )
                    continue
                
                extra_visits_data.append({
                    'PatientID': selected_patient_id,
                    'Study': patient_study,
                    'VisitName': extra_name,
                    'ActualDate': formatted_date,
                    'Day': int(extra_row.get('Day', 0)),
                    'Notes': final_notes,
                    'VisitType': 'extra'
                })
            
            all_new_visits = [new_visit] + extra_visits_data
            
            # Handle database or file mode
            if load_from_database:
                try:
                    import database as db
                    # Convert dict to DataFrame
                    visit_df = pd.DataFrame(all_new_visits)
                    success, message, code = db.append_visit_to_database(visit_df)
                    
                    if success:
                        success_msg = f"Visit recorded successfully for patient {selected_patient_id}!"
                        if extra_visits_data:
                            success_msg += f" ({len(extra_visits_data)} extra{'s' if len(extra_visits_data) != 1 else ''} added)"
                        st.success(success_msg)
                        log_activity(
                            f"Recorded visit {selected_visit_name} for patient {selected_patient_id} "
                            f"with {len(extra_visits_data)} extras",
                            level='success'
                        )
                        
                        # Trigger data refresh
                        trigger_data_refresh()
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
                st.session_state.new_visit_data = all_new_visits
                log_activity(
                    f"Created new visit record for {selected_patient_id} "
                    f"with {len(extra_visits_data)} extras",
                    level='success'
                )
                st.session_state.show_visit_form = False
                st.rerun()
    
    with col_cancel:
        if st.button("✖ Cancel", width='stretch'):
            st.session_state.show_visit_form = False
            st.rerun()

@st.dialog("📅 Record Site Event (SIV/Monitor)", width="large")
def study_event_entry_modal():
    """Modal dialog for recording actual SIV/Monitor events"""
    
    # Check if we're using database
    load_from_database = st.session_state.get('use_database', False)
    
    st.markdown("### Record Site Event (SIV/Monitor)")
    st.caption("ℹ️ **Site Events**: Site-wide events that appear in the Events column. Event Name automatically matches Event Type (SIV or Monitor).")
    st.caption("ℹ️ For patient-specific visits (V1.1, Unscheduled, Extra Visit), use 'Record Patient Visit' button")
    
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
        st.markdown("**Study***")
        selected_study = st.selectbox(
            "Study*",
            options=available_studies,
            help="Select the study for this event",
            label_visibility="collapsed"
        )
        
        st.markdown("**Event Type***")
        event_type = st.selectbox(
            "Event Type*",
            options=["SIV", "Monitor"],
            help="Site Initiation Visit or Monitoring Visit. Event Name will automatically match the selected type.",
            label_visibility="collapsed"
        )
        
        # Auto-populate Event Name from Event Type
        event_name = event_type  # SIV -> "SIV", Monitor -> "Monitor"
        
        st.markdown("**Event Name***")
        st.text_input(
            "Event Name*",
            value=event_name,
            disabled=True,
            help="Automatically set to match Event Type. Site-wide events only (SIV, Monitor). For patient visits like V1.1 or Unscheduled, use 'Record Patient Visit' button.",
            label_visibility="collapsed"
        )
    
    with col2:
        event_date = st.date_input(
            "Event Date*",
            value=date.today(),
            format="DD/MM/YYYY",
            help="Actual date when the event occurred"
        )
        
        st.markdown("**Status***")
        status = st.selectbox(
            "Status*",
            options=["Completed", "Proposed", "Cancelled"],
            help="Status of the event",
            label_visibility="collapsed"
        )
        
        st.markdown("**Site***")
        site = st.selectbox(
            "Site*",
            options=["Ashfields", "Kiltearn"],
            help="Which site hosted this event",
            label_visibility="collapsed"
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
            
            # Auto-detect proposed event if date is in the future or status is "Proposed"
            from datetime import date
            today = date.today()
            event_date_obj = event_date if isinstance(event_date, date) else pd.to_datetime(event_date).date()
            is_future_date = event_date_obj > today
            is_proposed_status = status.lower() == 'proposed'
            
            # Set VisitType to event_proposed if future date or status is Proposed
            if is_future_date or is_proposed_status:
                visit_type = 'event_proposed'
                if is_future_date:
                    st.info(f"📅 This event will be marked as **Proposed** since the date ({formatted_date}) is in the future.")
                elif is_proposed_status:
                    st.info(f"📅 This event is marked as **Proposed** based on the selected status.")
            
            # Create new study event data
            new_event = {
                'PatientID': pseudo_patient_id,
                'Study': selected_study,
                'VisitName': event_name,
                'ActualDate': formatted_date,
                'VisitType': visit_type,
                'Status': status.lower(),
                'Notes': notes if notes else '',
                'SiteforVisit': site  # Include site so it can be used during processing
            }
            
            # Handle database or file mode
            if load_from_database:
                try:
                    import database as db
                    # Convert dict to DataFrame
                    event_df = pd.DataFrame([new_event])
                    success, message, code = db.append_visit_to_database(event_df)
                    
                    if success:
                        # Automatically create/update trial_schedules template for this SIV/Monitor
                        # This ensures the event will display properly on the calendar
                        # Event Name is always "SIV" or "Monitor" (matches Event Type)
                        try:
                            # Determine underlying event type for template (siv or monitor, not event_proposed)
                            template_event_type = event_type.lower()  # Use original event_type, not visit_type
                            template_df = pd.DataFrame([{
                                'Study': selected_study,
                                'Day': 0 if template_event_type == 'siv' else 999,  # SIVs use Day 0, Monitors use 999
                                'VisitName': event_name,  # Always "SIV" or "Monitor" (matches Event Type)
                                'SiteforVisit': site,
                                'Payment': 0,  # Default to 0, can be updated later
                                'ToleranceBefore': 0,
                                'ToleranceAfter': 0,
                                'VisitType': template_event_type  # Use underlying type for template
                            }])
                            
                            # Try to append the template (will fail silently if duplicate exists, which is fine)
                            db.append_trial_schedule_to_database(template_df)
                            log_activity(f"Created/updated trial schedule template for {event_name} ({selected_study}) at {site}", level='info')
                        except Exception as template_error:
                            # Template might already exist - that's okay
                            log_activity(f"Note: Trial schedule template for {event_name} may already exist: {template_error}", level='info')
                        
                        st.success(f"Study event '{event_name}' recorded successfully!")
                        log_activity(f"Recorded study event {event_name} for {selected_study}", level='success')
                        
                        # Trigger data refresh
                        trigger_data_refresh()
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

def open_switch_patient_form():
    """Helper function to open switch patient study form"""
    st.session_state.show_switch_patient_form = True

def handle_study_settings_modal():
    """Handle study settings (status/targets) modal"""
    if st.session_state.get('show_study_settings_form', False) and not st.session_state.get('any_dialog_open', False):
        try:
            st.session_state.any_dialog_open = True
            study_settings_modal()
        except AttributeError:
            st.error("Modal dialogs require Streamlit 1.28+")
            st.session_state.show_study_settings_form = False
        except Exception as e:
            st.error(f"Error opening study settings form: {e}")
            st.session_state.show_study_settings_form = False
        finally:
            st.session_state.any_dialog_open = False

def open_study_settings_form():
    """Open study settings form"""
    st.session_state.show_study_settings_form = True

@st.dialog("⚙️ Study Settings (Status & Recruitment)", width="large")
def study_settings_modal():
    """Modal form to edit study status and recruitment targets"""
    try:
        # Load data
        trials_df = db.fetch_all_trial_schedules()
        if trials_df is None or trials_df.empty:
            st.error("No trial schedules found. Please upload trials data first.")
            if st.button("✖ Close", width='stretch'):
                st.session_state.show_study_settings_form = False
                st.rerun()
            return
        
        # Get unique study-site combinations
        if 'SiteforVisit' not in trials_df.columns:
            st.error("SiteforVisit column not found in trials data.")
            if st.button("✖ Close", width='stretch'):
                st.session_state.show_study_settings_form = False
                st.rerun()
            return
        
        study_site_combos = trials_df.groupby(['Study', 'SiteforVisit']).first().reset_index()
        
        # Study and Site selectors
        col1, col2 = st.columns(2)
        with col1:
            selected_study = st.selectbox(
                "Select Study",
                options=sorted(study_site_combos['Study'].unique()),
                key="study_settings_study"
            )
        
        with col2:
            # Filter sites for selected study
            study_sites = study_site_combos[study_site_combos['Study'] == selected_study]['SiteforVisit'].unique()
            selected_site = st.selectbox(
                "Select Site",
                options=sorted(study_sites),
                key="study_settings_site"
            )
        
        # Get current values
        current_trials = trials_df[
            (trials_df['Study'] == selected_study) & 
            (trials_df['SiteforVisit'] == selected_site)
        ]
        
        current_status = 'active'
        if not current_trials.empty and 'StudyStatus' in current_trials.columns:
            status_values = current_trials['StudyStatus'].dropna().unique()
            if len(status_values) > 0:
                current_status = str(status_values[0]).lower()
        
        current_target = None
        if not current_trials.empty and 'RecruitmentTarget' in current_trials.columns:
            target_values = current_trials['RecruitmentTarget'].dropna().unique()
            if len(target_values) > 0:
                current_target = int(target_values[0]) if pd.notna(target_values[0]) else None
        
        # Date overrides
        current_fpfv = None
        current_lpfv = None
        current_lplv = None
        
        if not current_trials.empty:
            for date_col, var_name in [('FPFV', 'current_fpfv'), ('LPFV', 'current_lpfv'), ('LPLV', 'current_lplv')]:
                if date_col in current_trials.columns:
                    date_values = current_trials[date_col].dropna()
                    if not date_values.empty:
                        date_val = pd.to_datetime(date_values.iloc[0], errors='coerce')
                        if pd.notna(date_val):
                            if var_name == 'current_fpfv':
                                current_fpfv = date_val.date()
                            elif var_name == 'current_lpfv':
                                current_lpfv = date_val.date()
                            elif var_name == 'current_lplv':
                                current_lplv = date_val.date()
        
        st.divider()
        
        # Status selector
        status_options = ['active', 'contracted', 'in_setup', 'expression_of_interest']
        status_labels = {
            'active': 'Active',
            'contracted': 'Contracted',
            'in_setup': 'In Setup',
            'expression_of_interest': 'Expression of Interest'
        }
        selected_status = st.selectbox(
            "Study Status",
            options=status_options,
            index=status_options.index(current_status) if current_status in status_options else 0,
            format_func=lambda x: status_labels[x],
            key="study_settings_status"
        )
        
        # Recruitment target
        recruitment_target = st.number_input(
            "Recruitment Target",
            min_value=0,
            value=int(current_target) if current_target else 0,
            step=1,
            help="Target number of patients for this study at this site",
            key="study_settings_target"
        )
        if recruitment_target == 0:
            recruitment_target = None
        
        st.divider()
        st.markdown("### Date Overrides (Optional)")
        st.caption("Leave blank to use calculated dates from patient/visit data")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            fpfv_date = st.date_input(
                "FPFV (First Patient First Visit)",
                value=current_fpfv,
                key="study_settings_fpfv"
            )
        with col2:
            lpfv_date = st.date_input(
                "LPFV (Last Patient First Visit)",
                value=current_lpfv,
                key="study_settings_lpfv"
            )
        with col3:
            lplv_date = st.date_input(
                "LPLV (Last Patient Last Visit)",
                value=current_lplv,
                key="study_settings_lplv"
            )
        
        st.divider()
        
        # Action buttons
        col_save, col_cancel = st.columns([1, 1])
        
        with col_save:
            if st.button("💾 Save Changes", type="primary", width='stretch'):
                try:
                    # Update all trial schedule rows for this study+site combination
                    # We need to update the database directly
                    client = db.get_supabase_client()
                    if client is None:
                        st.error("Database connection unavailable")
                        return
                    
                    # Update all rows for this study+site
                    update_data = {
                        'StudyStatus': selected_status,
                        'RecruitmentTarget': recruitment_target,
                        'FPFV': str(fpfv_date) if fpfv_date else None,
                        'LPFV': str(lpfv_date) if lpfv_date else None,
                        'LPLV': str(lplv_date) if lplv_date else None
                    }
                    
                    # Remove None values
                    update_data = {k: v for k, v in update_data.items() if v is not None}
                    
                    # Update in database
                    result = client.table('trial_schedules').update(update_data).eq('Study', selected_study).eq('SiteforVisit', selected_site).execute()
                    
                    if result.data:
                        st.success(f"✅ Successfully updated settings for {selected_study} at {selected_site}")
                        log_activity(f"Updated study settings: {selected_study}/{selected_site} - Status: {selected_status}, Target: {recruitment_target}", level='success')
                        
                        # Clear cache and refresh
                        db.clear_database_cache()
                        trigger_data_refresh()
                        
                        st.session_state.show_study_settings_form = False
                        st.rerun()
                    else:
                        st.error("Failed to update settings. No rows were updated.")
                        
                except Exception as e:
                    st.error(f"Error saving settings: {str(e)}")
                    log_activity(f"Error saving study settings: {str(e)}", level='error')
        
        with col_cancel:
            if st.button("✖ Cancel", width='stretch'):
                st.session_state.show_study_settings_form = False
                st.rerun()
    
    except Exception as e:
        st.error(f"Error in study settings form: {str(e)}")
        log_activity(f"Error in study settings form: {str(e)}", level='error')
        if st.button("✖ Close", width='stretch'):
            st.session_state.show_study_settings_form = False
            st.rerun()

@st.dialog("🔄 Switch Patient Study", width="large")
def switch_patient_study_modal():
    """Modal dialog for switching a patient from one study to another"""
    
    # Check if we're using database
    load_from_database = st.session_state.get('use_database', False)
    
    st.markdown("### Switch Patient Study")
    st.caption("ℹ️ Move a patient from one study to another (e.g., BaxDuo1 → BaxDuo2)")
    
    # Load required data based on mode
    if load_from_database:
        import database as db
        patients_df = db.fetch_all_patients()
        trial_schedule_df = db.fetch_all_trial_schedules()
        actual_visits_df = db.fetch_all_actual_visits()
    else:
        st.error("Switch Patient Study is only available in database mode.")
        if st.button("Close"):
            st.session_state.show_switch_patient_form = False
            st.rerun()
        return
    
    if patients_df is None or patients_df.empty or trial_schedule_df is None or trial_schedule_df.empty:
        st.error("Unable to load required data files.")
        if st.button("Close"):
            st.session_state.show_switch_patient_form = False
            st.rerun()
        return
    
    # Get unique studies from trial schedule
    available_studies = sorted(trial_schedule_df['Study'].unique().tolist())
    
    # Create patient selection options with current study
    patient_options = [
        f"{row['PatientID']} ({row['Study']})"
        for _, row in patients_df.iterrows()
    ]
    
    if not patient_options:
        st.warning("No patients available.")
        if st.button("Close"):
            st.session_state.show_switch_patient_form = False
            st.rerun()
        return
    
    # Form inputs
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Select Patient***")
        selected_patient_display = st.selectbox(
            "Select Patient*",
            options=patient_options,
            help="Choose the patient to switch",
            label_visibility="collapsed"
        )
        
        # Extract patient ID and current study
        selected_patient_id = selected_patient_display.split(' (')[0]
        current_study = selected_patient_display.split(' (')[1].rstrip(')')
    
    with col2:
        # Filter out current study from available options
        target_studies = [s for s in available_studies if s != current_study]
        
        if not target_studies:
            st.error(f"No other studies available. Patient is already in {current_study}.")
            if st.button("Close"):
                st.session_state.show_switch_patient_form = False
                st.rerun()
            return
        
        st.markdown("**Switch To Study***")
        target_study = st.selectbox(
            "Switch To Study*",
            options=target_studies,
            help="Select the target study",
            label_visibility="collapsed"
        )
    
    # Analyze impact
    if selected_patient_id and target_study:
        st.markdown("---")
        st.markdown("**📊 Impact Analysis**")
        
        # Get current and target study info
        current_study_visits = trial_schedule_df[trial_schedule_df['Study'] == current_study]
        target_study_visits = trial_schedule_df[trial_schedule_df['Study'] == target_study]
        
        # Find screening visits
        current_screening = current_study_visits[current_study_visits['Day'] < 1]
        target_screening = target_study_visits[target_study_visits['Day'] < 1]
        
        current_screening_day = current_screening['Day'].min() if not current_screening.empty else "None"
        target_screening_day = target_screening['Day'].min() if not target_screening.empty else "None"
        
        # Get actual visits for this patient
        patient_actual_visits = actual_visits_df[
            (actual_visits_df['PatientID'] == selected_patient_id) & 
            (actual_visits_df['Study'] == current_study)
        ] if actual_visits_df is not None else pd.DataFrame()
        
        col1, col2 = st.columns(2)
        with col1:
            st.info(f"**Current:** {current_study}\n- Screening: Day {current_screening_day}")
        with col2:
            st.info(f"**Target:** {target_study}\n- Screening: Day {target_screening_day}")
        
        if not patient_actual_visits.empty:
            st.write(f"**Actual visits to update:** {len(patient_actual_visits)}")
            for _, visit in patient_actual_visits.iterrows():
                st.write(f"  - {visit['VisitName']} ({visit['ActualDate']})")
        else:
            st.write("**Actual visits to update:** 0 (no actual visits recorded)")
    
    # Day 1 calculation
    if selected_patient_id and target_study:
        st.markdown("---")
        st.markdown("**📅 Day 1 Calculation**")
        
        # Check for actual visits
        if actual_visits_df is not None and not actual_visits_df.empty:
            patient_visits = actual_visits_df[
                (actual_visits_df['PatientID'] == selected_patient_id) & 
                (actual_visits_df['Study'] == current_study)
            ]
            
            # Check for actual screening visit
            screening_visits = patient_visits[
                patient_visits['VisitName'].str.contains('Screen', case=False, na=False)
            ]
            
            # Check for actual Day 1 visit
            day1_visits = patient_visits[
                patient_visits['VisitName'].str.contains('Random', case=False, na=False) |
                patient_visits['VisitName'].str.contains('Day 1', case=False, na=False) |
                patient_visits['VisitName'].str.contains('Baseline', case=False, na=False)
            ]
            
            if not screening_visits.empty and target_screening_day != "None":
                # Auto-calculate from actual screening
                actual_screening_date = pd.to_datetime(screening_visits.iloc[0]['ActualDate'])
                offset_days = int(1 - target_screening_day)
                new_day1_date = actual_screening_date + timedelta(days=offset_days)
                
                st.success(f"✅ **Auto-calculated from actual screening:**\n"
                          f"New Day 1: {new_day1_date.strftime('%d/%m/%Y')}\n"
                          f"({actual_screening_date.strftime('%d/%m/%Y')} + {offset_days} days)")
                
                final_start_date = new_day1_date.strftime('%d/%m/%Y')
                
            elif not day1_visits.empty:
                # Use existing Day 1
                actual_day1_date = pd.to_datetime(day1_visits.iloc[0]['ActualDate'])
                
                st.success(f"✅ **Using existing Day 1 from actual visit:**\n"
                          f"Day 1: {actual_day1_date.strftime('%d/%m/%Y')}")
                
                final_start_date = actual_day1_date.strftime('%d/%m/%Y')
                
            else:
                # No actual visits - ask user for date
                st.warning("⚠️ **No actual visits found** - please specify the date to use:")
                
                date_type = st.radio(
                    "Date Type*",
                    ["Screening Date", "Randomization Date (Day 1)"],
                    help="Which date should be used for Day 1 calculation?"
                )
                
                start_date = st.date_input(
                    "Date*",
                    value=date.today(),
                    format="DD/MM/YYYY",
                    help="Enter the actual date"
                )
                
                if date_type == "Screening Date" and target_screening_day != "None":
                    # Calculate Day 1 from screening
                    offset_days = int(1 - target_screening_day)
                    new_day1_date = start_date + timedelta(days=offset_days)
                    
                    st.info(f"📅 **Calculated Day 1:** {new_day1_date.strftime('%d/%m/%Y')} "
                           f"(Screening + {offset_days} days)")
                    
                    final_start_date = new_day1_date.strftime('%d/%m/%Y')
                else:
                    # Use as Day 1 directly
                    st.info(f"📅 **Day 1:** {start_date.strftime('%d/%m/%Y')}")
                    final_start_date = start_date.strftime('%d/%m/%Y')
        else:
            # No actual visits data - ask user
            st.warning("⚠️ **No actual visits data available** - please specify the date to use:")
            
            date_type = st.radio(
                "Date Type*",
                ["Screening Date", "Randomization Date (Day 1)"],
                help="Which date should be used for Day 1 calculation?"
            )
            
            start_date = st.date_input(
                "Date*",
                value=date.today(),
                format="DD/MM/YYYY",
                help="Enter the actual date"
            )
            
            if date_type == "Screening Date" and target_screening_day != "None":
                # Calculate Day 1 from screening
                offset_days = int(1 - target_screening_day)
                new_day1_date = start_date + timedelta(days=offset_days)
                
                st.info(f"📅 **Calculated Day 1:** {new_day1_date.strftime('%d/%m/%Y')} "
                       f"(Screening + {offset_days} days)")
                
                final_start_date = new_day1_date.strftime('%d/%m/%Y')
            else:
                # Use as Day 1 directly
                st.info(f"📅 **Day 1:** {start_date.strftime('%d/%m/%Y')}")
                final_start_date = start_date.strftime('%d/%m/%Y')
    
    # Validation and submission
    col_submit, col_cancel = st.columns([1, 1])
    
    with col_submit:
        if st.button("🔄 Switch Study", type="primary", width='stretch'):
            # Validate required fields
            if not selected_patient_id or not target_study:
                st.error("Please select both patient and target study")
                return
            
            try:
                import database as db
                success, message, visits_count = db.switch_patient_study(
                    selected_patient_id, current_study, target_study, final_start_date
                )
                
                if success:
                    st.success(f"✅ **Patient switched successfully!**\n\n"
                              f"- {selected_patient_id} moved from {current_study} → {target_study}\n"
                              f"- Start Date updated to: {final_start_date}\n"
                              f"- {visits_count} actual visits updated")
                    
                    log_activity(f"Successfully switched patient {selected_patient_id} from {current_study} to {target_study}", level='success')
                    
                    # Trigger data refresh
                    trigger_data_refresh()
                    st.session_state.show_switch_patient_form = False
                    st.rerun()
                else:
                    st.error(f"❌ **Switch failed:**\n\n{message}")
                    log_activity(f"Failed to switch patient: {message}", level='error')
                    
            except Exception as e:
                st.error(f"Database error: {str(e)}")
                log_activity(f"Database error switching patient: {str(e)}", level='error')
    
    with col_cancel:
        if st.button("✖ Cancel", width='stretch'):
            st.session_state.show_switch_patient_form = False
            st.rerun()
