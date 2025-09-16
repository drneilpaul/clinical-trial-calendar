import streamlit as st
import pandas as pd
import calendar as cal
from datetime import timedelta
import io

st.set_page_config(page_title="Clinical Trial Calendar Generator", layout="wide")

# === Styling Functions ===
def highlight_special_days(row):
    try:
        date_obj = pd.to_datetime(row.get("Date"))
        if pd.isna(date_obj):
            return [''] * len(row)

        # Financial year end (31 March)
        if date_obj.month == 3 and date_obj.day == 31:
            return ['background-color: #1e40af; color: white; font-weight: bold'] * len(row)

        # Month end
        # Using pandas offset check
        if date_obj == date_obj + pd.offsets.MonthEnd(0):
            return ['background-color: #3b82f6; color: white; font-weight: bold'] * len(row)

    except Exception:
        pass
    return [''] * len(row)


def highlight_weekends(row):
    try:
        date_obj = pd.to_datetime(row.get("Date"))
        if pd.isna(date_obj):
            return [''] * len(row)
        if date_obj.weekday() in (5, 6):  # Saturday=5, Sunday=6
            return ['background-color: #f3f4f6'] * len(row)
    except Exception:
        pass
    return [''] * len(row)


# === UI ===
st.title("🏥 Clinical Trial Calendar Generator")
st.caption("v2.2.1 | Fixed: SiteforVisit column detection issue")

st.sidebar.header("📁 Upload Data Files")
patients_file = st.sidebar.file_uploader("Upload Patients File", type=['csv', 'xls', 'xlsx'], key="patients")
trials_file = st.sidebar.file_uploader("Upload Trials File", type=['csv', 'xls', 'xlsx'], key="trials")
actual_visits_file = st.sidebar.file_uploader("Upload Actual Visits File (Optional)", type=['csv', 'xls', 'xlsx'], key="actual_visits")

# Information about required columns
with st.sidebar.expander("ℹ️ Required Columns"):
    st.write("**Patients File:**")
    st.write("- PatientID, Study, StartDate")
    st.write("- Site/PatientPractice (optional)")
    st.write("")
    st.write("**Trials File:**")
    st.write("- Study, Day, VisitNo, SiteforVisit")
    st.write("- Income/Payment, ToleranceBefore, ToleranceAfter")
    st.write("")
    st.write("**Actual Visits File (Optional):**")
    st.write("- PatientID, Study, VisitNo, ActualDate")
    st.write("- ActualPayment, Notes (optional)")
    st.write("- Use 'ScreenFail' in Notes to stop future visits")


# === File Loading Helper ===
def load_file(uploaded_file):
    if uploaded_file is None:
        return None
    if uploaded_file.name.endswith(".csv"):
        return pd.read_csv(uploaded_file, dayfirst=True)
    else:
        return pd.read_excel(uploaded_file, engine="openpyxl")


# === Main Logic ===
if patients_file and trials_file:
    try:
        # Load files
        patients_df = load_file(patients_file)
        trials_df = load_file(trials_file)
        actual_visits_df = load_file(actual_visits_file) if actual_visits_file else None

        # Clean columns
        patients_df.columns = patients_df.columns.str.strip()
        trials_df.columns = trials_df.columns.str.strip()
        if actual_visits_df is not None:
            actual_visits_df.columns = actual_visits_df.columns.str.strip()

        # Required columns check
        required_patients = {"PatientID", "Study", "StartDate"}
        required_trials = {"Study", "Day", "VisitNo"}

        if not required_patients.issubset(patients_df.columns):
            st.error(f"❌ Patients file missing required columns: {required_patients - set(patients_df.columns)}")
            st.stop()
        if not required_trials.issubset(trials_df.columns):
            st.error(f"❌ Trials file missing required columns: {required_trials - set(trials_df.columns)}")
            st.stop()

        # Check for SiteforVisit column
        if "SiteforVisit" not in trials_df.columns:
            st.warning("⚠️ No 'SiteforVisit' column found in trials file. Using default site grouping.")
            trials_df["SiteforVisit"] = "Default Site"

        # Process actual visits if provided
        screen_failures = {}
        if actual_visits_df is not None:
            required_actual = {"PatientID", "Study", "VisitNo", "ActualDate"}
            if not required_actual.issubset(actual_visits_df.columns):
                st.error(f"❌ Actual visits file missing required columns: {required_actual}")
                st.stop()
            
            # Process actual visits data
            actual_visits_df["PatientID"] = actual_visits_df["PatientID"].astype(str)
            actual_visits_df["Study"] = actual_visits_df["Study"].astype(str)
            actual_visits_df["ActualDate"] = pd.to_datetime(actual_visits_df["ActualDate"], dayfirst=True, errors="coerce")
            
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
            
            if len(screen_failures) > 0:
                st.info(f"📋 Detected {len(screen_failures)} screen failure(s) - future visits will be excluded after these dates")
            
            # Create lookup key for actual visits
            actual_visits_df["VisitKey"] = (
                actual_visits_df["PatientID"] + "_" + 
                actual_visits_df["Study"] + "_" + 
                actual_visits_df["VisitNo"].astype(str)
            )
            
            st.info(f"✅ Loaded {len(actual_visits_df)} actual visit records")
        else:
            st.info("ℹ️ No actual visits file provided - showing scheduled visits only")

        # Normalize column names
        column_mapping = {
            'Income': 'Payment',
            'Tolerance Before': 'ToleranceBefore',
            'Tolerance After': 'ToleranceAfter',
            'Visit No': 'VisitNo',
            'VisitNumber': 'VisitNo'
        }
        trials_df = trials_df.rename(columns=column_mapping)

        # Process patient data types
        patients_df["PatientID"] = patients_df["PatientID"].astype(str)
        patients_df["Study"] = patients_df["Study"].astype(str)
        patients_df["StartDate"] = pd.to_datetime(patients_df["StartDate"], dayfirst=True, errors="coerce")
        
        trials_df["Study"] = trials_df["Study"].astype(str)
        trials_df["SiteforVisit"] = trials_df["SiteforVisit"].astype(str)

        # Check for patient origin site column
        patient_origin_col = None
        possible_origin_cols = ['PatientSite', 'OriginSite', 'Practice', 'PatientPractice', 'HomeSite', 'Site']
        for col in possible_origin_cols:
            if col in patients_df.columns:
                patient_origin_col = col
                break
        
        if patient_origin_col:
            st.info(f"ℹ️ Using '{patient_origin_col}' column for patient origin site.")
            patients_df['OriginSite'] = patients_df[patient_origin_col].astype(str)
        else:
            st.warning("⚠️ No patient origin site column found.")
            patients_df['OriginSite'] = "Unknown Origin"

        # Create patient-site mapping
        patient_site_mapping = {}
        for _, patient in patients_df.iterrows():
            patient_id = patient["PatientID"]
            study = patient["Study"]
            study_sites = trials_df[trials_df["Study"] == study]["SiteforVisit"].unique()
            if len(study_sites) > 0:
                patient_site_mapping[patient_id] = study_sites[0]
            else:
                patient_site_mapping[patient_id] = "Unknown Site"

        patients_df['Site'] = patients_df['PatientID'].map(patient_site_mapping)

        # Build visit records with recalculation logic
        visit_records = []
        screen_fail_exclusions = 0
        actual_visits_used = 0
        recalculated_patients = []
        out_of_window_visits = []
        
        for _, patient in patients_df.iterrows():
            patient_id = patient["PatientID"]
            study = patient["Study"]
            start_date = patient["StartDate"]
            patient_origin = patient["OriginSite"]
            
            # Check if this patient has a screen failure
            patient_study_key = f"{patient_id}_{study}"
            screen_fail_date = screen_failures.get(patient_study_key)

            if pd.isna(start_date):
                continue

            # Get all visits for this study and sort by visit number/day
            study_visits = trials_df[trials_df["Study"] == study].sort_values(['VisitNo', 'Day']).copy()
            
            # Get all actual visits for this patient
            patient_actual_visits = {}
            if actual_visits_df is not None:
                patient_actuals = actual_visits_df[
                    (actual_visits_df["PatientID"] == str(patient_id)) & 
                    (actual_visits_df["Study"] == study)
                ].sort_values('VisitNo')
                
                for _, actual_visit in patient_actuals.iterrows():
                    visit_no = actual_visit["VisitNo"]
                    patient_actual_visits[visit_no] = actual_visit
            
            # Process each visit with recalculation logic
            current_baseline_date = start_date
            current_baseline_visit = 0
            patient_needs_recalc = False
            
            for _, visit in study_visits.iterrows():
                try:
                    visit_day = int(visit["Day"])
                    visit_no = visit.get("VisitNo", "")
                except Exception:
                    continue
                
                # Check if we have an actual visit for this visit number
                actual_visit_data = patient_actual_visits.get(visit_no)
                
                if actual_visit_data is not None:
                    # This is an actual visit
                    visit_date = actual_visit_data["ActualDate"]
                    payment = float(actual_visit_data.get("ActualPayment") or visit.get("Payment", 0) or 0.0)
                    notes = actual_visit_data.get("Notes", "")
                    
                    # Calculate expected date for validation
                    if current_baseline_visit == 0:
                        expected_date = start_date + timedelta(days=visit_day)
                    else:
                        baseline_visit_data = study_visits[study_visits["VisitNo"] == current_baseline_visit].iloc[0]
                        baseline_day = int(baseline_visit_data["Day"])
                        day_diff = visit_day - baseline_day
                        expected_date = current_baseline_date + timedelta(days=day_diff)
                    
                    # Check if actual visit is outside tolerance window
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
                    
                    # Update baseline for future calculations
                    original_scheduled_date = start_date + timedelta(days=visit_day)
                    if visit_date != original_scheduled_date:
                        patient_needs_recalc = True
                    
                    current_baseline_date = visit_date
                    current_baseline_visit = visit_no
                    
                    # Mark visit status based on notes and window compliance
                    if "ScreenFail" in str(notes):
                        visit_status = f"❌ Screen Fail {visit_no}"
                    elif is_out_of_window:
                        visit_status = f"⚠️ Visit {visit_no}"
                    else:
                        visit_status = f"✓ Visit {visit_no}"
                    
                    # Check if actual visit is after screen failure
                    if screen_fail_date is not None and visit_date > screen_fail_date:
                        screen_fail_exclusions += 1
                        continue
                    
                    actual_visits_used += 1
                    
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
                        "IsScreenFail": "ScreenFail" in str(actual_visit_data.get("Notes", "")),
                        "IsOutOfWindow": is_out_of_window
                    })
                    
                else:
                    # This is a scheduled visit
                    if current_baseline_visit == 0:
                        scheduled_date = start_date + timedelta(days=visit_day)
                    else:
                        baseline_visit_data = study_visits[study_visits["VisitNo"] == current_baseline_visit].iloc[0]
                        baseline_day = int(baseline_visit_data["Day"])
                        day_diff = visit_day - baseline_day
                        scheduled_date = current_baseline_date + timedelta(days=day_diff)
                    
                    # Check if visit date is after screen failure date
                    if screen_fail_date is not None and scheduled_date > screen_fail_date:
                        screen_fail_exclusions += 1
                        continue
                    
                    visit_date = scheduled_date
                    payment = float(visit.get("Payment", 0) or 0.0)
                    visit_status = f"Visit {visit_no}"
                    
                    tol_before = int(visit.get("ToleranceBefore", 0) or 0)
                    tol_after = int(visit.get("ToleranceAfter", 0) or 0)
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

                    # Tolerance periods
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
            
            # Track patients that had recalculations
            if patient_needs_recalc:
                recalculated_patients.append(f"{patient_id} ({study})")

        # Report on recalculations and validations
        if len(recalculated_patients) > 0:
            st.info(f"📅 Recalculated visit schedules for {len(recalculated_patients)} patient(s): {', '.join(recalculated_patients)}")

        if len(out_of_window_visits) > 0:
            st.warning(f"⚠️ {len(out_of_window_visits)} visit(s) occurred outside tolerance windows:")
            oow_df = pd.DataFrame(out_of_window_visits)
            st.dataframe(oow_df, use_container_width=True)

        if actual_visits_df is not None:
            st.success(f"✅ {actual_visits_used} actual visits matched and used in calendar")
            unmatched_actual = len(actual_visits_df) - actual_visits_used
            if unmatched_actual > 0:
                st.warning(f"⚠️ {unmatched_actual} actual visit records could not be matched to scheduled visits")

        if screen_fail_exclusions > 0:
            st.warning(f"⚠️ {screen_fail_exclusions} visits were excluded because they occur after screen failure dates.")

        visits_df = pd.DataFrame(visit_records)

        if visits_df.empty:
            st.error("❌ No visits generated. Check that Patient `Study` matches Trial `Study` values and StartDate is populated.")
            st.stop()

        # Build calendar
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

        # Fill calendar with color-coded visit information
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
                is_screen_fail = visit.get("IsScreenFail", False)
                is_out_of_window = visit.get("IsOutOfWindow", False)

                if col_id in calendar_df.columns:
                    if calendar_df.at[i, col_id] == "":
                        calendar_df.at[i, col_id] = visit_info
                    else:
                        calendar_df.at[i, col_id] += f", {visit_info}"

                # Count payments for actual visits and scheduled main visits (not tolerance periods)
                if (is_actual) or (not is_actual and visit_info not in ("-", "+")):
                    income_col = f"{study} Income"
                    if income_col in calendar_df.columns:
                        calendar_df.at[i, income_col] += payment
                        daily_total += payment

            calendar_df.at[i, "Daily Total"] = daily_total

        # Calculate totals
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

        # Prepare display
        final_ordered_columns = [col for col in ordered_columns if col in calendar_df.columns and 
                                not any(x in col for x in ["Income", "Total"])]
        calendar_df_display = calendar_df[final_ordered_columns].copy()

        # Display site information
        st.subheader("Site Summary")
        site_summary_data = []
        for site in unique_sites:
            site_patients = patients_df[patients_df["Site"] == site]
            site_studies = site_patients["Study"].unique()
            
            site_screen_fails = 0
            for _, patient in site_patients.iterrows():
                patient_study_key = f"{patient['PatientID']}_{patient['Study']}"
                if patient_study_key in screen_failures:
                    site_screen_fails += 1
            
            site_summary_data.append({
                "Site": site,
                "Patients": len(site_patients),
                "Screen Failures": site_screen_fails,
                "Active Patients": len(site_patients) - site_screen_fails,
                "Studies": ", ".join(sorted(site_studies))
            })
        
        site_summary_df = pd.DataFrame(site_summary_data)
        st.dataframe(site_summary_df, use_container_width=True)

        # Display legend with color coding
        if actual_visits_df is not None:
            st.info("""
            **Legend with Color Coding:**
            
            **Actual Visits:**
            - ✓ Visit X (Green background) = Completed Visit (within tolerance window)  
            - ⚠️ Visit X (Yellow background) = Completed Visit (outside tolerance window)
            - ❌ Screen Fail X (Red background) = Screen failure (no future visits)
            
            **Scheduled Visits:**
            - Visit X (Gray background) = Scheduled/Planned Visit
            - \\- (Light gray, italic) = Before tolerance period
            - \\+ (Light gray, italic) = After tolerance period
            """)
        else:
            st.info("**Legend:** Visit X (Gray) = Scheduled Visit, - = Before tolerance, + = After tolerance")

        # Display calendar with site headers
        st.subheader("Generated Visit Calendar")
        display_df = calendar_df_display.copy()
        display_df_for_view = display_df.copy()
        display_df_for_view["Date"] = display_df_for_view["Date"].dt.strftime("%Y-%m-%d")

        # Create site header row
        site_header_row = {}
        for col in display_df_for_view.columns:
            if col in ["Date", "Day"]:
                site_header_row[col] = ""
            else:
                site_found = ""
                for site in unique_sites:
                    if col in site_column_mapping.get(site, []):
                        site_found = site
                        break
                site_header_row[col] = site_found

        # Combine header with data
        site_header_df = pd.DataFrame([site_header_row])
        display_with_header = pd.concat([site_header_df, display_df_for_view], ignore_index=True)

        try:
            # Apply color-coded styling
            def highlight_with_header(row):
                if row.name == 0:  # Site header row
                    styles = []
                    for col_name in row.index:
                        if row[col_name] != "":
                            styles.append('background-color: #e6f3ff; font-weight: bold; text-align: center; border: 1px solid #ccc;')
                        else:
                            styles.append('background-color: #f8f9fa; border: 1px solid #ccc;')
                    return styles
                else:
                    # Data rows with visit type color coding
                    styles = []
                    for col_idx, (col_name, cell_value) in enumerate(row.items()):
                        style = ""
                        
                        # Date-based styling
                        try:
                            if col_name == "Date":
                                date_obj = pd.to_datetime(cell_value)
                                if not pd.isna(date_obj):
                                    if date_obj.month == 3 and date_obj.day == 31:
                                        style = 'background-color: #1e40af; color: white; font-weight: bold;'
                                    elif date_obj == date_obj + pd.offsets.MonthEnd(0):
                                        style = 'background-color: #3b82f6; color: white; font-weight: bold;'
                                    elif date_obj.weekday() in (5, 6):
                                        style = 'background-color: #f3f4f6;'
                        except Exception:
                            pass
                        
                        # Visit-specific color coding
                        if col_name not in ["Date", "Day"] and str(cell_value) != "" and style == "":
                            cell_str = str(cell_value)
                            
                            if "✓ Visit" in cell_str:  # Completed visits
                                style = 'background-color: #d4edda; color: #155724; font-weight: bold;'
                            elif "⚠️ Visit" in cell_str:  # Out of window visits
                                style = 'background-color: #fff3cd; color: #856404; font-weight: bold;'
                            elif "❌ Screen Fail" in cell_str:  # Screen failures
                                style = 'background-color: #f8d7da; color: #721c24; font-weight: bold;'
                            elif "Visit " in cell_str and not cell_str.startswith("✓") and not cell_str.startswith("⚠️"):  # Scheduled
                                style = 'background-color: #e2e3e5; color: #383d41; font-weight: normal;'
                            elif cell_str in ["+", "-"]:  # Tolerance periods
                                style = 'background-color: #f8f9fa; color: #6c757d; font-style: italic;'
                        
                        styles.append(style)
                    
                    return styles

            styled_df = display_with_header.style.apply(highlight_with_header, axis=1)
            
            import streamlit.components.v1 as components
            html_table = f"""
            <div style='max-height: 700px; overflow: auto; border: 1px solid #ddd;'>
                {styled_df.to_html(escape=False)}
            </div>
            """
            components.html(html_table, height=720, scrolling=True)
        except Exception as e:
            st.write(f"Styling error: {e}")
            st.dataframe(display_with_header, use_container_width=True)

        # Financial Analysis
        st.subheader("Financial Analysis")
        
        financial_df = visits_df[
            (visits_df['Visit'].str.startswith("✓")) |
            (visits_df['Visit'].str.startswith("❌ Screen Fail")) |
            (visits_df['Visit'].str.contains('Visit', na=False) & (~visits_df.get('IsActual', False)))
        ].copy()
        
        financial_df['MonthYear'] = financial_df['Date'].dt.to_period('M')
        financial_df['Quarter'] = financial_df['Date'].dt.quarter
        financial_df['Year'] = financial_df['Date'].dt.year
        financial_df['QuarterYear'] = financial_df['Year'].astype(str) + '-Q' + financial_df['Quarter'].astype(str)
        
        actual_financial = financial_df[financial_df.get('IsActual', False)]
        scheduled_financial = financial_df[~financial_df.get('IsActual', True)]
        
        if not actual_financial.empty:
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                actual_income = actual_financial['Payment'].sum()
                st.metric("Actual Income (Completed)", f"£{actual_income:,.2f}")
            with col2:
                scheduled_income = scheduled_financial['Payment'].sum()
                st.metric("Scheduled Income (Pending)", f"£{scheduled_income:,.2f}")
            with col3:
                total_income = actual_income + scheduled_income
                st.metric("Total Income", f"£{total_income:,.2f}")
            with col4:
                screen_fail_count = len(actual_financial[actual_financial.get('IsScreenFail', False)])
                st.metric("Screen Failures", screen_fail_count)
            
            completion_rate = (len(actual_financial) / len(financial_df)) * 100 if len(financial_df) > 0 else 0
            st.metric("Visit Completion Rate", f"{completion_rate:.1f}%")

        # Downloads section
        st.subheader("Download Options")

        # Excel exports with formatting
        try:
            import openpyxl
            from openpyxl.styles import PatternFill, Font, Alignment
            from openpyxl.utils import get_column_letter
            
            excel_financial_cols = ["Daily Total", "Monthly Total", "FY Total"] + [c for c in calendar_df.columns if "Income" in c]
            excel_full_df = calendar_df[final_ordered_columns + [col for col in excel_financial_cols if col in calendar_df.columns]].copy()
            
            excel_full_df["Date"] = excel_full_df["Date"].dt.strftime("%d/%m/%Y")
            
            for col in excel_financial_cols:
                if col in excel_full_df.columns:
                    if col in ["Monthly Total", "FY Total"]:
                        excel_full_df[col] = excel_full_df[col].apply(lambda v: f"£{v:,.2f}" if pd.notna(v) and v != 0 else "")
                    else:
                        excel_full_df[col] = excel_full_df[col].apply(lambda v: f"£{v:,.2f}" if pd.notna(v) else "£0.00")

            # Excel with finances and site headers
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                excel_full_df.to_excel(writer, index=False, sheet_name="VisitCalendar", startrow=1)
                ws = writer.sheets["VisitCalendar"]

                # Add site headers
                for col_idx, col_name in enumerate(excel_full_df.columns, 1):
                    col_letter = get_column_letter(col_idx)
                    if col_name not in ["Date", "Day"] and not any(x in col_name for x in ["Income", "Total"]):
                        for site in unique_sites:
                            if col_name in site_column_mapping.get(site, []):
                                ws[f"{col_letter}1"] = site
                                ws[f"{col_letter}1"].font = Font(bold=True, size=12)
                                ws[f"{col_letter}1"].fill = PatternFill(start_color="FFE6F3FF", end_color="FFE6F3FF", fill_type="solid")
                                ws[f"{col_letter}1"].alignment = Alignment(horizontal="center")
                                break

                # Auto-adjust column widths
                for idx, col in enumerate(excel_full_df.columns, 1):
                    col_letter = get_column_letter(idx)
                    max_length = max([len(str(cell)) if cell is not None else 0 for cell in excel_full_df[col].tolist()] + [len(col)])
                    ws.column_dimensions[col_letter].width = max(10, max_length + 2)

            st.download_button(
                "Excel with Finances & Site Headers",
                data=output.getvalue(),
                file_name="VisitCalendar_WithFinances_SiteGrouped.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        except ImportError:
            st.warning("Excel formatting unavailable - openpyxl not installed")

    except Exception as e:
        st.error(f"Error processing files: {e}")
        st.exception(e)

else:
    st.info("Please upload both Patients and Trials files to get started.")
    
    st.markdown("""
    ### Expected File Structure:
    
    **Patients File:**
    - PatientID, Study, StartDate
    - Site/PatientPractice (optional - for patient origin)
    
    **Trials File:**
    - Study, Day, VisitNo, SiteforVisit
    - Income/Payment, ToleranceBefore, ToleranceAfter (optional)
    
    **Actual Visits File (Optional):**
    - PatientID, Study, VisitNo, ActualDate
    - ActualPayment, Notes (optional)
    - Use 'ScreenFail' in Notes to stop future visits
    """)
