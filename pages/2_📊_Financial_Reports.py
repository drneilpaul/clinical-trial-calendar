import streamlit as st
import pandas as pd
from helpers import log_activity
import database as db
from processing_calendar import build_calendar
from display_components import (
    display_monthly_income_tables,
    display_quarterly_profit_sharing_tables,
    display_income_realization_analysis,
    display_site_income_by_fy,
    display_study_income_summary
)
from data_analysis import display_site_wise_statistics, extract_screen_failures, extract_withdrawals
from calculations import prepare_financial_data
from config import APP_TITLE, APP_VERSION

# CRITICAL: Hide page if not admin
if st.session_state.get('auth_level') != 'admin':
    st.warning("🔒 This page is only available to administrators.")
    st.info("Please log in as admin from the main Calendar page.")
    st.stop()

# Title
st.title("📊 Financial Reports")
st.caption(f"{APP_VERSION}")

# Load data from session state (shared from main page)
if 'visits_df' not in st.session_state or st.session_state.visits_df is None:
    st.error("No calendar data available. Please generate calendar from the main page first.")
    st.stop()

visits_df = st.session_state.visits_df
patients_df = st.session_state.patients_df
trials_df = st.session_state.trials_df

# Get filter data from session state
unique_visit_sites = st.session_state.get('unique_visit_sites', [])
screen_failures = st.session_state.get('screen_failures', [])
withdrawals = st.session_state.get('withdrawals', [])

# Display all financial reports
display_monthly_income_tables(visits_df)

financial_df = prepare_financial_data(visits_df)
if not financial_df.empty:
    display_quarterly_profit_sharing_tables(financial_df, patients_df)

display_income_realization_analysis(visits_df, trials_df, patients_df)
display_site_income_by_fy(visits_df, trials_df)
display_study_income_summary(visits_df)
display_site_wise_statistics(visits_df, patients_df, unique_visit_sites, screen_failures, withdrawals)
