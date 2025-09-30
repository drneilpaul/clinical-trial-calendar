import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple
import logging
from helpers import (
    add_error, add_warning, add_info, safe_string_conversion,
    parse_dates_column, calculate_financial_year, clean_patient_id,
    validate_required_columns
)

# Configure logging
logger = logging.getLogger(__name__)

# =============================================================================
# DATA VALIDATION FUNCTIONS
# =============================================================================

def validate_calendar_data(patients_df: pd.DataFrame, trials_df: pd.DataFrame) -> bool:
    """
    Comprehensive validation of input data for calendar generation
    
    Args:
        patients_df: Patients DataFrame
        trials_df: Trials DataFrame
        
    Returns:
        True if validation passes, False otherwise
    """
    validation_passed = True
    
    try:
        # Validate patients data
        if not validate_required_columns(patients_df, ['PatientID', 'Study', 'StartDate'], "Patients file"):
            validation_passed = False
        
        # Validate trials data
        if not validate_required_columns(trials_df, ['Study', 'Day', 'VisitName'], "Trials file"):
            validation_passed = False
        
        if not validation_passed:
            return False
        
        # Check for empty data
        if patients_df.empty:
            add_error("Patients file contains no data")
            return False
            
        if trials_df.empty:
            add_error("Trials file contains no data")
            return False
        
        # Validate data content
        if not _validate_patients_content(patients_df):
            validation_passed = False
            
        if not _validate_trials_content(trials_df):
            validation_passed = False
        
        # Cross-validate studies between files
        if not _validate_study_consistency(patients_df, trials_df):
            validation_passed = False
        
        return validation_passed
        
    except Exception as e:
        add_error(f"Validation failed with unexpected error: {str(e)}")
        logger.error(f"Validation error: {e}")
        return False

def _validate_patients_content(patients_df: pd.DataFrame) -> bool:
    """Validate patients data content"""
    validation_passed = True
    
    try:
        # Check for missing patient IDs
        missing_patient_ids = patients_df['PatientID'].isna().sum()
        if missing_patient_ids > 0:
            add_warning(f"{missing_patient_ids} rows have missing PatientID")
            validation_passed = False
        
        # Check for duplicate patient-study combinations
        duplicates = patients_df.duplicated(subset=['PatientID', 'Study']).sum()
        if duplicates > 0:
            add_warning(f"{duplicates} duplicate PatientID-Study combinations found")
            
        # Validate start dates
        start_date_issues = patients_df['StartDate'].isna().sum()
        if start_date_issues > 0:
            add_warning(f"{start_date_issues} rows have missing StartDate")
            validation_passed = False
        
        # Check for reasonable date ranges
        try:
            start_dates = pd.to_datetime(patients_df['StartDate'], errors='coerce')
            current_year = datetime.now().year
            
            # Check for dates too far in past or future
            old_dates = start_dates < datetime(current_year - 10, 1, 1)
            future_dates = start_dates > datetime(current_year + 5, 12, 31)
            
            if old_dates.sum() > 0:
                add_warning(f"{old_dates.sum()} start dates are more than 10 years old")
                
            if future_dates.sum() > 0:
                add_warning(f"{future_dates.sum()} start dates are more than 5 years in the future")
                
        except Exception as e:
            add_warning(f"Could not validate start date ranges: {str(e)}")
        
        return validation_passed
        
    except Exception as e:
        add_error(f"Error validating patients content: {str(e)}")
        return False

def _validate_trials_content(trials_df: pd.DataFrame) -> bool:
    """Validate trials data content"""
    validation_passed = True
    
    try:
        # Check for missing studies
        missing_studies = trials_df['Study'].isna().sum()
        if missing_studies > 0:
            add_warning(f"{missing_studies} rows have missing Study")
            validation_passed = False
        
        # Check for missing visit names
        missing_visits = trials_df['VisitName'].isna().sum()
        if missing_visits > 0:
            add_warning(f"{missing_visits} rows have missing VisitName")
            validation_passed = False
        
        # Validate day values
        try:
            day_values = pd.to_numeric(trials_df['Day'], errors='coerce')
            invalid_days = day_values.isna().sum()
            
            if invalid_days > 0:
                add_warning(f"{invalid_days} rows have invalid Day values")
                validation_passed = False
            
            # Check for reasonable day ranges
            negative_days = (day_values < 0).sum()
            large_days = (day_values > 3650).sum()  # 10 years
            
            if negative_days > 0:
                add_warning(f"{negative_days} visits have negative day values")
                
            if large_days > 0:
                add_warning(f"{large_days} visits have day values > 10 years")
                
        except Exception as e:
            add_warning(f"Could not validate day values: {str(e)}")
            validation_passed = False
        
        return validation_passed
        
    except Exception as e:
        add_error(f"Error validating trials content: {str(e)}")
        return False

def _validate_study_consistency(patients_df: pd.DataFrame, trials_df: pd.DataFrame) -> bool:
    """Validate that studies are consistent between files"""
    try:
        patient_studies = set(patients_df['Study'].dropna().unique())
        trial_studies = set(trials_df['Study'].dropna().unique())
        
        # Studies in patients but not in trials
        missing_trial_studies = patient_studies - trial_studies
        if missing_trial_studies:
            add_warning(f"Studies in patients file but not in trials file: {', '.join(missing_trial_studies)}")
        
        # Studies in trials but not in patients
        missing_patient_studies = trial_studies - patient_studies
        if missing_patient_studies:
            add_info(f"Studies in trials file but not in patients file: {', '.join(missing_patient_studies)}")
        
        # At least some overlap is required
        common_studies = patient_studies & trial_studies
        if not common_studies:
            add_error("No common studies found between patients and trials files")
            return False
        
        add_info(f"Found {len(common_studies)} common studies: {', '.join(sorted(common_studies))}")
        return True
        
    except Exception as e:
        add_error(f"Error validating study consistency: {str(e)}")
        return False

# =============================================================================
# MAIN CALENDAR GENERATION FUNCTION
# =============================================================================

def build_calendar(patients_df: pd.DataFrame, 
                  trials_df: pd.DataFrame, 
                  actual_visits_df: Optional[pd.DataFrame] = None) -> Optional[pd.DataFrame]:
    """
    Build comprehensive visit calendar with enhanced error handling
    
    Args:
        patients_df: Patient data with PatientID, Study, StartDate
        trials_df: Trial schedule with Study, Day, VisitName
        actual_visits_df: Optional actual visit data
        
    Returns:
        Generated calendar DataFrame or None if failed
    """
    try:
        add_info("Starting calendar generation process...")
        
        # Prepare data with error handling
        patients_clean = _prepare_patients_data(patients_df)
        if patients_clean is None:
            add_error("Failed to prepare patients data")
            return None
        
        trials_clean = _prepare_trials_data(trials_df)
        if trials_clean is None:
            add_error("Failed to prepare trials data")
            return None
        
        # Generate base calendar
        calendar_df = _generate_base_calendar(patients_clean, trials_clean)
        if calendar_df is None or calendar_df.empty:
            add_error("Failed to generate base calendar")
            return None
        
        # Merge actual visits if provided
        if actual_visits_df is not None and not actual_visits_df.empty:
            calendar_df = _merge_actual_visits(calendar_df, actual_visits_df)
        
        # Add calculated fields
        calendar_df = _add_calculated_fields(calendar_df)
        
        # Final validation and cleanup
        calendar_df = _finalize_calendar(calendar_df)
        
        if calendar_df is not None and not calendar_df.empty:
            add_info(f"Calendar generation completed successfully: {len(calendar_df)} visit records created")
        else:
            add_error("Calendar generation completed but result is empty")
            
        return calendar_df
        
    except Exception as e:
        add_error(f"Unexpected error in calendar generation: {str(e)}")
        logger.error(f"Calendar generation error: {e}")
        return None

# =============================================================================
# DATA PREPARATION FUNCTIONS
# =============================================================================

def _prepare_patients_data(patients_df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """Prepare and clean patients data"""
    try:
        df = patients_df.copy()
        initial_count = len(df)
        
        # Clean patient IDs
        df['PatientID'] = df['PatientID'].apply(clean_patient_id)
        
        # Remove rows with empty patient IDs
        df = df[df['PatientID'] != '']
        empty_id_removed = initial_count - len(df)
        if empty_id_removed > 0:
            add_warning(f"Removed {empty_id_removed} rows with empty PatientID")
        
        # Parse start dates
        df = parse_dates_column(df, 'StartDate')
        
        # Remove rows with invalid start dates
        df = df[df['StartDate'].notna()]
        invalid_date_removed = len(df) - (initial_count - empty_id_removed)
        if invalid_date_removed > 0:
            add_warning(f"Removed {abs(invalid_date_removed)} rows with invalid StartDate")
        
        # Clean study names
        df['Study'] = df['Study'].astype(str).str.strip()
        df = df[df['Study'] != '']
        
        add_info(f"Prepared patients data: {len(df)} valid records from {initial_count} input records")
        return df
        
    except Exception as e:
        add_error(f"Error preparing patients data: {str(e)}")
        return None

def _prepare_trials_data(trials_df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """Prepare and clean trials data"""
    try:
        df = trials_df.copy()
        initial_count = len(df)
        
        # Clean study names
        df['Study'] = df['Study'].astype(str).str.strip()
        df = df[df['Study'] != '']
        
        # Clean visit names
        df['VisitName'] = df['VisitName'].astype(str).str.strip()
        df = df[df['VisitName'] != '']
        
        # Convert and validate day values
        df['Day'] = pd.to_numeric(df['Day'], errors='coerce')
        df = df[df['Day'].notna()]
        
        # Remove duplicate entries
        df = df.drop_duplicates(subset=['Study', 'Day', 'VisitName'])
        
        final_count = len(df)
        removed_count = initial_count - final_count
        if removed_count > 0:
            add_warning(f"Removed {removed_count} invalid/duplicate trial records")
        
        add_info(f"Prepared trials data: {final_count} valid records from {initial_count} input records")
        return df
        
    except Exception as e:
        add_error(f"Error preparing trials data: {str(e)}")
        return None

# =============================================================================
# CALENDAR GENERATION CORE FUNCTIONS
# =============================================================================

def _generate_base_calendar(patients_df: pd.DataFrame, trials_df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """Generate base calendar by merging patients and trials"""
    try:
        # Merge patients with trials on Study
        calendar_df = patients_df.merge(trials_df, on='Study', how='inner')
        
        if calendar_df.empty:
            add_error("No matching studies found between patients and trials - check study names")
            return None
        
        # Calculate planned visit dates
        calendar_df['PlannedDate'] = calendar_df['StartDate'] + pd.to_timedelta(calendar_df['Day'], unit='days')
        
        # Create visit key for matching
        calendar_df['VisitKey'] = (
            calendar_df['PatientID'].astype(str) + '|' + 
            calendar_df['Study'].astype(str) + '|' + 
            calendar_df['VisitName'].astype(str)
        )
        
        # Sort by patient and planned date
        calendar_df = calendar_df.sort_values(['PatientID', 'PlannedDate'])
        
        add_info(f"Generated base calendar with {len(calendar_df)} planned visits")
        return calendar_df
        
    except Exception as e:
        add_error(f"Error generating base calendar: {str(e)}")
        return None

def _merge_actual_visits(calendar_df: pd.DataFrame, actual_visits_df: pd.DataFrame) -> pd.DataFrame:
    """Merge actual visit data with planned calendar"""
    try:
        actual_df = actual_visits_df.copy()
        
        # Prepare actual visits data
        actual_df['PatientID'] = actual_df['PatientID'].apply(clean_patient_id)
        actual_df['Study'] = actual_df['Study'].astype(str).str.strip()
        actual_df['VisitName'] = actual_df['VisitName'].astype(str).str.strip()
        
        # Parse actual dates
        actual_df = parse_dates_column(actual_df, 'ActualDate')
        
        # Create visit key
        actual_df['VisitKey'] = (
            actual_df['PatientID'].astype(str) + '|' + 
            actual_df['Study'].astype(str) + '|' + 
            actual_df['VisitName'].astype(str)
        )
        
        # Remove duplicates, keeping the latest actual date
        actual_df = actual_df.sort_values('ActualDate').drop_duplicates(subset=['VisitKey'], keep='last')
        
        # Merge with calendar
        calendar_df = calendar_df.merge(
            actual_df[['VisitKey', 'ActualDate']], 
            on='VisitKey', 
            how='left'
        )
        
        actual_visits_count = calendar_df['ActualDate'].notna().sum()
        add_info(f"Merged {actual_visits_count} actual visit records")
        
        return calendar_df
        
    except Exception as e:
        add_warning(f"Error merging actual visits: {str(e)}")
        return calendar_df  # Return original calendar if merge fails

def _add_calculated_fields(calendar_df: pd.DataFrame) -> pd.DataFrame:
    """Add calculated fields to calendar"""
    try:
        # Add financial year
        calendar_df['FinancialYear'] = calendar_df['PlannedDate'].apply(calculate_financial_year)
        
        # Add visit status
        calendar_df['VisitStatus'] = 'Planned'
        calendar_df.loc[calendar_df['ActualDate'].notna(), 'VisitStatus'] = 'Completed'
        
        # Add days variance for completed visits
        if 'ActualDate' in calendar_df.columns:
            calendar_df['DaysVariance'] = (
                calendar_df['ActualDate'] - calendar_df['PlannedDate']
            ).dt.days
            
            # Only show variance for completed visits
            calendar_df.loc[calendar_df['ActualDate'].isna(), 'DaysVariance'] = None
        
        # Add overdue flag
        today = datetime.now().date()
        calendar_df['IsOverdue'] = (
            (calendar_df['ActualDate'].isna()) & 
            (calendar_df['PlannedDate'].dt.date < today)
        )
        
        add_info("Added calculated fields to calendar")
        return calendar_df
        
    except Exception as e:
        add_warning(f"Error adding calculated fields: {str(e)}")
        return calendar_df

def _finalize_calendar(calendar_df: pd.DataFrame) -> pd.DataFrame:
    """Final cleanup and organization of calendar"""
    try:
        # Select and order columns
        output_columns = [
            'PatientID', 'Study', 'VisitName', 'Day', 
            'PlannedDate', 'ActualDate', 'VisitStatus',
            'DaysVariance', 'IsOverdue', 'FinancialYear'
        ]
        
        # Only include columns that exist
        available_columns = [col for col in output_columns if col in calendar_df.columns]
        calendar_df = calendar_df[available_columns]
        
        # Sort final output
        calendar_df = calendar_df.sort_values(['PatientID', 'PlannedDate'])
        
        # Reset index
        calendar_df = calendar_df.reset_index(drop=True)
        
        add_info("Calendar finalization completed")
        return calendar_df
        
    except Exception as e:
        add_warning(f"Error finalizing calendar: {str(e)}")
        return calendar_df
