import streamlit as st

def visit_entry_form(patients_file, trials_file, actual_visits_file):
    """
    This function is now deprecated - visit entry is handled by modal dialogs in the main app.
    This is kept for compatibility but should not be used.
    """
    st.warning("Visit entry is now handled through modal dialogs in the main application.")
    st.info("Please use the 'Record Visit' button in the main interface.")
    return None
