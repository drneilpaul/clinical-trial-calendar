import streamlit as st
import pandas as pd
from datetime import datetime

def extract_screen_failures(actual_visits_df):
    """Extract screen failure information from actual visits"""
    screen_failures = {}
    
    if actual_visits_df is not None and not actual_visits_df.empty:
        # Find visits marked as screen failures
        screen_fail_visits = actual_visits_df[
            actual_visits_df["Notes"].str.contains("ScreenFail", case=False, na=False)
        ]
        
        for _, visit in screen_fail_visits.iterrows():
            patient_study_key = f"{visit['PatientID']}_{visit['Study']}"
            screen_fail_date = visit['ActualDate']
            
            # Store the earliest screen failure date for each patient-study combination
            if patient_study_key not in screen_failures or screen_fail_date < screen_failures[patient_study_key]:
                screen_failures[patient_study_key] = screen_fail_date
    
    return screen_failures

def prepare_financial_data(visits_df):
    """Prepare financial data with proper columns for profit sharing analysis"""
    if visits_df.empty:
        return pd.DataFrame()
    
    # Create a copy and add required columns
    financial_df = visits_df.copy()
    
    # Add quarter and financial year columns if not present
    if 'QuarterYear' not in financial_df.columns:
        financial_df['Quarter'] = financial_df['Date'].dt.quarter
        financial_df['Year'] = financial_df['Date'].dt.year
        financial_df['QuarterYear'] = financial_df['Year'].astype(str) + '-Q' + financial_df['Quarter'].astype(str)
    
    if 'FinancialYear' not in financial_df.columns:
        financial_df['FinancialYear'] = financial_df['Date'].apply(
            lambda d: f"{d.year}-{d.year+1}" if d.month >= 4 else f"{d.year-1}-{d.year}"
        )
    
    return financial_df

def display_processing_messages(messages):
    """Display processing messages in a clean format"""
    if messages:
        st.subheader("Processing Summary")
        for message in messages:
            if message.startswith("✅"):
                st.success(message)
            elif message.startswith("⚠️"):
                st.warning(message)
            elif message.startswith("❌"):
                st.error(message)
            else:
                st.info(message)
