import pandas as pd
from datetime import timedelta
from helpers import safe_string_conversion
from visit_processor import (calculate_tolerance_windows, is_visit_out_of_protocol, 
                           create_tolerance_window_records)

def process_patient_actual_visits(patient_id, study, actual_visits_df, study_visits):
    """Process actual visits for a specific patient"""
    patient_actual_visits = {}
    actual_visits_used = 0
    unmatched_visits = []
    
    if actual_visits_df is None:
        return patient_actual_visits, actual_visits_used, unmatched_visits
    
    patient_actuals = actual_visits_df[
        (actual_visits_df["PatientID"] == patient_id) & 
        (actual_visits_df["Study"] == study) &
        (actual_visits_df.get("VisitType", "patient") == "patient")
    ]
    
    for _, actual_visit in patient_actuals.iterrows():
        visit_name = str(actual_visit["VisitName"]).strip()
        
        matching_trial = study_visits[study_visits["VisitName"].str.strip() == visit_name]
        if len(matching_trial) == 0:
            unmatched_visits.append(f"Patient {patient_id}, Study {study}: Visit '{visit_name}' not found in trials")
            continue
        
        patient_actual_visits[visit_name] = actual_visit
        actual_visits_used += 1
    
    return patient_actual_visits, actual_visits_used, unmatched_visits

def process_actual_visit(patient_id, study, patient_origin, visit, actual_visit_data, 
                        baseline_date, screen_fail_date, processing_messages, out_of_window_visits):
    """Process a single actual visit"""
    visit_day = int(visit["Day"])
    visit_name = str(visit["VisitName"])
    visit_date = actual_visit_data["ActualDate"]
    
    # Ensure it's a proper Timestamp and normalize to date only for calendar matching
    if not isinstance(visit_date, pd.Timestamp):
        visit_date = pd.Timestamp(visit_date)
    
    # Skip visits with invalid dates
    if pd.isna(visit_date):
        from helpers import log_activity
        log_activity(f"⚠️ Skipping visit '{visit_name}' for patient {patient_id} - invalid date: {actual_visit_data['ActualDate']}", level='warning')
        return None, []
    
    visit_date = pd.Timestamp(visit_date.date())  # Normalize to date only
    
    # Get payment amount
    trial_payment = visit.get("Payment", 0)
    if pd.notna(trial_payment):
        payment = float(trial_payment)
    else:
        payment = 0.0
    
    # Check for screen failure
    notes = str(actual_visit_data.get("Notes", ""))
    is_screen_fail = "ScreenFail" in notes
    
    # Improved data validation with warnings
    if screen_fail_date is not None and visit_date > screen_fail_date:
        visit_status = f"⚠️ DATA ERROR {visit_name}"
        is_out_of_protocol = False
        processing_messages.append(f"⚠️ Patient {patient_id} has visit '{visit_name}' on {visit_date.strftime('%Y-%m-%d')} AFTER screen failure")
    else:
        expected_date, earliest_acceptable, latest_acceptable, tolerance_before, tolerance_after = calculate_tolerance_windows(
            visit, baseline_date, visit_day
        )
        
        is_out_of_protocol = is_visit_out_of_protocol(
            visit_date, visit_day, visit_name, earliest_acceptable, latest_acceptable
        )
        
        if is_out_of_protocol:
            days_early = max(0, (earliest_acceptable - visit_date).days)
            days_late = max(0, (visit_date - latest_acceptable).days)
            deviation = days_early + days_late
            out_of_window_visits.append({
                'patient': f"{patient_id} ({study})",
                'visit': visit_name,
                'expected': expected_date.strftime('%Y-%m-%d'),
                'actual': visit_date.strftime('%Y-%m-%d'),
                'deviation': f"{deviation} days {'early' if days_early > 0 else 'late'}",
                'tolerance': f"+{tolerance_after}/-{tolerance_before} days"
            })
        
        if is_screen_fail:
            visit_status = f"⚠️ Screen Fail {visit_name}"
        elif is_out_of_protocol:
            visit_status = f"🔴 OUT OF PROTOCOL {visit_name}"
        else:
            visit_status = f"✅ {visit_name}"
    
    site = str(visit.get("SiteforVisit", "Unknown Site"))
    
    # Create main visit record
    visit_record = {
        "Date": visit_date,
        "PatientID": patient_id,
        "Visit": visit_status,
        "Study": study,
        "Payment": payment,
        "SiteofVisit": site,
        "PatientOrigin": patient_origin,
        "IsActual": True,
        "IsScreenFail": is_screen_fail,
        "IsOutOfProtocol": is_out_of_protocol,
        "VisitDay": visit_day,
        "VisitName": visit_name
    }
    
    # Create tolerance window records
    tolerance_records = []
    if screen_fail_date is None or visit_date <= screen_fail_date:
        expected_date, _, _, tolerance_before, tolerance_after = calculate_tolerance_windows(
            visit, baseline_date, visit_day
        )
        tolerance_records = create_tolerance_window_records(
            patient_id, study, site, patient_origin, expected_date,
            tolerance_before, tolerance_after, visit_day, visit_name,
            screen_fail_date, visit_date
        )
    
    return visit_record, tolerance_records

def process_scheduled_visit(patient_id, study, patient_origin, visit, baseline_date, screen_fail_date, has_actual_visit=False):
    """Process a single scheduled (predicted) visit"""
    visit_day = int(visit["Day"])
    visit_name = str(visit["VisitName"])
    
    # Ensure baseline_date is a proper Timestamp and normalize to date only
    if not isinstance(baseline_date, pd.Timestamp):
        baseline_date = pd.Timestamp(baseline_date)
    baseline_date = pd.Timestamp(baseline_date.date())  # Normalize to date only
    
    scheduled_date = baseline_date + timedelta(days=visit_day - 1)
    # Normalize scheduled_date to date only for calendar matching
    scheduled_date = pd.Timestamp(scheduled_date.date())
    
    # Use patient-specific screen failure check
    if screen_fail_date is not None and scheduled_date > screen_fail_date:
        return [], 1  # Return empty list and increment exclusion count
    
    try:
        payment = float(visit.get("Payment", 0) or 0)
    except:
        payment = 0.0
    
    site = str(visit.get("SiteforVisit", "Unknown Site"))
    
    # Style the visit name based on whether there's an actual visit
    if has_actual_visit:
        # This visit has an actual visit - show as planned (grayed out)
        visit_display = f"📅 {visit_name} (Planned)"
    else:
        # This visit has no actual visit - show as predicted
        visit_display = f"📋 {visit_name} (Predicted)"
    
    # Create main scheduled visit record
    main_record = {
        "Date": scheduled_date,
        "PatientID": patient_id,
        "Visit": visit_display,
        "Study": study,
        "Payment": payment,
        "SiteofVisit": site,
        "PatientOrigin": patient_origin,
        "IsActual": False,
        "IsScreenFail": False,
        "IsOutOfProtocol": False,
        "VisitDay": visit_day,
        "VisitName": visit_name
    }
    
    # Only create tolerance window records if there's NO actual visit
    if not has_actual_visit:
        expected_date, _, _, tolerance_before, tolerance_after = calculate_tolerance_windows(
            visit, baseline_date, visit_day
        )
        tolerance_records = create_tolerance_window_records(
            patient_id, study, site, patient_origin, expected_date,
            tolerance_before, tolerance_after, visit_day, visit_name,
            screen_fail_date
        )
        return [main_record] + tolerance_records, 0
    else:
        # Has actual visit - only return the planned visit marker, no tolerance windows
        return [main_record], 0

def process_single_patient(patient, patient_visits, screen_failures, actual_visits_df=None):
    """Process all visits for a single patient"""
    from helpers import log_activity
    
    patient_id = str(patient["PatientID"])
    study = str(patient["Study"])
    start_date = patient["StartDate"]
    patient_origin = str(patient["OriginSite"])
    
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
    
    # Use patient-specific screen failure key
    this_patient_screen_fail_key = f"{patient_id}_{study}"
    screen_fail_date = screen_failures.get(this_patient_screen_fail_key)
    
    study_visits = patient_visits[patient_visits["Study"] == study].sort_values('Day').copy()
    
    if len(study_visits) == 0:
        return visit_records, actual_visits_used, unmatched_visits, screen_fail_exclusions, out_of_window_visits, processing_messages, patient_needs_recalc
    
    # Get baseline visit
    day_1_visits = study_visits[study_visits["Day"] == 1]
    baseline_visit_name = str(day_1_visits.iloc[0]["VisitName"])
    
    # Process actual visits for this patient
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
    
    # Process each visit for this patient
    for _, visit in study_visits.iterrows():
        visit_name = str(visit["VisitName"])
        actual_visit_data = patient_actual_visits.get(visit_name)
        
        if actual_visit_data is not None:
            # Process actual visit - includes its own tolerance windows
            visit_record, tolerance_records = process_actual_visit(
                patient_id, study, patient_origin, visit, actual_visit_data,
                baseline_date, screen_fail_date, processing_messages, out_of_window_visits
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
            
            # Only add planned marker if actual happened on a different date
            if expected_date != actual_date:
                scheduled_records, exclusions = process_scheduled_visit(
                    patient_id, study, patient_origin, visit, baseline_date, screen_fail_date, 
                    has_actual_visit=True
                )
                visit_records.extend(scheduled_records)
        else:
            # No actual visit - process scheduled with full tolerance windows
            scheduled_records, exclusions = process_scheduled_visit(
                patient_id, study, patient_origin, visit, baseline_date, screen_fail_date, 
                has_actual_visit=False
            )
            visit_records.extend(scheduled_records)
            screen_fail_exclusions += exclusions
    
    log_activity(f"Patient {patient_id} generated {len(visit_records)} visit records", level='info')
    return visit_records, actual_visits_used, unmatched_visits, screen_fail_exclusions, out_of_window_visits, processing_messages, patient_needs_recalc
