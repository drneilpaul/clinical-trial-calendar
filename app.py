import streamlit as st
import pandas as pd
from datetime import timedelta
import io

st.set_page_config(page_title="Clinical Trial Calendar Generator", layout="wide")

def highlight_special_days(row):
    """Return list of CSS styles for a row highlighting end-of-month and financial year end."""
    try:
        date_obj = pd.to_datetime(row.get("Date"))
        if pd.isna(date_obj):
            return [''] * len(row)
        
        # Check if it's FY end (31 March)
        if date_obj.month == 3 and date_obj.day == 31:
            return ['background-color: #1e40af; color: white; font-weight: bold'] * len(row)  # Dark blue for FY end
        
        # Check if it's month end
        if date_obj == date_obj + pd.offsets.MonthEnd(0):  # More reliable month end check
            return ['background-color: #3b82f6; color: white; font-weight: bold'] * len(row)  # Blue for month end
            
    except Exception:
        pass
    return [''] * len(row)

def highlight_weekends(row):
    """Return list of CSS styles for weekends (Saturday/Sunday)."""
    try:
        date_obj = pd.to_datetime(row.get("Date"))
        if pd.isna(date_obj):
            return [''] * len(row)
        if date_obj.weekday() in (5, 6):  # Saturday=5, Sunday=6
            return ['background-color: #f3f4f6'] * len(row)  # Light gray
    except Exception:
        pass
    return [''] * len(row)

st.title("🏥 Clinical Trial Calendar Generator")
st.caption("v1.4.1 | Version: 2025-09-15 | Fixed dynamic date range")

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

        # Convert to DataFrame for easier date calculations
        visits_df = pd.DataFrame(visit_records)
        
        # FIXED: Calculate date range based on actual visit dates, not hardcoded 60 days
        min_date = visits_df["Date"].min()
        max_date = visits_df["Date"].max()
        
        # Add a small buffer to ensure we capture all dates
        min_date = min_date - timedelta(days=1)
        max_date = max_date + timedelta(days=1)
        
        # Create date range for calendar
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

            calendar_df.at[i, "Daily Total"] = daily_total

        # Calculate period totals - only show on last day of period
        calendar_df["Date"] = pd.to_datetime(calendar_df["Date"])
        calendar_df["Daily Total"] = pd.to_numeric(calendar_df["Daily Total"], errors="coerce").fillna(0.0)

        # Monthly totals: show only on month end
        calendar_df["MonthPeriod"] = calendar_df["Date"].dt.to_period("M")
        monthly_totals = calendar_df.groupby("MonthPeriod")["Daily Total"].sum()
        calendar_df["IsMonthEnd"] = calendar_df["Date"] == calendar_df["Date"] + pd.offsets.MonthEnd(0)
        calendar_df["Monthly Total"] = calendar_df.apply(
            lambda r: monthly_totals.get(r["MonthPeriod"], 0.0) if r["IsMonthEnd"] else pd.NA,
            axis=1
        )

        # Fiscal year totals: show only on FY end (31 March)
        calendar_df["FYStart"] = calendar_df["Date"].apply(lambda d: d.year if d.month >= 4 else d.year - 1)
        fy_totals = calendar_df.groupby("FYStart")["Daily Total"].sum()
        calendar_df["IsFYE"] = (calendar_df["Date"].dt.month == 3) & (calendar_df["Date"].dt.day == 31)
        calendar_df["FY Total"] = calendar_df.apply(
            lambda r: fy_totals.get(r["FYStart"], 0.0) if r["IsFYE"] else pd.NA,
            axis=1
        )

        # Convert totals to numeric
        calendar_df["Monthly Total"] = pd.to_numeric(calendar_df["Monthly Total"], errors="coerce")
        calendar_df["FY Total"] = pd.to_numeric(calendar_df["FY Total"], errors="coerce")

        # Display the calendar
        st.subheader("🗓️ Generated Visit Calendar")
        
        # Debug information with date range
        total_payments = visits_df[visits_df["Payment"] > 0]["Payment"].sum()
        st.write(f"📊 Calendar spans from {min_date.strftime('%Y-%m-%d')} to {max_date.strftime('%Y-%m-%d')}")
        st.write(f"📈 Total calendar rows: {len(calendar_df)}")
        st.write(f"💰 Total payments in visit records: £{total_payments:,.2f}")
        st.write(f"🏥 Number of paid visits: {len(visits_df[visits_df['Payment'] > 0])}")
        
        # Show sample of paid visits
        paid_visits = visits_df[visits_df["Payment"] > 0].head().copy()
        if not paid_visits.empty:
            st.write("Sample of paid visits:")
            paid_visits["Payment"] = paid_visits["Payment"].apply(lambda x: f"£{x:,.2f}")
            st.dataframe(paid_visits)
        
        # Prepare display dataframe
        display_df = calendar_df.copy()
        display_df["Date_str"] = display_df["Date"].dt.strftime("%Y-%m-%d")
        display_df["Date"] = display_df["Date_str"]
        display_df = display_df.drop(columns=["Date_str"])

        # Remove helper columns
        helper_cols = ["MonthPeriod", "IsMonthEnd", "FYStart", "IsFYE"]
        display_df = display_df.drop(columns=[col for col in helper_cols if col in display_df.columns])

        # Currency formatter function
        def fmt_currency(v):
            if pd.isna(v) or v == 0:
                return ""
            return f"£{v:,.2f}"

        # Format financial columns
        format_funcs = {}
        financial_cols = ["Daily Total", "Monthly Total", "FY Total"] + [col for col in display_df.columns if "Income" in col]
        
        for col in financial_cols:
            if col in display_df.columns:
                if col in ["Monthly Total", "FY Total"]:
                    format_funcs[col] = fmt_currency  # Shows blank for zeros/NaN
                else:
                    format_funcs[col] = lambda v: f"£{v:,.2f}" if not pd.isna(v) else "£0.00"

        # Create styled dataframe
        try:
            styled_df = display_df.style.format(format_funcs).apply(highlight_weekends, axis=1).apply(highlight_special_days, axis=1)
            
            # Try HTML rendering for better styling
            import streamlit.components.v1 as components
            html_table = f"""
            <div style='max-height: 700px; overflow: auto; border: 1px solid #ddd;'>
                {styled_df.to_html(escape=False)}
            </div>
            """
            components.html(html_table, height=720, scrolling=True)
            
        except Exception as e:
            # Fallback to regular dataframe
            st.warning(f"Advanced styling failed ({e}), showing basic table:")
            st.dataframe(display_df, use_container_width=True)

        # Download options
        st.subheader("📥 Download Options")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            csv_data = calendar_df.to_csv(index=False)
            st.download_button(
                label="📄 Download Full CSV",
                data=csv_data,
                file_name="VisitCalendar_Full.csv",
                mime="text/csv"
            )
        
        with col2:
            if excel_available:
                try:
                    # Full Excel with financial data
                    excel_df = display_df.copy()
                    
                    # Format financial columns for Excel
                    financial_cols = ["Daily Total", "Monthly Total", "FY Total"] + [col for col in excel_df.columns if "Income" in col]
                    
                    for col in financial_cols:
                        if col in excel_df.columns:
                            if col in ["Monthly Total", "FY Total"]:
                                excel_df[col] = excel_df[col].apply(lambda v: f"£{v:,.2f}" if pd.notna(v) and v != 0 else "")
                            else:
                                excel_df[col] = excel_df[col].apply(lambda v: f"£{v:,.2f}" if pd.notna(v) else "£0.00")
                    
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        excel_df.to_excel(writer, index=False, sheet_name="VisitCalendar")
                        
                        worksheet = writer.sheets["VisitCalendar"]
                        worksheet.column_dimensions['A'].width = 12
                        worksheet.column_dimensions['B'].width = 10
                        
                        for idx, col in enumerate(excel_df.columns, 1):
                            if any(keyword in col for keyword in ["Income", "Total"]):
                                worksheet.column_dimensions[chr(64 + idx)].width = 15
                            elif col not in ["Date", "Day"]:
                                worksheet.column_dimensions[chr(64 + idx)].width = 10
                    
                    st.download_button(
                        label="💰 Excel with Finances",
                        data=output.getvalue(),
                        file_name="VisitCalendar_WithFinances.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                except Exception as e:
                    st.warning(f"Excel export failed: {str(e)}")
            else:
                st.warning("⚠️ Excel not available")
        
        with col3:
            if excel_available:
                try:
                    # Schedule-only Excel (no financial data)
                    schedule_df = display_df.copy()
                    
                    # Remove all financial columns
                    financial_cols = ["Daily Total", "Monthly Total", "FY Total"] + [col for col in schedule_df.columns if "Income" in col]
                    schedule_df = schedule_df.drop(columns=[col for col in financial_cols if col in schedule_df.columns])
                    
                    output_schedule = io.BytesIO()
                    with pd.ExcelWriter(output_schedule, engine='openpyxl') as writer:
                        schedule_df.to_excel(writer, index=False, sheet_name="VisitSchedule")
                        
                        worksheet = writer.sheets["VisitSchedule"]
                        worksheet.column_dimensions['A'].width = 12  # Date
                        worksheet.column_dimensions['B'].width = 10  # Day
                        
                        # Set patient columns width
                        for idx, col in enumerate(schedule_df.columns, 1):
                            if col not in ["Date", "Day"] and ":" in col:  # Patient columns with study:id format
                                worksheet.column_dimensions[chr(64 + idx)].width = 14
                            elif col not in ["Date", "Day"]:
                                worksheet.column_dimensions[chr(64 + idx)].width = 12
                        
                        # Add Excel formatting for highlighting
                        from openpyxl.styles import PatternFill, Font
                        
                        # Define fill styles
                        weekend_fill = PatternFill(start_color="F3F4F6", end_color="F3F4F6", fill_type="solid")
                        month_end_fill = PatternFill(start_color="3B82F6", end_color="3B82F6", fill_type="solid")
                        fy_end_fill = PatternFill(start_color="1E40AF", end_color="1E40AF", fill_type="solid")
                        white_font = Font(color="FFFFFF", bold=True)
                        
                        # Apply formatting to data rows (skip header)
                        for row_idx, (_, row_data) in enumerate(schedule_df.iterrows(), 2):  # Start from row 2 (after header)
                            try:
                                date_str = row_data["Date"]
                                date_obj = pd.to_datetime(date_str)
                                
                                # Check if it's FY end (31 March) - highest priority
                                if date_obj.month == 3 and date_obj.day == 31:
                                    for col_idx in range(1, len(schedule_df.columns) + 1):
                                        cell = worksheet.cell(row=row_idx, column=col_idx)
                                        cell.fill = fy_end_fill
                                        cell.font = white_font
                                
                                # Check if it's month end
                                elif date_obj == date_obj + pd.offsets.MonthEnd(0):
                                    for col_idx in range(1, len(schedule_df.columns) + 1):
                                        cell = worksheet.cell(row=row_idx, column=col_idx)
                                        cell.fill = month_end_fill
                                        cell.font = white_font
                                
                                # Check if it's weekend
                                elif date_obj.weekday() in (5, 6):  # Saturday=5, Sunday=6
                                    for col_idx in range(1, len(schedule_df.columns) + 1):
                                        cell = worksheet.cell(row=row_idx, column=col_idx)
                                        cell.fill = weekend_fill
                                        
                            except Exception:
                                continue  # Skip rows with invalid dates
                    
                    st.download_button(
                        label="📅 Excel Schedule Only",
                        data=output_schedule.getvalue(),
                        file_name="VisitSchedule_Only.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                except Exception as e:
                    st.warning(f"Schedule export failed: {str(e)}")
            else:
                st.warning("⚠️ Excel not available")

        # Summary statistics with correct currency
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
        st.error(f"Error processing files: {str(e)}")
        st.error("Please check your CSV file formats and column names.")
        
        # Show expected formats...
        st.subheader("Expected CSV Format:")
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**Patients CSV:**")
            st.write("- PatientID, Study, StartDate")
            
        with col2:
            st.write("**Trials CSV:**")
            st.write("- Study, Day, VisitNo, ToleranceBefore, ToleranceAfter, Payment/Income")

else:
    st.info("👆 Please upload both CSV files to generate the calendar.")
    
    # Example formats
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
