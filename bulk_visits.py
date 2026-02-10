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

        # Add data validation dropdowns for Outcome column
        try:
            from openpyxl.worksheet.datavalidation import DataValidation
            workbook = writer.book
            worksheet = writer.sheets["OverduePredicted"]

            # Outcome dropdown options
            outcome_options = '"Completed,DNA,Withdrawn,ScreenFail,Deceased,Cancelled,Rescheduled"'
            outcome_validation = DataValidation(
                type="list",
                formula1=outcome_options,
                allow_blank=True,
                showErrorMessage=True,
                error="Please select a valid outcome from the dropdown",
                errorTitle="Invalid Outcome"
            )
            # Apply to Outcome column (column J, rows 2 onwards, assuming up to 1000 rows)
            outcome_col_idx = export_df.columns.get_loc("Outcome") + 1  # +1 because Excel is 1-indexed
            outcome_col_letter = chr(64 + outcome_col_idx)  # Convert to letter (A=65)
            outcome_validation.add(f"{outcome_col_letter}2:{outcome_col_letter}1000")
            worksheet.add_data_validation(outcome_validation)
        except Exception as e:
            log_activity(f"Could not add data validation dropdowns: {e}", level='warning')

        # Add instructions sheet
        instructions_data = {
            "Instructions": [
                "OVERDUE PREDICTED VISITS - BULK COMPLETION WORKFLOW",
                "",
                "This file contains visits that were scheduled to occur but have not been recorded yet.",
                "These are 'predicted' visits from the study schedule that are now overdue (past their scheduled date).",
                "",
                "WHAT ARE OVERDUE PREDICTED VISITS?",
                "• Visits that were scheduled before today",
                "• Have NOT been marked as completed in the system",
                "• Are for patients still active in the study",
                "• Occur AFTER the patient's most recent completed visit",
                "",
                "NOTE: Visits BEFORE a patient's most recent visit are considered 'missed' and not included.",
                "Example: If patient came for V5 but missed V3, only visits after V5 show as overdue.",
                "",
                "HOW TO USE THIS FILE:",
                "1. Review each overdue visit in the 'OverduePredicted' sheet",
                "2. Fill in the required fields based on what happened:",
                "",
                "⚠️ REQUIRED FIELDS (MUST BE FILLED IN):",
                "   • ActualDate = When the visit actually occurred (DD/MM/YYYY format)",
                "     ⚠️ CRITICAL: Rows WITHOUT an ActualDate will be SKIPPED during upload!",
                "     Example: 08/02/2026 for a visit that occurred on 8 February 2026",
                "   • Outcome = What happened at this visit (see options below)",
                "",
                "💡 TIP: The ActualDate column (Column I) is EMPTY by default - you MUST fill it in!",
                "         Only rows with ActualDate filled in will be imported.",
                "",
                "OUTCOME OPTIONS:",
                "   • Completed = Visit occurred and completed normally",
                "   • DNA = Patient Did Not Attend (no show for this visit)",
                "   • Withdrawn = Patient withdrew from study at/after this visit",
                "   • ScreenFail = Patient failed screening criteria",
                "   • Deceased = Patient passed away",
                "   • Cancelled = Visit cancelled (study ended, protocol change, etc.)",
                "   • Rescheduled = Visit moved to different date (enter new date in ActualDate)",
                "",
                "RESCHEDULING VISITS TO FUTURE DATES:",
                "If a visit needs to be rescheduled (not yet occurred):",
                "   • Fill in ActualDate with the NEW future date (e.g., 15/03/2026)",
                "   • The visit will be created as a PROPOSED visit (📅 emoji on calendar)",
                "   • It will appear in 'Proposed Visits Confirmation' for final confirmation",
                "   • Leave Outcome blank for rescheduled visits",
                "",
                "Example - Rescheduling:",
                "PatientID | Study | VisitName | ScheduledDate | ActualDate | Outcome | Notes",
                "P005      | BaxDuo| V6        | 10/02/2026    | 20/03/2026 |         | Rescheduled - patient on vacation",
                "",
                "PATIENT STATUS CONTEXT:",
                "The system tracks 8 patient statuses throughout their journey:",
                "   • screening = Patient in screening phase",
                "   • screen_failed = Patient failed screening criteria",
                "   • dna_screening = Patient did not attend screening",
                "   • randomized = Patient successfully randomized into study",
                "   • withdrawn = Patient withdrew from study",
                "   • deceased = Patient passed away",
                "   • completed = Patient completed all study visits",
                "   • lost_to_followup = Patient lost contact",
                "",
                "The Outcome you select will update the patient's status accordingly.",
                "",
                "NOTES FIELD (OPTIONAL):",
                "Use the Notes column to add any relevant information:",
                "   • Reason for DNA (sick, forgot, conflicting appointment)",
                "   • Reason for withdrawal",
                "   • Any adverse events or protocol deviations",
                "   • Reason for rescheduling",
                "",
                "AFTER COMPLETING THIS FILE:",
                "1. Save the file",
                "2. Go to Import/Export page in the application",
                "3. Upload this file in the 'Import Completed Visits' section",
                "4. The system will:",
                "   - Validate all entries",
                "   - Add completed visits to actual_visits table",
                "   - Update patient statuses based on Outcome",
                "   - Show any errors or warnings",
                "",
                "IMPORTANT NOTES:",
                "• Do NOT modify PatientID, Study, VisitName, or ScheduledDate columns",
                "• ⚠️ ActualDate format MUST be DD/MM/YYYY (e.g., 15/06/2026)",
                "• ⚠️ ActualDate MUST be filled in - blank rows will be skipped!",
                "• 📅 Future ActualDates (> today) will create PROPOSED visits, not completed visits",
                "• Outcome field is case-insensitive (completed = Completed)",
                "• For Withdrawn/Deceased outcomes, all future visits will be suppressed",
                "• SiteofVisit, ContractSite, PatientOrigin are auto-filled from schedule",
                "",
                "EXAMPLES:",
                "",
                "Example 1 - Completed Visit:",
                "PatientID | Study  | VisitName | ScheduledDate | ActualDate | Outcome   | Notes",
                "P001      | BaxDuo | V5        | 15/05/2026    | 15/05/2026 | Completed | On time",
                "",
                "Example 2 - DNA (Did Not Attend):",
                "PatientID | Study | VisitName | ScheduledDate | ActualDate | Outcome | Notes",
                "P002      | Zeus  | V3        | 20/05/2026    |            | DNA     | Patient forgot appointment",
                "",
                "Example 3 - Rescheduled:",
                "PatientID | Study  | VisitName | ScheduledDate | ActualDate | Outcome     | Notes",
                "P003      | FluSn  | V2        | 25/05/2026    | 02/06/2026 | Completed   | Rescheduled due to vacation",
                "",
                "Example 4 - Patient Withdrew:",
                "PatientID | Study  | VisitName | ScheduledDate | ActualDate | Outcome   | Notes",
                "P004      | BaxDuo | V4        | 30/05/2026    | 28/05/2026 | Withdrawn | Patient moved cities",
                "",
                "VALIDATION:",
                "The system will check for:",
                "   • Valid dates in DD/MM/YYYY format",
                "   • Recognized Outcome values",
                "   • Patient and Study exist in database",
                "   • No duplicate entries",
                "",
                "Any errors will be reported before saving to prevent data issues.",
            ]
        }
        instructions_df = pd.DataFrame(instructions_data)
        instructions_df.to_excel(writer, sheet_name="Instructions", index=False, header=False)

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
        # Enhanced error message with upload location guidance
        found_cols_str = ', '.join(df.columns.tolist())
        error_msg = (
            f"❌ Missing required columns: {', '.join(missing)}\n\n"
            f"This upload expects: PatientID, Study, VisitName, ActualDate, Outcome\n"
            f"Found columns in your file: {found_cols_str}\n\n"
            f"💡 Common issues:\n"
            f"   • Wrong upload location? Make sure you're uploading to 'Import Completed Visits'\n"
            f"   • Patients data → Use 'Patients CSV Upload' on Import/Export page\n"
            f"   • Trial schedules → Use 'Trial Schedules CSV Upload' on Import/Export page\n"
            f"   • Proposed visits → Use 'Proposed Visits Upload' section"
        )
        return {"errors": [error_msg], "warnings": [], "records": []}

    actual_date_col = "ActualDate" if "ActualDate" in df.columns else None
    if actual_date_col is None:
        error_msg = (
            f"❌ Missing ActualDate column\n\n"
            f"This upload requires an 'ActualDate' column for recording when visits occurred.\n\n"
            f"💡 If you're trying to upload:\n"
            f"   • Overdue Predicted Visits → This file should have ActualDate column\n"
            f"   • Different data (patients, trials) → Use the appropriate upload location"
        )
        errors.append(error_msg)
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
            warnings.append(
                f"⚠️ Skipped row with missing ActualDate: {patient_id} / {study} / {visit_name}\n"
                f"   💡 Tip: Fill in the ActualDate column (Column I) with the actual visit date in DD/MM/YYYY format"
            )
            continue

        # Track if this is a future date (will become proposed visit)
        from datetime import date as date_cls
        is_future = False
        if hasattr(actual_date, 'date'):
            try:
                is_future = actual_date.date() > date_cls.today()
            except (AttributeError, TypeError):
                pass

        note_parts = []
        # Only add outcome/notes if they're not empty or NaN
        if outcome and not pd.isna(outcome) and str(outcome).strip():
            note_parts.append(f"Outcome: {outcome}")
        if notes and not pd.isna(notes) and str(notes).strip():
            note_parts.append(str(notes).strip())

        # Add note for future dates to inform user
        if is_future:
            note_parts.append("📅 Rescheduled to future date (will be created as proposed visit)")

        records.append({
            "PatientID": patient_id,
            "Study": study,
            "VisitName": _normalize_visit_name(visit_name),
            "ActualDate": actual_date,
            "VisitType": str(visit_type).strip().lower() if visit_type else "patient",
            "Notes": " | ".join(note_parts) if note_parts else "",
            "IsFuture": is_future  # Flag for summary message
        })

    # Count future dates and add informational warning
    future_count = sum(1 for r in records if r.get('IsFuture', False))
    if future_count > 0:
        warnings.append(
            f"📅 {future_count} visit(s) have future dates and will be created as PROPOSED visits:\n"
            f"   • These will appear on the calendar with 📅 emoji\n"
            f"   • They can be confirmed later using 'Proposed Visits Confirmation' workflow\n"
            f"   • To record as completed visits instead, use past dates"
        )

    # Remove IsFuture flag before returning (not needed in database)
    for record in records:
        record.pop('IsFuture', None)

    # If no records were imported but we had warnings about missing ActualDate, provide helpful guidance
    if not records and warnings and any("missing ActualDate" in w for w in warnings):
        # Count how many rows had missing ActualDate
        skipped_count = sum(1 for w in warnings if "missing ActualDate" in w)

        helpful_msg = (
            f"⚠️ No visits imported - All {skipped_count} row(s) were skipped\n\n"
            f"All rows in your file are missing ActualDate values.\n\n"
            f"To import these visits:\n"
            f"1. Open the Excel file\n"
            f"2. Fill in the ActualDate column (Column I) with actual visit dates\n"
            f"3. Use format: DD/MM/YYYY (e.g., 08/02/2026 for today)\n"
            f"4. Optionally fill in Outcome and Notes columns\n"
            f"5. Save and upload again\n\n"
            f"Note: Only rows with ActualDate filled in will be imported."
        )
        errors.append(helpful_msg)

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

        # Add data validation dropdowns for Status column
        try:
            from openpyxl.worksheet.datavalidation import DataValidation
            workbook = writer.book
            worksheet = writer.sheets["ProposedVisits"]

            # Status dropdown options
            status_options = '"Confirmed,Rescheduled,Cancelled,DNA"'
            status_validation = DataValidation(
                type="list",
                formula1=status_options,
                allow_blank=True,
                showErrorMessage=True,
                error="Please select a valid status from the dropdown",
                errorTitle="Invalid Status"
            )
            # Apply to Status column (column F, rows 2 onwards, assuming up to 1000 rows)
            status_col_idx = export_df.columns.get_loc("Status") + 1  # +1 because Excel is 1-indexed
            status_col_letter = chr(64 + status_col_idx)  # Convert to letter (A=65)
            status_validation.add(f"{status_col_letter}2:{status_col_letter}1000")
            worksheet.add_data_validation(status_validation)
        except Exception as e:
            log_activity(f"Could not add data validation dropdowns: {e}", level='warning')

        # Add instructions sheet
        instructions_data = {
            "Instructions": [
                "PROPOSED VISITS CONFIRMATION WORKFLOW",
                "",
                "This file contains visits that are currently marked as 'Proposed' (tentative bookings).",
                "These visits need to be confirmed or updated based on actual patient attendance.",
                "",
                "HOW TO USE THIS FILE:",
                "1. Review each proposed visit in the 'ProposedVisits' sheet",
                "2. Update the Status column based on what happened:",
                "",
                "STATUS OPTIONS:",
                "   • Confirmed = Visit occurred as scheduled",
                "   • Rescheduled = Visit moved to different date (update ActualDate to new date)",
                "   • Cancelled = Visit cancelled (patient withdrew, study ended, etc.)",
                "   • DNA = Patient Did Not Attend (no show)",
                "   • [Leave blank] = Still proposed/tentative (no change)",
                "",
                "PATIENT STATUS CONTEXT:",
                "The system tracks 8 patient statuses throughout their journey:",
                "   • screening = Patient in screening phase",
                "   • screen_failed = Patient failed screening criteria",
                "   • dna_screening = Patient did not attend screening",
                "   • randomized = Patient successfully randomized into study",
                "   • withdrawn = Patient withdrew from study",
                "   • deceased = Patient passed away",
                "   • completed = Patient completed all study visits",
                "   • lost_to_followup = Patient lost contact",
                "",
                "NOTES FIELD:",
                "Use the Notes column to add any relevant information:",
                "   • Reason for DNA (sick, forgot, etc.)",
                "   • Reason for cancellation",
                "   • Any special circumstances",
                "",
                "AFTER COMPLETING THIS FILE:",
                "1. Save the file",
                "2. Go to Import/Export page in the application",
                "3. Upload this file in the 'Proposed Visits Confirmation' section",
                "4. The system will:",
                "   - Convert 'Confirmed' visits to actual visits",
                "   - Update dates for 'Rescheduled' visits",
                "   - Remove 'Cancelled' and 'DNA' visits",
                "   - Keep blank Status visits as proposed",
                "",
                "IMPORTANT NOTES:",
                "• Do NOT modify PatientID, Study, or VisitName columns",
                "• ActualDate format must be DD/MM/YYYY",
                "• Status field is case-insensitive (confirmed = Confirmed)",
                "• For rescheduled visits, make sure to update ActualDate to the new date",
                "",
                "EXAMPLE:",
                "PatientID | Study | VisitName | ActualDate | Status     | Notes",
                "P001      | BaxDuo| V5        | 15/06/2026 | Confirmed  | Patient attended",
                "P002      | Zeus  | V3        | 20/06/2026 | DNA        | Patient forgot",
                "P003      | FluSn | V2        | 25/06/2026 | Rescheduled| Moved to 02/07/2026 (update ActualDate)",
                "P004      | BaxDuo| V-EOT     | 30/06/2026 | Cancelled  | Study terminated early",
            ]
        }
        instructions_df = pd.DataFrame(instructions_data)
        instructions_df.to_excel(writer, sheet_name="Instructions", index=False, header=False)

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
