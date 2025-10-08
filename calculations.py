import pandas as pd
import streamlit as st
from datetime import date
from helpers import get_financial_year, get_current_financial_year_boundaries, create_trial_payment_lookup, get_trial_payment_for_visit, log_activity

def prepare_financial_data(visits_df):
    """Prepare visits data with financial period columns"""
    if visits_df.empty:
        return pd.DataFrame()
    
    # Create copy first
    financial_df = visits_df.copy()
    
    # Debug: Log input data
    from helpers import log_activity
    log_activity(f"Input visits_df shape: {visits_df.shape}", level='info')
    log_activity(f"Input columns: {list(visits_df.columns)}", level='info')
    if 'Date' in visits_df.columns:
        log_activity(f"Date column type: {visits_df['Date'].dtype}", level='info')
        log_activity(f"Sample dates: {visits_df['Date'].head().tolist()}", level='info')
    
    # Ensure Payment column exists for financial calculations and is numeric
    if 'Payment' not in financial_df.columns:
        financial_df['Payment'] = 0.0
    else:
        # Convert to numeric, replacing non-numeric values with 0
        financial_df['Payment'] = pd.to_numeric(financial_df['Payment'], errors='coerce').fillna(0.0)
    
    # Filter for relevant visits (exclude only tolerance periods '-' and '+')
    # Include: actual visits (with ✅, 🔴, ⚠  ), scheduled visits (plain visit names), but exclude tolerance periods
    mask = ~financial_df['Visit'].isin(['-', '+'])
    
    financial_df = financial_df[mask].copy()
    
    # Debug: Log after filtering
    log_activity(f"After filtering shape: {financial_df.shape}", level='info')
    log_activity(f"Visit values: {financial_df['Visit'].unique() if not financial_df.empty else 'Empty'}", level='info')

    if financial_df.empty:
        # If filtering results in empty df, create empty df with required columns and proper structure
        empty_df = pd.DataFrame()
        # Add all the required columns that the rest of the code expects
        for col in ['Date', 'Visit', 'Study', 'Payment', 'SiteofVisit', 'PatientOrigin', 
                   'IsActual', 'IsScreenFail', 'IsOutOfProtocol', 'VisitDay', 'VisitName',
                   'MonthYear', 'Quarter', 'Year', 'QuarterYear', 'FinancialYear']:
            empty_df[col] = pd.Series(dtype='object')
        return empty_df
        
    # Add all time period columns
    # Check for NaN values in Date column
    nan_dates = financial_df['Date'].isna().sum()
    if nan_dates > 0:
        # Filter out invalid dates silently
        log_activity(f"Removing {nan_dates} rows with NaN dates", level='info')
        financial_df = financial_df.dropna(subset=['Date'])
    
    # Debug: Log before creating time columns
    log_activity(f"Before time columns - shape: {financial_df.shape}", level='info')
    log_activity(f"Date column type: {financial_df['Date'].dtype}", level='info')
    log_activity(f"Sample dates: {financial_df['Date'].head().tolist()}", level='info')
    
    financial_df['MonthYear'] = financial_df['Date'].dt.to_period('M')
    financial_df['Quarter'] = financial_df['Date'].dt.quarter
    financial_df['Year'] = financial_df['Date'].dt.year
    # Handle NaN values before converting to int
    financial_df['QuarterYear'] = (
        financial_df['Year'].fillna(0).astype(int).astype(str) + '-Q' + 
        financial_df['Quarter'].fillna(0).astype(int).astype(str)
    )
    
    # FIXED: Use consistent FY calculation from helpers
    financial_df['FinancialYear'] = financial_df['Date'].apply(get_financial_year)
    
    # Debug: Log final result
    log_activity(f"Final financial_df shape: {financial_df.shape}", level='info')
    log_activity(f"Unique MonthYear values: {financial_df['MonthYear'].unique()}", level='info')
    log_activity(f"Payment sum: {financial_df['Payment'].sum()}", level='info')
    
    return financial_df

def calculate_work_ratios(data_df, period_column, period_value):
    """Calculate work done ratios for a specific period"""
    if data_df.empty or period_column not in data_df.columns:
        return {
            'ashfields_work_ratio': 0,
            'kiltearn_work_ratio': 0,
            'total_work': 0,
            'ashfields_work_count': 0,
            'kiltearn_work_count': 0
        }
    
    period_data = data_df[data_df[period_column] == period_value]
    
    if len(period_data) == 0 or 'SiteofVisit' not in period_data.columns:
        return {
            'ashfields_work_ratio': 0,
            'kiltearn_work_ratio': 0,
            'total_work': 0,
            'ashfields_work_count': 0,
            'kiltearn_work_count': 0
        }
    
    # CRITICAL FIX: Only count work at Ashfields and Kiltearn
    # Exclude third-party sites from profit sharing work calculations
    relevant_sites = ['Ashfields', 'Kiltearn']
    period_data_filtered = period_data[period_data['SiteofVisit'].isin(relevant_sites)]
    
    if len(period_data_filtered) == 0:
        # No work at either practice this period
        return {
            'ashfields_work_ratio': 0,
            'kiltearn_work_ratio': 0,
            'total_work': 0,
            'ashfields_work_count': 0,
            'kiltearn_work_count': 0
        }
    
    site_work = period_data_filtered.groupby('SiteofVisit').size()
    total_work = site_work.sum()
    
    # Verification logging
    log_activity(f"Work calculation for period {period_value}:", level='info')
    log_activity(f"  Total work items in period: {len(period_data)}", level='info')
    if 'period_data_filtered' in locals():
        log_activity(f"  Work items at Ashfields/Kiltearn: {len(period_data_filtered)}", level='info')
        excluded_count = len(period_data) - len(period_data_filtered)
        if excluded_count > 0:
            excluded_sites = period_data[~period_data['SiteofVisit'].isin(['Ashfields', 'Kiltearn'])]['SiteofVisit'].unique()
            log_activity(f"  Excluded {excluded_count} visits at third-party sites: {excluded_sites}", level='warning')
    
    ashfields_count = site_work.get('Ashfields', 0)
    kiltearn_count = site_work.get('Kiltearn', 0)
    
    return {
        'ashfields_work_ratio': ashfields_count / total_work if total_work > 0 else 0,
        'kiltearn_work_ratio': kiltearn_count / total_work if total_work > 0 else 0,
        'total_work': total_work,
        'ashfields_work_count': ashfields_count,
        'kiltearn_work_count': kiltearn_count
    }

def calculate_recruitment_ratios(patients_df, period_column, period_value):
    """Calculate patient recruitment ratios for a specific period"""
    if patients_df.empty or 'StartDate' not in patients_df.columns:
        return {
            'ashfields_recruitment_ratio': 0,
            'kiltearn_recruitment_ratio': 0,
            'total_recruitment': 0,
            'ashfields_recruitment_count': 0,
            'kiltearn_recruitment_count': 0
        }
    
    try:
        if period_column == 'MonthYear':
            period_patients = patients_df[patients_df['StartDate'].dt.to_period('M').astype(str) == str(period_value)]
        elif period_column == 'QuarterYear':
            # Convert both to strings for comparison
            # Handle NaN values before converting to int
            patients_quarter = (
                patients_df['StartDate'].dt.year.fillna(0).astype(int).astype(str) + '-Q' + 
                patients_df['StartDate'].dt.quarter.fillna(0).astype(int).astype(str)
            )
            period_patients = patients_df[patients_quarter == str(period_value)]
        elif period_column == 'FinancialYear':
            # FIXED: Use centralized FY calculation from helpers
            patient_fy = patients_df['StartDate'].apply(get_financial_year)
            period_patients = patients_df[patient_fy == str(period_value)]
        else:
            return {
                'ashfields_recruitment_ratio': 0,
                'kiltearn_recruitment_ratio': 0,
                'total_recruitment': 0,
                'ashfields_recruitment_count': 0,
                'kiltearn_recruitment_count': 0
            }
        
        # Use centralized helper function for consistent site detection
        from helpers import get_patient_origin_site
        
        # Create a temporary column with standardized origin site
        period_patients['_OriginSite'] = period_patients.apply(
            lambda row: get_patient_origin_site(row), axis=1
        )
        site_column = '_OriginSite'

        if period_patients.empty:
            return {
                'ashfields_recruitment_ratio': 0,
                'kiltearn_recruitment_ratio': 0,
                'total_recruitment': 0,
                'ashfields_recruitment_count': 0,
                'kiltearn_recruitment_count': 0
            }
        
        recruitment = period_patients.groupby(site_column)['PatientID'].count()
        total_recruitment = recruitment.sum()
        
        ashfields_count = recruitment.get('Ashfields', 0)
        kiltearn_count = recruitment.get('Kiltearn', 0)
        
        return {
            'ashfields_recruitment_ratio': ashfields_count / total_recruitment if total_recruitment > 0 else 0,
            'kiltearn_recruitment_ratio': kiltearn_count / total_recruitment if total_recruitment > 0 else 0,
            'total_recruitment': total_recruitment,
            'ashfields_recruitment_count': ashfields_count,
            'kiltearn_recruitment_count': kiltearn_count
        }
    except Exception as e:
        st.error(f"Error calculating recruitment ratios for {period_value}: {e}")
        return {
            'ashfields_recruitment_ratio': 0,
            'kiltearn_recruitment_ratio': 0,
            'total_recruitment': 0,
            'ashfields_recruitment_count': 0,
            'kiltearn_recruitment_count': 0
        }

def calculate_combined_ratios(list_ratios, work_ratios, recruitment_ratios, weights):
    """Calculate final combined profit sharing ratios"""
    list_weight, work_weight, recruitment_weight = weights
    
    # Get list ratios
    ashfields_list_ratio = list_ratios['ashfields']
    kiltearn_list_ratio = list_ratios['kiltearn']
    
    # Calculate combined ratios
    ashfields_final = (ashfields_list_ratio * list_weight + 
                      work_ratios['ashfields_work_ratio'] * work_weight + 
                      recruitment_ratios['ashfields_recruitment_ratio'] * recruitment_weight)
    
    kiltearn_final = (kiltearn_list_ratio * list_weight + 
                     work_ratios['kiltearn_work_ratio'] * work_weight + 
                     recruitment_ratios['kiltearn_recruitment_ratio'] * recruitment_weight)
    
    # Normalize to ensure they sum to 1
    total_ratio = ashfields_final + kiltearn_final
    if total_ratio > 0:
        ashfields_final = ashfields_final / total_ratio
        kiltearn_final = kiltearn_final / total_ratio
    else:
        # Fallback to list ratios if everything else is zero
        ashfields_final = ashfields_list_ratio
        kiltearn_final = kiltearn_list_ratio
    
    return {
        'ashfields_final_ratio': ashfields_final,
        'kiltearn_final_ratio': kiltearn_final
    }

def get_list_ratios():
    """Get fixed list size ratios"""
    ashfields_list_size = 28500
    kiltearn_list_size = 12500
    total_list_size = ashfields_list_size + kiltearn_list_size
    
    return {
        'ashfields': ashfields_list_size / total_list_size,
        'kiltearn': kiltearn_list_size / total_list_size,
        'ashfields_size': ashfields_list_size,
        'kiltearn_size': kiltearn_list_size
    }

def calculate_period_ratios(data_df, patients_df, period_column, period_value, weights):
    """Calculate all ratios for a specific period"""
    list_ratios = get_list_ratios()
    work_ratios = calculate_work_ratios(data_df, period_column, period_value)
    recruitment_ratios = calculate_recruitment_ratios(patients_df, period_column, period_value)
    combined_ratios = calculate_combined_ratios(list_ratios, work_ratios, recruitment_ratios, weights)
    
    return {
        'list': list_ratios,
        'work': work_ratios,
        'recruitment': recruitment_ratios,
        'combined': combined_ratios
    }

def build_profit_sharing_analysis(financial_df, patients_df, weights):
    """Build complete profit sharing analysis data"""
    if financial_df.empty:
        return []
    
    quarters = sorted([q for q in financial_df['QuarterYear'].unique() if pd.notna(q)]) if 'QuarterYear' in financial_df.columns else []
    financial_years = sorted([fy for fy in financial_df['FinancialYear'].unique() if pd.notna(fy)]) if 'FinancialYear' in financial_df.columns else []
    
    quarterly_ratios = []
    
    # Process quarters
    for quarter in quarters:
        quarter_data = financial_df[financial_df['QuarterYear'] == quarter]
        if len(quarter_data) == 0:
            continue
            
        ratios = calculate_period_ratios(financial_df, patients_df, 'QuarterYear', quarter, weights)
        
        # Calculate quarter income - handle NaN values safely
        quarter_total_income = quarter_data['Payment'].fillna(0).sum()
        ashfields_income = quarter_total_income * ratios['combined']['ashfields_final_ratio']
        kiltearn_income = quarter_total_income * ratios['combined']['kiltearn_final_ratio']
        
        # Extract financial year for sorting - improved parsing
        try:
            year_part = int(quarter.split('-Q')[0])
            quarter_num = int(quarter.split('-Q')[1])
            # Q1 and Q2 are in the previous financial year start
            fy_year = year_part if quarter_num >= 2 else year_part - 1
        except:
            fy_year = 2024  # fallback
        
        quarterly_ratios.append({
            'Period': quarter,
            'Financial Year': fy_year,
            'Type': 'Quarter',
            'Total Visits': ratios['work']['total_work'],
            'Ashfields Visits': ratios['work']['ashfields_work_count'],
            'Kiltearn Visits': ratios['work']['kiltearn_work_count'],
            'Ashfields Patients': ratios['recruitment']['ashfields_recruitment_count'],
            'Kiltearn Patients': ratios['recruitment']['kiltearn_recruitment_count'],
            'Ashfields Share': f"{ratios['combined']['ashfields_final_ratio']:.1%}",
            'Kiltearn Share': f"{ratios['combined']['kiltearn_final_ratio']:.1%}",
            'Total Income': f"£{quarter_total_income:,.2f}",
            'Ashfields Income': f"£{ashfields_income:,.2f}",
            'Kiltearn Income': f"£{kiltearn_income:,.2f}"
        })
    
    # Process financial years
    for fy in financial_years:
        fy_data = financial_df[financial_df['FinancialYear'] == fy]
        if len(fy_data) == 0:
            continue
            
        ratios = calculate_period_ratios(financial_df, patients_df, 'FinancialYear', fy, weights)
        
        # Calculate financial year income - handle NaN values safely
        fy_total_income = fy_data['Payment'].fillna(0).sum()
        ashfields_income = fy_total_income * ratios['combined']['ashfields_final_ratio']
        kiltearn_income = fy_total_income * ratios['combined']['kiltearn_final_ratio']
        
        try:
            fy_year = int(fy.split('-')[0])
        except:
            fy_year = 2024  # fallback
        
        quarterly_ratios.append({
            'Period': f"FY {fy}",
            'Financial Year': fy_year,
            'Type': 'Financial Year',
            'Total Visits': ratios['work']['total_work'],
            'Ashfields Visits': ratios['work']['ashfields_work_count'],
            'Kiltearn Visits': ratios['work']['kiltearn_work_count'],
            'Ashfields Patients': ratios['recruitment']['ashfields_recruitment_count'],
            'Kiltearn Patients': ratios['recruitment']['kiltearn_recruitment_count'],
            'Ashfields Share': f"{ratios['combined']['ashfields_final_ratio']:.1%}",
            'Kiltearn Share': f"{ratios['combined']['kiltearn_final_ratio']:.1%}",
            'Total Income': f"£{fy_total_income:,.2f}",
            'Ashfields Income': f"£{ashfields_income:,.2f}",
            'Kiltearn Income': f"£{kiltearn_income:,.2f}"
        })
    
    # Sort results
    quarterly_ratios.sort(key=lambda x: (x['Financial Year'], x['Type'] == 'Financial Year', x['Period']))
    
    return quarterly_ratios

def build_ratio_breakdown_data(financial_df, patients_df, period_config, weights):
    """Build ratio breakdown data for any time period"""
    period_column = period_config['column']
    period_name = period_config['name']
    
    # Handle empty financial_df case
    if financial_df.empty or period_column not in financial_df.columns:
        return []
    
    if period_column == 'MonthYear':
        periods = sorted([p for p in financial_df['MonthYear'].unique() if pd.notna(p)]) if not financial_df.empty else []
    elif period_column == 'QuarterYear':
        periods = sorted([p for p in financial_df['QuarterYear'].unique() if pd.notna(p)]) if 'QuarterYear' in financial_df.columns else []
    elif period_column == 'FinancialYear':
        periods = sorted([p for p in financial_df['FinancialYear'].unique() if pd.notna(p)]) if 'FinancialYear' in financial_df.columns else []
    else:
        return []
    
    list_ratios = get_list_ratios()
    ratio_data = []
    
    for period in periods:
        ratios = calculate_period_ratios(financial_df, patients_df, period_column, period, weights)
        
        period_display = str(period) if period_column == 'MonthYear' else period
        if period_column == 'FinancialYear':
            period_display = f"FY {period}"
        
        ratio_data.append({
            f'{period_name}': period_display,
            'Ashfields List %': f"{ratios['list']['ashfields']:.1%}",
            'Kiltearn List %': f"{ratios['list']['kiltearn']:.1%}",
            'Ashfields Work %': f"{ratios['work']['ashfields_work_ratio']:.1%}",
            'Kiltearn Work %': f"{ratios['work']['kiltearn_work_ratio']:.1%}",
            'Ashfields Recruit %': f"{ratios['recruitment']['ashfields_recruitment_ratio']:.1%}",
            'Kiltearn Recruit %': f"{ratios['recruitment']['kiltearn_recruitment_ratio']:.1%}",
            'Ashfields Final %': f"{ratios['combined']['ashfields_final_ratio']:.1%}",
            'Kiltearn Final %': f"{ratios['combined']['kiltearn_final_ratio']:.1%}",
            'Total Visits': ratios['work']['total_work'],
            'Total Recruits': ratios['recruitment']['total_recruitment']
        })
    
    return ratio_data

def calculate_income_realization_metrics(visits_df, trials_df, patients_df):
    """Calculate income realization and pipeline metrics"""
    # Get current financial year boundaries using centralized function
    fy_start, fy_end = get_current_financial_year_boundaries()

    # Filter visits for current financial year only
    fy_visits = visits_df[(visits_df['Date'] >= fy_start) & (visits_df['Date'] <= fy_end)].copy()
    
    # Separate completed vs scheduled work
    completed_visits = fy_visits[fy_visits.get('IsActual', False) == True].copy()
    all_visits = fy_visits.copy()  # Both completed and scheduled
    
    # Create trial payment lookup using centralized function
    trials_lookup = create_trial_payment_lookup(trials_df)
    
    # Add trial payment amounts to visits
    def get_trial_payment(row):
        study = str(row['Study'])
        visit_name = str(row.get('VisitName', ''))  # Use VisitName from visits_df
        return get_trial_payment_for_visit(trials_lookup, study, visit_name)
    
    # Calculate metrics safely
    try:
        completed_visits['TrialPayment'] = completed_visits.apply(get_trial_payment, axis=1)
        all_visits['TrialPayment'] = all_visits.apply(get_trial_payment, axis=1)
        
        # Remove tolerance periods (-, +) from calculations
        completed_visits = completed_visits[~completed_visits['Visit'].isin(['-', '+'])]
        all_visits = all_visits[~all_visits['Visit'].isin(['-', '+'])]
        
        # Calculate totals - handle NaN values safely
        completed_income = completed_visits['TrialPayment'].fillna(0).sum()
        total_scheduled_income = all_visits['TrialPayment'].fillna(0).sum()
        
        # Pipeline = remaining scheduled income
        remaining_visits = all_visits[all_visits.get('IsActual', False) == False]
        pipeline_income = remaining_visits['TrialPayment'].fillna(0).sum()
        
        # Realization rate - prevent division by zero
        realization_rate = (completed_income / total_scheduled_income * 100) if total_scheduled_income > 0 else 0
        
        return {
            'completed_income': completed_income,
            'total_scheduled_income': total_scheduled_income,
            'pipeline_income': pipeline_income,
            'realization_rate': realization_rate,
            'completed_visits_count': len(completed_visits),
            'total_scheduled_visits_count': len(all_visits),
            'pipeline_visits_count': len(remaining_visits)
        }
    except Exception as e:
        st.error(f"Error calculating realization metrics: {e}")
        return {
            'completed_income': 0,
            'total_scheduled_income': 0,
            'pipeline_income': 0,
            'realization_rate': 0,
            'completed_visits_count': 0,
            'total_scheduled_visits_count': 0,
            'pipeline_visits_count': 0
        }

def calculate_actual_and_predicted_income_by_site(visits_df, trials_df):
    """Calculate actual and predicted income by site for current financial year"""
    from datetime import date
    from helpers import get_current_financial_year_boundaries, create_trial_payment_lookup, get_trial_payment_for_visit
    
    try:
        # Get current date and financial year boundaries
        today = pd.to_datetime(date.today())
        fy_start, fy_end = get_current_financial_year_boundaries()
        
        # Filter visits for current financial year
        fy_visits = visits_df[
            (visits_df['Date'] >= fy_start) & 
            (visits_df['Date'] <= fy_end)
        ].copy()
        
        if fy_visits.empty:
            return pd.DataFrame()
        
        # Exclude tolerance markers
        fy_visits = fy_visits[~fy_visits['Visit'].isin(['-', '+'])].copy()
        
        if fy_visits.empty:
            return pd.DataFrame()
        
        # Use all visits as-is without filtering or modifying site assignments
        # This ensures consistency with Quarterly Profit Sharing calculations
        
        # Create trial payment lookup
        trials_lookup = create_trial_payment_lookup(trials_df)
        
        # Add trial payment amounts to visits
        def get_trial_payment(row):
            study = str(row['Study'])
            visit_name = str(row.get('VisitName', ''))
            return get_trial_payment_for_visit(trials_lookup, study, visit_name)
        
        fy_visits['TrialPayment'] = fy_visits.apply(get_trial_payment, axis=1)
        
        # Separate actual and predicted visits
        actual_visits = fy_visits[fy_visits.get('IsActual', False) == True].copy()
        predicted_visits = fy_visits[fy_visits.get('IsActual', False) == False].copy()
        
        # Calculate actual income by site - handle NaN values safely
        actual_income = actual_visits.groupby('SiteofVisit').agg({
            'TrialPayment': lambda x: x.fillna(0).sum(),
            'VisitName': 'count'
        }).rename(columns={
            'TrialPayment': 'Actual Income',
            'VisitName': 'Actual Visits'
        }).reset_index()
        
        # Calculate predicted income by site - handle NaN values safely
        predicted_income = predicted_visits.groupby('SiteofVisit').agg({
            'TrialPayment': lambda x: x.fillna(0).sum(),
            'VisitName': 'count'
        }).rename(columns={
            'TrialPayment': 'Predicted Income',
            'VisitName': 'Predicted Visits'
        }).reset_index()
        
        # Merge actual and predicted data
        site_income = pd.merge(
            actual_income, 
            predicted_income, 
            on='SiteofVisit', 
            how='outer'
        ).fillna(0)
        
        # Calculate totals
        site_income['Total Income'] = site_income['Actual Income'] + site_income['Predicted Income']
        site_income['Total Visits'] = site_income['Actual Visits'] + site_income['Predicted Visits']
        
        # Sort by total income descending
        site_income = site_income.sort_values('Total Income', ascending=False)
        
        # Add financial year info
        site_income['Financial Year'] = f"{fy_start.strftime('%d/%m/%Y')} to {fy_end.strftime('%d/%m/%Y')}"
        
        return site_income
        
    except Exception as e:
        st.error(f"Error calculating actual and predicted income: {e}")
        return pd.DataFrame()

def calculate_monthly_realization_breakdown(visits_df, trials_df):
    """Calculate month-by-month realization metrics"""
    try:
        # Get current financial year boundaries using centralized function
        fy_start, fy_end = get_current_financial_year_boundaries()
        
        # Filter for current financial year
        fy_visits = visits_df[(visits_df['Date'] >= fy_start) & (visits_df['Date'] <= fy_end)].copy()
        
        if fy_visits.empty:
            return []
        
        # Add month-year column
        fy_visits['MonthYear'] = fy_visits['Date'].dt.to_period('M')
        
        # Create trial payment lookup using centralized function
        trials_lookup = create_trial_payment_lookup(trials_df)
        
        def get_trial_payment(row):
            study = str(row['Study'])
            visit_name = str(row.get('VisitName', ''))
            return get_trial_payment_for_visit(trials_lookup, study, visit_name)
        
        fy_visits['TrialPayment'] = fy_visits.apply(get_trial_payment, axis=1)
        
        # Remove tolerance periods
        fy_visits = fy_visits[~fy_visits['Visit'].isin(['-', '+'])]
        
        # Calculate monthly breakdown
        monthly_data = []
        month_values = fy_visits['MonthYear'].dropna().unique()
        for month in sorted(month_values):
            month_visits = fy_visits[fy_visits['MonthYear'] == month]
            
            completed = month_visits[month_visits.get('IsActual', False) == True]
            completed_income = completed['TrialPayment'].sum()
            
            total_scheduled_income = month_visits['TrialPayment'].sum()
            
            realization_rate = (completed_income / total_scheduled_income * 100) if total_scheduled_income > 0 else 0
            
            monthly_data.append({
                'Month': str(month),
                'Completed_Income': completed_income,
                'Scheduled_Income': total_scheduled_income,
                'Realization_Rate': realization_rate,
                'Completed_Visits': len(completed),
                'Scheduled_Visits': len(month_visits)
            })
        
        return monthly_data
    except Exception as e:
        st.error(f"Error calculating monthly realization breakdown: {e}")
        return []

def calculate_study_pipeline_breakdown(visits_df, trials_df):
    """Calculate pipeline value by study"""
    from datetime import date
    
    try:
        today = pd.to_datetime(date.today())
        
        # Get remaining visits (future scheduled visits)
        remaining_visits = visits_df[
            (visits_df['Date'] >= today) & 
            (visits_df.get('IsActual', False) == False)
        ].copy()
        
        # Remove tolerance periods
        remaining_visits = remaining_visits[~remaining_visits['Visit'].isin(['-', '+'])]
        
        if remaining_visits.empty:
            return pd.DataFrame(columns=['Study', 'Pipeline_Value', 'Remaining_Visits'])
        
        # Create trial payment lookup using centralized function
        trials_lookup = create_trial_payment_lookup(trials_df)
        
        def get_trial_payment(row):
            study = str(row['Study'])
            visit_name = str(row.get('VisitName', ''))
            return get_trial_payment_for_visit(trials_lookup, study, visit_name)
        
        remaining_visits['TrialPayment'] = remaining_visits.apply(get_trial_payment, axis=1)
        
        # Group by study
        study_pipeline = remaining_visits.groupby('Study').agg({
            'TrialPayment': 'sum',
            'Visit': 'count'
        }).rename(columns={'TrialPayment': 'Pipeline_Value', 'Visit': 'Remaining_Visits'})
        
        # Sort by pipeline value descending
        study_pipeline = study_pipeline.sort_values('Pipeline_Value', ascending=False)
        
        return study_pipeline.reset_index()
    except Exception as e:
        st.error(f"Error calculating study pipeline breakdown: {e}")
        return pd.DataFrame(columns=['Study', 'Pipeline_Value', 'Remaining_Visits'])

def calculate_site_realization_breakdown(visits_df, trials_df):
    """Calculate realization rates by site"""
    try:
        # Create trial payment lookup using centralized function
        trials_lookup = create_trial_payment_lookup(trials_df)
        
        def get_trial_payment(row):
            study = str(row['Study'])
            visit_name = str(row.get('VisitName', ''))
            return get_trial_payment_for_visit(trials_lookup, study, visit_name)
        
        # Get current financial year boundaries using centralized function
        fy_start, fy_end = get_current_financial_year_boundaries()
        
        fy_visits = visits_df[(visits_df['Date'] >= fy_start) & (visits_df['Date'] <= fy_end)].copy()
        fy_visits = fy_visits[~fy_visits['Visit'].isin(['-', '+'])]  # Remove tolerance periods
        
        if fy_visits.empty:
            return []
        
        fy_visits['TrialPayment'] = fy_visits.apply(get_trial_payment, axis=1)
        
        # Calculate by site
        site_data = []
        for site in fy_visits['SiteofVisit'].unique():
            site_visits = fy_visits[fy_visits['SiteofVisit'] == site]
            
            completed = site_visits[site_visits.get('IsActual', False) == True]
            completed_income = completed['TrialPayment'].fillna(0).sum()
            
            total_scheduled_income = site_visits['TrialPayment'].fillna(0).sum()
            
            # Remaining pipeline for this site
            from datetime import date
            today = pd.to_datetime(date.today())
            remaining = site_visits[(site_visits['Date'] >= today) & (site_visits.get('IsActual', False) == False)]
            pipeline_income = remaining['TrialPayment'].fillna(0).sum()
            
            realization_rate = (completed_income / total_scheduled_income * 100) if total_scheduled_income > 0 else 0
            
            site_data.append({
                'Site': site,
                'Completed_Income': completed_income,
                'Total_Scheduled_Income': total_scheduled_income,
                'Pipeline_Income': pipeline_income,
                'Realization_Rate': realization_rate,
                'Completed_Visits': len(completed),
                'Total_Visits': len(site_visits),
                'Remaining_Visits': len(remaining)
            })
        
        return site_data
    except Exception as e:
        st.error(f"Error calculating site realization breakdown: {e}")
        return []
