import io
from datetime import date
from typing import Tuple, Dict, Any, List

import pandas as pd

from helpers import log_activity


def _normalize_visit_name(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    # Remove leading emoji markers like "✅ " or "⚠️ "
    if len(text) > 2 and text[1] == " ":
        text = text[2:]
    return text.strip()


def _infer_event_type(visit_name: str) -> str:
    name = str(visit_name).lower()
    if "siv" in name or "site initiation" in name:
        return "siv"
    if "monitor" in name or "monitoring" in name:
        return "monitor"
    return "event"


def _safe_to_datetime(series: pd.Series) -> pd.Series:
    if series is None:
        return pd.Series(dtype="datetime64[ns]")
    return pd.to_datetime(series, dayfirst=True, errors="coerce")


def build_overdue_predicted_export(
    visits_df: pd.DataFrame,
    trials_df: pd.DataFrame,
    calendar_start
) -> Tuple[io.BytesIO, str]:
    """
    Build Excel export for overdue predicted visits (scheduled but not yet completed).

    Filters:
    - Only PREDICTED visits (IsActual != True, IsProposed != True)
    - Only dates BEFORE today (overdue)
    - Only patient visits (not study events like SIV, monitoring)
    - Excludes placeholder visits ("-", "+")

    Returns (BytesIO or None, message).
    """
    if visits_df is None or visits_df.empty:
        return None, "No visits available for overdue export."

    df = visits_df.copy()
    if "Date" not in df.columns:
        return None, "Visits data is missing Date column."

    initial_count = len(df)

    # Parse dates
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"])

    # CRITICAL: Filter for predicted visits only (not actual, not proposed, not study events)
    # Exclude actual visits (visits that have already occurred and been recorded)
    if "IsActual" in df.columns:
        df = df[df["IsActual"] != True]

    # Exclude proposed visits (future visits beyond schedule window)
    if "IsProposed" in df.columns:
        df = df[df["IsProposed"] != True]

    # Exclude study events (SIV, monitoring, closeout, etc.)
    if "IsStudyEvent" in df.columns:
        df = df[df["IsStudyEvent"] != True]

    # Alternative: Filter by VisitType if IsStudyEvent not available
    if "VisitType" in df.columns:
        # Only include 'patient' and 'extra' visits, exclude 'siv', 'monitor', 'closeout', etc.
        df = df[df["VisitType"].isin(["patient", "extra"])]

    # Exclude placeholder visits ("-" and "+")
    if "Visit" in df.columns:
        df = df[~df["Visit"].isin(["-", "+"])]

    # CRITICAL: Exclude visits for inactive patients (withdrawn, screen failed, deceased, completed)
    # These patients shouldn't have "overdue" visits since they're no longer in the study
    if "PatientStatus" in df.columns:
        # Only include active patients (screening, randomized, lost_to_followup)
        # Exclude: withdrawn, screen_failed, deceased, completed, dna_screening
        active_statuses = ["screening", "randomized", "lost_to_followup"]
        df = df[df["PatientStatus"].isin(active_statuses)]

    # CRITICAL: Only include visits BEFORE today (overdue)
    today = pd.Timestamp(date.today())
    df = df[df["Date"] < today]

    # Apply calendar start filter if provided
    if calendar_start is not None:
        df = df[df["Date"] >= pd.to_datetime(calendar_start)]

    # Log filtering results for debugging
    from helpers import log_activity
    log_activity(f"Overdue predicted visits export: Started with {initial_count} total visits, filtered to {len(df)} overdue predicted visits", level='info')

    if df.empty:
        return None, "No overdue predicted visits found."

    export_df = pd.DataFrame({
        "PatientID": df.get("PatientID", ""),
        "Study": df.get("Study", ""),
        "VisitName": df.get("VisitName", df.get("Visit", "")).apply(_normalize_visit_name),
        "ScheduledDate": df["Date"].dt.strftime("%d/%m/%Y"),
        "SiteofVisit": df.get("SiteofVisit", ""),
        "ContractSite": df.get("ContractSite", ""),
        "PatientOrigin": df.get("PatientOrigin", ""),
        "VisitType": df.get("VisitType", "patient"),
        "ActualDate": "",
        "Outcome": "",
        "Notes": ""
    })

    export_df = export_df.sort_values(["Study", "ScheduledDate", "PatientID"]).reset_index(drop=True)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        export_df.to_excel(writer, sheet_name="OverduePredicted", index=False)

    output.seek(0)
    return output, f"Prepared {len(export_df)} overdue predicted visit(s)."


def parse_bulk_upload(
    uploaded_file,
    visits_df: pd.DataFrame,
    trials_df: pd.DataFrame,
    calendar_start
) -> Dict[str, Any]:
    """
    Parse completed overdue visit workbook.
    Returns dict with keys: errors, warnings, records.
    """
    errors: List[str] = []
    warnings: List[str] = []
    records: List[Dict[str, Any]] = []

    try:
        df = pd.read_excel(uploaded_file)
    except Exception as e:
        return {"errors": [f"Failed to read Excel file: {e}"], "warnings": [], "records": []}

    if df is None or df.empty:
        return {"errors": ["Uploaded file has no rows."], "warnings": [], "records": []}

    required_cols = ["PatientID", "Study", "VisitName"]
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        return {"errors": [f"Missing required columns: {', '.join(missing)}"], "warnings": [], "records": []}

    actual_date_col = "ActualDate" if "ActualDate" in df.columns else None
    if actual_date_col is None:
        errors.append("Missing ActualDate column. Add dates to import completed visits.")
        return {"errors": errors, "warnings": warnings, "records": records}

    df["ActualDate"] = _safe_to_datetime(df[actual_date_col])

    for row in df.itertuples(index=False):
        patient_id = getattr(row, "PatientID", None)
        study = getattr(row, "Study", None)
        visit_name = getattr(row, "VisitName", None)
        actual_date = getattr(row, "ActualDate", None)
        visit_type = getattr(row, "VisitType", "patient")
        outcome = getattr(row, "Outcome", "")
        notes = getattr(row, "Notes", "")

        if pd.isna(actual_date):
            warnings.append(f"Skipped row with missing ActualDate: {patient_id} / {study} / {visit_name}")
            continue

        note_parts = []
        if outcome and str(outcome).strip():
            note_parts.append(f"Outcome: {outcome}")
        if notes and str(notes).strip():
            note_parts.append(str(notes).strip())

        records.append({
            "PatientID": patient_id,
            "Study": study,
            "VisitName": _normalize_visit_name(visit_name),
            "ActualDate": actual_date,
            "VisitType": str(visit_type).strip().lower() if visit_type else "patient",
            "Notes": " | ".join(note_parts) if note_parts else ""
        })

    return {"errors": errors, "warnings": warnings, "records": records}


def build_proposed_visits_export(actual_visits_df: pd.DataFrame) -> Tuple[io.BytesIO, str]:
    """
    Build Excel export for proposed visits/events.
    """
    if actual_visits_df is None or actual_visits_df.empty:
        return None, "No actual visits available."

    df = actual_visits_df.copy()

    proposed_mask = pd.Series([False] * len(df), index=df.index)
    if "VisitType" in df.columns:
        proposed_mask = df["VisitType"].astype(str).str.lower().isin(["patient_proposed", "event_proposed"])
    if "IsProposed" in df.columns:
        proposed_mask = proposed_mask | (df["IsProposed"] == True)

    df = df[proposed_mask]
    if df.empty:
        return None, "No proposed visits found."

    df["ActualDate"] = _safe_to_datetime(df.get("ActualDate"))

    export_df = pd.DataFrame({
        "PatientID": df.get("PatientID", ""),
        "Study": df.get("Study", ""),
        "VisitName": df.get("VisitName", ""),
        "ActualDate": df["ActualDate"].dt.strftime("%d/%m/%Y"),
        "ProposedType": df.get("VisitType", ""),
        "Status": "",
        "Notes": df.get("Notes", "")
    })

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        export_df.to_excel(writer, sheet_name="ProposedVisits", index=False)

    output.seek(0)
    return output, f"Prepared {len(export_df)} proposed visit(s)."


def parse_proposed_confirmation_upload(uploaded_file, actual_visits_df: pd.DataFrame) -> Dict[str, Any]:
    """
    Parse proposed visits confirmation file.
    Returns dict with keys: errors, warnings, records.
    """
    errors: List[str] = []
    warnings: List[str] = []
    records: List[Dict[str, Any]] = []

    try:
        df = pd.read_excel(uploaded_file)
    except Exception as e:
        return {"errors": [f"Failed to read Excel file: {e}"], "warnings": [], "records": []}

    if df is None or df.empty:
        return {"errors": ["Uploaded file has no rows."], "warnings": [], "records": []}

    required_cols = ["PatientID", "Study", "VisitName", "ActualDate", "Status"]
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        return {"errors": [f"Missing required columns: {', '.join(missing)}"], "warnings": [], "records": []}

    df["ActualDate"] = _safe_to_datetime(df["ActualDate"])

    for row in df.itertuples(index=False):
        status = str(getattr(row, "Status", "")).strip().lower()
        if status != "confirmed":
            continue

        patient_id = getattr(row, "PatientID", None)
        study = getattr(row, "Study", None)
        visit_name = getattr(row, "VisitName", None)
        actual_date = getattr(row, "ActualDate", None)
        proposed_type = getattr(row, "ProposedType", getattr(row, "VisitType", ""))
        notes = getattr(row, "Notes", "")

        if pd.isna(actual_date):
            warnings.append(f"Confirmed row missing ActualDate: {patient_id} / {study} / {visit_name}")
            continue

        proposed_type = str(proposed_type).strip().lower()
        if proposed_type.endswith("_proposed"):
            proposed_type = proposed_type.replace("_proposed", "")

        if proposed_type in ["event", "event_proposed"]:
            visit_type = _infer_event_type(visit_name)
        elif proposed_type:
            visit_type = proposed_type
        else:
            visit_type = "patient"

        records.append({
            "PatientID": patient_id,
            "Study": study,
            "VisitName": _normalize_visit_name(visit_name),
            "ActualDate": actual_date,
            "VisitType": visit_type,
            "Notes": str(notes).strip() if notes else ""
        })

    return {"errors": errors, "warnings": warnings, "records": records}
