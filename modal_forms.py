import streamlit as st
import pandas as pd
import io
from datetime import date, datetime, timedelta
from typing import List, Tuple, Dict, Optional, Any
from helpers import load_file, log_activity, get_visit_type_series, trigger_data_refresh
import database as db

def calculate_day_1_date(entered_date, study, trial_schedule_df, pathway='standard'):
    """
    Calculate Day 1 date from screening date based on trial schedule.

    Args:
        entered_date: The date entered by user (screening date)
        study: Selected study name
        trial_schedule_df: Trial schedule DataFrame
        pathway: Patient pathway variant (default: 'standard')

    Returns:
        tuple: (adjusted_date, offset_days, screening_day_found)
    """
    # Filter trial schedule for selected study and pathway
    if 'Pathway' in trial_schedule_df.columns:
        study_visits = trial_schedule_df[
            (trial_schedule_df['Study'] == study) &
            (trial_schedule_df['Pathway'] == pathway)
        ].copy()
    else:
        # Backward compatibility: if no Pathway column, use all visits for that study
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
    load_from_database = True  # Always use database
    
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

        # PATHWAY SELECTION: Check if selected study has multiple pathways
        available_pathways = ['standard']  # Default pathway
        if selected_study and 'Pathway' in trial_schedule_df.columns:
            study_pathways = trial_schedule_df[trial_schedule_df['Study'] == selected_study]['Pathway'].unique().tolist()
            if len(study_pathways) > 1:
                available_pathways = sorted(study_pathways)

        if len(available_pathways) > 1:
            st.markdown("**Enrollment Pathway***")
            selected_pathway = st.selectbox(
                "Enrollment Pathway*",
                options=available_pathways,
                help="Select enrollment pathway (e.g., 'standard' for normal enrollment, 'with_run_in' for medication run-in period)",
                label_visibility="collapsed"
            )
        else:
            selected_pathway = 'standard'

    with col2:
        # REFACTOR: New model uses ScreeningDate (Day 1) as baseline
        # Show status selection
        st.markdown("**Patient Status***")
        patient_status = st.selectbox(
            "Patient Status*",
            options=["screening", "randomized", "screen_failed", "dna_screening", "withdrawn", "deceased", "completed", "lost_to_followup"],
            index=0,  # Default to 'screening'
            help="Select patient journey status. 'screening' = not yet randomized, 'randomized' = recruited, 'dna_screening' = didn't attend screening.",
            label_visibility="collapsed"
        )

        screening_date = st.date_input(
            "Screening Date* (Day 1)",
            value=date.today(),
            format="DD/MM/YYYY",
            help="Enter the date of the first screening visit (Day 1 baseline)"
        )

        # If status is randomized or beyond, ask for randomization date
        randomization_date = None
        if patient_status in ['randomized', 'withdrawn', 'deceased', 'completed', 'lost_to_followup']:
            randomization_date = st.date_input(
                "Randomization Date",
                value=screening_date,
                format="DD/MM/YYYY",
                help="Enter the date of randomization (V1). Must be >= screening date."
            )

            # Validation
            if randomization_date and randomization_date < screening_date:
                st.error("⚠️ Randomization date cannot be before screening date")
                randomization_date = screening_date
        
        st.markdown("**Recruited By***")
        recruitment_site = st.selectbox(
            "Recruited By*",
            options=["Ashfields", "Kiltearn"],
            help="Which practice recruited this patient?",
            label_visibility="collapsed"
        )
        
        st.markdown("**Seen At***")
        seen_site_options = ["Ashfields", "Kiltearn"]
        seen_site_default = seen_site_options.index(recruitment_site) if recruitment_site in seen_site_options else 0
        site_seen_at = st.selectbox(
            "Seen At*",
            options=seen_site_options,
            index=seen_site_default,
            help="Where the patient will be seen for visits",
            label_visibility="collapsed"
        )
    
    # Show status information
    if selected_study and screening_date:
        if patient_status in ['randomized', 'withdrawn', 'deceased', 'completed', 'lost_to_followup']:
            st.success(f"✅ **This patient will be counted as RECRUITED** (Status: {patient_status})")
        elif patient_status == 'screening':
            st.info(f"📋 **This patient is in screening** and not yet recruited")
        elif patient_status == 'dna_screening':
            st.warning(f"⚠️ **DNA Screening** - Did not attend screening, will not count as recruited")
        else:
            st.warning(f"⚠️ **This patient screen failed** and will not count as recruited")
    
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

            # REFACTOR: Format dates for new model
            formatted_screening_date = screening_date.strftime('%d/%m/%Y')
            formatted_randomization_date = randomization_date.strftime('%d/%m/%Y') if randomization_date else None

            # Create new patient data with new schema
            new_patient = {
                'PatientID': new_patient_id,
                'Study': selected_study,
                'ScreeningDate': formatted_screening_date,
                'RandomizationDate': formatted_randomization_date,
                'Status': patient_status,
                'Site': recruitment_site,  # Which practice recruited them
                'PatientPractice': recruitment_site,  # Recruitment site
                'SiteSeenAt': site_seen_at,  # Visit location
                'Pathway': selected_pathway  # Enrollment pathway variant
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
    load_from_database = True  # Always use database
    
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
        
        # Get patient's study and pathway
        patient_row = patients_df[patients_df['PatientID'] == selected_patient_id].iloc[0]
        patient_study = patient_row['Study']
        patient_pathway = patient_row.get('Pathway', 'standard') if 'Pathway' in patients_df.columns else 'standard'

        # Filter visits for this study and pathway
        if 'Pathway' in trial_schedule_df.columns:
            study_visits = trial_schedule_df[
                (trial_schedule_df['Study'] == patient_study) &
                (trial_schedule_df['Pathway'] == patient_pathway)
            ].copy()
        else:
            # Backward compatibility: if no Pathway column, use all visits for that study
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
    load_from_database = True  # Always use database
    
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

def get_study_site_combinations(trials_df: pd.DataFrame) -> List[Tuple[str, str]]:
    """
    Get sorted list of unique Study+Site combinations.
    
    Args:
        trials_df: Trial schedules dataframe
    
    Returns:
        List of (Study, Site) tuples, sorted by Study then Site
    """
    if 'SiteforVisit' not in trials_df.columns:
        return []
    
    study_site_combos = trials_df.groupby(['Study', 'SiteforVisit']).first().reset_index()
    combinations = [(row.Study, row.SiteforVisit) for row in study_site_combos.itertuples(index=False)]
    return sorted(combinations, key=lambda x: (x[0], x[1]))

def get_calculated_study_values(study: str, site: str, patients_df: pd.DataFrame, visits_df: pd.DataFrame) -> Dict[str, Any]:
    """
    Calculate FPFV, LPFV, LPLV, and recruitment count from patient/visit data.
    
    Args:
        study: Study name
        site: Contract site name (ContractSite)
        patients_df: Patients dataframe
        visits_df: Visits dataframe (with Date column)
    
    Returns:
        dict with keys: 'fpfv', 'lpfv', 'lplv', 'recruitment_count'
    """
    # ContractSite counts all patients in the study, regardless of visit location
    study_patients = patients_df[
        (patients_df['Study'] == study)
    ]

    fpfv = None
    lpfv = None
    recruitment_count = 0

    if not study_patients.empty:
        # REFACTOR: Count recruited patients based on Status
        if 'Status' in study_patients.columns:
            recruited_statuses = ['randomized', 'withdrawn', 'deceased', 'completed', 'lost_to_followup']
            recruited_patients = study_patients[study_patients['Status'].isin(recruited_statuses)]
            recruitment_count = len(recruited_patients)

            # Use RandomizationDate for FPFV/LPFV if available, else ScreeningDate, else StartDate
            if 'RandomizationDate' in recruited_patients.columns:
                date_col = 'RandomizationDate'
            elif 'ScreeningDate' in recruited_patients.columns:
                date_col = 'ScreeningDate'
            elif 'StartDate' in recruited_patients.columns:
                date_col = 'StartDate'
            else:
                date_col = None

            if date_col and not recruited_patients.empty:
                dates = pd.to_datetime(recruited_patients[date_col], errors='coerce').dropna()
                if not dates.empty:
                    fpfv = dates.min().date()
                    lpfv = dates.max().date()
        else:
            # Backward compatibility: no Status column, count all patients
            recruitment_count = len(study_patients)
            if 'StartDate' in study_patients.columns:
                start_dates = pd.to_datetime(study_patients['StartDate'], errors='coerce').dropna()
                if not start_dates.empty:
                    fpfv = start_dates.min().date()
                    lpfv = start_dates.max().date()
    
    # Get visits for this study (regardless of visit location)
    study_visits = visits_df[
        (visits_df['Study'] == study)
    ]
    
    lplv = None
    if not study_visits.empty and 'Date' in study_visits.columns:
        visit_dates = pd.to_datetime(study_visits['Date'], errors='coerce').dropna()
        if not visit_dates.empty:
            lplv = visit_dates.max().date()
    
    return {
        'fpfv': fpfv,
        'lpfv': lpfv,
        'lplv': lplv,
        'recruitment_count': recruitment_count
    }

def handle_study_settings_modal():
    """Handle study settings (status/targets) modal with navigation"""
    if st.session_state.get('show_study_settings_form', False) and not st.session_state.get('any_dialog_open', False):
        try:
            st.session_state.any_dialog_open = True
            study_settings_navigation_modal()
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

@st.dialog("⚙️ Study Settings", width="large")
def study_settings_navigation_modal():
    """Modal form to edit study status and recruitment targets with navigation"""
    try:
        # Load data - try study_site_details first, fallback to trial_schedules
        study_details_df = db.fetch_all_study_site_details()
        trials_df = db.fetch_all_trial_schedules()
        
        # Get unique study-site combinations from both sources (merge to include all)
        combinations_set = set()
        
        # Add from study_site_details (preferred source)
        if study_details_df is not None and not study_details_df.empty:
            site_col = 'ContractSite' if 'ContractSite' in study_details_df.columns else 'SiteforVisit'
            for _, row in study_details_df.iterrows():
                combinations_set.add((row['Study'], row[site_col]))
        
        # Add from trial_schedules (for backward compatibility - studies without details yet)
        if trials_df is not None and not trials_df.empty:
            trial_combinations = get_study_site_combinations(trials_df)
            for combo in trial_combinations:
                combinations_set.add(combo)
        
        # Convert to sorted list
        combinations = sorted(list(combinations_set), key=lambda x: (x[0], x[1]))
        
        if not combinations:
            st.error("No study-site combinations found.")
            if st.button("✖ Close", width='stretch'):
                st.session_state.show_study_settings_form = False
                st.rerun()
            return
        
        # Check if we're in "Add New Study" mode
        add_new_mode = st.session_state.get('study_settings_add_new', False)
        
        # Add New Study button at the top
        if not add_new_mode:
            if st.button("➕ Add New Study", type="primary", width='stretch'):
                st.session_state['study_settings_add_new'] = True
                st.rerun()
            st.divider()
        
        # Handle Add New Study mode
        if add_new_mode:
            st.markdown("### ➕ Add New Study")
            
            # Form for new study
            new_study = st.text_input("Study Name *", key="new_study_name", help="Enter the study name/code")
            
            # Get available sites from trials_df or allow manual entry
            available_sites = []
            if trials_df is not None and not trials_df.empty and 'SiteforVisit' in trials_df.columns:
                available_sites = sorted(trials_df['SiteforVisit'].dropna().unique().tolist())
            
            if available_sites:
                new_site = st.selectbox("Contract Site *", options=available_sites, key="new_study_site")
            else:
                new_site = st.text_input("Contract Site *", key="new_study_site", help="Enter the contract holder site name")
            
            # Status selector with new option
            status_options_new = ['active', 'contracted', 'in_setup', 'expression_of_interest', 'eoi_didnt_get']
            status_labels_new = {
                'active': 'Active',
                'contracted': 'Contracted',
                'in_setup': 'In Setup',
                'expression_of_interest': 'Expression of Interest',
                'eoi_didnt_get': 'EOI - Didn\'t Get'
            }
            new_status = st.selectbox(
                "Study Status",
                options=status_options_new,
                index=3,  # Default to expression_of_interest for new studies
                format_func=lambda x: status_labels_new[x],
                key="new_study_status"
            )
            
            new_target = st.number_input(
                "Recruitment Target",
                min_value=0,
                value=0,
                step=1,
                help="Target number of patients (0 = no target)",
                key="new_study_target"
            )
            if new_target == 0:
                new_target = None
            
            new_description = st.text_area(
                "Description",
                help="Study description/information",
                key="new_study_description",
                height=100
            )
            
            new_eoi_date = st.date_input(
                "EOI Date",
                value=None,
                help="Date when Expression of Interest was submitted",
                key="new_study_eoi_date"
            )
            
            # Date overrides
            st.markdown("#### Date Overrides (Optional)")
            new_fpfv = st.date_input("FPFV", value=None, key="new_study_fpfv")
            new_lpfv = st.date_input("LPFV", value=None, key="new_study_lpfv")
            new_lplv = st.date_input("LPLV", value=None, key="new_study_lplv")
            
            col_save_new, col_cancel_new = st.columns([1, 1])
            with col_save_new:
                if st.button("💾 Create Study", type="primary", width='stretch', key="save_new_study"):
                    if not new_study or not new_site:
                        st.error("Study name and Site are required")
                    else:
                        # Create new study entry
                        details = {
                            'StudyStatus': new_status,
                            'RecruitmentTarget': new_target,
                            'Description': new_description if new_description else None,
                            'EOIDate': new_eoi_date if new_eoi_date else None,
                            'FPFV': new_fpfv if new_fpfv else None,
                            'LPFV': new_lpfv if new_lpfv else None,
                            'LPLV': new_lplv if new_lplv else None
                        }
                        
                        if db.create_study_site_details(new_study, new_site, details):
                            st.success(f"✅ Successfully created {new_study} at {new_site}")
                            log_activity(f"Created new study: {new_study}/{new_site}", level='success')
                            db.clear_database_cache()
                            trigger_data_refresh()
                            # Close modal and refresh to show new study
                            st.session_state['study_settings_add_new'] = False
                            st.session_state['show_study_settings_form'] = False
                            st.rerun()
                        else:
                            st.error("Failed to create study. It may already exist.")
            
            with col_cancel_new:
                if st.button("✖ Cancel", width='stretch', key="cancel_new_study"):
                    st.session_state['study_settings_add_new'] = False
                    st.rerun()
            
            return
        
        # Initialize or get current index
        session_key = 'study_settings_current_index'
        if session_key not in st.session_state:
            st.session_state[session_key] = 0
        
        current_index = st.session_state[session_key]
        if current_index >= len(combinations):
            current_index = 0
            st.session_state[session_key] = 0
        
        # Navigation buttons
        col_nav1, col_nav2, col_nav3, col_nav4 = st.columns([1, 2, 1, 1])
        
        with col_nav1:
            if st.button("← Previous", disabled=(len(combinations) <= 1), width='stretch'):
                # Clear flags for current study before navigating
                clear_key_base = f"clear_flags_{current_index}"
                if clear_key_base in st.session_state:
                    del st.session_state[clear_key_base]
                st.session_state[session_key] = (current_index - 1) % len(combinations)
                st.rerun()
        
        with col_nav2:
            selected_study, selected_site = combinations[current_index]
            st.markdown(f"**Study {current_index + 1} of {len(combinations)}**")
            st.caption(f"{selected_study} at {selected_site}")
        
        with col_nav3:
            if st.button("Next →", disabled=(len(combinations) <= 1), width='stretch'):
                # Clear flags for current study before navigating
                clear_key_base = f"clear_flags_{current_index}"
                if clear_key_base in st.session_state:
                    del st.session_state[clear_key_base]
                st.session_state[session_key] = (current_index + 1) % len(combinations)
                st.rerun()
        
        with col_nav4:
            if st.button("🔄 Reset", help="Reset to first study", width='stretch'):
                # Clear all flags
                for i in range(len(combinations)):
                    clear_key = f"clear_flags_{i}"
                    if clear_key in st.session_state:
                        del st.session_state[clear_key]
                st.session_state[session_key] = 0
                st.rerun()
        
        st.divider()
        
        # Get current values from study_site_details (preferred) or fallback to trial_schedules
        current_status = 'active'
        current_target = None
        current_fpfv = None
        current_lpfv = None
        current_lplv = None
        current_description = None
        current_eoi_date = None
        
        # Try to get from study_site_details first
        study_details = db.fetch_study_site_details(selected_study, selected_site)
        
        if study_details:
            current_status = study_details.get('StudyStatus', 'active')
            current_target = study_details.get('RecruitmentTarget')
            if study_details.get('FPFV'):
                current_fpfv = pd.to_datetime(study_details['FPFV'], errors='coerce').date() if pd.notna(pd.to_datetime(study_details['FPFV'], errors='coerce')) else None
            if study_details.get('LPFV'):
                current_lpfv = pd.to_datetime(study_details['LPFV'], errors='coerce').date() if pd.notna(pd.to_datetime(study_details['LPFV'], errors='coerce')) else None
            if study_details.get('LPLV'):
                current_lplv = pd.to_datetime(study_details['LPLV'], errors='coerce').date() if pd.notna(pd.to_datetime(study_details['LPLV'], errors='coerce')) else None
            current_description = study_details.get('Description')
            if study_details.get('EOIDate'):
                current_eoi_date = pd.to_datetime(study_details['EOIDate'], errors='coerce').date() if pd.notna(pd.to_datetime(study_details['EOIDate'], errors='coerce')) else None
        else:
            # Fallback to trial_schedules for backward compatibility
            current_trials = trials_df[
                (trials_df['Study'] == selected_study) & 
                (trials_df['SiteforVisit'] == selected_site)
            ] if trials_df is not None and not trials_df.empty else pd.DataFrame()
            
            if not current_trials.empty and 'StudyStatus' in current_trials.columns:
                status_values = current_trials['StudyStatus'].dropna().unique()
                if len(status_values) > 0:
                    current_status = str(status_values[0]).lower()
            
            if not current_trials.empty and 'RecruitmentTarget' in current_trials.columns:
                target_values = current_trials['RecruitmentTarget'].dropna().unique()
                if len(target_values) > 0:
                    current_target = int(target_values[0]) if pd.notna(target_values[0]) else None
            
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
        
        # Load patients and visits for calculated values
        patients_df = db.fetch_all_patients()
        if patients_df is None:
            patients_df = pd.DataFrame(columns=['PatientID', 'Study', 'ScreeningDate', 'RandomizationDate', 'Status', 'PatientPractice', 'SiteSeenAt', 'Pathway'])
        
        # Build visits_df from actual_visits and trial_schedules to get SiteofVisit
        visits_df = pd.DataFrame(columns=['Study', 'SiteofVisit', 'Date'])
        try:
            actual_visits_df = db.fetch_all_actual_visits()
            if actual_visits_df is not None and not actual_visits_df.empty:
                # Get SiteforVisit from trial_schedules for each visit
                visit_records = []
                for _, visit in actual_visits_df.iterrows():
                    visit_study = visit.get('Study')
                    visit_name = visit.get('VisitName')
                    visit_date = visit.get('ActualDate')
                    
                    if pd.notna(visit_date) and visit_study and visit_name:
                        # Find SiteforVisit from trial_schedules
                        matching_trials = trials_df[
                            (trials_df['Study'] == visit_study) & 
                            (trials_df['VisitName'] == visit_name)
                        ]
                        if not matching_trials.empty:
                            site = matching_trials.iloc[0]['SiteforVisit']
                            visit_records.append({
                                'Study': visit_study,
                                'SiteofVisit': site,
                                'Date': pd.to_datetime(visit_date, errors='coerce')
                            })
                
                if visit_records:
                    visits_df = pd.DataFrame(visit_records)
                    visits_df = visits_df[visits_df['Date'].notna()]
        except Exception as e:
            log_activity(f"Error building visits_df for calculated values: {e}", level='warning')
            visits_df = pd.DataFrame(columns=['Study', 'SiteforVisit', 'Date'])
        
        # Get calculated values
        calculated = get_calculated_study_values(selected_study, selected_site, patients_df, visits_df)
        
        # Display calculated values section
        st.markdown("### 📊 Calculated Values (from patient/visit data)")
        st.caption("These values are automatically calculated from your data. Override fields below take precedence.")
        
        calc_col1, calc_col2, calc_col3, calc_col4 = st.columns(4)
        with calc_col1:
            fpfv_display = calculated['fpfv'].strftime('%d/%m/%Y') if calculated['fpfv'] else "N/A"
            st.info(f"**FPFV:**\n{fpfv_display}")
        with calc_col2:
            lpfv_display = calculated['lpfv'].strftime('%d/%m/%Y') if calculated['lpfv'] else "N/A"
            st.info(f"**LPFV:**\n{lpfv_display}")
        with calc_col3:
            lplv_display = calculated['lplv'].strftime('%d/%m/%Y') if calculated['lplv'] else "N/A"
            st.info(f"**LPLV:**\n{lplv_display}")
        with calc_col4:
            st.info(f"**Recruitment:**\n{calculated['recruitment_count']} patients")
        
        st.divider()
        
        # Override fields section
        st.markdown("### ✏️ Study Information (editable)")
        st.caption("Set study information, status, and override values. Leave blank to use calculated values.")
        
        # Initialize clear flags in session state
        clear_key_base = f"clear_flags_{current_index}"
        if clear_key_base not in st.session_state:
            st.session_state[clear_key_base] = {
                'status': False,
                'target': False,
                'fpfv': False,
                'lpfv': False,
                'lplv': False,
                'description': False,
                'eoi_date': False
            }
        
        # Handle clear button clicks
        clear_flags = st.session_state[clear_key_base]
        
        # Description field
        st.markdown("#### Study Description")
        description_value = ""
        if not clear_flags['description'] and current_description:
            description_value = current_description
        description = st.text_area(
            "Description",
            value=description_value,
            help="Study description/information (shown on hover, etc.)",
            key=f"study_settings_description_{current_index}",
            height=100
        )
        if st.button("Clear Description", key=f"clear_description_{current_index}", help="Clear description"):
            clear_flags['description'] = True
            st.session_state[clear_key_base] = clear_flags
            st.rerun()
        
        st.divider()
        
        # Status selector (updated to include eoi_didnt_get)
        status_options = ['active', 'contracted', 'in_setup', 'expression_of_interest', 'eoi_didnt_get']
        status_labels = {
            'active': 'Active',
            'contracted': 'Contracted',
            'in_setup': 'In Setup',
            'expression_of_interest': 'Expression of Interest',
            'eoi_didnt_get': 'EOI - Didn\'t Get'
        }
        
        col_status1, col_status2 = st.columns([3, 1])
        with col_status1:
            status_index = 0
            if not clear_flags['status'] and current_status in status_options:
                status_index = status_options.index(current_status)
            selected_status = st.selectbox(
                "Study Status",
                options=status_options,
                index=status_index,
                format_func=lambda x: status_labels[x],
                key=f"study_settings_status_{current_index}"
            )
        with col_status2:
            if st.button("Clear", key=f"clear_status_{current_index}", help="Reset to default (active)"):
                clear_flags['status'] = True
                st.session_state[clear_key_base] = clear_flags
                st.rerun()
        
        # Recruitment target
        col_target1, col_target2 = st.columns([3, 1])
        with col_target1:
            target_value = 0
            if not clear_flags['target'] and current_target:
                target_value = int(current_target)
            recruitment_target = st.number_input(
                "Recruitment Target",
                min_value=0,
                value=target_value,
                step=1,
                help="Target number of patients for this study at this site",
                key=f"study_settings_target_{current_index}"
            )
            if recruitment_target == 0:
                recruitment_target = None
        with col_target2:
            if st.button("Clear", key=f"clear_target_{current_index}", help="Remove target (use NULL)"):
                clear_flags['target'] = True
                st.session_state[clear_key_base] = clear_flags
                st.rerun()
        
        # Date overrides with clear buttons
        st.markdown("#### Date Overrides")
        
        col_fpfv1, col_fpfv2 = st.columns([3, 1])
        with col_fpfv1:
            fpfv_value = None
            if not clear_flags['fpfv']:
                fpfv_value = current_fpfv
            fpfv_date = st.date_input(
                "FPFV (First Patient First Visit)",
                value=fpfv_value,
                key=f"study_settings_fpfv_{current_index}"
            )
        with col_fpfv2:
            if st.button("Clear", key=f"clear_fpfv_{current_index}", help="Remove override"):
                clear_flags['fpfv'] = True
                st.session_state[clear_key_base] = clear_flags
                st.rerun()
        
        col_lpfv1, col_lpfv2 = st.columns([3, 1])
        with col_lpfv1:
            lpfv_value = None
            if not clear_flags['lpfv']:
                lpfv_value = current_lpfv
            lpfv_date = st.date_input(
                "LPFV (Last Patient First Visit)",
                value=lpfv_value,
                key=f"study_settings_lpfv_{current_index}"
            )
        with col_lpfv2:
            if st.button("Clear", key=f"clear_lpfv_{current_index}", help="Remove override"):
                clear_flags['lpfv'] = True
                st.session_state[clear_key_base] = clear_flags
                st.rerun()
        
        col_lplv1, col_lplv2 = st.columns([3, 1])
        with col_lplv1:
            lplv_value = None
            if not clear_flags['lplv']:
                lplv_value = current_lplv
            lplv_date = st.date_input(
                "LPLV (Last Patient Last Visit)",
                value=lplv_value,
                key=f"study_settings_lplv_{current_index}"
            )
        with         col_lplv2:
            if st.button("Clear", key=f"clear_lplv_{current_index}", help="Remove override"):
                clear_flags['lplv'] = True
                st.session_state[clear_key_base] = clear_flags
                st.rerun()
        
        # EOI Date field
        st.markdown("#### EOI Information")
        col_eoi1, col_eoi2 = st.columns([3, 1])
        with col_eoi1:
            eoi_value = None
            if not clear_flags['eoi_date']:
                eoi_value = current_eoi_date
            eoi_date = st.date_input(
                "EOI Date",
                value=eoi_value,
                help="Date when Expression of Interest was submitted",
                key=f"study_settings_eoi_date_{current_index}"
            )
        with col_eoi2:
            if st.button("Clear", key=f"clear_eoi_date_{current_index}", help="Remove EOI date"):
                clear_flags['eoi_date'] = True
                st.session_state[clear_key_base] = clear_flags
                st.rerun()
        
        st.divider()
        
        # Action buttons
        col_save, col_cancel = st.columns([1, 1])
        
        with col_save:
            if st.button("💾 Save Changes", type="primary", width='stretch', key=f"save_{current_index}"):
                try:
                    client = db.get_supabase_client()
                    if client is None:
                        st.error("Database connection unavailable")
                        return
                    
                    # Prepare update data - apply clear flags
                    if clear_flags['status']:
                        selected_status = 'active'
                    if clear_flags['target']:
                        recruitment_target = None
                    if clear_flags['fpfv']:
                        fpfv_date = None
                    if clear_flags['lpfv']:
                        lpfv_date = None
                    if clear_flags['lplv']:
                        lplv_date = None
                    if clear_flags['description']:
                        description = None
                    if clear_flags['eoi_date']:
                        eoi_date = None
                    
                    # Prepare update data for study_site_details
                    # DEBUG: Log what dates we're trying to save
                    log_activity(f"DEBUG Study Settings Save - FPFV: {fpfv_date}, LPFV: {lpfv_date}, LPLV: {lplv_date}", level='info')

                    details = {
                        'StudyStatus': selected_status,
                        'RecruitmentTarget': recruitment_target,
                        'FPFV': fpfv_date if fpfv_date else None,
                        'LPFV': lpfv_date if lpfv_date else None,
                        'LPLV': lplv_date if lplv_date else None,
                        'Description': description if description else None,
                        'EOIDate': eoi_date if eoi_date else None
                    }
                    
                    # Save to study_site_details table (creates if doesn't exist, updates if exists)
                    if db.save_study_site_details(selected_study, selected_site, details):
                        st.success(f"✅ Successfully updated settings for {selected_study} at {selected_site}")
                        log_activity(f"Updated study settings: {selected_study}/{selected_site} - Status: {selected_status}, Target: {recruitment_target}", level='success')

                        # Clear cache and refresh
                        db.clear_database_cache()
                        trigger_data_refresh()

                        # Reset clear flags for this study
                        if clear_key_base in st.session_state:
                            st.session_state[clear_key_base] = {
                                'status': False,
                                'target': False,
                                'fpfv': False,
                                'lpfv': False,
                                'lplv': False,
                                'description': False,
                                'eoi_date': False
                            }

                        # Close the modal after successful save
                        st.session_state.show_study_settings_form = False
                        st.rerun()
                    else:
                        st.error("Failed to update settings. Please try again.")
                        
                except Exception as e:
                    st.error(f"Error saving settings: {str(e)}")
                    log_activity(f"Error saving study settings: {str(e)}", level='error')
        
        with col_cancel:
            if st.button("✖ Cancel", width='stretch', key=f"cancel_{current_index}"):
                st.session_state.show_study_settings_form = False
                st.rerun()
    
    except Exception as e:
        st.error(f"Error in study settings form: {str(e)}")
        log_activity(f"Error in study settings form: {str(e)}", level='error')
        if st.button("✖ Close", width='stretch'):
            st.session_state.show_study_settings_form = False
            st.rerun()

# Keep old modal for backward compatibility (can be removed later)
@st.dialog("⚙️ Study Settings (Status & Recruitment)", width="large")
def study_settings_modal():
    """Legacy modal - redirects to navigation modal"""
    study_settings_navigation_modal()

@st.dialog("🔄 Switch Patient Study", width="large")
def switch_patient_study_modal():
    """Modal dialog for switching a patient from one study to another"""
    
    # Check if we're using database
    load_from_database = True  # Always use database
    
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
