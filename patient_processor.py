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
            # Check if this might be a Day 0 visit (optional visit not in scheduled trials)
            # For now, we'll still add it but mark it as unmatched for reporting
            # In the future, we could add special handling for Day 0 visits
            unmatched_visits.append(f"Patient {patient_id}, Study {study}: Visit '{visit_name}' not found in trials (may be optional Day 0 visit)")
            # Still add it to actual visits so it shows up on calendar
            patient_actual_visits[visit_name] = actual_visit
            actual_visits_used += 1
            continue
        
        patient_actual_visits[visit_name] = actual_visit
        actual_visits_used += 1
    
    return patient_actual_visits, actual_visits_used, unmatched_visits

def process_actual_visit(patient_id, study, patient_origin, visit, actual_visit_data, 
                        baseline_date, screen_fail_date, processing_messages, out_of_window_visits, skipped_counter=None):
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
        if skipped_counter is not None:
            skipped_counter[0] += 1
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
        # Simplified: All actual visits are just marked as completed (no tolerance window checking)
        is_out_of_protocol = False  # Always False - we don't check tolerance windows anymore
        
        if is_screen_fail:
            visit_status = f"⚠️ Screen Fail {visit_name}"
        else:
            visit_status = f"✅ {visit_name}"
    
    # CHANGED: Validate site exists and is valid, don't default
    site = visit.get("SiteforVisit")
    
    if pd.isna(site) or site in ['', 'nan', 'None', 'null', 'NULL', 'Unknown Site', 'Default Site']:
        error_msg = f"❌ DATA ERROR: Visit '{visit_name}' for patient {patient_id} has invalid SiteforVisit: '{site}'"
        from helpers import log_activity
        log_activity(error_msg, level='error')
        # Return None to skip this visit rather than using a default
        return None, []
    
    site = str(site)
    # END CHANGED
    
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
    
    # Simplified: No tolerance window records created
    tolerance_records = []
    
    return visit_record, tolerance_records

def process_scheduled_visit(patient_id, study, patient_origin, visit, baseline_date, screen_fail_date):
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
    
    # CHANGED: Validate site exists and is valid, don't default
    site = visit.get("SiteforVisit")
    
    if pd.isna(site) or site in ['', 'nan', 'None', 'null', 'NULL', 'Unknown Site', 'Default Site']:
        error_msg = f"❌ DATA ERROR: Scheduled visit '{visit_name}' for patient {patient_id} has invalid SiteforVisit: '{site}'"
        from helpers import log_activity
        log_activity(error_msg, level='error')
        # Return empty list to skip this visit rather than using a default
        return [], 0
    
    site = str(site)
    # END CHANGED
    
    # Style the visit name as predicted (no actual visit yet)
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
    
    # Create tolerance window records for predicted visits
    expected_date, _, _, tolerance_before, tolerance_after = calculate_tolerance_windows(
        visit, baseline_date, visit_day
    )
    tolerance_records = create_tolerance_window_records(
        patient_id, study, site, patient_origin, expected_date,
        tolerance_before, tolerance_after, visit_day, visit_name,
        screen_fail_date
    )
    return [main_record] + tolerance_records, 0

def process_single_patient(patient, patient_visits, screen_failures, actual_visits_df=None):
    """Process all visits for a single patient"""
    from helpers import log_activity
    
    # Debug: Track skipped visits due to invalid dates
    skipped_invalid_dates = [0]  # Use list so it can be modified by reference
    
    patient_id = str(patient["PatientID"])
    study = str(patient["Study"])
    start_date = patient["StartDate"]
    patient_origin = str(patient.get("PatientPractice", "Unknown Site"))
    
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
    
    # Process each visit for this patient
    for _, visit in study_visits.iterrows():
        visit_name = str(visit["VisitName"])
        actual_visit_data = patient_actual_visits.get(visit_name)
        
        if actual_visit_data is not None:
            # Debug: Log when we find a matching actual visit
            from helpers import log_activity
            log_activity(f"🎯 Found matching actual visit: {patient_id} | {visit_name} | {actual_visit_data['ActualDate']}", level='info')
            
            # Process actual visit - includes its own tolerance windows
            visit_record, tolerance_records = process_actual_visit(
                patient_id, study, patient_origin, visit, actual_visit_data,
                baseline_date, screen_fail_date, processing_messages, out_of_window_visits, skipped_invalid_dates
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
            # No actual visit - process scheduled with full tolerance windows
            scheduled_records, exclusions = process_scheduled_visit(
                patient_id, study, patient_origin, visit, baseline_date, screen_fail_date
            )
            visit_records.extend(scheduled_records)
            screen_fail_exclusions += exclusions
    
    # Handle unmatched actual visits (including Day 0 optional visits)
    for visit_name, actual_visit_data in patient_actual_visits.items():
        if visit_name not in [str(v["VisitName"]) for _, v in study_visits.iterrows()]:
            # This is an unmatched actual visit (likely Day 0 optional visit)
            from helpers import log_activity
            log_activity(f"🎯 Processing unmatched actual visit (Day 0?): {patient_id} | {visit_name} | {actual_visit_data['ActualDate']}", level='info')
            
            # Create a minimal visit record for Day 0 visits
            visit_record = {
                "Date": pd.Timestamp(actual_visit_data["ActualDate"].date()),
                "PatientID": patient_id,
                "Visit": f"✅ {visit_name}",
                "Study": study,
                "Payment": 0.0,  # Day 0 visits typically don't have payment
                "SiteofVisit": str(actual_visit_data.get("SiteofVisit", "Unknown Site")),
                "PatientOrigin": patient_origin,
                "IsActual": True,
                "IsScreenFail": "ScreenFail" in str(actual_visit_data.get("Notes", "")),
                "IsOutOfProtocol": False,  # Day 0 visits are never out of protocol
                "VisitDay": 0,  # Mark as Day 0
                "VisitName": visit_name
            }
            visit_records.append(visit_record)
    
    if skipped_invalid_dates[0] > 0:
        log_activity(f"⚠️ Patient {patient_id} had {skipped_invalid_dates[0]} actual visits skipped due to invalid dates", level='warning')
    return visit_records, actual_visits_used, unmatched_visits, screen_fail_exclusions, out_of_window_visits, processing_messages, patient_needs_recalc
