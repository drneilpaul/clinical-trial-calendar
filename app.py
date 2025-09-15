import streamlit as st
import pandas as pd
from datetime import timedelta
import io

st.set_page_config(page_title="Clinical Trial Calendar Generator", layout="wide")

# =========================
# Highlighting functions
# =========================
def highlight_special_days(row):
    """Highlight end-of-month and financial year end."""
    try:
        date_obj = pd.to_datetime(row.get("Date"))
        if pd.isna(date_obj):
            return [''] * len(row)

        # Fiscal year end: 31 March
        if date_obj.month == 3 and date_obj.day == 31:
            return ['background-color: #1e40af; color: white; font-weight: bold'] * len(row)

        # Month end
        if date_obj == date_obj + pd.offsets.MonthEnd(0):
            return ['background-color: #3b82f6; color: white; font-weight: bold'] * len(row)

    except Exception:
        pass
    return [''] * len(row)


def highlight_weekends(row):
    """Highlight weekends (Saturday/Sunday)."""
    try:
        date_obj = pd.to_datetime(row.get("Date"))
        if pd.isna(date_obj):
            return [''] * len(row)
        if date_obj.weekday() in (5, 6):  # Sat=5, Sun=6
            return ['background-color: #f3f4f6'] * len(row)
    except Exception:
        pass
    return [''] * len(row)


# =========================
# App start
# =========================
st.title("🏥 Clinical Trial Calendar Generator")
st.caption("v1.4.2 | Version: 2025-09-15 | Cleaned up + fixed loop + Excel col widths")

debug_mode = False  # 👈 set True for debug prints

st.sidebar.header("📁 Upload Data Files")
patients_file = st.sidebar.file_uploader("Upload Patients CSV", type=['csv'], key="patients")
trials_file = st.sidebar.file_uploader("Upload Trials CSV", type=['csv'], key="trials")

if patients_file and trials_file:
    try:
        import openpyxl
        excel_available = True
    except ImportError:
        excel_available = False

    try:
        # =========================
        # Load data
        # =========================
        patients_df = pd.read_csv(patients_file, dayfirst=True)
        trials_df = pd.read_csv(trials_file)

        # Clean headers
        patients_df.columns = patients_df.columns.str.strip()
        trials_df.columns = trials_df.columns.str.strip()

        # Ensure key types are strings
        patients_df["PatientID"] = patients_df["PatientID"].astype(str)
        patients_df["Study"] = patients_df["Study"].astype(str)
        trials_df["Study"] = trials_df["Study"].astype(str)

        if debug_mode:
            st.write("**Debug: After type conversion:**")
            st.write("Patient IDs:", patients_df["PatientID"].tolist())
            st.write("Patient Studies:", patients_df["Study"].tolist())

        # Map alternative column names
        column_mapping = {
            'Income': 'Payment',
            'Tolerance Before': 'ToleranceBefore',
            'Tolerance After': 'ToleranceAfter',
            'Visit No': 'VisitNo',
            'VisitNumber': 'VisitNo'
        }
        trials_df = trials_df.rename(columns=column_mapping)

        patients_df["StartDate"] = pd.to_datetime(patients_df["StartDate"], dayfirst=True)

        # =========================
        # Generate visits
        # =========================
        visit_records = []
        for _, patient in patients_df.iterrows():
            patient_id = patient["PatientID"]
            study = patient["Study"]
            start_date = patient["StartDate"]

            study_visits = trials_df[trials_df["Study"] == study]
            for _, visit in study_visits.iterrows():
                visit_day = int(visit["Day"])
                visit_date = start_date + timedelta(days=visit_day)
                visit_no = visit["VisitNo"]

                tol_before = int(visit.get("ToleranceBefore", 0) or 0)
                tol_after = int(visit.get("ToleranceAfter", 0) or 0)
                payment = float(visit.get("Payment", 0) or 0.0)

                # Main visit
                visit_records.append({
                    "Date": visit_date,
                    "PatientID": patient_id,
                    "Visit": f"Visit {visit_no}",
                    "Study": study,
                    "Payment": payment
                })

                # Tolerance before
                for i in range(1, tol_before + 1):
                    visit_records.append({
                        "Date": visit_date - timedelta(days=i),
                        "PatientID": patient_id,
                        "Visit": "-",
                        "Study": study,
                        "Payment": 0
                    })

                # Tolerance after
                for i in range(1, tol_after + 1):
                    visit_records.append({
                        "Date": visit_date + timedelta(days=i),
                        "PatientID": patient_id,
                        "Visit": "+",
                        "Study": study,
                        "Payment": 0
                    })

        visits_df = pd.DataFrame(visit_records)

        # =========================
        # Calendar setup
        # =========================
        min_date = visits_df["Date"].min() - timedelta(days=1)
        max_date = visits_df["Date"].max() + timedelta(days=1)
        calendar_dates = pd.date_range(start=min_date, end=max_date)

        calendar_df = pd.DataFrame({"Date": calendar_dates})
        calendar_df["Day"] = calendar_df["Date"].dt.day_name()

        patients_df["ColumnID"] = patients_df["Study"] + "_" + patients_df["PatientID"]
        for col_id in patients_df["ColumnID"]:
            calendar_df[col_id] = ""

        for study in trials_df["Study"].unique():
            calendar_df[f"{study} Income"] = 0.0

        calendar_df["Daily Total"] = 0.0

        # =========================
        # Fill calendar
        # =========================
        for i, row in calendar_df.iterrows():
            date = row["Date"]
            visits_today = visits_df[visits_df["Date"] == date]
            daily_total = 0.0

            for _, visit in visits_today.iterrows():
                study = str(visit["Study"])
                pid = str(visit["PatientID"])
                col_id = f"{study}_{pid}"
                visit_info = visit["Visit"]
                payment = float(visit["Payment"]) if pd.notna(visit["Payment"]) else 0.0

                # Update patient col
                if col_id in calendar_df.columns:
                    if calendar_df.at[i, col_id] == "":
                        calendar_df.at[i, col_id] = visit_info
                    else:
                        calendar_df.at[i, col_id] += f", {visit_info}"

                # Income only for actual visits
                if visit_info not in ("-", "+"):
                    income_col = f"{study} Income"
                    if income_col in calendar_df.columns:
                        calendar_df.at[i, income_col] += payment
                        daily_total += payment

            calendar_df.at[i, "Daily Total"] = daily_total

        # =========================
        # Totals
        # =========================
        calendar_df["Date"] = pd.to_datetime(calendar_df["Date"])
        calendar_df["Daily Total"] = pd.to_numeric(calendar_df["Daily Total"], errors="coerce").fillna(0.0)

        # Monthly totals
        calendar_df["MonthPeriod"] = calendar_df["Date"].dt.to_period("M")
        monthly_totals = calendar_df.groupby("MonthPeriod")["Daily Total"].sum()
        calendar_df["IsMonthEnd"] = calendar_df["Date"] == calendar_df["Date"] + pd.offsets.MonthEnd(0)
        calendar_df["Monthly Total"] = calendar_df.apply(
            lambda r: monthly_totals.get(r["MonthPeriod"], 0.0) if r["IsMonthEnd"] else pd.NA, axis=1
        )

        # Fiscal year totals
        calendar_df["FYStart"] = calendar_df["Date"].apply(lambda d: d.year if d.month >= 4 else d.year - 1)
        fy_totals = calendar_df.groupby("FYStart")["Daily Total"].sum()
        calendar_df["IsFYE"] = (calendar_df["Date"].dt.month == 3) & (calendar_df["Date"].dt.day == 31)
        calendar_df["FY Total"] = calendar_df.apply(
            lambda r: fy_totals.get(r["FYStart"], 0.0) if r["IsFYE"] else pd.NA, axis=1
        )

        calendar_df["Monthly Total"] = pd.to_numeric(calendar_df["Monthly Total"], errors="coerce")
        calendar_df["FY Total"] = pd.to_numeric(calendar_df["FY Total"], errors="coerce")

        # =========================
        # Display
        # =========================
        st.subheader("🗓️ Generated Visit Calendar")
        total_payments = visits_df[visits_df["Payment"] > 0]["Payment"].sum()
        st.write(f"📊 Calendar spans {min_date:%Y-%m-%d} → {max_date:%Y-%m-%d}")
        st.write(f"📈 Total rows: {len(calendar_df)}")
        st.write(f"💰 Total payments in visits: £{total_payments:,.2f}")
        st.write(f"🏥 Paid visits: {len(visits_df[visits_df['Payment'] > 0])}")

        paid_visits = visits_df[visits_df["Payment"] > 0].head().copy()
        if not paid_visits.empty:
            paid_visits["Payment"] = paid_visits["Payment"].apply(lambda x: f"£{x:,.2f}")
            st.write("Sample of paid visits:")
            st.dataframe(paid_visits)

        # Prepare display
        display_df = calendar_df.copy()
        display_df["Date"] = display_df["Date"].dt.strftime("%Y-%m-%d")
        display_df = display_df.drop(columns=["MonthPeriod", "IsMonthEnd", "FYStart", "IsFYE"])

        def fmt_currency(v):
            if pd.isna(v) or v == 0:
                return ""
            return f"£{v:,.2f}"

        format_funcs = {}
        financial_cols = ["Daily Total", "Monthly Total", "FY Total"] + [c for c in display_df.columns if "Income" in c]
        for col in financial_cols:
            if col in ["Monthly Total", "FY Total"]:
                format_funcs[col] = fmt_currency
            else:
                format_funcs[col] = lambda v: f"£{v:,.2f}" if not pd.isna(v) else "£0.00"

        try:
            styled_df = display_df.style.format(format_funcs).apply(highlight_weekends, axis=1).apply(highlight_special_days, axis=1)
            import streamlit.components.v1 as components
            html_table = f"""
            <div style='max-height: 700px; overflow: auto; border: 1px solid #ddd;'>
                {styled_df.to_html(escape=False)}
            </div>
            """
            components.html(html_table, height=720, scrolling=True)
        except Exception as e:
            st.warning(f"Advanced styling failed ({e}), showing basic table")
            st.dataframe(display_df, use_container_width=True)

        # =========================
        # Downloads
        # =========================
        st.subheader("📥 Download Options")
        col1, col2, col3 = st.columns(3)

        # CSV
        with col1:
            st.download_button(
                "📄 Download Full CSV",
                data=calendar_df.to_csv(index=False),
                file_name="VisitCalendar_Full.csv",
                mime="text/csv"
            )

        # Excel (finances)
        def excel_col_letter(idx):
            """Convert 1-based index to Excel column letter (handles AA, AB etc)."""
            result = ""
            while idx:
                idx, rem = divmod(idx - 1, 26)
                result = chr(65 + rem) + result
            return result

        with col2:
            if excel_available:
                try:
                    excel_df = display_df.copy()
                    for col in financial_cols:
                        if col in excel_df.columns:
                            if col in ["Monthly Total", "FY Total"]:
                                excel_df[col] = excel_df[col].apply(lambda v: f"£{v:,.2f}" if pd.notna(v) and v != 0 else "")
                            else:
                                excel_df[col] = excel_df[col].apply(lambda v: f"£{v:,.2f}" if pd.notna(v) else "£0.00")

                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        excel_df.to_excel(writer, index=False, sheet_name="VisitCalendar")
                        ws = writer.sheets["VisitCalendar"]
                        ws.column_dimensions['A'].width = 12
                        ws.column_dimensions['B'].width = 10
                        for idx, col in enumerate(excel_df.columns, 1):
                            col_letter = excel_col_letter(idx)
                            if any(k in col for k in ["Income", "Total"]):
                                ws.column_dimensions[col_letter].width = 15
                            elif col not in ["Date", "Day"]:
                                ws.column_dimensions[col_letter].width = 10

                    st.download_button(
                        "💰 Excel with Finances",
                        data=output.getvalue(),
                        file_name="VisitCalendar_WithFinances.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                except Exception as e:
                    st.warning(f"Excel export failed: {str(e)}")
            else:
                st.warning("⚠️ Excel not available")

        # Excel (schedule only)
        with col3:
            if excel_available:
                try:
                    schedule_df = display_df.drop(columns=[c for c in financial_cols if c in display_df.columns])
                    output_schedule = io.BytesIO()
                    with pd.ExcelWriter(output_schedule, engine='openpyxl') as writer:
                        schedule_df.to_excel(writer, index=False, sheet_name="VisitSchedule")
                        ws = writer.sheets["VisitSchedule"]
                        ws.column_dimensions['A'].width = 12
                        ws.column_dimensions['B'].width = 10
                        for idx, col in enumerate(schedule_df.columns, 1):
                            col_letter = excel_col_letter(idx)
                            if col not in ["Date", "Day"]:
                                ws.column_dimensions[col_letter].width = 14
                    st.download_button(
                        "📅 Excel Schedule Only",
                        data=output_schedule.getvalue(),
                        file_name="VisitSchedule_Only.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                except Exception as e:
                    st.warning(f"Schedule export failed: {str(e)}")
            else:
                st.warning("⚠️ Excel not available")

        # =========================
        # Summary metrics
        # =========================
        st.subheader("📊 Summary Statistics")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Total Patients", len(patients_df))
        with c2:
            st.metric("Total Visits", len(visits_df[visits_df["Visit"].str.contains("Visit")]))
        with c3:
            st.metric("Total Income", f"£{calendar_df['Daily Total'].sum():,.2f}")

    except Exception as e:
        st.error(f"Error processing files: {str(e)}")
        st.subheader("Expected File Format:")
        col1, col2 = st.columns(2)
        with col1:
            st.write("**Patients File:**")
            st.write("- PatientID, Study, StartDate")
        with col2:
            st.write("**Trials File:**")
            st.write("- Study, Day, VisitNo, ToleranceBefore, ToleranceAfter, Payment/Income")

else:
    st.info("👆 Upload both CSV files to generate the calendar.")
    st.subheader("📋 Example File Formats")
    col1, col2 = st.columns(2)
    with col1:
        st.write("**Patients CSV:**")
        st.dataframe(pd.DataFrame({
            "PatientID": ["P001", "P002", "P003"],
            "Study": ["STUDY-A", "STUDY-B", "STUDY-A"],
            "StartDate": ["2025-01-15", "2025-01-20", "2025-02-01"]
        }))
    with col2:
        st.write("**Trials CSV:**")
        st.dataframe(pd.DataFrame({
            "Study": ["STUDY-A", "STUDY-A", "STUDY-B"],
            "Day": [0, 7, 0],
            "VisitNo": [1, 2, 1],
            "ToleranceBefore": [2, 1, 0],
            "ToleranceAfter": [2, 1, 0],
            "Payment": [500.0, 300.0, 750.0]
        }))
