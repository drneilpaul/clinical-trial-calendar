import pandas as pd
from datetime import timedelta
from helpers import safe_string_conversion, get_screen_failure_key

def process_study_events(event_templates, actual_visits_df):
    """Process all study-level events (SIV, monitor, etc.)"""
    event_records = []
    
    if actual_visits_df is None or event_templates.empty:
        return event_records
    
    study_events = actual_visits_df[
        actual_visits_df.get('VisitType', 'patient').isin(['siv', 'monitor'])
    ]
    
    for _, event_visit in study_events.iterrows():
        # Validate required fields and skip if missing/invalid
        study = safe_string_conversion(event_visit.get('Study', ''))
        visit_name = safe_string_conversion(event_visit.get('VisitName', ''))
        visit_type = safe_string_conversion(event_visit.get('VisitType', 'siv')).lower()
        status = safe_string_conversion(event_visit.get('Status', 'completed')).lower()
        
        # Skip if essential fields are missing or invalid - simplified and safe
        if pd.isna(event_visit.get('Study')) or str(event_visit.get('Study', '')).strip() == '':
            continue
        if pd.isna(event_visit.get('VisitName')) or str(event_visit.get('VisitName', '')).strip() == '':
            continue
        if visit_type not in ['siv', 'monitor']:
            continue
            
        # Validate date
        if pd.isna(event_visit.get('ActualDate')):
            continue
        
        template = event_templates[
            (event_templates['Study'] == study) & 
            (event_templates['VisitName'] == visit_name) &
            (event_templates['VisitType'] == visit_type)
        ]
        
        if template.empty:
            continue
        
        template_row = template.iloc[0]
        
        if status == 'completed':
            payment = float(template_row.get('Payment', 0))
            visit_status = f"✅ {visit_type.upper()}_{study}"
            is_actual = True
        elif status == 'proposed':
            payment = 0
            visit_status = f"{visit_type.upper()}_{study} (PROPOSED)"
            is_actual = False
        elif status == 'cancelled':
            payment = 0
            visit_status = f"{visit_type.upper()}_{study} (CANCELLED)"
            is_actual = False
        else:
            continue
        
        site = safe_string_conversion(template_row.get('SiteforVisit', 'Unknown Site'))
        
        event_records.append({
            "Date": event_visit['ActualDate'],
            "PatientID": f"{visit_type.upper()}_{study}",
            "Visit": visit_status,
            "Study": study,
            "Payment": payment,
            "SiteofVisit": site,
            "PatientOrigin": site,
            "IsActual": is_actual,
            "IsScreenFail": False,
            "IsOutOfProtocol": False,
            "VisitDay": 0 if visit_type == 'siv' else 999,
            "VisitName": visit_name,
            "IsStudyEvent": True,
            "EventType": visit_type,
            "EventStatus": status
        })
    
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
    
    # Sort by date to ensure we process chronologically and avoid race conditions
    if not screen_fail_visits.empty:
        screen_fail_visits = screen_fail_visits.sort_values('ActualDate')
    
    for _, visit in screen_fail_visits.iterrows():
        # Create patient-specific key using centralized function
        patient_study_key = get_screen_failure_key(visit['PatientID'], visit['Study'])
        screen_fail_date = visit['ActualDate']
        
        study_visits = trials_df[
            (trials_df["Study"] == visit["Study"]) & 
            (trials_df["VisitName"] == visit["VisitName"])
        ]
        
        if len(study_visits) == 0:
            unmatched_visits.append(f"Screen failure visit '{visit['VisitName']}' not found in study {visit['Study']}")
            continue
        
        # Store earliest screen failure date for this specific patient
        if patient_study_key not in screen_failures or screen_fail_date < screen_failures[patient_study_key]:
            screen_failures[patient_study_key] = screen_fail_date
    
    return screen_failures, unmatched_visits

def calculate_tolerance_windows(visit, baseline_date, visit_day):
    """Calculate tolerance windows for a visit"""
    expected_date = baseline_date + timedelta(days=visit_day - 1)
    
    tolerance_before = 0
    tolerance_after = 0
    
    # Use centralized numeric conversion from helpers
    from helpers import clean_numeric_for_display
    tolerance_before = int(clean_numeric_for_display(visit.get("ToleranceBefore", 0)))
        
    tolerance_after = int(clean_numeric_for_display(visit.get("ToleranceAfter", 0)))
    
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
                                  screen_fail_date, actual_visit_date=None):
    """Create tolerance window records for a visit"""
    records = []
    
    # Add tolerance windows before the visit
    if visit_day > 1:
        for i in range(1, tolerance_before + 1):
            tolerance_date = expected_date - timedelta(days=i)
            if screen_fail_date is not None and tolerance_date > screen_fail_date:
                continue
            if actual_visit_date is not None and tolerance_date.date() == actual_visit_date.date():
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
                "IsScreenFail": False,
                "IsOutOfProtocol": False,
                "VisitDay": visit_day,
                "VisitName": visit_name
            })

    # Add tolerance windows after the visit
    for i in range(1, tolerance_after + 1):
        tolerance_date = expected_date + timedelta(days=i)
        if screen_fail_date is not None and tolerance_date > screen_fail_date:
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
            "IsScreenFail": False,
            "IsOutOfProtocol": False,
            "VisitDay": visit_day,
            "VisitName": visit_name
        })
    
    return records
