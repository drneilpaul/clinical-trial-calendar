
import streamlit as st
import pandas as pd
from datetime import timedelta
import io

st.set_page_config(page_title="Clinical Trial Calendar Generator", layout="wide")
st.title("🏥 Clinical Trial Calendar Generator")
st.caption("v1.3.2 | Version: 2025-09-11")

st.sidebar.header("📁 Upload Data Files")
patients_file = st.sidebar.file_uploader("Upload Patients CSV", type=['csv'], key="patients")
trials_file = st.sidebar.file_uploader("Upload Trials CSV", type=['csv'], key="trials")

if patients_file and trials_file:
    patients_df = pd.read_csv(patients_file, dayfirst=True)
    trials_df = pd.read_csv(trials_file)
    patients_df["StartDate"] = pd.to_datetime(patients_df["StartDate"], dayfirst=True)

    visit_records = []
    for _, patient in patients_df.iterrows():
        patient_id = patient["PatientID"]
        study = patient["Study"]
        start_date = patient["StartDate"]

        for _, visit in trials_df[trials_df["Study"] == study].iterrows():
            visit_day = visit["Day"]
            visit_date = start_date + timedelta(days=visit_day)
            visit_no = visit["VisitNo"]
            tol_before = visit.get("ToleranceBefore", 0)
            tol_after = visit.get("ToleranceAfter", 0)
            payment = visit.get("Payment", 0)

            visit_records.append({
                "Date": visit_date,
                "PatientID": patient_id,
                "Visit": f"Visit {visit_no}",
                "Study": study,
                "Payment": payment
            })

            for i in range(1, int(tol_before) + 1):
                tol_date = visit_date - timedelta(days=i)
                visit_records.append({
                    "Date": tol_date,
                    "PatientID": patient_id,
                    "Visit": "-",
                    "Study": study,
                    "Payment": 0
                })

            for i in range(1, int(tol_after) + 1):
                tol_date = visit_date + timedelta(days=i)
                visit_records.append({
                    "Date": tol_date,
                    "PatientID": patient_id,
                    "Visit": "+",
                    "Study": study,
                    "Payment": 0
                })

    min_date = patients_df["StartDate"].min()
    max_date = patients_df["StartDate"].max() + timedelta(days=60)
    calendar_dates = pd.date_range(start=min_date, end=max_date)

    calendar_df = pd.DataFrame({"Date": calendar_dates})
    calendar_df["Day"] = calendar_df["Date"].dt.day_name()

    for pid in patients_df["PatientID"]:
        calendar_df[pid] = ""

    for study in trials_df["Study"].unique():
        calendar_df[f"{study} Income"] = 0.0

    calendar_df["Monthly Total"] = 0.0
    calendar_df["FY Total"] = 0.0

    fy_total = 0.0
    month_total = 0.0

    for i, row in calendar_df.iterrows():
        date = row["Date"]
        visits_today = [v for v in visit_records if v["Date"] == date]

        for visit in visits_today:
            pid = visit["PatientID"]
            calendar_df.at[i, pid] = visit["Visit"]
            income_col = f"{visit['Study']} Income"
            calendar_df.at[i, income_col] += visit["Payment"]
            month_total += visit["Payment"]

            if date >= pd.Timestamp(year=date.year, month=4, day=1) and date < pd.Timestamp(year=date.year + 1, month=4, day=1):
                fy_total += visit["Payment"]

        calendar_df.at[i, "Monthly Total"] = month_total
        calendar_df.at[i, "FY Total"] = fy_total

        if i + 1 < len(calendar_df):
            next_date = calendar_df.at[i + 1, "Date"]
            if next_date.month != date.month:
                month_total = 0.0

    st.subheader("🗓️ Generated Visit Calendar")
    st.dataframe(calendar_df, use_container_width=True)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        calendar_df.to_excel(writer, index=False, sheet_name="VisitCalendar")
    st.download_button(
        label="📥 Download Calendar Excel",
        data=output.getvalue(),
        file_name="VisitCalendar.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
else:
    st.info("👆 Please upload both Patients and Trials CSV files to generate the calendar.")

