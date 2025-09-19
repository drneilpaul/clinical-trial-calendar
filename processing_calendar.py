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

    patient_studies = set(patients_df["Study"].unique())
    trials_studies = set(trials_df["Study"].unique())
    missing_studies = patient_studies - trials_studies

    if "SiteforVisit" not in trials_df.columns:
        trials_df["SiteforVisit"] = "Default Site"

    screen_failures = {}
    if actual_visits_df is not None:
        required_actual = {"PatientID", "Study", "VisitNo", "ActualDate"}
        if not required_actual.issubset(actual_visits_df.columns):
            raise ValueError(f"❌ Actual visits file missing required columns: {required_actual}")

        actual_visits_df["PatientID"] = actual_visits_df["PatientID"].astype(str)
        actual_visits_df["Study"] = actual_visits_df["Study"].astype(str)
        actual_visits_df["ActualDate"] = pd.to_datetime(actual_visits_df["ActualDate"], dayfirst=True, errors="coerce")
        if "ActualPayment" not in actual_visits_df.columns:
            actual_visits_df["ActualPayment"] = None
        if "Notes" not in actual_visits_df.columns:
            actual_visits_df["Notes"] = ""
        else:
            actual_visits_df["Notes"] = actual_visits_df["Notes"].fillna("").astype(str)

        screen_fail_visits = actual_visits_df[
            actual_visits_df["Notes"].str.contains("ScreenFail", case=False, na=False)
        ]
        for _, visit in screen_fail_visits.iterrows():
            patient_study_key = f"{visit['PatientID']}_{visit['Study']}"
            screen_fail_date = visit['ActualDate']
            if patient_study_key not in screen_failures or screen_fail_date < screen_failures[patient_study_key]:
                screen_failures[patient_study_key] = screen_fail_date

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

    patients_df["PatientID"] = patients_df["PatientID"].astype(str)
    patients_df["Study"] = patients_df["Study"].astype(str)
    patients_df["StartDate"] = pd.to_datetime(patients_df["StartDate"], dayfirst=True, errors="coerce")
    trials_df["Study"] = trials_df["Study"].astype(str)
    trials_df["SiteforVisit"] = trials_df["SiteforVisit"].astype(str)

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

    if patient_origin_col:
        patients_df['Site'] = patients_df['OriginSite']
    else:
        patient_site_mapping = {}
        for _, patient in patients_df.iterrows():
            patient_id = patient["PatientID"]
            study = patient["Study"]
            study_sites = trials_df[trials_df["Study"] == study]["SiteforVisit"].unique()
            if len(study_sites) > 0:
                patient_site_mapping[patient_id] = study_sites[0]
            else:
                patient_site_mapping[patient_id] = f"{study}_Site"
        patients_df['Site'] = patients_df['PatientID'].map(patient_site_mapping)

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
        patient_study_key = f"{patient_id}_{study}"
        screen_fail_date = screen_failures.get(patient_study_key)

        if pd.isna(start_date):
            continue

        study_visits = trials_df[trials_df["Study"] == study].sort_values(['VisitNo', 'Day']).copy()
        if len(study_visits) == 0:
            patients_with_no_visits.append(f"{patient_id} (Study: {study})")
            continue

        patient_actual_visits = {}
        if actual_visits_df is not None:
            patient_actuals = actual_visits_df[
                (actual_visits_df["PatientID"] == str(patient_id)) &
                (actual_visits_df["Study"] == study)
            ].sort_values('VisitNo')
            for _, actual_visit in patient_actuals.iterrows():
                visit_no = actual_visit["VisitNo"]
                patient_actual_visits[visit_no] = actual_visit

        current_baseline_date = start_date
        current_baseline_visit = 0
        patient_needs_recalc = False

        for _, visit in study_visits.iterrows():
            try:
                visit_day = int(visit["Day"])
                visit_no = visit.get("VisitNo", "")
            except Exception:
                continue

            actual_visit_data = patient_actual_visits.get(visit_no)
            if actual_visit_data is not None:
                visit_date = actual_visit_data["ActualDate"]
                payment = float(actual_visit_data.get("ActualPayment") or visit.get("Payment", 0) or 0.0)
                notes = actual_visit_data.get("Notes", "")

                if current_baseline_visit == 0:
                    expected_date = start_date + timedelta(days=visit_day)
                else:
                    baseline_visit_data = study_visits[study_visits["VisitNo"] == current_baseline_visit].iloc[0]
                    baseline_day = int(baseline_visit_data["Day"])
                    day_diff = visit_day - baseline_day
                    expected_date = current_baseline_date + timedelta(days=day_diff)

                tolerance_before = int(visit.get("ToleranceBefore", 0) or 0)
                tolerance_after = int(visit.get("ToleranceAfter", 0) or 0)
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

                original_scheduled_date = start_date + timedelta(days=visit_day)
                if visit_date != original_scheduled_date:
                    patient_needs_recalc = True

                current_baseline_date = visit_date
                current_baseline_visit = visit_no

                visit_no_clean = int(float(visit_no)) if pd.notna(visit_no) else visit_no
                if "ScreenFail" in str(notes):
                    visit_status = f"❌ Screen Fail {visit_no_clean}"
                elif is_out_of_window:
                    visit_status = f"⚠️ Visit {visit_no_clean}"
                else:
                    visit_status = f"✅ Visit {visit_no_clean}"

                if screen_fail_date is not None and visit_date > screen_fail_date:
                    screen_fail_exclusions += 1
                    continue

                actual_visits_used += 1
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
                    "IsScreenFail": "ScreenFail" in str(actual_visit_data.get("Notes", "")),
                    "IsOutOfWindow": is_out_of_window
                })

            else:
                if current_baseline_visit == 0:
                    scheduled_date = start_date + timedelta(days=visit_day)
                else:
                    baseline_visit_data = study_visits[study_visits["VisitNo"] == current_baseline_visit].iloc[0]
                    baseline_day = int(baseline_visit_data["Day"])
                    day_diff = visit_day - baseline_day
                    scheduled_date = current_baseline_date + timedelta(days=day_diff)

                if screen_fail_date is not None and scheduled_date > screen_fail_date:
                    screen_fail_exclusions += 1
                    continue

                visit_date = scheduled_date
                payment = float(visit.get("Payment", 0) or 0.0)
                visit_no_clean = int(float(visit_no)) if pd.notna(visit_no) else visit_no
                visit_status = f"Visit {visit_no_clean}"

                tol_before = int(visit.get("ToleranceBefore", 0) or 0)
                tol_after = int(visit.get("ToleranceAfter", 0) or 0)
                site = visit.get("SiteforVisit", "Unknown Site")

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

                for i in range(1, tol_before + 1):
                    tolerance_date = visit_date - timedelta(days=i)
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
                        "IsOutOfWindow": False
                    })

                for i in range(1, tol_after + 1):
                    tolerance_date = visit_date + timedelta(days=i)
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
                        "IsOutOfWindow": False
                    })

        if patient_needs_recalc:
            recalculated_patients.append(f"{patient_id} ({study})")

    visits_df = pd.DataFrame(visit_records)

    processing_messages = []
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

    total_visit_records = len(visit_records)
    total_scheduled_visits = len([v for v in visit_records if not v.get('IsActual', False) and v['Visit'] not in ['-', '+']])
    total_tolerance_periods = len([v for v in visit_records if v['Visit'] in ['-', '+']])
    processing_messages.append(f"Generated {total_visit_records} total calendar entries ({total_scheduled_visits} scheduled visits, {total_tolerance_periods} tolerance periods)")

    # Build calendar dataframe
    min_date = visits_df["Date"].min() - timedelta(days=1)
    max_date = visits_df["Date"].max() + timedelta(days=1)
    calendar_dates = pd.date_range(start=min_date, end=max_date)
    calendar_df = pd.DataFrame({"Date": calendar_dates})
    calendar_df["Day"] = calendar_df["Date"].dt.day_name()

    patients_df["ColumnID"] = patients_df["Study"] + "_" + patients_df["PatientID"]
    unique_sites = sorted(patients_df["Site"].unique())

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

    calendar_df["Daily Total"] = 0.0

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
                    if visit_info in ["-", "+"]:
                        if not any(x in current_value for x in ["Visit", "✅", "⚠️", "❌"]):
                            calendar_df.at[i, col_id] = visit_info if current_value in ["-", "+"] else f"{current_value}, {visit_info}"
                    else:
                        if current_value in ["-", "+", "", "-", "+"]:
                            calendar_df.at[i, col_id] = visit_info
                        else:
                            calendar_df.at[i, col_id] = f"{current_value}, {visit_info}"
            if (is_actual) or (not is_actual and visit_info not in ("-", "+")):
                daily_total += payment
        calendar_df.at[i, "Daily Total"] = daily_total

    stats = {
        "total_visits": total_scheduled_visits,
        "total_income": visits_df["Payment"].sum(),
        "messages": processing_messages,
        "out_of_window_visits": out_of_window_visits
    }

    return visits_df, calendar_df, stats, processing_messages, site_column_mapping, unique_sites
