import pandas as pd
from datetime import date

def format_currency(value):
    """Format a numeric value as currency"""
    if pd.isna(value) or value == 0:
        return "£0.00"
    return f"£{value:,.2f}"

def format_currency_or_empty(value):
    """Format currency but return empty string for zero values"""
    if pd.isna(value) or value == 0:
        return ""
    return f"£{value:,.2f}"

def format_percentage(value, decimals=1):
    """Format a decimal as percentage"""
    return f"{value:.{decimals}%}"

def apply_currency_formatting(df, columns):
    """Apply currency formatting to specified columns in a dataframe"""
    df_formatted = df.copy()
    for col in columns:
        if col in df_formatted.columns:
            df_formatted[col] = df_formatted[col].apply(format_currency)
    return df_formatted

def apply_currency_or_empty_formatting(df, columns):
    """Apply currency formatting but empty for zeros to specified columns"""
    df_formatted = df.copy()
    for col in columns:
        if col in df_formatted.columns:
            df_formatted[col] = df_formatted[col].apply(format_currency_or_empty)
    return df_formatted

def create_site_header_row(columns, site_column_mapping):
    """Create enhanced three-level site header row for calendar display"""
    header_rows = {
        'level1_site': {},      # Visit site (where work is done)
        'level2_study_patient': {},  # Study_PatientID 
        'level3_origin': {}     # Origin site (who recruited)
    }
    
    for col in columns:
        if col in ["Date", "Day", "Label"]:
            # System columns
            header_rows['level1_site'][col] = ""
            header_rows['level2_study_patient'][col] = ""
            header_rows['level3_origin'][col] = ""
        else:
            # Find which visit site this column belongs to
            visit_site_found = ""
            study_patient = ""
            origin_site = ""
            
            for visit_site, site_data in site_column_mapping.items():
                if col in site_data['columns']:
                    visit_site_found = visit_site
                    
                    # Find patient info for this column
                    for patient_info in site_data['patient_info']:
                        if patient_info['col_id'] == col:
                            study_code = str(patient_info['study'])
                            patient_code = str(patient_info['patient_id'])
                            study_patient = f"{study_code}_{patient_code}"
                            if len(study_code) > 6:
                                study_code = study_code[:5] + "…"
                            if len(patient_code) > 6:
                                patient_code = "…" + patient_code[-5:]
                            study_patient = f"{study_code}_{patient_code}"
                            origin_site_value = patient_info.get('origin_site', '')
                            if origin_site_value and origin_site_value != 'Unknown Origin':
                                origin_site = origin_site_value  # Show full name, no truncation
                            else:
                                origin_site = ""
                            break
                    break
            
            header_rows['level1_site'][col] = visit_site_found
            header_rows['level2_study_patient'][col] = study_patient
            header_rows['level3_origin'][col] = origin_site
    
    return header_rows

def style_calendar_row(row, today_date):
    """Apply styling to calendar rows - updated for three-level headers"""
    try:
        if row.name < 3:  # First three rows are headers
            return create_enhanced_header_styles(row, row.name)
        else:
            return create_data_row_styles(row, today_date)
    except Exception as e:
        # Fallback to basic styling if there are issues
        return [''] * len(row)

def create_enhanced_header_styles(row, header_level):
    """Create styles for three-level headers"""
    styles = []
    for col_name in row.index:
        if header_level == 0:  # Level 1: Visit sites
            if row[col_name] != "":
                styles.append('background-color: #1e40af; color: white; font-weight: bold; text-align: center; border: 1px solid #ccc; font-size: 14px;')
            else:
                styles.append('background-color: #f8f9fa; border: 1px solid #ccc;')
        elif header_level == 1:  # Level 2: Study_PatientID  
            if row[col_name] != "":
                styles.append('background-color: #3b82f6; color: white; font-weight: bold; text-align: center; border: 1px solid #ccc; font-size: 12px;')
            else:
                styles.append('background-color: #f8f9fa; border: 1px solid #ccc;')
        elif header_level == 2:  # Level 3: Origin sites
            if row[col_name] != "":
                styles.append('background-color: #93c5fd; color: #1e40af; font-weight: normal; text-align: center; border: 1px solid #ccc; font-size: 10px; font-style: italic;')
            else:
                styles.append('background-color: #f8f9fa; border: 1px solid #ccc;')
        else:
            styles.append('background-color: #f8f9fa; border: 1px solid #ccc;')
    return styles

def create_header_styles(row):
    """Legacy function - kept for compatibility"""
    return create_enhanced_header_styles(row, 0)

def create_data_row_styles(row, today_date):
    """Create styles for data rows"""
    styles = []
    
    # Get date for this row
    date_str = row.get("Date", "")
    date_obj = None
    try:
        if date_str and str(date_str) != "":
            date_obj = pd.to_datetime(date_str)
    except:
        pass

    for col_name, cell_value in row.items():
        style = ""
        
        try:
            # Apply date-based styling first
            if date_obj is not None and not pd.isna(date_obj):
                style = get_date_based_style(date_obj, today_date)
            
            # Apply visit-specific styling if no date styling
            if style == "" and col_name not in ["Date", "Day"] and str(cell_value) != "":
                style = get_visit_based_style(str(cell_value))
        except Exception as e:
            # If there's any error with styling, just use empty style
            style = ""
        
        styles.append(style)
    
    return styles

def get_date_based_style(date_obj, today_date):
    """Get styling based on date characteristics"""
    if date_obj.date() == today_date.date():
        return 'background-color: #dc2626; color: white; font-weight: bold;'
    elif date_obj.month == 3 and date_obj.day == 31:
        return 'background-color: #1e40af; color: white; font-weight: bold;'
    elif date_obj == date_obj + pd.offsets.MonthEnd(0):
        return 'background-color: #60a5fa; color: white; font-weight: normal;'
    elif date_obj.weekday() in (5, 6):
        return 'background-color: #e5e7eb;'
    return ""

def get_visit_based_style(cell_str):
    """Get styling based on visit type - simplified without tolerance windows"""
    if '✅' in cell_str or ('Visit' in cell_str and any(symbol in cell_str for symbol in ["✅"])):
        return 'background-color: #d4edda; color: #155724; font-weight: bold;'
    elif '⚠️ Screen Fail' in cell_str or 'Screen Fail' in cell_str:
        return 'background-color: #f8d7da; color: #721c24; font-weight: bold; border: 2px solid #dc3545;'
    elif '⚠️ Withdrawn' in cell_str or 'Withdrawn' in cell_str:
        return 'background-color: #fff3cd; color: #856404; font-weight: bold; border: 2px solid #ffc107;'
    elif '📋' in cell_str and '(Predicted)' in cell_str:
        # Predicted visits (no actual visit yet)
        return 'background-color: #e2e3e5; color: #383d41; font-weight: normal;'
    elif "Visit " in cell_str and not any(symbol in cell_str for symbol in ["✅", "⚠️", "📋"]):
        return 'background-color: #e2e3e5; color: #383d41; font-weight: normal;'
    return ""

def create_fy_highlighting_function():
    """Create function for highlighting financial year rows"""
    def highlight_fy_rows(row):
        if row.get('Type') == 'Financial Year':
            return ['background-color: #e6f3ff; font-weight: bold;'] * len(row)
        else:
            return [''] * len(row)
    return highlight_fy_rows

def format_dataframe_index_as_string(df, index_col=None):
    """Format dataframe index as string for display"""
    df_display = df.copy()
    if index_col:
        df_display[index_col] = df_display[index_col].astype(str)
    else:
        df_display.index = df_display.index.astype(str)
    return df_display

def format_visit_display_string(visit_name, is_actual=False, is_screen_fail=False, is_withdrawn=False, is_out_of_protocol=False):
    """Format visit display string with appropriate emoji and status - simplified without tolerance windows"""    
    if is_screen_fail:
        return f"⚠️ Screen Fail {visit_name}"
    elif is_withdrawn:
        return f"⚠️ Withdrawn {visit_name}"
    elif visit_name.lower() in ["randomisation", "randomization"] and is_actual:
        # Randomisation is always just completed
        return f"✅ {visit_name}"
    elif is_actual:
        # All actual visits are just marked as completed (no tolerance checking)
        return f"✅ {visit_name}"
    else:
        return visit_name

def format_period_display(period_value, period_type):
    """Format time period for display"""
    if period_type == 'month':
        return str(period_value)
    elif period_type == 'quarter':
        return period_value
    elif period_type == 'financial_year':
        return f"FY {period_value}"
    else:
        return str(period_value)

def create_metric_display_value(value, format_type='number'):
    """Create formatted value for metric display"""
    if format_type == 'currency':
        return format_currency(value)
    elif format_type == 'percentage':
        return format_percentage(value)
    elif format_type == 'integer':
        return f"{int(value):,}" if pd.notna(value) else "0"
    else:
        return str(value) if pd.notna(value) else "0"

def apply_conditional_formatting(df, condition_column, condition_value, style_dict):
    """Apply conditional formatting to entire dataframe rows"""
    def highlight_rows(row):
        if row.get(condition_column) == condition_value:
            return [f'background-color: {style_dict.get("bg_color", "#e6f3ff")}; font-weight: {style_dict.get("weight", "bold")};'] * len(row)
        return [''] * len(row)
    return df.style.apply(highlight_rows, axis=1)

def clean_numeric_for_display(value, default_display="0"):
    """Clean numeric values for display, handling NaN and zero cases"""
    if pd.isna(value):
        return default_display
    elif isinstance(value, (int, float)):
        return str(int(value)) if value == int(value) else str(value)
    else:
        return str(value)

def format_table_headers(headers, title_case=True):
    """Format table headers consistently"""
    if title_case:
        return [header.replace('_', ' ').title() for header in headers]
    return [header.replace('_', ' ') for header in headers]
