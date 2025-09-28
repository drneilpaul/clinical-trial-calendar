import pandas as pd
from dateutil.parser import parse
from datetime import datetime

def load_file(uploaded_file):
    """Load CSV or Excel file with proper handling"""
    if uploaded_file is None:
        return None
    if uploaded_file.name.endswith(".csv"):
        # For CSV files, read without automatic date parsing
        return pd.read_csv(uploaded_file)
    else:
        # For Excel files, also avoid automatic date parsing to maintain control
        return pd.read_excel(uploaded_file, engine="openpyxl")

def load_file_with_defaults(uploaded_file, default_columns=None):
    """Load file and ensure required columns exist with defaults"""
    df = load_file(uploaded_file)
    if df is None or df.empty:
        return df
    
    if default_columns:
        for col, default_value in default_columns.items():
            if col not in df.columns:
                df[col] = default_value
    
    return df

def normalize_columns(df):
    """Normalize column names by stripping whitespace"""
    if df is not None:
        df.columns = df.columns.str.strip()
    return df

def safe_string_conversion(value, default=""):
    """Safely convert value to string with fallback for NaN/None values"""
    # Handle Series - apply to each element
    if isinstance(value, pd.Series):
        return value.apply(lambda x: safe_string_conversion(x, default))
    
    # Handle individual values
    if pd.isna(value) or value is None:
        return default
    return str(value).strip()

def safe_string_conversion_series(series, default=""):
    """Safely convert an entire Series to string values"""
    return series.fillna(default).astype(str).str.strip()

def parse_dates_column(df, col, errors="raise"):
    """Parse dates in a column with UK format preference (DD/MM/YYYY)"""
    if col not in df.columns:
        return df, []
    
    failed_rows = []
    
    def try_parse_uk_date(val):
        if pd.isna(val) or val == '' or val is None:
            return pd.NaT
            
        try:
            # If it's already a datetime, handle timezone properly
            if isinstance(val, (pd.Timestamp, datetime)):
                # Convert to just the date part to avoid timezone issues
                return pd.Timestamp(val.date())
            
            # Convert to string first
            val_str = str(val).strip()
            
            # Handle Excel serial dates (numbers like 45564.0)
            if isinstance(val, (int, float)):
                try:
                    # This might be an Excel serial date - convert and use date part only
                    excel_date = pd.to_datetime(val, origin='1899-12-30', unit='D')
                    return pd.Timestamp(excel_date.date())  # Just the date part
                except:
                    pass
            
            # For string dates, be very explicit about UK format
            uk_formats = [
                '%d/%m/%y',    # 1/8/25
                '%d/%m/%Y',    # 1/8/2025  
                '%d-%m-%y',    # 1-8-25
                '%d-%m-%Y',    # 1-8-2025
                '%d.%m.%y',    # 1.8.25
                '%d.%m.%Y',    # 1.8.2025
            ]
            
            for fmt in uk_formats:
                try:
                    parsed_date = datetime.strptime(val_str, fmt)
                    return pd.Timestamp(parsed_date.date())  # Just the date part
                except ValueError:
                    continue
            
            # If standard formats fail, try dateutil with UK preference
            parsed_date = parse(val_str, dayfirst=True, yearfirst=False)
            return pd.Timestamp(parsed_date.date())  # Just the date part
            
        except Exception as e:
            failed_rows.append(f"{val} (error: {str(e)})")
            return pd.NaT
    
    # Apply the parsing function
    df[col] = df[col].apply(try_parse_uk_date)
    
    return df, failed_rows

def validate_required_columns(df, required_columns, file_name):
    """Validate that required columns exist in dataframe"""
    missing_columns = set(required_columns) - set(df.columns)
    if missing_columns:
        raise ValueError(f"{file_name} missing required columns: {', '.join(missing_columns)}")
    return True

def clean_numeric_column(df, column_name, default_value=0):
    """Clean and convert a column to numeric, handling NaN values"""
    if column_name in df.columns:
        df[column_name] = pd.to_numeric(df[column_name], errors='coerce').fillna(default_value)
    return df

def standardize_visit_columns(df):
    """Ensure VisitName column exists (no more VisitNo support)"""
    if 'VisitName' not in df.columns:
        raise ValueError("VisitName column is required. VisitNo is no longer supported.")
    
    # Ensure VisitName is string type - use the safe conversion for Series
    df['VisitName'] = safe_string_conversion_series(df['VisitName'])
    return df

def get_event_unique_key(patient_id, study, visit_name, visit_type):
    """Generate unique key for event identification"""
    return f"{patient_id}_{study}_{visit_name}_{visit_type}"

def format_site_events(events_list, max_length=50):
    """Format multiple events for site column with readability"""
    if not events_list:
        return ""
    
    if len(events_list) == 1:
        return events_list[0]
    
    # For multiple events, check total length
    combined = ", ".join(events_list)
    
    if len(combined) <= max_length:
        return combined
    
    # If too long, show abbreviated format
    event_types = []
    for event in events_list:
        if "_" in event:
            event_type = event.split("_")[0]
            event_types.append(event_type)
        else:
            event_types.append(event[:8])
    
    return f"{len(events_list)} Events: {', '.join(set(event_types))}"

# CENTRALIZED FINANCIAL YEAR FUNCTIONS - Single Source of Truth
def get_financial_year(date_obj):
    """
    Get financial year for a given date (April to March)
    Returns format: "2024-2025" for dates from April 2024 to March 2025
    
    Args:
        date_obj: pandas.Timestamp or datetime object
        
    Returns:
        str: Financial year in format "YYYY-YYYY" or None if date is NaT/None
        
    Examples:
        get_financial_year(pd.Timestamp('2024-03-31')) -> '2023-2024'  
        get_financial_year(pd.Timestamp('2024-04-01')) -> '2024-2025'
        get_financial_year(pd.Timestamp('2024-12-25')) -> '2024-2025'
    """
    if pd.isna(date_obj) or date_obj is None:
        return None
    if date_obj.month >= 4:  # April onwards
        return f"{date_obj.year}-{date_obj.year+1}"
    else:  # Jan-Mar
        return f"{date_obj.year-1}-{date_obj.year}"

def get_financial_year_start_year(date_obj):
    """
    Get the starting year of the financial year for a given date
    Used for grouping and sorting operations
    
    Args:
        date_obj: pandas.Timestamp or datetime object
        
    Returns:
        int: Starting year of the financial year or None if date is NaT/None
        
    Examples:
        get_financial_year_start_year(pd.Timestamp('2024-03-31')) -> 2023
        get_financial_year_start_year(pd.Timestamp('2024-04-01')) -> 2024
    """
    if pd.isna(date_obj) or date_obj is None:
        return None
    if date_obj.month >= 4:  # April onwards
        return date_obj.year
    else:  # Jan-Mar
        return date_obj.year - 1

def is_financial_year_end(date_obj):
    """
    Check if date is financial year end (31 March)
    
    Args:
        date_obj: pandas.Timestamp or datetime object
        
    Returns:
        bool: True if date is 31 March, False otherwise
    """
    if pd.isna(date_obj) or date_obj is None:
        return False
    return date_obj.month == 3 and date_obj.day == 31

def get_financial_year_for_series(date_series):
    """
    Apply financial year calculation to an entire pandas Series efficiently
    
    Args:
        date_series: pandas.Series of datetime objects
        
    Returns:
        pandas.Series: Series of financial year strings
    """
    return date_series.apply(get_financial_year)

def safe_numeric_conversion(value, default=0):
    """Safely convert value to numeric with fallback"""
    try:
        if pd.isna(value) or value is None or value == '':
            return default
        return float(value)
    except (ValueError, TypeError):
        return default

# Validation functions for financial year logic
def validate_financial_year_string(fy_string):
    """
    Validate that a financial year string is in the correct format
    
    Args:
        fy_string: str like "2024-2025"
        
    Returns:
        bool: True if valid format, False otherwise
    """
    if not isinstance(fy_string, str):
        return False
    
    try:
        parts = fy_string.split('-')
        if len(parts) != 2:
            return False
        
        start_year = int(parts[0])
        end_year = int(parts[1])
        
        # End year should be exactly start year + 1
        return end_year == start_year + 1
    except ValueError:
        return False

def get_financial_year_boundaries(fy_string):
    """
    Get the start and end dates for a financial year string
    
    Args:
        fy_string: str like "2024-2025"
        
    Returns:
        tuple: (start_date, end_date) as pandas.Timestamp objects
    """
    if not validate_financial_year_string(fy_string):
        raise ValueError(f"Invalid financial year format: {fy_string}")
    
    start_year = int(fy_string.split('-')[0])
    
    start_date = pd.Timestamp(f"{start_year}-04-01")
    end_date = pd.Timestamp(f"{start_year + 1}-03-31")
    
    return start_date, end_date

def get_current_financial_year_boundaries():
    """
    Get the start and end dates for the current financial year
    
    Returns:
        tuple: (start_date, end_date) as pandas.Timestamp objects
    """
    from datetime import date
    today = pd.to_datetime(date.today())
    
    if today.month >= 4:
        fy_start = pd.to_datetime(f"{today.year}-04-01")
        fy_end = pd.to_datetime(f"{today.year + 1}-03-31")
    else:
        fy_start = pd.to_datetime(f"{today.year - 1}-04-01")
        fy_end = pd.to_datetime(f"{today.year}-03-31")
    
    return fy_start, fy_end

def create_trial_payment_lookup(trials_df):
    """
    Create a lookup dictionary for trial payments by study and visit name
    
    Args:
        trials_df: DataFrame with trial information
        
    Returns:
        dict: Dictionary with keys like "Study_VisitName" and payment values
    """
    trials_lookup = {}
    
    if trials_df.empty:
        return trials_lookup
    
    for _, trial in trials_df.iterrows():
        study = str(trial['Study'])
        visit_name = str(trial['VisitName'])
        payment_key = f"{study}_{visit_name}"
        
        # Handle payment column with multiple possible names
        payment = 0.0
        for col in ['Payment', 'Income', 'Cost']:
            if col in trial.index and pd.notna(trial.get(col)):
                try:
                    payment = float(trial[col])
                    break
                except (ValueError, TypeError):
                    continue
        
        trials_lookup[payment_key] = payment
    
    return trials_lookup

def get_trial_payment_for_visit(trials_lookup, study, visit_name):
    """
    Get payment amount for a specific study and visit from the lookup dictionary
    
    Args:
        trials_lookup: Dictionary created by create_trial_payment_lookup
        study: Study name
        visit_name: Visit name
        
    Returns:
        float: Payment amount or 0 if not found
    """
    if not visit_name or visit_name in ['-', '+']:
        return 0
    
    key = f"{study}_{visit_name}"
    return trials_lookup.get(key, 0)
