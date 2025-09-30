"""
Centralized Payment Column Handler

This module provides consistent payment column handling across all modules
to prevent data loss and ensure accurate financial calculations.
"""

import pandas as pd
import streamlit as st
from helpers import log_activity

def get_payment_column_name(df):
    """
    Identify the correct payment column name in a DataFrame.
    
    Args:
        df (pd.DataFrame): DataFrame to search for payment column
        
    Returns:
        str: The correct payment column name, or 'Payment' if none found
    """
    if df is None or df.empty:
        return 'Payment'
    
    # Priority order for payment column names
    payment_columns = ['Payment', 'Income', 'Amount', 'Revenue', 'Fee', 'Cost']
    
    for col in payment_columns:
        if col in df.columns:
            log_activity(f"Found payment column: {col}", level='info')
            return col
    
    # If no payment column found, return default
    log_activity("No payment column found, using default 'Payment'", level='warning')
    return 'Payment'

def normalize_payment_column(df, target_column='Payment'):
    """
    Normalize payment column to a standard name and clean the data.
    
    Args:
        df (pd.DataFrame): DataFrame to normalize
        target_column (str): Target column name (default: 'Payment')
        
    Returns:
        pd.DataFrame: DataFrame with normalized payment column
    """
    if df is None or df.empty:
        return df
    
    # Find the payment column
    payment_col = get_payment_column_name(df)
    
    # If it's already the target column, just clean it
    if payment_col == target_column:
        df[target_column] = clean_payment_values(df[payment_col])
        return df
    
    # Rename the column
    df = df.rename(columns={payment_col: target_column})
    
    # Clean the values
    df[target_column] = clean_payment_values(df[target_column])
    
    log_activity(f"Normalized payment column '{payment_col}' to '{target_column}'", level='info')
    return df

def clean_payment_values(series):
    """
    Clean payment values by removing currency symbols and converting to float.
    
    Args:
        series (pd.Series): Series containing payment values
        
    Returns:
        pd.Series: Cleaned payment values as float
    """
    if series is None or series.empty:
        return pd.Series(dtype='float64')
    
    # Convert to string first to handle various data types
    cleaned = series.astype(str)
    
    # Remove common currency symbols and formatting
    cleaned = cleaned.str.replace('£', '', regex=False)
    cleaned = cleaned.str.replace('$', '', regex=False)
    cleaned = cleaned.str.replace('€', '', regex=False)
    cleaned = cleaned.str.replace(',', '', regex=False)
    cleaned = cleaned.str.replace(' ', '', regex=False)
    cleaned = cleaned.str.replace('"', '', regex=False)
    
    # Convert to numeric, coercing errors to NaN
    cleaned = pd.to_numeric(cleaned, errors='coerce')
    
    # Fill NaN values with 0
    cleaned = cleaned.fillna(0)
    
    # Log any problematic values
    if cleaned.isna().any():
        nan_count = cleaned.isna().sum()
        log_activity(f"Warning: {nan_count} payment values could not be converted to numeric", level='warning')
    
    return cleaned

def get_payment_value(row, payment_column='Payment'):
    """
    Safely extract payment value from a row.
    
    Args:
        row (pd.Series or dict): Row containing payment data
        payment_column (str): Name of the payment column
        
    Returns:
        float: Payment value, or 0.0 if not found/invalid
    """
    try:
        if payment_column in row:
            value = row[payment_column]
            if pd.isna(value) or value == '':
                return 0.0
            return float(value)
        else:
            log_activity(f"Payment column '{payment_column}' not found in row", level='warning')
            return 0.0
    except (ValueError, TypeError) as e:
        log_activity(f"Error converting payment value to float: {e}", level='warning')
        return 0.0

def validate_payment_data(df, payment_column='Payment'):
    """
    Validate payment data and report issues.
    
    Args:
        df (pd.DataFrame): DataFrame to validate
        payment_column (str): Name of the payment column
        
    Returns:
        dict: Validation results with counts and issues
    """
    if df is None or df.empty:
        return {'valid': True, 'total_rows': 0, 'valid_payments': 0, 'issues': []}
    
    if payment_column not in df.columns:
        return {
            'valid': False, 
            'total_rows': len(df), 
            'valid_payments': 0, 
            'issues': [f"Payment column '{payment_column}' not found"]
        }
    
    payment_series = df[payment_column]
    total_rows = len(payment_series)
    
    # Check for non-numeric values
    non_numeric = payment_series.apply(lambda x: not pd.api.types.is_numeric_dtype(type(x)) and str(x) not in ['0', '0.0', ''])
    non_numeric_count = non_numeric.sum()
    
    # Check for negative values
    negative_count = (payment_series < 0).sum()
    
    # Check for very large values (potential data entry errors)
    large_values = (payment_series > 1000000).sum()
    
    issues = []
    if non_numeric_count > 0:
        issues.append(f"{non_numeric_count} non-numeric payment values")
    if negative_count > 0:
        issues.append(f"{negative_count} negative payment values")
    if large_values > 0:
        issues.append(f"{large_values} very large payment values (>£1M)")
    
    valid_payments = total_rows - non_numeric_count
    
    return {
        'valid': len(issues) == 0,
        'total_rows': total_rows,
        'valid_payments': valid_payments,
        'issues': issues
    }

def ensure_payment_column(df, payment_column='Payment'):
    """
    Ensure a DataFrame has a payment column with proper data.
    
    Args:
        df (pd.DataFrame): DataFrame to process
        payment_column (str): Desired payment column name
        
    Returns:
        pd.DataFrame: DataFrame with guaranteed payment column
    """
    if df is None or df.empty:
        # Create empty DataFrame with payment column
        empty_df = pd.DataFrame()
        empty_df[payment_column] = pd.Series(dtype='float64')
        return empty_df
    
    # Normalize the payment column
    df = normalize_payment_column(df, payment_column)
    
    # Validate the data
    validation = validate_payment_data(df, payment_column)
    
    if not validation['valid']:
        log_activity(f"Payment data validation issues: {validation['issues']}", level='warning')
    
    return df
