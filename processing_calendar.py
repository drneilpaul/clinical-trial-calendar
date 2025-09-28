import pandas as pd
import streamlit as st
from datetime import timedelta
from helpers import (safe_string_conversion, standardize_visit_columns, validate_required_columns, 
                    get_financial_year_start_year, is_financial_year_end, format_site_events)

def process_study_events(event_templates, actual_visits_df):
    """Process all study-level events (SIV, monitor, etc.)"""
    event_records = []
    
    if actual_visits_df is None or event_templates.empty:
        return event_records
    
    study_events = actual_visits_df[
        actual_visits_df.get('VisitType', 'patient').isin(['siv', 'monitor'])
    ]
    
    for _, event_visit in study_events.iterrows():
        study = str(event_visit['Study'])
        visit_name = str(event_visit['VisitName'])
        visit_type = str(event_visit.get('VisitType', 'siv'))
        status = str(event_visit.get('Status', 'completed')).lower()
        
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
        
        site = str(template_row.get('SiteforVisit', 'Unknown Site'))
        
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

def build_calendar(patients_df, trials_df, actual_visits_df=None):
    """Enhanced calendar builder with study events support"""
    
    # Clean columns
    patients_df.columns = patients_df.columns.str.strip()
    trials_df.columns = trials_df.columns.str.strip()
    if actual_visits_df is not None:
        actual_visits_df.columns = actual_visits_df.columns.str.strip()

    # Validate required columns
    validate_required_columns(patients_df, {"PatientID", "Study", "StartDate"}, "Patients file")
    validate_required_columns(trials_df, {"Study", "Day", "VisitName"}, "Trials file")

    # Standardize visit columns
    trials_df = standardize_visit_columns(trials_df)
    if actual_visits_df is not None:
        validate_required_columns(actual_visits_df, {"PatientID", "Study", "VisitName", "ActualDate"}, "Actual visits file")
        actual_visits_df = standardize_visit_columns(actual_visits_df)

    # Check for SiteforVisit column
    if "SiteforVisit" not in trials_df.columns:
        trials_df["SiteforVisit"] = "Default Site"

    screen_failures = {}
    unmatched_visits = []
    
    # Process actual visits if provided
    if actual_visits_df is not None:
        actual_visits_df["PatientID"] = safe_string_conversion(actual_visits_df["PatientID"])
        actual_visits_df["Study"] = safe_string_conversion(actual_visits_df["Study"])
        actual_visits_df["VisitName"] = safe_string_conversion(actual_visits_df["VisitName"])
        
        if not pd.api.types.is_datetime64_any_dtype(actual_visits_df["ActualDate"]):
            actual_visits_df["ActualDate"] = pd.to_datetime(actual_visits_df["ActualDate"], dayfirst=True, errors="coerce")
        
        if "Notes" not in actual_visits_df.columns:
            actual_visits_df["Notes"] = ""
        else:
            actual_visits_df["Notes"] = safe_string_conversion(actual_visits_df["Notes"], "")
        
        if "VisitType" not in actual_visits_df.columns:
            actual_visits_df["VisitType"] = "patient"
        
        if "Status" not in actual_visits_df.columns:
            actual_visits_df["Status"] = "completed"

        # Detect screen failures
        screen_fail_visits = actual_visits_df[
            actual_visits_df["Notes"].str.contains("ScreenFail", case=False, na=False)
        ]
        
        for _, visit in screen_fail_visits.iterrows():
            patient_study_key = f"{visit['PatientID']}_{visit['Study']}"
            screen_fail_date = visit['ActualDate']
            
            study_visits = trials_df[
                (trials_df["Study"] == visit["Study"]) & 
                (trials_df["VisitName"] == visit["VisitName"])
            ]
            
            if len(study_visits) == 0:
                unmatched_visits.append(f"Screen failure visit '{visit['VisitName']}' not found in study {visit['Study']}")
                continue
            
            if patient_study_key not in screen_failures or screen_fail_date < screen_failures[patient_study_key]:
                screen_failures[patient_study_key] = screen_fail_date

        actual_visits_df["VisitKey"] = (
            safe_string_conversion(actual_visits_df["PatientID"]) + "_" +
            safe_string_conversion(actual_visits_df["Study"]) + "_" +
            safe_string_conversion(actual_visits_df["VisitName"])
        )

    # Normalize column names
    column_mapping = {
        'Income': 'Payment',
        'Tolerance Before': 'ToleranceBefore',
        'Tolerance After': 'ToleranceAfter'
    }
    trials_df = trials_df.rename(columns=column_mapping)

    # Process patient data types
    patients_df["PatientID"] = safe_string_conversion(patients_df["PatientID"])
    patients_df["Study"] = safe_string_conversion(patients_df["Study"])
    
    if not pd.api.types.is_datetime64_any_dtype(patients_df["StartDate"]):
        patients_df["StartDate"] = pd.to_datetime(patients_df["StartDate"], dayfirst=True, errors="coerce")
    
    # Process trials data types
    trials_df["Study"] = safe_string_conversion(trials_df["Study"])
    trials_df["VisitName"] = safe_string_conversion(trials_df["VisitName"])
    trials_df["SiteforVisit"] = safe_string_conversion(trials_df["SiteforVisit"])
    
    try:
        trials_df["Day"] = pd.to_numeric(trials_df["Day"], errors='coerce').fillna(1).astype(int)
    except:
        st.error("Invalid 'Day' values in trials file. Days must be numeric.")
        raise ValueError("Invalid Day column in trials file")

    # Check for patient origin site column
    patient_origin_col = None
    possible_origin_cols = ['PatientSite', 'OriginSite', 'Practice', 'PatientPractice', 'HomeSite', 'Site']
    for col in possible_origin_cols:
        if col in patients_df.columns:
            patient_origin_col = col
            break
    
    if patient_origin_col:
        patients_df['OriginSite'] = safe_string_conversion(patients_df[patient_origin_col], "Unknown Origin")
    else:
        patients_df['OriginSite'] = "Unknown Origin"

    # Create patient-site mapping
    if patient_origin_col:
        patients_df['Site'] = patients_df['OriginSite']
    else:
        patient_site_mapping = {}
        for _, patient in patients_df.iterrows():
            study = patient["Study"]
            patient_id = patient["PatientID"]
            
            study_sites = trials_df[trials_df["Study"] == study]["SiteforVisit"].unique()
            if len(study_sites) > 0:
                patient_site_mapping[patient_id] = study_sites[0]
            else:
                patient_site_mapping[patient_id] = f"{study}_Site"
        
        patients_df['Site'] = patients_df['PatientID'].map(patient_site_mapping).fillna("Unknown Site")

    # Validate Day 1 baseline exists for each study
    for study in patients_df["Study"].unique():
        study_visits = trials_df[trials_df["Study"] == study]
        day_1_visits = study_visits[study_visits["Day"] == 1]
        
        if len(day_1_visits) == 0:
            raise ValueError(f"Study {study} has no Day 1 visit defined. Day 1 is required as baseline.")
        elif len(day_1_visits) > 1:
            visit_names = day_1_visits["VisitName"].tolist()
            raise ValueError(f"Study {study} has multiple Day 1 visits: {visit_names}. Only one Day 1 visit allowed.")

    # Separate visit types - FIXED: Handle missing VisitType column safely
    if 'VisitType' in trials_df.columns:
        patient_visits = trials_df[
            (trials_df['VisitType'] == 'patient') |
            (pd.isna(trials_df['VisitType']))
        ]
        
        study_event_templates = trials_df[
            trials_df['VisitType'].isin(['siv', 'monitor'])
        ]
    else:
        patient_visits = trials_df.copy()
        study_event_templates = pd.DataFrame()

    # Build visit records
    visit_records = []
    
    # Process study events first
    if not study_event_templates.empty:
        visit_records.extend(process_study_events(study_event_templates, actual_visits_df))
    
    screen_fail_exclusions = 0
    actual_visits_used = 0
    recalculated_patients = []
    out_of_window_visits = []
    patients_with_no_visits = []
    processing_messages = []
    
    for _, patient in patients_df.iterrows():
        patient_id = str(patient["PatientID"])
        study = str(patient["Study"])
        start_date = patient["StartDate"]
        patient_origin = str(patient["OriginSite"])
        
        if pd.isna(start_date):
            continue

        patient_study_key = f"{patient_id}_{study}"
        screen_fail_date = screen_failures.get(patient_study_key)

        study_visits = patient_visits[patient_visits["Study"] == study].sort_values('Day').copy()
        
        if len(study_visits) == 0:
            patients_with_no_visits.append(f"{patient_id} (Study: {study})")
            continue

        day_1_visits = study_visits[study_visits["Day"] == 1]
        baseline_visit_name = str(day_1_visits.iloc[0]["VisitName"])

        patient_actual_visits = {}
        if actual_visits_df is not None:
            patient_actuals = actual_visits_df[
                (actual_visits_df["PatientID"] == patient_id) & 
                (actual_visits_df["Study"] == study) &
                (actual_visits_df.get("VisitType", "patient") == "patient")
            ]
            
            for _, actual_visit in patient_actuals.iterrows():
                visit_name = str(actual_visit["VisitName"])
                
                matching_trial = study_visits[study_visits["VisitName"] == visit_name]
                if len(matching_trial) == 0:
                    unmatched_visits.append(f"Patient {patient_id}, Study {study}: Visit '{visit_name}' not found in trials")
                    continue
                
                patient_actual_visits[visit_name] = actual_visit
                actual_visits_used += 1

        baseline_date = start_date
        patient_needs_recalc = False
        
        if baseline_visit_name in patient_actual_visits:
            actual_baseline_date = patient_actual_visits[baseline_visit_name]["ActualDate"]
            if actual_baseline_date != start_date:
                baseline_date = actual_baseline_date
                patient_needs_recalc = True

        for _, visit in study_visits.iterrows():
            visit_day = int(visit["Day"])
            visit_name = str(visit["VisitName"])
            
            actual_visit_data = patient_actual_visits.get(visit_name)
            
            if actual_visit_data is not None:
                visit_date = actual_visit_data["ActualDate"]
                
                trial_payment = visit.get("Payment", 0)
                if pd.notna(trial_payment):
                    payment = float(trial_payment)
                else:
                    payment = 0.0
                
                notes = str(actual_visit_data.get("Notes", ""))
                is_screen_fail = "ScreenFail" in notes
                
                if screen_fail_date is not None and visit_date > screen_fail_date:
                    visit_status = f"⚠️ DATA ERROR {visit_name}"
                    is_out_of_protocol = False
                    processing_messages.append(f"⚠️ Patient {patient_id} has visit '{visit_name}' on {visit_date.strftime('%Y-%m-%d')} AFTER screen failure")
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
                    
                    is_day_1 = (visit_day == 1)
                    
                    if is_day_1:
                        is_out_of_protocol = False
                    else:
                        is_out_of_protocol = visit_date < earliest_acceptable or visit_date > latest_acceptable
                    
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
                
                visit_records.append({
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
                })
                
            else:
                scheduled_date = baseline_date + timedelta(days=visit_day - 1)
                
                if screen_fail_date is not None and scheduled_date > screen_fail_date:
                    screen_fail_exclusions += 1
                    continue
                
                try:
                    payment = float(visit.get("Payment", 0) or 0)
                except:
                    payment = 0.0
                    
                visit_status = visit_name
                
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
                
                site = str(visit.get("SiteforVisit", "Unknown Site"))
                
                visit_records.append({
                    "Date": scheduled_date,
                    "PatientID": patient_id,
                    "Visit": visit_status,
                    "Study": study,
                    "Payment": payment,
                    "SiteofVisit": site,
                    "PatientOrigin": patient_origin,
                    "IsActual": False,
                    "IsScreenFail": False,
                    "IsOutOfProtocol": False,
                    "VisitDay": visit_day,
                    "VisitName": visit_name
                })

                if visit_day > 1:
                    for i in range(1, tolerance_before + 1):
                        tolerance_date = scheduled_date - timedelta(days=i)
                        if screen_fail_date is not None and tolerance_date > screen_fail_date:
                            continue
                        visit_records.append({
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

                for i in range(1, tolerance_after + 1):
                    tolerance_date = scheduled_date + timedelta(days=i)
                    if screen_fail_date is not None and tolerance_date > screen_fail_date:
                        continue
                    visit_records.append({
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
        
        if patient_needs_recalc:
            recalculated_patients.append(f"{patient_id} ({study})")

    # Create visits DataFrame
    visits_df = pd.DataFrame(visit_records)

    if visits_df.empty:
        raise ValueError("No visits generated. Check that Patient 'Study' matches Trial 'Study' values and StartDate is populated.")

    # Report processing issues
    if unmatched_visits:
        for unmatched in unmatched_visits:
            processing_messages.append(f"⚠️ {unmatched}")

    # Collect processing messages
    if patients_with_no_visits:
        processing_messages.append(f"⚠️ {len(patients_with_no_visits)} patient(s) skipped due to missing study definitions: {', '.join(patients_with_no_visits)}")
        
    if recalculated_patients:
        processing_messages.append(f"📅 Recalculated visit schedules for {len(recalculated_patients)} patient(s) based on actual Day 1 baseline: {', '.join(recalculated_patients)}")

    if out_of_window_visits:
        processing_messages.append(f"🔴 {len(out_of_window_visits)} visit(s) occurred outside tolerance windows (marked as OUT OF PROTOCOL)")

    if actual_visits_df is not None:
        processing_messages.append(f"✅ {actual_visits_used} actual visits matched and used in calendar")
        unmatched_actual = len(actual_visits_df[actual_visits_df.get('VisitType', 'patient') == 'patient']) - actual_visits_used
        if unmatched_actual > 0:
            processing_messages.append(f"⚠️ {unmatched_actual} actual visit records could not be matched to scheduled visits")

    if screen_fail_exclusions > 0:
        processing_messages.append(f"⚠️ {screen_fail_exclusions} visits were excluded because they occur after screen failure dates")

    # Build calendar dataframe with enhanced site events columns
    min_date = visits_df["Date"].min() - timedelta(days=1)
    max_date = visits_df["Date"].max() + timedelta(days=1)
    calendar_dates = pd.date_range(start=min_date, end=max_date)
    calendar_df = pd.DataFrame({"Date": calendar_dates})
    calendar_df["Day"] = calendar_df["Date"].dt.day_name()

    # Group patients by visit site for three-level headers
    patients_df["ColumnID"] = patients_df["Study"] + "_" + patients_df["PatientID"]
    
    # Get unique visit sites
    unique_visit_sites = sorted(visits_df["SiteofVisit"].unique())
    
    # Create enhanced column structure with site events
    ordered_columns = ["Date", "Day"]
    site_column_mapping = {}
    
    for visit_site in unique_visit_sites:
        site_visits = visits_df[visits_df["SiteofVisit"] == visit_site]
        site_patients_info = []
        
        # Get unique patient-study combinations at this visit site (exclude study events)
        for patient_study in site_visits[['PatientID', 'Study']].drop_duplicates().itertuples():
            patient_id = patient_study.PatientID
            study = patient_study.Study
            
            # Skip study event pseudo-patients
            if patient_id.startswith(('SIV_', 'MONITOR_')):
                continue
            
            patient_row = patients_df[
                (patients_df['PatientID'] == patient_id) & 
                (patients_df['Study'] == study)
            ]
            
            if not patient_row.empty:
                origin_site = patient_row.iloc[0]['Site']
                col_id = f"{study}_{patient_id}"
                
                site_patients_info.append({
                    'col_id': col_id,
                    'study': study,
                    'patient_id': patient_id,
                    'origin_site': origin_site
                })
        
        # Sort by study then patient ID for consistent ordering
        site_patients_info.sort(key=lambda x: (x['study'], x['patient_id']))
        
        # Add patient columns for this visit site
        site_columns = []
        for patient_info in site_patients_info:
            col_id = patient_info['col_id']
            ordered_columns.append(col_id)
            site_columns.append(col_id)
            calendar_df[col_id] = ""
        
        # Add site events column
        events_col = f"{visit_site}_Events"
        ordered_columns.append(events_col)
        site_columns.append(events_col)
        calendar_df[events_col] = ""
        
        site_column_mapping[visit_site] = {
            'columns': site_columns,
            'patient_info': site_patients_info,
            'events_column': events_col
        }

    # Create income tracking columns
    for study in trials_df["Study"].unique():
        income_col = f"{study} Income"
        calendar_df[income_col] = 0.0
    
    calendar_df["Daily Total"] = 0.0

    # Fill calendar with improved duplicate handling and site events
    for i, row in calendar_df.iterrows():
        date = row["Date"]
        visits_today = visits_df[visits_df["Date"] == date]
        daily_total = 0.0

        # Group events by site for the events columns
        site_events = {}

        for _, visit in visits_today.iterrows():
            study = str(visit["Study"])
            pid = str(visit["PatientID"])
            visit_info = visit["Visit"]
            payment = float(visit["Payment"]) if pd.notna(visit["Payment"]) else 0.0
            is_actual = visit.get("IsActual", False)
            visit_site = visit["SiteofVisit"]

            # Handle study events
            if visit.get("IsStudyEvent", False):
                if visit_site not in site_events:
                    site_events[visit_site] = []
                
                # Format event for display
                event_type = visit.get("EventType", "").upper()
                event_display = f"{event_type}_{study}"
                if "PROPOSED" in visit_info:
                    event_display += " (PROPOSED)"
                elif "CANCELLED" in visit_info:
                    event_display += " (CANCELLED)"
                else:
                    event_display = f"✅ {event_display}"
                
                site_events[visit_site].append(event_display)
                
                # Add to study income
                income_col = f"{study} Income"
                if income_col in calendar_df.columns and payment > 0:
                    calendar_df.at[i, income_col] += payment
                    daily_total += payment

            else:
                # Handle regular patient visits
                col_id = f"{study}_{pid}"
                if col_id in calendar_df.columns:
                    current_value = calendar_df.at[i, col_id]
                    
                    if current_value == "":
                        calendar_df.at[i, col_id] = visit_info
                    else:
                        # Handle multiple visits on same day
                        if visit_info in ["-", "+"]:
                            if not any(symbol in str(current_value) for symbol in ["✅", "🔴", "⚠️"]):
                                if current_value in ["-", "+", ""]:
                                    calendar_df.at[i, col_id] = visit_info
                                else:
                                    calendar_df.at[i, col_id] = f"{current_value}, {visit_info}"
                        else:
                            # This is a main visit
                            if current_value in ["-", "+", ""]:
                                calendar_df.at[i, col_id] = visit_info
                            else:
                                calendar_df.at[i, col_id] = f"{current_value}, {visit_info}"

                # Count payments for actual visits and scheduled main visits
                if (is_actual) or (not is_actual and visit_info not in ("-", "+")):
                    income_col = f"{study} Income"
                    if income_col in calendar_df.columns:
                        calendar_df.at[i, income_col] += payment
                        daily_total += payment

        # Fill site events columns
        for site, events in site_events.items():
            events_col = f"{site}_Events"
            if events_col in calendar_df.columns:
                calendar_df.at[i, events_col] = format_site_events(events)

        calendar_df.at[i, "Daily Total"] = daily_total

    # Calculate monthly and financial year totals
    calendar_df["MonthPeriod"] = calendar_df["Date"].dt.to_period("M")
    monthly_totals = calendar_df.groupby("MonthPeriod")["Daily Total"].sum()
    calendar_df["IsMonthEnd"] = calendar_df["Date"] == calendar_df["Date"] + pd.offsets.MonthEnd(0)
    calendar_df["Monthly Total"] = calendar_df.apply(
        lambda r: monthly_totals.get(r["MonthPeriod"], 0.0) if r["IsMonthEnd"] else pd.NA, axis=1
    )

    # Use centralized financial year calculation
    calendar_df["FYStart"] = calendar_df["Date"].apply(get_financial_year_start_year)
    fy_totals = calendar_df.groupby("FYStart")["Daily Total"].sum()
    calendar_df["IsFYE"] = calendar_df["Date"].apply(is_financial_year_end)
    calendar_df["FY Total"] = calendar_df.apply(
        lambda r: fy_totals.get(r["FYStart"], 0.0) if r["IsFYE"] else pd.NA, axis=1
    )

    stats = {
        "total_visits": len([v for v in visit_records if not v.get('IsActual', False) and v['Visit'] not in ['-', '+'] and not v.get('IsStudyEvent', False)]),
        "total_income": visits_df["Payment"].sum(),
        "messages": processing_messages,
        "out_of_window_visits": out_of_window_visits
    }

    return visits_df, calendar_df, stats, processing_messages, site_column_mapping, unique_visit_sites
