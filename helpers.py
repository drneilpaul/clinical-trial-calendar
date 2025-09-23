import pandas as pd
from dateutil.parser import parse
from datetime import datetime

def load_file(uploaded_file):
    if uploaded_file is None:
        return None
    if uploaded_file.name.endswith(".csv"):
        # For CSV files, read without automatic date parsing
        return pd.read_csv(uploaded_file)
    else:
        # For Excel files, also avoid automatic date parsing to maintain control
        return pd.read_excel(uploaded_file, engine="openpyxl")

def normalize_columns(df):
    if df is not None:
        df.columns = df.columns.str.strip()
    return df

def parse_dates_column(df, col, errors="raise"):
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
