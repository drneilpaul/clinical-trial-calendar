import streamlit as st
import pandas as pd
import calendar as cal
from datetime import timedelta, date
import io

st.set_page_config(page_title="Clinical Trial Calendar Generator", layout="wide")

# Initialize session state variables
if 'show_patient_form' not in st.session_state:
    st.session_state.show_patient_form = False
if 'show_visit_form' not in st.session_state:
    st.session_state.show_visit_form = False
if 'patient_added' not in st.session_state:
    st.session_state.patient_added = False
if 'visit_added' not in st.session_state:
    st.session_state.visit_added = False

# === File Loading Helper ===
def load_file(uploaded_file):
    if uploaded_file is None:
        return None
    if uploaded_file.name.endswith(".csv"):
        return pd.read_csv(uploaded_file, dayfirst=True)
    else:
        return pd.read_excel(uploaded_file, engine="openpyxl")

# === UI ===
st.title("🏥 Clinical Trial Calendar Generator")
st.caption("v2.2.2 | Fixed: Date formatting for weekends, month ends, and financial year ends")

st.sidebar.header("📁 Upload Data Files")
patients_file = st.sidebar.file_uploader("Upload Patients File", type=['csv', 'xls', 'xlsx'], key="patients")
trials_file = st.sidebar.file_uploader("Upload Trials File", type=['csv', 'xls', 'xlsx'], key="trials")
actual_visits_file = st.sidebar.file_uploader("Upload Actual Visits File (Optional)", type=['csv', 'xls', 'xlsx'], key="actual_visits")

# Information about required columns
with st.sidebar.expander("ℹ️ Required Columns"):
    st.write("**Patients File:**")
    st.write("- PatientID, Study, StartDate")
    st.write("- Site/PatientPractice (optional)")
    st.write("")
    st.write("**Trials File:**")
    st.write("- Study, Day, VisitNo, SiteforVisit")
    st.write("- Income/Payment, ToleranceBefore, ToleranceAfter")
    st.write("")
    st.write("**Actual Visits File (Optional):**")
    st.write("- PatientID, Study, VisitNo, ActualDate")
    st.write("- ActualPayment, Notes (optional)")
    st.write("- Use 'ScreenFail' in Notes to stop future visits")

# === Main Logic ===
if patients_file and trials_file:
    # Add Patient Entry Button at the top
    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        if st.button("➕ Add New Patient", use_container_width=True):
            st.session_state.show_patient_form = True
    with col2:
        if st.button("📋 Record Visit", use_container_width=True):
            st.session_state.show_visit_form = True
    
    # Patient Entry Modal using session state
    if st.session_state.get('show_patient_form', False):
        # Check if @st.dialog is available (Streamlit 1.28+)
        try:
            @st.dialog("Add New Patient")
            def patient_entry_form():
                # Load existing data for validation
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
                        # Determine the correct data type for PatientID based on existing data
                        existing_patient_ids = existing_patients["PatientID"]
                        
                        # Check if existing IDs are numeric
                        if existing_patient_ids.dtype in ['int64', 'float64'] or all(pd.to_numeric(existing_patient_ids, errors='coerce').notna()):
                            # Convert new ID to numeric to match existing format
                            try:
                                processed_patient_id = int(new_patient_id) if new_patient_id.isdigit() else float(new_patient_id)
                            except:
                                processed_patient_id = new_patient_id  # Keep as string if conversion fails
                        else:
                            # Keep as string to match existing format
                            processed_patient_id = new_patient_id
                        
                        # Create new patient record
                        new_patient_data = {
                            "PatientID": processed_patient_id,  # Use processed ID with correct data type
                            "Study": new_study,
                            "StartDate": new_start_date,
                        }
                        
                        if patient_origin_col:
                            new_patient_data[patient_origin_col] = new_site
                        else:
                            new_patient_data["PatientPractice"] = new_site
                        
                        # Add any other columns with empty values, preserving data types
                        for col in existing_patients.columns:
                            if col not in new_patient_data:
                                # Try to preserve the data type of existing columns
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
            
        except AttributeError:
            # Fallback for older Streamlit versions without @st.dialog
            st.error("Modal dialogs require Streamlit version 1.28 or newer. Please upgrade Streamlit or use an alternative interface.")
            st.session_state.show_patient_form = False
    
    # Visit Entry Modal using session state
    if st.session_state.get('show_visit_form', False):
        @st.dialog("Record Visit")
        def visit_entry_form():
            # Load existing data
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
                    
                    from datetime import date
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
    
    # Show download button if patient was added
    if st.session_state.get('patient_added', False):
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.download_button(
                "💾 Download Updated Patients File",
                data=st.session_state.updated_patients_file,
                file_name=st.session_state.updated_filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
            if st.button("✅ Done", use_container_width=True):
                st.session_state.patient_added = False
                st.rerun()
        
        st.info("Patient added successfully! Download the updated file and re-upload to see changes in the calendar.")
        st.divider()
    
    # Show download button if visit was added
    if st.session_state.get('visit_added', False):
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.download_button(
                "💾 Download Updated Actual Visits File",
                data=st.session_state.updated_visits_file,
                file_name=st.session_state.updated_visits_filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
            if st.button("✅ Done", use_container_width=True):
                st.session_state.visit_added = False
                st.rerun()
        
        st.info("Visit recorded successfully! Download the updated file and re-upload to see changes in the calendar.")
        st.divider()
    
    try:
        # Load files
        patients_df = load_file(patients_file)
        trials_df = load_file(trials_file)
        actual_visits_df = load_file(actual_visits_file) if actual_visits_file else None

        # Clean columns
        patients_df.columns = patients_df.columns.str.strip()
        trials_df.columns = trials_df.columns.str.strip()
        if actual_visits_df is not None:
            actual_visits_df.columns = actual_visits_df.columns.str.strip()

        # Required columns check
        required_patients = {"PatientID", "Study", "StartDate"}
        required_trials = {"Study", "Day", "VisitNo"}

        if not required_patients.issubset(patients_df.columns):
            st.error(f"❌ Patients file missing required columns: {required_patients - set(patients_df.columns)}")
            st.stop()
        if not required_trials.issubset(trials_df.columns):
            st.error(f"❌ Trials file missing required columns: {required_trials - set(trials_df.columns)}")
            st.stop()

        # Check for missing studies in trials file
        patient_studies = set(patients_df["Study"].unique())
        trials_studies = set(trials_df["Study"].unique())
        missing_studies = patient_studies - trials_studies
        
        if missing_studies:
            st.error(f"⚠️ **Missing Study Definitions**: The following studies appear in your patients file but are missing from your trials file:")
            for study in sorted(missing_studies):
                patient_count = len(patients_df[patients_df["Study"] == study])
                st.write(f"   • **{study}** ({patient_count} patients)")
            
            st.warning("""
            **Action Required:** 
            - Add visit schedules for these studies to your trials file, OR
            - Remove patients with undefined studies from your patients file
            
            **Impact:** Patients with missing study definitions will be assigned to their PatientPractice site but won't have any visit schedules generated.
            """)
        
        # Show which studies are properly defined
        if trials_studies:
            defined_studies = patient_studies & trials_studies
            if defined_studies:
                st.success(f"✅ **Properly Defined Studies**: {', '.join(sorted(defined_studies))}")

        # Check for SiteforVisit column
        if "SiteforVisit" not in trials_df.columns:
            st.warning("⚠️ No 'SiteforVisit' column found in trials file. Using default site grouping.")
            trials_df["SiteforVisit"] = "Default Site"

        # Process actual visits if provided
        screen_failures = {}
        if actual_visits_df is not None:
            required_actual = {"PatientID", "Study", "VisitNo", "ActualDate"}
            if not required_actual.issubset(actual_visits_df.columns):
                st.error(f"❌ Actual visits file missing required columns: {required_actual}")
                st.stop()
            
            # Process actual visits data
            actual_visits_df["PatientID"] = actual_visits_df["PatientID"].astype(str)
            actual_visits_df["Study"] = actual_visits_df["Study"].astype(str)
            actual_visits_df["ActualDate"] = pd.to_datetime(actual_visits_df["ActualDate"], dayfirst=True, errors="coerce")
            
            # Handle optional columns
            if "ActualPayment" not in actual_visits_df.columns:
                actual_visits_df["ActualPayment"] = None
            if "Notes" not in actual_visits_df.columns:
                actual_visits_df["Notes"] = ""
            else:
                actual_visits_df["Notes"] = actual_visits_df["Notes"].fillna("").astype(str)
            
            # Detect screen failures
            screen_fail_visits = actual_visits_df[
                actual_visits_df["Notes"].str.contains("ScreenFail", case=False, na=False)
            ]
            
            for _, visit in screen_fail_visits.iterrows():
                patient_study_key = f"{visit['PatientID']}_{visit['Study']}"
                screen_fail_date = visit['ActualDate']
                if patient_study_key not in screen_failures or screen_fail_date < screen_failures[patient_study_key]:
                    screen_failures[patient_study_key] = screen_fail_date
            
            if len(screen_failures) > 0:
                st.info(f"📋 Detected {len(screen_failures)} screen failure(s) - future visits will be excluded after these dates")
            
            # Create lookup key for actual visits
            actual_visits_df["VisitKey"] = (
                actual_visits_df["PatientID"] + "_" + 
                actual_visits_df["Study"] + "_" + 
                actual_visits_df["VisitNo"].astype(str)
            )
            
            st.info(f"✅ Loaded {len(actual_visits_df)} actual visit records")
        else:
            st.info("ℹ️ No actual visits file provided - showing scheduled visits only")

        # Normalize column names
        column_mapping = {
            'Income': 'Payment',
            'Tolerance Before': 'ToleranceBefore',
            'Tolerance After': 'ToleranceAfter',
            'Visit No': 'VisitNo',
            'VisitNumber': 'VisitNo'
        }
        trials_df = trials_df.rename(columns=column_mapping)

        # Process patient data types
        patients_df["PatientID"] = patients_df["PatientID"].astype(str)
        patients_df["Study"] = patients_df["Study"].astype(str)
        patients_df["StartDate"] = pd.to_datetime(patients_df["StartDate"], dayfirst=True, errors="coerce")
        
        trials_df["Study"] = trials_df["Study"].astype(str)
        trials_df["SiteforVisit"] = trials_df["SiteforVisit"].astype(str)

        # Check for patient origin site column
        patient_origin_col = None
        possible_origin_cols = ['PatientSite', 'OriginSite', 'Practice', 'PatientPractice', 'HomeSite', 'Site']
        for col in possible_origin_cols:
            if col in patients_df.columns:
                patient_origin_col = col
                break
        
        if patient_origin_col:
            patients_df['OriginSite'] = patients_df[patient_origin_col].astype(str)
        else:
            st.warning("No patient origin site column found.")
            patients_df['OriginSite'] = "Unknown Origin"

        # Create patient-site mapping - use patient origin site directly instead of trials mapping
        if patient_origin_col:
            patients_df['Site'] = patients_df['OriginSite']
        else:
            # Fallback: try to map from trials, but prioritize patient's own site info
            patient_site_mapping = {}
            for _, patient in patients_df.iterrows():
                patient_id = patient["PatientID"]
                study = patient["Study"]
                
                # First try to get site from trials file for this study
                study_sites = trials_df[trials_df["Study"] == study]["SiteforVisit"].unique()
                if len(study_sites) > 0:
                    patient_site_mapping[patient_id] = study_sites[0]
                else:
                    # If study not found in trials, use a default based on study name
                    patient_site_mapping[patient_id] = f"{study}_Site"
            
            patients_df['Site'] = patients_df['PatientID'].map(patient_site_mapping)

        # Build visit records with recalculation logic
        visit_records = []
        screen_fail_exclusions = 0
        actual_visits_used = 0
        recalculated_patients = []
        out_of_window_visits = []
        patients_with_no_visits = []
        processing_messages = []  # Initialize processing messages list here
        
        for _, patient in patients_df.iterrows():
            patient_id = patient["PatientID"]
            study = patient["Study"]
            start_date = patient["StartDate"]
            patient_origin = patient["OriginSite"]
            
            # Check if this patient has a screen failure
            patient_study_key = f"{patient_id}_{study}"
            screen_fail_date = screen_failures.get(patient_study_key)

            if pd.isna(start_date):
                continue

            # Get all visits for this study and sort by visit number/day
            study_visits = trials_df[trials_df["Study"] == study].sort_values(['VisitNo', 'Day']).copy()
            
            # Check if this study has any visit definitions
            if len(study_visits) == 0:
                patients_with_no_visits.append(f"{patient_id} (Study: {study})")
                continue  # Skip this patient as no visit schedule is defined
            
            # Get all actual visits for this patient
            patient_actual_visits = {}
            if actual_visits_df is not None:
                patient_actuals = actual_visits_df[
                    (actual_visits_df["PatientID"] == str(patient_id)) & 
                    (actual_visits_df["Study"] == study)
                ].sort_values('VisitNo')
                
                for _, actual_visit in patient_actuals.iterrows():
                    visit_no = actual_visit["VisitNo"]
                    patient_actual_visits[visit_no] = actual_visit
            
            # Process each visit with recalculation logic
            current_baseline_date = start_date
            current_baseline_visit = 0
            patient_needs_recalc = False
            
            for _, visit in study_visits.iterrows():
                try:
                    visit_day = int(visit["Day"])
                    visit_no = visit.get("VisitNo", "")
                except Exception:
                    continue
                
                # Check if we have an actual visit for this visit number
                actual_visit_data = patient_actual_visits.get(visit_no)
                
                if actual_visit_data is not None:
                    # This is an actual visit
                    visit_date = actual_visit_data["ActualDate"]
                    payment = float(actual_visit_data.get("ActualPayment") or visit.get("Payment", 0) or 0.0)
                    notes = actual_visit_data.get("Notes", "")
                    
                    # Calculate expected date for validation
                    if current_baseline_visit == 0:
                        expected_date = start_date + timedelta(days=visit_day)
                    else:
                        baseline_visit_data = study_visits[study_visits["VisitNo"] == current_baseline_visit].iloc[0]
                        baseline_day = int(baseline_visit_data["Day"])
                        day_diff = visit_day - baseline_day
                        expected_date = current_baseline_date + timedelta(days=day_diff)
                    
                    # Check if actual visit is outside tolerance window
                    tolerance_before = int(visit.get("ToleranceBefore", 0) or 0)
                    tolerance_after = int(visit.get("ToleranceAfter", 0) or 0)
                    earliest_acceptable = expected_date - timedelta(days=tolerance_before)
                    latest_acceptable = expected_date + timedelta(days=tolerance_after)
                    
                    is_out_of_window = visit_date < earliest_acceptable or visit_date > latest_acceptable
                    if is_out_of_window:
                        days_early = max(0, (earliest_acceptable - visit_date).days)
                        days_late = max(0, (visit_date - latest_acceptable).days)
                        deviation = days_early + days_late
                        out_of_window_visits.append({
                            'patient': f"{patient_id} ({study})",
                            'visit': f"V{visit_no}",
                            'expected': expected_date.strftime('%Y-%m-%d'),
                            'actual': visit_date.strftime('%Y-%m-%d'),
                            'deviation': f"{deviation} days {'early' if days_early > 0 else 'late'}",
                            'tolerance': f"+{tolerance_after}/-{tolerance_before} days"
                        })
                    
                    # Update baseline for future calculations
                    original_scheduled_date = start_date + timedelta(days=visit_day)
                    if visit_date != original_scheduled_date:
                        patient_needs_recalc = True
                    
                    current_baseline_date = visit_date
                    current_baseline_visit = visit_no
                    
                    # Mark visit status based on notes and window compliance
                    # Convert visit_no to int to remove .0 decimal
                    visit_no_clean = int(float(visit_no)) if pd.notna(visit_no) else visit_no
                    
                    if "ScreenFail" in str(notes):
                        visit_status = f"❌ Screen Fail {visit_no_clean}"
                    elif is_out_of_window:
                        visit_status = f"⚠️ Visit {visit_no_clean}"
                    else:
                        visit_status = f"✅ Visit {visit_no_clean}"
                    
                    # Check if actual visit is after screen failure
                    if screen_fail_date is not None and visit_date > screen_fail_date:
                        screen_fail_exclusions += 1
                        continue
                    
                    actual_visits_used += 1
                    
                    # Record the actual visit
                    site = visit.get("SiteforVisit", "Unknown Site")
                    
                    visit_records.append({
                        "Date": visit_date,
                        "PatientID": patient_id,
                        "Visit": visit_status,
                        "Study": study,
                        "Payment": payment,
                        "SiteofVisit": site,
                        "PatientOrigin": patient_origin,
                        "IsActual": True,
                        "IsScreenFail": "ScreenFail" in str(actual_visit_data.get("Notes", "")),
                        "IsOutOfWindow": is_out_of_window
                    })
                    
                else:
                    # This is a scheduled visit
                    if current_baseline_visit == 0:
                        scheduled_date = start_date + timedelta(days=visit_day)
                    else:
                        baseline_visit_data = study_visits[study_visits["VisitNo"] == current_baseline_visit].iloc[0]
                        baseline_day = int(baseline_visit_data["Day"])
                        day_diff = visit_day - baseline_day
                        scheduled_date = current_baseline_date + timedelta(days=day_diff)
                    
                    # Check if visit date is after screen failure date
                    if screen_fail_date is not None and scheduled_date > screen_fail_date:
                        screen_fail_exclusions += 1
                        continue
                    
                    visit_date = scheduled_date
                    payment = float(visit.get("Payment", 0) or 0.0)
                    # Convert visit_no to int to remove .0 decimal  
                    visit_no_clean = int(float(visit_no)) if pd.notna(visit_no) else visit_no
                    visit_status = f"Visit {visit_no_clean}"
                    
                    tol_before = int(visit.get("ToleranceBefore", 0) or 0)
                    tol_after = int(visit.get("ToleranceAfter", 0) or 0)
                    site = visit.get("SiteforVisit", "Unknown Site")
                    
                    # Add main visit + tolerance periods
                    visit_records.append({
                        "Date": visit_date,
                        "PatientID": patient_id,
                        "Visit": visit_status,
                        "Study": study,
                        "Payment": payment,
                        "SiteofVisit": site,
                        "PatientOrigin": patient_origin,
                        "IsActual": False,
                        "IsScreenFail": False,
                        "IsOutOfWindow": False
                    })

                    # Tolerance periods
                    for i in range(1, tol_before + 1):
                        tolerance_date = visit_date - timedelta(days=i)
                        if screen_fail_date is not None and tolerance_date > screen_fail_date:
                            continue
                        visit_records.append({
                            "Date": tolerance_date,
                            "PatientID": patient_id,
                            "Visit": "-",
                            "Study": study,
                            "Payment": 0,
                            "SiteofVisit": site,
                            "PatientOrigin": patient_origin,
                            "IsActual": False,
                            "IsScreenFail": False,
                            "IsOutOfWindow": False
                        })

                    for i in range(1, tol_after + 1):
                        tolerance_date = visit_date + timedelta(days=i)
                        if screen_fail_date is not None and tolerance_date > screen_fail_date:
                            continue
                        visit_records.append({
                            "Date": tolerance_date,
                            "PatientID": patient_id,
                            "Visit": "+",
                            "Study": study,
                            "Payment": 0,
                            "SiteofVisit": site,
                            "PatientOrigin": patient_origin,
                            "IsActual": False,
                            "IsScreenFail": False,
                            "IsOutOfWindow": False
                        })
            
            # Track patients that had recalculations
            if patient_needs_recalc:
                recalculated_patients.append(f"{patient_id} ({study})")

        # Create visits DataFrame
        visits_df = pd.DataFrame(visit_records)

        if visits_df.empty:
            st.error("❌ No visits generated. Check that Patient `Study` matches Trial `Study` values and StartDate is populated.")
            st.stop()

        # Collect processing messages
        if len(patients_with_no_visits) > 0:
            processing_messages.append(f"⚠️ {len(patients_with_no_visits)} patient(s) skipped due to missing study definitions: {', '.join(patients_with_no_visits)}")
            
        if len(recalculated_patients) > 0:
            processing_messages.append(f"📅 Recalculated visit schedules for {len(recalculated_patients)} patient(s): {', '.join(recalculated_patients)}")

        if len(out_of_window_visits) > 0:
            processing_messages.append(f"⚠️ {len(out_of_window_visits)} visit(s) occurred outside tolerance windows")

        if actual_visits_df is not None:
            processing_messages.append(f"✅ {actual_visits_used} actual visits matched and used in calendar")
            unmatched_actual = len(actual_visits_df) - actual_visits_used
            if unmatched_actual > 0:
                processing_messages.append(f"⚠️ {unmatched_actual} actual visit records could not be matched to scheduled visits")

        if screen_fail_exclusions > 0:
            processing_messages.append(f"⚠️ {screen_fail_exclusions} visits were excluded because they occur after screen failure dates.")

        # Collect final processing statistics
        total_visit_records = len(visit_records)
        total_scheduled_visits = len([v for v in visit_records if not v.get('IsActual', False) and v['Visit'] not in ['-', '+']])
        total_tolerance_periods = len([v for v in visit_records if v['Visit'] in ['-', '+']])
        
        processing_messages.append(f"Generated {total_visit_records} total calendar entries ({total_scheduled_visits} scheduled visits, {total_tolerance_periods} tolerance periods)")
        
        if actual_visits_df is not None:
            actual_visit_entries = len([v for v in visit_records if v.get('IsActual', False)])
            processing_messages.append(f"Calendar includes {actual_visit_entries} actual visits and {total_scheduled_visits} scheduled visits")
            
            if actual_visits_used < len(actual_visits_df):
                processing_messages.append(f"Visit matching: {actual_visits_used} matched, {len(actual_visits_df) - actual_visits_used} unmatched")
        
        # Date range statistics
        if not visits_df.empty:
            earliest_date = visits_df["Date"].min()
            latest_date = visits_df["Date"].max()
            date_range_days = (latest_date - earliest_date).days
            processing_messages.append(f"Calendar spans {date_range_days} days ({earliest_date.strftime('%Y-%m-%d')} to {latest_date.strftime('%Y-%m-%d')})")
        
        # Get patient studies for study completion statistics
        patient_studies = patients_df["Study"].unique()
        
        # Study completion statistics (with safety checks)
        if actual_visits_df is not None and len(actual_visits_df) > 0:
            study_stats = []
            for study in patient_studies:
                study_patients = patients_df[patients_df["Study"] == study]
                study_actual_visits = actual_visits_df[actual_visits_df["Study"] == study]
                
                if len(study_patients) > 0:  # Prevent division by zero
                    if len(study_actual_visits) > 0:
                        completion_rate = (len(study_actual_visits) / len(study_patients)) * 100
                        study_stats.append(f"{study}: {completion_rate:.1f}% visit activity")
                    else:
                        study_stats.append(f"{study}: 0% visit activity")
            
            if study_stats:
                processing_messages.append(f"Study activity rates: {', '.join(study_stats)}")
        
        # Financial statistics (with safety checks)
        financial_df = visits_df[
            (visits_df['Visit'].str.startswith("✅")) |
            (visits_df['Visit'].str.startswith("❌ Screen Fail")) |
            (visits_df['Visit'].str.contains('Visit', na=False) & (~visits_df.get('IsActual', False)))
        ].copy()
        
        actual_financial = financial_df[financial_df.get('IsActual', False)]
        scheduled_financial = financial_df[~financial_df.get('IsActual', True)]
        
        if not financial_df.empty:
            total_income = financial_df["Payment"].sum()
            processing_messages.append(f"Total financial value: £{total_income:,.2f}")
            
            if actual_visits_df is not None and len(actual_financial) > 0:
                actual_income = actual_financial["Payment"].sum()
                scheduled_income = scheduled_financial["Payment"].sum() if len(scheduled_financial) > 0 else 0
                processing_messages.append(f"Income breakdown: £{actual_income:,.2f} actual, £{scheduled_income:,.2f} projected")

        # Processing Log (expandable)
        with st.expander("📋 View Processing Log", expanded=False):
            for message in processing_messages:
                st.write(message)
            
            # Show out of window visits detail if any
            if len(out_of_window_visits) > 0:
                st.write("**Out-of-Window Visit Details:**")
                oow_df = pd.DataFrame(out_of_window_visits)
                st.dataframe(oow_df, use_container_width=True)

        # Build calendar
        min_date = visits_df["Date"].min() - timedelta(days=1)
        max_date = visits_df["Date"].max() + timedelta(days=1)
        calendar_dates = pd.date_range(start=min_date, end=max_date)
        calendar_df = pd.DataFrame({"Date": calendar_dates})
        calendar_df["Day"] = calendar_df["Date"].dt.day_name()

        # Group patients by site
        patients_df["ColumnID"] = patients_df["Study"] + "_" + patients_df["PatientID"]
        unique_sites = sorted(patients_df["Site"].unique())
        
        # Create ordered columns
        ordered_columns = ["Date", "Day"]
        site_column_mapping = {}
        
        for site in unique_sites:
            site_patients = patients_df[patients_df["Site"] == site].sort_values(["Study", "PatientID"])
            site_columns = []
            for _, patient in site_patients.iterrows():
                col_id = patient["ColumnID"]
                ordered_columns.append(col_id)
                site_columns.append(col_id)
                calendar_df[col_id] = ""
            site_column_mapping[site] = site_columns

        # Create income tracking columns
        for study in trials_df["Study"].unique():
            income_col = f"{study} Income"
            calendar_df[income_col] = 0.0
        
        calendar_df["Daily Total"] = 0.0

        # Fill calendar with color-coded visit information
        for i, row in calendar_df.iterrows():
            date = row["Date"]
            visits_today = visits_df[visits_df["Date"] == date]
            daily_total = 0.0

            for _, visit in visits_today.iterrows():
                study = str(visit["Study"])
                pid = str(visit["PatientID"])
                col_id = f"{study}_{pid}"
                visit_info = visit["Visit"]
                payment = float(visit["Payment"]) or 0.0
                is_actual = visit.get("IsActual", False)
                is_screen_fail = visit.get("IsScreenFail", False)
                is_out_of_window = visit.get("IsOutOfWindow", False)

                if col_id in calendar_df.columns:
                    # Handle concatenation more carefully to avoid "Visit 1, -" issues
                    current_value = calendar_df.at[i, col_id]
                    
                    if current_value == "":
                        calendar_df.at[i, col_id] = visit_info
                    else:
                        # Only concatenate if it's not a tolerance period conflicting with main visit
                        if visit_info in ["-", "+"]:
                            # Don't add tolerance symbols if there's already a main visit
                            if not any(x in current_value for x in ["Visit", "✅", "⚠️", "❌"]):
                                calendar_df.at[i, col_id] = visit_info if current_value in ["-", "+"] else f"{current_value}, {visit_info}"
                        else:
                            # This is a main visit - replace any tolerance periods
                            if current_value in ["-", "+", "", "-", "+"]:
                                calendar_df.at[i, col_id] = visit_info
                            else:
                                calendar_df.at[i, col_id] = f"{current_value}, {visit_info}"

                # Count payments for actual visits and scheduled main visits (not tolerance periods)
                if (is_actual) or (not is_actual and visit_info not in ("-", "+")):
                    income_col = f"{study} Income"
                    if income_col in calendar_df.columns:
                        calendar_df.at[i, income_col] += payment
                        daily_total += payment

            calendar_df.at[i, "Daily Total"] = daily_total

        # Calculate totals
        calendar_df["MonthPeriod"] = calendar_df["Date"].dt.to_period("M")
        monthly_totals = calendar_df.groupby("MonthPeriod")["Daily Total"].sum()
        calendar_df["IsMonthEnd"] = calendar_df["Date"] == calendar_df["Date"] + pd.offsets.MonthEnd(0)
        calendar_df["Monthly Total"] = calendar_df.apply(
            lambda r: monthly_totals.get(r["MonthPeriod"], 0.0) if r["IsMonthEnd"] else pd.NA, axis=1
        )

        calendar_df["FYStart"] = calendar_df["Date"].apply(lambda d: d.year if d.month >= 4 else d.year - 1)
        fy_totals = calendar_df.groupby("FYStart")["Daily Total"].sum()
        calendar_df["IsFYE"] = (calendar_df["Date"].dt.month == 3) & (calendar_df["Date"].dt.day == 31)
        calendar_df["FY Total"] = calendar_df.apply(
            lambda r: fy_totals.get(r["FYStart"], 0.0) if r["IsFYE"] else pd.NA, axis=1
        )

        # Prepare display
        final_ordered_columns = [col for col in ordered_columns if col in calendar_df.columns and 
                                not any(x in col for x in ["Income", "Total"])]
        calendar_df_display = calendar_df[final_ordered_columns].copy()

        # Display site information
        st.subheader("Site Summary")
        site_summary_data = []
        for site in unique_sites:
            site_patients = patients_df[patients_df["Site"] == site]
            site_studies = site_patients["Study"].unique()
            
            site_screen_fails = 0
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
        
        site_summary_df = pd.DataFrame(site_summary_data)
        st.dataframe(site_summary_df, use_container_width=True)

        # Display legend with updated color coding
        if actual_visits_df is not None:
            st.info("""
            **Legend with Color Coding:**
            
            **Actual Visits:**
            - ✅ Visit X (Green background) = Completed Visit (within tolerance window)  
            - ⚠️ Visit X (Yellow background) = Completed Visit (outside tolerance window)
            - ❌ Screen Fail X (Red background) = Screen failure (no future visits)
            
            **Scheduled Visits:**
            - Visit X (Gray background) = Scheduled/Planned Visit
            - \\- (Light blue-gray, italic) = Before tolerance period
            - \\+ (Light blue-gray, italic) = After tolerance period
            
            **Date Formatting:**
            - Light blue background = Month end (softer highlighting)
            - Dark blue background = Financial year end (31 March)
            - Gray background = Weekend
            - Blue separator lines = Month boundaries (screen only)
            """)
        else:
            st.info("""
            **Legend:** 
            - Visit X (Gray) = Scheduled Visit
            - - (Light blue-gray) = Before tolerance period
            - + (Light blue-gray) = After tolerance period
            - Light blue background = Month end (softer highlighting)
            - Dark blue background = Financial year end (31 March)
            - Gray background = Weekend
            - Blue separator lines = Month boundaries (screen only)
            """)

        # Display calendar with site headers and improved styling
        st.subheader("Generated Visit Calendar")
        display_df = calendar_df_display.copy()
        display_df_for_view = display_df.copy()
        display_df_for_view["Date"] = display_df_for_view["Date"].dt.strftime("%Y-%m-%d")

        # Create site header row
        site_header_row = {}
        for col in display_df_for_view.columns:
            if col in ["Date", "Day"]:
                site_header_row[col] = ""
            else:
                site_found = ""
                for site in unique_sites:
                    if col in site_column_mapping.get(site, []):
                        site_found = site
                        break
                site_header_row[col] = site_found

        # Combine header with data
        site_header_df = pd.DataFrame([site_header_row])
        display_with_header = pd.concat([site_header_df, display_df_for_view], ignore_index=True)

        # Create improved styling function with better colors
        def highlight_with_header_fixed(row):
            if row.name == 0:  # Site header row
                styles = []
                for col_name in row.index:
                    if row[col_name] != "":
                        styles.append('background-color: #e6f3ff; font-weight: bold; text-align: center; border: 1px solid #ccc;')
                    else:
                        styles.append('background-color: #f8f9fa; border: 1px solid #ccc;')
                return styles
            else:
                # Data rows - first apply date-based styling, then visit-specific styling
                styles = []
                
                # Get the actual date for this row
                date_str = row.get("Date", "")
                date_obj = None
                try:
                    if date_str:
                        date_obj = pd.to_datetime(date_str)
                except:
                    pass
                
                for col_idx, (col_name, cell_value) in enumerate(row.items()):
                    style = ""
                    
                    # First check for date-based styling (applies to entire row)
                    if date_obj is not None and not pd.isna(date_obj):
                        # Financial year end (31 March) - highest priority
                        if date_obj.month == 3 and date_obj.day == 31:
                            style = 'background-color: #1e40af; color: white; font-weight: bold;'
                        # Month end - softer blue, second priority  
                        elif date_obj == date_obj + pd.offsets.MonthEnd(0):
                            style = 'background-color: #60a5fa; color: white; font-weight: normal;'
                        # Weekend - more obvious gray, third priority
                        elif date_obj.weekday() in (5, 6):  # Saturday=5, Sunday=6
                            style = 'background-color: #e5e7eb;'
                    
                    # Only apply visit-specific styling if no date styling was applied
                    if style == "" and col_name not in ["Date", "Day"] and str(cell_value) != "":
                        cell_str = str(cell_value)
                        
                        # Visit-specific color coding
                        if "✅ Visit" in cell_str:  # Completed visits
                            style = 'background-color: #d4edda; color: #155724; font-weight: bold;'
                        elif "⚠️ Visit" in cell_str:  # Out of window visits
                            style = 'background-color: #fff3cd; color: #856404; font-weight: bold;'
                        elif "❌ Screen Fail" in cell_str:  # Screen failures
                            style = 'background-color: #f8d7da; color: #721c24; font-weight: bold;'
                        elif "Visit " in cell_str and not cell_str.startswith("✅") and not cell_str.startswith("⚠️"):  # Scheduled
                            style = 'background-color: #e2e3e5; color: #383d41; font-weight: normal;'
                        elif cell_str in ["+", "-"]:  # Tolerance periods - different from weekends
                            style = 'background-color: #f1f5f9; color: #64748b; font-style: italic; font-size: 0.9em;'
                    
                    styles.append(style)
                
                return styles

        try:
            styled_df = display_with_header.style.apply(highlight_with_header_fixed, axis=1)
            
            # Add month separators by modifying the HTML
            html_table_base = styled_df.to_html(escape=False)
            
            # Add month separators in the HTML by finding month boundaries
            html_lines = html_table_base.split('\n')
            modified_html_lines = []
            
            prev_month = None
            for i, line in enumerate(html_lines):
                # Check if this is a data row with a date
                if '<td>' in line and len(html_lines) > i+1:
                    # Try to extract date from the line
                    date_match = None
                    import re
                    date_pattern = r'<td>(\d{4}-\d{2}-\d{2})</td>'
                    match = re.search(date_pattern, line)
                    if match:
                        try:
                            date_obj = pd.to_datetime(match.group(1))
                            current_month = date_obj.to_period('M')
                            
                            # Add separator line if month changed
                            if prev_month is not None and current_month != prev_month:
                                # Count columns for proper separator
                                col_count = line.count('<td>')
                                separator_line = f'<tr style="border-top: 3px solid #3b82f6; background-color: #eff6ff;"><td colspan="{col_count}" style="text-align: center; font-weight: bold; color: #1e40af; padding: 2px;">{current_month}</td></tr>'
                                modified_html_lines.append(separator_line)
                            
                            prev_month = current_month
                        except:
                            pass
                
                modified_html_lines.append(line)
            
            html_table_with_separators = '\n'.join(modified_html_lines)
            
            import streamlit.components.v1 as components
            html_table = f"""
            <div style='max-height: 700px; overflow: auto; border: 1px solid #ddd;'>
                {html_table_with_separators}
            </div>
            """
            components.html(html_table, height=720, scrolling=True)
        except Exception as e:
            st.write(f"Styling error: {e}")
            st.dataframe(display_with_header, use_container_width=True)

        # Financial Analysis
        st.subheader("💰 Financial Analysis")
        
        if not actual_financial.empty:
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                actual_income = actual_financial['Payment'].sum()
                st.metric("Actual Income (Completed)", f"£{actual_income:,.2f}")
            with col2:
                scheduled_income = scheduled_financial['Payment'].sum()
                st.metric("Scheduled Income (Pending)", f"£{scheduled_income:,.2f}")
            with col3:
                total_income = actual_income + scheduled_income
                st.metric("Total Income", f"£{total_income:,.2f}")
            with col4:
                screen_fail_count = len(actual_financial[actual_financial.get('IsScreenFail', False)])
                st.metric("Screen Failures", screen_fail_count)
            
            completion_rate = (len(actual_financial) / len(financial_df)) * 100 if len(financial_df) > 0 else 0
            st.metric("Visit Completion Rate", f"{completion_rate:.1f}%")

        # Monthly income analysis
        financial_df['MonthYear'] = financial_df['Date'].dt.to_period('M')
        financial_df['Quarter'] = financial_df['Date'].dt.quarter
        financial_df['Year'] = financial_df['Date'].dt.year
        financial_df['QuarterYear'] = financial_df['Year'].astype(str) + '-Q' + financial_df['Quarter'].astype(str)
        
        # Add financial year calculation
        financial_df['FinancialYear'] = financial_df['Date'].apply(
            lambda d: f"{d.year}-{d.year+1}" if d.month >= 4 else f"{d.year-1}-{d.year}"
        )
        
        # Monthly analysis with financial year totals
        monthly_income_by_site = financial_df.groupby(['SiteofVisit', 'MonthYear'])['Payment'].sum().reset_index()
        monthly_pivot = monthly_income_by_site.pivot(index='MonthYear', columns='SiteofVisit', values='Payment').fillna(0)
        monthly_pivot['Total'] = monthly_pivot.sum(axis=1)
        
        # Add financial year totals to monthly data
        fy_monthly_totals = []
        for fy in sorted(financial_df['FinancialYear'].unique()):
            fy_data = financial_df[financial_df['FinancialYear'] == fy]
            fy_income_by_site = fy_data.groupby('SiteofVisit')['Payment'].sum()
            
            fy_row = {}
            for site in monthly_pivot.columns:
                if site == 'Total':
                    fy_row[site] = fy_income_by_site.sum()
                else:
                    fy_row[site] = fy_income_by_site.get(site, 0)
            
            fy_monthly_totals.append((f"FY {fy}", fy_row))
        
        # Quarterly analysis with financial year totals  
        quarterly_income_by_site = financial_df.groupby(['SiteofVisit', 'QuarterYear'])['Payment'].sum().reset_index()
        quarterly_pivot = quarterly_income_by_site.pivot(index='QuarterYear', columns='SiteofVisit', values='Payment').fillna(0)
        quarterly_pivot['Total'] = quarterly_pivot.sum(axis=1)
        
        # Add financial year totals to quarterly data (same as monthly FY totals)
        fy_quarterly_totals = fy_monthly_totals  # Same data, different context
        
        # Monthly Income Chart
        st.subheader("📊 Monthly Income Chart")
        monthly_chart_data = monthly_pivot[[col for col in monthly_pivot.columns if col != 'Total']]
        monthly_chart_data.index = monthly_chart_data.index.astype(str)
        st.bar_chart(monthly_chart_data)
        
        # Display financial tables with FY totals
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**Monthly Income by Visit Site**")
            monthly_display = monthly_pivot.copy()
            monthly_display.index = monthly_display.index.astype(str)
            
            # Format currency
            for col in monthly_display.columns:
                monthly_display[col] = monthly_display[col].apply(lambda x: f"£{x:,.2f}" if x != 0 else "£0.00")
            
            st.dataframe(monthly_display, use_container_width=True)
            
            # Add financial year totals for monthly
            if fy_monthly_totals:
                st.write("**Financial Year Totals**")
                fy_monthly_data = []
                for fy_name, fy_row in fy_monthly_totals:
                    formatted_row = {"Financial Year": fy_name}
                    for col, val in fy_row.items():
                        formatted_row[col] = f"£{val:,.2f}" if val != 0 else "£0.00"
                    fy_monthly_data.append(formatted_row)
                
                fy_monthly_df = pd.DataFrame(fy_monthly_data)
                st.dataframe(fy_monthly_df, use_container_width=True)
        
        with col2:
            st.write("**Quarterly Income by Visit Site**")
            quarterly_display = quarterly_pivot.copy()
            
            # Format currency
            for col in quarterly_display.columns:
                quarterly_display[col] = quarterly_display[col].apply(lambda x: f"£{x:,.2f}" if x != 0 else "£0.00")
            
            st.dataframe(quarterly_display, use_container_width=True)
            
            # Add financial year totals for quarterly  
            if fy_quarterly_totals:
                st.write("**Financial Year Totals**")
                fy_quarterly_data = []
                for fy_name, fy_row in fy_quarterly_totals:
                    formatted_row = {"Financial Year": fy_name}
                    for col, val in fy_row.items():
                        formatted_row[col] = f"£{val:,.2f}" if val != 0 else "£0.00"
                    fy_quarterly_data.append(formatted_row)
                
                fy_quarterly_df = pd.DataFrame(fy_quarterly_data)
                st.dataframe(fy_quarterly_df, use_container_width=True)

        # Summary totals by site only (no grand total)
        st.write("**Financial Summary by Site**")
        total_by_site = financial_df.groupby('SiteofVisit')['Payment'].sum()
        summary_data = []
        for site in total_by_site.index:
            summary_data.append({
                "Site": site,
                "Total Income": f"£{total_by_site[site]:,.2f}"
            })
        
        summary_df = pd.DataFrame(summary_data)
        st.dataframe(summary_df, use_container_width=True)

        # Quarterly Profit Sharing Analysis
        st.subheader("📊 Quarterly Profit Sharing Analysis")
        
        # Fixed list sizes and weights for calculations
        ashfields_list_size = 28500
        kiltearn_list_size = 12500
        total_list_size = ashfields_list_size + kiltearn_list_size
        ashfields_list_ratio = ashfields_list_size / total_list_size
        kiltearn_list_ratio = kiltearn_list_size / total_list_size
        list_weight = 0.35
        work_weight = 0.35
        recruitment_weight = 0.30
        
        # Create quarterly data with financial years
        financial_df['Quarter'] = financial_df['Date'].dt.quarter
        financial_df['Year'] = financial_df['Date'].dt.year
        financial_df['QuarterYear'] = financial_df['Year'].astype(str) + '-Q' + financial_df['Quarter'].astype(str)
        
        # Calculate financial year (April to March)
        financial_df['FinancialYear'] = financial_df['Date'].apply(
            lambda d: f"{d.year}-{d.year+1}" if d.month >= 4 else f"{d.year-1}-{d.year}"
        )
        
        # Get unique quarters and financial years
        quarters = sorted(financial_df['QuarterYear'].unique())
        financial_years = sorted(financial_df['FinancialYear'].unique())
        
        if len(quarters) > 0:
            quarterly_ratios = []
            
            # Process quarterly data
            for quarter in quarters:
                quarter_data = financial_df[financial_df['QuarterYear'] == quarter]
                
                # Skip if no data
                if len(quarter_data) == 0:
                    continue
                
                # Work done ratios for this quarter
                quarter_site_work = quarter_data.groupby('SiteofVisit').size()
                quarter_total_work = quarter_site_work.sum()
                
                q_ashfields_work_ratio = quarter_site_work.get('Ashfields', 0) / quarter_total_work if quarter_total_work > 0 else 0
                q_kiltearn_work_ratio = quarter_site_work.get('Kiltearn', 0) / quarter_total_work if quarter_total_work > 0 else 0
                
                # Patient recruitment ratios for this quarter
                quarter_recruitment = quarter_data.groupby('PatientOrigin').agg({'PatientID': 'nunique'})
                quarter_total_patients = quarter_recruitment['PatientID'].sum()
                
                q_ashfields_recruitment_ratio = quarter_recruitment.loc['Ashfields', 'PatientID'] / quarter_total_patients if 'Ashfields' in quarter_recruitment.index and quarter_total_patients > 0 else 0
                q_kiltearn_recruitment_ratio = quarter_recruitment.loc['Kiltearn', 'PatientID'] / quarter_total_patients if 'Kiltearn' in quarter_recruitment.index and quarter_total_patients > 0 else 0
                
                # Calculate weighted ratios (list sizes remain constant)
                q_ashfields_final_ratio = (ashfields_list_ratio * list_weight + 
                                          q_ashfields_work_ratio * work_weight + 
                                          q_ashfields_recruitment_ratio * recruitment_weight)
                
                q_kiltearn_final_ratio = (kiltearn_list_ratio * list_weight + 
                                         q_kiltearn_work_ratio * work_weight + 
                                         q_kiltearn_recruitment_ratio * recruitment_weight)
                
                # Normalize to ensure they sum to 100%
                q_total_ratio = q_ashfields_final_ratio + q_kiltearn_final_ratio
                if q_total_ratio > 0:
                    q_ashfields_final_ratio = q_ashfields_final_ratio / q_total_ratio
                    q_kiltearn_final_ratio = q_kiltearn_final_ratio / q_total_ratio
                
                # Calculate quarterly income
                quarter_income = quarter_data['Payment'].sum()
                
                # Calculate income by site for this quarter
                quarter_income_by_site = quarter_data.groupby('SiteofVisit')['Payment'].sum()
                ashfields_quarter_income = quarter_income_by_site.get('Ashfields', 0)
                kiltearn_quarter_income = quarter_income_by_site.get('Kiltearn', 0)
                
                # Get financial year for this quarter
                fy = quarter_data['FinancialYear'].iloc[0] if len(quarter_data) > 0 else ""
                
                quarterly_ratios.append({
                    'Period': quarter,
                    'Financial Year': fy,
                    'Type': 'Quarter',
                    'Total Visits': quarter_total_work,
                    'Ashfields Visits': quarter_site_work.get('Ashfields', 0),
                    'Kiltearn Visits': quarter_site_work.get('Kiltearn', 0),
                    'Ashfields Patients': quarter_recruitment.loc['Ashfields', 'PatientID'] if 'Ashfields' in quarter_recruitment.index else 0,
                    'Kiltearn Patients': quarter_recruitment.loc['Kiltearn', 'PatientID'] if 'Kiltearn' in quarter_recruitment.index else 0,
                    'Ashfields Share': f"{q_ashfields_final_ratio:.1%}",
                    'Kiltearn Share': f"{q_kiltearn_final_ratio:.1%}",
                    'Total Income': f"£{quarter_income:,.2f}",
                    'Ashfields Income': f"£{ashfields_quarter_income:,.2f}",
                    'Kiltearn Income': f"£{kiltearn_quarter_income:,.2f}"
                })
            
            # Add financial year summaries
            for fy in financial_years:
                fy_data = financial_df[financial_df['FinancialYear'] == fy]
                
                if len(fy_data) == 0:
                    continue
                
                # Work done ratios for this financial year
                fy_site_work = fy_data.groupby('SiteofVisit').size()
                fy_total_work = fy_site_work.sum()
                
                fy_ashfields_work_ratio = fy_site_work.get('Ashfields', 0) / fy_total_work if fy_total_work > 0 else 0
                fy_kiltearn_work_ratio = fy_site_work.get('Kiltearn', 0) / fy_total_work if fy_total_work > 0 else 0
                
                # Patient recruitment ratios for this financial year
                fy_recruitment = fy_data.groupby('PatientOrigin').agg({'PatientID': 'nunique'})
                fy_total_patients = fy_recruitment['PatientID'].sum()
                
                fy_ashfields_recruitment_ratio = fy_recruitment.loc['Ashfields', 'PatientID'] / fy_total_patients if 'Ashfields' in fy_recruitment.index and fy_total_patients > 0 else 0
                fy_kiltearn_recruitment_ratio = fy_recruitment.loc['Kiltearn', 'PatientID'] / fy_total_patients if 'Kiltearn' in fy_recruitment.index and fy_total_patients > 0 else 0
                
                # Calculate weighted ratios for financial year
                fy_ashfields_final_ratio = (ashfields_list_ratio * list_weight + 
                                           fy_ashfields_work_ratio * work_weight + 
                                           fy_ashfields_recruitment_ratio * recruitment_weight)
                
                fy_kiltearn_final_ratio = (kiltearn_list_ratio * list_weight + 
                                          fy_kiltearn_work_ratio * work_weight + 
                                          fy_kiltearn_recruitment_ratio * recruitment_weight)
                
                # Normalize
                fy_total_ratio = fy_ashfields_final_ratio + fy_kiltearn_final_ratio
                if fy_total_ratio > 0:
                    fy_ashfields_final_ratio = fy_ashfields_final_ratio / fy_total_ratio
                    fy_kiltearn_final_ratio = fy_kiltearn_final_ratio / fy_total_ratio
                
                # Calculate financial year income
                fy_income = fy_data['Payment'].sum()
                
                # Calculate income by site for this financial year
                fy_income_by_site = fy_data.groupby('SiteofVisit')['Payment'].sum()
                ashfields_fy_income = fy_income_by_site.get('Ashfields', 0)
                kiltearn_fy_income = fy_income_by_site.get('Kiltearn', 0)
                
                quarterly_ratios.append({
                    'Period': f"FY {fy}",
                    'Financial Year': fy,
                    'Type': 'Financial Year',
                    'Total Visits': fy_total_work,
                    'Ashfields Visits': fy_site_work.get('Ashfields', 0),
                    'Kiltearn Visits': fy_site_work.get('Kiltearn', 0),
                    'Ashfields Patients': fy_recruitment.loc['Ashfields', 'PatientID'] if 'Ashfields' in fy_recruitment.index else 0,
                    'Kiltearn Patients': fy_recruitment.loc['Kiltearn', 'PatientID'] if 'Kiltearn' in fy_recruitment.index else 0,
                    'Ashfields Share': f"{fy_ashfields_final_ratio:.1%}",
                    'Kiltearn Share': f"{fy_kiltearn_final_ratio:.1%}",
                    'Total Income': f"£{fy_income:,.2f}",
                    'Ashfields Income': f"£{ashfields_fy_income:,.2f}",
                    'Kiltearn Income': f"£{kiltearn_fy_income:,.2f}"
                })
            
            if quarterly_ratios:
                # Sort by financial year and type (FY summaries at end of each year)
                quarterly_ratios.sort(key=lambda x: (x['Financial Year'], x['Type'] == 'Financial Year', x['Period']))
                
                quarterly_df = pd.DataFrame(quarterly_ratios)
                
                # Style the dataframe to highlight financial year rows
                def highlight_fy_rows(row):
                    if row['Type'] == 'Financial Year':
                        return ['background-color: #e6f3ff; font-weight: bold'] * len(row)
                    else:
                        return [''] * len(row)
                
                styled_quarterly_df = quarterly_df.style.apply(highlight_fy_rows, axis=1)
                st.dataframe(styled_quarterly_df, use_container_width=True)
                
                # Visual chart of quarterly ratios (quarters only, not FY summaries)
                st.write("**Quarterly Profit Sharing Trends**")
                
                # Prepare chart data - quarters only
                chart_data = []
                for ratio in quarterly_ratios:
                    if ratio['Type'] == 'Quarter':
                        # Convert percentages back to numbers for charting
                        ashfields_pct = float(ratio['Ashfields Share'].rstrip('%')) / 100
                        kiltearn_pct = float(ratio['Kiltearn Share'].rstrip('%')) / 100
                        
                        chart_data.append({
                            'Quarter': ratio['Period'],
                            'Ashfields': ashfields_pct,
                            'Kiltearn': kiltearn_pct
                        })
                
                if chart_data:
                    chart_df = pd.DataFrame(chart_data).set_index('Quarter')
                    st.bar_chart(chart_df)
                
                st.info("""
                **Analysis Notes:**
                - **Blue highlighted rows** = Financial Year totals (April to March)
                - Use **Financial Year ratios** for annual profit sharing decisions
                - **Total Income** = Combined clinical trial income from all studies
                - **Ashfields/Kiltearn Income** = Trial income generated at each practice site
                - Quarterly ratios show seasonal variations within each financial year
                - List sizes (35% weight) remain constant; work done and recruitment vary by period
                - **Note:** Income shown is clinical trial income only, not total practice revenue
                """)
            else:
                st.warning("No quarterly data available for profit sharing analysis.")
        else:
            st.warning("No financial data available for quarterly analysis.")

        # Downloads section
        st.subheader("💾 Download Options")

        # Excel exports with formatting
        try:
            import openpyxl
            from openpyxl.styles import PatternFill, Font, Alignment
            from openpyxl.utils import get_column_letter
            
            excel_financial_cols = ["Daily Total", "Monthly Total", "FY Total"] + [c for c in calendar_df.columns if "Income" in c]
            excel_full_df = calendar_df[final_ordered_columns + [col for col in excel_financial_cols if col in calendar_df.columns]].copy()
            
            excel_full_df["Date"] = excel_full_df["Date"].dt.strftime("%d/%m/%Y")
            
            for col in excel_financial_cols:
                if col in excel_full_df.columns:
                    if col in ["Monthly Total", "FY Total"]:
                        excel_full_df[col] = excel_full_df[col].apply(lambda v: f"£{v:,.2f}" if pd.notna(v) and v != 0 else "")
                    else:
                        excel_full_df[col] = excel_full_df[col].apply(lambda v: f"£{v:,.2f}" if pd.notna(v) else "£0.00")

            # Excel with finances and site headers
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                excel_full_df.to_excel(writer, index=False, sheet_name="VisitCalendar", startrow=1)
                ws = writer.sheets["VisitCalendar"]

                # Add site headers
                for col_idx, col_name in enumerate(excel_full_df.columns, 1):
                    col_letter = get_column_letter(col_idx)
                    if col_name not in ["Date", "Day"] and not any(x in col_name for x in ["Income", "Total"]):
                        for site in unique_sites:
                            if col_name in site_column_mapping.get(site, []):
                                ws[f"{col_letter}1"] = site
                                ws[f"{col_letter}1"].font = Font(bold=True, size=12)
                                ws[f"{col_letter}1"].fill = PatternFill(start_color="FFE6F3FF", end_color="FFE6F3FF", fill_type="solid")
                                ws[f"{col_letter}1"].alignment = Alignment(horizontal="center")
                                break

                # Auto-adjust column widths
                for idx, col in enumerate(excel_full_df.columns, 1):
                    col_letter = get_column_letter(idx)
                    max_length = max([len(str(cell)) if cell is not None else 0 for cell in excel_full_df[col].tolist()] + [len(col)])
                    ws.column_dimensions[col_letter].width = max(10, max_length + 2)

                # Define fills and fonts for formatting with improved colors
                weekend_fill = PatternFill(start_color="FFE5E7EB", end_color="FFE5E7EB", fill_type="solid")  # More obvious gray
                month_end_fill = PatternFill(start_color="FF60A5FA", end_color="FF60A5FA", fill_type="solid")  # Softer blue
                fy_end_fill = PatternFill(start_color="FF1E40AF", end_color="FF1E40AF", fill_type="solid")  # Keep dark blue
                white_font = Font(color="FFFFFFFF", bold=True)
                normal_white_font = Font(color="FFFFFFFF", bold=False)  # For softer month ends
                
                # Visit type color fills
                completed_visit_fill = PatternFill(start_color="FFD4EDDA", end_color="FFD4EDDA", fill_type="solid")
                completed_visit_font = Font(color="FF155724", bold=True)
                
                out_of_window_fill = PatternFill(start_color="FFFFF3CD", end_color="FFFFF3CD", fill_type="solid")
                out_of_window_font = Font(color="FF856404", bold=True)
                
                screen_fail_fill = PatternFill(start_color="FFF8D7DA", end_color="FFF8D7DA", fill_type="solid")
                screen_fail_font = Font(color="FF721C24", bold=True)
                
                scheduled_visit_fill = PatternFill(start_color="FFE2E3E5", end_color="FFE2E3E5", fill_type="solid")
                scheduled_visit_font = Font(color="FF383D41", bold=False)
                
                # Different color for tolerance periods to distinguish from weekends
                tolerance_fill = PatternFill(start_color="FFF1F5F9", end_color="FFF1F5F9", fill_type="solid")
                tolerance_font = Font(color="FF64748B", italic=True)

                # Apply formatting row-by-row with proper date-based styling
                for row_idx in range(3, len(excel_full_df) + 3):
                    try:
                        date_idx = row_idx - 3
                        if date_idx < len(calendar_df):
                            date_obj = calendar_df.iloc[date_idx]["Date"]
                            
                            # Apply date-based formatting first (takes priority)
                            date_style_applied = False
                            if not pd.isna(date_obj):
                                # Financial year end (highest priority)
                                if date_obj.month == 3 and date_obj.day == 31:
                                    for col_idx in range(1, len(excel_full_df.columns) + 1):
                                        cell = ws.cell(row=row_idx, column=col_idx)
                                        cell.fill = fy_end_fill
                                        cell.font = white_font
                                    date_style_applied = True
                                # Month end (second priority) - softer styling
                                elif date_obj == date_obj + pd.offsets.MonthEnd(0):
                                    for col_idx in range(1, len(excel_full_df.columns) + 1):
                                        cell = ws.cell(row=row_idx, column=col_idx)
                                        cell.fill = month_end_fill
                                        cell.font = normal_white_font
                                    date_style_applied = True
                                # Weekend (third priority)
                                elif date_obj.weekday() in (5, 6):
                                    for col_idx in range(1, len(excel_full_df.columns) + 1):
                                        cell = ws.cell(row=row_idx, column=col_idx)
                                        cell.fill = weekend_fill
                                    date_style_applied = True
                            
                            # Apply visit-specific styling only if no date styling was applied
                            if not date_style_applied:
                                for col_idx, col_name in enumerate(excel_full_df.columns, 1):
                                    if col_name not in ["Date", "Day"] and not any(x in col_name for x in ["Income", "Total"]):
                                        cell = ws.cell(row=row_idx, column=col_idx)
                                        cell_value = str(cell.value) if cell.value else ""
                                        
                                        if "✅ Visit" in cell_value:
                                            cell.fill = completed_visit_fill
                                            cell.font = completed_visit_font
                                        elif "⚠️ Visit" in cell_value:
                                            cell.fill = out_of_window_fill
                                            cell.font = out_of_window_font
                                        elif "❌ Screen Fail" in cell_value:
                                            cell.fill = screen_fail_fill
                                            cell.font = screen_fail_font
                                        elif "Visit " in cell_value and not cell_value.startswith("✅") and not cell_value.startswith("⚠️"):
                                            cell.fill = scheduled_visit_fill
                                            cell.font = scheduled_visit_font
                                        elif cell_value in ["+", "-"]:
                                            cell.fill = tolerance_fill
                                            cell.font = tolerance_font

                    except Exception:
                        continue

            st.download_button(
                "💰 Excel with Finances & Site Headers",
                data=output.getvalue(),
                file_name="VisitCalendar_WithFinances_SiteGrouped.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

            # Schedule-only Excel with same formatting
            schedule_df = display_df.copy()
            schedule_df["Date"] = schedule_df["Date"].dt.strftime("%d/%m/%Y")
                
            output2 = io.BytesIO()
            with pd.ExcelWriter(output2, engine='openpyxl') as writer:
                schedule_df.to_excel(writer, index=False, sheet_name="VisitSchedule", startrow=1)
                ws2 = writer.sheets["VisitSchedule"]

                # Add site headers
                for col_idx, col_name in enumerate(schedule_df.columns, 1):
                    col_letter = get_column_letter(col_idx)
                    if col_name not in ["Date", "Day"]:
                        for site in unique_sites:
                            if col_name in site_column_mapping.get(site, []):
                                ws2[f"{col_letter}1"] = site
                                ws2[f"{col_letter}1"].font = Font(bold=True, size=12)
                                ws2[f"{col_letter}1"].fill = PatternFill(start_color="FFE6F3FF", end_color="FFE6F3FF", fill_type="solid")
                                ws2[f"{col_letter}1"].alignment = Alignment(horizontal="center")
                                break

                # Set column widths
                for idx, col in enumerate(schedule_df.columns, 1):
                    col_letter = get_column_letter(idx)
                    max_length = max([len(str(cell)) if cell is not None else 0 for cell in schedule_df[col].tolist()] + [len(col)])
                    ws2.column_dimensions[col_letter].width = max(10, max_length + 2)

                # Apply same formatting to schedule-only file
                for row_idx in range(3, len(schedule_df) + 3):
                    try:
                        date_idx = row_idx - 3
                        if date_idx < len(calendar_df):
                            date_obj = calendar_df.iloc[date_idx]["Date"]
                            
                            date_style_applied = False
                            if not pd.isna(date_obj):
                                if date_obj.month == 3 and date_obj.day == 31:
                                    for col_idx in range(1, len(schedule_df.columns) + 1):
                                        cell = ws2.cell(row=row_idx, column=col_idx)
                                        cell.fill = fy_end_fill
                                        cell.font = white_font
                                    date_style_applied = True
                                elif date_obj == date_obj + pd.offsets.MonthEnd(0):
                                    for col_idx in range(1, len(schedule_df.columns) + 1):
                                        cell = ws2.cell(row=row_idx, column=col_idx)
                                        cell.fill = month_end_fill
                                        cell.font = normal_white_font
                                    date_style_applied = True
                                elif date_obj.weekday() in (5, 6):
                                    for col_idx in range(1, len(schedule_df.columns) + 1):
                                        cell = ws2.cell(row=row_idx, column=col_idx)
                                        cell.fill = weekend_fill
                                    date_style_applied = True
                            
                            # Apply visit-specific styling
                            if not date_style_applied:
                                for col_idx, col_name in enumerate(schedule_df.columns, 1):
                                    if col_name not in ["Date", "Day"]:
                                        cell = ws2.cell(row=row_idx, column=col_idx)
                                        cell_value = str(cell.value) if cell.value else ""
                                        
                                        if "✅ Visit" in cell_value:
                                            cell.fill = completed_visit_fill
                                            cell.font = completed_visit_font
                                        elif "⚠️ Visit" in cell_value:
                                            cell.fill = out_of_window_fill
                                            cell.font = out_of_window_font
                                        elif "❌ Screen Fail" in cell_value:
                                            cell.fill = screen_fail_fill
                                            cell.font = screen_fail_font
                                        elif "Visit " in cell_value and not cell_value.startswith("✅") and not cell_value.startswith("⚠️"):
                                            cell.fill = scheduled_visit_fill
                                            cell.font = scheduled_visit_font
                                        elif cell_value in ["+", "-"]:
                                            cell.fill = tolerance_fill
                                            cell.font = tolerance_font

                    except Exception:
                        continue

            st.download_button(
                "📅 Excel Schedule Only with Site Headers",
                data=output2.getvalue(),
                file_name="VisitSchedule_Only_SiteGrouped.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        except ImportError:
            st.warning("Excel formatting unavailable - openpyxl not installed")

        # Summary statistics
        st.subheader("📊 Summary Statistics")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Sites", len(unique_sites))
        with col2:
            st.metric("Total Patients", len(patients_df))
        with col3:
            total_visits = len(financial_df)
            st.metric("Total Visits", total_visits)
        with col4:
            total_income = financial_df["Payment"].sum()
            st.metric("Total Income", f"£{total_income:,.2f}")

        # Visit status breakdown
        if actual_visits_df is not None:
            st.subheader("📈 Visit Status Breakdown")
            col1, col2, col3, col4 = st.columns(4)
            
            actual_count = len(actual_financial)
            scheduled_count = len(scheduled_financial)
            total_visits_due = actual_count + scheduled_count
            screen_fail_visits = len(visits_df[visits_df.get('IsScreenFail', False)])
            
            with col1:
                st.metric("Completed Visits", actual_count - screen_fail_visits)
            with col2:
                st.metric("Screen Failures", screen_fail_visits)
            with col3:
                st.metric("Pending Visits", scheduled_count)
            with col4:
                completion_percentage = ((actual_count - screen_fail_visits) / total_visits_due * 100) if total_visits_due > 0 else 0
                st.metric("Success Rate", f"{completion_percentage:.1f}%")

        # Site-wise breakdown
        st.subheader("🏢 Site-wise Statistics")
        site_stats = []
        for site in unique_sites:
            site_patients = patients_df[patients_df["Site"] == site]
            site_visits = visits_df[(visits_df["PatientID"].isin(site_patients["PatientID"])) & 
                                  ((visits_df["Visit"].str.startswith("✅")) | 
                                   (visits_df["Visit"].str.startswith("❌ Screen Fail")) | 
                                   (visits_df["Visit"].str.contains("Visit")))]
            site_income = visits_df[visits_df["PatientID"].isin(site_patients["PatientID"])]["Payment"].sum()
            
            # Count screen failures vs active patients
            site_screen_fails = 0
            for _, patient in site_patients.iterrows():
                patient_study_key = f"{patient['PatientID']}_{patient['Study']}"
                if patient_study_key in screen_failures:
                    site_screen_fails += 1
            
            active_patients = len(site_patients) - site_screen_fails
            
            # Count completed vs pending visits for this site
            completed_visits = len(site_visits[site_visits["Visit"].str.startswith("✅")]) if actual_visits_df is not None else 0
            screen_fail_visits = len(site_visits[site_visits["Visit"].str.startswith("❌ Screen Fail")]) if actual_visits_df is not None else 0
            total_visits = len(site_visits)
            pending_visits = total_visits - completed_visits - screen_fail_visits
            
            site_stats.append({
                "Site": site,
                "Total Patients": len(site_patients),
                "Active Patients": active_patients,
                "Screen Failures": site_screen_fails,
                "Completed Visits": completed_visits,
                "Screen Fail Visits": screen_fail_visits,
                "Pending Visits": pending_visits,
                "Total Visits": total_visits,
                "Total Income": f"£{site_income:,.2f}"
            })
        
        site_stats_df = pd.DataFrame(site_stats)
        st.dataframe(site_stats_df, use_container_width=True)

        # Monthly analysis by site
        st.subheader("📅 Monthly Analysis by Site")
        
        # Create month-year period for analysis
        visits_df['MonthYear'] = visits_df['Date'].dt.to_period('M')
        
        # Filter only actual visits and main scheduled visits
        analysis_visits = visits_df[
            (visits_df['Visit'].str.startswith("✅")) |  # Actual completed visits
            (visits_df['Visit'].str.startswith("❌ Screen Fail")) |  # Screen failure visits
            (visits_df['Visit'].str.contains('Visit', na=False) & (~visits_df.get('IsActual', False)))  # Scheduled main visits
        ]
        
        # Analysis 1: Visits by Site of Visit (where visits happen)
        st.write("**Analysis by Visit Location (Where visits occur)**")
        visits_by_site_month = analysis_visits.groupby(['SiteofVisit', 'MonthYear']).size().reset_index(name='Visits')
        visits_pivot = visits_by_site_month.pivot(index='MonthYear', columns='SiteofVisit', values='Visits').fillna(0)
        
        # Calculate visit ratios
        visits_pivot['Total_Visits'] = visits_pivot.sum(axis=1)
        visit_sites = [col for col in visits_pivot.columns if col != 'Total_Visits']
        for site in visit_sites:
            visits_pivot[f'{site}_Ratio'] = (visits_pivot[site] / visits_pivot['Total_Visits'] * 100).round(1)
        
        # Count unique patients by visit site per month
        patients_by_visit_site_month = analysis_visits.groupby(['SiteofVisit', 'MonthYear'])['PatientID'].nunique().reset_index(name='Patients')
        patients_visit_pivot = patients_by_visit_site_month.pivot(index='MonthYear', columns='SiteofVisit', values='Patients').fillna(0)
        
        # Calculate patient ratios for visit site
        patients_visit_pivot['Total_Patients'] = patients_visit_pivot.sum(axis=1)
        for site in visit_sites:
            if site in patients_visit_pivot.columns:
                patients_visit_pivot[f'{site}_Ratio'] = (patients_visit_pivot[site] / patients_visit_pivot['Total_Patients'] * 100).round(1)
        
        # Analysis 2: Patients by Origin Site (where patients come from)
        st.write("**Analysis by Patient Origin (Where patients come from)**")
        patients_by_origin_month = analysis_visits.groupby(['PatientOrigin', 'MonthYear'])['PatientID'].nunique().reset_index(name='Patients')
        patients_origin_pivot = patients_by_origin_month.pivot(index='MonthYear', columns='PatientOrigin', values='Patients').fillna(0)
        
        # Calculate patient origin ratios
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
        st.subheader("📊 Monthly Trends")
        
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
