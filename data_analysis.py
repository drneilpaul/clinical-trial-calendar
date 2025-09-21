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

def display_site_wise_statistics(visits_df, patients_df, unique_sites, screen_failures):
    """Display detailed statistics for each site"""
    if visits_df.empty or patients_df.empty:
        return
    
    st.subheader("📊 Site-wise Analysis")
    
    # Create tabs for each site
    if len(unique_sites) > 1:
        tabs = st.tabs(unique_sites)
        
        for i, site in enumerate(unique_sites):
            with tabs[i]:
                _display_single_site_stats(visits_df, patients_df, site, screen_failures)
    else:
        # If only one site, display directly
        _display_single_site_stats(visits_df, patients_df, unique_sites[0], screen_failures)

def _display_single_site_stats(visits_df, patients_df, site, screen_failures):
    """Display statistics for a single site"""
    # Filter data for this site
    site_patients = patients_df[patients_df['Site'] == site]
    site_visits = visits_df[visits_df['SiteofVisit'] == site]
    
    if site_patients.empty:
        st.warning(f"No patients found for site: {site}")
        return
    
    # Basic statistics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        total_patients = len(site_patients)
        st.metric("Total Patients", total_patients)
    
    with col2:
        total_visits = len(site_visits)
        st.metric("Total Visits", total_visits)
    
    with col3:
        actual_visits = len(site_visits[site_visits.get('IsActual', False)])
        st.metric("Completed Visits", actual_visits)
    
    with col4:
        total_income = site_visits['Payment'].sum()
        st.metric("Total Income", f"£{total_income:,.2f}")
    
    # Study breakdown
    st.write("**Studies at this site:**")
    study_breakdown = site_patients.groupby('Study').agg({
        'PatientID': 'count'
    }).rename(columns={'PatientID': 'Patient Count'})
    
    # Add visit counts
    visit_breakdown = site_visits.groupby('Study').agg({
        'Visit': 'count',
        'Payment': 'sum'
    }).rename(columns={'Visit': 'Visit Count', 'Payment': 'Total Income'})
    
    # Combine the data
    combined_breakdown = study_breakdown.join(visit_breakdown, how='left').fillna(0)
    combined_breakdown['Total Income'] = combined_breakdown['Total Income'].apply(lambda x: f"£{x:,.2f}")
    
    st.dataframe(combined_breakdown, use_container_width=True)
    
    # Screen failures for this site
    site_screen_failures = []
    for patient in site_patients.itertuples():
        patient_study_key = f"{patient.PatientID}_{patient.Study}"
        if patient_study_key in screen_failures:
            site_screen_failures.append({
                'Patient': patient.PatientID,
                'Study': patient.Study,
                'Screen Fail Date': screen_failures[patient_study_key].strftime('%Y-%m-%d')
            })
    
    if site_screen_failures:
        st.write("**Screen Failures:**")
        st.dataframe(pd.DataFrame(site_screen_failures), use_container_width=True)

def display_monthly_analysis_by_site(visits_df):
    """Display monthly analysis broken down by site"""
    if visits_df.empty:
        return
    
    st.subheader("📅 Monthly Analysis by Site")
    
    # Create monthly breakdown
    visits_df['MonthYear'] = visits_df['Date'].dt.to_period('M')
    
    # Group by month and site
    monthly_site_data = visits_df.groupby(['MonthYear', 'SiteofVisit']).agg({
        'Visit': 'count',
        'Payment': 'sum'
    }).rename(columns={'Visit': 'Visit Count', 'Payment': 'Income'})
    
    # Pivot to show sites as columns
    monthly_visits = monthly_site_data['Visit Count'].unstack(fill_value=0)
    monthly_income = monthly_site_data['Income'].unstack(fill_value=0)
    
    # Display visit counts
    st.write("**Monthly Visit Counts by Site:**")
    monthly_visits.index = monthly_visits.index.astype(str)
    st.dataframe(monthly_visits, use_container_width=True)
    
    # Display income
    st.write("**Monthly Income by Site:**")
    monthly_income_display = monthly_income.copy()
    monthly_income_display.index = monthly_income_display.index.astype(str)
    
    # Format as currency
    for col in monthly_income_display.columns:
        monthly_income_display[col] = monthly_income_display[col].apply(lambda x: f"£{x:,.2f}")
    
    st.dataframe(monthly_income_display, use_container_width=True)
    
    # Chart showing monthly trends
    if len(monthly_visits.columns) > 1:
        st.write("**Monthly Visit Trends:**")
        st.line_chart(monthly_visits)
        
        st.write("**Monthly Income Trends:**")
        st.line_chart(monthly_income)
