import streamlit as st
import pandas as pd

def extract_site_summary(patients_df, screen_failures=None):
    """Extract site summary statistics"""
    if patients_df.empty:
        return pd.DataFrame()
    
    unique_sites = sorted(patients_df["Site"].unique())
    site_summary_data = []
    
    for site in unique_sites:
        site_patients = patients_df[patients_df["Site"] == site]
        site_studies = site_patients["Study"].unique()
        
        site_screen_fails = 0
        if screen_failures:
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
    
    return pd.DataFrame(site_summary_data)

def extract_screen_failures(actual_visits_df):
    """Extract screen failures from actual visits data"""
    screen_failures = {}
    if actual_visits_df is not None:
        screen_fail_visits = actual_visits_df[
            actual_visits_df["Notes"].str.contains("ScreenFail", case=False, na=False)
        ]
        for _, visit in screen_fail_visits.iterrows():
            patient_study_key = f"{visit['PatientID']}_{visit['Study']}"
            screen_fail_date = visit['ActualDate']
            if patient_study_key not in screen_failures or screen_fail_date < screen_failures[patient_study_key]:
                screen_failures[patient_study_key] = screen_fail_date
    return screen_failures

def prepare_financial_data(visits_df):
    """Prepare financial data for analysis"""
    # FIX: Use consistent emoji symbols
    financial_df = visits_df[
        (visits_df['Visit'].str.startswith("✅")) |
        (visits_df['Visit'].str.startswith("❌ Screen Fail")) |
        (visits_df['Visit'].str.contains('Visit', na=False) & (~visits_df.get('IsActual', False)))
    ].copy()
    
    if not financial_df.empty:
        # Add time columns for profit sharing
        financial_df['Quarter'] = financial_df['Date'].dt.quarter
        financial_df['Year'] = financial_df['Date'].dt.year
        financial_df['QuarterYear'] = financial_df['Year'].astype(str) + '-Q' + financial_df['Quarter'].astype(str)
        financial_df['FinancialYear'] = financial_df['Date'].apply(
            lambda d: f"{d.year}-{d.year+1}" if d.month >= 4 else f"{d.year-1}-{d.year}"
        )
    
    return financial_df

def display_site_wise_statistics(visits_df, patients_df, unique_sites, screen_failures):
    """Display site-wise statistics by month"""
    st.subheader("Site-wise Statistics by Month")
    
    # Create a copy to avoid modifying the original
    visits_df_copy = visits_df.copy()
    
    # Add month-year and financial year columns
    visits_df_copy['MonthYear'] = visits_df_copy['Date'].dt.to_period('M')
    visits_df_copy['FinancialYear'] = visits_df_copy['Date'].apply(
        lambda d: f"{d.year}-{d.year+1}" if d.month >= 4 else f"{d.year-1}-{d.year}"
    )
    
    # Get the full date range for comprehensive monthly analysis
    min_date = visits_df_copy['Date'].min()
    max_date = visits_df_copy['Date'].max()
    all_months = pd.period_range(start=min_date, end=max_date, freq='M')
    
    monthly_site_stats = []
    
    # Process each month in the full range
    for month in all_months:
        month_visits = visits_df_copy[visits_df_copy['MonthYear'] == month]
        
        # Get financial year for this month
        sample_date = month.start_time
        fy = f"{sample_date.year}-{sample_date.year+1}" if sample_date.month >= 4 else f"{sample_date.year-1}-{sample_date.year}"
        
        for site in unique_sites:
            # Get all patients from this site
            site_patients = patients_df[patients_df["Site"] == site]
            
            # Get visits for patients from this site in this month
            site_patient_ids = site_patients['PatientID'].unique()
            site_visits = month_visits[month_visits["PatientID"].isin(site_patient_ids)]
            
            # FIX: Filter relevant visits with consistent emoji symbols
            relevant_visits = site_visits[
                (site_visits["Visit"].str.startswith("✅")) | 
                (site_visits["Visit"].str.startswith("❌ Screen Fail")) | 
                (site_visits["Visit"].str.contains("Visit", na=False))
            ]
            
            # Calculate metrics with safe operations
            site_income = relevant_visits["Payment"].sum() if not relevant_visits.empty else 0
            completed_visits = len(relevant_visits[relevant_visits["Visit"].str.startswith("✅")])
            screen_fail_visits = len(relevant_visits[relevant_visits["Visit"].str.startswith("❌ Screen Fail")])
            total_visits = len(relevant_visits)
            pending_visits = total_visits - completed_visits - screen_fail_visits
            
            # Count new patients recruited this month
            month_start = month.start_time
            month_end = month.end_time
            
            new_patients_this_month = len(site_patients[
                (site_patients['StartDate'] >= month_start) & 
                (site_patients['StartDate'] <= month_end)
            ])
            
            # Only add rows where there's actual activity
            if total_visits > 0 or new_patients_this_month > 0 or site_income > 0:
                monthly_site_stats.append({
                    'Period': str(month),
                    'Financial Year': fy,
                    'Type': 'Month',
                    'Site': site,
                    'New Patients': new_patients_this_month,
                    'Completed Visits': completed_visits,
                    'Screen Fail Visits': screen_fail_visits,
                    'Pending Visits': pending_visits,
                    'Total Visits': total_visits,
                    'Income': f"£{site_income:,.2f}"
                })
    
    # Add financial year summaries
    financial_years = sorted(visits_df_copy['FinancialYear'].unique())
    for fy in financial_years:
        fy_visits = visits_df_copy[visits_df_copy['FinancialYear'] == fy]
        
        for site in unique_sites:
            site_patients = patients_df[patients_df["Site"] == site]
            site_patient_ids = site_patients['PatientID'].unique()
            site_visits = fy_visits[fy_visits["PatientID"].isin(site_patient_ids)]
            
            # FIX: Use consistent emoji symbols
            relevant_visits = site_visits[
                (site_visits["Visit"].str.startswith("✅")) | 
                (site_visits["Visit"].str.startswith("❌ Screen Fail")) | 
                (site_visits["Visit"].str.contains("Visit", na=False))
            ]
            
            # Calculate annual metrics with safe operations
            site_income = relevant_visits["Payment"].sum() if not relevant_visits.empty else 0
            completed_visits = len(relevant_visits[relevant_visits["Visit"].str.startswith("✅")])
            screen_fail_visits = len(relevant_visits[relevant_visits["Visit"].str.startswith("❌ Screen Fail")])
            total_visits = len(relevant_visits)
            pending_visits = total_visits - completed_visits - screen_fail_visits
            
            # Count patients recruited in this financial year
            try:
                fy_start_year = int(fy.split('-')[0])
                fy_start = pd.Timestamp(f"{fy_start_year}-04-01")
                fy_end = pd.Timestamp(f"{fy_start_year + 1}-03-31")
                
                fy_new_patients = len(site_patients[
                    (site_patients['StartDate'] >= fy_start) & 
                    (site_patients['StartDate'] <= fy_end)
                ])
            except (ValueError, IndexError):
                fy_new_patients = 0
            
            # Count screen failures for this financial year
            site_screen_fails = 0
            if screen_failures:
                for _, patient in site_patients.iterrows():
                    patient_study_key = f"{patient['PatientID']}_{patient['Study']}"
                    if patient_study_key in screen_failures:
                        screen_fail_date = screen_failures[patient_study_key]
                        try:
                            if fy_start <= screen_fail_date <= fy_end:
                                site_screen_fails += 1
                        except (TypeError, NameError):
                            pass
            
            active_patients = max(0, fy_new_patients - site_screen_fails)
            
            monthly_site_stats.append({
                'Period': f"FY {fy}",
                'Financial Year': fy,
                'Type': 'Financial Year',
                'Site': site,
                'New Patients': f"{fy_new_patients} ({active_patients} active)",
                'Completed Visits': completed_visits,
                'Screen Fail Visits': screen_fail_visits,
                'Pending Visits': pending_visits,
                'Total Visits': total_visits,
                'Income': f"£{site_income:,.2f}"
            })
    
    if monthly_site_stats:
        # Sort and display by site
        monthly_site_stats.sort(key=lambda x: (x['Financial Year'], x['Type'] == 'Financial Year', x['Period'], x['Site']))
        
        for site in unique_sites:
            st.write(f"**{site} Practice**")
            
            site_data = [stat for stat in monthly_site_stats if stat['Site'] == site]
            if site_data:
                site_df = pd.DataFrame(site_data)
                display_df = site_df.drop('Site', axis=1)
                
                def highlight_fy_rows(row):
                    if row['Type'] == 'Financial Year':
                        return ['background-color: #e6f3ff; font-weight: bold'] * len(row)
                    else:
                        return [''] * len(row)
                
                styled_site_df = display_df.style.apply(highlight_fy_rows, axis=1)
                st.dataframe(styled_site_df, use_container_width=True)
                st.write("")
            else:
                st.write("No activity recorded for this site")
                st.write("")
        
        st.info("""
        **Site Statistics Notes:**
        - **Blue highlighted rows** = Financial Year totals (April to March)
        - **New Patients** = Patients recruited in that period (based on StartDate)
        - **Income** = Clinical trial income generated from visits
        - Only months/periods with activity are shown
        - Financial year rows show annual totals and active patient counts
        """)

def display_monthly_analysis_by_site(visits_df):
    """Display monthly analysis by site"""
    st.subheader("Monthly Analysis by Site")
    
    # FIX: Filter only actual visits and main scheduled visits with consistent emoji symbols
    analysis_visits = visits_df[
        (visits_df['Visit'].str.startswith("✅")) |
        (visits_df['Visit'].str.startswith("❌ Screen Fail")) |
        (visits_df['Visit'].str.contains('Visit', na=False) & (~visits_df.get('IsActual', False)))
    ].copy()
    
    if not analysis_visits.empty:
        # Ensure MonthYear column exists
        if 'MonthYear' not in analysis_visits.columns:
            analysis_visits['MonthYear'] = analysis_visits['Date'].dt.to_period('M')
        
        # Analysis by Visit Location
        st.write("**Analysis by Visit Location (Where visits occur)**")
        visits_by_site_month = analysis_visits.groupby(['SiteofVisit', 'MonthYear']).size().reset_index(name='Visits')
        
        if not visits_by_site_month.empty:
            visits_pivot = visits_by_site_month.pivot(index='MonthYear', columns='SiteofVisit', values='Visits').fillna(0)
            visits_pivot['Total_Visits'] = visits_pivot.sum(axis=1)
            visit_sites = [col for col in visits_pivot.columns if col != 'Total_Visits']
            
            # FIX: Safe ratio calculations
            for site in visit_sites:
                try:
                    visits_pivot[f'{site}_Ratio'] = (visits_pivot[site] / visits_pivot['Total_Visits'] * 100).round(1)
                    visits_pivot[f'{site}_Ratio'] = visits_pivot[f'{site}_Ratio'].fillna(0)  # Handle division by zero
                except (ZeroDivisionError, KeyError):
                    visits_pivot[f'{site}_Ratio'] = 0
            
            # Count unique patients by visit site per month
            patients_by_visit_site_month = analysis_visits.groupby(['SiteofVisit', 'MonthYear'])['PatientID'].nunique().reset_index(name='Patients')
            patients_visit_pivot = patients_by_visit_site_month.pivot(index='MonthYear', columns='SiteofVisit', values='Patients').fillna(0)
            patients_visit_pivot['Total_Patients'] = patients_visit_pivot.sum(axis=1)
            
            # FIX: Safe ratio calculations for patients
            for site in visit_sites:
                if site in patients_visit_pivot.columns:
                    try:
                        patients_visit_pivot[f'{site}_Ratio'] = (patients_visit_pivot[site] / patients_visit_pivot['Total_Patients'] * 100).round(1)
                        patients_visit_pivot[f'{site}_Ratio'] = patients_visit_pivot[f'{site}_Ratio'].fillna(0)
                    except (ZeroDivisionError, KeyError):
                        patients_visit_pivot[f'{site}_Ratio'] = 0
            
            # Analysis by Patient Origin
            st.write("**Analysis by Patient Origin (Where patients come from)**")
            patients_by_origin_month = analysis_visits.groupby(['PatientOrigin', 'MonthYear'])['PatientID'].nunique().reset_index(name='Patients')
            patients_origin_pivot = patients_by_origin_month.pivot(index='MonthYear', columns='PatientOrigin', values='Patients').fillna(0)
            patients_origin_pivot['Total_Patients'] = patients_origin_pivot.sum(axis=1)
            origin_sites = [col for col in patients_origin_pivot.columns if col != 'Total_Patients']
            
            # FIX: Safe ratio calculations for origin
            for site in origin_sites:
                try:
                    patients_origin_pivot[f'{site}_Ratio'] = (patients_origin_pivot[site] / patients_origin_pivot['Total_Patients'] * 100).round(1)
                    patients_origin_pivot[f'{site}_Ratio'] = patients_origin_pivot[f'{site}_Ratio'].fillna(0)
                except (ZeroDivisionError, KeyError):
                    patients_origin_pivot[f'{site}_Ratio'] = 0
            
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
            
            # FIX: Safe percentage calculations for cross-tabulation
            for col in cross_pivot.columns:
                if col != 'Total':
                    try:
                        cross_pivot[f'{col}_%'] = (cross_pivot[col] / cross_pivot['Total'] * 100).round(1)
                        cross_pivot[f'{col}_%'] = cross_pivot[f'{col}_%'].fillna(0)
                    except (ZeroDivisionError, KeyError):
                        cross_pivot[f'{col}_%'] = 0
            
            st.dataframe(cross_pivot, use_container_width=True)
            
            # Charts
            st.subheader("Monthly Trends")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.write("**Visits by Visit Site**")
                if not visits_pivot.empty:
                    chart_data = visits_pivot[[col for col in visits_pivot.columns if not col.endswith('_Ratio') and col != 'Total_Visits']]
                    chart_data.index = chart_data.index.astype(str)
                    if not chart_data.empty:
                        st.bar_chart(chart_data)
            
            with col2:
                st.write("**Patients by Visit Site**") 
                if not patients_visit_pivot.empty:
                    chart_data = patients_visit_pivot[[col for col in patients_visit_pivot.columns if not col.endswith('_Ratio') and col != 'Total_Patients']]
                    chart_data.index = chart_data.index.astype(str)
                    if not chart_data.empty:
                        st.bar_chart(chart_data)
            
            with col3:
                st.write("**Patients by Origin Site**")
                if not patients_origin_pivot.empty:
                    chart_data = patients_origin_pivot[[col for col in patients_origin_pivot.columns if not col.endswith('_Ratio') and col != 'Total_Patients']]
                    chart_data.index = chart_data.index.astype(str)
                    if not chart_data.empty:
                        st.bar_chart(chart_data)
        else:
            st.info("No visit data available for monthly analysis")
    else:
        st.info("No visit data available for analysis")

def display_processing_messages(messages):
    """Display processing log messages"""
    if messages:
        with st.expander("Processing Log", expanded=False):
            for message in messages:
                st.write(message)
