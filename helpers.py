import pandas as pd
from dateutil.parser import parse
from datetime import datetime

def load_file(uploaded_file):
    """Load CSV or Excel file with proper handling"""
    if uploaded_file is None:
        return None
    if uploaded_file.name.endswith(".csv"):
        return pd.read_csv(uploaded_file)
    else:
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
    if isinstance(value, pd.Series):
        return value.apply(lambda x: safe_string_conversion(x, default))
    
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
            if isinstance(val, (pd.Timestamp, datetime)):
                return pd.Timestamp(val.date())
            
            val_str = str(val).strip()
            
            if isinstance(val, (int, float)):
                try:
                    excel_date = pd.to_datetime(val, origin='1899-12-30', unit='D')
                    return pd.Timestamp(excel_date.date())
                except:
                    pass
            
            uk_formats = ['%d/%m/%y', '%d/%m/%Y', '%d-%m-%y', '%d-%m-%Y', '%d.%m.%y', '%d.%m.%Y']
            
            for fmt in uk_formats:
                try:
                    parsed_date = datetime.strptime(val_str, fmt)
                    return pd.Times
