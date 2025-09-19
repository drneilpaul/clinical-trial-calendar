import streamlit as st
import pandas as pd
from datetime import date

def visit_entry_form(patients_file, trials_file, actual_visits_file):
    existing_patients = pd.read_csv(patients_file) if patients_file.name.endswith('.csv') else pd.read_excel(patients_file)
    existing_patients.columns = existing_patients.columns.str.strip()
    existing_trials = pd.read_csv(trials_file) if trials_file.name.endswith('.csv') else pd.read_excel(trials_file)
    existing_trials.columns = existing_trials.columns.str.strip()
    existing_visits = None
    if actual_visits_file:
        existing_visits = pd.read_csv(actual_visits_file) if actual_visits_file.name.endswith('.csv') else pd.read_excel(actual_visits_file)
        existing_visits.columns = existing_visits.columns.str.strip()
    patient_options = [f"{row['PatientID']} ({row['Study']})" for _, row in existing_patients.iterrows()]
    with st.form("record_visit_form"):
        st.subheader("Record Visit")
        selected_patient = st.selectbox("Select Patient", options=patient_options)
        if selected_patient:
            patient_id, study = selected_patient.split(" (")
            study = study.rstrip(")")
            study_visits = existing_trials[existing_trials["Study"].astype(str) == str(study)]
            if len(study_visits) == 0:
                st.error(f"No visits defined for Study '{study}'. Please check your trials file.")
                st.stop()
            visit_options = [f"Visit {v['VisitNo']} (Day {v['Day']})" for _, v in study_visits.iterrows()]
            selected_visit = st.selectbox("Visit Number", options=visit_options)
            if selected_visit:
                visit_no = selected_visit.split(" ")[1]
                visit_date = st.date_input("Visit Date")
                visit_payment = study_visits[study_visits["VisitNo"].astype(str) == str(visit_no)]
                payment = visit_payment["Payment"].iloc[0] if "Payment" in visit_payment and not visit_payment.empty else 0
                actual_payment = st.number_input("Payment Amount", value=float(payment), min_value=0.0)
                notes = st.text_area("Notes (Optional)")
        submit = st.form_submit_button("Record Visit")
        cancel = st.form_submit_button("Cancel")
        if cancel:
            st.info("Visit entry cancelled.")
            return None
        validation_errors = []
        if selected_patient and selected_visit:
            if visit_date > date.today():
                validation_errors.append("Visit date cannot be in the future")
            if existing_visits is not None and not existing_visits.empty:
                duplicate = existing_visits[
                    (existing_visits["PatientID"].astype(str) == str(patient_id)) &
                    (existing_visits["Study"].astype(str) == str(study)) &
                    (existing_visits["VisitNo"].astype(str) == str(visit_no))
                ]
                if not duplicate.empty:
                    validation_errors.append(f"Visit {visit_no} for patient {patient_id} already recorded")
        if submit:
            if validation_errors:
                st.error("Please fix the following issues:")
                for error in validation_errors:
                    st.write(f"• {error}")
                return None
            if selected_patient and selected_visit:
                st.success("Visit data is valid")
                preview_data = {
                    "PatientID": [patient_id],
                    "Study": [study],
                    "VisitNo": [visit_no],
                    "ActualDate": [visit_date.strftime('%Y-%m-%d')],
                    "ActualPayment": [actual_payment],
                    "Notes": [notes or ""]
                }
                st.dataframe(pd.DataFrame(preview_data))
                new_visit_data = {
                    "PatientID": patient_id,
                    "Study": study,
                    "VisitNo": visit_no,
                    "ActualDate": visit_date,
                    "ActualPayment": actual_payment,
                    "Notes": notes or ""
                }
                if existing_visits is not None and not existing_visits.empty:
                    new_visit_df = pd.DataFrame([new_visit_data])
                    updated_visits_df = pd.concat([existing_visits, new_visit_df], ignore_index=True)
                else:
                    updated_visits_df = pd.DataFrame([new_visit_data])
                import io
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    updated_visits_df.to_excel(writer, index=False, sheet_name="ActualVisits")
                st.download_button(
                    "💾 Download Updated Actual Visits File",
                    data=output.getvalue(),
                    file_name=f"ActualVisits_Updated_{visit_date.strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                st.success(f"Visit {visit_no} for patient {patient_id} recorded successfully! Download and re-upload the file to see changes.")
                return new_visit_data
    return None