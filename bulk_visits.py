from datetime import date
from typing import List, Dict, Any, Tuple
import io
import datetime
import pandas as pd
from helpers import get_current_financial_year_boundaries

try:
    import xlsxwriter  # noqa: F401
    XLSX_ENGINE = "xlsxwriter"
except ImportError:
    XLSX_ENGINE = "openpyxl"

EXPORT_COLUMNS = [
    "PatientID",
    "Study",
    "VisitName",
    "VisitDay",
    "ScheduledDate",
    "SiteofVisit",
    "VisitType",
    "ActualDate",
    "Outcome",
    "IsWithdrawn",
    "IsDied",
    "Notes",
    "ExtrasPerformed"
]


def _normalise_key(patient_id: Any, study: Any) -> Tuple[str, str]:
    return (str(patient_id).strip(), str(study).strip())


def _filter_overdue_predicted(visits_df: pd.DataFrame, start_date=None) -> pd.DataFrame:
    if visits_df is None or visits_df.empty:
        return pd.DataFrame()

    df_all = visits_df.copy()
    if 'Date' not in df_all.columns:
        return pd.DataFrame()

    df_all['Date'] = pd.to_datetime(df_all['Date'], errors='coerce')
    df_all = df_all[df_all['Date'].notna()]

    screen_fail_map: Dict[Tuple[str, str], pd.Timestamp] = {}
    if 'IsScreenFail' in df_all.columns:
        screen_fail_df = df_all[df_all['IsScreenFail'].astype(bool)].copy()
        if not screen_fail_df.empty:
            screen_fail_df['PatientID'] = screen_fail_df['PatientID'].astype(str).str.strip()
            screen_fail_df['Study'] = screen_fail_df['Study'].astype(str).str.strip()
            screen_fail_dates = screen_fail_df.groupby(['PatientID', 'Study'])['Date'].min()
            screen_fail_map = {
                (pid, study): dt for (pid, study), dt in screen_fail_dates.items() if pd.notna(dt)
            }

    if start_date is None:
        start_date = get_current_financial_year_boundaries()[0]
    else:
        start_date = pd.Timestamp(start_date)

    today = pd.Timestamp(date.today())

    df = df_all[
        (~df_all.get('IsActual', False)) &
        (df_all['Date'] <= today) &
        (df_all['Date'] >= start_date)
    ].copy()

    if df.empty:
        return pd.DataFrame()

    if 'Visit' in df.columns:
        df = df[~df['Visit'].isin(['-', '+'])]
    df = df[df.get('VisitDay', 0) != 0]

    if df.empty:
        return pd.DataFrame()

    df['VisitType'] = df.get('VisitType', 'patient').astype(str).str.strip().str.lower()
    df.loc[df['VisitType'].isin(['', 'nan', 'none', 'null']), 'VisitType'] = 'patient'

    if screen_fail_map:
        df = df[df.apply(
            lambda row: row['Date'] < screen_fail_map.get(_normalise_key(row['PatientID'], row['Study']), pd.Timestamp.max),
            axis=1
        )]

    if df.empty:
        return pd.DataFrame()

    df = df[[
        'PatientID', 'Study', 'VisitName', 'VisitDay', 'Date', 'SiteofVisit',
        'Payment', 'VisitType'
    ]].copy()

    return df


def build_overdue_predicted_export(visits_df: pd.DataFrame, trials_df: pd.DataFrame, start_date=None) -> Tuple[io.BytesIO, str]:
    filtered = _filter_overdue_predicted(visits_df, start_date)

    if filtered.empty:
        return None, "No overdue predicted visits found."

    filtered = filtered.sort_values(['Study', 'PatientID', 'VisitName']).reset_index(drop=True)
    filtered['ScheduledDate'] = filtered['Date'].dt.strftime('%Y-%m-%d')

    extras_by_study: Dict[str, List[str]] = {}
    if trials_df is not None and not trials_df.empty:
        extras_lookup = trials_df[
            trials_df.get('VisitType', '').astype(str).str.lower() == 'extra'
        ].copy()
        if not extras_lookup.empty:
            extras_lookup['VisitName'] = extras_lookup['VisitName'].astype(str).str.strip()
            extras_group = extras_lookup.groupby('Study')['VisitName'].apply(list)
            extras_by_study = {str(k).strip(): sorted(set(v)) for k, v in extras_group.items() if v}

    output = io.BytesIO()

    with pd.ExcelWriter(output, engine=XLSX_ENGINE) as writer:
        scheduled_column = pd.to_datetime(filtered['Date']).dt.strftime('%d/%m/%Y')

        export_df = pd.DataFrame({
            "PatientID": filtered['PatientID'].astype(str).str.strip(),
            "Study": filtered['Study'].astype(str).str.strip(),
            "VisitName": filtered['VisitName'].astype(str).str.strip(),
            "VisitDay": filtered['VisitDay'],
            "ScheduledDate": scheduled_column,
            "SiteofVisit": filtered.get('SiteofVisit', ''),
            "VisitType": filtered.get('VisitType', '')
        })

        export_df["ActualDate"] = pd.NaT
        export_df["Outcome"] = ""
        export_df["IsWithdrawn"] = ""
        export_df["IsDied"] = ""
        export_df["Notes"] = ""
        export_df["ExtrasPerformed"] = ""

        export_df = export_df.reindex(columns=EXPORT_COLUMNS)
        export_df.to_excel(writer, sheet_name="OverdueVisits", index=False)

        workbook = writer.book
        worksheet = writer.sheets["OverdueVisits"]

        actual_date_col = EXPORT_COLUMNS.index("ActualDate")
        outcome_col = EXPORT_COLUMNS.index("Outcome")
        extras_col = EXPORT_COLUMNS.index("ExtrasPerformed")

        if XLSX_ENGINE == "xlsxwriter":
            header_format = workbook.add_format({'bold': True, 'bg_color': '#e0f2fe'})
            date_format = workbook.add_format({'num_format': 'dd/mm/yyyy'})
            
            # Write header with formatting
            for col_num, value in enumerate(EXPORT_COLUMNS):
                worksheet.write(0, col_num, value, header_format)

            col_widths = {
                "PatientID": 15,
                "Study": 20,
                "VisitName": 25,
                "VisitDay": 10,
                "ScheduledDate": 15,
                "SiteofVisit": 15,
                "VisitType": 12,
                "ActualDate": 15,
                "Outcome": 18,
                "IsWithdrawn": 14,
                "IsDied": 14,
                "Notes": 30,
                "ExtrasPerformed": 25
            }
            for idx, column in enumerate(EXPORT_COLUMNS):
                width = col_widths.get(column, 15)
                worksheet.set_column(idx, idx, width)

            worksheet.data_validation(
                1, actual_date_col,
                len(export_df) + 1, actual_date_col,
                {
                    'validate': 'date',
                    'criteria': 'between',
                    'minimum': datetime.date(2000, 1, 1),
                    'maximum': datetime.date(2100, 12, 31),
                    'error_title': 'Invalid Date',
                    'error_message': 'Enter a valid date (DD/MM/YYYY).'
                }
            )

            worksheet.set_column(EXPORT_COLUMNS.index("ScheduledDate"), EXPORT_COLUMNS.index("ScheduledDate"), col_widths["ScheduledDate"])
            worksheet.set_column(actual_date_col, actual_date_col, col_widths["ActualDate"], date_format)

            outcome_options = ['Happened', 'Did not happen', 'Cancelled', 'Unknown']
            worksheet.data_validation(
                1, outcome_col,
                len(export_df) + 1, outcome_col,
                {
                    'validate': 'list',
                    'source': outcome_options
                }
            )
        else:
            # openpyxl: Set column widths
            from openpyxl.styles import Font, PatternFill
            from openpyxl.utils import get_column_letter
            
            # Format header row
            header_fill = PatternFill(start_color='E0F2FE', end_color='E0F2FE', fill_type='solid')
            header_font = Font(bold=True)
            for col_num in range(1, len(EXPORT_COLUMNS) + 1):
                cell = worksheet.cell(row=1, column=col_num)
                cell.fill = header_fill
                cell.font = header_font
            
            col_widths = {
                "PatientID": 15,
                "Study": 20,
                "VisitName": 25,
                "VisitDay": 10,
                "ScheduledDate": 15,
                "SiteofVisit": 15,
                "VisitType": 12,
                "ActualDate": 15,
                "Outcome": 18,
                "IsWithdrawn": 14,
                "IsDied": 14,
                "Notes": 30,
                "ExtrasPerformed": 25
            }
            for idx, column in enumerate(EXPORT_COLUMNS):
                width = col_widths.get(column, 15)
                col_letter = get_column_letter(idx + 1)
                worksheet.column_dimensions[col_letter].width = width

            # Data validation for ActualDate
            from openpyxl.worksheet.datavalidation import DataValidation
            date_validation = DataValidation(
                type="date",
                operator="between",
                formula1=datetime.date(2000, 1, 1),
                formula2=datetime.date(2100, 12, 31),
                error="Enter a valid date (DD/MM/YYYY).",
                errorTitle="Invalid Date"
            )
            date_range = f"{get_column_letter(actual_date_col + 1)}2:{get_column_letter(actual_date_col + 1)}{len(export_df) + 1}"
            date_validation.add(date_range)
            worksheet.add_data_validation(date_validation)

            # Data validation for Outcome
            outcome_options = ['Happened', 'Did not happen', 'Cancelled', 'Unknown']
            outcome_validation = DataValidation(
                type="list",
                formula1=f'"{",".join(outcome_options)}"',
                allow_blank=True
            )
            outcome_range = f"{get_column_letter(outcome_col + 1)}2:{get_column_letter(outcome_col + 1)}{len(export_df) + 1}"
            outcome_validation.add(outcome_range)
            worksheet.add_data_validation(outcome_validation)

        if extras_by_study and XLSX_ENGINE == "xlsxwriter":
            helper = workbook.add_worksheet("ExtraOptions")
            helper.hide()
            helper.write(0, 0, "Study")
            helper.write(0, 1, "Extras")
            helper_row = 1
            for study_name, extras in extras_by_study.items():
                helper.write(helper_row, 0, study_name)
                helper.write(helper_row, 1, ",".join(extras))
                helper_row += 1

            for row_idx, row in export_df.iterrows():
                study = row['Study']
                extras = extras_by_study.get(study, [])
                if extras:
                    worksheet.data_validation(
                        row_idx + 1, extras_col,
                        row_idx + 1, extras_col,
                        {
                            'validate': 'list',
                            'source': extras,
                            'error_title': 'Invalid Extra',
                            'error_message': f"Choose an extra defined for study {study}."
                        }
                    )
        elif extras_by_study and XLSX_ENGINE == "openpyxl":
            # For openpyxl, create helper sheet and use it for data validation
            from openpyxl.utils import get_column_letter
            helper = workbook.create_sheet("ExtraOptions")
            helper.sheet_state = 'hidden'
            helper.cell(row=1, column=1, value="Study")
            helper.cell(row=1, column=2, value="Extras")
            helper_row = 2
            for study_name, extras in extras_by_study.items():
                helper.cell(row=helper_row, column=1, value=study_name)
                helper.cell(row=helper_row, column=2, value=",".join(extras))
                helper_row += 1
            
            # Add data validation for extras per row
            from openpyxl.worksheet.datavalidation import DataValidation
            for row_idx, row in export_df.iterrows():
                study = row['Study']
                extras = extras_by_study.get(study, [])
                if extras:
                    extras_str = ",".join(extras)
                    extras_validation = DataValidation(
                        type="list",
                        formula1=f'"{extras_str}"',
                        allow_blank=True
                    )
                    cell_ref = f"{get_column_letter(extras_col + 1)}{row_idx + 2}"
                    extras_validation.add(cell_ref)
                    worksheet.add_data_validation(extras_validation)

    output.seek(0)
    return output, ""


def parse_bulk_upload(uploaded_file, visits_df: pd.DataFrame, trials_df: pd.DataFrame, start_date=None) -> Dict[str, Any]:
    try:
        suffix = uploaded_file.name.lower()
        if suffix.endswith('.xlsx') or suffix.endswith('.xls'):
            uploaded = pd.read_excel(uploaded_file)
        else:
            uploaded = pd.read_csv(uploaded_file)
    except Exception as e:
        return {"errors": [f"Failed to read file: {e}"], "records": [], "warnings": []}

    def _truthy(val) -> bool:
        if pd.isna(val):
            return False
        s = str(val).strip().lower()
        return s in {"true", "yes", "y", "1", "withdrawn"}

    required_columns = {
        "PatientID", "Study", "VisitName", "ScheduledDate",
        "ActualDate", "Outcome", "ExtrasPerformed", "Notes"
    }
    missing = required_columns - set(uploaded.columns)
    if missing:
        return {"errors": [f"Missing required columns: {', '.join(sorted(missing))}"], "records": [], "warnings": []}

    predicted_df = _filter_overdue_predicted(visits_df, start_date)
    warnings: List[str] = []
    records: List[Dict[str, Any]] = []

    if predicted_df.empty:
        warnings.append("No overdue predicted visits found. Uploaded rows may be outdated.")

    filtered_df = predicted_df.copy()
    filtered_df['ScheduledDate'] = filtered_df['Date'].dt.strftime('%Y-%m-%d')
    filtered_df['ScheduledDateNormalized'] = filtered_df['ScheduledDate']
    filtered_df['key'] = (
        filtered_df['PatientID'].astype(str).str.strip() + "|" +
        filtered_df['Study'].astype(str).str.strip() + "|" +
        filtered_df['VisitName'].astype(str).str.strip() + "|" +
        filtered_df['ScheduledDateNormalized']
    )
    predicted_indexed = filtered_df.set_index('key')

    extras_lookup = pd.DataFrame()
    if trials_df is not None and not trials_df.empty:
        extras_lookup = trials_df[
            trials_df.get('VisitType', '').astype(str).str.lower() == 'extra'
        ].copy()
        extras_lookup['VisitName'] = extras_lookup['VisitName'].astype(str).str.strip()

    outcome_negative = {'no', 'did not happen', 'cancelled', 'canceled', 'missed', 'n', 'false', 'f', '0'}
    used_keys = set()

    for row in uploaded.itertuples(index=False):
        patient_id = str(getattr(row, 'PatientID', '')).strip()
        study = str(getattr(row, 'Study', '')).strip()
        visit_name = str(getattr(row, 'VisitName', '')).strip()
        scheduled_raw = getattr(row, 'ScheduledDate', '')
        if pd.isna(scheduled_raw):
            scheduled_date = ''
        elif isinstance(scheduled_raw, (datetime.date, datetime.datetime)):
            scheduled_date = pd.to_datetime(scheduled_raw).strftime('%Y-%m-%d')
        else:
            scheduled_date = str(scheduled_raw).strip()
            try:
                scheduled_date = pd.to_datetime(scheduled_date, dayfirst=True).strftime('%Y-%m-%d')
            except Exception:
                scheduled_date = scheduled_date
        actual_value = getattr(row, 'ActualDate', '')
        actual_date_raw = '' if pd.isna(actual_value) else actual_value
        outcome_value = getattr(row, 'Outcome', '')
        outcome = '' if pd.isna(outcome_value) else str(outcome_value).strip().lower()
        notes_value = getattr(row, 'Notes', '')
        notes = '' if pd.isna(notes_value) else str(notes_value).strip()
        # Optional IsWithdrawn column
        is_withdrawn_val = getattr(row, 'IsWithdrawn', '') if hasattr(row, 'IsWithdrawn') else ''
        if _truthy(is_withdrawn_val) and 'Withdrawn' not in notes:
            notes = (notes + ('; ' if notes else '') + 'Withdrawn').strip()
        # Optional IsDied column
        is_died_val = getattr(row, 'IsDied', '') if hasattr(row, 'IsDied') else ''
        if _truthy(is_died_val) and 'Died' not in notes:
            notes = (notes + ('; ' if notes else '') + 'Died').strip()
        extras_value = getattr(row, 'ExtrasPerformed', '')
        extras_field = '' if pd.isna(extras_value) else str(extras_value).strip()

        if outcome in outcome_negative or actual_date_raw == '' or str(actual_date_raw).lower() in ('nan', 'nat'):
            continue

        parsed_date = None
        if isinstance(actual_date_raw, (datetime.date, datetime.datetime)):
            parsed_date = pd.Timestamp(actual_date_raw)
        elif isinstance(actual_date_raw, (int, float)):
            try:
                parsed_date = pd.to_datetime("1899-12-30") + pd.to_timedelta(float(actual_date_raw), unit='D')
            except Exception:
                parsed_date = None
        elif isinstance(actual_date_raw, str):
            try:
                parsed_date = pd.to_datetime(actual_date_raw, dayfirst=True, errors='raise')
            except Exception:
                try:
                    parsed_date = pd.to_datetime(actual_date_raw, errors='raise')
                except Exception:
                    parsed_date = None

        if parsed_date is None:
            warnings.append(f"Invalid ActualDate '{actual_date_raw}' for {patient_id}/{study}/{visit_name}. Skipping.")
            continue

        actual_date = pd.Timestamp(parsed_date).normalize()

        key = f"{patient_id}|{study}|{visit_name}|{scheduled_date}"
        if key in used_keys:
            warnings.append(f"Duplicate row for {patient_id}/{study}/{visit_name} on {scheduled_date}. Skipping.")
            continue

        if key not in predicted_indexed.index:
            warnings.append(f"Predicted visit not found or no longer due: {patient_id}/{study}/{visit_name} ({scheduled_date}). Skipping.")
            continue

        predicted_row = predicted_indexed.loc[key]
        visit_type = predicted_row.get('VisitType', 'patient')

        record = {
            'PatientID': patient_id,
            'Study': study,
            'VisitName': visit_name,
            'ActualDate': actual_date,
            'Notes': notes,
            'VisitType': visit_type or 'patient'
        }
        records.append(record)
        used_keys.add(key)

        if extras_field and extras_field.lower() not in ('nan', 'nat', 'none') and not extras_lookup.empty:
            extras_list = [item.strip() for item in extras_field.replace(';', ',').split(',') if item.strip()]
            for extra_name in extras_list:
                extra_match = extras_lookup[
                    (extras_lookup['Study'].astype(str).str.strip() == study) &
                    (extras_lookup['VisitName'].str.lower() == extra_name.lower())
                ]
                if extra_match.empty:
                    warnings.append(f"Extra '{extra_name}' not defined in trial schedule for study {study}. Skipping.")
                    continue
                extra_record = {
                    'PatientID': patient_id,
                    'Study': study,
                    'VisitName': extra_match.iloc[0]['VisitName'],
                    'ActualDate': actual_date,
                    'Notes': notes,
                    'VisitType': 'extra'
                }
                records.append(extra_record)

    return {"records": records, "warnings": warnings, "errors": []}


def build_proposed_visits_export(actual_visits_df: pd.DataFrame) -> Tuple[io.BytesIO, str]:
    """
    Export proposed visits and events for confirmation workflow.
    
    Args:
        actual_visits_df: DataFrame containing actual visits from database
        
    Returns:
        Tuple of (Excel file buffer, message string)
    """
    if actual_visits_df is None or actual_visits_df.empty:
        return None, "No visits found in database."
    
    # Filter for proposed visits/events
    proposed_mask = actual_visits_df.get('VisitType', '').astype(str).str.lower().isin(['patient_proposed', 'event_proposed'])
    proposed_df = actual_visits_df[proposed_mask].copy()
    
    if proposed_df.empty:
        return None, "No proposed visits or events found."
    
    # Prepare export data
    export_data = []
    for _, row in proposed_df.iterrows():
        # Normalize date
        actual_date = row.get('ActualDate', '')
        if pd.notna(actual_date):
            if isinstance(actual_date, str):
                date_obj = pd.to_datetime(actual_date, dayfirst=True)
            else:
                date_obj = pd.Timestamp(actual_date)
            formatted_date = date_obj.strftime('%d/%m/%Y')
        else:
            formatted_date = ''
        
        export_data.append({
            'PatientID': str(row.get('PatientID', '')),
            'Study': str(row.get('Study', '')),
            'VisitName': str(row.get('VisitName', '')),
            'ActualDate': formatted_date,
            'VisitType': str(row.get('VisitType', '')),
            'Notes': str(row.get('Notes', '')),
            'Status': 'Proposed'  # Default status
        })
    
    export_df = pd.DataFrame(export_data)
    export_df = export_df.sort_values(['Study', 'PatientID', 'ActualDate']).reset_index(drop=True)
    
    # Create Excel file
    output = io.BytesIO()
    
    with pd.ExcelWriter(output, engine=XLSX_ENGINE) as writer:
        export_df.to_excel(writer, sheet_name="ProposedVisits", index=False)
        
        workbook = writer.book
        worksheet = writer.sheets["ProposedVisits"]
        
        # Set column widths
        col_widths = {
            'PatientID': 20,
            'Study': 25,
            'VisitName': 25,
            'ActualDate': 15,
            'VisitType': 18,
            'Notes': 40,
            'Status': 15
        }
        
        status_col = export_df.columns.get_loc('Status')
        status_options = ['Proposed', 'Confirmed']
        
        if XLSX_ENGINE == "xlsxwriter":
            # Format headers
            header_format = workbook.add_format({'bold': True, 'bg_color': '#e0f2fe'})
            date_format = workbook.add_format({'num_format': 'dd/mm/yyyy'})
            
            # Write header with formatting
            for col_idx, col_name in enumerate(export_df.columns):
                worksheet.write(0, col_idx, col_name, header_format)
                width = col_widths.get(col_name, 15)
                worksheet.set_column(col_idx, col_idx, width)
            
            # Add data validation for Status column
            worksheet.data_validation(
                1, status_col,
                len(export_df) + 1, status_col,
                {
                    'validate': 'list',
                    'source': status_options,
                    'error_title': 'Invalid Status',
                    'error_message': 'Status must be either "Proposed" or "Confirmed".'
                }
            )
        else:
            # openpyxl: Format headers and set column widths
            from openpyxl.styles import Font, PatternFill
            from openpyxl.utils import get_column_letter
            
            header_fill = PatternFill(start_color='E0F2FE', end_color='E0F2FE', fill_type='solid')
            header_font = Font(bold=True)
            for col_idx, col_name in enumerate(export_df.columns):
                cell = worksheet.cell(row=1, column=col_idx + 1)
                cell.fill = header_fill
                cell.font = header_font
                width = col_widths.get(col_name, 15)
                col_letter = get_column_letter(col_idx + 1)
                worksheet.column_dimensions[col_letter].width = width
            
            # Add data validation for Status column
            from openpyxl.worksheet.datavalidation import DataValidation
            status_validation = DataValidation(
                type="list",
                formula1=f'"{",".join(status_options)}"',
                allow_blank=True,
                error="Status must be either \"Proposed\" or \"Confirmed\".",
                errorTitle="Invalid Status"
            )
            status_range = f"{get_column_letter(status_col + 1)}2:{get_column_letter(status_col + 1)}{len(export_df) + 1}"
            status_validation.add(status_range)
            worksheet.add_data_validation(status_validation)
        
        # Format date column if using xlsxwriter
        if XLSX_ENGINE == "xlsxwriter" and 'ActualDate' in export_df.columns:
            date_col = export_df.columns.get_loc('ActualDate')
            worksheet.set_column(date_col, date_col, col_widths['ActualDate'], date_format)
    
    output.seek(0)
    count = len(export_df)
    message = f"Exported {count} proposed visit(s)/event(s) for confirmation."
    return output, message


def parse_proposed_confirmation_upload(uploaded_file, actual_visits_df: pd.DataFrame) -> Dict[str, Any]:
    """
    Parse uploaded Excel file with proposed visit confirmations.
    
    Args:
        uploaded_file: Uploaded Excel file
        actual_visits_df: Current actual visits DataFrame from database
        
    Returns:
        Dict with 'records' (list of updates), 'warnings', 'errors'
    """
    try:
        suffix = uploaded_file.name.lower()
        if suffix.endswith('.xlsx') or suffix.endswith('.xls'):
            uploaded = pd.read_excel(uploaded_file)
        else:
            uploaded = pd.read_csv(uploaded_file)
    except Exception as e:
        return {"errors": [f"Failed to read file: {e}"], "records": [], "warnings": []}
    
    required_columns = {"PatientID", "Study", "VisitName", "ActualDate", "Status"}
    missing = required_columns - set(uploaded.columns)
    if missing:
        return {"errors": [f"Missing required columns: {', '.join(sorted(missing))}"], "records": [], "warnings": []}
    
    warnings: List[str] = []
    records: List[Dict[str, Any]] = []
    
    # Create lookup for existing proposed visits
    if actual_visits_df is None or actual_visits_df.empty:
        return {"errors": ["No visits found in database to update."], "records": [], "warnings": []}
    
    proposed_mask = actual_visits_df.get('VisitType', '').astype(str).str.lower().isin(['patient_proposed', 'event_proposed'])
    proposed_visits = actual_visits_df[proposed_mask].copy()
    
    if proposed_visits.empty:
        return {"errors": ["No proposed visits found in database to update."], "records": [], "warnings": []}
    
    # Normalize dates for matching
    proposed_visits['ActualDate_normalized'] = pd.to_datetime(proposed_visits['ActualDate'], dayfirst=True, errors='coerce').dt.date
    proposed_visits['key'] = (
        proposed_visits['PatientID'].astype(str).str.strip() + "|" +
        proposed_visits['Study'].astype(str).str.strip() + "|" +
        proposed_visits['VisitName'].astype(str).str.strip() + "|" +
        proposed_visits['ActualDate_normalized'].astype(str)
    )
    proposed_indexed = proposed_visits.set_index('key')
    
    used_keys = set()
    
    for row in uploaded.itertuples(index=False):
        patient_id = str(getattr(row, 'PatientID', '')).strip()
        study = str(getattr(row, 'Study', '')).strip()
        visit_name = str(getattr(row, 'VisitName', '')).strip()
        status = str(getattr(row, 'Status', '')).strip()
        
        # Parse date
        actual_date_raw = getattr(row, 'ActualDate', '')
        if pd.isna(actual_date_raw):
            warnings.append(f"Missing ActualDate for {patient_id}/{study}/{visit_name}. Skipping.")
            continue
        
        try:
            if isinstance(actual_date_raw, (datetime.date, datetime.datetime)):
                actual_date_obj = pd.Timestamp(actual_date_raw).date()
            elif isinstance(actual_date_raw, str):
                actual_date_obj = pd.to_datetime(actual_date_raw, dayfirst=True).date()
            else:
                actual_date_obj = pd.to_datetime(actual_date_raw).date()
        except Exception as e:
            warnings.append(f"Invalid ActualDate '{actual_date_raw}' for {patient_id}/{study}/{visit_name}: {e}. Skipping.")
            continue
        
        # Only process if Status is "Confirmed"
        if status.lower() != 'confirmed':
            continue
        
        # Create key for lookup
        key = f"{patient_id}|{study}|{visit_name}|{actual_date_obj}"
        
        if key in used_keys:
            warnings.append(f"Duplicate row for {patient_id}/{study}/{visit_name} on {actual_date_obj}. Skipping.")
            continue
        
        if key not in proposed_indexed.index:
            warnings.append(f"Proposed visit not found: {patient_id}/{study}/{visit_name} on {actual_date_obj}. Skipping.")
            continue
        
        proposed_row = proposed_indexed.loc[key]
        current_visit_type = str(proposed_row.get('VisitType', '')).lower()
        
        # Determine new VisitType based on current type
        if current_visit_type == 'patient_proposed':
            new_visit_type = 'patient'
        elif current_visit_type == 'event_proposed':
            # Determine underlying event type from VisitName
            visit_name_upper = visit_name.upper()
            if 'SIV' in visit_name_upper or visit_name_upper == 'SIV':
                new_visit_type = 'siv'
            elif 'MONITOR' in visit_name_upper:
                new_visit_type = 'monitor'
            else:
                new_visit_type = 'siv'  # Default
        else:
            warnings.append(f"Visit {patient_id}/{study}/{visit_name} is not a proposed visit. Skipping.")
            continue
        
        # Create update record
        record = {
            'PatientID': patient_id,
            'Study': study,
            'VisitName': visit_name,
            'ActualDate': actual_date_obj.strftime('%d/%m/%Y'),
            'VisitType': new_visit_type,
            'Notes': str(proposed_row.get('Notes', '')),
            'action': 'update'  # Mark as update
        }
        records.append(record)
        used_keys.add(key)
    
    return {"records": records, "warnings": warnings, "errors": []}

