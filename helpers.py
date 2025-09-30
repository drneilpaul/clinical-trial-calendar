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
                    return pd.Timestamp(parsed_date.date())
                except ValueError:
                    continue
            
            parsed_date = parse(val_str, dayfirst=True, yearfirst=False)
            return pd.Timestamp(parsed_date.date())
            
        except Exception as e:
            failed_rows.append(f"{val} (error: {str(e)})")
            return pd.NaT
    
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
    
    combined = ", ".join(events_list)
    
    if len(combined) <= max_length:
        return combined
    
    event_types = []
    for event in events_list:
        if "_" in event:
            event_type = event.split("_")[0]
            event_types.append(event_type)
        else:
            event_types.append(event[:8])
    
    return f"{len(events_list)} Events: {', '.join(set(event_types))}"

# CENTRALIZED FINANCIAL YEAR FUNCTIONS
def get_financial_year(date_obj):
    """Get financial year for a given date (April to March)"""
    if pd.isna(date_obj) or date_obj is None:
        return None
    if date_obj.month >= 4:
        return f"{date_obj.year}-{date_obj.year+1}"
    else:
        return f"{date_obj.year-1}-{date_obj.year}"

def get_financial_year_start_year(date_obj):
    """Get the starting year of the financial year for a given date"""
    if pd.isna(date_obj) or date_obj is None:
        return None
    if date_obj.month >= 4:
        return date_obj.year
    else:
        return date_obj.year - 1

def is_financial_year_end(date_obj):
    """Check if date is financial year end (31 March)"""
    if pd.isna(date_obj) or date_obj is None:
        return False
    return date_obj.month == 3 and date_obj.day == 31

def get_financial_year_for_series(date_series):
    """Apply financial year calculation to an entire pandas Series efficiently"""
    return date_series.apply(get_financial_year)

def safe_numeric_conversion(value, default=0):
    """Safely convert value to numeric with fallback"""
    try:
        if pd.isna(value) or value is None or value == '':
            return default
        return float(value)
    except (ValueError, TypeError):
        return default

def validate_financial_year_string(fy_string):
    """Validate that a financial year string is in the correct format"""
    if not isinstance(fy_string, str):
        return False
    
    try:
        parts = fy_string.split('-')
        if len(parts) != 2:
            return False
        
        start_year = int(parts[0])
        end_year = int(parts[1])
        
        return end_year == start_year + 1
    except ValueError:
        return False

def get_financial_year_boundaries(fy_string):
    """Get the start and end dates for a financial year string"""
    if not validate_financial_year_string(fy_string):
        raise ValueError(f"Invalid financial year format: {fy_string}")
    
    start_year = int(fy_string.split('-')[0])
    
    start_date = pd.Timestamp(f"{start_year}-04-01")
    end_date = pd.Timestamp(f"{start_year + 1}-03-31")
    
    return start_date, end_date

def get_current_financial_year_boundaries():
    """Get the start and end dates for the current financial year"""
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
    """Create a lookup dictionary for trial payments by study and visit name"""
    trials_lookup = {}
    
    if trials_df.empty:
        return trials_lookup
    
    for _, trial in trials_df.iterrows():
        study = str(trial['Study'])
        visit_name = str(trial['VisitName'])
        payment_key = f"{study}_{visit_name}"
        
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
    """Get payment amount for a specific study and visit from the lookup dictionary"""
    if not visit_name or visit_name in ['-', '+']:
        return 0
    
    key = f"{study}_{visit_name}"
    return trials_lookup.get(key, 0)

# =============================================================================
# ERROR COLLECTION SYSTEM (ADD TO END OF EXISTING helpers.py)
# =============================================================================

def init_error_system():
    """Initialize error tracking in session state"""
    if 'error_messages' not in st.session_state:
        st.session_state.error_messages = []
    if 'warning_messages' not in st.session_state:
        st.session_state.warning_messages = []
    if 'info_messages' not in st.session_state:
        st.session_state.info_messages = []

def add_error(message: str):
    """Add error message to collection"""
    if 'error_messages' not in st.session_state:
        init_error_system()
    st.session_state.error_messages.append({
        'message': message,
        'timestamp': datetime.now()
    })

def add_warning(message: str):
    """Add warning message to collection"""
    if 'warning_messages' not in st.session_state:
        init_error_system()
    st.session_state.warning_messages.append({
        'message': message,
        'timestamp': datetime.now()
    })

def add_info(message: str):
    """Add info message to collection"""
    if 'info_messages' not in st.session_state:
        init_error_system()
    st.session_state.info_messages.append({
        'message': message,
        'timestamp': datetime.now()
    })

def clear_messages():
    """Clear all error messages"""
    if 'error_messages' in st.session_state:
        st.session_state.error_messages = []
    if 'warning_messages' in st.session_state:
        st.session_state.warning_messages = []
    if 'info_messages' in st.session_state:
        st.session_state.info_messages = []

def has_critical_errors() -> bool:
    """Check if there are any critical error messages"""
    return len(st.session_state.get('error_messages', [])) > 0

def display_enhanced_messages_section():
    """Display all collected messages in organized sections"""
    try:
        # Error messages
        if st.session_state.get('error_messages'):
            st.error("❌ Errors encountered:")
            for msg in st.session_state.error_messages:
                timestamp = msg['timestamp'].strftime('%H:%M:%S')
                st.markdown(f"🔸 **{timestamp}**: {msg['message']}")
        
        # Warning messages  
        if st.session_state.get('warning_messages'):
            st.warning("⚠️ Warnings:")
            for msg in st.session_state.warning_messages:
                timestamp = msg['timestamp'].strftime('%H:%M:%S')
                st.markdown(f"🔸 **{timestamp}**: {msg['message']}")
        
        # Info messages
        if st.session_state.get('info_messages'):
            st.info("ℹ️ Processing Information:")
            for msg in st.session_state.info_messages:
                timestamp = msg['timestamp'].strftime('%H:%M:%S')
                st.markdown(f"🔸 **{timestamp}**: {msg['message']}")
        
        # Show clear button if there are any messages
        total_messages = (
            len(st.session_state.get('error_messages', [])) +
            len(st.session_state.get('warning_messages', [])) +
            len(st.session_state.get('info_messages', []))
        )
        
        if total_messages > 0:
            if st.button("🗑️ Clear Messages"):
                clear_messages()
                st.rerun()
    
    except Exception as e:
        st.error(f"Error displaying messages: {str(e)}")
