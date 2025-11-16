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
        export_df["Notes"] = ""
        export_df["ExtrasPerformed"] = ""

        export_df = export_df.reindex(columns=EXPORT_COLUMNS)
        export_df.to_excel(writer, sheet_name="OverdueVisits", index=False)

        workbook = writer.book
        worksheet = writer.sheets["OverdueVisits"]

        header_format = None
        if XLSX_ENGINE == "xlsxwriter":
            header_format = workbook.add_format({'bold': True, 'bg_color': '#e0f2fe'})
            date_format = workbook.add_format({'num_format': 'dd/mm/yyyy'})
        for col_num, value in enumerate(EXPORT_COLUMNS):
            if header_format is not None:
                worksheet.write(0, col_num, value, header_format)
            else:
                worksheet.write(0, col_num, value)

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
            "Notes": 30,
            "ExtrasPerformed": 25
        }
        for idx, column in enumerate(EXPORT_COLUMNS):
            width = col_widths.get(column, 15)
            worksheet.set_column(idx, idx, width)

        actual_date_col = EXPORT_COLUMNS.index("ActualDate")
        outcome_col = EXPORT_COLUMNS.index("Outcome")
        extras_col = EXPORT_COLUMNS.index("ExtrasPerformed")

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
        if XLSX_ENGINE == "xlsxwriter":
            worksheet.set_column(actual_date_col, actual_date_col, col_widths["ActualDate"], date_format)
        else:
            worksheet.set_column(actual_date_col, actual_date_col, col_widths["ActualDate"])

        outcome_options = ['Happened', 'Did not happen', 'Cancelled', 'Unknown']
        worksheet.data_validation(
            1, outcome_col,
            len(export_df) + 1, outcome_col,
            {
                'validate': 'list',
                'source': outcome_options
            }
        )

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
        elif extras_by_study:
            for row_idx, row in export_df.iterrows():
                study = row['Study']
                extras = extras_by_study.get(study, [])
                if extras:
                    worksheet.data_validation(
                        row_idx + 1, extras_col,
                        row_idx + 1, extras_col,
                        {
                            'validate': 'list',
                            'source': extras
                        }
                    )

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

