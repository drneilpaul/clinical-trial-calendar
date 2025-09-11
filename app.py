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
    # Check if openpyxl is available
    try:
        import openpyxl
        excel_available = True
    except ImportError:
        excel_available = False
        
    try:
        # Read CSV files
        patients_df = pd.read_csv(patients_file, dayfirst=True)
        trials_df = pd.read_csv(trials_file)
        
        # Debug: Show column names
        st.write("**Debug - Trials CSV columns:**", list(trials_df.columns))
        st.write("**Debug - Patients CSV columns:**", list(patients_df.columns))
        
        # Clean column names (remove extra spaces)
        trials_df.columns = trials_df.columns.str.strip()
        patients_df.columns = patients_df.columns.str.strip()
        
        # Map common alternative column names
        column_mapping = {
            'Income': 'Payment',
            'Tolerance Before': 'ToleranceBefore',
            'Tolerance After': 'ToleranceAfter',
            'Visit No': 'VisitNo',
            'VisitNumber': 'VisitNo'
        }
        
        # Apply column mapping
        trials_df = trials_df.rename(columns=column_mapping)
        
        # Show what columns we have after mapping
        st.write("**Debug - After column mapping:**", list(trials_df.columns))
        
        # Convert StartDate to datetime
        patients_df["StartDate"] = pd.to_datetime(patients_df["StartDate"], dayfirst=True)

        # Generate visit records
        visit_records = []
        for _, patient in patients_df.iterrows():
            patient_id = patient["PatientID"]
            study = patient["Study"]
            start_date = patient["StartDate"]

            # Get visits for this study
            study_visits = trials_df[trials_df["Study"] == study]
            
            for _, visit in study_visits.iterrows():
                visit_day = int(visit["Day"])
                visit_date = start_date + timedelta(days=visit_day)
                visit_no = visit["VisitNo"]
                
                # Handle tolerance values (ensure they're numeric)
                tol_before = int(visit.get("ToleranceBefore", 0)) if pd.notna(visit.get("ToleranceBefore", 0)) else 0
                tol_after = int(visit.get("ToleranceAfter", 0)) if pd.notna(visit.get("ToleranceAfter", 0)) else 0
                payment = float(visit.get("Payment", 0)) if pd.notna(visit.get("Payment", 0)) else 0.0

                # Main visit
                visit_records.append({
                    "Date": visit_date,
                    "PatientID": patient_id,
                    "Visit": f"Visit {visit_no}",
                    "Study": study,
                    "Payment": payment
                })

                # Tolerance days before
                for i in range(1, tol_before + 1):
                    tol_date = visit_date - timedelta(days=i)
                    visit_records.append({
                        "Date": tol_date,
                        "PatientID": patient_id,
                        "Visit": "-",
                        "Study": study,
                        "Payment": 0
                    })

                # Tolerance days after
                for i in range(1, tol_after + 1):
                    tol_date = visit_date + timedelta(days=i)
                    visit_records.append({
                        "Date": tol_date,
                        "PatientID": patient_id,
                        "Visit": "+",
                        "Study": study,
                        "Payment": 0
                    })

        # Create date range for calendar
        min_date = patients_df["StartDate"].min()
        max_date = patients_df["StartDate"].max() + timedelta(days=60)
        calendar_dates = pd.date_range(start=min_date, end=max_date)

        # Initialize calendar dataframe
        calendar_df = pd.DataFrame({"Date": calendar_dates})
        calendar_df["Day"] = calendar_df["Date"].dt.day_name()

        # Add patient columns
        for pid in patients_df["PatientID"]:
            calendar_df[str(pid)] = ""

        # Add study income columns
        for study in trials_df["Study"].unique():
            calendar_df[f"{study} Income"] = 0.0

        calendar_df["Daily Total"] = 0.0
        calendar_df["Monthly Total"] = 0.0
        calendar_df["FY Total"] = 0.0

        # Convert visit records to DataFrame for easier processing
        visits_df = pd.DataFrame(visit_records)
        
        # Process each date
        for i, row in calendar_df.iterrows():
            date = row["Date"]
            
            # Get visits for this date
            visits_today = visits_df[visits_df["Date"] == date]
            daily_total = 0.0
            
            for _, visit in visits_today.iterrows():
                pid = str(visit["PatientID"])
                visit_info = visit["Visit"]
                payment = float(visit["Payment"]) if pd.notna(visit["Payment"]) else 0.0
                
                # Update patient column
                if calendar_df.at[i, pid] == "":
                    calendar_df.at[i, pid] = visit_info
                else:
                    calendar_df.at[i, pid] += f", {visit_info}"
                
                # Update study income (only for actual visits, not tolerance days)
                if visit_info != "-" and visit_info != "+":
                    income_col = f"{visit['Study']} Income"
                    if income_col in calendar_df.columns:
                        calendar_df.at[i, income_col] += payment
                        daily_total += payment
                        
                        # Debug info
                        if payment > 0:
                            print(f"Added payment: {payment} for {visit_info} on {date}")

            calendar_df.at[i, "Daily Total"] = daily_total

        # Calculate monthly and FY totals
        calendar_df["Month"] = calendar_df["Date"].dt.to_period("M")
        calendar_df["FY"] = calendar_df["Date"].apply(
            lambda x: x.year if x.month >= 4 else x.year - 1
        )

        # Calculate cumulative totals
        monthly_totals = {}
        fy_totals = {}

        for i, row in calendar_df.iterrows():
            month = row["Month"]
            fy = row["FY"]
            daily_total = row["Daily Total"]
            
            # Update monthly total
            if month not in monthly_totals:
                monthly_totals[month] = 0.0
            monthly_totals[month] += daily_total
            calendar_df.at[i, "Monthly Total"] = monthly_totals[month]
            
            # Update FY total
            if fy not in fy_totals:
                fy_totals[fy] = 0.0
            fy_totals[fy] += daily_total
            calendar_df.at[i, "FY Total"] = fy_totals[fy]

        # Remove helper columns
        calendar_df = calendar_df.drop(columns=["Month", "FY"])

        # Display the calendar
        st.subheader("🗓️ Generated Visit Calendar")
        
        # Debug information
        total_payments = visits_df[visits_df["Payment"] > 0]["Payment"].sum()
        st.write(f"Debug: Total payments in visit records: ${total_payments:,.2f}")
        st.write(f"Debug: Number of paid visits: {len(visits_df[visits_df['Payment'] > 0])}")
        
        # Show a sample of visit records with payments
        paid_visits = visits_df[visits_df["Payment"] > 0].head()
        if not paid_visits.empty:
            st.write("Sample of paid visits:")
            st.dataframe(paid_visits)
        
        # Format the dataframe for better display
        display_df = calendar_df.copy()
        display_df["Date"] = display_df["Date"].dt.strftime("%Y-%m-%d")
        
        # Round financial columns to 2 decimal places
        financial_cols = [col for col in display_df.columns if "Income" in col or "Total" in col]
        for col in financial_cols:
            display_df[col] = display_df[col].round(2)
        
        st.dataframe(display_df, use_container_width=True)

        # Provide download options
        col1, col2 = st.columns(2)
        
        with col1:
            # CSV download (always available)
            csv_data = calendar_df.to_csv(index=False)
            st.download_button(
                label="📥 Download Calendar CSV",
                data=csv_data,
                file_name="VisitCalendar.csv",
                mime="text/csv"
            )
        
        with col2:
            # Excel download (only if openpyxl is available)
            if excel_available:
                try:
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        calendar_df.to_excel(writer, index=False, sheet_name="VisitCalendar")
                    
                    st.download_button(
                        label="📥 Download Calendar Excel",
                        data=output.getvalue(),
                        file_name="VisitCalendar.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                except Exception as e:
                    st.warning(f"Excel export failed: {str(e)}")
                    st.info("CSV download is still available above.")
            else:
                st.warning("⚠️ Excel download not available. Install openpyxl to enable Excel export.")
                st.code("pip install openpyxl", language="bash")

        # Display summary statistics
        st.subheader("📊 Summary Statistics")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            total_patients = len(patients_df)
            st.metric("Total Patients", total_patients)
        
        with col2:
            total_visits = len(visits_df[visits_df["Visit"].str.contains("Visit")])
            st.metric("Total Visits", total_visits)
        
        with col3:
            total_income = calendar_df["Daily Total"].sum()
            st.metric("Total Income", f"${total_income:,.2f}")

    except Exception as e:
        st.error(f"Error processing files: {str(e)}")
        st.error("Please check that your CSV files have the correct format and column names.")
        
        st.subheader("Expected CSV Format:")
        
        col1, col2 = st.columns(2)
        with col1:
            st.write("**Patients CSV should contain:**")
            st.write("- PatientID")
            st.write("- Study") 
            st.write("- StartDate")
            
        with col2:
            st.write("**Trials CSV should contain:**")
            st.write("- Study")
            st.write("- Day")
            st.write("- VisitNo")
            st.write("- ToleranceBefore (optional)")
            st.write("- ToleranceAfter (optional)")
            st.write("- Payment/Income (optional)")

else:
    st.info("👆 Please upload both Patients and Trials CSV files to generate the calendar.")
    
    # Show example of expected file formats
    st.subheader("📋 Expected File Formats")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**Example Patients CSV:**")
        example_patients = pd.DataFrame({
            "PatientID": ["P001", "P002", "P003"],
            "Study": ["STUDY-A", "STUDY-B", "STUDY-A"],
            "StartDate": ["2025-01-15", "2025-01-20", "2025-02-01"]
        })
        st.dataframe(example_patients)
    
    with col2:
        st.write("**Example Trials CSV:**")
        example_trials = pd.DataFrame({
            "Study": ["STUDY-A", "STUDY-A", "STUDY-B"],
            "Day": [0, 7, 0],
            "VisitNo": [1, 2, 1],
            "ToleranceBefore": [2, 1, 0],
            "ToleranceAfter": [2, 1, 0],
            "Payment": [500.0, 300.0, 750.0]
        })
        st.dataframe(example_trials)
