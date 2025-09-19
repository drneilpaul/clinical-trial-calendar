import streamlit as st
import pandas as pd
from datetime import date
import io

def patient_entry_form(patients_file, trials_file):
    # Load existing data for validation
    existing_patients = load_file_helper(patients_file)
    existing_patients.columns = existing_patients.columns.str.strip()
    
    existing_trials = load_file_helper(trials_file)
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

    with st.form("add_patient_form"):
        st.subheader("Add New Patient")
        new_patient_id = st.text_input("Patient ID", help="Enter unique patient identifier (letters, numbers, -, _)")
        new_study = st.selectbox("Study", options=available_studies, help="Select study from trials file")
        new_start_date = st.date_input("Start Date", help="Patient study start date")
        
        if patient_origin_col:
            new_site = st.selectbox(f"{patient_origin_col}", options=existing_sites + ["Add New..."], 
                                  help="Select patient origin site")
            if new_site == "Add New...":
                new_site = st.text_input("New Site Name", help="Enter new site name")
        else:
            new_site = st.text_input("Patient Origin Site (required)", help="No origin column found. Enter origin manually.")
        
        submit = st.form_submit_button("Add Patient")
        cancel = st.form_submit_button("Cancel")
        
        if cancel:
            st.info("Patient entry cancelled.")
            return None

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
        
        if not new_site:
            validation_errors.append("Patient origin/site is required.")

        if submit:
            if validation_errors:
                st.error("Please fix the following issues:")
                for error in validation_errors:
                    st.write(f"• {error}")
                return None
            
            st.success("Patient data is valid")
            
            # Show preview
            preview_data = {
                "PatientID": [new_patient_id],
                "Study": [new_study],
                "StartDate": [new_start_date.strftime('%Y-%m-%d')],
                (patient_origin_col or "PatientPractice"): [new_site]
            }
            st.dataframe(pd.DataFrame(preview_data))
            
            # Prepare row for download - match data types from existing file
            processed_patient_id = new_patient_id
            if len(existing_patients) > 0:
                existing_patient_ids = existing_patients["PatientID"]
                # Check if existing IDs are numeric
                if existing_patient_ids.dtype in ['int64', 'float64'] or all(pd.to_numeric(existing_patient_ids, errors='coerce').notna()):
                    try:
                        processed_patient_id = int(new_patient_id) if new_patient_id.isdigit() else float(new_patient_id)
                    except:
                        processed_patient_id = new_patient_id  # Keep as string if conversion fails
            
            new_row = {
                "PatientID": processed_patient_id,
                "Study": new_study,
                "StartDate": new_start_date,
            }
            
            if patient_origin_col:
                new_row[patient_origin_col] = new_site
            else:
                new_row["PatientPractice"] = new_site
            
            # Add other columns with appropriate default values
            for col in existing_patients.columns:
                if col not in new_row:
                    if len(existing_patients[col].dropna()) > 0:
                        sample_value = existing_patients[col].dropna().iloc[0]
                        if isinstance(sample_value, (int, float)):
                            new_row[col] = 0 if isinstance(sample_value, int) else 0.0
                        else:
                            new_row[col] = ""
                    else:
                        new_row[col] = ""
            
            new_row_df = pd.DataFrame([new_row])
            updated_patients_df = pd.concat([existing_patients, new_row_df], ignore_index=True)
            
            # Create download
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                updated_patients_df.to_excel(writer, index=False, sheet_name="Patients")
            
            st.download_button(
                "💾 Download Updated Patients File",
                data=output.getvalue(),
                file_name=f"Patients_Updated_{new_start_date.strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            st.success(f"Patient {new_patient_id} added successfully! Download and re-upload the file to see changes.")
            return new_row
    return None

def load_file_helper(uploaded_file):
    """Helper function to load files consistently"""
    if uploaded_file is None:
        return None
    if uploaded_file.name.endswith(".csv"):
        return pd.read_csv(uploaded_file, dayfirst=True)
    else:
        return pd.read_excel(uploaded_file, engine="openpyxl")
