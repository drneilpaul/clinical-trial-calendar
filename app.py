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
st.caption("v1.6.1 | Updated: Fixed site grouping with proper patient origin handling")

st.sidebar.header("📁 Upload Data Files")
patients_file = st.sidebar.file_uploader("Upload Patients File", type=['csv', 'xls', 'xlsx'], key="patients")
trials_file = st.sidebar.file_uploader("Upload Trials File", type=['csv', 'xls', 'xlsx'], key="trials")

# Information about required columns
with st.sidebar.expander("ℹ️ Required Columns"):
    st.write("**Patients File:**")
    st.write("- PatientID")
    st.write("- Study") 
    st.write("- StartDate")
    st.write("- Site/PatientSite/Practice (optional - for patient origin)")
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
            # For now, use a default value
            patients_df['OriginSite'] = "Unknown Origin"

        # Create patient-site mapping based on their studies and trial sites
        # This will be used for the Site column for grouping purposes
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

        # Add Site column to patients_df for grouping (this is different from OriginSite)
        patients_df['Site'] = patients_df['PatientID'].map(patient_site_mapping)

        # Build visit records
        visit_records = []
        for _, patient in patients_df.iterrows():
            patient_id = patient["PatientID"]
            study = patient["Study"]
            start_date = patient["StartDate"]
            patient_origin = patient["OriginSite"]

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
                    "SiteofVisit": site,
                    "PatientOrigin": patient_origin
                })

                # Tolerance before
                for i in range(1, tol_before + 1):
                    visit_records.append({
                        "Date": visit_date - timedelta(days=i),
                        "PatientID": patient_id,
                        "Visit": "-",
                        "Study": study,
                        "Payment": 0,
                        "SiteofVisit": site,
                        "PatientOrigin": patient_origin
                    })

                # Tolerance after
                for i in range(1, tol_after + 1):
                    visit_records.append({
                        "Date": visit_date + timedelta(days=i),
                        "PatientID": patient_id,
                        "Visit": "+",
                        "Study": study,
                        "Payment": 0,
                        "SiteofVisit": site,
                        "PatientOrigin": patient_origin
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

        # Create income tracking columns (but don't add to display)
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
        
        # Reorder columns for display (exclude financial columns)
        final_ordered_columns = [col for col in ordered_columns if col in calendar_df.columns and 
                                not any(x in col for x in ["Income", "Total"])]
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
            # Skip formatting for non-numeric values (like site headers)
            if isinstance(v, str) and not v.replace('.', '').replace('-', '').isdigit():
                return v
            if pd.isna(v) or v == 0:
                return "£0.00"
            try:
                return f"£{float(v):,.2f}"
            except (ValueError, TypeError):
                return v

        def fmt_currency_summary(v):
            if pd.isna(v):
                return ""
            if v == 0:
                return "£0.00"
            try:
                return f"£{float(v):,.2f}"
            except (ValueError, TypeError):
                return v

        # No financial columns in main display
        financial_cols = []
        format_funcs = {}

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
            # Apply styling function that handles the header row differently
            def highlight_with_header(row):
                if row.name == 0:  # First row is site header
                    # Style site header row
                    styles = []
                    for col_name in row.index:
                        if row[col_name] != "":  # Site name present
                            styles.append('background-color: #e6f3ff; font-weight: bold; text-align: center; border: 1px solid #ccc;')
                        else:
                            styles.append('background-color: #f8f9fa; border: 1px solid #ccc;')
                    return styles
                else:
                    # Apply normal styling to data rows
                    try:
                        date_obj = pd.to_datetime(row.get("Date"))
                        if pd.isna(date_obj):
                            return [''] * len(row)

                        # Financial year end (31 March)
                        if date_obj.month == 3 and date_obj.day == 31:
                            return ['background-color: #1e40af; color: white; font-weight: bold'] * len(row)

                        # Month end
                        if date_obj == date_obj + pd.offsets.MonthEnd(0):
                            return ['background-color: #3b82f6; color: white; font-weight: bold'] * len(row)

                        # Weekend
                        if date_obj.weekday() in (5, 6):
                            return ['background-color: #f3f4f6'] * len(row)

                    except Exception:
                        pass
                    return [''] * len(row)

            styled_df = display_with_header.style.format(format_funcs).apply(highlight_with_header, axis=1)
            
            import streamlit.components.v1 as components
            html_table = f"""
            <div style='max-height: 700px; overflow: auto; border: 1px solid #ddd;'>
                {styled_df.to_html(escape=False)}
            </div>
            """
            components.html(html_table, height=720, scrolling=True)
        except Exception as e:
            st.write(f"Styling error: {e}")
            # Fallback to regular dataframe display
            st.dataframe(display_with_header, use_container_width=True)

        # Financial Analysis Section
        st.subheader("💰 Financial Analysis")
        
        # Calculate monthly income by visit site
        financial_df = visits_df[visits_df['Visit'].str.contains('Visit', na=False)].copy()
        financial_df['MonthYear'] = financial_df['Date'].dt.to_period('M')
        financial_df['Quarter'] = financial_df['Date'].dt.quarter
        financial_df['Year'] = financial_df['Date'].dt.year
        financial_df['QuarterYear'] = financial_df['Year'].astype(str) + '-Q' + financial_df['Quarter'].astype(str)
        
        # Monthly income by site
        monthly_income_by_site = financial_df.groupby(['SiteofVisit', 'MonthYear'])['Payment'].sum().reset_index()
        monthly_pivot = monthly_income_by_site.pivot(index='MonthYear', columns='SiteofVisit', values='Payment').fillna(0)
        monthly_pivot['Total'] = monthly_pivot.sum(axis=1)
        
        # Running totals
        for col in monthly_pivot.columns:
            monthly_pivot[f'{col}_Running'] = monthly_pivot[col].cumsum()
        
        # Quarterly totals by site
        quarterly_income_by_site = financial_df.groupby(['SiteofVisit', 'QuarterYear'])['Payment'].sum().reset_index()
        quarterly_pivot = quarterly_income_by_site.pivot(index='QuarterYear', columns='SiteofVisit', values='Payment').fillna(0)
        quarterly_pivot['Total'] = quarterly_pivot.sum(axis=1)
        
        # Monthly Income Bar Chart
        st.subheader("📊 Monthly Income Chart")
        monthly_chart_data = monthly_pivot[[col for col in monthly_pivot.columns if not col.endswith('_Running') and col != 'Total']]
        monthly_chart_data.index = monthly_chart_data.index.astype(str)
        st.bar_chart(monthly_chart_data)
        
        # Display financial tables
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**Monthly Income by Visit Site**")
            monthly_display = monthly_pivot.copy()
            monthly_display.index = monthly_display.index.astype(str)
            
            # Format as currency
            for col in monthly_display.columns:
                monthly_display[col] = monthly_display[col].apply(lambda x: f"£{x:,.2f}" if x != 0 else "£0.00")
            
            st.dataframe(monthly_display, use_container_width=True)
        
        with col2:
            st.write("**Quarterly Income by Visit Site**")
            quarterly_display = quarterly_pivot.copy()
            
            # Format as currency
            for col in quarterly_display.columns:
                quarterly_display[col] = quarterly_display[col].apply(lambda x: f"£{x:,.2f}" if x != 0 else "£0.00")
            
            st.dataframe(quarterly_display, use_container_width=True)
        
        # Running totals chart
        st.write("**Running Totals by Site**")
        running_totals_chart_data = monthly_pivot[[col for col in monthly_pivot.columns if col.endswith('_Running')]]
        running_totals_chart_data.columns = [col.replace('_Running', '') for col in running_totals_chart_data.columns]
        running_totals_chart_data.index = running_totals_chart_data.index.astype(str)
        st.line_chart(running_totals_chart_data)
        
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
                            for col_idx in range(1, len(excel_full_df.columns) + 1):
                                cell = ws.cell(row=row_idx, column=col_idx)
                                cell.fill = fy_end_fill
                                cell.font = white_font
                        else:
                            last_day = cal.monthrange(date_obj.year, date_obj.month)[1]
                            if date_obj.day == last_day:
                                for col_idx in range(1, len(excel_full_df.columns) + 1):
                                    cell = ws.cell(row=row_idx, column=col_idx)
                                    cell.fill = month_end_fill
                                    cell.font = white_font
                            elif date_obj.weekday() in (5, 6):
                                for col_idx in range(1, len(excel_full_df.columns) + 1):
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

        # Monthly analysis by site
        st.subheader("📅 Monthly Analysis by Site")
        
        # Create month-year period for analysis
        visits_df['MonthYear'] = visits_df['Date'].dt.to_period('M')
        
        # Filter only actual visits (not tolerance periods)
        actual_visits = visits_df[visits_df['Visit'].str.contains('Visit', na=False)]
        
        # Analysis 1: Visits by Site of Visit (where visits happen)
        st.write("**Analysis by Visit Location (Where visits occur)**")
        visits_by_site_month = actual_visits.groupby(['SiteofVisit', 'MonthYear']).size().reset_index(name='Visits')
        visits_pivot = visits_by_site_month.pivot(index='MonthYear', columns='SiteofVisit', values='Visits').fillna(0)
        
        # Calculate visit ratios
        visits_pivot['Total_Visits'] = visits_pivot.sum(axis=1)
        visit_sites = [col for col in visits_pivot.columns if col != 'Total_Visits']
        for site in visit_sites:
            visits_pivot[f'{site}_Ratio'] = (visits_pivot[site] / visits_pivot['Total_Visits'] * 100).round(1)
        
        # Count unique patients by visit site per month
        patients_by_visit_site_month = actual_visits.groupby(['SiteofVisit', 'MonthYear'])['PatientID'].nunique().reset_index(name='Patients')
        patients_visit_pivot = patients_by_visit_site_month.pivot(index='MonthYear', columns='SiteofVisit', values='Patients').fillna(0)
        
        # Calculate patient ratios for visit site
        patients_visit_pivot['Total_Patients'] = patients_visit_pivot.sum(axis=1)
        for site in visit_sites:
            if site in patients_visit_pivot.columns:
                patients_visit_pivot[f'{site}_Ratio'] = (patients_visit_pivot[site] / patients_visit_pivot['Total_Patients'] * 100).round(1)
        
        # Analysis 2: Patients by Origin Site (where patients come from)
        st.write("**Analysis by Patient Origin (Where patients come from)**")
        patients_by_origin_month = actual_visits.groupby(['PatientOrigin', 'MonthYear'])['PatientID'].nunique().reset_index(name='Patients')
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
            
            # Format columns
            format_dict = {}
            for col in visits_display.columns:
                if '_Ratio' in col:
                    format_dict[col] = lambda x: f"{x:.1f}%" if pd.notna(x) and x > 0 else "0.0%"
                else:
                    format_dict[col] = lambda x: f"{int(x)}" if pd.notna(x) else "0"
            
            try:
                st.dataframe(visits_display.style.format(format_dict), use_container_width=True)
            except:
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
            
            # Format columns
            format_dict = {}
            for col in patients_visit_display.columns:
                if '_Ratio' in col:
                    format_dict[col] = lambda x: f"{x:.1f}%" if pd.notna(x) and x > 0 else "0.0%"
                else:
                    format_dict[col] = lambda x: f"{int(x)}" if pd.notna(x) else "0"
            
            try:
                st.dataframe(patients_visit_display.style.format(format_dict), use_container_width=True)
            except:
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
        
        # Format columns
        format_dict = {}
        for col in patients_origin_display.columns:
            if '_Ratio' in col:
                format_dict[col] = lambda x: f"{x:.1f}%" if pd.notna(x) and x > 0 else "0.0%"
            else:
                format_dict[col] = lambda x: f"{int(x)}" if pd.notna(x) else "0"
        
        try:
            st.dataframe(patients_origin_display.style.format(format_dict), use_container_width=True)
        except:
            st.dataframe(patients_origin_display, use_container_width=True)
        
        # Cross-tabulation: Origin vs Visit Site
        st.write("**Cross-Analysis: Patient Origin vs Visit Site**")
        cross_tab = actual_visits.groupby(['PatientOrigin', 'SiteofVisit'])['PatientID'].nunique().reset_index(name='Patients')
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
        st.exception(e)  # This will show the full error traceback for debugging
else:
    st.info("👆 Please upload both Patients and Trials files (CSV or Excel).")
    st.markdown("""
    ### Expected File Structure:
    
    **Patients File should contain:**
    - PatientID
    - Study 
    - StartDate
    - Site/PatientSite/Practice (optional - for patient origin)
    
    **Trials File should contain:**
    - Study
    - Day
    - VisitNo  
    - SiteforVisit (used for site grouping)
    - Income/Payment (optional)
    - ToleranceBefore, ToleranceAfter (optional)
    """)
    
