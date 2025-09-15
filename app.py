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
st.caption("v1.6.0 | Updated: Site grouping using SiteforVisit column with headers above patient columns")

st.sidebar.header("📁 Upload Data Files")
patients_file = st.sidebar.file_uploader("Upload Patients File", type=['csv', 'xls', 'xlsx'], key="patients")
trials_file = st.sidebar.file_uploader("Upload Trials File", type=['csv', 'xls', 'xlsx'], key="trials")

# Information about required columns
with st.sidebar.expander("ℹ️ Required Columns"):
    st.write("**Patients File:**")
    st.write("- PatientID")
    st.write("- Study") 
    st.write("- StartDate")
    st.write("")
    st.write("**Trials File:**")
    st.write("- Study")
    st.write("- Day")
    st.write("- VisitNo")
    st.write("- SiteforVisit (used for grouping)")


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

        # Clean columns
        trials_df.columns = trials_df.columns.str.strip()
        patients_df.columns = patients_df.columns.str.strip()

        # Required columns check
        required_patients = {"PatientID", "Study", "StartDate"}
        required_trials = {"Study", "Day", "VisitNo"}

        if not required_patients.issubset(patients_df.columns):
            st.error(f"❌ Patients file missing required columns: {required_patients}")
            st.stop()
        if not required_trials.issubset(trials_df.columns):
            st.error(f"❌ Trials file missing required columns: {required_trials}")
            st.stop()

        # Check for SiteforVisit column
        if "SiteforVisit" not in trials_df.columns:
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
        trials_df["Study"] = trials_df["Study"].astype(str)
        trials_df["SiteforVisit"] = trials_df["SiteforVisit"].astype(str)

        # Create patient-site mapping based on their studies and trial sites
        patient_site_mapping = {}
        for _, patient in patients_df.iterrows():
            patient_id = patient["PatientID"]
            study = patient["Study"]
            # Find the site for this study from trials data
            study_sites = trials_df[trials_df["Study"] == study]["SiteforVisit"].unique()
            if len(study_sites) > 0:
                patient_site_mapping[patient_id] = study_sites[0]  # Take the first site if multiple
            else:
                patient_site_mapping[patient_id] = "Unknown Site"

        # Add site information to patients dataframe for reference
        patients_df["Site"] = patients_df["PatientID"].map(patient_site_mapping)

        # Build visit records
        visit_records = []
        for _, patient in patients_df.iterrows():
            patient_id = patient["PatientID"]
            study = patient["Study"]
            start_date = patient["StartDate"]
            patient_site = patient["Site"]

            if pd.isna(start_date):
                continue

            study_visits = trials_df[trials_df["Study"] == study]
            for _, visit in study_visits.iterrows():
                try:
                    visit_day = int(visit["Day"])
                except Exception:
                    continue
                visit_date = start_date + timedelta(days=visit_day)
                visit_no = visit.get("VisitNo", "")
                tol_before = int(visit.get("ToleranceBefore", 0) or 0)
                tol_after = int(visit.get("ToleranceAfter", 0) or 0)
                payment = float(visit.get("Payment", 0) or 0.0)
                site = visit.get("SiteforVisit", "Unknown Site")

                # Main visit
                visit_records.append({
                    "Date": visit_date,
                    "PatientID": patient_id,
                    "Visit": f"Visit {visit_no}",
                    "Study": study,
                    "Payment": payment,
                    "Site": site
                })

                # Tolerance before
                for i in range(1, tol_before + 1):
                    visit_records.append({
                        "Date": visit_date - timedelta(days=i),
                        "PatientID": patient_id,
                        "Visit": "-",
                        "Study": study,
                        "Payment": 0,
                        "Site": site
                    })

                # Tolerance after
                for i in range(1, tol_after + 1):
                    visit_records.append({
                        "Date": visit_date + timedelta(days=i),
                        "PatientID": patient_id,
                        "Visit": "+",
                        "Study": study,
                        "Payment": 0,
                        "Site": site
                    })

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
        site_column_mapping = {}  # Track which columns belong to which site
        
        for site in unique_sites:
            site_patients = patients_df[patients_df["Site"] == site].sort_values(["Study", "PatientID"])
            site_columns = []
            for _, patient in site_patients.iterrows():
                col_id = patient["ColumnID"]
                ordered_columns.append(col_id)
                site_columns.append(col_id)
                calendar_df[col_id] = ""
            site_column_mapping[site] = site_columns

        # Add income columns after patient columns
        study_sites = trials_df.groupby("Study")["SiteforVisit"].first().to_dict()
        for study in trials_df["Study"].unique():
            income_col = f"{study} Income"
            ordered_columns.append(income_col)
            calendar_df[income_col] = 0.0
        
        ordered_columns.extend(["Daily Total", "Monthly Total", "FY Total"])
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

                if col_id in calendar_df.columns:
                    if calendar_df.at[i, col_id] == "":
                        calendar_df.at[i, col_id] = visit_info
                    else:
                        calendar_df.at[i, col_id] += f", {visit_info}"

                if visit_info not in ("-", "+"):
                    income_col = f"{study} Income"
                    if income_col in calendar_df.columns:
                        calendar_df.at[i, income_col] += payment
                        daily_total += payment

            calendar_df.at[i, "Daily Total"] = daily_total

        # Totals
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

        # Store helper columns before reordering
        helper_columns = ["MonthPeriod", "IsMonthEnd", "FYStart", "IsFYE"]
        
        # Reorder columns according to site grouping (excluding helper columns)
        final_ordered_columns = [col for col in ordered_columns if col in calendar_df.columns]
        calendar_df_display = calendar_df[final_ordered_columns].copy()

        # Display site information
        st.subheader("🏢 Site Summary")
        site_summary_data = []
        for site in unique_sites:
            site_patients = patients_df[patients_df["Site"] == site]
            site_studies = site_patients["Study"].unique()
            site_summary_data.append({
                "Site": site,
                "Patients": len(site_patients),
                "Studies": ", ".join(sorted(site_studies))
            })
        
        site_summary_df = pd.DataFrame(site_summary_data)
        st.dataframe(site_summary_df, use_container_width=True)

        # Display table with site headers
        st.subheader("🗓️ Generated Visit Calendar")
        display_df = calendar_df_display.copy()
        display_df_for_view = display_df.copy()
        display_df_for_view["Date"] = display_df_for_view["Date"].dt.strftime("%Y-%m-%d")

        def fmt_currency(v):
            if pd.isna(v) or v == 0:
                return ""
            return f"£{v:,.2f}"

        financial_cols = ["Daily Total", "Monthly Total", "FY Total"] + [c for c in display_df_for_view.columns if "Income" in c]
        format_funcs = {col: fmt_currency for col in financial_cols if col in display_df_for_view.columns}

        # Create site header row for display
        site_header_row = ["", ""]  # Date and Day columns
        current_site_index = 0
        sites_list = list(unique_sites)
        
        for col in display_df_for_view.columns[2:]:  # Skip Date and Day
            if col in financial_cols:
                site_header_row.append("")
            else:
                # Check if this column belongs to current site
                found_in_current_site = False
                if current_site_index < len(sites_list):
                    current_site = sites_list[current_site_index]
                    if col in site_column_mapping.get(current_site, []):
                        site_header_row.append(current_site)
                        found_in_current_site = True
                    else:
                        # Move to next site
                        for next_site_idx in range(current_site_index + 1, len(sites_list)):
                            next_site = sites_list[next_site_idx]
                            if col in site_column_mapping.get(next_site, []):
                                current_site_index = next_site_idx
                                site_header_row.append(next_site)
                                found_in_current_site = True
                                break
                
                if not found_in_current_site:
                    site_header_row.append("")

        # Display site header information
        st.write("**Site Organization:**")
        for site, columns in site_column_mapping.items():
            patient_info = []
            for col in columns:
                study, patient_id = col.split("_", 1)
                patient_info.append(f"{study}_{patient_id}")
            st.write(f"**{site}:** {', '.join(patient_info)}")

        try:
            styled_df = display_df_for_view.style.format(format_funcs).apply(highlight_weekends, axis=1).apply(highlight_special_days, axis=1)
            import streamlit.components.v1 as components
            html_table = f"""
            <div style='max-height: 700px; overflow: auto; border: 1px solid #ddd;'>
                {styled_df.to_html(escape=False)}
            </div>
            """
            components.html(html_table, height=720, scrolling=True)
        except Exception:
            st.dataframe(display_df_for_view, use_container_width=True)

        # Chart
        st.subheader("📈 Daily Income Chart")
        st.line_chart(calendar_df.set_index("Date")["Daily Total"])

        # Downloads
        st.subheader("💾 Download Options")
        csv_data = calendar_df_display.to_csv(index=False)
        st.download_button("📄 Download Full CSV", csv_data, "VisitCalendar_Full.csv", "text/csv")

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
            # Prepare excel-friendly df for writing
            excel_df = display_df.copy()
            for col in financial_cols:
                if col in excel_df.columns:
                    if col in ["Monthly Total", "FY Total"]:
                        excel_df[col] = excel_df[col].apply(lambda v: f"£{v:,.2f}" if pd.notna(v) and v != 0 else "")
                    else:
                        excel_df[col] = excel_df[col].apply(lambda v: f"£{v:,.2f}" if pd.notna(v) else "£0.00")

            # Excel with finances and site headers
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                excel_df.to_excel(writer, index=False, sheet_name="VisitCalendar", startrow=1)  # Start at row 2 to leave room for site headers
                ws = writer.sheets["VisitCalendar"]

                # Add site headers in row 1
                current_site_index = 0
                sites_list = list(unique_sites)
                
                for col_idx, col_name in enumerate(excel_df.columns, 1):
                    col_letter = get_column_letter(col_idx)
                    
                    if col_name in ["Date", "Day"] or col_name in financial_cols:
                        # Leave these cells empty or add appropriate headers
                        continue
                    else:
                        # Find which site this column belongs to
                        site_found = False
                        for site in unique_sites:
                            if col_name in site_column_mapping.get(site, []):
                                ws[f"{col_letter}1"] = site
                                ws[f"{col_letter}1"].font = Font(bold=True, size=12)
                                ws[f"{col_letter}1"].fill = PatternFill(start_color="FFE6F3FF", end_color="FFE6F3FF", fill_type="solid")
                                ws[f"{col_letter}1"].alignment = Alignment(horizontal="center")
                                site_found = True
                                break

                # Auto-adjust col widths
                for idx, col in enumerate(excel_df.columns, 1):
                    col_letter = get_column_letter(idx)
                    max_length = max(
                        [len(str(cell)) if cell is not None else 0 for cell in excel_df[col].tolist()] + [len(col)]
                    )
                    ws.column_dimensions[col_letter].width = max(10, max_length + 2)

                # Define fills / fonts
                weekend_fill = PatternFill(start_color="FFF3F4F6", end_color="FFF3F4F6", fill_type="solid")
                month_end_fill = PatternFill(start_color="FF3B82F6", end_color="FF3B82F6", fill_type="solid")
                fy_end_fill = PatternFill(start_color="FF1E40AF", end_color="FF1E40AF", fill_type="solid")
                white_font = Font(color="FFFFFFFF", bold=True)

                # Apply formatting row-by-row (starting from row 3 due to headers)
                for row_idx, date_obj in enumerate(calendar_df["Date"], start=3):
                    try:
                        if pd.isna(date_obj):
                            continue

                        if date_obj.month == 3 and date_obj.day == 31:
                            for col_idx in range(1, len(excel_df.columns) + 1):
                                cell = ws.cell(row=row_idx, column=col_idx)
                                cell.fill = fy_end_fill
                                cell.font = white_font
                        else:
                            last_day = cal.monthrange(date_obj.year, date_obj.month)[1]
                            if date_obj.day == last_day:
                                for col_idx in range(1, len(excel_df.columns) + 1):
                                    cell = ws.cell(row=row_idx, column=col_idx)
                                    cell.fill = month_end_fill
                                    cell.font = white_font
                            elif date_obj.weekday() in (5, 6):
                                for col_idx in range(1, len(excel_df.columns) + 1):
                                    cell = ws.cell(row=row_idx, column=col_idx)
                                    cell.fill = weekend_fill

                    except Exception:
                        continue

            st.download_button(
                "💰 Excel with Finances & Site Headers",
                data=output.getvalue(),
                file_name="VisitCalendar_WithFinances_SiteGrouped.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

            # Schedule-only Excel with site headers
            schedule_df = excel_df.drop(columns=[c for c in financial_cols if c in excel_df.columns])
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

                # Apply same row formatting
                for row_idx, date_obj in enumerate(calendar_df["Date"], start=3):
                    try:
                        if pd.isna(date_obj):
                            continue

                        if date_obj.month == 3 and date_obj.day == 31:
                            for col_idx in range(1, len(schedule_df.columns) + 1):
                                cell = ws2.cell(row=row_idx, column=col_idx)
                                cell.fill = fy_end_fill
                                cell.font = white_font
                        else:
                            last_day = cal.monthrange(date_obj.year, date_obj.month)[1]
                            if date_obj.day == last_day:
                                for col_idx in range(1, len(schedule_df.columns) + 1):
                                    cell = ws2.cell(row=row_idx, column=col_idx)
                                    cell.fill = month_end_fill
                                    cell.font = white_font
                            elif date_obj.weekday() in (5, 6):
                                for col_idx in range(1, len(schedule_df.columns) + 1):
                                    cell = ws2.cell(row=row_idx, column=col_idx)
                                    cell.fill = weekend_fill

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

        # Summary stats
        st.subheader("📊 Summary Statistics")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Sites", len(unique_sites))
        with col2:
            st.metric("Total Patients", len(patients_df))
        with col3:
            total_visits = len(visits_df[visits_df["Visit"].str.contains("Visit")])
            st.metric("Total Visits", total_visits)
        with col4:
            total_income = calendar_df["Daily Total"].sum()
            st.metric("Total Income", f"£{total_income:,.2f}")

        # Site-wise breakdown
        st.subheader("🏢 Site-wise Statistics")
        site_stats = []
        for site in unique_sites:
            site_patients = patients_df[patients_df["Site"] == site]
            site_visits = visits_df[(visits_df["PatientID"].isin(site_patients["PatientID"])) & (visits_df["Visit"].str.contains("Visit"))]
            site_income = visits_df[visits_df["PatientID"].isin(site_patients["PatientID"])]["Payment"].sum()
            
            site_stats.append({
                "Site": site,
                "Patients": len(site_patients),
                "Visits": len(site_visits),
                "Total Income": f"£{site_income:,.2f}"
            })
        
        site_stats_df = pd.DataFrame(site_stats)
        st.dataframe(site_stats_df, use_container_width=True)

    except Exception as e:
        st.error(f"❌ Error processing files: {e}")
        st.exception(e)  # This will show the full error traceback for debugging
else:
    st.info("👆 Please upload both Patients and Trials files (CSV or Excel).")
    st.markdown("""
    ### Expected File Structure:
    
    **Patients File should contain:**
    - PatientID
    - Study 
    - StartDate
    
    **Trials File should contain:**
    - Study
    - Day
    - VisitNo  
    - SiteforVisit (used for site grouping)
    - Income/Payment (optional)
    - ToleranceBefore, ToleranceAfter (optional)
    """)
