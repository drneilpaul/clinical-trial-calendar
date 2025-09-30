"""
Modal forms for manual data entry in Clinical Trial Calendar Generator
Enhanced for error handling and Supabase preparation
"""

import streamlit as st
import pandas as pd
from datetime import datetime, date
from typing import Optional, Dict, Any
from helpers import add_error, add_warning, add_info, safe_string_conversion, clean_patient_id
from config import VALIDATION_RULES, REQUIRED_COLUMNS

# =============================================================================
# MODAL FORM FUNCTIONS
# =============================================================================

def show_manual_entry_modal():
    """Display manual entry form in modal dialog"""
    try:
        st.subheader("✏️ Manual Data Entry")
        
        # Create tabs for different entry types
        tab1, tab2, tab3 = st.tabs(["Patient Entry", "Visit Entry", "Batch Upload"])
        
        with tab1:
            show_patient_entry_form()
            
        with tab2:
            show_visit_entry_form()
            
        with tab3:
            show_batch_upload_form()
            
    except Exception as e:
        add_error(f"Error displaying manual entry modal: {str(e)}")

def show_patient_entry_form():
    """Form for manual patient entry"""
    try:
        st.markdown("#### Add New Patient")
        
        with st.form("patient_entry_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                patient_id = st.text_input(
                    "Patient ID *",
                    help="Unique patient identifier",
                    max_chars=VALIDATION_RULES['patient_id']['max_length']
                )
                
                study = st.text_input(
                    "Study *",
                    help="Study protocol identifier",
                    max_chars=VALIDATION_RULES['study_name']['max_length']
                )
            
            with col2:
                start_date = st.date_input(
                    "Start Date *",
                    value=datetime.now().date(),
                    help="Patient study start date"
                )
                
                site = st.text_input(
                    "Site (Optional)",
                    help="Study site identifier"
                )
            
            # Optional fields
            notes = st.text_area(
                "Notes (Optional)",
                help="Additional patient information"
            )
            
            # Form submission
            submitted = st.form_submit_button("Add Patient", type="primary")
            
            if submitted:
                if _validate_patient_entry(patient_id, study, start_date):
                    success = _save_patient_entry({
                        'PatientID': patient_id,
                        'Study': study,
                        'StartDate': start_date,
                        'Site': site,
                        'Notes': notes
                    })
                    
                    if success:
                        st.success("✅ Patient added successfully!")
                        st.rerun()
                    else:
                        st.error("❌ Failed to add patient - check error messages")
                        
    except Exception as e:
        add_error(f"Error in patient entry form: {str(e)}")

def show_visit_entry_form():
    """Form for manual visit entry"""
    try:
        st.markdown("#### Record Visit")
        
        with st.form("visit_entry_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                patient_id = st.text_input(
                    "Patient ID *",
                    help="Patient identifier for the visit"
                )
                
                study = st.text_input(
                    "Study *",
                    help="Study protocol identifier"
                )
                
                visit_name = st.text_input(
                    "Visit Name *",
                    help="Visit identifier (e.g., Screening, Week 4)"
                )
            
            with col2:
                actual_date = st.date_input(
                    "Actual Visit Date *",
                    value=datetime.now().date(),
                    help="Date when visit was completed"
                )
                
                status = st.selectbox(
                    "Visit Status",
                    options=["Completed", "Missed", "Cancelled", "Rescheduled"],
                    help="Current status of the visit"
                )
                
                site = st.text_input(
                    "Site (Optional)",
                    help="Site where visit was conducted"
                )
            
            notes = st.text_area(
                "Visit Notes (Optional)",
                help="Additional visit information"
            )
            
            submitted = st.form_submit_button("Record Visit", type="primary")
            
            if submitted:
                if _validate_visit_entry(patient_id, study, visit_name, actual_date):
                    success = _save_visit_entry({
                        'PatientID': patient_id,
                        'Study': study,
                        'VisitName': visit_name,
                        'ActualDate': actual_date,
                        'Status': status,
                        'Site': site,
                        'Notes': notes
                    })
                    
                    if success:
                        st.success("✅ Visit recorded successfully!")
                        st.rerun()
                    else:
                        st.error("❌ Failed to record visit - check error messages")
                        
    except Exception as e:
        add_error(f"Error in visit entry form: {str(e)}")

def show_batch_upload_form():
    """Form for batch data upload"""
    try:
        st.markdown("#### Batch Upload")
        st.info("💡 Upload CSV files with multiple records at once")
        
        upload_type = st.selectbox(
            "Data Type",
            options=["Patients", "Actual Visits"],
            help="Type of data to upload"
        )
        
        uploaded_file = st.file_uploader(
            f"Upload {upload_type} CSV",
            type=['csv'],
            help=f"CSV file containing {upload_type.lower()} data"
        )
        
        if uploaded_file is not None:
            try:
                # Preview the data
                df = pd.read_csv(uploaded_file)
                st.markdown("##### Data Preview")
                st.dataframe(df.head(), use_container_width=True)
                
                # Validate columns
                if upload_type == "Patients":
                    required_cols = REQUIRED_COLUMNS['patients']['required']
                else:
                    required_cols = REQUIRED_COLUMNS['actual_visits']['required']
                
                missing_cols = [col for col in required_cols if col not in df.columns]
                
                if missing_cols:
                    st.error(f"❌ Missing required columns: {', '.join(missing_cols)}")
                    st.info(f"Required columns: {', '.join(required_cols)}")
                else:
                    st.success("✅ All required columns present")
                    
                    if st.button(f"Process {len(df)} Records", type="primary"):
                        success_count = _process_batch_upload(df, upload_type.lower())
                        if success_count > 0:
                            st.success(f"✅ Successfully processed {success_count} records")
                        if success_count < len(df):
                            st.warning(f"⚠️ {len(df) - success_count} records had errors")
                            
            except Exception as e:
                st.error(f"❌ Error reading file: {str(e)}")
                
    except Exception as e:
        add_error(f"Error in batch upload form: {str(e)}")

# =============================================================================
# VALIDATION FUNCTIONS
# =============================================================================

def _validate_patient_entry(patient_id: str, study: str, start_date: date) -> bool:
    """Validate patient entry data"""
    validation_passed = True
    
    # Validate patient ID
    if not patient_id or not patient_id.strip():
        add_error("Patient ID is required")
        validation_passed = False
    elif len(patient_id) > VALIDATION_RULES['patient_id']['max_length']:
        add_error(f"Patient ID too long (max {VALIDATION_RULES['patient_id']['max_length']} characters)")
        validation_passed = False
    
    # Validate study
    if not study or not study.strip():
        add_error("Study is required")
        validation_passed = False
    elif len(study) > VALIDATION_RULES['study_name']['max_length']:
        add_error(f"Study name too long (max {VALIDATION_RULES['study_name']['max_length']} characters)")
        validation_passed = False
    
    # Validate start date
    if not start_date:
        add_error("Start date is required")
        validation_passed = False
    else:
        current_year = datetime.now().year
        min_year = VALIDATION_RULES['date_range']['min_year']
        max_year = current_year + VALIDATION_RULES['date_range']['max_years_future']
        
        if start_date.year < min_year:
            add_error(f"Start date too old (minimum year: {min_year})")
            validation_passed = False
        elif start_date.year > max_year:
            add_error(f"Start date too far in future (maximum year: {max_year})")
            validation_passed = False
    
    return validation_passed

def _validate_visit_entry(patient_id: str, study: str, visit_name: str, actual_date: date) -> bool:
    """Validate visit entry data"""
    validation_passed = True
    
    # Validate patient ID
    if not patient_id or not patient_id.strip():
        add_error("Patient ID is required")
        validation_passed = False
    
    # Validate study
    if not study or not study.strip():
        add_error("Study is required")
        validation_passed = False
    
    # Validate visit name
    if not visit_name or not visit_name.strip():
        add_error("Visit name is required")
        validation_passed = False
    elif len(visit_name) > VALIDATION_RULES['visit_name']['max_length']:
        add_error(f"Visit name too long (max {VALIDATION_RULES['visit_name']['max_length']} characters)")
        validation_passed = False
    
    # Validate actual date
    if not actual_date:
        add_error("Actual date is required")
        validation_passed = False
    else:
        current_year = datetime.now().year
        min_year = VALIDATION_RULES['date_range']['min_year']
        max_year = current_year + VALIDATION_RULES['date_range']['max_years_future']
        
        if actual_date.year < min_year:
            add_error(f"Actual date too old (minimum year: {min_year})")
            validation_passed = False
        elif actual_date.year > max_year:
            add_error(f"Actual date too far in future (maximum year: {max_year})")
            validation_passed = False
    
    return validation_passed

# =============================================================================
# DATA PERSISTENCE FUNCTIONS
# =============================================================================

def _save_patient_entry(patient_data: Dict[str, Any]) -> bool:
    """Save patient entry to session state (prepare for Supabase)"""
    try:
        # Initialize session state for manual entries
        if 'manual_patients' not in st.session_state:
            st.session_state.manual_patients = []
        
        # Clean the data
        clean_data = {
            'PatientID': clean_patient_id(patient_data['PatientID']),
            'Study': patient_data['Study'].strip(),
            'StartDate': patient_data['StartDate'],
            'Site': patient_data.get('Site', '').strip(),
            'Notes': patient_data.get('Notes', '').strip(),
            'EntryTimestamp': datetime.now(),
            'EntryMethod': 'Manual'
        }
        
        # Check for duplicates
        existing = [p for p in st.session_state.manual_patients 
                   if p['PatientID'] == clean_data['PatientID'] and p['Study'] == clean_data['Study']]
        
        if existing:
            add_warning(f"Patient {clean_data['PatientID']} already exists in {clean_data['Study']}")
            return False
        
        # Add to session state
        st.session_state.manual_patients.append(clean_data)
        add_info(f"Patient {clean_data['PatientID']} added to {clean_data['Study']}")
        
        return True
        
    except Exception as e:
        add_error(f"Error saving patient entry: {str(e)}")
        return False

def _save_visit_entry(visit_data: Dict[str, Any]) -> bool:
    """Save visit entry to session state (prepare for Supabase)"""
    try:
        # Initialize session state for manual entries
        if 'manual_visits' not in st.session_state:
            st.session_state.manual_visits = []
        
        # Clean the data
        clean_data = {
            'PatientID': clean_patient_id(visit_data['PatientID']),
            'Study': visit_data['Study'].strip(),
            'VisitName': visit_data['VisitName'].strip(),
            'ActualDate': visit_data['ActualDate'],
            'Status': visit_data.get('Status', 'Completed'),
            'Site': visit_data.get('Site', '').strip(),
            'Notes': visit_data.get('Notes', '').strip(),
            'EntryTimestamp': datetime.now(),
            'EntryMethod': 'Manual'
        }
        
        # Check for duplicates
        existing = [v for v in st.session_state.manual_visits 
                   if (v['PatientID'] == clean_data['PatientID'] and 
                       v['Study'] == clean_data['Study'] and
                       v['VisitName'] == clean_data['VisitName'])]
        
        if existing:
            add_warning(f"Visit {clean_data['VisitName']} for patient {clean_data['PatientID']} already recorded")
            return False
        
        # Add to session state
        st.session_state.manual_visits.append(clean_data)
        add_info(f"Visit {clean_data['VisitName']} recorded for patient {clean_data['PatientID']}")
        
        return True
        
    except Exception as e:
        add_error(f"Error saving visit entry: {str(e)}")
        return False

def _process_batch_upload(df: pd.DataFrame, data_type: str) -> int:
    """Process batch upload data"""
    try:
        success_count = 0
        
        if data_type == "patients":
            for index, row in df.iterrows():
                try:
                    if _validate_patient_entry(
                        str(row.get('PatientID', '')),
                        str(row.get('Study', '')),
                        pd.to_datetime(row.get('StartDate')).date()
                    ):
                        if _save_patient_entry({
                            'PatientID': row.get('PatientID'),
                            'Study': row.get('Study'),
                            'StartDate': pd.to_datetime(row.get('StartDate')).date(),
                            'Site': row.get('Site', ''),
                            'Notes': row.get('Notes', '')
                        }):
                            success_count += 1
                except Exception as e:
                    add_warning(f"Row {index + 1}: {str(e)}")
                    
        elif data_type == "actual visits":
            for index, row in df.iterrows():
                try:
                    if _validate_visit_entry(
                        str(row.get('PatientID', '')),
                        str(row.get('Study', '')),
                        str(row.get('VisitName', '')),
                        pd.to_datetime(row.get('ActualDate')).date()
                    ):
                        if _save_visit_entry({
                            'PatientID': row.get('PatientID'),
                            'Study': row.get('Study'),
                            'VisitName': row.get('VisitName'),
                            'ActualDate': pd.to_datetime(row.get('ActualDate')).date(),
                            'Status': row.get('Status', 'Completed'),
                            'Site': row.get('Site', ''),
                            'Notes': row.get('Notes', '')
                        }):
                            success_count += 1
                except Exception as e:
                    add_warning(f"Row {index + 1}: {str(e)}")
        
        return success_count
        
    except Exception as e:
        add_error(f"Error processing batch upload: {str(e)}")
        return 0

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_manual_entries_summary() -> Dict[str, int]:
    """Get summary of manual entries in session state"""
    return {
        'patients': len(st.session_state.get('manual_patients', [])),
        'visits': len(st.session_state.get('manual_visits', []))
    }

def clear_manual_entries():
    """Clear all manual entries from session state"""
    if 'manual_patients' in st.session_state:
        del st.session_state.manual_patients
    if 'manual_visits' in st.session_state:
        del st.session_state.manual_visits
    add_info("Manual entries cleared")

def export_manual_entries() -> Dict[str, pd.DataFrame]:
    """Export manual entries as DataFrames"""
    result = {}
    
    if st.session_state.get('manual_patients'):
        result['patients'] = pd.DataFrame(st.session_state.manual_patients)
    
    if st.session_state.get('manual_visits'):
        result['visits'] = pd.DataFrame(st.session_state.manual_visits)
    
    return result
