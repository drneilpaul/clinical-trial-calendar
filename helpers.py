import pandas as pd
from dateutil.parser import parse
from datetime import datetime

def get_patient_origin_site(patient_row, default="Unknown Site"):
    """
    Get patient origin site with consistent column priority.
    
    Args:
        patient_row: DataFrame row or dict with patient data
        default: Default value if no valid site found
    
    Returns:
        str: Patient origin site name
    """
    # Standard priority order for site columns
    site_columns = ['PatientPractice', 'PatientSite', 'Site', 'Practice', 'HomeSite']
    
    for col in site_columns:
        if col in patient_row and pd.notna(patient_row[col]):
            site_value = str(patient_row[col]).strip()
            # Validate it's not an invalid placeholder
            if site_value and site_value not in ['nan', 'None', '', 'null', 'NULL', 'Unknown Site']:
                return site_value
    
    return default

def log_site_detection_summary(patients_df, function_name="Unknown"):
    """
    Log a summary of site detection results for verification.
    
    Args:
        patients_df: DataFrame with patient data
        function_name: Name of the calling function for context
    """
    from helpers import log_activity
    
    log_activity(f"SITE DETECTION SUMMARY - {function_name}", level='info')
    log_activity("=" * 40, level='info')
    
    # Get all detected sites using the helper function
    detected_sites = set()
    for _, patient_row in patients_df.iterrows():
        site = get_patient_origin_site(patient_row)
        detected_sites.add(site)
    
    log_activity(f"Total patients processed: {len(patients_df)}", level='info')
    log_activity(f"Unique sites detected: {sorted(detected_sites)}", level='info')
    
    # Count sites
    site_counts = {}
    for _, patient_row in patients_df.iterrows():
        site = get_patient_origin_site(patient_row)
        site_counts[site] = site_counts.get(site, 0) + 1
    
    for site, count in sorted(site_counts.items()):
        log_activity(f"  {site}: {count} patients", level='info')
    
    log_activity("=" * 40, level='info')

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
        # Handle both list and dict inputs
        if isinstance(default_columns, list):
            # If list, add columns with empty string defaults
            for col in default_columns:
                if col not in df.columns:
                    df[col] = ""
        elif isinstance(default_columns, dict):
            # If dict, use provided default values
            for col, default_value in default_columns.items():
                if col not in df.columns:
                    df[col] = default_value
    
    return df

def normalize_columns(df):
    """Normalize column names by stripping whitespace"""
    if df is not None:
        df.columns = [str(col).strip() for col in df.columns]
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

def get_visit_type_series(df, default='patient'):
    """
    Retrieve VisitType column from a DataFrame, tolerating different casing and missing values.
    
    Args:
        df: pandas DataFrame
        default: value to use when VisitType is missing/blank
    
    Returns:
        pandas Series with normalized lowercase visit types.
    """
    if df is None or len(df.columns) == 0:
        return pd.Series(dtype='object')
    
    column_name = None
    if 'VisitType' in df.columns:
        column_name = 'VisitType'
    elif 'visit_type' in df.columns:
        column_name = 'visit_type'
    elif 'visitType' in df.columns:
        column_name = 'visitType'
    
    if column_name is None:
        return pd.Series([default] * len(df), index=df.index, dtype='object')
    
    series = df[column_name].astype(str)
    series = series.replace({'': default, 'nan': default, 'None': default, 'none': default, 'null': default, 'NULL': default})
    series = series.fillna(default)
    series = series.str.strip().str.lower()
    series = series.mask(series == '', default)
    return series

def generate_financial_year_options(years_back: int = 4, include_future: bool = False, include_show_all: bool = True):
    """
    Build a list of financial year options for UI selectors.
    
    Args:
        years_back: How many completed financial years (prior to the current FY) to include.
        include_future: Whether to include the next financial year after the current one.
        include_show_all: Whether to prepend a "Show All" option with no start date.
    
    Returns:
        List of dicts with keys:
            - label: Friendly label (e.g., "FY 2024-25")
            - start: pd.Timestamp start date for the FY (or None for Show All)
            - end: pd.Timestamp end date (None for Show All)
    """
    current_start, current_end = get_current_financial_year_boundaries()
    options = []
    
    if include_show_all:
        options.append({"label": "Show All", "start": None, "end": None})
    
    # Current FY
    current_label = f"FY {current_start.year}-{current_end.year}"
    options.append({"label": current_label, "start": current_start, "end": current_end})
    
    # Previous FYs
    for i in range(1, years_back + 1):
        start_year = current_start.year - i
        start = pd.Timestamp(f"{start_year}-04-01")
        end = pd.Timestamp(f"{start_year + 1}-03-31")
        label = f"FY {start.year}-{end.year}"
        options.append({"label": label, "start": start, "end": end})
    
    if include_future:
        next_start = pd.Timestamp(f"{current_end.year}-04-01")
        next_end = pd.Timestamp(f"{current_end.year + 1}-03-31")
        next_label = f"FY {next_start.year}-{next_end.year}"
        options.insert(1 if include_show_all else 0, {"label": next_label + " (Next)", "start": next_start, "end": next_end})
    
    return options

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
# ERROR COLLECTION SYSTEM - SUPABASE PREPARATION
# =============================================================================
import streamlit as st
from datetime import datetime
from typing import List, Dict, Optional

def init_error_system():
    """Initialize error tracking in session state for Supabase preparation"""
    if 'error_log' not in st.session_state:
        st.session_state.error_log = {
            'errors': [],
            'warnings': [],
            'info': [],
            'session_id': datetime.now().strftime('%Y%m%d_%H%M%S')
        }

def log_error(message: str, error_type: str = 'error', context: Optional[Dict] = None):
    """
    Log error with context for future Supabase storage
    
    Args:
        message: Error message
        error_type: 'error', 'warning', or 'info'
        context: Optional dict with patient_id, study, file_name, etc.
    """
    if 'error_log' not in st.session_state:
        init_error_system()
    
    log_entry = {
        'timestamp': datetime.now(),
        'message': message,
        'type': error_type,
        'context': context or {}
    }
    
    st.session_state.error_log[f"{error_type}s"].append(log_entry)

def get_error_summary() -> Dict[str, int]:
    """Get summary of errors for display"""
    if 'error_log' not in st.session_state:
        return {'errors': 0, 'warnings': 0, 'info': 0}
    
    return {
        'errors': len(st.session_state.error_log.get('errors', [])),
        'warnings': len(st.session_state.error_log.get('warnings', [])),
        'info': len(st.session_state.error_log.get('info', []))
    }

def display_error_log_section():
    """Display collected errors in expandable section"""
    if 'error_log' not in st.session_state:
        return
    
    summary = get_error_summary()
    total = sum(summary.values())
    
    if total == 0:
        return
    
    with st.expander(f"📋 Processing Log ({total} messages)", expanded=False):
        # Errors
        if summary['errors'] > 0:
            st.error(f"**{summary['errors']} Errors:**")
            for entry in st.session_state.error_log['errors']:
                time_str = entry['timestamp'].strftime('%H:%M:%S')
                st.markdown(f"- **{time_str}**: {entry['message']}")
                if entry['context']:
                    st.caption(f"  Context: {entry['context']}")
        
        # Warnings
        if summary['warnings'] > 0:
            st.warning(f"**{summary['warnings']} Warnings:**")
            for entry in st.session_state.error_log['warnings']:
                time_str = entry['timestamp'].strftime('%H:%M:%S')
                st.markdown(f"- **{time_str}**: {entry['message']}")
        
        # Info
        if summary['info'] > 0:
            st.info(f"**{summary['info']} Info Messages:**")
            for entry in st.session_state.error_log['info']:
                time_str = entry['timestamp'].strftime('%H:%M:%S')
                st.markdown(f"- **{time_str}**: {entry['message']}")

def clear_error_log():
    """Clear error log"""
    if 'error_log' in st.session_state:
        st.session_state.error_log = {
            'errors': [],
            'warnings': [],
            'info': [],
            'session_id': datetime.now().strftime('%Y%m%d_%H%M%S')
        }

# Supabase preparation - data validation helpers
def prepare_for_database_insert(data: Dict) -> Dict:
    """
    Clean data for database insertion (Supabase preparation)
    Handles None, NaN, and type conversions
    """
    clean_data = {}
    for key, value in data.items():
        if pd.isna(value):
            clean_data[key] = None
        elif isinstance(value, (pd.Timestamp, datetime)):
            clean_data[key] = value.isoformat()
        elif isinstance(value, (int, float)):
            clean_data[key] = value
        else:
            clean_data[key] = str(value)
    return clean_data

def validate_database_schema(df: pd.DataFrame, required_columns: List[str]) -> tuple:
    """
    Validate DataFrame matches expected database schema
    
    Returns:
        (is_valid: bool, missing_columns: list, error_message: str)
    """
    missing = [col for col in required_columns if col not in df.columns]
    
    if missing:
        error_msg = f"Missing required columns for database: {', '.join(missing)}"
        return False, missing, error_msg
    
    return True, [], ""

# =============================================================================
# ACTIVITY LOG SYSTEM
# =============================================================================
from datetime import datetime

def init_activity_log():
    """Initialize activity log in session state"""
    if 'activity_log' not in st.session_state:
        st.session_state.activity_log = []

def log_activity(message: str, level: str = 'info', details: str = None):
    """
    Log activity with timestamp
    
    Args:
        message: Main activity message
        level: 'info', 'success', 'error', or 'warning'
        details: Optional additional details
    """
    if 'activity_log' not in st.session_state:
        init_activity_log()
    
    log_entry = {
        'timestamp': datetime.now(),
        'message': message,
        'level': level,
        'details': details
    }
    
    st.session_state.activity_log.append(log_entry)
    
    # Keep only last 100 entries to prevent memory issues
    if len(st.session_state.activity_log) > 100:
        st.session_state.activity_log = st.session_state.activity_log[-100:]

def display_activity_log_sidebar():
    """Display activity log in sidebar expander"""
    if 'activity_log' not in st.session_state or not st.session_state.activity_log:
        return
    
    log_count = len(st.session_state.activity_log)
    
    with st.sidebar.expander(f"📋 Activity Log ({log_count})", expanded=False):
        # Display in reverse chronological order (newest first)
        for entry in reversed(st.session_state.activity_log[-50:]):  # Show last 50
            timestamp_str = entry['timestamp'].strftime('%H:%M:%S')
            level = entry['level']
            message = entry['message']
            
            # Choose icon based on level
            if level == 'success':
                icon = '✅'
            elif level == 'error':
                icon = '❌'
            elif level == 'warning':
                icon = '⚠️'
            else:
                icon = 'ℹ️'
            
            st.text(f"{icon} {timestamp_str} - {message}")
            
            # Show details if present
            if entry.get('details'):
                st.caption(f"   {entry['details']}")


def trigger_data_refresh():
    """Mark that data should be refreshed and bump cache buster."""
    import streamlit as st

    st.session_state.data_refresh_needed = True
    st.session_state.calendar_cache_buster = st.session_state.get('calendar_cache_buster', 0) + 1
