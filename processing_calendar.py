import pandas as pd
from datetime import timedelta

def build_calendar(patients_df, trials_df, actual_visits_df=None):
    # Clean columns
    patients_df.columns = patients_df.columns.str.strip()
    trials_df.columns = trials_df.columns.str.strip()
    if actual_visits_df is not None:
        actual_visits_df.columns = actual_visits_df.columns.str.strip()

    required_patients = {"PatientID", "Study", "StartDate"}
    required_trials = {"Study", "Day", "VisitName"}

    if not required_patients.issubset(patients_df.columns):
        raise ValueError(f"⚠ Patients file missing required columns: {required_patients - set(patients_df.columns)}")
    if not required_trials.issubset(trials_df.columns):
        raise ValueError(f"⚠ Trials file missing required columns: {required_trials - set(trials_df.columns)}")

    # Check for SiteforVisit column
    if "SiteforVisit" not in trials_df.columns:
        trials_df["SiteforVisit"] = "Default Site"

    screen_failures = {}
    unmatched_visits = []
    
    if actual_visits_df is not None:
        required_actual = {"PatientID", "Study", "VisitName", "ActualDate"}
        if not required_actual.issubset(actual_visits_df.columns):
            raise ValueError(f"⚠ Actual visits file missing required columns: {required_actual}")

        # Ensure proper data types
        actual_visits_df["PatientID"] = actual_visits_df["PatientID"].astype(str)
        actual_visits_df["Study"] = actual_visits_df["Study"].astype(str)
        actual_visits_df["VisitName"] = actual_visits_df["VisitName"].astype(str)
        actual_visits_df["ActualDate"] = pd.to_datetime(actual_visits_df["ActualDate"], dayfirst=True, errors="coerce")
        
        # Handle optional columns
        if "ActualPayment" not in actual_visits_df.columns:
            actual_visits_df["ActualPayment"] = None
        if "Notes" not in actual_visits_df.columns:
            actual_visits_df["Notes"] = ""
        else:
            actual_visits_df["Notes"] = actual_visits_df["Notes"].fillna("").astype(str)

        # Detect screen failures - only valid up to Day 1
        screen_fail_visits = actual_visits_df[
            actual_visits_df["Notes"].str.contains("ScreenFail", case=False, na=False)
        ]
        
        for _, visit in screen_fail_visits.iterrows():
            # Check if this visit is valid for screen failure (Day <= 1)
            study_visits = trials_df[
                (trials_df["Study"] == visit["Study"]) & 
                (trials_df["VisitName"] == visit["VisitName"])
            ]
            
            if len(study_visits) == 0:
                unmatched_visits.append(f"Screen failure visit '{visit['VisitName']}' not found in study {visit['Study']}")
                continue
                
            visit_day = study_visits.iloc[0]["Day"]
            if visit_day > 1:
                raise ValueError(f"Screen failure cannot occur after Day 1. Visit '{visit['VisitName']}' is on Day {visit_day}")
            
            patient_study_key = f"{visit['PatientID']}_{visit['Study']}"
            screen_fail_date = visit['ActualDate']
            if patient_study_key not in screen_failures or screen_fail_date < screen_failures[patient_study_key]:
                screen_failures[patient_study_key] = screen_fail_date

        # Create lookup key for actual visits
        actual_visits_df["VisitKey"] = (
            actual_visits_df["PatientID"] + "_" +
            actual_visits_df["Study"] + "_" +
            actual_visits_df["VisitName"]
        )

    # Normalize column names
    column_mapping = {
        'Income': 'Payment',
        'Tolerance Before': 'ToleranceBefore',
        'Tolerance After': 'ToleranceAfter'
    }
    trials_df = trials_df.rename(columns=column_mapping)

    # Process patient data types
    patients_df["PatientID"] = patients_df["PatientID"].astype(str)
    patients_df["Study"] = patients_df["Study"].astype(str)
    patients_df["StartDate"] = pd.to_datetime(patients_df["StartDate"], dayfirst=True, errors="coerce")
    
    # Ensure data types in trials
    trials_df["Study"] = trials_df["Study"].astype(str)
    trials_df["VisitName"] = trials_df["VisitName"].astype(str)
    trials_df["SiteforVisit"] = trials_df["SiteforVisit"].astype(str)
    trials_df["Day"] = trials_df["Day"].astype(int)

    # Check for patient origin site column
    patient_origin_col = None
    possible_origin_cols = ['PatientSite', 'OriginSite', 'Practice', 'PatientPractice', 'HomeSite', 'Site']
    for col in possible_origin_cols:
        if col in patients_df.columns:
            patient_origin_col = col
            break
    
    if patient_origin_col:
        patients_df['OriginSite'] = patients_df[patient_origin_col].astype(str)
    else:
        patients_df['OriginSite'] = "Unknown Origin"

    # Create patient-site mapping
    if patient_origin_col:
        patients_df['Site'] = patients_df['OriginSite']
    else:
        # Fallback: use site from trials file
        patient_site_mapping = {}
        for _, patient in patients_df.iterrows():
            study = patient["Study"]
            study_sites = trials_df[trials_df["Study"] == study]["SiteforVisit"].unique()
            if len(study_sites) > 0:
                patient_site_mapping[patient["PatientID"]] = study_sites[0]
            else:
                patient_site_mapping[patient["PatientID"]] = f"{study}_Site"
        
        patients_df['Site'] = patients_df['PatientID'].map(patient_site_mapping)

    # Validate Day 1 baseline exists for each study
    for study in patients_df["Study"].unique():
        study_visits = trials_df[trials_df["Study"] == study]
        day_1_visits = study_visits[study_visits["Day"] == 1]
        
        if len(day_1_visits) == 0:
            raise ValueError(f"Study {study} has no Day 1 visit defined. Day 1 is required as baseline.")
        elif len(day_1_visits) > 1:
            visit_names = day_1_visits["VisitName"].tolist()
            raise ValueError(f"Study {study} has multiple Day 1 visits: {visit_names}. Only one Day 1 visit allowed.")

    # Build visit records
    visit_records = []
    screen_fail_exclusions = 0
    actual_visits_used = 0
    recalculated_patients = []
    out_of_window_visits = []
    patients_with_no_visits = []
    processing_messages = []
    
    for _, patient in patients_df.iterrows():
        patient_id = patient["PatientID"]
        study = patient["Study"]
        start_date = patient["StartDate"]
        patient_origin = patient["OriginSite"]
        
        if pd.isna(start_date):
            continue

        # Check if this patient has a screen failure
        patient_study_key = f"{patient_id}_{study}"
        screen_fail_date = screen_failures.get(patient_study_key)

        # Get all visits for this study and sort by Day
        study_visits = trials_df[trials_df["Study"] == study].sort_values('Day').copy()
        
        if len(study_visits) == 0:
            patients_with_no_visits.append(f"{patient_id} (Study: {study})")
            continue

        # Find Day 1 baseline visit
        day_1_visits = study_visits[study_visits["Day"] == 1]
        baseline_visit_name = day_1_visits.iloc[0]["VisitName"]

        # Get all actual visits for this patient
        patient_actual_visits = {}
        if actual_visits_df is not None:
            patient_actuals = actual_visits_df[
                (actual_visits_df["PatientID"] == patient_id) & 
                (actual_visits_df["Study"] == study)
            ]
            
            for _, actual_visit in patient_actuals.iterrows():
                visit_name = actual_visit["VisitName"]
                
                # Check if this visit name exists in trials
                matching_trial = study_visits[study_visits["VisitName"] == visit_name]
                if len(matching_trial) == 0:
                    unmatched_visits.append(f"Patient {patient_id}, Study {study}: Visit '{visit_name}' not found in trials")
                    continue
                
                patient_actual_visits[visit_name] = actual_visit
                actual_visits_used += 1

        # Determine baseline date - Day 1 actual date or start date
        baseline_date = start_date  # Default baseline
        day_1_actual_date = None
        patient_needs_recalc = False
        
        # Check if we have an actual Day 1 visit
        if baseline_visit_name in patient_actual_visits:
            day_1_actual_date = patient_actual_visits[baseline_visit_name]["ActualDate"]
            if day_1_actual_date != start_date:
                baseline_date = day_1_actual_date
                patient_needs_recalc = True

        # Process all visits for this patient
        for _, visit in study_visits.iterrows():
            visit_day = visit["Day"]
            visit_name = visit["VisitName"]
            
            # Check if we have an actual visit for this visit name
            actual_visit_data = patient_actual_visits.get(visit_name)
            
            if actual_visit_data is not None:
                # This is an actual visit
                visit_date = actual_visit_data["ActualDate"]
                payment = float(actual_visit_data.get("ActualPayment") or visit.get("Payment", 0) or 0.0)
                notes = actual_visit_data.get("Notes", "")
                
                # Check for screen failure
                is_screen_fail = "ScreenFail" in str(notes)
                
                # Check if this visit is after a screen failure for this patient
                if screen_fail_date is not None and visit_date > screen_fail_date:
                    error_msg = (f"DATA ERROR: Patient {patient_id} has visit '{visit_name}' on {visit_date.strftime('%Y-%m-%d')} "
                               f"AFTER their screen failure date ({screen_fail_date.strftime('%Y-%m-%d')})")
                    processing_messages.append(f"⚠ {error_msg}")
                    visit_status = f"⚠ DATA ERROR {visit_name}"
                    is_out_of_protocol = False
                else:
                    # Normal processing - calculate expected date from Day 1 baseline
                    expected_date = baseline_date + timedelta(days=visit_day - 1)  # Day 1 = baseline, Day 2 = baseline + 1, etc.
                    
                    # Handle tolerance
                    tolerance_before = int(visit.get("ToleranceBefore", 0) or 0)
                    tolerance_after = int(visit.get("ToleranceAfter", 0) or 0)
                    
                    earliest_acceptable = expected_date - timedelta(days=tolerance_before)
                    latest_acceptable = expected_date + timedelta(days=tolerance_after)
                    
                    # Day 1 baseline visit is never out of protocol
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
                    
                    # Set visit status
                    if is_screen_fail:
                        visit_status = f"⚠ Screen Fail {visit_name}"
                    elif is_out_of_protocol:
                        visit_status = f"🔴 OUT OF PROTOCOL {visit_name}"
                    else:
                        visit_status = f"✅ {visit_name}"
                
                # Record the actual visit
                site = visit.get("SiteforVisit", "Unknown Site")
                
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
                # This is a scheduled visit - calculate from Day 1 baseline
                scheduled_date = baseline_date + timedelta(days=visit_day - 1)
                
                # Check if this scheduled visit is after this patient's screen failure
                if screen_fail_date is not None and scheduled_date > screen_fail_date:
                    screen_fail_exclusions += 1
                    continue
                
                # Normal scheduled visit processing
                payment = float(visit.get("Payment", 0) or 0.0)
                visit_status = visit_name
                
                # Handle tolerance
                tolerance_before = int(visit.get("ToleranceBefore", 0) or 0)
                tolerance_after = int(visit.get("ToleranceAfter", 0) or 0)
                
                site = visit.get("SiteforVisit", "Unknown Site")
                
                # Add main visit
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

                # Add tolerance periods - but skip tolerance before Day 1 visits
                # Day 1 is the baseline, so tolerance periods before it don't make sense
                if visit_day > 1:  # Only add tolerance periods for visits after Day 1
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

                # Add tolerance periods after - this applies to all visits including Day 1
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
        
        # Track patients that had recalculations
        if patient_needs_recalc:
            recalculated_patients.append(f"{patient_id} ({study})")

    # Debug: Print visit records for first patient to see what's being generated
    if visit_records:
        first_patient_id = visit_records[0]['PatientID']
        print(f"\nDEBUG: Visit records for {first_patient_id}:")
        patient_records = [r for r in visit_records if r['PatientID'] == first_patient_id]
        for record in sorted(patient_records, key=lambda x: x['Date']):
            print(f"  Date: {record['Date'].strftime('%Y-%m-%d')}, Visit: '{record['Visit']}', VisitDay: {record.get('VisitDay', 'N/A')}, VisitName: '{record.get('VisitName', 'N/A')}'")
        print("END DEBUG\n")

    # Create visits DataFrame
    visits_df = pd.DataFrame(visit_records)

    if visits_df.empty:
        raise ValueError("⚠ No visits generated. Check that Patient `Study` matches Trial `Study` values and StartDate is populated.")

    # Report unmatched visits
    if unmatched_visits:
        for unmatched in unmatched_visits:
            processing_messages.append(f"⚠ {unmatched}")

    # Collect processing messages
    if patients_with_no_visits:
        processing_messages.append(f"⚠ {len(patients_with_no_visits)} patient(s) skipped due to missing study definitions: {', '.join(patients_with_no_visits)}")
        
    if recalculated_patients:
        processing_messages.append(f"📅 Recalculated visit schedules for {len(recalculated_patients)} patient(s) based on Day 1 baseline: {', '.join(recalculated_patients)}")

    if out_of_window_visits:
        processing_messages.append(f"🔴 {len(out_of_window_visits)} visit(s) occurred outside tolerance windows (marked as OUT OF PROTOCOL)")

    if actual_visits_df is not None:
        processing_messages.append(f"✅ {actual_visits_used} actual visits matched and used in calendar")
        unmatched_actual = len(actual_visits_df) - actual_visits_used
        if unmatched_actual > 0:
            processing_messages.append(f"⚠ {unmatched_actual} actual visit records could not be matched to scheduled visits")

    if screen_fail_exclusions > 0:
        processing_messages.append(f"⚠ {screen_fail_exclusions} visits were excluded because they occur after screen failure dates")

    # Build calendar dataframe
    min_date = visits_df["Date"].min() - timedelta(days=1)
    max_date = visits_df["Date"].max() + timedelta(days=1)
    calendar_dates = pd.date_range(start=min_date, end=max_date)
    calendar_df = pd.DataFrame({"Date": calendar_dates})
    calendar_df["Day"] = calendar_df["Date"].dt.day_name()

    # Group patients by site
    patients_df["ColumnID"] = patients_df["Study"] + "_" + patients_df["PatientID"]
    unique_sites = sorted(patients_df["Site"].unique())
    
    # Create ordered columns
    ordered_columns = ["Date", "Day"]
    site_column_mapping = {}
    
    for site in unique_sites:
        site_patients = patients_df[patients_df["Site"] == site].sort_values(["Study", "PatientID"])
        site_columns = []
        for _, patient in site_patients.iterrows():
            col_id = patient["ColumnID"]
            ordered_columns.append(col_id)
            site_columns.append(col_id)
            calendar_df[col_id] = ""
        site_column_mapping[site] = site_columns

    # Create income tracking columns
    for study in trials_df["Study"].unique():
        income_col = f"{study} Income"
        calendar_df[income_col] = 0.0
    
    calendar_df["Daily Total"] = 0.0

    # Fill calendar
    for i, row in calendar_df.iterrows():
        date = row["Date"]
        visits_today = visits_df[visits_df["Date"] == date]
        daily_total = 0.0

        for _, visit in visits_today.iterrows():
            study = str(visit["Study"])
            pid = str(visit["PatientID"])
            col_id = f"{study}_{pid}"
            visit_info = visit["Visit"]
            payment = float(visit["Payment"]) or 0.0
            is_actual = visit.get("IsActual", False)

            if col_id in calendar_df.columns:
                current_value = calendar_df.at[i, col_id]
                
                if current_value == "":
                    calendar_df.at[i, col_id] = visit_info
                else:
                    # Handle multiple visits on same day
                    if visit_info in ["-", "+"]:
                        # Only add tolerance if there's no main visit already
                        if not any(symbol in str(current_value) for symbol in ["✅", "🔴", "⚠"]) and not any(visit_name in str(current_value) for visit_name in ["Randomisation", "Screening", "V1", "V2", "V3", "V4", "V5", "V6", "V7", "V8", "V9", "V10", "V11", "V12", "V13", "V14", "V15", "V16", "V17", "V18", "V19", "V20", "V21"]):
                            if current_value in ["-", "+", ""]:
                                calendar_df.at[i, col_id] = visit_info
                            else:
                                calendar_df.at[i, col_id] = f"{current_value}, {visit_info}"
                    else:
                        # This is a main visit - it should replace tolerance periods
                        if current_value in ["-", "+", ""]:
                            calendar_df.at[i, col_id] = visit_info
                        else:
                            # Multiple main visits on same day
                            calendar_df.at[i, col_id] = f"{current_value}, {visit_info}"

            # Count payments for actual visits and scheduled main visits (not tolerance periods)
            if (is_actual) or (not is_actual and visit_info not in ("-", "+")):
                income_col = f"{study} Income"
                if income_col in calendar_df.columns:
                    calendar_df.at[i, income_col] += payment
                    daily_total += payment

        calendar_df.at[i, "Daily Total"] = daily_total

    # Calculate monthly and financial year totals
    calendar_df["MonthPeriod"] = calendar_df["Date"].dt.to_period("M")
    monthly_totals = calendar_df.groupby("MonthPeriod")["Daily Total"].sum()
    calendar_df["IsMonthEnd"] = calendar_df["Date"] == calendar_df["Date"] + pd.offsets.MonthEnd(0)
    calendar_df["Monthly Total"] = calendar_df.apply(
        lambda r: monthly_totals.get(r["MonthPeriod"], 0.0) if r["IsMonthEnd"] else pd.NA, axis=1
    )

    calendar_df["FYStart"] = calendar_df["Date"].apply(lambda d: d.year if d.month >= 4 else d.year - 1)
    fy_totals = calendar_df.groupby("FYStart")["Daily Total"].sum()
    calendar_df["IsFYE"] = (calendar_df["Date"].dt.month == 3) & (calendar_df["Date"].dt.day == 31)
    calendar_df["FY Total"] = calendar_df.apply(
        lambda r: fy_totals.get(r["FYStart"], 0.0) if r["IsFYE"] else pd.NA, axis=1
    )

    stats = {
        "total_visits": len([v for v in visit_records if not v.get('IsActual', False) and v['Visit'] not in ['-', '+']]),
        "total_income": visits_df["Payment"].sum(),
        "messages": processing_messages,
        "out_of_window_visits": out_of_window_visits
    }

    return visits_df, calendar_df, stats, processing_messages, site_column_mapping, unique_sites
