import streamlit as st
import pandas as pd
from formatters import (
    apply_currency_formatting, apply_currency_or_empty_formatting,
    create_fy_highlighting_function, format_dataframe_index_as_string,
    format_currency, clean_numeric_for_display, apply_conditional_formatting
)
from calculations import (
    calculate_income_realization_metrics, calculate_monthly_realization_breakdown,
    calculate_study_pipeline_breakdown, calculate_site_realization_breakdown
)

def create_pivot_income_table(financial_df, group_cols, period_col, value_col='Payment'):
    """Create a pivot table for income analysis"""
    if financial_df.empty:
        return None, None
    
    income_by_period = financial_df.groupby(group_cols)[value_col].sum().reset_index()
    if income_by_period.empty:
        return None, None
    
    pivot = income_by_period.pivot(index=period_col, columns='SiteofVisit', values=value_col).fillna(0)
    pivot['Total'] = pivot.sum(axis=1)
    
    return pivot, income_by_period

def create_financial_year_totals(financial_df, site_columns):
    """Create financial year totals for income data"""
    fy_totals = []
    for fy in sorted(financial_df['FinancialYear'].unique()):
        fy_data = financial_df[financial_df['FinancialYear'] == fy]
        fy_income_by_site = fy_data.groupby('SiteofVisit')['Payment'].sum()
        
        fy_row = {}
        for site in site_columns:
            if site == 'Total':
                fy_row[site] = fy_income_by_site.sum()
            else:
                fy_row[site] = fy_income_by_site.get(site, 0)
        
        fy_totals.append((f"FY {fy}", fy_row))
    
    return fy_totals

def display_income_table_pair(financial_df):
    """Display monthly and quarterly income tables side by side"""
    # Monthly analysis
    monthly_pivot, _ = create_pivot_income_table(
        financial_df, ['SiteofVisit', 'MonthYear'], 'MonthYear'
    )
    
    # Quarterly analysis
    quarterly_pivot, _ = create_pivot_income_table(
        financial_df, ['SiteofVisit', 'QuarterYear'], 'QuarterYear'
    )
    
    if monthly_pivot is not None and quarterly_pivot is not None:
        # Create financial year totals
        fy_monthly_totals = create_financial_year_totals(financial_df, monthly_pivot.columns)
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**Monthly Income by Visit Site**")
            monthly_display = format_dataframe_index_as_string(monthly_pivot)
            monthly_display = apply_currency_formatting(monthly_display, monthly_display.columns)
            st.dataframe(monthly_display, use_container_width=True)
            
            # Financial year totals for monthly
            if fy_monthly_totals:
                st.write("**Financial Year Totals (Monthly)**")
                display_fy_totals_table(fy_monthly_totals)
        
        with col2:
            st.write("**Quarterly Income by Visit Site**")
            quarterly_display = apply_currency_formatting(quarterly_pivot, quarterly_pivot.columns)
            st.dataframe(quarterly_display, use_container_width=True)

def display_fy_totals_table(fy_totals):
    """Display financial year totals table"""
    fy_data = []
    for fy_name, fy_row in fy_totals:
        formatted_row = {"Financial Year": fy_name}
        for col, val in fy_row.items():
            formatted_row[col] = format_currency(val)
        fy_data.append(formatted_row)
    
    fy_df = pd.DataFrame(fy_data)
    st.dataframe(fy_df, use_container_width=True)

def create_styled_dataframe(df, highlight_column=None, highlight_value=None):
    """Create a styled dataframe with optional highlighting"""
    if highlight_column and highlight_value:
        style_dict = {"bg_color": "#e6f3ff", "weight": "bold"}
        return apply_conditional_formatting(df, highlight_column, highlight_value, style_dict)
    return df

def display_profit_sharing_table(quarterly_ratios):
    """Display the main profit sharing analysis table"""
    if not quarterly_ratios:
        st.warning("No quarterly data available for analysis.")
        return
    
    quarterly_df = pd.DataFrame(quarterly_ratios)
    
    # Style to highlight financial year rows
    highlight_function = create_fy_highlighting_function()
    styled_df = quarterly_df.style.apply(highlight_function, axis=1)
    
    st.write("**Quarterly Profit Sharing Analysis**")
    st.dataframe(styled_df, use_container_width=True)

def display_ratio_breakdown_table(ratio_data, title):
    """Display a ratio breakdown table"""
    if not ratio_data:
        return
    
    st.write(f"**{title}**")
    ratio_df = pd.DataFrame(ratio_data)
    st.dataframe(ratio_df, use_container_width=True)

def create_summary_metrics_row(data_dict, columns=4):
    """Create a row of metric displays"""
    cols = st.columns(columns)
    
    for i, (label, value) in enumerate(data_dict.items()):
        with cols[i % columns]:
            st.metric(label, value)

def display_breakdown_by_study(df, patient_df, site):
    """Display study breakdown for a specific site"""
    site_patients = patient_df[patient_df['Site'] == site]
    site_visits = df[df['SiteofVisit'] == site]
    
    if site_patients.empty:
        return
    
    # Study breakdown
    study_breakdown = site_patients.groupby('Study').agg({
        'PatientID': 'count'
    }).rename(columns={'PatientID': 'Patient Count'})
    
    # Add visit counts and income
    visit_breakdown = site_visits.groupby('Study').agg({
        'Visit': 'count',
        'Payment': 'sum'
    }).rename(columns={'Visit': 'Visit Count', 'Payment': 'Total Income'})
    
    # Combine data
    combined_breakdown = study_breakdown.join(visit_breakdown, how='left').fillna(0)
    combined_breakdown = apply_currency_formatting(combined_breakdown, ['Total Income'])
    
    st.dataframe(combined_breakdown, use_container_width=True)

def create_time_period_config():
    """Configuration for different time periods"""
    return {
        'monthly': {
            'column': 'MonthYear',
            'name': 'Month',
            'title': 'Monthly Ratio Breakdowns'
        },
        'quarterly': {
            'column': 'QuarterYear', 
            'name': 'Quarter',
            'title': 'Quarterly Ratio Breakdowns'
        },
        'financial_year': {
            'column': 'FinancialYear',
            'name': 'Financial Year', 
            'title': 'Financial Year Ratio Breakdowns'
        }
    }

def display_site_time_analysis(visits_df, patients_df, site, enhanced_visits_df):
    """Display time-based analysis for a specific site"""
    st.write("**Quarterly Analysis**")
    
    # Filter for financial visits only
    financial_site_visits = enhanced_visits_df[enhanced_visits_df['SiteofVisit'] == site]
    
    if not financial_site_visits.empty:
        # Quarterly stats
        quarterly_stats = financial_site_visits.groupby('QuarterYear').agg({
            'Visit': 'count',
            'Payment': 'sum'
        }).rename(columns={'Visit': 'Visit Count', 'Payment': 'Income'})
        
        # Financial year stats  
        fy_stats = financial_site_visits.groupby('FinancialYear').agg({
            'Visit': 'count',
            'Payment': 'sum'
        }).rename(columns={'Visit': 'Visit Count', 'Payment': 'Income'})
        
        if not quarterly_stats.empty:
            col1, col2 = st.columns(2)
            
            with col1:
                st.write("*Visit Counts by Quarter*")
                st.dataframe(quarterly_stats[['Visit Count']], use_container_width=True)
            
            with col2:
                quarterly_display = apply_currency_formatting(quarterly_stats[['Income']], ['Income'])
                st.write("*Income by Quarter*")
                st.dataframe(quarterly_display, use_container_width=True)
        
        st.write("**Financial Year Analysis**")
        
        if not fy_stats.empty:
            col1, col2 = st.columns(2)
            
            with col1:
                st.write("*Visit Counts by Financial Year*")
                st.dataframe(fy_stats[['Visit Count']], use_container_width=True)
            
            with col2:
                fy_display = apply_currency_formatting(fy_stats[['Income']], ['Income'])
                st.write("*Income by Financial Year*")
                st.dataframe(fy_display, use_container_width=True)

def display_site_recruitment_analysis(site_patients, enhanced_visits_df, site):
    """Display patient recruitment analysis for a site"""
    st.write("**Patient Recruitment Analysis**")
    
    # Add time period columns to patients
    site_patients_enhanced = site_patients.copy()
    site_patients_enhanced['Quarter'] = site_patients_enhanced['StartDate'].dt.quarter
    site_patients_enhanced['Year'] = site_patients_enhanced['StartDate'].dt.year
    site_patients_enhanced['QuarterYear'] = site_patients_enhanced['Year'].astype(str) + '-Q' + site_patients_enhanced['Quarter'].astype(str)
    site_patients_enhanced['FinancialYear'] = site_patients_enhanced['StartDate'].apply(
        lambda d: f"{d.year}-{d.year+1}" if d.month >= 4 else f"{d.year-1}-{d.year}"
    )
    
    # Recruitment summaries
    quarterly_recruitment = site_patients_enhanced.groupby('QuarterYear')['PatientID'].count()
    fy_recruitment = site_patients_enhanced.groupby('FinancialYear')['PatientID'].count()
    
    if not quarterly_recruitment.empty or not fy_recruitment.empty:
        col1, col2 = st.columns(2)
        
        with col1:
            if not quarterly_recruitment.empty:
                st.write("*Patients Recruited by Quarter*")
                quarterly_df = quarterly_recruitment.to_frame()
                quarterly_df.columns = ['Patients Recruited']
                st.dataframe(quarterly_df, use_container_width=True)
        
        with col2:
            if not fy_recruitment.empty:
                st.write("*Patients Recruited by Financial Year*")
                fy_df = fy_recruitment.to_frame()
                fy_df.columns = ['Patients Recruited']
                st.dataframe(fy_df, use_container_width=True)
    
    # Combined summary tables
    display_site_summary_tables(site_patients_enhanced, enhanced_visits_df, site, quarterly_recruitment, fy_recruitment)

def display_site_summary_tables(site_patients, enhanced_visits_df, site, quarterly_recruitment, fy_recruitment):
    """Display combined summary tables for a site"""
    site_enhanced_visits = enhanced_visits_df[enhanced_visits_df['SiteofVisit'] == site]
    
    # Quarterly summary
    st.write("**Quarterly Summary Table**")
    quarterly_summary = build_period_summary(
        site_enhanced_visits, quarterly_recruitment, 'QuarterYear', 'Quarter'
    )
    if quarterly_summary:
        st.dataframe(pd.DataFrame(quarterly_summary), use_container_width=True)
    
    # Financial year summary  
    st.write("**Financial Year Summary Table**")
    fy_summary = build_period_summary(
        site_enhanced_visits, fy_recruitment, 'FinancialYear', 'Financial Year'
    )
    if fy_summary:
        st.dataframe(pd.DataFrame(fy_summary), use_container_width=True)

def build_period_summary(visits_df, recruitment_series, period_col, period_name):
    """Build summary data for a time period"""
    if visits_df.empty:
        return []
    
    visit_stats = visits_df.groupby(period_col).agg({'Visit': 'count', 'Payment': 'sum'})
    all_periods = set(visit_stats.index) | set(recruitment_series.index)
    
    summary_data = []
    for period in sorted(all_periods):
        visits = visit_stats.loc[period, 'Visit'] if period in visit_stats.index else 0
        income = visit_stats.loc[period, 'Payment'] if period in visit_stats.index else 0
        patients = recruitment_series.loc[period] if period in recruitment_series.index else 0
        
        summary_data.append({
            period_name: period if period_name == 'Quarter' else period,
            'Patients Recruited': clean_numeric_for_display(patients),
            'Visits Completed': clean_numeric_for_display(visits),
            'Income': format_currency(income)
        })
    
    return summary_data

def display_site_screen_failures(site_patients, screen_failures):
    """Display screen failures for a site"""
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
        st.write("**Screen Failures**")
        st.dataframe(pd.DataFrame(site_screen_failures), use_container_width=True)

def create_excel_export_data(calendar_df, site_column_mapping, unique_sites):
    """Prepare data for Excel export with proper formatting"""
    # Get ordered columns
    final_ordered_columns = ["Date", "Day"]
    for site in unique_sites:
        site_columns = site_column_mapping.get(site, [])
        for col in site_columns:
            if col in calendar_df.columns:
                final_ordered_columns.append(col)

    # Add financial columns
    excel_financial_cols = ["Daily Total", "Monthly Total", "FY Total"] + [c for c in calendar_df.columns if "Income" in c]
    all_columns = final_ordered_columns + [col for col in excel_financial_cols if col in calendar_df.columns]
    
    excel_df = calendar_df[all_columns].copy()
    
    # Format dates and currency
    excel_df["Date"] = excel_df["Date"].dt.strftime("%d/%m/%Y")
    excel_df = apply_currency_or_empty_formatting(excel_df, ["Monthly Total", "FY Total"])
    excel_df = apply_currency_formatting(excel_df, [col for col in excel_financial_cols if col not in ["Monthly Total", "FY Total"] and col in excel_df.columns])
    
    return excel_df

def apply_excel_formatting(ws, excel_df, site_column_mapping, unique_sites):
    """Apply formatting to Excel worksheet"""
    try:
        from openpyxl.styles import PatternFill, Font, Alignment
        from openpyxl.utils import get_column_letter
        
        # Add site headers
        for col_idx, col_name in enumerate(excel_df.columns, 1):
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
        for idx, col in enumerate(excel_df.columns, 1):
            col_letter = get_column_letter(idx)
            max_length = max([len(str(cell)) if cell is not None else 0 for cell in excel_df[col].tolist()] + [len(col)])
            ws.column_dimensions[col_letter].width = max(10, max_length + 2)
    except ImportError:
        # If openpyxl styles not available, skip formatting
        pass

def display_complete_realization_analysis(visits_df, trials_df, patients_df):
    """Display complete income realization analysis"""
    st.subheader("💰 Income Realization Analysis")
    
    # Calculate overall metrics
    overall_metrics = calculate_income_realization_metrics(visits_df, trials_df, patients_df)
    
    # Display key metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Completed Income", format_currency(overall_metrics['completed_income']))
    with col2:
        st.metric("Total Scheduled", format_currency(overall_metrics['total_scheduled_income']))
    with col3:
        st.metric("Pipeline Remaining", format_currency(overall_metrics['pipeline_income']))
    with col4:
        st.metric("Realization Rate", f"{overall_metrics['realization_rate']:.1f}%")
    
    # Monthly breakdown
    st.write("**Monthly Realization Breakdown**")
    monthly_data = calculate_monthly_realization_breakdown(visits_df, trials_df)
    
    if monthly_data:
        monthly_df = pd.DataFrame(monthly_data)
        monthly_df['Completed_Income'] = monthly_df['Completed_Income'].apply(format_currency)
        monthly_df['Scheduled_Income'] = monthly_df['Scheduled_Income'].apply(format_currency)
        monthly_df['Realization_Rate'] = monthly_df['Realization_Rate'].apply(lambda x: f"{x:.1f}%")
        
        # Rename columns for display
        monthly_df = monthly_df.rename(columns={
            'Month': 'Month',
            'Completed_Income': 'Completed Income',
            'Scheduled_Income': 'Scheduled Income', 
            'Realization_Rate': 'Realization %',
            'Completed_Visits': 'Completed Visits',
            'Scheduled_Visits': 'Total Visits'
        })
        
        st.dataframe(monthly_df, use_container_width=True)
    
    # Study pipeline breakdown
    st.write("**Study Pipeline Breakdown**")
    study_pipeline = calculate_study_pipeline_breakdown(visits_df, trials_df)
    
    if not study_pipeline.empty:
        study_pipeline_display = study_pipeline.copy()
        study_pipeline_display['Pipeline_Value'] = study_pipeline_display['Pipeline_Value'].apply(format_currency)
        study_pipeline_display = study_pipeline_display.rename(columns={
            'Study': 'Study',
            'Pipeline_Value': 'Pipeline Value',
            'Remaining_Visits': 'Remaining Visits'
        })
        st.dataframe(study_pipeline_display, use_container_width=True)
    
    # Site realization breakdown
    st.write("**Site Realization Breakdown**")
    site_data = calculate_site_realization_breakdown(visits_df, trials_df)
    
    if site_data:
        site_df = pd.DataFrame(site_data)
        site_df['Completed_Income'] = site_df['Completed_Income'].apply(format_currency)
        site_df['Total_Scheduled_Income'] = site_df['Total_Scheduled_Income'].apply(format_currency)
        site_df['Pipeline_Income'] = site_df['Pipeline_Income'].apply(format_currency)
        site_df['Realization_Rate'] = site_df['Realization_Rate'].apply(lambda x: f"{x:.1f}%")
        
        site_df = site_df.rename(columns={
            'Site': 'Site',
            'Completed_Income': 'Completed Income',
            'Total_Scheduled_Income': 'Total Scheduled',
            'Pipeline_Income': 'Pipeline Value',
            'Realization_Rate': 'Realization %',
            'Completed_Visits': 'Completed Visits',
            'Total_Visits': 'Total Visits',
            'Remaining_Visits': 'Remaining Visits'
        })
        
        st.dataframe(site_df, use_container_width=True)
    
    # Analysis notes
    st.info("""
    **Income Realization Analysis Notes:**
    - **Completed Income**: Actual payments received from completed visits
    - **Total Scheduled**: Full potential income if all scheduled visits are completed
    - **Pipeline Value**: Expected income from remaining scheduled visits
    - **Realization Rate**: Percentage of scheduled income actually realized
    - Analysis covers current financial year only (April to March)
    """)
