import streamlit as st
import pandas as pd
from datetime import datetime
from helpers import get_financial_year, get_financial_year_for_series, log_activity

def extract_screen_failures(actual_visits_df):
    """Extract screen failure information from actual visits"""
    screen_failures = {}
    
    if actual_visits_df is not None and not actual_visits_df.empty:
        # Find visits marked as screen failures
        screen_fail_visits = actual_visits_df[
            actual_visits_df["Notes"].str.contains("ScreenFail", case=False, na=False)
        ]
        
        # OPTIMIZED: use itertuples for 2-3x speedup
        for visit in screen_fail_visits.itertuples(index=False):
            patient_study_key = f"{visit.PatientID}_{visit.Study}"
            screen_fail_date = visit.ActualDate

            # Store the earliest screen failure date for each patient-study combination
            if patient_study_key not in screen_failures or screen_fail_date < screen_failures[patient_study_key]:
                screen_failures[patient_study_key] = screen_fail_date
    
    return screen_failures

def extract_withdrawals(actual_visits_df):
    """Extract withdrawal information from actual visits"""
    withdrawals = {}
    
    if actual_visits_df is not None and not actual_visits_df.empty:
        # Find visits marked as withdrawals
        withdrawal_visits = actual_visits_df[
            actual_visits_df["Notes"].str.contains("Withdrawn", case=False, na=False)
        ]
        
        # OPTIMIZED: use itertuples for 2-3x speedup
        for visit in withdrawal_visits.itertuples(index=False):
            patient_study_key = f"{visit.PatientID}_{visit.Study}"
            withdrawal_date = visit.ActualDate

            # Store the earliest withdrawal date for each patient-study combination
            if patient_study_key not in withdrawals or withdrawal_date < withdrawals[patient_study_key]:
                withdrawals[patient_study_key] = withdrawal_date
    
    return withdrawals

def extract_deaths(actual_visits_df):
    """Extract death information from actual visits"""
    deaths = {}
    
    if actual_visits_df is not None and not actual_visits_df.empty:
        # Find visits marked as deaths
        death_visits = actual_visits_df[
            actual_visits_df["Notes"].str.contains("Died", case=False, na=False)
        ]
        
        # OPTIMIZED: use itertuples for 2-3x speedup
        for visit in death_visits.itertuples(index=False):
            patient_study_key = f"{visit.PatientID}_{visit.Study}"
            death_date = visit.ActualDate

            # Store the earliest death date for each patient-study combination
            if patient_study_key not in deaths or death_date < deaths[patient_study_key]:
                deaths[patient_study_key] = death_date
    
    return deaths

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
        # Handle NaN values before converting to int
        financial_df['QuarterYear'] = (
            financial_df['Year'].fillna(0).astype(int).astype(str) + '-Q' + 
            financial_df['Quarter'].fillna(0).astype(int).astype(str)
        )
    
    # FIXED: Use centralized FY calculation from helpers
    if 'FinancialYear' not in financial_df.columns:
        # OPTIMIZED: Use vectorized financial year calculation
        financial_df['FinancialYear'] = get_financial_year_for_series(financial_df['Date'])
    
    return financial_df

def display_processing_messages(messages):
    """Log processing messages to sidebar activity log instead of displaying in main UI"""
    if messages:
        # Log all processing messages to sidebar activity log
        for message in messages:
            if message.startswith("✅"):
                log_activity(message, level='success')
            elif message.startswith("⚠"):
                log_activity(message, level='warning')
            elif message.startswith("🔴"):
                log_activity(message, level='error')
            elif message.startswith("⌛"):
                log_activity(message, level='error')
            else:
                log_activity(message, level='info')

def display_site_wise_statistics(visits_df, patients_df, unique_visit_sites, screen_failures, withdrawals=None):
    """Display detailed statistics for each visit site with quarterly and financial year analysis"""
    if visits_df.empty or patients_df.empty:
        return
    
    st.subheader("📊 Visit Site Analysis")
    
    # Add time period columns to visits_df if not already present
    visits_df_enhanced = visits_df.copy()
    if 'QuarterYear' not in visits_df_enhanced.columns:
        # Check for NaN values in Date column
        nan_dates = visits_df_enhanced['Date'].isna().sum()
        if nan_dates > 0:
            log_activity(f"Filtered {nan_dates} invalid dates", level='info')
            visits_df_enhanced = visits_df_enhanced.dropna(subset=['Date'])
        
        visits_df_enhanced['Quarter'] = visits_df_enhanced['Date'].dt.quarter
        visits_df_enhanced['Year'] = visits_df_enhanced['Date'].dt.year
        # Handle NaN values before converting to int
        visits_df_enhanced['QuarterYear'] = (
            visits_df_enhanced['Year'].fillna(0).astype(int).astype(str) + '-Q' + 
            visits_df_enhanced['Quarter'].fillna(0).astype(int).astype(str)
        )
    
    # FIXED: Use centralized FY calculation from helpers
    if 'FinancialYear' not in visits_df_enhanced.columns:
        visits_df_enhanced['FinancialYear'] = get_financial_year_for_series(visits_df_enhanced['Date'])
    
    # Always create tabs for all visit sites, even if they have no visits
    # This ensures sites like Kiltearn are visible even when they only have patient recruitment income
    if len(unique_visit_sites) > 1:
        tabs = st.tabs(unique_visit_sites)
        
        for i, visit_site in enumerate(unique_visit_sites):
            with tabs[i]:
                _display_enhanced_single_site_stats(visits_df_enhanced, patients_df, visit_site, screen_failures, withdrawals)
    else:
        # If only one site, display directly
        _display_enhanced_single_site_stats(visits_df_enhanced, patients_df, unique_visit_sites[0], screen_failures, withdrawals)

def _display_enhanced_single_site_stats(visits_df, patients_df, site, screen_failures, withdrawals=None):
    """Display enhanced statistics for a single visit site including quarterly and financial year analysis"""
    try:
        # Filter data for this visit site (where work is actually done)
        site_visits = visits_df[visits_df['SiteofVisit'] == site]
        
        # Find patients who have visits at this site (regardless of their origin)
        patients_with_visits_here = site_visits['PatientID'].unique()
        site_related_patients = patients_df[patients_df['PatientID'].isin(patients_with_visits_here)]
        
        # If no patients with visits at this site, check if there are patients recruited by this site
        if site_related_patients.empty:
            # Use centralized helper function for consistent site detection
            from helpers import get_patient_origin_site
            
            # Create a standardized origin site column and filter
            patients_df['_OriginSite'] = patients_df.apply(
                lambda row: get_patient_origin_site(row, default="Unknown Site"), axis=1
            )
            site_related_patients = patients_df[patients_df['_OriginSite'] == site]
            
            if not site_related_patients.empty:
                log_activity(f"Found {len(site_related_patients)} patients recruited by {site} via standardized site detection", level='info')
            
            if site_related_patients.empty:
                st.warning(f"No patients found for site: {site}")
                return
            else:
                st.info(f"ℹ️ No visits performed at {site}, but showing patient recruitment data")
        
        st.subheader(f"🏥 {site} - Visit Site Analysis")
        
        # Overall statistics
        st.write("**Overall Statistics**")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            total_patients = len(site_related_patients)
            if len(site_visits) > 0:
                st.metric("Patients with visits here", total_patients)
            else:
                st.metric("Patients recruited by this site", total_patients)
        
        with col2:
            # Filter out tolerance window markers (-, +) to get actual visit count
            total_visits = len(site_visits[
                (site_visits['Visit'] != '-') & 
                (site_visits['Visit'] != '+')
            ])
            st.metric("Total Visits", total_visits)
        
        with col3:
            if len(site_visits) > 0:
                actual_visits = len(site_visits[site_visits.get('IsActual', False)])
                st.metric("Completed Visits", actual_visits)
            else:
                st.metric("Recruitment Income", "See below")
        
        with col4:
            if len(site_visits) > 0:
                total_income = site_visits['Payment'].sum()
                st.metric("Total Income", f"£{total_income:,.2f}")
            else:
                st.metric("Visit Income", "£0.00")
        
        # Study breakdown at this visit site
        if len(site_visits) > 0:
            st.write("**Studies performed at this site:**")
        else:
            st.write("**Studies recruited by this site:**")
        
        study_breakdown = site_related_patients.groupby('Study').agg({
            'PatientID': 'count'
        }).rename(columns={'PatientID': 'Patient Count'})
        
        if len(site_visits) > 0:
            # Filter out tolerance window markers (-, +) to get actual visit count
            filtered_site_visits = site_visits[
                (site_visits['Visit'] != '-') & 
                (site_visits['Visit'] != '+')
            ]
            # Add visit counts and income for work done at this site
            visit_breakdown = filtered_site_visits.groupby('Study').agg({
                'Visit': 'count',
                'Payment': 'sum'
            }).rename(columns={'Visit': 'Visit Count', 'Payment': 'Total Income'})
            
            combined_breakdown = study_breakdown.join(visit_breakdown, how='left').fillna(0)
            combined_breakdown['Total Income'] = combined_breakdown['Total Income'].apply(lambda x: f"£{x:,.2f}")
        else:
            # Just show patient recruitment data
            combined_breakdown = study_breakdown.copy()
            combined_breakdown['Visit Count'] = 0
            combined_breakdown['Total Income'] = "£0.00"
        
        st.dataframe(combined_breakdown, width='stretch')
        
        # Patient origin breakdown (who recruited the patients)
        st.write("**Patient Origins (Who Recruited):**")
        # Use PatientPractice as the source of site information
        if 'PatientPractice' in site_related_patients.columns:
            origin_breakdown = site_related_patients.groupby('PatientPractice')['PatientID'].count().reset_index()
            origin_breakdown.columns = ['Origin Site', 'Patients Recruited']
            st.dataframe(origin_breakdown, width='stretch')
        else:
            st.info("No patient practice information available")
        
        # Quarterly Analysis
        if len(site_visits) > 0:
            st.write("**Quarterly Analysis**")
            
            # Filter for relevant visits (exclude tolerance periods)
            financial_site_visits = site_visits[
                (site_visits['Visit'].str.startswith("✅", na=False)) |
                (site_visits['Visit'].str.startswith("⚠️ Screen Fail", na=False)) |
                (site_visits['Visit'].str.startswith("🔴", na=False)) |
                (~site_visits['Visit'].isin(['-', '+']) & (~site_visits.get('IsActual', False)))
            ].copy()
        else:
            st.write("**Quarterly Analysis**")
            st.info("No visits performed at this site - showing patient recruitment analysis only")
            financial_site_visits = pd.DataFrame()  # Empty dataframe
        
        # Initialize empty dataframes to avoid UnboundLocalError
        quarterly_stats = pd.DataFrame()
        fy_stats = pd.DataFrame()
        
        if not financial_site_visits.empty:
            # Quarterly visit and income analysis
            quarterly_stats = financial_site_visits.groupby('QuarterYear').agg({
                'Visit': 'count',
                'Payment': 'sum'
            }).rename(columns={'Visit': 'Visit Count', 'Payment': 'Income'})
            
            if not quarterly_stats.empty:
                quarterly_display = quarterly_stats.copy()
                quarterly_display['Income'] = quarterly_display['Income'].apply(lambda x: f"£{x:,.2f}")
                
                col1, col2 = st.columns(2)
                with col1:
                    st.write("*Visit Counts by Quarter*")
                    st.dataframe(quarterly_stats[['Visit Count']], width='stretch')
                
                with col2:
                    st.write("*Income by Quarter*")
                    st.dataframe(quarterly_display[['Income']], width='stretch')
        
        # Financial Year Analysis
        if len(site_visits) > 0:
            st.write("**Financial Year Analysis**")
        else:
            st.write("**Financial Year Analysis**")
            st.info("No visits performed at this site - showing patient recruitment analysis only")
        
        if not financial_site_visits.empty:
            # Financial year visit and income analysis
            fy_stats = financial_site_visits.groupby('FinancialYear').agg({
                'Visit': 'count',
                'Payment': 'sum'
            }).rename(columns={'Visit': 'Visit Count', 'Payment': 'Income'})
            
            if not fy_stats.empty:
                fy_display = fy_stats.copy()
                fy_display['Income'] = fy_display['Income'].apply(lambda x: f"£{x:,.2f}")
                
                col1, col2 = st.columns(2)
                with col1:
                    st.write("*Visit Counts by Financial Year*")
                    st.dataframe(fy_stats[['Visit Count']], width='stretch')
                
                with col2:
                    st.write("*Income by Financial Year*")
                    st.dataframe(fy_display[['Income']], width='stretch')
        
        # Patient recruitment by time period (for patients who have visits at this site)
        st.write("**Patient Recruitment Analysis**")
        
        # REFACTOR: Use RandomizationDate for recruited patients, with fallbacks
        site_patients_enhanced = site_related_patients.copy()

        # Determine date column to use
        date_column = None
        if 'RandomizationDate' in site_patients_enhanced.columns:
            date_column = 'RandomizationDate'
        elif 'ScreeningDate' in site_patients_enhanced.columns:
            date_column = 'ScreeningDate'
        elif 'StartDate' in site_patients_enhanced.columns:
            date_column = 'StartDate'

        if date_column is None:
            log_activity("No date column found for patient recruitment analysis", level='warning')
            return

        # Check for NaN values in date column
        nan_dates = site_patients_enhanced[date_column].isna().sum()
        if nan_dates > 0:
            log_activity(f"Filtered {nan_dates} invalid dates from {date_column}", level='info')
            site_patients_enhanced = site_patients_enhanced.dropna(subset=[date_column])

        site_patients_enhanced['Quarter'] = site_patients_enhanced[date_column].dt.quarter
        site_patients_enhanced['Year'] = site_patients_enhanced[date_column].dt.year
        # Handle NaN values before converting to int
        site_patients_enhanced['QuarterYear'] = (
            site_patients_enhanced['Year'].fillna(0).astype(int).astype(str) + '-Q' +
            site_patients_enhanced['Quarter'].fillna(0).astype(int).astype(str)
        )
        # FIXED: Use centralized FY calculation from helpers
        site_patients_enhanced['FinancialYear'] = get_financial_year_for_series(site_patients_enhanced[date_column])
        
        # Quarterly patient recruitment
        quarterly_recruitment = site_patients_enhanced.groupby('QuarterYear')['PatientID'].count()
        
        # Financial year patient recruitment
        fy_recruitment = site_patients_enhanced.groupby('FinancialYear')['PatientID'].count()
        
        if not quarterly_recruitment.empty or not fy_recruitment.empty:
            col1, col2 = st.columns(2)
            
            with col1:
                if not quarterly_recruitment.empty:
                    st.write("*Patients Recruited by Quarter*")
                    quarterly_recruitment_df = quarterly_recruitment.to_frame()
                    quarterly_recruitment_df.columns = ['Patients Recruited']
                    st.dataframe(quarterly_recruitment_df, width='stretch')
            
            with col2:
                if not fy_recruitment.empty:
                    st.write("*Patients Recruited by Financial Year*")
                    fy_recruitment_df = fy_recruitment.to_frame()
                    fy_recruitment_df.columns = ['Patients Recruited']
                    st.dataframe(fy_recruitment_df, width='stretch')
        
        # Combined quarterly summary
        st.write("**Quarterly Summary Table**")
        
        # Create comprehensive quarterly summary
        quarterly_summary_data = []
        
        all_quarters = set()
        if not financial_site_visits.empty:
            # Filter out None values from QuarterYear
            quarter_values = financial_site_visits['QuarterYear'].dropna().unique()
            all_quarters.update(quarter_values)
        if not quarterly_recruitment.empty:
            # Filter out None values from index
            quarter_index_values = quarterly_recruitment.index.dropna()
            all_quarters.update(quarter_index_values)
        
        # Filter out any remaining None values and sort safely
        all_quarters = [quarter for quarter in all_quarters if quarter is not None and pd.notna(quarter)]
        try:
            sorted_quarters = sorted(all_quarters)
        except TypeError:
            # If sorting fails due to mixed types, convert all to strings
            sorted_quarters = sorted([str(quarter) for quarter in all_quarters])
        
        for quarter in sorted_quarters:
            quarter_visits = quarterly_stats.loc[quarter, 'Visit Count'] if quarter in quarterly_stats.index else 0
            quarter_income = quarterly_stats.loc[quarter, 'Income'] if quarter in quarterly_stats.index else 0
            quarter_patients = quarterly_recruitment.loc[quarter] if quarter in quarterly_recruitment.index else 0
            
            quarterly_summary_data.append({
                'Quarter': quarter,
                'Patients Recruited': quarter_patients,
                'Visits Completed': quarter_visits,
                'Income': f"£{quarter_income:,.2f}"
            })
        
        if quarterly_summary_data:
            quarterly_summary_df = pd.DataFrame(quarterly_summary_data)
            st.dataframe(quarterly_summary_df, width='stretch')
        
        # Combined financial year summary
        st.write("**Financial Year Summary Table**")
        
        # Create comprehensive financial year summary
        fy_summary_data = []
        
        all_fys = set()
        if not financial_site_visits.empty:
            # Filter out None values from FinancialYear
            fy_values = financial_site_visits['FinancialYear'].dropna().unique()
            all_fys.update(fy_values)
        if not fy_recruitment.empty:
            # Filter out None values from index
            fy_index_values = fy_recruitment.index.dropna()
            all_fys.update(fy_index_values)
        
        # Filter out any remaining None values and sort safely
        all_fys = [fy for fy in all_fys if fy is not None and pd.notna(fy)]
        try:
            sorted_fys = sorted(all_fys)
        except TypeError:
            # If sorting fails due to mixed types, convert all to strings
            sorted_fys = sorted([str(fy) for fy in all_fys])
        
        for fy in sorted_fys:
            fy_visits = fy_stats.loc[fy, 'Visit Count'] if fy in fy_stats.index else 0
            fy_income = fy_stats.loc[fy, 'Income'] if fy in fy_stats.index else 0
            fy_patients = fy_recruitment.loc[fy] if fy in fy_recruitment.index else 0
            
            fy_summary_data.append({
                'Financial Year': fy,
                'Patients Recruited': fy_patients,
                'Visits Completed': fy_visits,
                'Income': f"£{fy_income:,.2f}"
            })
        
        if fy_summary_data:
            fy_summary_df = pd.DataFrame(fy_summary_data)
            st.dataframe(fy_summary_df, width='stretch')
        
        # Screen failures and withdrawals for patients who have visits at this site
        site_screen_failures = []
        site_withdrawals = []
        for patient in site_related_patients.itertuples():
            patient_study_key = f"{patient.PatientID}_{patient.Study}"
            if patient_study_key in screen_failures:
                site_screen_failures.append({
                    'Patient': patient.PatientID,
                    'Study': patient.Study,
                    'Screen Fail Date': screen_failures[patient_study_key].strftime('%Y-%m-%d')
                })
            if withdrawals and patient_study_key in withdrawals:
                site_withdrawals.append({
                    'Patient': patient.PatientID,
                    'Study': patient.Study,
                    'Withdrawal Date': withdrawals[patient_study_key].strftime('%Y-%m-%d')
                })
        
        if site_screen_failures:
            st.write("**Screen Failures**")
            st.dataframe(pd.DataFrame(site_screen_failures), width='stretch')
        
        if site_withdrawals:
            st.write("**Withdrawals**")
            st.dataframe(pd.DataFrame(site_withdrawals), width='stretch')
        
    except Exception as e:
        st.error(f"Error displaying site statistics: {e}")
        st.exception(e)

def display_monthly_analysis_by_site(visits_df):
    """Display monthly analysis broken down by visit site"""
    if visits_df.empty:
        return
    
    st.subheader("📅 Monthly Analysis by Visit Site")
    
    # Create monthly breakdown
    visits_df['MonthYear'] = visits_df['Date'].dt.to_period('M')
    
    # Group by month and visit site (where work is done)
    monthly_site_data = visits_df.groupby(['MonthYear', 'SiteofVisit']).agg({
        'Visit': 'count',
        'Payment': 'sum'
    }).rename(columns={'Visit': 'Visit Count', 'Payment': 'Income'})
    
    # Pivot to show visit sites as columns
    monthly_visits = monthly_site_data['Visit Count'].unstack(fill_value=0)
    monthly_income = monthly_site_data['Income'].unstack(fill_value=0)
    
    # Display visit counts
    st.write("**Monthly Visit Counts by Visit Site:**")
    monthly_visits.index = monthly_visits.index.astype(str)
    st.dataframe(monthly_visits, width='stretch')
    
    # Display income
    st.write("**Monthly Income by Visit Site:**")
    monthly_income_display = monthly_income.copy()
    monthly_income_display.index = monthly_income_display.index.astype(str)
    
    # Format as currency
    for col in monthly_income_display.columns:
        monthly_income_display[col] = monthly_income_display[col].apply(lambda x: f"£{x:,.2f}")
    
    st.dataframe(monthly_income_display, width='stretch')
    
    # Chart showing monthly trends
    if len(monthly_visits.columns) > 1:
        st.write("**Monthly Visit Trends:**")
        st.line_chart(monthly_visits)
        
        st.write("**Monthly Income Trends:**")
        st.line_chart(monthly_income)
