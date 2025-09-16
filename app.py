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
st.caption("v2.2.0 | Updated: Support for combined patient/visit file format + automatic file conversion tool")

st.sidebar.header("📁 Upload Data Files")
patients_file = st.sidebar.file_uploader("Upload Patients File", type=['csv', 'xls', 'xlsx'], key="patients")
trials_file = st.sidebar.file_uploader("Upload Trials File", type=['csv', 'xls', 'xlsx'], key="trials")
actual_visits_file = st.sidebar.file_uploader("Upload Actual Visits File (Optional)", type=['csv', 'xls', 'xlsx'], key="actual_visits")

# Information about required columns
with st.sidebar.expander("ℹ️ File Format Options"):
    st.write("**Option 1: Combined Format (Recommended)**")
    st.write("Upload single file with both patient and visit data:")
    st.write("- PatientID, Study, StartDate, Site/PatientPractice")
    st.write("- RecordType ('Patient' or 'Visit')")  
    st.write("- VisitNo, ActualDate, ActualPayment, Notes")
    st.write("")
    st.write("**Option 2: Separate Files**")
    st.write("**Patients File:**")
    st.write("- PatientID, Study, StartDate")
    st.write("- Site/PatientSite/Practice (optional)")
    st.write("")
    st.write("**Trials File:**")
    st.write("- Study, Day, VisitNo, SiteforVisit")
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
        # Use engine='openpyxl' for modern Excel files
        return pd.read_excel(uploaded_file, engine="openpyxl")


# === Excel column letter helper ===
def excel_col_letter(idx):
    from openpyxl.utils import get_column_letter
    return get_column_letter(idx)


# === Main Logic ===
if patients_file and trials_file:
    try:
        patients_df = load_file(patients_file)
        trials_df = load_file(trials_file)
        actual_visits_df = load_file(actual_visits_file) if actual_visits_file else None

        # Clean columns
        trials_df.columns = trials_df.columns.str.strip()
        patients_df.columns = patients_df.columns.str.strip()
        if actual_visits_df is not None:
            actual_visits_df.columns = actual_visits_df.columns.str.strip()

        # Required columns check
        required_patients = {"PatientID", "Study", "StartDate"}
        required_trials = {"Study", "Day", "VisitNo"}

        if not required_patients.issubset(patients_df.columns):
            st.error(f"❌ Patients file missing required columns: {required_patients}")
            st.stop()
        if not required_trials.issubset(trials_df.columns):
            st.error(f"❌ Trials file missing required columns: {required_trials}")
            st.stop()

        # Process screen failures from actual visits
        screen_failures = {}  # {patient_id_study: screen_fail_date}
        
        if actual_visits_df is not None:
            required_actual = {"PatientID", "Study", "VisitNo", "ActualDate"}
            if not required_actual.issubset(actual_visits_df.columns):
                st.error(f"❌ Actual visits file missing required columns: {required_actual}")
                st.stop()
            
            # Process actual visits data
            actual_visits_df["PatientID"] = actual_visits_df["PatientID"].astype(str)
            actual_visits_df["Study"] = actual_visits_df["Study"].astype(str)
            actual_visits_df["ActualDate"] = pd.to_datetime(actual_visits_df["ActualDate"], dayfirst=True, errors="coerce")
            
            # Handle ActualPayment column
            if "ActualPayment" not in actual_visits_df.columns:
                actual_visits_df["ActualPayment"] = None
            
            # Handle Notes column
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

        # Check if we're using combined format or separate files
        combined_file_mode = False
        if patients_file and not trials_file:
            # Check if the patients file might be a combined format
            try:
                test_df = load_file(patients_file)
                test_df.columns = test_df.columns.str.strip()
                if "RecordType" in test_df.columns:
                    combined_file_mode = True
                    st.info("📋 Combined format detected - processing patient and visit data from single file")
            except Exception:
                pass

        # Debug: Show which processing path we're taking
        st.write(f"**Debug Path Info:**")
        st.write(f"patients_file uploaded: {patients_file is not None}")
        st.write(f"trials_file uploaded: {trials_file is not None}")
        st.write(f"actual_visits_file uploaded: {actual_visits_file is not None}")
        st.write(f"combined_file_mode: {combined_file_mode}")

        if combined_file_mode:
            # Process combined file format
            combined_df = load_file(patients_file)
            combined_df.columns = combined_df.columns.str.strip()
            
            # Split into patients and visits
            patients_df = combined_df[combined_df["RecordType"] == "Patient"].copy()
            actual_visits_from_combined = combined_df[combined_df["RecordType"] == "Visit"].copy()
            
            # Load trials file separately (still needed for visit schedule)
            if not trials_file:
                st.error("❌ Trials file is still required even with combined patient data format")
                st.stop()
                
            trials_df = load_file(trials_file)
            trials_df.columns = trials_df.columns.str.strip()
            
            # Use visits from combined file if no separate actual visits file
            if not actual_visits_file and len(actual_visits_from_combined) > 0:
                actual_visits_df = actual_visits_from_combined
                st.info(f"📋 Using visit data from combined file ({len(actual_visits_df)} visit records)")
            elif actual_visits_file:
                actual_visits_df = load_file(actual_visits_file)
                st.info("📋 Using separate actual visits file (overrides combined file visit data)")
            else:
                actual_visits_df = None
                
        else:
            # Original separate files format
            if not patients_file or not trials_file:
                st.info("👆 Please upload both Patients and Trials files (CSV or Excel).")
                
                # Add file conversion tool section
                st.subheader("🔄 File Format Conversion Tool")
                st.info("Convert your existing separate files into the new combined format for easier data management")
                
                convert_patients = st.file_uploader("Upload Patients File for Conversion", type=['csv', 'xls', 'xlsx'], key="convert_patients")
                convert_actual_visits = st.file_uploader("Upload Actual Visits File for Conversion (Optional)", type=['csv', 'xls', 'xlsx'], key="convert_actual_visits")
                
                if convert_patients:
                    try:
                        # Load files for conversion
                        conv_patients_df = load_file(convert_patients)
                        conv_patients_df.columns = conv_patients_df.columns.str.strip()
                        
                        conv_actual_visits_df = None
                        if convert_actual_visits:
                            conv_actual_visits_df = load_file(convert_actual_visits)
                            conv_actual_visits_df.columns = conv_actual_visits_df.columns.str.strip()
                        
                        # Create combined format
                        combined_records = []
                        
                        # Add patient records
                        for _, patient in conv_patients_df.iterrows():
                            patient_record = patient.to_dict()
                            patient_record["RecordType"] = "Patient"
                            # Clear visit-related fields for patient records
                            patient_record["VisitNo"] = ""
                            patient_record["ActualDate"] = ""
                            patient_record["ActualPayment"] = ""
                            patient_record["Notes"] = ""
                            combined_records.append(patient_record)
                        
                        # Add visit records
                        if conv_actual_visits_df is not None:
                            for _, visit in conv_actual_visits_df.iterrows():
                                # Find matching patient to get their details
                                matching_patient = conv_patients_df[
                                    (conv_patients_df["PatientID"].astype(str) == str(visit["PatientID"])) &
                                    (conv_patients_df["Study"].astype(str) == str(visit["Study"]))
                                ]
                                
                                if not matching_patient.empty:
                                    patient_info = matching_patient.iloc[0]
                                    visit_record = {
                                        "PatientID": visit["PatientID"],
                                        "Study": visit["Study"],
                                        "StartDate": "",  # Empty for visit records
                                    }
                                    
                                    # Add any other patient fields that exist
                                    for col in conv_patients_df.columns:
                                        if col not in ["PatientID", "Study", "StartDate"]:
                                            visit_record[col] = ""
                                    
                                    # Add visit-specific data
                                    visit_record["RecordType"] = "Visit"
                                    visit_record["VisitNo"] = visit["VisitNo"]
                                    visit_record["ActualDate"] = visit["ActualDate"]
                                    visit_record["ActualPayment"] = visit.get("ActualPayment", "")
                                    visit_record["Notes"] = visit.get("Notes", "")
                                    
                                    combined_records.append(visit_record)
                        
                        # Create DataFrame and prepare for download
                        combined_conversion_df = pd.DataFrame(combined_records)
                        
                        # Ensure consistent column order
                        base_columns = ["PatientID", "Study", "StartDate"]
                        patient_columns = [col for col in conv_patients_df.columns if col not in base_columns]
                        visit_columns = ["RecordType", "VisitNo", "ActualDate", "ActualPayment", "Notes"]
                        
                        all_columns = base_columns + patient_columns + visit_columns
                        combined_conversion_df = combined_conversion_df.reindex(columns=all_columns)
                        
                        # Display preview
                        st.subheader("📋 Combined Format Preview")
                        st.dataframe(combined_conversion_df.head(10), use_container_width=True)
                        
                        st.success(f"✅ Conversion complete: {len(conv_patients_df)} patients, {len(conv_actual_visits_df) if conv_actual_visits_df is not None else 0} visits")
                        
                        # Create Excel download
                        output = io.BytesIO()
                        with pd.ExcelWriter(output, engine='openpyxl') as writer:
                            combined_conversion_df.to_excel(writer, index=False, sheet_name="CombinedPatientData")
                        
                        st.download_button(
                            "📥 Download Combined Format Excel File",
                            data=output.getvalue(),
                            file_name="CombinedPatientData.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                        
                    except Exception as e:
                        st.error(f"❌ Error during conversion: {e}")
                
                st.markdown("""
                ### File Structure Information:
                
                **Combined Format (New - Recommended):**
                Upload a single file containing both patient and visit data with these columns:
                - PatientID, Study, StartDate, Site/PatientPractice (patient info)
                - RecordType ("Patient" or "Visit")
                - VisitNo, ActualDate, ActualPayment, Notes (visit info)
                
                **Separate Files Format (Current):**
                - **Patients File:** PatientID, Study, StartDate, Site/PatientPractice
                - **Trials File:** Study, Day, VisitNo, SiteforVisit, Income/Payment, ToleranceBefore, ToleranceAfter  
                - **Actual Visits File (Optional):** PatientID, Study, VisitNo, ActualDate, ActualPayment, Notes
                """)
                st.stop()
            
            # Process separate files normally
            patients_df = load_file(patients_file)
            trials_df = load_file(trials_file)
            actual_visits_df = load_file(actual_visits_file) if actual_visits_file else None
            st.warning("⚠️ No 'SiteforVisit' column found in trials file. Using default site grouping.")
            trials_df["SiteforVisit"] = "Default Site"

        # Normalise columns (common alternates)
        column_mapping = {
            'Income': 'Payment',
            'Tolerance Before': 'ToleranceBefore',
            'Tolerance After': 'ToleranceAfter',
            'Visit No': 'VisitNo',
            'VisitNumber': 'VisitNo'
        }
        trials_df = trials_df.rename(columns=column_mapping)

        # Types & parsing
        patients_df["PatientID"] = patients_df["PatientID"].astype(str)
        patients_df["Study"] = patients_df["Study"].astype(str)
        patients_df["StartDate"] = pd.to_datetime(patients_df["StartDate"], dayfirst=True, errors="coerce")
        
        # Remove StopDate processing since we're getting it from actual visits now
        if "StopDate" in patients_df.columns:
            st.warning("⚠️ StopDate column found in patients file but will be ignored. Screen failures are now detected from actual visits Notes field.")
            
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
            st.warning("⚠️ No patient origin site column found. Add a column like 'PatientSite', 'Practice', or 'OriginSite' to track where patients come from.")
            patients_df['OriginSite'] = "Unknown Origin"

        # Create patient-site mapping based on their studies and trial sites
        patient_site_mapping = {}
        for _, patient in patients_df.iterrows():
            patient_id = patient["PatientID"]
            study = patient["Study"]
            study_sites = trials_df[trials_df["Study"] == study]["SiteforVisit"].unique()
            if len(study_sites) > 0:
                patient_site_mapping[patient_id] = study_sites[0]
            else:
                patient_site_mapping[patient_id] = "Unknown Site"

        # Add Site column to patients_df for grouping
        patients_df['Site'] = patients_df['PatientID'].map(patient_site_mapping)

        # Build visit records with improved logic for actual visit recalculation and validation
        visit_records = []
        excluded_visits_count = 0
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
            
            # Get all actual visits for this patient to build a recalculation baseline
            patient_actual_visits = {}
            if actual_visits_df is not None:
                patient_actuals = actual_visits_df[
                    (actual_visits_df["PatientID"] == str(patient_id)) & 
                    (actual_visits_df["Study"] == study)
                ].sort_values('VisitNo')
                
                for _, actual_visit in patient_actuals.iterrows():
                    visit_no = actual_visit["VisitNo"]
                    patient_actual_visits[visit_no] = actual_visit
            
            # Calculate the effective start date for future visit calculations
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
                    # This is an actual visit - use actual data
                    visit_date = actual_visit_data["ActualDate"]
                    payment = float(actual_visit_data.get("ActualPayment") or visit.get("Payment", 0) or 0.0)
                    notes = actual_visit_data.get("Notes", "")
                    
                    # Calculate what the expected date should be (for validation)
                    if current_baseline_visit == 0:
                        # First visit - compare against original schedule
                        expected_date = start_date + timedelta(days=visit_day)
                    else:
                        # Calculate from the last actual visit date
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
                    
                    # Update baseline for future calculations if this actual visit differs from original
                    original_scheduled_date = start_date + timedelta(days=visit_day)
                    if visit_date != original_scheduled_date:
                        patient_needs_recalc = True
                    
                    # Update the baseline date and visit number for subsequent calculations
                    current_baseline_date = visit_date
                    current_baseline_visit = visit_no
                    
                    # Mark visit status based on notes and window compliance
                    if "ScreenFail" in str(notes):
                        visit_status = f"❌ Screen Fail {visit_no}"
                    elif is_out_of_window:
                        visit_status = f"⚠️ Visit {visit_no}"  # Warning for out of window
                    else:
                        visit_status = f"✓ Visit {visit_no}"
                    
                    # Check if actual visit is after screen failure
                    if screen_fail_date is not None and visit_date > screen_fail_date:
                        screen_fail_exclusions += 1
                        continue
                    
                    actual_visits_used += 1
                    
                    # Record the actual visit
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
                        "IsActual": True,
                        "IsScreenFail": "ScreenFail" in str(actual_visit_data.get("Notes", "")),
                        "IsOutOfWindow": is_out_of_window
                    })
                    
                else:
                    # This is a scheduled visit - calculate date based on current baseline
                    if current_baseline_visit == 0:
                        # No actual visits yet, use original start date calculation
                        scheduled_date = start_date + timedelta(days=visit_day)
                    else:
                        # Calculate from the last actual visit date
                        # Find the day difference between current visit and the baseline visit
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
                    
                    # For scheduled visits, add main visit + tolerance periods
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

                    # Tolerance before - only for scheduled visits
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

                    # Tolerance after - only for scheduled visits
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

        # Report on recalculations
        if len(recalculated_patients) > 0:
            st.info(f"📅 Recalculated visit schedules for {len(recalculated_patients)} patient(s) based on actual visit dates: {', '.join(recalculated_patients)}")

        # Report on out-of-window visits
        if len(out_of_window_visits) > 0:
            st.warning(f"⚠️ {len(out_of_window_visits)} visit(s) occurred outside tolerance windows:")
            
            # Create a detailed table for out-of-window visits
            oow_df = pd.DataFrame(out_of_window_visits)
            st.dataframe(oow_df, use_container_width=True)

        # Report on actual visits usage
        if actual_visits_df is not None:
            st.success(f"✅ {actual_visits_used} actual visits matched and used in calendar")
            unmatched_actual = len(actual_visits_df) - actual_visits_used
            if unmatched_actual > 0:
                st.warning(f"⚠️ {unmatched_actual} actual visit records could not be matched to scheduled visits")

        # Report on excluded visits
        if screen_fail_exclusions > 0:
            st.warning(f"⚠️ {screen_fail_exclusions} visits were excluded because they occur after screen failure dates.")

        visits_df = pd.DataFrame(visit_records)

        if visits_df.empty:
            st.error("❌ No visits generated. Check that Patient `Study` matches Trial `Study` values and StartDate is populated.")
            st.stop()

        # Build calendar range
        min_date = visits_df["Date"].min() - timedelta(days=1)
        max_date = visits_df["Date"].max() + timedelta(days=1)
        calendar_dates = pd.date_range(start=min_date, end=max_date)
        calendar_df = pd.DataFrame({"Date": calendar_dates})
        calendar_df["Day"] = calendar_df["Date"].dt.day_name()

        # Group patients by site and create ordered column structure
        patients_df["ColumnID"] = patients_df["Study"] + "_" + patients_df["PatientID"]
        
        # Get unique sites and sort them
        unique_sites = sorted(patients_df["Site"].unique())
        
        # Create ordered column list: Date, Day, then patients grouped by site
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
                # Screen failures still count as completed visits for payment
                if (is_actual) or (not is_actual and visit_info not in ("-", "+")):
                    income_col = f"{study} Income"
                    if income_col in calendar_df.columns:
                        calendar_df.at[i, income_col] += payment
                        daily_total += payment

            calendar_df.at[i, "Daily Total"] = daily_total

        # Totals calculation
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

        # Reorder columns for display
        final_ordered_columns = [col for col in ordered_columns if col in calendar_df.columns and 
                                not any(x in col for x in ["Income", "Total"])]
        calendar_df_display = calendar_df[final_ordered_columns].copy()

        # Display site information
        st.subheader("🏢 Site Summary")
        site_summary_data = []
        for site in unique_sites:
            site_patients = patients_df[patients_df["Site"] == site]
            site_studies = site_patients["Study"].unique()
            
            # Count screen failures for this site
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

        # Display legend for visit markers with color coding
        if actual_visits_df is not None:
            st.info("""
            **Legend with Color Coding:**
            
            **Actual Visits:**
            - ✓ Visit X (Green background) = Completed Visit (within tolerance window)  
            - ⚠️ Visit X (Yellow background) = Completed Visit (outside tolerance window)
            - ❌ Screen Fail X (Red background) = Screen failure (no future visits)
            
            **Scheduled Visits:**
            - Visit X (Gray background) = Scheduled/Planned Visit
            - \- (Light gray, italic) = Before tolerance period
            - \+ (Light gray, italic) = After tolerance period
            """)
        else:
            st.info("**Legend:** Visit X (Gray) = Scheduled Visit, - = Before tolerance, + = After tolerance")

        # Display table with site headers
        st.subheader("🗓️ Generated Visit Calendar")
        display_df = calendar_df_display.copy()
        display_df_for_view = display_df.copy()
        display_df_for_view["Date"] = display_df_for_view["Date"].dt.strftime("%Y-%m-%d")

        # Create site header row for display
        site_header_row = {}
        for col in display_df_for_view.columns:
            if col in ["Date", "Day"]:
                site_header_row[col] = ""
            else:
                # Find which site this column belongs to
                site_found = ""
                for site in unique_sites:
                    if col in site_column_mapping.get(site, []):
                        site_found = site
                        break
                site_header_row[col] = site_found

        # Create a DataFrame with the site header as the first row
        site_header_df = pd.DataFrame([site_header_row])
        
        # Combine site header with the main data
        display_with_header = pd.concat([site_header_df, display_df_for_view], ignore_index=True)

        try:
            # Apply styling function with visit color coding
            def highlight_with_header(row):
                if row.name == 0:  # First row is site header
                    styles = []
                    for col_name in row.index:
                        if row[col_name] != "":
                            styles.append('background-color: #e6f3ff; font-weight: bold; text-align: center; border: 1px solid #ccc;')
                        else:
                            styles.append('background-color: #f8f9fa; border: 1px solid #ccc;')
                    return styles
                else:
                    # Apply normal styling to data rows
                    styles = []
                    for col_idx, (col_name, cell_value) in enumerate(row.items()):
                        style = ""
                        
                        # First check for date-based styling (weekends, month-end, etc.)
                        try:
                            if col_name == "Date":
                                date_obj = pd.to_datetime(cell_value)
                                if not pd.isna(date_obj):
                                    # Financial year end (31 March)
                                    if date_obj.month == 3 and date_obj.day == 31:
                                        style = 'background-color: #1e40af; color: white; font-weight: bold;'
                                    # Month end
                                    elif date_obj == date_obj + pd.offsets.MonthEnd(0):
                                        style = 'background-color: #3b82f6; color: white; font-weight: bold;'
                                    # Weekend
                                    elif date_obj.weekday() in (5, 6):
                                        style = 'background-color: #f3f4f6;'
                        except Exception:
                            pass
                        
                        # Then check for visit-specific color coding in patient columns
                        if col_name not in ["Date", "Day"] and str(cell_value) != "" and style == "":
                            # Check if this cell contains visit information
                            cell_str = str(cell_value)
                            
                            # Color coding for different visit types
                            if "✓ Visit" in cell_str:  # Completed visits (within window)
                                style = 'background-color: #d4edda; color: #155724; font-weight: bold;'
                            elif "⚠️ Visit" in cell_str:  # Completed visits (outside window)
                                style = 'background-color: #fff3cd; color: #856404; font-weight: bold;'
                            elif "❌ Screen Fail" in cell_str:  # Screen failures
                                style = 'background-color: #f8d7da; color: #721c24; font-weight: bold;'
                            elif "Visit " in cell_str and not cell_str.startswith("✓") and not cell_str.startswith("⚠️"):  # Scheduled visits
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

        # Financial Analysis Section
        st.subheader("💰 Financial Analysis")
        
        # Calculate financial data using only actual visits and scheduled main visits
        # Exclude screen failures from projected income but include them in actual income
        financial_df = visits_df[
            (visits_df['Visit'].str.startswith("✓")) |  # Actual completed visits (includes visit number)
            (visits_df['Visit'].str.startswith("❌ Screen Fail")) |  # Screen failure visits (actual)
            (visits_df['Visit'].str.contains('Visit', na=False) & (~visits_df.get('IsActual', False)))  # Scheduled main visits
        ].copy()
        
        financial_df['MonthYear'] = financial_df['Date'].dt.to_period('M')
        financial_df['Quarter'] = financial_df['Date'].dt.quarter
        financial_df['Year'] = financial_df['Date'].dt.year
        financial_df['QuarterYear'] = financial_df['Year'].astype(str) + '-Q' + financial_df['Quarter'].astype(str)
        
        # Separate actual vs scheduled income
        actual_financial = financial_df[financial_df.get('IsActual', False)]
        scheduled_financial = financial_df[~financial_df.get('IsActual', True)]
        
        # Display actual vs scheduled summary
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

        # Monthly income analysis
        monthly_income_by_site = financial_df.groupby(['SiteofVisit', 'MonthYear'])['Payment'].sum().reset_index()
        monthly_pivot = monthly_income_by_site.pivot(index='MonthYear', columns='SiteofVisit', values='Payment').fillna(0)
        monthly_pivot['Total'] = monthly_pivot.sum(axis=1)
        
        # Quarterly totals
        quarterly_income_by_site = financial_df.groupby(['SiteofVisit', 'QuarterYear'])['Payment'].sum().reset_index()
        quarterly_pivot = quarterly_income_by_site.pivot(index='QuarterYear', columns='SiteofVisit', values='Payment').fillna(0)
        quarterly_pivot['Total'] = quarterly_pivot.sum(axis=1)
        
        # Monthly Income Chart
        st.subheader("📊 Monthly Income Chart")
        monthly_chart_data = monthly_pivot[[col for col in monthly_pivot.columns if col != 'Total']]
        monthly_chart_data.index = monthly_chart_data.index.astype(str)
        st.bar_chart(monthly_chart_data)
        
        # Display financial tables
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**Monthly Income by Visit Site**")
            monthly_display = monthly_pivot.copy()
            monthly_display.index = monthly_display.index.astype(str)
            
            for col in monthly_display.columns:
                monthly_display[col] = monthly_display[col].apply(lambda x: f"£{x:,.2f}" if x != 0 else "£0.00")
            
            st.dataframe(monthly_display, use_container_width=True)
        
        with col2:
            st.write("**Quarterly Income by Visit Site**")
            quarterly_display = quarterly_pivot.copy()
            
            for col in quarterly_display.columns:
                quarterly_display[col] = quarterly_display[col].apply(lambda x: f"£{x:,.2f}" if x != 0 else "£0.00")
            
            st.dataframe(quarterly_display, use_container_width=True)

        # Summary totals
        st.write("**Financial Summary**")
        total_by_site = financial_df.groupby('SiteofVisit')['Payment'].sum()
        summary_data = []
        for site in total_by_site.index:
            summary_data.append({
                "Site": site,
                "Total Income": f"£{total_by_site[site]:,.2f}"
            })
        summary_data.append({
            "Site": "**GRAND TOTAL**",
            "Total Income": f"**£{total_by_site.sum():,.2f}**"
        })
        
        summary_df = pd.DataFrame(summary_data)
        st.dataframe(summary_df, use_container_width=True)

        # Downloads section
        st.subheader("💾 Download Options")

        # Excel exports with formatting and site headers
        try:
            import openpyxl
            from openpyxl.styles import PatternFill, Font, Alignment
            from openpyxl.utils import get_column_letter
            from openpyxl.styles.borders import Border, Side

            excel_available = True
        except ImportError:
            excel_available = False

        if excel_available:
            # Create full df with financial columns for Excel export
            excel_financial_cols = ["Daily Total", "Monthly Total", "FY Total"] + [c for c in calendar_df.columns if "Income" in c]
            excel_full_df = calendar_df[final_ordered_columns + [col for col in excel_financial_cols if col in calendar_df.columns]].copy()
            
            # Format the Date column for UK short date format
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

                # Add site headers in row 1
                for col_idx, col_name in enumerate(excel_full_df.columns, 1):
                    col_letter = get_column_letter(col_idx)
                    
                    if col_name in ["Date", "Day"] or col_name in excel_financial_cols:
                        continue
                    else:
                        for site in unique_sites:
                            if col_name in site_column_mapping.get(site, []):
                                ws[f"{col_letter}1"] = site
                                ws[f"{col_letter}1"].font = Font(bold=True, size=12)
                                ws[f"{col_letter}1"].fill = PatternFill(start_color="FFE6F3FF", end_color="FFE6F3FF", fill_type="solid")
                                ws[f"{col_letter}1"].alignment = Alignment(horizontal="center")
                                break

                # Auto-adjust col widths
                for idx, col in enumerate(excel_full_df.columns, 1):
                    col_letter = get_column_letter(idx)
                    max_length = max(
                        [len(str(cell)) if cell is not None else 0 for cell in excel_full_df[col].tolist()] + [len(col)]
                    )
                    ws.column_dimensions[col_letter].width = max(10, max_length + 2)

                # Define fills / fonts with visit type color coding
                weekend_fill = PatternFill(start_color="FFF3F4F6", end_color="FFF3F4F6", fill_type="solid")
                month_end_fill = PatternFill(start_color="FF3B82F6", end_color="FF3B82F6", fill_type="solid")
                fy_end_fill = PatternFill(start_color="FF1E40AF", end_color="FF1E40AF", fill_type="solid")
                white_font = Font(color="FFFFFFFF", bold=True)
                
                # Visit type color fills
                completed_visit_fill = PatternFill(start_color="FFD4EDDA", end_color="FFD4EDDA", fill_type="solid")  # Green
                completed_visit_font = Font(color="FF155724", bold=True)
                
                out_of_window_fill = PatternFill(start_color="FFFFF3CD", end_color="FFFFF3CD", fill_type="solid")  # Yellow
                out_of_window_font = Font(color="FF856404", bold=True)
                
                screen_fail_fill = PatternFill(start_color="FFF8D7DA", end_color="FFF8D7DA", fill_type="solid")  # Red
                screen_fail_font = Font(color="FF721C24", bold=True)
                
                scheduled_visit_fill = PatternFill(start_color="FFE2E3E5", end_color="FFE2E3E5", fill_type="solid")  # Gray
                scheduled_visit_font = Font(color="FF383D41", bold=False)
                
                tolerance_fill = PatternFill(start_color="FFF8F9FA", end_color="FFF8F9FA", fill_type="solid")  # Light gray
                tolerance_font = Font(color="FF6C757D", italic=True)

                # Apply formatting row-by-row and cell-by-cell (starting from row 3 due to headers)
                for row_idx in range(3, len(excel_full_df) + 3):
                    try:
                        # Get the original date for date-based formatting
                        date_idx = row_idx - 3
                        if date_idx < len(calendar_df):
                            date_obj = calendar_df.iloc[date_idx]["Date"]
                            
                            # Apply date-based formatting first (this affects entire row)
                            date_style_applied = False
                            if not pd.isna(date_obj):
                                if date_obj.month == 3 and date_obj.day == 31:
                                    # Financial year end - apply to entire row
                                    for col_idx in range(1, len(excel_full_df.columns) + 1):
                                        cell = ws.cell(row=row_idx, column=col_idx)
                                        cell.fill = fy_end_fill
                                        cell.font = white_font
                                    date_style_applied = True
                                elif date_obj == date_obj + pd.offsets.MonthEnd(0):
                                    # Month end - apply to entire row
                                    for col_idx in range(1, len(excel_full_df.columns) + 1):
                                        cell = ws.cell(row=row_idx, column=col_idx)
                                        cell.fill = month_end_fill
                                        cell.font = white_font
                                    date_style_applied = True
                                elif date_obj.weekday() in (5, 6):
                                    # Weekend - apply to entire row
                                    for col_idx in range(1, len(excel_full_df.columns) + 1):
                                        cell = ws.cell(row=row_idx, column=col_idx)
                                        cell.fill = weekend_fill
                                    date_style_applied = True
                            
                            # If no date-based styling was applied, apply visit-specific styling to patient columns
                            if not date_style_applied:
                                for col_idx, col_name in enumerate(excel_full_df.columns, 1):
                                    if col_name not in ["Date", "Day"] and not any(x in col_name for x in ["Income", "Total"]):
                                        cell = ws.cell(row=row_idx, column=col_idx)
                                        cell_value = str(cell.value) if cell.value else ""
                                        
                                        # Apply visit-specific color coding
                                        if "✓ Visit" in cell_value:
                                            cell.fill = completed_visit_fill
                                            cell.font = completed_visit_font
                                        elif "⚠️ Visit" in cell_value:
                                            cell.fill = out_of_window_fill
                                            cell.font = out_of_window_font
                                        elif "❌ Screen Fail" in cell_value:
                                            cell.fill = screen_fail_fill
                                            cell.font = screen_fail_font
                                        elif "Visit " in cell_value and not cell_value.startswith("✓") and not cell_value.startswith("⚠️"):
                                            cell.fill = scheduled_visit_fill
                                            cell.font = scheduled_visit_font
                                        elif cell_value in ["+", "-"]:
                                            cell.fill = tolerance_fill
                                            cell.font = tolerance_font

                    except Exception:
                        continue

            st.download_button(
                "💰 Excel with Finances & Site Headers",
                data=output.getvalue(),
                file_name="VisitCalendar_WithFinances_SiteGrouped.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

            # Schedule-only Excel with site headers (using display df)
            schedule_df = display_df.copy()
            schedule_df["Date"] = schedule_df["Date"].dt.strftime("%d/%m/%Y")
                
            output2 = io.BytesIO()
            with pd.ExcelWriter(output2, engine='openpyxl') as writer:
                schedule_df.to_excel(writer, index=False, sheet_name="VisitSchedule", startrow=1)
                ws2 = writer.sheets["VisitSchedule"]

                # Add site headers
                for col_idx, col_name in enumerate(schedule_df.columns, 1):
                    col_letter = get_column_letter(col_idx)
                    
                    if col_name not in ["Date", "Day"]:
                        for site in unique_sites:
                            if col_name in site_column_mapping.get(site, []):
                                ws2[f"{col_letter}1"] = site
                                ws2[f"{col_letter}1"].font = Font(bold=True, size=12)
                                ws2[f"{col_letter}1"].fill = PatternFill(start_color="FFE6F3FF", end_color="FFE6F3FF", fill_type="solid")
                                ws2[f"{col_letter}1"].alignment = Alignment(horizontal="center")
                                break

                # Set widths
                for idx, col in enumerate(schedule_df.columns, 1):
                    col_letter = get_column_letter(idx)
                    max_length = max(
                        [len(str(cell)) if cell is not None else 0 for cell in schedule_df[col].tolist()] + [len(col)]
                    )
                    ws2.column_dimensions[col_letter].width = max(10, max_length + 2)

                # Apply same row and cell formatting to schedule-only file
                for row_idx in range(3, len(schedule_df) + 3):
                    try:
                        # Get the original date for date-based formatting
                        date_idx = row_idx - 3
                        if date_idx < len(calendar_df):
                            date_obj = calendar_df.iloc[date_idx]["Date"]
                            
                            # Apply date-based formatting first
                            date_style_applied = False
                            if not pd.isna(date_obj):
                                if date_obj.month == 3 and date_obj.day == 31:
                                    for col_idx in range(1, len(schedule_df.columns) + 1):
                                        cell = ws2.cell(row=row_idx, column=col_idx)
                                        cell.fill = fy_end_fill
                                        cell.font = white_font
                                    date_style_applied = True
                                elif date_obj == date_obj + pd.offsets.MonthEnd(0):
                                    for col_idx in range(1, len(schedule_df.columns) + 1):
                                        cell = ws2.cell(row=row_idx, column=col_idx)
                                        cell.fill = month_end_fill
                                        cell.font = white_font
                                    date_style_applied = True
                                elif date_obj.weekday() in (5, 6):
                                    for col_idx in range(1, len(schedule_df.columns) + 1):
                                        cell = ws2.cell(row=row_idx, column=col_idx)
                                        cell.fill = weekend_fill
                                    date_style_applied = True
                            
                            # Apply visit-specific styling to patient columns if no date styling
                            if not date_style_applied:
                                for col_idx, col_name in enumerate(schedule_df.columns, 1):
                                    if col_name not in ["Date", "Day"]:
                                        cell = ws2.cell(row=row_idx, column=col_idx)
                                        cell_value = str(cell.value) if cell.value else ""
                                        
                                        # Apply visit-specific color coding
                                        if "✓ Visit" in cell_value:
                                            cell.fill = completed_visit_fill
                                            cell.font = completed_visit_font
                                        elif "⚠️ Visit" in cell_value:
                                            cell.fill = out_of_window_fill
                                            cell.font = out_of_window_font
                                        elif "❌ Screen Fail" in cell_value:
                                            cell.fill = screen_fail_fill
                                            cell.font = screen_fail_font
                                        elif "Visit " in cell_value and not cell_value.startswith("✓") and not cell_value.startswith("⚠️"):
                                            cell.fill = scheduled_visit_fill
                                            cell.font = scheduled_visit_font
                                        elif cell_value in ["+", "-"]:
                                            cell.fill = tolerance_fill
                                            cell.font = tolerance_font

                    except Exception:
                        continue

            st.download_button(
                "📅 Excel Schedule Only with Site Headers",
                data=output2.getvalue(),
                file_name="VisitSchedule_Only_SiteGrouped.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.warning("⚠️ Excel formatting unavailable because openpyxl is not installed in this environment.")

        # Summary statistics
        st.subheader("📊 Summary Statistics")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Sites", len(unique_sites))
        with col2:
            st.metric("Total Patients", len(patients_df))
        with col3:
            total_visits = len(financial_df)
            st.metric("Total Visits", total_visits)
        with col4:
            total_income = financial_df["Payment"].sum()
            st.metric("Total Income", f"£{total_income:,.2f}")

        # Actual vs Scheduled breakdown
        if actual_visits_df is not None:
            st.subheader("📈 Visit Status Breakdown")
            col1, col2, col3, col4 = st.columns(4)
            
            actual_count = len(actual_financial)
            scheduled_count = len(scheduled_financial)
            total_visits_due = actual_count + scheduled_count
            screen_fail_visits = len(visits_df[visits_df.get('IsScreenFail', False)])
            
            with col1:
                st.metric("Completed Visits", actual_count - screen_fail_visits)
            with col2:
                st.metric("Screen Failures", screen_fail_visits)
            with col3:
                st.metric("Pending Visits", scheduled_count)
            with col4:
                completion_percentage = ((actual_count - screen_fail_visits) / total_visits_due * 100) if total_visits_due > 0 else 0
                st.metric("Success Rate", f"{completion_percentage:.1f}%")

        # Site-wise breakdown
        st.subheader("🏢 Site-wise Statistics")
        site_stats = []
        for site in unique_sites:
            site_patients = patients_df[patients_df["Site"] == site]
            site_visits = visits_df[(visits_df["PatientID"].isin(site_patients["PatientID"])) & 
                                  ((visits_df["Visit"].str.startswith("✓")) | 
                                   (visits_df["Visit"].str.startswith("❌ Screen Fail")) | 
                                   (visits_df["Visit"].str.contains("Visit")))]
            site_income = visits_df[visits_df["PatientID"].isin(site_patients["PatientID"])]["Payment"].sum()
            
            # Count screen failures vs active patients
            site_screen_fails = 0
            for _, patient in site_patients.iterrows():
                patient_study_key = f"{patient['PatientID']}_{patient['Study']}"
                if patient_study_key in screen_failures:
                    site_screen_fails += 1
            
            active_patients = len(site_patients) - site_screen_fails
            
            # Count completed vs pending visits for this site
            completed_visits = len(site_visits[site_visits["Visit"].str.startswith("✓")]) if actual_visits_df is not None else 0
            screen_fail_visits = len(site_visits[site_visits["Visit"].str.startswith("❌ Screen Fail")]) if actual_visits_df is not None else 0
            total_visits = len(site_visits)
            pending_visits = total_visits - completed_visits - screen_fail_visits
            
            site_stats.append({
                "Site": site,
                "Total Patients": len(site_patients),
                "Active Patients": active_patients,
                "Screen Failures": site_screen_fails,
                "Completed Visits": completed_visits,
                "Screen Fail Visits": screen_fail_visits,
                "Pending Visits": pending_visits,
                "Total Visits": total_visits,
                "Total Income": f"£{site_income:,.2f}"
            })
        
        site_stats_df = pd.DataFrame(site_stats)
        st.dataframe(site_stats_df, use_container_width=True)

        # Monthly analysis by site
        st.subheader("📅 Monthly Analysis by Site")
        
        # Create month-year period for analysis
        visits_df['MonthYear'] = visits_df['Date'].dt.to_period('M')
        
        # Filter only actual visits and main scheduled visits
        analysis_visits = visits_df[
            (visits_df['Visit'].str.startswith("✓")) |  # Actual completed visits (includes visit number)
            (visits_df['Visit'].str.startswith("❌ Screen Fail")) |  # Screen failure visits
            (visits_df['Visit'].str.contains('Visit', na=False) & (~visits_df.get('IsActual', False)))  # Scheduled main visits
        ]
        
        # Analysis 1: Visits by Site of Visit (where visits happen)
        st.write("**Analysis by Visit Location (Where visits occur)**")
        visits_by_site_month = analysis_visits.groupby(['SiteofVisit', 'MonthYear']).size().reset_index(name='Visits')
        visits_pivot = visits_by_site_month.pivot(index='MonthYear', columns='SiteofVisit', values='Visits').fillna(0)
        
        # Calculate visit ratios
        visits_pivot['Total_Visits'] = visits_pivot.sum(axis=1)
        visit_sites = [col for col in visits_pivot.columns if col != 'Total_Visits']
        for site in visit_sites:
            visits_pivot[f'{site}_Ratio'] = (visits_pivot[site] / visits_pivot['Total_Visits'] * 100).round(1)
        
        # Count unique patients by visit site per month
        patients_by_visit_site_month = analysis_visits.groupby(['SiteofVisit', 'MonthYear'])['PatientID'].nunique().reset_index(name='Patients')
        patients_visit_pivot = patients_by_visit_site_month.pivot(index='MonthYear', columns='SiteofVisit', values='Patients').fillna(0)
        
        # Calculate patient ratios for visit site
        patients_visit_pivot['Total_Patients'] = patients_visit_pivot.sum(axis=1)
        for site in visit_sites:
            if site in patients_visit_pivot.columns:
                patients_visit_pivot[f'{site}_Ratio'] = (patients_visit_pivot[site] / patients_visit_pivot['Total_Patients'] * 100).round(1)
        
        # Analysis 2: Patients by Origin Site (where patients come from)
        st.write("**Analysis by Patient Origin (Where patients come from)**")
        patients_by_origin_month = analysis_visits.groupby(['PatientOrigin', 'MonthYear'])['PatientID'].nunique().reset_index(name='Patients')
        patients_origin_pivot = patients_by_origin_month.pivot(index='MonthYear', columns='PatientOrigin', values='Patients').fillna(0)
        
        # Calculate patient origin ratios
        patients_origin_pivot['Total_Patients'] = patients_origin_pivot.sum(axis=1)
        origin_sites = [col for col in patients_origin_pivot.columns if col != 'Total_Patients']
        for site in origin_sites:
            patients_origin_pivot[f'{site}_Ratio'] = (patients_origin_pivot[site] / patients_origin_pivot['Total_Patients'] * 100).round(1)
        
        # Display tables
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**Monthly Visits by Visit Site**")
            visits_display = visits_pivot.copy()
            visits_display.index = visits_display.index.astype(str)
            
            # Reorder columns
            display_cols = []
            for site in sorted(visit_sites):
                display_cols.append(site)
            for site in sorted(visit_sites):
                ratio_col = f'{site}_Ratio'
                if ratio_col in visits_display.columns:
                    display_cols.append(ratio_col)
            display_cols.append('Total_Visits')
            
            visits_display = visits_display[display_cols]
            st.dataframe(visits_display, use_container_width=True)
        
        with col2:
            st.write("**Monthly Patients by Visit Site**")
            patients_visit_display = patients_visit_pivot.copy()
            patients_visit_display.index = patients_visit_display.index.astype(str)
            
            # Reorder columns
            display_cols = []
            for site in sorted(visit_sites):
                if site in patients_visit_display.columns:
                    display_cols.append(site)
            for site in sorted(visit_sites):
                ratio_col = f'{site}_Ratio'
                if ratio_col in patients_visit_display.columns:
                    display_cols.append(ratio_col)
            display_cols.append('Total_Patients')
            
            patients_visit_display = patients_visit_display[display_cols]
            st.dataframe(patients_visit_display, use_container_width=True)
        
        # Patient Origin Analysis
        st.write("**Monthly Patients by Origin Site (Where patients come from)**")
        patients_origin_display = patients_origin_pivot.copy()
        patients_origin_display.index = patients_origin_display.index.astype(str)
        
        # Reorder columns
        display_cols = []
        for site in sorted(origin_sites):
            display_cols.append(site)
        for site in sorted(origin_sites):
            ratio_col = f'{site}_Ratio'
            if ratio_col in patients_origin_display.columns:
                display_cols.append(ratio_col)
        display_cols.append('Total_Patients')
        
        patients_origin_display = patients_origin_display[display_cols]
        st.dataframe(patients_origin_display, use_container_width=True)
        
        # Cross-tabulation: Origin vs Visit Site
        st.write("**Cross-Analysis: Patient Origin vs Visit Site**")
        cross_tab = analysis_visits.groupby(['PatientOrigin', 'SiteofVisit'])['PatientID'].nunique().reset_index(name='Patients')
        cross_pivot = cross_tab.pivot(index='PatientOrigin', columns='SiteofVisit', values='Patients').fillna(0)
        cross_pivot['Total'] = cross_pivot.sum(axis=1)
        
        # Add row percentages
        for col in cross_pivot.columns:
            if col != 'Total':
                cross_pivot[f'{col}_%'] = (cross_pivot[col] / cross_pivot['Total'] * 100).round(1)
        
        st.dataframe(cross_pivot, use_container_width=True)
        
        # Charts
        st.subheader("📊 Monthly Trends")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.write("**Visits by Visit Site**")
            if not visits_pivot.empty:
                chart_data = visits_pivot[[col for col in visits_pivot.columns if not col.endswith('_Ratio') and col != 'Total_Visits']]
                chart_data.index = chart_data.index.astype(str)
                st.bar_chart(chart_data)
        
        with col2:
            st.write("**Patients by Visit Site**") 
            if not patients_visit_pivot.empty:
                chart_data = patients_visit_pivot[[col for col in patients_visit_pivot.columns if not col.endswith('_Ratio') and col != 'Total_Patients']]
                chart_data.index = chart_data.index.astype(str)
                st.bar_chart(chart_data)
        
        with col3:
            st.write("**Patients by Origin Site**")
            if not patients_origin_pivot.empty:
                chart_data = patients_origin_pivot[[col for col in patients_origin_pivot.columns if not col.endswith('_Ratio') and col != 'Total_Patients']]
                chart_data.index = chart_data.index.astype(str)
                st.bar_chart(chart_data)

    except Exception as e:
        st.error(f"❌ Error processing files: {e}")
        st.exception(e)
else:
    st.info("👆 Please upload both Patients and Trials files (CSV or Excel).")
    st.markdown("""
    ### Expected File Structure:
    
    **Patients File should contain:**
    - PatientID
    - Study 
    - StartDate
    - Site/PatientSite/Practice (optional - for patient origin)
    - Note: StopDate no longer needed - screen failures detected from actual visits
    
    **Trials File should contain:**
    - Study
    - Day
    - VisitNo  
    - SiteforVisit (used for site grouping)
    - Income/Payment (optional)
    - ToleranceBefore, ToleranceAfter (optional)
    
    **Actual Visits File (Optional) should contain:**
    - PatientID
    - Study
    - VisitNo
    - ActualDate
    - ActualPayment (optional)
    - Notes (optional - use "ScreenFail" to stop future visits)
    """)
