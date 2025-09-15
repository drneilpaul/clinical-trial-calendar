import streamlit as st
import pandas as pd
import numpy as np
import calendar
from datetime import datetime
import matplotlib.pyplot as plt
from io import BytesIO
import openpyxl

st.set_page_config(page_title="Study Calendar & Income", layout="wide")

# --- Debug toggle ---
DEBUG_MODE = False

st.title("Study Calendar & Income Visualiser")

# --- File Uploaders ---
st.subheader("Upload Study Data")

visits_file = st.file_uploader("Upload Visits file (CSV or Excel)", type=["csv", "xlsx", "xls"], key="visits")
patients_file = st.file_uploader("Upload Patients file (CSV or Excel)", type=["csv", "xlsx", "xls"], key="patients")

# --- Load files ---
def load_uploaded_file(file):
    if file is None:
        return None
    if file.name.endswith(".csv"):
        return pd.read_csv(file)
    elif file.name.endswith((".xlsx", ".xls")):
        return pd.read_excel(file)
    return None

if visits_file and patients_file:
    visits_df = load_uploaded_file(visits_file)
    patients_df = load_uploaded_file(patients_file)

    if visits_df is None or patients_df is None:
        st.error("One of the uploaded files could not be read. Please upload CSV or Excel.")
    else:
        # --- Normalise columns ---
        visits_df = visits_df.rename(columns=lambda x: x.strip())
        patients_df = patients_df.rename(columns=lambda x: x.strip())

        # Convert dates
        for col in ["Date", "DOB"]:
            if col in visits_df.columns:
                visits_df[col] = pd.to_datetime(visits_df[col], errors="coerce")
            if col in patients_df.columns:
                patients_df[col] = pd.to_datetime(patients_df[col], errors="coerce")

        # --- Calendar range ---
        min_date = visits_df["Date"].min()
        max_date = visits_df["Date"].max()
        calendar_range = pd.date_range(min_date, max_date, freq="D")

        # --- Calendar dataframe ---
        calendar_df = pd.DataFrame({
            "Date": calendar_range,
            "Day": [calendar.day_name()[d.weekday()] for d in calendar_range]
        })

        # Add patient visit columns
        for _, row in patients_df.iterrows():
            col_id = f"{row['Study']}_{row['PatientID']}"
            calendar_df[col_id] = ""

        # Add study income columns
        for study in patients_df["Study"].unique():
            calendar_df[f"{study} Income"] = 0.0

        # Daily total column
        calendar_df["Daily Total"] = 0.0

        # --- Populate visits and income ---
        for i, row in calendar_df.iterrows():
            date = row["Date"]
            visits_today = visits_df[visits_df["Date"] == date]
            daily_total = 0.0

            for _, visit in visits_today.iterrows():
                study = str(visit["Study"])
                pid = str(visit["PatientID"])
                col_id = f"{study}_{pid}"
                visit_info = str(visit["Visit"])
                payment = float(visit["Payment"]) if pd.notna(visit["Payment"]) else 0.0

                # Update patient cell
                if col_id in calendar_df.columns:
                    if calendar_df.at[i, col_id] == "":
                        calendar_df.at[i, col_id] = visit_info
                    else:
                        calendar_df.at[i, col_id] += f", {visit_info}"

                # Update study income if real visit
                if visit_info not in ("-", "+"):
                    income_col = f"{study} Income"
                    if income_col in calendar_df.columns:
                        calendar_df.at[i, income_col] += payment
                        daily_total += payment

            calendar_df.at[i, "Daily Total"] = daily_total

        # --- Display calendar table ---
        st.subheader("Study Calendar Table")
        st.dataframe(calendar_df)

        # --- Income summary ---
        st.subheader("Income Summary")
        income_summary = calendar_df[[c for c in calendar_df.columns if "Income" in c or c == "Daily Total"]].sum().reset_index()
        income_summary.columns = ["Category", "Total Income"]
        st.dataframe(income_summary)

        # --- Chart ---
        st.subheader("Daily Income Chart")
        plt.figure(figsize=(12, 6))
        plt.plot(calendar_df["Date"], calendar_df["Daily Total"], marker="o", linestyle="-")
        plt.title("Daily Total Income")
        plt.xlabel("Date")
        plt.ylabel("Income (£)")
        plt.grid(True)
        st.pyplot(plt)

        # --- Export to Excel ---
        st.subheader("Download Results")
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            calendar_df.to_excel(writer, sheet_name="Calendar", index=False)
            income_summary.to_excel(writer, sheet_name="Summary", index=False)
            worksheet = writer.sheets["Calendar"]

            # Auto-adjust column widths
            for col in worksheet.columns:
                max_length = 0
                col_letter = openpyxl.utils.get_column_letter(col[0].column)
                for cell in col:
                    try:
                        if cell.value:
                            max_length = max(max_length, len(str(cell.value)))
                    except:
                        pass
                worksheet.column_dimensions[col_letter].width = max_length + 2

        st.download_button(
            label="Download Excel File",
            data=output.getvalue(),
            file_name="study_calendar.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
