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

def get_financial_year(date_obj):
    """Get financial year for a given date (April to March)"""
    if pd.isna(date_obj):
        return None
    if date_obj.month >= 4:  # April onwards
        return f"{date_obj.year}-{date_obj.year+1}"
    else:  # Jan-Mar
        return f"{date_obj.year-1}-{date_obj.year}"

def safe_numeric_conversion(value, default=0):
    """Safely convert value to numeric with fallback"""
    try:
        if pd.isna(value) or value is None or value == '':
            return default
        return float(value)
    except (ValueError, TypeError):
        return default
