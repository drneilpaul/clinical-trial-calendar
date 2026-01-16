import pandas as pd
import streamlit as st
from datetime import date
from helpers import get_financial_year, get_financial_year_for_series, get_current_financial_year_boundaries, create_trial_payment_lookup, get_trial_payment_for_visit, log_activity

@st.cache_data(ttl=60, show_spinner=False)
def _prepare_financial_data_impl(visits_df):
    """Internal cached implementation of financial data preparation"""
    if visits_df.empty:
        return pd.DataFrame()
    
    # Create copy first (needed since we modify the DataFrame)
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
    
    # OPTIMIZED: No need for .copy() here since we're just filtering, not modifying the filtered result
    financial_df = financial_df[mask]
    
    # Debug: Log after filtering
    log_activity(f"After filtering shape: {financial_df.shape}", level='info')
    log_activity(f"Visit values: {financial_df['Visit'].unique() if not financial_df.empty else 'Empty'}", level='info')

    if financial_df.empty:
        # If filtering results in empty df, create empty df with required columns and proper structure
        empty_df = pd.DataFrame()
        # Add all the required columns that the rest of the code expects
        for col in ['Date', 'Visit', 'Study', 'Payment', 'SiteofVisit', 'PatientOrigin', 
                   'IsActual', 'IsScreenFail', 'IsWithdrawn', 'IsDied', 'IsOutOfProtocol', 'VisitDay', 'VisitName',
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
    # Handle NaN values: filter out invalid dates before creating QuarterYear to avoid "0-Q0" strings
    # Only create QuarterYear for rows with valid dates
    valid_date_mask = financial_df['Year'].notna() & financial_df['Quarter'].notna()
    financial_df['QuarterYear'] = None
    financial_df.loc[valid_date_mask, 'QuarterYear'] = (
        financial_df.loc[valid_date_mask, 'Year'].astype(int).astype(str) + '-Q' + 
        financial_df.loc[valid_date_mask, 'Quarter'].astype(int).astype(str)
    )
    
    # OPTIMIZED: Use vectorized financial year calculation (much faster than apply)
    financial_df['FinancialYear'] = get_financial_year_for_series(financial_df['Date'])
    
    # Debug: Log final result
    log_activity(f"Final financial_df shape: {financial_df.shape}", level='info')
    log_activity(f"Unique MonthYear values: {financial_df['MonthYear'].unique()}", level='info')
    log_activity(f"Payment sum: {financial_df['Payment'].sum()}", level='info')
    
    return financial_df

def prepare_financial_data(visits_df):
    """Prepare visits data with financial period columns (with caching)"""
    return _prepare_financial_data_impl(visits_df)

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
        # Create copies to avoid SettingWithCopyWarning when modifying
        if period_column == 'MonthYear':
            period_patients = patients_df[patients_df['StartDate'].dt.to_period('M').astype(str) == str(period_value)].copy()
        elif period_column == 'QuarterYear':
            # Convert both to strings for comparison
            # Handle NaN values before converting to int
            patients_quarter = (
                patients_df['StartDate'].dt.year.fillna(0).astype(int).astype(str) + '-Q' + 
                patients_df['StartDate'].dt.quarter.fillna(0).astype(int).astype(str)
            )
            period_patients = patients_df[patients_quarter == str(period_value)].copy()
        elif period_column == 'FinancialYear':
            # FIXED: Use centralized FY calculation from helpers
            patient_fy = get_financial_year_for_series(patients_df['StartDate'])
            period_patients = patients_df[patient_fy == str(period_value)].copy()
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
            lambda row: get_patient_origin_site(row, default="Unknown Site"), axis=1
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
    from datetime import date
    # Get current financial year boundaries using centralized function
    fy_start, fy_end = get_current_financial_year_boundaries()

    # OPTIMIZED: Filter visits for current financial year only (no copy needed for filtering)
    fy_visits = visits_df[(visits_df['Date'] >= fy_start) & (visits_df['Date'] <= fy_end)]
    
    # Get today's date for filtering proposed visits
    today = pd.to_datetime(date.today()).normalize()
    
    # Separate completed vs scheduled work (no copy needed - just filtering/reading)
    # CRITICAL: Exclude proposed visits from completed income (only count past actual visits)
    is_actual = fy_visits.get('IsActual', False) == True
    is_proposed = fy_visits.get('IsProposed', False) == True if 'IsProposed' in fy_visits.columns else pd.Series([False] * len(fy_visits))
    date_past = fy_visits['Date'] <= today
    completed_visits = fy_visits[is_actual & ~is_proposed & date_past]
    all_visits = fy_visits  # Both completed and scheduled - no copy needed since we're just reading
    
    # Use existing Payment column directly - already has correct values
    # (No need to recalculate from trial schedule as this causes double-counting)
    
    # Remove tolerance periods (-, +) from calculations
    completed_visits = completed_visits[~completed_visits['Visit'].isin(['-', '+'])]
    all_visits = all_visits[~all_visits['Visit'].isin(['-', '+'])]
    
    # Calculate totals - handle NaN values safely
    completed_income = completed_visits['Payment'].fillna(0).sum()
    total_scheduled_income = all_visits['Payment'].fillna(0).sum()
    
    # Pipeline = remaining scheduled income
    remaining_visits = all_visits[all_visits.get('IsActual', False) == False]
    pipeline_income = remaining_visits['Payment'].fillna(0).sum()
    
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

def calculate_actual_and_predicted_income_by_site(visits_df, trials_df):
    """Calculate actual and predicted income by site for current financial year"""
    from datetime import date
    from helpers import get_current_financial_year_boundaries, create_trial_payment_lookup, get_trial_payment_for_visit
    
    try:
        # Get current date and financial year boundaries
        today = pd.to_datetime(date.today())
        fy_start, fy_end = get_current_financial_year_boundaries()
        
        # OPTIMIZED: Filter visits for current financial year (no copy needed for filtering)
        fy_visits = visits_df[
            (visits_df['Date'] >= fy_start) & 
            (visits_df['Date'] <= fy_end)
        ]
        
        if fy_visits.empty:
            return pd.DataFrame()
        
        # Exclude tolerance markers (no copy needed - just filtering)
        fy_visits = fy_visits[~fy_visits['Visit'].isin(['-', '+'])]
        
        if fy_visits.empty:
            return pd.DataFrame()
        
        # Use all visits as-is without filtering or modifying site assignments
        # This ensures consistency with Quarterly Profit Sharing calculations
        
        # Use existing Payment column directly - already has correct values
        # (No need to recalculate from trial schedule as this causes double-counting)
        
        # OPTIMIZED: Separate actual and predicted visits (no copy needed - just filtering)
        # CRITICAL: Exclude proposed visits from actual income (only count past actual visits)
        is_actual = fy_visits.get('IsActual', False) == True
        is_proposed = fy_visits.get('IsProposed', False) == True if 'IsProposed' in fy_visits.columns else pd.Series([False] * len(fy_visits))
        date_past = fy_visits['Date'] <= today
        actual_visits = fy_visits[is_actual & ~is_proposed & date_past]
        predicted_visits = fy_visits[fy_visits.get('IsActual', False) == False]
        
        # Calculate actual income by site - handle NaN values safely
        actual_income = actual_visits.groupby('SiteofVisit').agg({
            'Payment': lambda x: x.fillna(0).sum(),
            'VisitName': 'count'
        }).rename(columns={
            'Payment': 'Actual Income',
            'VisitName': 'Actual Visits'
        }).reset_index()
        
        # Calculate predicted income by site - handle NaN values safely
        predicted_income = predicted_visits.groupby('SiteofVisit').agg({
            'Payment': lambda x: x.fillna(0).sum(),
            'VisitName': 'count'
        }).rename(columns={
            'Payment': 'Predicted Income',
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
        
        # OPTIMIZED: Filter for current financial year (use view first, copy only when modifying)
        fy_visits_view = visits_df[(visits_df['Date'] >= fy_start) & (visits_df['Date'] <= fy_end)]
        
        if fy_visits_view.empty:
            return []
        
        # OPTIMIZED: Only copy when we need to modify (add MonthYear column)
        fy_visits = fy_visits_view.copy()
        fy_visits['MonthYear'] = fy_visits['Date'].dt.to_period('M')
        
        # Use existing Payment column directly - already has correct values
        # (No need to recalculate from trial schedule as this causes double-counting)
        
        # Remove tolerance periods (no copy needed - just filtering)
        fy_visits = fy_visits[~fy_visits['Visit'].isin(['-', '+'])]
        
        # Calculate monthly breakdown
        monthly_data = []
        from datetime import date
        today = pd.to_datetime(date.today()).normalize()
        month_values = fy_visits['MonthYear'].dropna().unique()
        for month in sorted(month_values):
            month_visits = fy_visits[fy_visits['MonthYear'] == month]
            
            # CRITICAL: Exclude proposed visits from completed income (only count past actual visits)
            is_actual = month_visits.get('IsActual', False) == True
            is_proposed = month_visits.get('IsProposed', False) == True if 'IsProposed' in month_visits.columns else pd.Series([False] * len(month_visits))
            date_past = month_visits['Date'] <= today
            completed = month_visits[is_actual & ~is_proposed & date_past]
            completed_income = completed['Payment'].sum()
            
            total_scheduled_income = month_visits['Payment'].sum()
            
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
        
        # OPTIMIZED: Get remaining visits (use view first, copy only if needed)
        remaining_visits_view = visits_df[
            (visits_df['Date'] >= today) & 
            (visits_df.get('IsActual', False) == False)
        ]
        
        # Remove tolerance periods (filtering doesn't require copy)
        remaining_visits = remaining_visits_view[~remaining_visits_view['Visit'].isin(['-', '+'])]
        
        if remaining_visits.empty:
            return pd.DataFrame(columns=['Study', 'Pipeline_Value', 'Remaining_Visits'])
        
        # Use existing Payment column directly - already has correct values
        # (No need to recalculate from trial schedule as this causes double-counting)
        
        # Group by study
        study_pipeline = remaining_visits.groupby('Study').agg({
            'Payment': 'sum',
            'Visit': 'count'
        }).rename(columns={'Payment': 'Pipeline_Value', 'Visit': 'Remaining_Visits'})
        
        # Sort by pipeline value descending
        study_pipeline = study_pipeline.sort_values('Pipeline_Value', ascending=False)
        
        return study_pipeline.reset_index()
    except Exception as e:
        st.error(f"Error calculating study pipeline breakdown: {e}")
        return pd.DataFrame(columns=['Study', 'Pipeline_Value', 'Remaining_Visits'])

def calculate_site_realization_breakdown(visits_df, trials_df):
    """Calculate realization rates by site"""
    try:
        # Use existing Payment column directly - already has correct values
        # (No need to recalculate from trial schedule as this causes double-counting)
        
        # Get current financial year boundaries using centralized function
        fy_start, fy_end = get_current_financial_year_boundaries()
        
        # OPTIMIZED: Filter visits (no copy needed - just filtering/reading)
        fy_visits = visits_df[(visits_df['Date'] >= fy_start) & (visits_df['Date'] <= fy_end)]
        fy_visits = fy_visits[~fy_visits['Visit'].isin(['-', '+'])]  # Remove tolerance periods
        
        if fy_visits.empty:
            return []
        
        # Calculate by site
        site_data = []
        from datetime import date
        today = pd.to_datetime(date.today()).normalize()
        
        for site in fy_visits['SiteofVisit'].unique():
            site_visits = fy_visits[fy_visits['SiteofVisit'] == site]
            
            # CRITICAL: Exclude proposed visits from completed income (only count past actual visits)
            is_actual = site_visits.get('IsActual', False) == True
            is_proposed = site_visits.get('IsProposed', False) == True if 'IsProposed' in site_visits.columns else pd.Series([False] * len(site_visits))
            date_past = site_visits['Date'] <= today
            completed = site_visits[is_actual & ~is_proposed & date_past]
            completed_income = completed['Payment'].fillna(0).sum()
            
            total_scheduled_income = site_visits['Payment'].fillna(0).sum()
            
            # Remaining pipeline for this site
            remaining = site_visits[(site_visits['Date'] >= today) & (site_visits.get('IsActual', False) == False)]
            pipeline_income = remaining['Payment'].fillna(0).sum()
            
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

def calculate_study_realization_by_study(visits_df, period: str = 'current_fy'):
    """Build per-study realization (completed vs scheduled vs pipeline) for a period.

    Args:
        visits_df: Visits with columns including Date, Study, Payment, Visit, IsActual
        period: 'current_fy' or 'all_time'

    Returns:
        pd.DataFrame with columns:
            Study, Completed Income, Completed Visits, Scheduled Income,
            Scheduled Visits, Pipeline Income, Remaining Visits, Realization Rate
    """
    try:
        if visits_df is None or visits_df.empty:
            return pd.DataFrame(columns=[
                'Study', 'Completed Income', 'Completed Visits',
                'Scheduled Income', 'Scheduled Visits',
                'Pipeline Income', 'Remaining Visits', 'Realization Rate'
            ])

        # OPTIMIZED: Only copy if we need to modify, otherwise use views
        df = visits_df.copy()  # Keep copy here since we modify Payment column below

        # Filter by period (no copy needed - just filtering)
        if period == 'current_fy':
            from helpers import get_current_financial_year_boundaries
            fy_start, fy_end = get_current_financial_year_boundaries()
            df = df[(df['Date'] >= fy_start) & (df['Date'] <= fy_end)]

        if df.empty:
            return pd.DataFrame(columns=[
                'Study', 'Completed Income', 'Completed Visits',
                'Scheduled Income', 'Scheduled Visits',
                'Pipeline Income', 'Remaining Visits', 'Realization Rate'
            ])

        # Exclude tolerance markers (no copy needed - just filtering)
        df = df[~df['Visit'].isin(['-', '+'])]

        if df.empty:
            return pd.DataFrame(columns=[
                'Study', 'Completed Income', 'Completed Visits',
                'Scheduled Income', 'Scheduled Visits',
                'Pipeline Income', 'Remaining Visits', 'Realization Rate'
            ])

        # Ensure numeric payments
        df['Payment'] = pd.to_numeric(df.get('Payment', 0), errors='coerce').fillna(0.0)

        # Completed vs scheduled flags
        # CRITICAL: Exclude proposed visits from completed income (only count past actual visits)
        from datetime import date
        today = pd.to_datetime(date.today()).normalize()
        is_actual = df.get('IsActual', False) == True
        is_proposed = df.get('IsProposed', False) == True if 'IsProposed' in df.columns else pd.Series([False] * len(df))
        date_past = df['Date'] <= today
        is_completed = is_actual & ~is_proposed & date_past
        is_pipeline = df.get('IsActual', False) == False

        # Group aggregations
        completed = df[is_completed].groupby('Study').agg(
            Completed_Income=('Payment', 'sum'),
            Completed_Visits=('Visit', 'count')
        )
        scheduled = df.groupby('Study').agg(
            Scheduled_Income=('Payment', 'sum'),
            Scheduled_Visits=('Visit', 'count')
        )
        pipeline = df[is_pipeline].groupby('Study').agg(
            Pipeline_Income=('Payment', 'sum'),
            Remaining_Visits=('Visit', 'count')
        )

        # Merge
        result = scheduled.join(completed, how='left').join(pipeline, how='left').fillna(0)

        # Realization rate
        result['Realization Rate'] = result.apply(
            lambda r: (r['Completed_Income'] / r['Scheduled_Income'] * 100) if r['Scheduled_Income'] > 0 else 0,
            axis=1
        )

        # Reorder and rename columns for display
        result = result.reset_index()
        result = result.rename(columns={
            'Study': 'Study',
            'Completed_Income': 'Completed Income',
            'Completed_Visits': 'Completed Visits',
            'Scheduled_Income': 'Scheduled Income',
            'Scheduled_Visits': 'Scheduled Visits',
            'Pipeline_Income': 'Pipeline Income',
            'Remaining_Visits': 'Remaining Visits'
        })

        # Sort by scheduled income desc
        result = result.sort_values('Scheduled Income', ascending=False)

        return result
    except Exception as e:
        st.error(f"Error calculating by-study realization: {e}")
        return pd.DataFrame(columns=[
            'Study', 'Completed Income', 'Completed Visits',
            'Scheduled Income', 'Scheduled Visits',
            'Pipeline Income', 'Remaining Visits', 'Realization Rate'
        ])
