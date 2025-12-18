# -*- coding: utf-8 -*-
import pandas as pd
from datetime import timedelta
from helpers import safe_string_conversion

def process_study_events(event_templates, actual_visits_df):
    """Process all study-level events (SIV, monitor, etc.)"""
    event_records = []
    
    if actual_visits_df is None:
        return event_records
    
    study_events = actual_visits_df[
        actual_visits_df.get('VisitType', 'patient').isin(['siv', 'monitor'])
    ]
    
    # OPTIMIZED: Use itertuples for faster iteration (2-3x faster than iterrows)
    for event_tuple in study_events.itertuples(index=False):
        # Validate required fields and skip if missing/invalid
        study = safe_string_conversion(getattr(event_tuple, 'Study', ''))
        visit_name = safe_string_conversion(getattr(event_tuple, 'VisitName', ''))
        visit_type = safe_string_conversion(getattr(event_tuple, 'VisitType', 'siv')).lower()
        
        # Skip if essential fields are missing or invalid
        if not study or study.lower() in ['nan', 'none', ''] or pd.isna(getattr(event_tuple, 'Study', None)):
            continue
        if not visit_name or visit_name.lower() in ['nan', 'none', ''] or pd.isna(getattr(event_tuple, 'VisitName', None)):
            continue
        if not visit_type or visit_type not in ['siv', 'monitor']:
            continue
            
        # Validate date
        actual_date = getattr(event_tuple, 'ActualDate', None)
        if pd.isna(actual_date):
            continue
        
        # Study events MUST have a valid template with site information
        payment = 0
        site = None
        
        if not event_templates.empty:
            template = event_templates[
                (event_templates['Study'] == study) & 
                (event_templates['VisitName'] == visit_name) &
                (event_templates['VisitType'] == visit_type)
            ]
            
            if not template.empty:
                template_row = template.iloc[0]
                payment = float(template_row.get('Payment', 0))
                site_value = template_row.get('SiteforVisit')
                
                # Validate site is not empty/invalid
                if pd.notna(site_value) and str(site_value).strip() not in ['', 'nan', 'None', 'null', 'NULL', 'Unknown Site', 'unknown site', 'UNKNOWN SITE', 'Default Site']:
                    site = str(site_value).strip()

        # Skip this event if no valid site found
        if site is None:
            from helpers import log_activity
            log_activity(f"WARNING: Skipping study event {visit_name} for {study} - no valid SiteforVisit found in trial schedule", level='warning')
            continue
        
        # All study events in actual_visits are completed
        visit_status = f"✅ {visit_type.upper()}_{study}"
        is_actual = True
        # payment already set from template (line 48)
        
        event_records.append({
            "Date": actual_date,
            "PatientID": f"{visit_type.upper()}_{study}",
            "Visit": visit_status,
            "Study": study,
            "Payment": payment,
            "SiteofVisit": site,
            "PatientOrigin": site,
            "IsActual": is_actual,
            "IsProposed": False,  # Study events are always actual when recorded
            "IsScreenFail": False,
            "IsOutOfProtocol": False,
            "VisitDay": 0 if visit_type == 'siv' else 999,
            "VisitName": visit_name,
            "IsStudyEvent": True,
            "EventType": visit_type,
        })
    
    # After the main loop, add summary logging
    if event_records:
        from helpers import log_activity
        log_activity(f"INFO: Processed {len(event_records)} study events with valid sites", level='info')
    
    return event_records

def detect_screen_failures(actual_visits_df, trials_df):
    """Detect screen failures from actual visits data"""
    screen_failures = {}
    unmatched_visits = []
    
    if actual_visits_df is None:
        return screen_failures, unmatched_visits
    
    screen_fail_visits = actual_visits_df[
        actual_visits_df["Notes"].str.contains("ScreenFail", case=False, na=False)
    ]
    
    # OPTIMIZED: Use itertuples for faster iteration (2-3x faster than iterrows)
    for visit_tuple in screen_fail_visits.itertuples(index=False):
        # Create patient-specific key
        patient_study_key = f"{visit_tuple.PatientID}_{visit_tuple.Study}"
        screen_fail_date = visit_tuple.ActualDate
        
        study_visits = trials_df[
            (trials_df["Study"] == visit_tuple.Study) & 
            (trials_df["VisitName"] == visit_tuple.VisitName)
        ]
        
        if len(study_visits) == 0:
            unmatched_visits.append(f"Screen failure visit '{visit_tuple.VisitName}' not found in study {visit_tuple.Study}")
            continue
        
        # Store earliest screen failure date for this specific patient
        if patient_study_key not in screen_failures or screen_fail_date < screen_failures[patient_study_key]:
            screen_failures[patient_study_key] = screen_fail_date
    
    return screen_failures, unmatched_visits

def detect_withdrawals(actual_visits_df, trials_df):
    """Detect patient withdrawals from actual visits data"""
    withdrawals = {}
    unmatched_visits = []
    
    if actual_visits_df is None:
        return withdrawals, unmatched_visits
    
    withdrawal_visits = actual_visits_df[
        actual_visits_df["Notes"].str.contains("Withdrawn", case=False, na=False)
    ]
    
    # OPTIMIZED: Use itertuples for faster iteration (2-3x faster than iterrows)
    for visit_tuple in withdrawal_visits.itertuples(index=False):
        # Create patient-specific key
        patient_study_key = f"{visit_tuple.PatientID}_{visit_tuple.Study}"
        withdrawal_date = visit_tuple.ActualDate
        
        study_visits = trials_df[
            (trials_df["Study"] == visit_tuple.Study) & 
            (trials_df["VisitName"] == visit_tuple.VisitName)
        ]
        
        if len(study_visits) == 0:
            unmatched_visits.append(f"Withdrawal visit '{visit_tuple.VisitName}' not found in study {visit_tuple.Study}")
            continue
        
        # Store earliest withdrawal date for this specific patient
        if patient_study_key not in withdrawals or withdrawal_date < withdrawals[patient_study_key]:
            withdrawals[patient_study_key] = withdrawal_date
    
    return withdrawals, unmatched_visits

def detect_deaths(actual_visits_df, trials_df):
    """Detect patient deaths from actual visits data"""
    deaths = {}
    unmatched_visits = []
    
    if actual_visits_df is None:
        return deaths, unmatched_visits
    
    death_visits = actual_visits_df[
        actual_visits_df["Notes"].str.contains("Died", case=False, na=False)
    ]
    
    # OPTIMIZED: Use itertuples for faster iteration (2-3x faster than iterrows)
    for visit_tuple in death_visits.itertuples(index=False):
        # Create patient-specific key
        patient_study_key = f"{visit_tuple.PatientID}_{visit_tuple.Study}"
        death_date = visit_tuple.ActualDate
        
        study_visits = trials_df[
            (trials_df["Study"] == visit_tuple.Study) & 
            (trials_df["VisitName"] == visit_tuple.VisitName)
        ]
        
        if len(study_visits) == 0:
            unmatched_visits.append(f"Death visit '{visit_tuple.VisitName}' not found in study {visit_tuple.Study}")
            continue
        
        # Store earliest death date for this specific patient
        if patient_study_key not in deaths or death_date < deaths[patient_study_key]:
            deaths[patient_study_key] = death_date
    
    return deaths, unmatched_visits

def detect_patient_stoppages(actual_visits_df, trials_df):
    """Detect screen failures, withdrawals, and deaths, returning combined stoppage dates"""
    screen_failures, screen_fail_unmatched = detect_screen_failures(actual_visits_df, trials_df)
    withdrawals, withdrawal_unmatched = detect_withdrawals(actual_visits_df, trials_df)
    deaths, death_unmatched = detect_deaths(actual_visits_df, trials_df)
    
    # Combine stoppages - use earliest date for each patient+study
    stoppages = {}
    for key in set(list(screen_failures.keys()) + list(withdrawals.keys()) + list(deaths.keys())):
        dates = []
        if key in screen_failures:
            dates.append(screen_failures[key])
        if key in withdrawals:
            dates.append(withdrawals[key])
        if key in deaths:
            dates.append(deaths[key])
        if dates:
            stoppages[key] = min(dates)
    
    unmatched_visits = screen_fail_unmatched + withdrawal_unmatched + death_unmatched
    return stoppages, unmatched_visits

def calculate_tolerance_windows(visit, baseline_date, visit_day):
    """Calculate tolerance windows for a visit"""
    # Determine expected date using optional month-based intervals
    try:
        unit = str(visit.get("IntervalUnit", "")).strip().lower() if hasattr(visit, 'get') else str(visit.get("IntervalUnit", "")).strip().lower()
    except Exception:
        unit = str(visit.get("IntervalUnit", "")).strip().lower()
    value = visit.get("IntervalValue", None)

    # Normalize baseline_date to Timestamp if needed
    if not isinstance(baseline_date, pd.Timestamp):
        baseline_date = pd.Timestamp(baseline_date)

    if unit == 'month' and pd.notna(value):
        try:
            months = int(value)
        except Exception:
            months = None
        if months is not None:
            # Calendar-aware month addition
            expected_date = baseline_date + pd.DateOffset(months=months)
        else:
            expected_date = baseline_date + timedelta(days=visit_day - 1)
    else:
        expected_date = baseline_date + timedelta(days=visit_day - 1)
    
    tolerance_before = 0
    tolerance_after = 0
    
    try:
        if pd.notna(visit.get("ToleranceBefore")):
            tolerance_before = int(float(visit.get("ToleranceBefore", 0)))
    except:
        tolerance_before = 0
        
    try:
        if pd.notna(visit.get("ToleranceAfter")):
            tolerance_after = int(float(visit.get("ToleranceAfter", 0)))
    except:
        tolerance_after = 0
    
    earliest_acceptable = expected_date - timedelta(days=tolerance_before)
    latest_acceptable = expected_date + timedelta(days=tolerance_after)
    
    return expected_date, earliest_acceptable, latest_acceptable, tolerance_before, tolerance_after

def is_visit_out_of_protocol(visit_date, visit_day, visit_name, earliest_acceptable, latest_acceptable):
    """Determine if a visit is out of protocol based on tolerance windows"""
    is_day_1 = (visit_day == 1)
    is_screening = visit_name.lower() in ['screening', 'screen', 'scr', 'v0']
    
    # Only visits after baseline/screening can be out of protocol
    if is_day_1 or is_screening:
        return False
    else:
        return visit_date < earliest_acceptable or visit_date > latest_acceptable

def create_tolerance_window_records(patient_id, study, site, patient_origin, expected_date, 
                                  tolerance_before, tolerance_after, visit_day, visit_name, 
                                  stoppage_date, actual_visit_date=None):
    """Create tolerance window records for a visit
    
    Args:
        stoppage_date: Date of screen failure, withdrawal, or death (stops future visits)
    """
    records = []
    
    # Add tolerance windows before the visit
    if visit_day > 1:
        for i in range(1, tolerance_before + 1):
            tolerance_date = expected_date - timedelta(days=i)
            if stoppage_date is not None and tolerance_date > stoppage_date:
                continue
            if actual_visit_date is not None and tolerance_date == actual_visit_date:
                continue  # Don't duplicate actual visit date
            
            records.append({
                "Date": tolerance_date,
                "PatientID": patient_id,
                "Visit": "-",
                "Study": study,
                "Payment": 0,
                "SiteofVisit": site,
                "PatientOrigin": patient_origin,
                "IsActual": False,
                "IsProposed": False,  # Tolerance markers are never proposed
                "IsScreenFail": False,
                "IsOutOfProtocol": False,
                "VisitDay": visit_day,
                "VisitName": visit_name
            })

    # Add tolerance windows after the visit
    for i in range(1, tolerance_after + 1):
        tolerance_date = expected_date + timedelta(days=i)
        if stoppage_date is not None and tolerance_date > stoppage_date:
            continue
        if actual_visit_date is not None and tolerance_date == actual_visit_date:
            continue  # Don't duplicate actual visit date
        
        records.append({
            "Date": tolerance_date,
            "PatientID": patient_id,
            "Visit": "+",
            "Study": study,
            "Payment": 0,
            "SiteofVisit": site,
            "PatientOrigin": patient_origin,
            "IsActual": False,
            "IsProposed": False,  # Tolerance markers are never proposed
            "IsScreenFail": False,
            "IsOutOfProtocol": False,
            "VisitDay": visit_day,
            "VisitName": visit_name
        })
    
    return records
