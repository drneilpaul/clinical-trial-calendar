"""
File validation and data cleaning utilities for clinical trial calendar
Handles validation and cleaning of uploaded CSV/Excel files
"""

import pandas as pd
import re
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from helpers import log_activity
from payment_handler import normalize_payment_column, clean_payment_values, validate_payment_data

class FileValidationError(Exception):
    """Custom exception for file validation errors"""
    pass

def clean_currency_value(value) -> float:
    """Clean currency values by removing symbols, spaces, and commas"""
    if pd.isna(value) or value == '':
        return 0.0
    
    # Convert to string and clean
    value_str = str(value).strip()
    
    # Remove currency symbols (£, $, €)
    value_str = re.sub(r'[£$€]', '', value_str)
    
    # Remove commas
    value_str = value_str.replace(',', '')
    
    # Remove extra spaces
    value_str = value_str.strip()
    
    # Handle empty strings
    if value_str == '' or value_str == '0':
        return 0.0
    
    # Convert to float
    try:
        return float(value_str)
    except ValueError:
        log_activity(f"Could not convert currency value '{value}' to float, using 0", level='warning')
        return 0.0

def clean_date_value(value, expected_format='%d/%m/%Y') -> Optional[str]:
    """Clean and standardize date values"""
    if pd.isna(value) or value == '':
        return None
    
    # If already a datetime object, format it
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.strftime(expected_format)
    
    # Convert to string and clean
    value_str = str(value).strip()
    
    # Handle common date formats - prioritize UK format (D/M/Y)
    date_formats = [
        '%d/%m/%Y',      # 25/12/2024 (UK format - highest priority)
        '%d-%m-%Y',      # 25-12-2024 (UK format with dashes)
        '%d.%m.%Y',      # 25.12.2024 (UK format with dots)
        '%Y-%m-%d',      # 2024-12-25 (ISO format)
        '%m/%d/%Y',      # 12/25/2024 (US format - lowest priority)
    ]
    
    for fmt in date_formats:
        try:
            parsed_date = datetime.strptime(value_str, fmt)
            return parsed_date.strftime(expected_format)
        except ValueError:
            continue
    
    # If no format matches, try pandas parsing with UK format preference
    try:
        parsed_date = pd.to_datetime(value_str, dayfirst=True)
        return parsed_date.strftime(expected_format)
    except:
        log_activity(f"Could not parse date '{value}', using None", level='warning')
        return None

def clean_numeric_value(value, default=0) -> float:
    """Clean numeric values"""
    if pd.isna(value) or value == '':
        return default
    
    # Convert to string and clean
    value_str = str(value).strip()
    
    # Remove any non-numeric characters except decimal point and minus
    value_str = re.sub(r'[^\d.-]', '', value_str)
    
    if value_str == '' or value_str == '.':
        return default
    
    try:
        return float(value_str)
    except ValueError:
        log_activity(f"Could not convert numeric value '{value}' to float, using {default}", level='warning')
        return default

def validate_patients_file(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
    """Validate and clean patients file"""
    errors = []
    warnings = []
    
    # Required columns
    required_columns = ['PatientID', 'Study', 'StartDate']
    missing_columns = [col for col in required_columns if col not in df.columns]
    
    if missing_columns:
        errors.append(f"Missing required columns: {missing_columns}")
        return df, errors
    
    # Clean the dataframe
    df_clean = df.copy()
    
    # Clean PatientID - ensure it's a string
    if 'PatientID' in df_clean.columns:
        df_clean['PatientID'] = df_clean['PatientID'].astype(str)
    
    # Clean Study - ensure it's a string
    if 'Study' in df_clean.columns:
        df_clean['Study'] = df_clean['Study'].astype(str)
    
    # Clean StartDate
    if 'StartDate' in df_clean.columns:
        df_clean['StartDate'] = df_clean['StartDate'].apply(lambda x: clean_date_value(x))
        # Check for invalid dates
        invalid_dates = df_clean['StartDate'].isna().sum()
        if invalid_dates > 0:
            warnings.append(f"{invalid_dates} patients have invalid start dates")
    
    # Clean optional columns
    optional_columns = {
        'Site': str,
        'PatientPractice': str,
        # OriginSite column removed - using PatientPractice only
    }
    
    for col, dtype in optional_columns.items():
        if col in df_clean.columns:
            df_clean[col] = df_clean[col].fillna('').astype(str)
        else:
            df_clean[col] = ''
            warnings.append(f"Missing optional column '{col}', filled with empty strings")
    
    # Validate data quality
    if len(df_clean) == 0:
        errors.append("No valid patient records found")
    
    # Check for duplicate PatientIDs
    duplicates = df_clean['PatientID'].duplicated().sum()
    if duplicates > 0:
        warnings.append(f"{duplicates} duplicate PatientIDs found")
    
    log_activity(f"Validated patients file: {len(df_clean)} records, {len(errors)} errors, {len(warnings)} warnings", level='info')
    
    return df_clean, errors + warnings

def validate_trials_file(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
    """Validate and clean trials file"""
    errors = []
    warnings = []
    
    # Required columns
    required_columns = ['Study', 'Day', 'VisitName']
    missing_columns = [col for col in required_columns if col not in df.columns]
    
    if missing_columns:
        errors.append(f"Missing required columns: {missing_columns}")
        return df, errors
    
    # Clean the dataframe
    df_clean = df.copy()
    
    # Use centralized payment column handling
    df_clean = normalize_payment_column(df_clean, 'Payment')
    
    # Validate payment data
    payment_validation = validate_payment_data(df_clean, 'Payment')
    if not payment_validation['valid']:
        for issue in payment_validation['issues']:
            warnings.append(f"Payment data issue: {issue}")
    
    # Clean Study - ensure it's a string
    if 'Study' in df_clean.columns:
        df_clean['Study'] = df_clean['Study'].astype(str)
    
    # Clean Day - ensure it's numeric
    if 'Day' in df_clean.columns:
        df_clean['Day'] = df_clean['Day'].apply(lambda x: clean_numeric_value(x, 0))
        df_clean['Day'] = df_clean['Day'].astype(int)
    
    # Clean VisitName - ensure it's a string
    if 'VisitName' in df_clean.columns:
        df_clean['VisitName'] = df_clean['VisitName'].astype(str)
    
    # Clean optional columns
    optional_columns = {
        'SiteforVisit': str,
        'ToleranceBefore': int,
        'ToleranceAfter': int
    }
    
    for col, dtype in optional_columns.items():
        if col in df_clean.columns:
            if dtype == int:
                df_clean[col] = df_clean[col].apply(lambda x: clean_numeric_value(x, 0))
                df_clean[col] = df_clean[col].astype(int)
            else:
                df_clean[col] = df_clean[col].fillna('').astype(str)
        else:
            if dtype == int:
                df_clean[col] = 0
            else:
                df_clean[col] = ''
            warnings.append(f"Missing optional column '{col}', filled with defaults")
    
    # Validate data quality
    if len(df_clean) == 0:
        errors.append("No valid trial records found")
    
    # Check for studies without Day 1
    studies = df_clean['Study'].unique()
    for study in studies:
        study_data = df_clean[df_clean['Study'] == study]
        if 1 not in study_data['Day'].values:
            errors.append(f"Study '{study}' has no Day 1 visit defined. Day 1 is required as baseline.")
    
    # Check for duplicate Study+Day combinations
    duplicates = df_clean.duplicated(subset=['Study', 'Day']).sum()
    if duplicates > 0:
        warnings.append(f"{duplicates} duplicate Study+Day combinations found")
    
    log_activity(f"Validated trials file: {len(df_clean)} records, {len(errors)} errors, {len(warnings)} warnings", level='info')
    
    return df_clean, errors + warnings

def validate_visits_file(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
    """Validate and clean visits file"""
    errors = []
    warnings = []
    
    # Required columns
    required_columns = ['PatientID', 'Study', 'VisitName', 'ActualDate']
    missing_columns = [col for col in required_columns if col not in df.columns]
    
    if missing_columns:
        errors.append(f"Missing required columns: {missing_columns}")
        return df, errors
    
    # Clean the dataframe
    df_clean = df.copy()
    
    # Clean PatientID - ensure it's a string
    if 'PatientID' in df_clean.columns:
        df_clean['PatientID'] = df_clean['PatientID'].astype(str)
    
    # Clean Study - ensure it's a string
    if 'Study' in df_clean.columns:
        df_clean['Study'] = df_clean['Study'].astype(str)
    
    # Clean VisitName - ensure it's a string
    if 'VisitName' in df_clean.columns:
        df_clean['VisitName'] = df_clean['VisitName'].astype(str)
    
    # Clean ActualDate
    if 'ActualDate' in df_clean.columns:
        df_clean['ActualDate'] = df_clean['ActualDate'].apply(lambda x: clean_date_value(x))
        # Check for invalid dates
        invalid_dates = df_clean['ActualDate'].isna().sum()
        if invalid_dates > 0:
            warnings.append(f"{invalid_dates} visits have invalid actual dates")
    
    # Clean optional columns
    optional_columns = {
        'Notes': str
    }
    
    for col, dtype in optional_columns.items():
        if col in df_clean.columns:
            df_clean[col] = df_clean[col].fillna('').astype(str)
        else:
            df_clean[col] = ''
            warnings.append(f"Missing optional column '{col}', filled with empty strings")
    
    # Validate data quality
    if len(df_clean) == 0:
        errors.append("No valid visit records found")
    
    log_activity(f"Validated visits file: {len(df_clean)} records, {len(errors)} errors, {len(warnings)} warnings", level='info')
    
    return df_clean, errors + warnings

def validate_file_upload(file, file_type: str) -> Tuple[Optional[pd.DataFrame], List[str]]:
    """Main validation function for file uploads"""
    try:
        # Read the file
        if file.name.endswith('.csv'):
            df = pd.read_csv(file)
        elif file.name.endswith(('.xls', '.xlsx')):
            df = pd.read_excel(file)
        else:
            return None, [f"Unsupported file type: {file.name.split('.')[-1]}"]
        
        # Validate based on file type
        if file_type == 'patients':
            return validate_patients_file(df)
        elif file_type == 'trials':
            return validate_trials_file(df)
        elif file_type == 'visits':
            return validate_visits_file(df)
        else:
            return None, [f"Unknown file type: {file_type}"]
            
    except Exception as e:
        return None, [f"Error reading file: {str(e)}"]

def get_validation_summary(errors: List[str], warnings: List[str]) -> str:
    """Generate a user-friendly validation summary"""
    summary = []
    
    if errors:
        summary.append(f"❌ **Errors ({len(errors)}):**")
        for error in errors:
            summary.append(f"  • {error}")
    
    if warnings:
        summary.append(f"⚠️ **Warnings ({len(warnings)}):**")
        for warning in warnings:
            summary.append(f"  • {warning}")
    
    if not errors and not warnings:
        summary.append("✅ **File validation passed successfully!**")
    
    return "\n".join(summary)
