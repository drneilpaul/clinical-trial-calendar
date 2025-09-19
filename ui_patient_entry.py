import streamlit as st

def patient_entry_form(patients_file, trials_file):
    """
    This function is now deprecated - patient entry is handled by modal dialogs in the main app.
    This is kept for compatibility but should not be used.
    """
    st.warning("Patient entry is now handled through modal dialogs in the main application.")
    st.info("Please use the 'Add New Patient' button in the main interface.")
    return None
