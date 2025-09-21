import pandas as pd
from datetime import timedelta

def build_calendar(patients_df, trials_df, actual_visits_df=None):
    # Clean columns
    patients_df.columns = patients_df.columns.str.strip()
    trials_df.columns = trials_df.columns.str.strip()
    if actual_visits_df is not None:
        actual_visits_df.columns = actual_visits_df.columns.str.strip()

    required_patients = {"PatientID", "Study", "StartDate"}
    required_trials = {"Study", "Day", "VisitNo"}

    if not required_patients.issubset(patients_df.columns):
        raise ValueError(f"❌ Patients file missing required columns: {required_patients - set(patients_df.columns)}")
    if not required_trials.issubset(trials_df.columns):
        raise ValueError(f"❌ Trials file missing required columns: {required_trials - set(trials_df.columns)}")

    # Check for SiteforVisit column
    if "SiteforVisit" not in trials_df.columns:
        trials_df["SiteforVisit"] = "Default Site"

    # Initialize debug messages list
    debug_messages = []
    
    screen_failures = {}
    if actual_visits_df is not None:
        required_actual = {"PatientID", "Study", "VisitNo", "ActualDate"}
        if not required_actual.issubset(actual_visits_df.columns):
            raise ValueError(f"❌ Actual visits file missing required columns: {required_actual}")

        debug_messages.append(f"Raw actual visits data: {len(actual_visits_df)} records")
        for idx, row in actual_visits_df.head(3).iterrows():
            debug_messages.append(f"Raw ActualVisit {idx}: PatientID={repr(row['PatientID'])} (type: {type(row['PatientID'])}), Study={repr(row['Study'])}")

        # Ensure proper data type handling
        actual_visits_df["PatientID"] = actual_visits_df["PatientID"].astype(str)
        actual_visits_df["Study"] = actual_visits_df["Study"].astype(str)
        actual_visits_df["VisitNo"] = actual_visits_df["VisitNo"].astype(str)
        actual_visits_df["ActualDate"] = pd.to_datetime(actual_visits_df["ActualDate"], dayfirst=True, errors="coerce")
        
        debug_messages.append("After type conversion:")
        for idx, row in actual_visits_df.head(3).iterrows():
            debug_messages.append(f"Processed ActualVisit {idx}: PatientID={repr(row['PatientID'])}, Study={repr(row['Study'])}")
        
        # Handle optional columns
        if "ActualPayment" not in actual_visits_df.columns:
            actual_visits_df["ActualPayment"] = None
        if "Notes" not in actual_visits_df.columns:
            actual_visits_df["Notes"] = ""
        else:
            actual_visits_df["Notes"] = actual_visits_df["Notes"].fillna("").astype(str)

        # Detect screen failures
        screen_fail_visits = actual_visits_df[
            actual_visits_df["Notes"].str.contains("ScreenFail", case=False, na=False)
        ]
        
        for _, visit in screen_fail_visits.iterrows():
            patient_study_key = f"{visit['PatientID']}_{visit['Study']}"
            screen_fail_date = visit['ActualDate']
            if patient_study_key not in screen_failures or screen_fail_date < screen_failures[patient_study_key]:
                screen_failures[patient_study_key] = screen_fail_date

        # Create lookup key for actual visits
        actual_visits_df["VisitKey"] = (
            actual_visits_df["PatientID"] + "_" +
            actual_visits_df["Study"] + "_" +
            actual_visits_df["VisitNo"].astype(str)
        )

    # Normalize column names
    column_mapping = {
        'Income': 'Payment',
        'Tolerance Before': 'ToleranceBefore',
        'Tolerance After': 'ToleranceAfter',
        'Visit No': 'VisitNo',
        'VisitNumber': 'VisitNo'
    }
    trials_df = trials_df.rename(columns=column_mapping)

    debug_messages.append(f"Raw patients data: {len(patients_df)} records")
    for idx, row in patients_df.head(3).iterrows():
        debug_messages.append(f"Raw Patient {idx}: PatientID={repr(row['PatientID'])} (type: {type(row['PatientID'])}), Study={repr(row['Study'])}")

    # Process patient data types
    patients_df["PatientID"] = patients_df["PatientID"].astype(str)
    patients_df["Study"] = patients_df["Study"].astype(str)
    patients_df["StartDate"] = pd.to_datetime(patients_df["StartDate"], dayfirst=True, errors="coerce")
    
    debug_messages.append("After patients type conversion:")
    for idx, row in patients_df.head(3).iterrows():
        debug_messages.append(f"Processed Patient {idx}: PatientID={repr(row['PatientID'])}, Study={repr(row['Study'])}")
    
    # Ensure VisitNo in trials is also string for consistent matching
    trials_df["Study"] = trials_df["Study"].astype(str)
    trials_df["VisitNo"] = trials_df["VisitNo"].astype(str)
    trials_df["SiteforVisit"] = trials_df["SiteforVisit"].astype(str)

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

    # Create patient-site mapping - use patient origin site directly
    if patient_origin_col:
        patients_df['Site'] = patients_df['OriginSite']
    else:
        # Fallback: try to map from trials
        patient_site_mapping = {}
        for _, patient in patients_df.iterrows():
            patient_id = patient["PatientID"]
            study = patient["Study"]
            
            # First try to get site from trials file for this study
            study_sites = trials_df[trials_df["Study"] == study]["SiteforVisit"].unique()
            if len(study_sites) > 0:
                patient_site_mapping[patient_id] = study_sites[0]
            else:
                # If study not found in trials, use a default based on study name
                patient_site_mapping[patient_id] = f"{study}_Site"
        
        patients_df['Site'] = patients_df['PatientID'].map(patient_site_mapping)

    # Build visit records with recalculation logic
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
        
        debug_messages.append(f"Processing Patient {repr(patient_id)} in Study {repr(study)}")
        
        # Check if this patient has a screen failure
        patient_study_key = f"{patient_id}_{study}"
        screen_fail_date = screen_failures.get(patient_study_key)

        if pd.isna(start_date):
            continue

        # Get all visits for this study and sort by visit number/day
        study_visits = trials_df[trials_df["Study"] == study].sort_values(['VisitNo', 'Day']).copy()
        
        # Check if this study has any visit definitions
        if len(study_visits) == 0:
            patients_with_no_visits.append(f"{patient_id} (Study: {study})")
            continue  # Skip this patient as no visit schedule is defined
        
        # Get all actual visits for this patient - DETAILED DEBUG
        patient_actual_visits = {}
        if actual_visits_df is not None:
            debug_messages.append(f"Looking for actual visits: PatientID={repr(patient_id)}, Study={repr(study)}")
            
            # Test each condition separately
            pid_matches = actual_visits_df["PatientID"] == patient_id
            study_matches = actual_visits_df["Study"] == study
            
            debug_messages.append(f"PatientID matches: {pid_matches.sum()}/{len(actual_visits_df)}")
            debug_messages.append(f"Study matches: {study_matches.sum()}/{len(actual_visits_df)}")
            
            # Show detailed comparison for all rows
            for idx, row in actual_visits_df.iterrows():
                pid_match = row["PatientID"] == patient_id
                study_match = row["Study"] == study
                debug_messages.append(f"ActualVisit {idx}: PID {repr(row['PatientID'])}=={repr(patient_id)} -> {pid_match}")
                debug_messages.append(f"ActualVisit {idx}: Study {repr(row['Study'])}=={repr(study)} -> {study_match}")
                debug_messages.append(f"ActualVisit {idx}: BOTH -> {pid_match and study_match}")
            
            # Use consistent string comparison
            patient_actuals = actual_visits_df[
                (actual_visits_df["PatientID"] == patient_id) & 
                (actual_visits_df["Study"] == study)
            ].sort_values('VisitNo')
            
            debug_messages.append(f"RESULT: Found {len(patient_actuals)} actual visits for patient {patient_id}")
            
            for _, actual_visit in patient_actuals.iterrows():
                visit_no = str(actual_visit["VisitNo"])
                patient_actual_visits[visit_no] = actual_visit
                actual_visits_used += 1
                debug_messages.append(f"Added actual visit: VisitNo={visit_no}")
        
        # Process each visit with IMPROVED validation
        current_baseline_date = start_date
        current_baseline_visit = "0"
        patient_needs_recalc = False
        
        for _, visit in study_visits.iterrows():
            try:
                visit_day = int(visit["Day"])
                visit_no = str(visit.get("VisitNo", ""))
            except Exception:
                continue
            
            # Check if we have an actual visit for this visit number
            actual_visit_data = patient_actual_visits.get(visit_no)
            
            if actual_visit_data is not None:
                # This is an actual visit
                visit_date = actual_visit_data["ActualDate"]
                payment = float(actual_visit_data.get("ActualPayment") or visit.get("Payment", 0) or 0.0)
                notes = actual_visit_data.get("Notes", "")
                
                # VALIDATION: Check for impossible scenarios
                is_screen_fail = "ScreenFail" in str(notes)
                this_patient_screen_fail_key = f"{patient_id}_{study}"
                
                # Check if this visit is after a screen failure for THIS SPECIFIC PATIENT
                this_patient_screen_fail_date = screen_failures.get(this_patient_screen_fail_key)
                
                if this_patient_screen_fail_date is not None and visit_date > this_patient_screen_fail_date:
                    # DATA VALIDATION ERROR - warn instead of silently excluding
                    error_msg = (f"DATA ERROR: Patient {patient_id} has a visit on {visit_date.strftime('%Y-%m-%d')} "
                               f"AFTER their screen failure date ({this_patient_screen_fail_date.strftime('%Y-%m-%d')}). "
                               f"This should not happen - please check your data.")
                    processing_messages.append(f"⚠️ {error_msg}")
                    
                    # Continue processing but mark as data error
                    visit_status = f"❌ DATA ERROR Visit {visit_no}"
                    
                else:
                    # Normal processing
                    # Calculate expected date for validation
                    if current_baseline_visit == "0":
                        expected_date = start_date + timedelta(days=visit_day)
                    else:
                        baseline_visit_data = study_visits[study_visits["VisitNo"] == current_baseline_visit]
                        if len(baseline_visit_data) > 0:
                            baseline_day = int(baseline_visit_data.iloc[0]["Day"])
                            day_diff = visit_day - baseline_day
                            expected_date = current_baseline_date + timedelta(days=day_diff)
                        else:
                            expected_date = start_date + timedelta(days=visit_day)
                    
                    # Safe tolerance handling
                    tolerance_before = 0
                    tolerance_after = 0
                    try:
                        tolerance_before = int(visit.get("ToleranceBefore", 0) or 0)
                        tolerance_after = int(visit.get("ToleranceAfter", 0) or 0)
                    except (ValueError, TypeError):
                        pass
                    
                    earliest_acceptable = expected_date - timedelta(days=tolerance_before)
                    latest_acceptable = expected_date + timedelta(days=tolerance_after)
                    
                    is_out_of_window = visit_date < earliest_acceptable or visit_date > latest_acceptable
                    if is_out_of_window:
                        days_early = max(0, (earliest_acceptable - visit_date).days)
                        days_late = max(0, (visit_date - latest_acceptable).days)
                        deviation = days_early + days_late
                        out_of_window_visits.append({
                            'patient': f"{patient_id} ({study})",
                            'visit': f"V{visit_no}",
                            'expected': expected_date.strftime('%Y-%m-%d'),
                            'actual': visit_date.strftime('%Y-%m-%d'),
                            'deviation': f"{deviation} days {'early' if days_early > 0 else 'late'}",
                            'tolerance': f"+{tolerance_after}/-{tolerance_before} days"
                        })
                    
                    # Update baseline for future calculations
                    original_scheduled_date = start_date + timedelta(days=visit_day)
                    if visit_date != original_scheduled_date:
                        patient_needs_recalc = True
                    
                    current_baseline_date = visit_date
                    current_baseline_visit = visit_no
                    
                    # Safe visit number formatting
                    try:
                        visit_no_clean = int(float(visit_no)) if pd.notna(visit_no) else visit_no
                    except:
                        visit_no_clean = visit_no
                    
                    # Use consistent emoji symbols
                    if is_screen_fail:
                        visit_status = f"❌ Screen Fail {visit_no_clean}"
                    elif is_out_of_window:
                        visit_status = f"⚠️ Visit {visit_no_clean}"
                    else:
                        visit_status = f"✅ Visit {visit_no_clean}"
                
                debug_messages.append(f"Recording ACTUAL visit: {visit_status}")
                
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
                    "IsOutOfWindow": is_out_of_window
                })
                
            else:
                # This is a scheduled visit - check if we should skip due to screen failure
                if current_baseline_visit == "0":
                    scheduled_date = start_date + timedelta(days=visit_day)
                else:
                    baseline_visit_data = study_visits[study_visits["VisitNo"] == current_baseline_visit]
                    if len(baseline_visit_data) > 0:
                        baseline_day = int(baseline_visit_data.iloc[0]["Day"])
                        day_diff = visit_day - baseline_day
                        scheduled_date = current_baseline_date + timedelta(days=day_diff)
                    else:
                        scheduled_date = start_date + timedelta(days=visit_day)
                
                # Check if this SCHEDULED visit is after THIS PATIENT's screen failure
                this_patient_screen_fail_key = f"{patient_id}_{study}"
                this_patient_screen_fail_date = screen_failures.get(this_patient_screen_fail_key)
                
                if this_patient_screen_fail_date is not None and scheduled_date > this_patient_screen_fail_date:
                    screen_fail_exclusions += 1
                    continue
                
                # Normal scheduled visit processing
                visit_date = scheduled_date
                payment = float(visit.get("Payment", 0) or 0.0)
                
                try:
                    visit_no_clean = int(float(visit_no)) if pd.notna(visit_no) else visit_no
                except:
                    visit_no_clean = visit_no
                
                visit_status = f"Visit {visit_no_clean}"
                
                # Safe tolerance handling
                tol_before = 0
                tol_after = 0
                try:
                    tol_before = int(visit.get("ToleranceBefore", 0) or 0)
                    tol_after = int(visit.get("ToleranceAfter", 0) or 0)
                except (ValueError, TypeError):
                    pass
                
                site = visit.get("SiteforVisit", "Unknown Site")
                
                # Add main visit + tolerance periods
                visit_records.append({
                    "Date": visit_date,
                    "PatientID": patient_id,
                    "Visit": visit_status,
                    "Study": study,
                    "Payment": payment,
                    "SiteofVisit": site,
                    "PatientOrigin": patient_origin,
                    "IsActual": False,
                    "IsScreenFail": False,
                    "IsOutOfWindow": False
                })

                # Add tolerance periods (with same screen failure check)
                for i in range(1, tol_before + 1):
                    tolerance_date = visit_date - timedelta(days=i)
                    if this_patient_screen_fail_date is not None and tolerance_date > this_patient_screen_fail_date:
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
                        "IsOutOfWindow": False
                    })

                for i in range(1, tol_after + 1):
                    tolerance_date = visit_date + timedelta(days=i)
                    if this_patient_screen_fail_date is not None and tolerance_date > this_patient_screen_fail_date:
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
                        "IsOutOfWindow": False
                    })
        
        # Track patients that had recalculations
        if patient_needs_recalc:
            recalculated_patients.append(f"{patient_id} ({study})")

    debug_messages.append(f"Final counts: actual_visits_used={actual_visits_used}, visit_records={len(visit_records)}")

    # Create visits DataFrame
    visits_df = pd.DataFrame(visit_records)

    if visits_df.empty:
        raise ValueError("❌ No visits generated. Check that Patient `Study` matches Trial `Study` values and StartDate is populated.")

    # Collect processing messages safely
    if len(patients_with_no_visits) > 0:
        processing_messages.append(f"⚠️ {len(patients_with_no_visits)} patient(s) skipped due to missing study definitions: {', '.join(patients_with_no_visits)}")
        
    if len(recalculated_patients) > 0:
        processing_messages.append(f"📅 Recalculated visit schedules for {len(recalculated_patients)} patient(s): {', '.join(recalculated_patients)}")

    if len(out_of_window_visits) > 0:
        processing_messages.append(f"⚠️ {len(out_of_window_visits)} visit(s) occurred outside tolerance windows")

    if actual_visits_df is not None:
        processing_messages.append(f"✅ {actual_visits_used} actual visits matched and used in calendar")
        unmatched_actual = len(actual_visits_df) - actual_visits_used
        if unmatched_actual > 0:
            processing_messages.append(f"⚠️ {unmatched_actual} actual visit records could not be matched to scheduled visits")

    if screen_fail_exclusions > 0:
        processing_messages.append(f"⚠️ {screen_fail_exclusions} visits were excluded because they occur after screen failure dates.")

    # Collect final processing statistics
    total_visit_records = len(visit_records)
    total_scheduled_visits = len([v for v in visit_records if not v.get('IsActual', False) and v['Visit'] not in ['-', '+']])
    total_tolerance_periods = len([v for v in visit_records if v['Visit'] in ['-', '+']])
    
    processing_messages.append(f"Generated {total_visit_records} total calendar entries ({total_scheduled_visits} scheduled visits, {total_tolerance_periods} tolerance periods)")
    
    # Safe financial calculations  
    if actual_visits_df is not None and len(actual_visits_df) > 0:
        actual_visit_entries = len([v for v in visit_records if v.get('IsActual', False)])
    
        # DEBUG: Show what actual visits are in visit_records
        actual_records = [v for v in visit_records if v.get('IsActual', False)]
        debug_messages.append(f"Actual visit records in visit_records: {len(actual_records)}")
        for i, record in enumerate(actual_records):
            debug_messages.append(f"  Actual record {i+1}: {record['Visit']} - IsActual={record.get('IsActual', 'MISSING')}")
    
        processing_messages.append(f"Calendar includes {actual_visit_entries} actual visits and {total_scheduled_visits} scheduled visits")
        
        if actual_visits_used < len(actual_visits_df):
            processing_messages.append(f"Visit matching: {actual_visits_used} matched, {len(actual_visits_df) - actual_visits_used} unmatched")
    
    # Date range statistics
    if not visits_df.empty:
        earliest_date = visits_df["Date"].min()
        latest_date = visits_df["Date"].max()
        date_range_days = (latest_date - earliest_date).days
        processing_messages.append(f"Calendar spans {date_range_days} days ({earliest_date.strftime('%Y-%m-%d')} to {latest_date.strftime('%Y-%m-%d')})")
    
    # Safe total income calculation
    try:
        total_income = visits_df["Payment"].sum()
        processing_messages.append(f"Total financial value: £{total_income:,.2f}")
    except Exception:
        processing_messages.append("Total financial value: £0.00")

    # Add debug messages to processing messages so they appear in the web interface
    if debug_messages:
        processing_messages.extend(["=== DEBUG INFO ==="] + debug_messages + ["=== END DEBUG ==="])
    
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

    # Improved calendar filling logic
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
                
                # Better concatenation logic to avoid issues
                if current_value == "":
                    calendar_df.at[i, col_id] = visit_info
                else:
                    # Handle tolerance periods more carefully
                    if visit_info in ["-", "+"]:
                        # Only add tolerance if there's no main visit already
                        if not any(x in current_value for x in ["Visit", "✅", "⚠️", "❌"]):
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

    # Calculate totals - Monthly and Financial Year
    calendar_df["MonthPeriod"] = calendar_df["Date"].dt.to_period("M")
    monthly_totals = calendar_df.groupby("MonthPeriod")["Daily Total"].sum()
    calendar_df["IsMonthEnd"] = calendar_df["Date"] == calendar_df["Date"] + pd.offsets.MonthEnd(0)
    calendar_df["Monthly Total"] = calendar_df.apply(
        lambda r: monthly_totals.get(r["MonthPeriod"], 0.0) if r["IsMonthEnd"] else pd.NA, axis=1
    )

    # Financial year calculation (April to March)
    calendar_df["FYStart"] = calendar_df["Date"].apply(lambda d: d.year if d.month >= 4 else d.year - 1)
    fy_totals = calendar_df.groupby("FYStart")["Daily Total"].sum()
    calendar_df["IsFYE"] = (calendar_df["Date"].dt.month == 3) & (calendar_df["Date"].dt.day == 31)
    calendar_df["FY Total"] = calendar_df.apply(
        lambda r: fy_totals.get(r["FYStart"], 0.0) if r["IsFYE"] else pd.NA, axis=1
    )

    stats = {
        "total_visits": total_scheduled_visits,
        "total_income": visits_df["Payment"].sum(),
        "messages": processing_messages,
        "out_of_window_visits": out_of_window_visits
    }

    return visits_df, calendar_df, stats, processing_messages, site_column_mapping, unique_sites
    
