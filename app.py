import streamlit as st
import pandas as pd
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
st.caption("v1.5 | Updated: Excel support, safer error handling, no matplotlib")

st.sidebar.header("📁 Upload Data Files")
patients_file = st.sidebar.file_uploader("Upload Patients File", type=['csv', 'xls', 'xlsx'], key="patients")
trials_file = st.sidebar.file_uploader("Upload Trials File", type=['csv', 'xls', 'xlsx'], key="trials")


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

        # Normalise columns
        column_mapping = {
            'Income': 'Payment',
            'Tolerance Before': 'ToleranceBefore',
            'Tolerance After': 'ToleranceAfter',
            'Visit No': 'VisitNo',
            'VisitNumber': 'VisitNo'
        }
        trials_df = trials_df.rename(columns=column_mapping)

        # Types
        patients_df["PatientID"] = patients_df["PatientID"].astype(str)
        patients_df["Study"] = patients_df["Study"].astype(str)
        patients_df["StartDate"] = pd.to_datetime(patients_df["StartDate"], dayfirst=True, errors="coerce")
        trials_df["Study"] = trials_df["Study"].astype(str)

        # Build visit records
        visit_records = []
        for _, patient in patients_df.iterrows():
            patient_id = patient["PatientID"]
            study = patient["Study"]
            start_date = patient["StartDate"]

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

        if visits_df.empty:
            st.error("❌ No visits generated. Check that Patient `Study` matches Trial `Study` values.")
            st.stop()

        # Build calendar range
        min_date = visits_df["Date"].min() - timedelta(days=1)
        max_date = visits_df["Date"].max() + timedelta(days=1)
        calendar_dates = pd.date_range(start=min_date, end=max_date)
        calendar_df = pd.DataFrame({"Date": calendar_dates})
        calendar_df["Day"] = calendar_df["Date"].dt.day_name()

        # Patient columns
        patients_df["ColumnID"] = patients_df["Study"] + "_" + patients_df["PatientID"]
        for col_id in patients_df["ColumnID"]:
            calendar_df[col_id] = ""

        # Study income
        for study in trials_df["Study"].unique():
            calendar_df[f"{study} Income"] = 0.0
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

        # Display table
        st.subheader("🗓️ Generated Visit Calendar")
        display_df = calendar_df.drop(columns=["MonthPeriod", "IsMonthEnd", "FYStart", "IsFYE"])
        display_df["Date"] = display_df["Date"].dt.strftime("%Y-%m-%d")

        def fmt_currency(v):
            if pd.isna(v) or v == 0:
                return ""
            return f"£{v:,.2f}"

        financial_cols = ["Daily Total", "Monthly Total", "FY Total"] + [c for c in display_df.columns if "Income" in c]
        format_funcs = {col: fmt_currency for col in financial_cols if col in display_df.columns}

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
            st.dataframe(display_df, use_container_width=True)

        # Chart
        st.subheader("📈 Daily Income Chart")
        st.line_chart(calendar_df.set_index("Date")["Daily Total"])

        # Downloads
        st.subheader("📥 Download Options")
        csv_data = calendar_df.to_csv(index=False)
        st.download_button("📄 Download Full CSV", csv_data, "VisitCalendar_Full.csv", "text/csv")

        try:
            import openpyxl
            excel_available = True
        except ImportError:
            excel_available = False

        if excel_available:
            # Excel with finances
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                display_df.to_excel(writer, index=False, sheet_name="VisitCalendar")
            st.download_button("💰 Excel with Finances", output.getvalue(),
                               "VisitCalendar_WithFinances.xlsx",
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

            # Excel schedule only
            schedule_df = display_df.drop(columns=[c for c in financial_cols if c in display_df.columns])
            output2 = io.BytesIO()
            with pd.ExcelWriter(output2, engine='openpyxl') as writer:
                schedule_df.to_excel(writer, index=False, sheet_name="VisitSchedule")
            st.download_button("📅 Excel Schedule Only", output2.getvalue(),
                               "VisitSchedule_Only.xlsx",
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        # Summary stats
        st.subheader("📊 Summary Statistics")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Patients", len(patients_df))
        with col2:
            total_visits = len(visits_df[visits_df["Visit"].str.contains("Visit")])
            st.metric("Total Visits", total_visits)
        with col3:
            total_income = calendar_df["Daily Total"].sum()
            st.metric("Total Income", f"£{total_income:,.2f}")

    except Exception as e:
        st.error(f"❌ Error processing files: {e}")
else:
    st.info("👆 Please upload both Patients and Trials files (CSV or Excel).")
