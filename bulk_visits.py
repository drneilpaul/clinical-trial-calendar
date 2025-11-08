from datetime import date
from typing import List, Dict, Any
import pandas as pd
from helpers import get_current_financial_year_boundaries

EXPORT_COLUMNS = [
    "ExportGeneratedAt",
    "PatientID",
    "Study",
    "VisitName",
    "VisitDay",
    "ScheduledDate",
    "SiteofVisit",
    "Payment",
    "VisitType",
    "ActualDate",
    "Outcome",
    "Notes",
    "ExtrasPerformed"
]

def _filter_overdue_predicted(visits_df: pd.DataFrame, start_date=None) -> pd.DataFrame:
    if visits_df is None or visits_df.empty:
        return pd.DataFrame()

    df = visits_df.copy()

    if 'Date' not in df.columns:
        return pd.DataFrame()

    if not pd.api.types.is_datetime64_any_dtype(df['Date']):
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')

    today = pd.Timestamp(date.today())

    if start_date is None:
        start_date = get_current_financial_year_boundaries()[0]
    else:
        start_date = pd.Timestamp(start_date)

    df = df[
        (~df.get('IsActual', False)) &
        (df['Date'].notna()) &
        (df['Date'] <= today) &
        (df['Date'] >= start_date)
    ].copy()

    if df.empty:
        return pd.DataFrame()
    
    df = df[~df.get('Visit', '').isin(['-', '+'])]
    df = df[df.get('VisitDay', 0) != 0]

    if df.empty:
        return pd.DataFrame()

    df['VisitType'] = df.get('VisitType', 'patient').astype(str).str.strip().str.lower()
    df.loc[df['VisitType'].isin(['', 'nan', 'none', 'null']), 'VisitType'] = 'patient'

    df = df[[
        'PatientID', 'Study', 'VisitName', 'VisitDay', 'Date', 'SiteofVisit',
        'Payment', 'VisitType'
    ]].copy()

    return df


def build_overdue_predicted_export(visits_df: pd.DataFrame, start_date=None) -> pd.DataFrame:
    filtered = _filter_overdue_predicted(visits_df, start_date)

    if filtered.empty:
        return pd.DataFrame(columns=EXPORT_COLUMNS)

    export_generated_at = pd.Timestamp.utcnow().strftime('%Y-%m-%d %H:%M:%SZ')

    export_generated_at = pd.Timestamp.utcnow().strftime('%Y-%m-%d %H:%M:%SZ')

    result = pd.DataFrame({
        "ExportGeneratedAt": export_generated_at,
        "PatientID": filtered.get('PatientID', ''),
        "Study": filtered.get('Study', ''),
        "VisitName": filtered.get('VisitName', ''),
        "VisitDay": filtered.get('VisitDay', ''),
        "ScheduledDate": filtered['Date'].dt.strftime('%Y-%m-%d'),
        "SiteofVisit": filtered.get('SiteofVisit', ''),
        "Payment": filtered.get('Payment', 0),
        "VisitType": filtered.get('VisitType', '')
    })

    result["ActualDate"] = ""
    result["Outcome"] = ""
    result["Notes"] = ""
    result["ExtrasPerformed"] = ""

    result = result.reindex(columns=EXPORT_COLUMNS)
    result = result.sort_values(["ScheduledDate", "Study", "PatientID"]).reset_index(drop=True)

    return result


def parse_bulk_upload(csv_file, visits_df: pd.DataFrame, trials_df: pd.DataFrame, start_date=None) -> Dict[str, Any]:
    try:
        uploaded = pd.read_csv(csv_file)
    except Exception as e:
        return {"errors": [f"Failed to read CSV: {e}"], "records": [], "warnings": []}

    required_columns = {
        "PatientID", "Study", "VisitName", "ScheduledDate",
        "ActualDate", "Outcome", "ExtrasPerformed", "Notes"
    }
    missing_columns = required_columns - set(uploaded.columns)
    if missing_columns:
        return {"errors": [f"Missing required columns: {', '.join(sorted(missing_columns))}"], "records": [], "warnings": []}

    predicted_df = _filter_overdue_predicted(visits_df, start_date)
    warnings: List[str] = []
    records: List[Dict[str, Any]] = []

    if predicted_df.empty:
        warnings.append("No overdue predicted visits found. Uploaded rows may be outdated.")

    predicted_df = predicted_df.copy()
    predicted_df['ScheduledDate'] = predicted_df['Date'].dt.strftime('%Y-%m-%d')
    predicted_df['key'] = (
        predicted_df['PatientID'].astype(str).str.strip() + "|" +
        predicted_df['Study'].astype(str).str.strip() + "|" +
        predicted_df['VisitName'].astype(str).str.strip() + "|" +
        predicted_df['ScheduledDate']
    )
    predicted_df_indexed = predicted_df.set_index('key')

    if trials_df is not None and not trials_df.empty:
        extras_lookup = trials_df[
            trials_df.get('VisitType', '').astype(str).str.lower() == 'extra'
        ].copy()
        extras_lookup['VisitName'] = extras_lookup['VisitName'].astype(str).str.strip()
        extras_lookup = extras_lookup[['Study', 'VisitName']]
    else:
        extras_lookup = pd.DataFrame(columns=['Study', 'VisitName'])

    outcome_positive = {'happened', 'completed', 'yes', 'y', 'true', 't', '1', ''}
    outcome_negative = {'no', 'did not happen', 'cancelled', 'canceled', 'missed', 'n', 'false', 'f', '0'}

    used_keys = set()

    for row in uploaded.itertuples(index=False):
        patient_id = str(getattr(row, 'PatientID', '')).strip()
        study = str(getattr(row, 'Study', '')).strip()
        visit_name = str(getattr(row, 'VisitName', '')).strip()
        scheduled_date = str(getattr(row, 'ScheduledDate', '')).strip()
        actual_date_raw = str(getattr(row, 'ActualDate', '')).strip()
        outcome = str(getattr(row, 'Outcome', '')).strip().lower()
        notes = str(getattr(row, 'Notes', '')).strip()
        extras_field = str(getattr(row, 'ExtrasPerformed', '')).strip()

        if not patient_id or not study or not visit_name:
            warnings.append("Skipping row with missing PatientID/Study/VisitName.")
            continue

        if outcome in outcome_negative or not actual_date_raw:
            continue

        try:
            actual_date = pd.to_datetime(actual_date_raw, errors='raise')
        except Exception:
            warnings.append(f"Invalid ActualDate '{actual_date_raw}' for {patient_id}/{study}/{visit_name}. Skipping.")
            continue

        key = f"{patient_id}|{study}|{visit_name}|{scheduled_date}"
        if key in used_keys:
            warnings.append(f"Duplicate row for {patient_id}/{study}/{visit_name} on {scheduled_date}. Skipping.")
            continue

        if key not in predicted_df_indexed.index:
            warnings.append(f"Predicted visit not found or no longer due: {patient_id}/{study}/{visit_name} ({scheduled_date}). Skipping.")
            continue

        predicted_row = predicted_df_indexed.loc[key]
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

        if extras_field:
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

