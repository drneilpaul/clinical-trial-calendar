import pandas as pd
from datetime import timedelta, date
import os
import json
from helpers import safe_string_conversion, get_visit_type_series
from visit_processor import (calculate_tolerance_windows, is_visit_out_of_protocol, 
                           create_tolerance_window_records)

# Global variable to store log path for access
_DEBUG_LOG_PATH = None

def _get_debug_log_path():
    """Get the debug log file path, creating directory if needed"""
    global _DEBUG_LOG_PATH
    if _DEBUG_LOG_PATH is None:
        try:
            # Try workspace-relative path first (for Streamlit Cloud)
            if os.path.exists('/mount/src'):
                log_dir = '/mount/src/clinical-trial-calendar/.cursor'
            else:
                # Try local path (for local development)
                log_dir = os.path.join(os.path.dirname(__file__), '.cursor')
            os.makedirs(log_dir, exist_ok=True)
            _DEBUG_LOG_PATH = os.path.join(log_dir, 'debug.log')
        except Exception:
            _DEBUG_LOG_PATH = None
    return _DEBUG_LOG_PATH

# Helper function for debug logging that works in both local and Streamlit Cloud environments
def _debug_log(location, message, data, hypothesis_id):
    """Write debug log entry, gracefully handling file system issues. Only logs if debug level >= DEBUG."""
    # Check debug level before doing any file I/O
    try:
        from config import should_log_debug
        if not should_log_debug():
            return  # No-op if debug level is too low
    except ImportError:
        # If config not available, log anyway (backward compatibility)
        pass
    except Exception:
        # If any error checking debug level, skip logging (fail closed for performance)
        return
    
    try:
        log_path = _get_debug_log_path()
        if log_path:
            with open(log_path, 'a') as f:
                f.write(json.dumps({"timestamp": pd.Timestamp.now().timestamp() * 1000, "sessionId": "debug-session", "runId": "run1", "hypothesisId": hypothesis_id, "location": location, "message": message, "data": data}) + '\n')
    except Exception:
        # Silently fail if logging isn't possible (e.g., permission issues)
        pass

def get_debug_log_content():
    """Read debug log file content for download/display, optionally including activity log"""
    try:
        from config import should_log_info, should_log_debug, get_debug_level, DEBUG_VERBOSE
        
        content_parts = []
        current_level = get_debug_level()
        
        # Include activity log if level >= VERBOSE
        if current_level >= DEBUG_VERBOSE:
            try:
                import streamlit as st
                if 'activity_log' in st.session_state and st.session_state.activity_log:
                    content_parts.append("=" * 80)
                    content_parts.append("ACTIVITY LOG")
                    content_parts.append("=" * 80)
                    for entry in st.session_state.activity_log:
                        timestamp = entry['timestamp'].strftime('%Y-%m-%d %H:%M:%S') if hasattr(entry['timestamp'], 'strftime') else str(entry['timestamp'])
                        level = entry.get('level', 'info').upper()
                        message = entry.get('message', '')
                        content_parts.append(f"[{timestamp}] [{level}] {message}")
                    content_parts.append("")
            except:
                pass
        
        # Include detailed debug log if level >= DEBUG
        if should_log_debug():
            log_path = _get_debug_log_path()
            if log_path and os.path.exists(log_path):
                if content_parts:
                    content_parts.append("=" * 80)
                    content_parts.append("DETAILED DEBUG LOG (JSON)")
                    content_parts.append("=" * 80)
                with open(log_path, 'r') as f:
                    debug_content = f.read()
                    if debug_content.strip():
                        content_parts.append(debug_content)
        
        if content_parts:
            return "\n".join(content_parts)
        
        # Fallback: just return debug log file if it exists
        log_path = _get_debug_log_path()
        if log_path and os.path.exists(log_path):
            with open(log_path, 'r') as f:
                return f.read()
    except Exception:
        pass
    return None

def process_patient_actual_visits(patient_id, study, actual_visits_df, study_visits):
    """Process actual visits for a specific patient"""
    from helpers import log_activity
    
    patient_actual_visits = {}
    actual_visits_used = 0
    unmatched_visits = []
    
    if actual_visits_df is None:
        return patient_actual_visits, actual_visits_used, unmatched_visits
    
    from helpers import get_visit_type_series
    visit_type_series = get_visit_type_series(actual_visits_df, default='patient')
    
    patient_actuals = actual_visits_df[
        (actual_visits_df["PatientID"] == patient_id) & 
        (actual_visits_df["Study"] == study) &
        (visit_type_series.isin(['patient', 'extra']))
    ]
    
    if len(patient_actuals) > 0:
        log_activity(f"  Found {len(patient_actuals)} actual patient visits for {patient_id}", level='info')
    
    # OPTIMIZED: Pre-create lookup dictionaries for faster matching (O(1) instead of O(n))
    # Create exact match lookup
    study_visits_stripped = study_visits["VisitName"].str.strip()
    exact_match_lookup = {}
    for idx, visit_name in study_visits_stripped.items():
        if visit_name not in exact_match_lookup:
            exact_match_lookup[visit_name] = study_visits.loc[idx]
    
    # Create case-insensitive lookup (lowercase key -> original row)
    case_insensitive_lookup = {}
    for idx, visit_name in study_visits_stripped.items():
        key = visit_name.lower()
        if key not in case_insensitive_lookup:
            case_insensitive_lookup[key] = study_visits.loc[idx]
    
    # OPTIMIZED: Use itertuples for faster iteration
    for actual_visit_tuple in patient_actuals.itertuples():
        visit_name = str(actual_visit_tuple.VisitName).strip()
        log_activity(f"    Matching actual visit '{visit_name}' for patient {patient_id}", level='info')
        
        # Convert tuple back to Series for compatibility with existing code
        actual_visit = patient_actuals.loc[actual_visit_tuple.Index]
        
        # Try exact match first (O(1) lookup)
        matching_trial = exact_match_lookup.get(visit_name)
        
        # If no exact match, try case-insensitive match (O(1) lookup)
        if matching_trial is None:
            matching_trial = case_insensitive_lookup.get(visit_name.lower())
        
        if matching_trial is None:
            # Check if this might be a Day 0 visit (optional visit not in scheduled trials)
            # For now, we'll still add it but mark it as unmatched for reporting
            # In the future, we could add special handling for Day 0 visits
            log_activity(f"      ⚠️ Visit '{visit_name}' not found in trial schedule (may be Day 0 or unscheduled)", level='warning')
            unmatched_visits.append(f"Patient {patient_id}, Study {study}: Visit '{visit_name}' not found in trials (may be optional Day 0 visit)")
            # Still add it to actual visits so it shows up on calendar
            patient_actual_visits[visit_name] = actual_visit
            actual_visits_used += 1
            continue
        
        # Found a match!
        matched_day = matching_trial["Day"]
        log_activity(f"      ✅ Matched to trial visit (Day {matched_day})", level='info')
        patient_actual_visits[visit_name] = actual_visit
        actual_visits_used += 1
    
    return patient_actual_visits, actual_visits_used, unmatched_visits

def process_actual_visit(patient_id, study, patient_origin, patient_seen_at, visit, actual_visit_data, 
                        baseline_date, stoppage_date, processing_messages, out_of_window_visits, skipped_counter=None):
    """Process a single actual visit
    
    Args:
        stoppage_date: Date of screen failure, withdrawal, or death (stops future visits)
    """
    visit_day = int(visit["Day"])
    visit_name = str(visit["VisitName"])
    visit_type = get_visit_type_series(pd.DataFrame([visit]), default='patient').iloc[0]
    
    # Check VisitType from actual_visit_data (may have patient_proposed)
    actual_visit_type = str(actual_visit_data.get("VisitType", visit_type)).lower()
    is_proposed_type = actual_visit_type == 'patient_proposed'
    
    visit_date = actual_visit_data["ActualDate"]
    
    # Ensure it's a proper Timestamp and normalize to date only for calendar matching
    if not isinstance(visit_date, pd.Timestamp):
        visit_date = pd.Timestamp(visit_date)
    
    # Skip visits with invalid dates
    if pd.isna(visit_date):
        from helpers import log_activity
        log_activity(f"⚠️ Skipping visit '{visit_name}' for patient {patient_id} - invalid date: {actual_visit_data['ActualDate']}", level='warning')
        if skipped_counter is not None:
            skipped_counter[0] += 1
        return None, []
    
    
    visit_date = pd.Timestamp(visit_date.date())  # Normalize to date only
    
    # Check if this is a proposed visit (future date or explicit patient_proposed type)
    # Ensure both dates are properly normalized for comparison
    today = pd.Timestamp(date.today()).normalize()
    # visit_date is already normalized above, ensure it's date-only
    visit_date = pd.Timestamp(visit_date.date()).normalize() if hasattr(visit_date, 'date') else pd.Timestamp(visit_date).normalize()
    
    # Proposed if explicitly marked as patient_proposed OR if date is in future
    is_proposed = is_proposed_type or (visit_date > today)
    
    # Debug logging for proposed visit detection
    if is_proposed:
        from helpers import log_activity
        log_activity(f"  Proposed visit detected: {visit_name} on {visit_date.strftime('%Y-%m-%d')} (today: {today.strftime('%Y-%m-%d')})", level='info')
    
    # Get payment amount
    trial_payment = visit.get("Payment", 0)
    if pd.notna(trial_payment):
        payment = float(trial_payment)
    else:
        payment = 0.0
    
    # Check for screen failure, withdrawal, and death
    notes = str(actual_visit_data.get("Notes", ""))
    is_screen_fail = "ScreenFail" in notes
    is_withdrawn = "Withdrawn" in notes
    is_died = "Died" in notes
    
    # Improved data validation with warnings
    # CRITICAL: Skip stoppage date validation for proposed visits (they're legitimate tentative bookings)
    if not is_proposed and stoppage_date is not None and visit_date > stoppage_date:
        visit_status = f"⚠️ DATA ERROR {visit_name}"
        is_out_of_protocol = False
        processing_messages.append(f"⚠️ Patient {patient_id} has visit '{visit_name}' on {visit_date.strftime('%Y-%m-%d')} AFTER screen failure, withdrawal, or death")
    else:
        # Simplified: All actual visits are just marked as completed (no tolerance window checking)
        is_out_of_protocol = False  # Always False - we don't check tolerance windows anymore
        
        if is_proposed:
            # Proposed visit - format with 📅 emoji and (Proposed) text
            from helpers import log_activity
            if is_screen_fail:
                visit_status = f"⚠️ Screen Fail {visit_name}"  # Shouldn't happen, but handle gracefully
            elif is_withdrawn:
                visit_status = f"⚠️ Withdrawn {visit_name}"  # Shouldn't happen, but handle gracefully
            elif is_died:
                visit_status = f"⚠️ Died {visit_name}"  # Shouldn't happen, but handle gracefully
            else:
                visit_status = f"📅 {visit_name} (Proposed)"
                log_activity(f"  Formatting as proposed: {visit_status}", level='info')
        elif is_screen_fail:
            visit_status = f"⚠️ Screen Fail {visit_name}"
        elif is_withdrawn:
            visit_status = f"⚠️ Withdrawn {visit_name}"
        elif is_died:
            visit_status = f"⚠️ Died {visit_name}"
        else:
            visit_status = f"✅ {visit_name}"
    
    # CHANGED: Use patient SiteSeenAt for visit location
    site = patient_seen_at
    
    if pd.isna(site) or site in ['', 'nan', 'None', 'null', 'NULL', 'Unknown Site', 'Default Site']:
        error_msg = f"❌ DATA ERROR: Visit '{visit_name}' for patient {patient_id} has invalid SiteSeenAt: '{site}'"
        from helpers import log_activity
        log_activity(error_msg, level='error')
        # Return None to skip this visit rather than using a default
        return None, []
    
    site = str(site)
    # END CHANGED
    
    # Create main visit record
    # Use actual_visit_type if it's patient_proposed, otherwise use visit_type from trial schedule
    final_visit_type = actual_visit_type if is_proposed_type else visit_type
    
    contract_site = visit.get("ContractSite") or visit.get("SiteforVisit")
    visit_record = {
        "Date": visit_date,
        "PatientID": patient_id,
        "Visit": visit_status,
        "Study": study,
        "Payment": payment,
        "SiteofVisit": site,
        "ContractSite": contract_site,
        "PatientOrigin": patient_origin,
        "IsActual": True,
        "IsProposed": is_proposed,  # Add IsProposed flag
        "IsScreenFail": is_screen_fail,
        "IsWithdrawn": is_withdrawn,
        "IsDied": is_died,
        "IsOutOfProtocol": is_out_of_protocol,
        "VisitDay": visit_day,
        "VisitName": visit_name,
        "VisitType": final_visit_type
    }
    
    # Simplified: No tolerance window records created for actual visits (proposed or not)
    tolerance_records = []
    
    return visit_record, tolerance_records

def process_scheduled_visit(patient_id, study, patient_origin, patient_seen_at, visit, baseline_date, stoppage_date):
    """Process a single scheduled (predicted) visit
    
    Args:
        stoppage_date: Date of screen failure, withdrawal, or death (stops future visits)
    """
    visit_day = int(visit["Day"])
    visit_name = str(visit["VisitName"])
    visit_type = str(visit.get("VisitType", "patient")).strip().lower()
    if visit_type in ['', 'nan', 'none', 'null']:
        visit_type = 'patient'
    
    # Ensure baseline_date is a proper Timestamp and normalize to date only
    if not isinstance(baseline_date, pd.Timestamp):
        baseline_date = pd.Timestamp(baseline_date)
    baseline_date = pd.Timestamp(baseline_date.date())  # Normalize to date only
    
    # Calculate expected date and tolerances using unified interval logic
    expected_date, _, _, tolerance_before, tolerance_after = calculate_tolerance_windows(
        visit, baseline_date, visit_day
    )
    # Normalize expected_date to date only for calendar matching
    scheduled_date = pd.Timestamp(pd.Timestamp(expected_date).date())
    
    # Use patient-specific stoppage check (screen failure, withdrawal, or death)
    if stoppage_date is not None and scheduled_date > stoppage_date:
        return [], 1  # Return empty list and increment exclusion count
    
    try:
        payment = float(visit.get("Payment", 0) or 0)
    except (ValueError, TypeError):
        payment = 0.0
    
    # CHANGED: Use patient SiteSeenAt for visit location
    site = patient_seen_at
    
    if pd.isna(site) or site in ['', 'nan', 'None', 'null', 'NULL', 'Unknown Site', 'Default Site']:
        error_msg = f"❌ DATA ERROR: Scheduled visit '{visit_name}' for patient {patient_id} has invalid SiteSeenAt: '{site}'"
        from helpers import log_activity
        log_activity(error_msg, level='error')
        # Return empty list to skip this visit rather than using a default
        return [], 0
    
    site = str(site)
    # END CHANGED
    
    # Style the visit name as predicted (no actual visit yet)
    visit_display = f"📋 {visit_name} (Predicted)"
    
    # Create main scheduled visit record
    contract_site = visit.get("ContractSite") or visit.get("SiteforVisit")
    main_record = {
        "Date": scheduled_date,
        "PatientID": patient_id,
        "Visit": visit_display,
        "Study": study,
        "Payment": payment,
        "SiteofVisit": site,
        "ContractSite": contract_site,
        "PatientOrigin": patient_origin,
        "IsActual": False,
        "IsProposed": False,  # Predicted visits are never proposed
        "IsScreenFail": False,
        "IsOutOfProtocol": False,
        "VisitDay": visit_day,
        "VisitName": visit_name,
        "VisitType": visit_type
    }
    
    # Create tolerance window records for predicted visits
    tolerance_records = create_tolerance_window_records(
        patient_id, study, site, patient_origin, expected_date,
        tolerance_before, tolerance_after, visit_day, visit_name,
        stoppage_date
    )
    return [main_record] + tolerance_records, 0

def process_single_patient(patient, patient_visits, stoppages, actual_visits_df=None):
    """Process all visits for a single patient
    
    Args:
        stoppages: Dictionary of patient+study keys to stoppage dates (screen failures, withdrawals, or deaths)
    """
    from helpers import log_activity
    
    # Debug: Track skipped visits due to invalid dates
    skipped_invalid_dates = [0]  # Use list so it can be modified by reference
    
    patient_id = str(patient["PatientID"])
    study = str(patient["Study"])
    start_date = patient["StartDate"]
    patient_origin = str(patient.get("PatientPractice", "Unknown Site"))
    patient_seen_at = patient.get("SiteSeenAt") or patient_origin
    
    log_activity(f"Processing patient {patient_id} (Study: {study}, StartDate: {start_date}, Origin: {patient_origin})", level='info')
    
    visit_records = []
    actual_visits_used = 0
    unmatched_visits = []
    screen_fail_exclusions = 0
    out_of_window_visits = []
    processing_messages = []
    patient_needs_recalc = False
    
    if pd.isna(start_date):
        from helpers import log_activity
        log_activity(f"Patient {patient_id} has invalid start_date: {start_date}", level='warning')
        return visit_records, actual_visits_used, unmatched_visits, screen_fail_exclusions, out_of_window_visits, processing_messages, patient_needs_recalc
    
    # Use patient-specific stoppage key (includes both screen failures and withdrawals)
    this_patient_stoppage_key = f"{patient_id}_{study}"
    stoppage_date = stoppages.get(this_patient_stoppage_key)
    
    study_visits = patient_visits[patient_visits["Study"] == study].sort_values('Day').copy()
    
    # Include Day 0 visits for matching actual visits (but not for scheduling)
    all_study_visits = study_visits.copy()
    if actual_visits_df is not None:
        # Get all visits for this study including Day 0
        all_trials_for_study = actual_visits_df[actual_visits_df["Study"] == study]["VisitName"].unique()
        # This will be used for matching actual visits
    
    if len(study_visits) == 0:
        return visit_records, actual_visits_used, unmatched_visits, screen_fail_exclusions, out_of_window_visits, processing_messages, patient_needs_recalc
    
    # Get baseline visit
    day_1_visits = study_visits[study_visits["Day"] == 1]
    baseline_visit_name = str(day_1_visits.iloc[0]["VisitName"])
    
    # Process actual visits for this patient (including Day 0 visits for matching)
    patient_actual_visits, patient_actual_count, patient_unmatched = process_patient_actual_visits(
        patient_id, study, actual_visits_df, study_visits
    )
    actual_visits_used += patient_actual_count
    unmatched_visits.extend(patient_unmatched)
    
    # Determine baseline date
    baseline_date = start_date
    if baseline_visit_name in patient_actual_visits:
        actual_baseline_date = patient_actual_visits[baseline_visit_name]["ActualDate"]
        if actual_baseline_date != start_date:
            baseline_date = actual_baseline_date
            patient_needs_recalc = True
    
    # CRITICAL: Identify proposed visits BEFORE creating predicted visits (for suppression logic)
    today = pd.Timestamp(date.today()).normalize()
    proposed_visits = {}  # visit_name -> proposed_date
    proposed_visit_dates = []  # List of all proposed dates for this patient
    
    for visit_name, actual_visit_data in patient_actual_visits.items():
        visit_date = actual_visit_data["ActualDate"]
        if not isinstance(visit_date, pd.Timestamp):
            visit_date = pd.Timestamp(visit_date)
        visit_date = pd.Timestamp(visit_date.date()).normalize()
        
        if visit_date > today:
            # This is a proposed visit
            proposed_visits[visit_name] = visit_date
            proposed_visit_dates.append(visit_date)
            log_activity(f"  Found proposed visit: {visit_name} on {visit_date.strftime('%Y-%m-%d')}", level='info')
    
    # Sort proposed dates for suppression logic
    # We need both earliest (for individual checks) and latest (for suppression range)
    proposed_visit_dates.sort()
    earliest_proposed_date = proposed_visit_dates[0] if proposed_visit_dates else None
    latest_proposed_date = proposed_visit_dates[-1] if proposed_visit_dates else None
    
    # Check if any proposed visit is among the last visits in the trial schedule
    # If so, we should suppress ALL visits after the latest proposed date (study ending early)
    is_terminal_proposed_visit = False
    if proposed_visits and len(study_visits) > 0:
        # Get the last few visits in the trial schedule (last 5 visits)
        sorted_study_visits = study_visits.sort_values('Day')
        last_visit_names = sorted_study_visits.tail(5)["VisitName"].astype(str).tolist()
        # Check if any proposed visit name matches one of the last visits
        if any(visit_name in last_visit_names for visit_name in proposed_visits.keys()):
            is_terminal_proposed_visit = True
            log_activity(f"  Terminal visit(s) detected in proposed visits - will suppress all visits after {latest_proposed_date.strftime('%Y-%m-%d')}", level='info')
    
    if proposed_visit_dates:
        log_activity(f"  Proposed visits found: {len(proposed_visit_dates)} - earliest: {earliest_proposed_date.strftime('%Y-%m-%d')}, latest: {latest_proposed_date.strftime('%Y-%m-%d')}", level='info')
    
    # OPTIMIZED: Process each visit using itertuples (faster than iterrows)
    for visit_tuple in study_visits.itertuples():
        visit_name = str(visit_tuple.VisitName)
        visit_day = int(visit_tuple.Day)
        # Convert tuple to dict-like for compatibility
        visit = {
            "Day": visit_tuple.Day,
            "VisitName": visit_tuple.VisitName,
            "Payment": getattr(visit_tuple, 'Payment', 0),
            "SiteforVisit": getattr(visit_tuple, 'SiteforVisit', ''),
            "ContractSite": getattr(visit_tuple, 'SiteforVisit', ''),
            "ToleranceBefore": getattr(visit_tuple, 'ToleranceBefore', 0),
            "ToleranceAfter": getattr(visit_tuple, 'ToleranceAfter', 0),
            "IntervalUnit": getattr(visit_tuple, 'IntervalUnit', None),
            "IntervalValue": getattr(visit_tuple, 'IntervalValue', None),
            "VisitType": getattr(visit_tuple, 'VisitType', 'patient')
        }
        actual_visit_data = patient_actual_visits.get(visit_name)
        
        if actual_visit_data is not None:
            # Actual visit found - process it
            
            # Process actual visit - includes its own tolerance windows
            visit_record, tolerance_records = process_actual_visit(
                patient_id, study, patient_origin, patient_seen_at, visit, actual_visit_data,
                baseline_date, stoppage_date, processing_messages, out_of_window_visits, skipped_invalid_dates
            )
            # Skip if visit was invalid (None returned)
            if visit_record is not None:
                visit_records.append(visit_record)
                visit_records.extend(tolerance_records)
            
            # DON'T create a scheduled visit on the ACTUAL date
            # Only create it on the EXPECTED date if different
            expected_date, _, _, _, _ = calculate_tolerance_windows(
                visit, baseline_date, int(visit["Day"])
            )
            expected_date = pd.Timestamp(expected_date.date())
            actual_date = pd.Timestamp(actual_visit_data["ActualDate"].date())
            
            # No planned marker needed - actual visit is sufficient
        else:
            # No actual visit found - check if we should suppress predicted visit
            # FIXED: Only schedule predicted visits for Day != 0
            # Day 0 visits (SIV, Monitor, V1.1, Unscheduled) are optional and only appear when actual
            # Day < 0 (Screening) and Day >= 1 should be predicted normally
            if visit_day != 0:
                # Calculate predicted date to check suppression rules
                expected_date, _, _, _, _ = calculate_tolerance_windows(
                    visit, baseline_date, visit_day
                )
                predicted_date = pd.Timestamp(expected_date.date()).normalize()
                
                # SUPPRESSION LOGIC: Check if this predicted visit should be suppressed
                should_suppress = False
                suppress_reason = None
                
                # Rule 1: If predicted visit name matches a proposed visit → skip
                if visit_name in proposed_visits:
                    should_suppress = True
                    suppress_reason = f"proposed visit exists for {visit_name}"
                
                # Rule 2: Suppress ALL predicted visits between today and latest proposed date
                # If multiple proposed visits exist (e.g., V-EOT and V-FU), suppress everything
                # between now and the latest proposed date
                elif predicted_date >= today and latest_proposed_date is not None:
                    if predicted_date < latest_proposed_date:
                        should_suppress = True
                        suppress_reason = f"before latest proposed visit on {latest_proposed_date.strftime('%Y-%m-%d')}"
                    # Rule 3: If the proposed visit is a terminal visit (one of the last in the schedule),
                    # also suppress ALL predicted visits AFTER the latest proposed date (study ending early)
                    elif is_terminal_proposed_visit and predicted_date > latest_proposed_date:
                        should_suppress = True
                        suppress_reason = f"after terminal proposed visit on {latest_proposed_date.strftime('%Y-%m-%d')} (study ending early)"
                
                # Keep predicted visits from the past (date < today) - they may have happened but not been recorded yet
                # (should_suppress remains False for past dates)
                
                if should_suppress:
                    log_activity(f"  Suppressing predicted visit {visit_name} on {predicted_date.strftime('%Y-%m-%d')} - {suppress_reason}", level='info')
                    # Don't create this predicted visit
                else:
                    # Process scheduled visit with full tolerance windows
                    scheduled_records, exclusions = process_scheduled_visit(
                        patient_id, study, patient_origin, patient_seen_at, visit, baseline_date, stoppage_date
                    )
                    visit_records.extend(scheduled_records)
                    screen_fail_exclusions += exclusions
            # else: Skip Day 0 visits only - they're optional and only appear when actual
    
    # OPTIMIZED: Handle unmatched actual visits (including Day 0 optional visits)
    # Pre-compute study visit names set for O(1) lookup
    study_visit_names = set(study_visits["VisitName"].astype(str))
    for visit_name, actual_visit_data in patient_actual_visits.items():
        if visit_name not in study_visit_names:
            # This is an unmatched actual visit (likely Day 0 optional visit)
            from helpers import log_activity
            # Unmatched visit - may be Day 0 or unscheduled
            
            # FIXED: Skip study events (SIV/Monitor) - they should be in Events column, not patient columns
            visit_type = str(actual_visit_data.get('VisitType', 'patient')).lower()
            if visit_type in ['siv', 'monitor']:
                log_activity(
                    f"ℹ️ Skipping study event '{visit_name}' for patient {patient_id} - should be in Events column",
                    level='info'
                )
                continue
            
            # For unmatched visits, use patient SiteSeenAt as visit location
            visit_site = patient_seen_at
            
            # Look for this visit in the trial schedule (case-insensitive, partial match)
            trial_matches = study_visits[
                study_visits["VisitName"].str.strip().str.lower() == visit_name.lower()
            ]
            
            if not trial_matches.empty:
                # Found in trial schedule - use its SiteforVisit
                trial_visit = trial_matches.iloc[0]
                contract_site = trial_visit.get("SiteforVisit")
                payment = trial_visit.get("Payment", 0.0)
                visit_day = trial_visit["Day"]
                
            else:
                # Truly unmatched - still use patient SiteSeenAt for visit location
                
                from helpers import log_activity
                log_activity(
                    f"⚠️ Skipping unmatched visit '{visit_name}' for patient {patient_id} - "
                    f"not in trial schedule and cannot safely determine ContractSite",
                    level='error'
                )
                continue  # Skip this visit entirely rather than misassigning the site
                
            
            # Validate the site
            invalid_sites = ['', 'nan', 'None', 'null', 'NULL', 'Unknown Site', 'unknown site', 'UNKNOWN SITE', 'Default Site']
            if pd.isna(visit_site) or str(visit_site).strip() in invalid_sites:
                log_activity(
                    f"❌ Skipping unmatched visit '{visit_name}' for patient {patient_id} - invalid site: '{visit_site}'",
                    level='error'
                )
                continue  # Skip this visit entirely
            
            # Create visit record
            actual_visit_type = get_visit_type_series(pd.DataFrame([actual_visit_data]), default='patient').iloc[0]
            notes_str = str(actual_visit_data.get("Notes", ""))
            is_screen_fail = "ScreenFail" in notes_str
            is_withdrawn = "Withdrawn" in notes_str
            is_died = "Died" in notes_str
            
            if is_screen_fail:
                visit_display = f"⚠️ Screen Fail {visit_name}"
            elif is_withdrawn:
                visit_display = f"⚠️ Withdrawn {visit_name}"
            elif is_died:
                visit_display = f"⚠️ Died {visit_name}"
            else:
                visit_display = f"✅ {visit_name}"
            
            # Check if this unmatched visit is proposed (future date)
            unmatched_visit_date = pd.Timestamp(actual_visit_data["ActualDate"].date())
            today = pd.Timestamp(date.today()).normalize()
            is_unmatched_proposed = unmatched_visit_date > today
            
            visit_record = {
                "Date": unmatched_visit_date,
                "PatientID": patient_id,
                "Visit": visit_display,
                "Study": study,
                "Payment": payment,
                "SiteofVisit": str(visit_site).strip(),
                "ContractSite": contract_site,
                "PatientOrigin": patient_origin,
                "IsActual": True,
                "IsProposed": is_unmatched_proposed,  # Add IsProposed flag
                "IsScreenFail": is_screen_fail,
                "IsWithdrawn": is_withdrawn,
                "IsDied": is_died,
                "IsOutOfProtocol": False,  # Day 0 visits are never out of protocol
                "VisitDay": visit_day,
                "VisitName": visit_name,
                "VisitType": actual_visit_type
            }
            visit_records.append(visit_record)
    
    if skipped_invalid_dates[0] > 0:
        log_activity(f"⚠️ Patient {patient_id} had {skipped_invalid_dates[0]} actual visits skipped due to invalid dates", level='warning')
    return visit_records, actual_visits_used, unmatched_visits, screen_fail_exclusions, out_of_window_visits, processing_messages, patient_needs_recalc
