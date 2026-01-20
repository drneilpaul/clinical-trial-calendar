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
    
    # Required columns - PatientPractice is recruitment site
    required_columns = ['PatientID', 'Study', 'StartDate', 'PatientPractice']
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
    
    # NEW SECTION: Validate PatientPractice is present and valid (recruitment site)
    if 'PatientPractice' in df_clean.columns:
        df_clean['PatientPractice'] = df_clean['PatientPractice'].fillna('').astype(str).str.strip()
        
        # Check for invalid values
        invalid_sites = ['', 'nan', 'None', 'null', 'NULL', 'Unknown Site', 'unknown site', 'UNKNOWN SITE']
        invalid_mask = df_clean['PatientPractice'].isin(invalid_sites)
        invalid_count = invalid_mask.sum()
        
        if invalid_count > 0:
            # Get row numbers and patient IDs of invalid rows
            invalid_rows = df_clean[invalid_mask]
            row_details = []
            for idx, row in invalid_rows.iterrows():
                row_num = idx + 2  # +2 because Excel is 1-indexed and has header row
                patient_id = row.get('PatientID', 'Unknown')
                row_details.append(f"Row {row_num} (Patient {patient_id})")
            
            error_msg = f"❌ {invalid_count} patient(s) missing required PatientPractice (recruitment site). "
            error_msg += f"Invalid rows: {', '.join(row_details[:5])}"  # Show first 5
            if len(row_details) > 5:
                error_msg += f" and {len(row_details) - 5} more"
            errors.append(error_msg)

    # NEW SECTION: Handle SiteSeenAt (visit location)
    if 'SiteSeenAt' not in df_clean.columns:
        # Default to PatientPractice for backward compatibility
        df_clean['SiteSeenAt'] = df_clean['PatientPractice']
        warnings.append("Missing optional column 'SiteSeenAt' (visit site), defaulted to PatientPractice")
    else:
        df_clean['SiteSeenAt'] = df_clean['SiteSeenAt'].fillna('').astype(str).str.strip()
        invalid_sites = ['', 'nan', 'None', 'null', 'NULL', 'Unknown Site', 'unknown site', 'UNKNOWN SITE']
        invalid_mask = df_clean['SiteSeenAt'].isin(invalid_sites)
        invalid_count = invalid_mask.sum()
        if invalid_count > 0:
            invalid_rows = df_clean[invalid_mask]
            row_details = []
            for idx, row in invalid_rows.iterrows():
                row_num = idx + 2
                patient_id = row.get('PatientID', 'Unknown')
                row_details.append(f"Row {row_num} (Patient {patient_id})")
            error_msg = f"❌ {invalid_count} patient(s) missing required SiteSeenAt (visit site). "
            error_msg += f"Invalid rows: {', '.join(row_details[:5])}"
            if len(row_details) > 5:
                error_msg += f" and {len(row_details) - 5} more"
            errors.append(error_msg)
    
    # Optional columns that can still be empty
    optional_columns = {
        'Site': str,  # Keep Site as optional for backward compatibility
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
    
    # Required columns - ADD SiteforVisit to this list
    required_columns = ['Study', 'Day', 'VisitName', 'SiteforVisit']
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
    
    # NEW SECTION: Validate SiteforVisit is present and valid
    if 'SiteforVisit' in df_clean.columns:
        df_clean['SiteforVisit'] = df_clean['SiteforVisit'].fillna('').astype(str).str.strip()
        
        # Check for invalid values
        invalid_sites = ['', 'nan', 'None', 'null', 'NULL', 'Unknown Site', 'unknown site', 'UNKNOWN SITE', 'Default Site']
        invalid_mask = df_clean['SiteforVisit'].isin(invalid_sites)
        invalid_count = invalid_mask.sum()
        
        if invalid_count > 0:
            # Get details of invalid rows
            invalid_rows = df_clean[invalid_mask]
            row_details = []
            for idx, row in invalid_rows.iterrows():
                row_num = idx + 2  # +2 because Excel is 1-indexed and has header row
                study = row.get('Study', 'Unknown')
                visit = row.get('VisitName', 'Unknown')
                row_details.append(f"Row {row_num} ({study}/{visit})")
            
            error_msg = f"❌ {invalid_count} trial visit(s) missing required SiteforVisit (contract holder). "
            error_msg += f"Invalid rows: {', '.join(row_details[:5])}"  # Show first 5
            if len(row_details) > 5:
                error_msg += f" and {len(row_details) - 5} more"
            errors.append(error_msg)
    
    # Optional columns
    optional_columns = {
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
    
    # NEW: Handle Gantt and recruitment tracking optional columns
    # Date override fields (FPFV, LPFV, LPLV)
    for date_col in ['FPFV', 'LPFV', 'LPLV']:
        if date_col in df_clean.columns:
            df_clean[date_col] = df_clean[date_col].apply(lambda x: clean_date_value(x))
        else:
            df_clean[date_col] = None
    
    # StudyStatus field
    if 'StudyStatus' in df_clean.columns:
        df_clean['StudyStatus'] = df_clean['StudyStatus'].fillna('active').astype(str).str.strip().str.lower()
        # Validate status values
        valid_statuses = ['active', 'contracted', 'in_setup', 'expression_of_interest']
        invalid_statuses = df_clean[~df_clean['StudyStatus'].isin(valid_statuses) & df_clean['StudyStatus'].notna()]
        if not invalid_statuses.empty:
            invalid_count = len(invalid_statuses)
            warnings.append(f"⚠️ {invalid_count} trial(s) have invalid StudyStatus values. Valid values: {', '.join(valid_statuses)}. Defaulting to 'active'.")
            df_clean.loc[~df_clean['StudyStatus'].isin(valid_statuses), 'StudyStatus'] = 'active'
    else:
        df_clean['StudyStatus'] = 'active'
        warnings.append("Missing optional column 'StudyStatus', filled with default 'active'")
    
    # RecruitmentTarget field
    if 'RecruitmentTarget' in df_clean.columns:
        df_clean['RecruitmentTarget'] = df_clean['RecruitmentTarget'].apply(lambda x: clean_numeric_value(x, None) if pd.notna(x) and str(x).strip() not in ['', 'None', 'nan', 'null', 'NULL'] else None)
        # Validate non-negative
        negative_targets = df_clean[(df_clean['RecruitmentTarget'] < 0) & df_clean['RecruitmentTarget'].notna()]
        if not negative_targets.empty:
            warnings.append(f"⚠️ {len(negative_targets)} trial(s) have negative RecruitmentTarget values. Setting to NULL.")
            df_clean.loc[df_clean['RecruitmentTarget'] < 0, 'RecruitmentTarget'] = None
        # Convert to int where not null
        df_clean['RecruitmentTarget'] = df_clean['RecruitmentTarget'].apply(lambda x: int(x) if pd.notna(x) else None)
    else:
        df_clean['RecruitmentTarget'] = None
    
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
        'Notes': str,
        'IsWithdrawn': object  # accept any truthy/falsy representation
    }

    def _normalize_withdrawn(val):
        if pd.isna(val):
            return ''
        s = str(val).strip().lower()
        if s in {'true', 'yes', 'y', '1', 'withdrawn'}:
            return 'True'
        if s in {'false', 'no', 'n', '0', ''}:
            return ''
        return s  # leave as-is for visibility

    for col, dtype in optional_columns.items():
        if col in df_clean.columns:
            if col == 'IsWithdrawn':
                df_clean[col] = df_clean[col].apply(_normalize_withdrawn)
            else:
                df_clean[col] = df_clean[col].fillna('').astype(str)
        else:
            df_clean[col] = ''
            warnings.append(f"Missing optional column '{col}', filled with empty strings")
    
    # Validate data quality
    if len(df_clean) == 0:
        errors.append("No valid visit records found")
    
    log_activity(f"Validated visits file: {len(df_clean)} records, {len(errors)} errors, {len(warnings)} warnings", level='info')
    
    return df_clean, errors + warnings

def validate_study_site_details_file(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
    """Validate and clean study site details file"""
    errors = []
    warnings = []
    
    df_clean = df.copy()
    if 'ContractSite' not in df_clean.columns:
        if 'ContractedSite' in df_clean.columns:
            df_clean = df_clean.rename(columns={'ContractedSite': 'ContractSite'})
        elif 'SiteforVisit' in df_clean.columns:
            df_clean = df_clean.rename(columns={'SiteforVisit': 'ContractSite'})
    
    required_columns = ['Study', 'ContractSite']
    missing = [col for col in required_columns if col not in df_clean.columns]
    if missing:
        return df_clean, [f"Missing required columns: {', '.join(missing)}"]
    
    # Normalize whitespace
    for col in df_clean.columns:
        if df_clean[col].dtype == 'object':
            df_clean[col] = df_clean[col].fillna('').astype(str).str.strip()
    
    # Validate required fields
    invalid_mask = (
        df_clean['Study'].isna() | (df_clean['Study'].astype(str).str.strip() == '') |
        df_clean['ContractSite'].isna() | (df_clean['ContractSite'].astype(str).str.strip() == '')
    )
    if invalid_mask.any():
        invalid_count = invalid_mask.sum()
        errors.append(f"❌ {invalid_count} row(s) missing Study or ContractSite")
    
    # Optional date fields
    for date_col in ['FPFV', 'LPFV', 'LPLV', 'EOIDate']:
        if date_col in df_clean.columns:
            df_clean[date_col] = pd.to_datetime(df_clean[date_col], errors='coerce')
    
    # RecruitmentTarget should be numeric when provided
    if 'RecruitmentTarget' in df_clean.columns:
        df_clean['RecruitmentTarget'] = pd.to_numeric(df_clean['RecruitmentTarget'], errors='coerce')
    
    log_activity(f"Validated study site details file: {len(df_clean)} records, {len(errors)} errors, {len(warnings)} warnings", level='info')
    
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
        elif file_type == 'study_site_details':
            return validate_study_site_details_file(df)
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
