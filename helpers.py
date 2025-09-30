import pandas as pd
import streamlit as st
from datetime import datetime, date
import logging
from typing import Optional, Union, List, Any
import numpy as np

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Custom exceptions for structured error handling
class AppError(Exception):
    """Base exception for application-level errors"""
    pass

class DataValidationError(AppError):
    """Errors related to data validation"""
    pass

class FileProcessingError(AppError):
    """Errors related to file processing"""
    pass

# =============================================================================
# ERROR MESSAGE MANAGEMENT
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
    logger.error(message)

def add_warning(message: str):
    """Add warning message to collection"""
    if 'warning_messages' not in st.session_state:
        init_error_system()
    st.session_state.warning_messages.append({
        'message': message,
        'timestamp': datetime.now()
    })
    logger.warning(message)

def add_info(message: str):
    """Add info message to collection"""
    if 'info_messages' not in st.session_state:
        init_error_system()
    st.session_state.info_messages.append({
        'message': message,
        'timestamp': datetime.now()
    })
    logger.info(message)

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

def display_messages_section():
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
        logger.error(f"Message display error: {e}")

# =============================================================================
# FILE PROCESSING UTILITIES
# =============================================================================

def safe_string_conversion(value: Any) -> str:
    """
    Safely convert any value to string with comprehensive error handling
    
    Args:
        value: Any value to convert to string
        
    Returns:
        String representation of the value
    """
    if value is None or pd.isna(value):
        return ""
    
    if isinstance(value, str):
        return str(value).strip()
    
    if isinstance(value, (int, float)):
        if pd.isna(value) or np.isinf(value):
            return ""
        # Convert float to int if it's a whole number
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value)
    
    if isinstance(value, (datetime, date)):
        return value.strftime('%Y-%m-%d')
    
    # Handle other types
    try:
        return str(value).strip()
    except Exception as e:
        logger.warning(f"String conversion failed for value {value}: {e}")
        return ""

def parse_dates_column(df: pd.DataFrame, column_name: str, 
                      date_formats: List[str] = None) -> pd.DataFrame:
    """
    Parse date column with multiple format attempts and error handling
    
    Args:
        df: DataFrame containing the date column
        column_name: Name of the column to parse
        date_formats: List of date formats to try
        
    Returns:
        DataFrame with parsed date column
    """
    if date_formats is None:
        # UK-first date formats
        date_formats = [
            '%d/%m/%Y',     # UK format
            '%d-%m-%Y',     # UK format with dashes
            '%Y-%m-%d',     # ISO format
            '%m/%d/%Y',     # US format
            '%Y/%m/%d'      # Alternative ISO
        ]
    
    if column_name not in df.columns:
        add_warning(f"Date column '{column_name}' not found")
        return df
    
    original_df = df.copy()
    parsing_success = False
    
    # Try each date format
    for date_format in date_formats:
        try:
            df[column_name] = pd.to_datetime(df[column_name], format=date_format, errors='coerce')
            valid_dates = df[column_name].notna().sum()
            total_dates = len(df)
            
            if valid_dates > 0:
                success_rate = valid_dates / total_dates
                add_info(f"Parsed {valid_dates}/{total_dates} dates using format {date_format} ({success_rate:.1%} success)")
                parsing_success = True
                break
                
        except Exception as e:
            logger.debug(f"Date format {date_format} failed for column {column_name}: {e}")
            continue
    
    # If no format worked, try pandas automatic parsing
    if not parsing_success:
        try:
            df[column_name] = pd.to_datetime(df[column_name], errors='coerce', dayfirst=True)
            valid_dates = df[column_name].notna().sum()
            total_dates = len(df)
            
            if valid_dates > 0:
                add_info(f"Used automatic date parsing: {valid_dates}/{total_dates} dates parsed ({valid_dates/total_dates:.1%} success)")
                parsing_success = True
        except Exception as e:
            add_error(f"All date parsing attempts failed for column '{column_name}': {str(e)}")
            return original_df
    
    # Check for parsing failures
    failed_dates = df[column_name].isna().sum()
    if failed_dates > 0:
        add_warning(f"{failed_dates} dates could not be parsed in column '{column_name}'")
        
        # Show examples of failed dates
        failed_examples = original_df[df[column_name].isna()][column_name].unique()[:5]
        if len(failed_examples) > 0:
            add_info(f"Examples of unparseable dates: {', '.join(map(str, failed_examples))}")
    
    return df

def load_file_safe(uploaded_file) -> Optional[pd.DataFrame]:
    """
    Safely load uploaded file with comprehensive error handling
    
    Args:
        uploaded_file: Streamlit uploaded file object
        
    Returns:
        DataFrame if successful, None if failed
    """
    if uploaded_file is None:
        return None
    
    try:
        # Determine file type
        file_extension = uploaded_file.name.lower().split('.')[-1]
        
        if file_extension == 'csv':
            # Try different encodings and separators
            encodings = ['utf-8', 'latin-1', 'cp1252']
            separators = [',', ';', '\t']
            
            for encoding in encodings:
                for separator in separators:
                    try:
                        uploaded_file.seek(0)  # Reset file position
                        df = pd.read_csv(uploaded_file, encoding=encoding, sep=separator)
                        
                        # Check if we got reasonable results
                        if len(df.columns) > 1 and len(df) > 0:
                            add_info(f"Successfully loaded CSV with encoding={encoding}, separator='{separator}'")
                            return df
                            
                    except Exception as e:
                        logger.debug(f"CSV load failed with encoding={encoding}, sep='{separator}': {e}")
                        continue
            
            # If all attempts failed
            add_error("Failed to load CSV file with any encoding/separator combination")
            return None
            
        elif file_extension in ['xlsx', 'xls']:
            try:
                # Try loading Excel file
                df = pd.read_excel(uploaded_file, engine='openpyxl' if file_extension == 'xlsx' else 'xlrd')
                add_info(f"Successfully loaded Excel file ({len(df)} rows, {len(df.columns)} columns)")
                return df
                
            except Exception as e:
                add_error(f"Failed to load Excel file: {str(e)}")
                return None
        
        else:
            add_error(f"Unsupported file type: {file_extension}")
            return None
            
    except Exception as e:
        add_error(f"Unexpected error loading file: {str(e)}")
        logger.error(f"File loading error: {e}")
        return None

# =============================================================================
# DATA VALIDATION UTILITIES  
# =============================================================================

def validate_required_columns(df: pd.DataFrame, required_columns: List[str], 
                            file_name: str = "file") -> bool:
    """
    Validate that DataFrame contains all required columns
    
    Args:
        df: DataFrame to validate
        required_columns: List of required column names
        file_name: Name of file for error messages
        
    Returns:
        True if all required columns present, False otherwise
    """
    if df is None or df.empty:
        add_error(f"{file_name} is empty or None")
        return False
    
    missing_columns = [col for col in required_columns if col not in df.columns]
    
    if missing_columns:
        add_error(f"{file_name} missing required columns: {', '.join(missing_columns)}")
        add_info(f"{file_name} available columns: {', '.join(df.columns.tolist())}")
        return False
    
    return True

def validate_data_types(df: pd.DataFrame, column_types: dict, 
                       file_name: str = "file") -> bool:
    """
    Validate data types of DataFrame columns
    
    Args:
        df: DataFrame to validate
        column_types: Dictionary of {column_name: expected_type}
        file_name: Name of file for error messages
        
    Returns:
        True if all types are valid, False otherwise
    """
    validation_passed = True
    
    for column, expected_type in column_types.items():
        if column not in df.columns:
            continue
            
        try:
            if expected_type == 'datetime':
                # Try to convert to datetime
                pd.to_datetime(df[column], errors='raise')
            elif expected_type == 'numeric':
                # Try to convert to numeric
                pd.to_numeric(df[column], errors='raise')
            elif expected_type == 'string':
                # Check if can be converted to string
                df[column].astype(str)
                
        except Exception as e:
            add_warning(f"{file_name} column '{column}' may have type issues: {str(e)}")
            validation_passed = False
    
    return validation_passed

def calculate_financial_year(date_value: Union[datetime, date, str]) -> Optional[str]:
    """
    Calculate financial year (April to March) for a given date with error handling
    
    Args:
        date_value: Date to calculate financial year for
        
    Returns:
        Financial year as string (e.g., "2024-25") or None if conversion fails
    """
    try:
        # Convert to datetime if needed
        if isinstance(date_value, str):
            date_obj = pd.to_datetime(date_value, errors='coerce')
            if pd.isna(date_obj):
                return None
        elif isinstance(date_value, date):
            date_obj = datetime.combine(date_value, datetime.min.time())
        elif isinstance(date_value, datetime):
            date_obj = date_value
        else:
            return None
        
        # Calculate financial year (April to March)
        if date_obj.month >= 4:  # April onwards
            fy_start = date_obj.year
            fy_end = date_obj.year + 1
        else:  # January to March
            fy_start = date_obj.year - 1
            fy_end = date_obj.year
        
        return f"{fy_start}-{str(fy_end)[-2:]}"
        
    except Exception as e:
        logger.warning(f"Financial year calculation failed for {date_value}: {e}")
        return None

def clean_patient_id(patient_id: Any) -> str:
    """
    Clean and standardize patient ID with error handling
    
    Args:
        patient_id: Patient ID value to clean
        
    Returns:
        Cleaned patient ID as string
    """
    try:
        if patient_id is None or pd.isna(patient_id):
            return ""
        
        # Convert to string and clean
        clean_id = safe_string_conversion(patient_id)
        
        # Remove common prefixes/suffixes and whitespace
        clean_id = clean_id.strip().upper()
        
        # Remove common separators and standardize
        clean_id = clean_id.replace('-', '').replace('_', '').replace(' ', '')
        
        return clean_id
        
    except Exception as e:
        logger.warning(f"Patient ID cleaning failed for {patient_id}: {e}")
        return safe_string_conversion(patient_id)

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def format_currency(amount: Union[int, float]) -> str:
    """Format currency with error handling"""
    try:
        if pd.isna(amount) or amount is None:
            return "£0.00"
        return f"£{float(amount):,.2f}"
    except (ValueError, TypeError):
        return "£0.00"

def safe_division(numerator: Union[int, float], denominator: Union[int, float]) -> float:
    """Perform safe division with error handling"""
    try:
        if denominator == 0 or pd.isna(denominator) or pd.isna(numerator):
            return 0.0
        return float(numerator) / float(denominator)
    except (ValueError, TypeError, ZeroDivisionError):
        return 0.0

def get_unique_studies(df: pd.DataFrame, study_column: str = 'Study') -> List[str]:
    """Get list of unique studies with error handling"""
    try:
        if df is None or df.empty or study_column not in df.columns:
            return []
        
        unique_studies = df[study_column].dropna().unique().tolist()
        return [str(study).strip() for study in unique_studies if str(study).strip()]
        
    except Exception as e:
        logger.warning(f"Error getting unique studies: {e}")
        return []
