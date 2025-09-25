import pandas as pd
from datetime import date

def prepare_financial_data(visits_df):
    """Prepare visits data with financial period columns"""
    if visits_df.empty:
        return pd.DataFrame()
    
    # Create copy first
    financial_df = visits_df.copy()
    
    # Filter for relevant visits (exclude only tolerance periods '-' and '+')
    # Include: actual visits (with ✅, 🔴, ⚠), scheduled visits (plain visit names), but exclude tolerance periods
    mask = ~financial_df['Visit'].isin(['-', '+'])
    
    financial_df = financial_df[mask].copy()

    if financial_df.empty:
        # If filtering results in empty df, create empty df with required columns
        financial_df = pd.DataFrame()
        for col in ['MonthYear', 'Quarter', 'Year', 'QuarterYear', 'FinancialYear']:
            financial_df[col] = pd.Series(dtype='object')
        return financial_df
        
    # Add all time period columns
    financial_df['MonthYear'] = financial_df['Date'].dt.to_period('M')
    financial_df['Quarter'] = financial_df['Date'].dt.quarter
    financial_df['Year'] = financial_df['Date'].dt.year
    financial_df['QuarterYear'] = financial_df['Year'].astype(str) + '-Q' + financial_df['Quarter'].astype(str)
    financial_df['FinancialYear'] = financial_df['Date'].apply(
        lambda d: f"{d.year}-{d.year+1}" if d.month >= 4 else f"{d.year-1}-{d.year}"
    )
    
    return financial_df

def calculate_work_ratios(data_df, period_column, period_value):
    """Calculate work done ratios for a specific period"""
    period_data = data_df[data_df[period_column] == period_value]
    
    if len(period_data) == 0:
        return {
            'ashfields_work_ratio': 0,
            'kiltearn_work_ratio': 0,
            'total_work': 0
        }
    
    site_work = period_data.groupby('SiteofVisit').size()
    total_work = site_work.sum()
    
    return {
        'ashfields_work_ratio': site_work.get('Ashfields', 0) / total_work if total_work > 0 else 0,
        'kiltearn_work_ratio': site_work.get('Kiltearn', 0) / total_work if total_work > 0 else 0,
        'total_work': total_work,
        'ashfields_work_count': site_work.get('Ashfields', 0),
        'kiltearn_work_count': site_work.get('Kiltearn', 0)
    }

def calculate_recruitment_ratios(patients_df, period_column, period_value):
    """Calculate patient recruitment ratios for a specific period"""
    if period_column == 'MonthYear':
        period_patients = patients_df[patients_df['StartDate'].dt.to_period('M') == period_value]
    elif period_column == 'QuarterYear':
        period_patients = patients_df[patients_df['StartDate'].dt.to_period('Q').astype(str) == period_value.replace('-Q', 'Q')]
    elif period_column == 'FinancialYear':
        fy_start = pd.to_datetime(f"{period_value.split('-')[0]}-04-01")
        fy_end = pd.to_datetime(f"{period_value.split('-')[1]}-03-31")
        period_patients = patients_df[(patients_df['StartDate'] >= fy_start) & (patients_df['StartDate'] <= fy_end)]
    else:
        return {
            'ashfields_recruitment_ratio': 0,
            'kiltearn_recruitment_ratio': 0,
            'total_recruitment': 0
        }
    
    recruitment = period_patients.groupby('Site')['PatientID'].count()
    total_recruitment = recruitment.sum()
    
    return {
        'ashfields_recruitment_ratio': recruitment.get('Ashfields', 0) / total_recruitment if total_recruitment > 0 else 0,
        'kiltearn_recruitment_ratio': recruitment.get('Kiltearn', 0) / total_recruitment if total_recruitment > 0 else 0,
        'total_recruitment': total_recruitment,
        'ashfields_recruitment_count': recruitment.get('Ashfields', 0),
        'kiltearn_recruitment_count': recruitment.get('Kiltearn', 0)
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
    
    # Normalize
    total_ratio = ashfields_final + kiltearn_final
    if total_ratio > 0:
        ashfields_final = ashfields_final / total_ratio
        kiltearn_final = kiltearn_final / total_ratio
    
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
    quarters = sorted(financial_df['QuarterYear'].unique()) if 'QuarterYear' in financial_df.columns else []
    financial_years = sorted(financial_df['FinancialYear'].unique()) if 'FinancialYear' in financial_df.columns else []
    
    quarterly_ratios = []
    
    # Process quarters
    for quarter in quarters:
        quarter_data = financial_df[financial_df['QuarterYear'] == quarter]
        if len(quarter_data) == 0:
            continue
            
        ratios = calculate_period_ratios(financial_df, patients_df, 'QuarterYear', quarter, weights)
        
        # Calculate quarter income
        quarter_total_income = quarter_data['Payment'].sum()
        ashfields_income = quarter_total_income * ratios['combined']['ashfields_final_ratio']
        kiltearn_income = quarter_total_income * ratios['combined']['kiltearn_final_ratio']
        
        # Extract financial year for sorting
        year_part = int(quarter.split('-Q')[0])
        quarter_num = int(quarter.split('-Q')[1])
        fy_year = year_part if quarter_num >= 2 else year_part - 1
        
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
        
        # Calculate financial year income
        fy_total_income = fy_data['Payment'].sum()
        ashfields_income = fy_total_income * ratios['combined']['ashfields_final_ratio']
        kiltearn_income = fy_total_income * ratios['combined']['kiltearn_final_ratio']
        
        quarterly_ratios.append({
            'Period': f"FY {fy}",
            'Financial Year': int(fy.split('-')[0]),
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
    
    if period_column == 'MonthYear':
        periods = sorted(financial_df['MonthYear'].unique()) if not financial_df.empty else []
    elif period_column == 'QuarterYear':
        periods = sorted(financial_df['QuarterYear'].unique()) if 'QuarterYear' in financial_df.columns else []
    elif period_column == 'FinancialYear':
        periods = sorted(financial_df['FinancialYear'].unique()) if 'FinancialYear' in financial_df.columns else []
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
    
    # Get current financial year
    today = pd.to_datetime(date.today())
    if today.month >= 4:
        fy_end = pd.to_datetime(f"{today.year + 1}-03-31")
    else:
        fy_end = pd.to_datetime(f"{today.year}-03-31")
    
    # Filter visits for current financial year only
    fy_visits = visits_df[visits_df['Date'] <= fy_end].copy()
    
    # Separate completed vs scheduled work
    completed_visits = fy_visits[fy_visits.get('IsActual', False)].copy()
    all_visits = fy_visits.copy()  # Both completed and scheduled
    
    # Get payment amounts from trials file for each visit - now using VisitName
    trials_lookup = {}
    for _, trial in trials_df.iterrows():
        key = f"{trial['Study']}_{trial['VisitName']}"
        trials_lookup[key] = float(trial.get('Payment', 0) or trial.get('Income', 0) or 0)
    
    # Add trial payment amounts to visits
    def get_trial_payment(row):
        study = str(row['Study'])
        visit_name = str(row.get('VisitName', ''))  # Use VisitName from visits_df
        
        if visit_name and visit_name not in ['-', '+']:
            key = f"{study}_{visit_name}"
            return trials_lookup.get(key, 0)
        return 0
    
    # Calculate metrics
    completed_visits['TrialPayment'] = completed_visits.apply(get_trial_payment, axis=1)
    all_visits['TrialPayment'] = all_visits.apply(get_trial_payment, axis=1)
    
    # Remove tolerance periods (-, +) from calculations
    completed_visits = completed_visits[~completed_visits['Visit'].isin(['-', '+'])]
    all_visits = all_visits[~all_visits['Visit'].isin(['-', '+'])]
    
    # Calculate totals
    completed_income = completed_visits['TrialPayment'].sum()
    total_scheduled_income = all_visits['TrialPayment'].sum()
    
    # Pipeline = remaining scheduled income
    remaining_visits = all_visits[~all_visits.get('IsActual', False)]
    pipeline_income = remaining_visits['TrialPayment'].sum()
    
    # Realization rate
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

def calculate_monthly_realization_breakdown(visits_df, trials_df):
    """Calculate month-by-month realization metrics"""
    from datetime import date
    
    # Get current financial year
    today = pd.to_datetime(date.today())
    if today.month >= 4:
        fy_start = pd.to_datetime(f"{today.year}-04-01")
        fy_end = pd.to_datetime(f"{today.year + 1}-03-31")
    else:
        fy_start = pd.to_datetime(f"{today.year - 1}-04-01")
        fy_end = pd.to_datetime(f"{today.year}-03-31")
    
    # Filter for current financial year
    fy_visits = visits_df[(visits_df['Date'] >= fy_start) & (visits_df['Date'] <= fy_end)].copy()
    
    # Add month-year column
    fy_visits['MonthYear'] = fy_visits['Date'].dt.to_period('M')
    
    # Get trial payments lookup - now using VisitName
    trials_lookup = {}
    for _, trial in trials_df.iterrows():
        key = f"{trial['Study']}_{trial['VisitName']}"
        trials_lookup[key] = float(trial.get('Payment', 0) or trial.get('Income', 0) or 0)
    
    def get_trial_payment(row):
        study = str(row['Study'])
        visit_name = str(row.get('VisitName', ''))
        
        if visit_name and visit_name not in ['-', '+']:
            key = f"{study}_{visit_name}"
            return trials_lookup.get(key, 0)
        return 0
    
    fy_visits['TrialPayment'] = fy_visits.apply(get_trial_payment, axis=1)
    
    # Remove tolerance periods
    fy_visits = fy_visits[~fy_visits['Visit'].isin(['-', '+'])]
    
    # Calculate monthly breakdown
    monthly_data = []
    for month in fy_visits['MonthYear'].unique():
        month_visits = fy_visits[fy_visits['MonthYear'] == month]
        
        completed = month_visits[month_visits.get('IsActual', False)]
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

def calculate_study_pipeline_breakdown(visits_df, trials_df):
    """Calculate pipeline value by study"""
    from datetime import date
    
    today = pd.to_datetime(date.today())
    
    # Get remaining visits (future scheduled visits)
    remaining_visits = visits_df[
        (visits_df['Date'] >= today) & 
        (~visits_df.get('IsActual', False))
    ].copy()
    
    # Remove tolerance periods
    remaining_visits = remaining_visits[~remaining_visits['Visit'].isin(['-', '+'])]
    
    # Get trial payments - now using VisitName
    trials_lookup = {}
    for _, trial in trials_df.iterrows():
        key = f"{trial['Study']}_{trial['VisitName']}"
        trials_lookup[key] = float(trial.get('Payment', 0) or trial.get('Income', 0) or 0)
    
    def get_trial_payment(row):
        study = str(row['Study'])
        visit_name = str(row.get('VisitName', ''))
        
        if visit_name and visit_name not in ['-', '+']:
            key = f"{study}_{visit_name}"
            return trials_lookup.get(key, 0)
        return 0
    
    remaining_visits['TrialPayment'] = remaining_visits.apply(get_trial_payment, axis=1)
    
    # Group by study
    study_pipeline = remaining_visits.groupby('Study').agg({
        'TrialPayment': 'sum',
        'Visit': 'count'
    }).rename(columns={'TrialPayment': 'Pipeline_Value', 'Visit': 'Remaining_Visits'})
    
    # Sort by pipeline value descending
    study_pipeline = study_pipeline.sort_values('Pipeline_Value', ascending=False)
    
    return study_pipeline.reset_index()

def calculate_site_realization_breakdown(visits_df, trials_df):
    """Calculate realization rates by site"""
    from datetime import date
    
    # Get trial payments lookup - now using VisitName
    trials_lookup = {}
    for _, trial in trials_df.iterrows():
        key = f"{trial['Study']}_{trial['VisitName']}"
        trials_lookup[key] = float(trial.get('Payment', 0) or trial.get('Income', 0) or 0)
    
    def get_trial_payment(row):
        study = str(row['Study'])
        visit_name = str(row.get('VisitName', ''))
        
        if visit_name and visit_name not in ['-', '+']:
            key = f"{study}_{visit_name}"
            return trials_lookup.get(key, 0)
        return 0
    
    # Filter current financial year visits
    today = pd.to_datetime(date.today())
    if today.month >= 4:
        fy_start = pd.to_datetime(f"{today.year}-04-01")
        fy_end = pd.to_datetime(f"{today.year + 1}-03-31")
    else:
        fy_start = pd.to_datetime(f"{today.year - 1}-04-01")
        fy_end = pd.to_datetime(f"{today.year}-03-31")
    
    fy_visits = visits_df[(visits_df['Date'] >= fy_start) & (visits_df['Date'] <= fy_end)].copy()
    fy_visits = fy_visits[~fy_visits['Visit'].isin(['-', '+'])]  # Remove tolerance periods
    
    fy_visits['TrialPayment'] = fy_visits.apply(get_trial_payment, axis=1)
    
    # Calculate by site
    site_data = []
    for site in fy_visits['SiteofVisit'].unique():
        site_visits = fy_visits[fy_visits['SiteofVisit'] == site]
        
        completed = site_visits[site_visits.get('IsActual', False)]
        completed_income = completed['TrialPayment'].sum()
        
        total_scheduled_income = site_visits['TrialPayment'].sum()
        
        # Remaining pipeline for this site
        remaining = site_visits[(site_visits['Date'] >= today) & (~site_visits.get('IsActual', False))]
        pipeline_income = remaining['TrialPayment'].sum()
        
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
