import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import io
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Page config
st.set_page_config(
    page_title="Clinical Trial Calendar Generator",
    page_icon="🏥",
    layout="wide"
)

class TrialCalendarBuilder:
    """Build calendar for clinical trial visits with payment tracking."""
    
    def __init__(self, patients_df, trials_df):
        self.patients = patients_df
        self.trials = trials_df
        self.calendar_df = None
        
    def validate_data(self):
        """Validate input data structure."""
        required_patient_cols = ["PatientID", "Study", "StartDate"]
        required_trial_cols = ["Study", "VisitNo", "Day"]
        
        missing_patient_cols = set(required_patient_cols) - set(self.patients.columns)
        missing_trial_cols = set(required_trial_cols) - set(self.trials.columns)
        
        errors = []
        if missing_patient_cols:
            errors.append(f"Missing patient columns: {', '.join(missing_patient_cols)}")
        if missing_trial_cols:
            errors.append(f"Missing trial columns: {', '.join(missing_trial_cols)}")
            
        return errors
            
    def prepare_patients(self):
        """Build patient visit 1 dates from StartDate column."""
        self.patients["V1_Date"] = pd.to_datetime(self.patients["StartDate"], dayfirst=True, errors="coerce")
        
    def create_visit_record(self, patient_id, study, visit_date, visit_label, payment):
        """Create a single visit record."""
        return {
            "Date": visit_date,
            "PatientID": patient_id,
            "Study": study,
            "Visit": visit_label,
            "Payment": payment
        }
        
    def add_tolerance_visits(self, visit_records, base_date, patient_id, study, tol_before, tol_after):
        """Add tolerance window visits around main visit."""
        for offset in range(1, tol_before + 1):
            visit_records.append(self.create_visit_record(
                patient_id, study, base_date - timedelta(days=offset), "-", 0
            ))
        
        for offset in range(1, tol_after + 1):
            visit_records.append(self.create_visit_record(
                patient_id, study, base_date + timedelta(days=offset), "+", 0
            ))
    
    def build_visit_schedule(self):
        """Build complete visit schedule with tolerances."""
        visit_records = []
        
        for _, trial in self.trials.iterrows():
            study = trial["Study"]
            visit_no = trial["VisitNo"]
            visit_day = trial["Day"]
            tol_before = int(trial.get("ToleranceBefore", 0))
            tol_after = int(trial.get("ToleranceAfter", 0))
            payment = float(trial.get("Payment", 0))
            
            study_patients = self.patients[self.patients["Study"] == study]
            
            for _, patient in study_patients.iterrows():
                v1_date = patient["V1_Date"]
                patient_id = patient["PatientID"]
                visit_date = v1_date + timedelta(days=visit_day)
                
                # Main visit
                visit_records.append(self.create_visit_record(
                    patient_id, study, visit_date, f"Visit {visit_no}", payment
                ))
                
                # Add tolerance visits
                self.add_tolerance_visits(
                    visit_records, visit_date, patient_id, study, tol_before, tol_after
                )
        
        return visit_records
    
    def build_calendar(self):
        """Build calendar DataFrame with date info."""
        visit_records = self.build_visit_schedule()
        
        self.calendar_df = pd.DataFrame(visit_records)
        self.calendar_df["Date"] = pd.to_datetime(self.calendar_df["Date"])
        self.calendar_df["Day"] = self.calendar_df["Date"].dt.day_name()
        self.calendar_df["Month"] = self.calendar_df["Date"].dt.month
        self.calendar_df["Year"] = self.calendar_df["Date"].dt.year
        
    @staticmethod
    def fiscal_year(date):
        """Calculate fiscal year (April start)."""
        return date.year if date.month >= 4 else date.year - 1
    
    def calculate_financials(self):
        """Calculate daily income, monthly totals, and fiscal year running totals."""
        daily_income = self.calendar_df.groupby("Date")["Payment"].sum().reset_index()
        daily_income["Day"] = daily_income["Date"].dt.day_name()
        
        # Monthly totals
        daily_income["MonthEnd"] = daily_income["Date"].dt.is_month_end
        monthly_totals = daily_income.groupby([daily_income["Date"].dt.year, 
                                             daily_income["Date"].dt.month])["Payment"].sum()
        
        daily_income["MonthlyTotal"] = ""
        for idx, row in daily_income.iterrows():
            if row["MonthEnd"]:
                year_month = (row["Date"].year, row["Date"].month)
                daily_income.at[idx, "MonthlyTotal"] = monthly_totals[year_month]
        
        # Fiscal year running totals
        daily_income["FY"] = daily_income["Date"].apply(self.fiscal_year)
        daily_income["FYRunningTotal"] = daily_income.groupby("FY")["Payment"].cumsum()
        
        return daily_income
    
    def generate_output(self):
        """Generate final formatted output."""
        daily_income = self.calculate_financials()
        output = daily_income[["Date", "Day", "Payment", "MonthlyTotal", "FYRunningTotal"]].copy()
        output["Date"] = output["Date"].dt.strftime("%d/%m/%Y")
        return output

def convert_df_to_csv(df):
    """Convert DataFrame to CSV for download."""
    return df.to_csv(index=False).encode('utf-8')

# Main App
def main():
    st.title("🏥 Clinical Trial Calendar Generator")
st.caption("v1.3.2 | Version: 2025-09-11")
    st.markdown("Upload your patient and trial data to generate a comprehensive visit calendar with payment tracking.")
    
    # Sidebar for file uploads
    st.sidebar.header("📁 Upload Data Files")
    
    patients_file = st.sidebar.file_uploader("Upload Patients CSV", type=['csv'], key="patients")
    trials_file = st.sidebar.file_uploader("Upload Trials CSV", type=['csv'], key="trials")
    
    if patients_file is not None and trials_file is not None:
        try:
            # Load data
            patients_df = pd.read_csv(patients_file)
            trials_df = pd.read_csv(trials_file)
            
            # Show data preview
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("📊 Patients Data Preview")
                st.dataframe(patients_df.head(), use_container_width=True)
                st.caption(f"Total patients: {len(patients_df)}")
            
            with col2:
                st.subheader("📅 Trials Data Preview") 
                st.dataframe(trials_df.head(), use_container_width=True)
                st.caption(f"Total trial visits: {len(trials_df)}")
            
            # Validate and process
            builder = TrialCalendarBuilder(patients_df, trials_df)
            validation_errors = builder.validate_data()
            
            if validation_errors:
                st.error("❌ Data Validation Errors:")
                for error in validation_errors:
                    st.error(f"• {error}")
                st.info("Please check your CSV files have the required columns.")
                return
            
            # Debug section
            with st.expander("🔍 Debug Info - Check Your Data"):
                st.write("**Patients CSV columns:**", patients_df.columns.tolist())
                st.write("**Trials CSV columns:**", trials_df.columns.tolist())
                
                # Show sample of date-related columns
                date_cols = [col for col in patients_df.columns if any(term in col.lower() for term in ['year', 'month', 'day', 'date', 'yr', 'mon'])]
                if date_cols:
                    st.write("**Date-related columns in patients:**")
                    st.dataframe(patients_df[date_cols].head(), use_container_width=True)
                else:
                    st.warning("No date columns found!")

            # Process button
            if st.button("🚀 Generate Calendar", type="primary", use_container_width=True):
                with st.spinner("Generating calendar..."):
                    builder.prepare_patients()
                    builder.build_calendar()
                    output = builder.generate_output()
                
                st.success(f"✅ Calendar generated successfully! {len(output)} days processed.")
                
                # Display results
                st.subheader("📋 Generated Calendar")
                st.dataframe(output, use_container_width=True)
                
                # Summary stats
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    total_payment = output['Payment'].sum()
                    st.metric("Total Payments", f"£{total_payment:,.2f}")
                
                with col2:
                    visit_days = len(output[output['Payment'] > 0])
                    st.metric("Visit Days", visit_days)
                
                with col3:
                    date_range = f"{output['Date'].min()} - {output['Date'].max()}"
                    st.metric("Date Range", "")
                    st.caption(date_range)
                
                with col4:
                    unique_studies = len(patients_df['Study'].unique())
                    st.metric("Studies", unique_studies)
                
                # Download button
                csv = convert_df_to_csv(output)
                st.download_button(
                    label="📥 Download Calendar CSV",
                    data=csv,
                    file_name=f"trial_calendar_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
                
        except Exception as e:
            st.error(f"❌ Error processing files: {str(e)}")
            logger.error(f"Processing error: {e}")
    
    else:
        # Instructions when no files uploaded
        st.info("👆 Please upload both CSV files to get started")
        
        with st.expander("📖 Required CSV Format"):
            st.markdown("""
            **Patients CSV should contain:**
            - `PatientID`: Unique patient identifier
            - `Study`: Study name/code
            - Date columns (flexible names accepted):
              - Year: `V1_Year`, `Year`, `Yr`, etc.
              - Month: `V1_Month`, `Month`, `Mon`, etc.  
              - Day: `V1_Day`, `Day`, etc.
            
            **Trials CSV should contain:**
            - `Study`: Study name/code (matching patients)
            - `VisitNo`: Visit number
            - `Day`: Days from Visit 1
            - `Payment`: Payment amount (optional)
            - `ToleranceBefore`, `ToleranceAfter`: Tolerance days (optional)
            """)
            
        with st.expander("🔍 Debug: Show My Column Names"):
            if patients_file is not None:
                st.write("**Your Patients columns:**", list(pd.read_csv(patients_file).columns))
            if trials_file is not None:
                st.write("**Your Trials columns:**", list(pd.read_csv(trials_file).columns))

if __name__ == "__main__":
    main()

