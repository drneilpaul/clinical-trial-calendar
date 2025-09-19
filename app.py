import streamlit as st
import pandas as pd
import io
from datetime import date
import re
import streamlit.components.v1 as components
from helpers import load_file, normalize_columns, parse_dates_column
from processing_calendar import build_calendar

def show_legend(actual_visits_df):
    if actual_visits_df is not None:
        st.info("""
        **Legend with Color Coding:**
        
        **Actual Visits:**
        - ✅ Visit X (Green background) = Completed Visit (within tolerance window)  
        - ⚠️ Visit X (Yellow background) = Completed Visit (outside tolerance window)
        - ❌ Screen Fail X (Red background) = Screen failure (no future visits)
        
        **Scheduled Visits:**
        - Visit X (Gray background) = Scheduled/Planned Visit
        - \\- (Light blue-gray, italic) = Before tolerance period
        - \\+ (Light blue-gray, italic) = After tolerance period
        
        **Date Formatting:**
        - Red background = Today's date
        - Light blue background = Month end
        - Dark blue background = Financial year end (31 March)
        - Gray background = Weekend
        """)
    else:
        st.info("""
        **Legend:** 
        - Visit X (Gray) = Scheduled Visit
        - - (Light blue-gray) = Before tolerance period
        - + (Light blue-gray) = After tolerance period
        """)

def display_styled_calendar(calendar_df, site_column_mapping, unique_sites):
    st.subheader("Generated Visit Calendar")
    
    # Create display dataframe
    final_ordered_columns = ["Date", "Day"]
    for site in unique_sites:
        site_columns = site_column_mapping.get(site, [])
        for col in site_columns:
            if col in calendar_df.columns:
                final_ordered_columns.append(col)
    
    display_df = calendar_df[final_ordered_columns].copy()
    display_df_for_view = display_df.copy()
    display_df_for_view["Date"] = display_df_for_view["Date"].dt.strftime("%Y-%m-%d")
    
    # Create site header row
    site_header_row = {}
    for col in display_df_for_view.columns:
        if col in ["Date", "Day"]:
            site_header_row[col] = ""
        else:
            site_found = ""
            for site in unique_sites:
                if col in site_column_mapping.get(site, []):
                    site_found = site
                    break
            site_header_row[col] = site_found
    
    # Combine header with data
    site_header_df = pd.DataFrame([site_header_row])
    display_with_header = pd.concat([site_header_df, display_df_for_view], ignore_index=True)
    
    # Create styling function
    def highlight_calendar(row):
        if row.name == 0:  # Site header row
            styles = []
            for col_name in row.index:
                if row[col_name] != "":
                    styles.append('background-color: #e6f3ff; font-weight: bold; text-align: center; border: 1px solid #ccc;')
                else:
                    styles.append('background-color: #f8f9fa; border: 1px solid #ccc;')
            return styles
        else:
            # Data rows
            styles = []
            date_str = row.get("Date", "")
            date_obj = None
            try:
                if date_str:
                    date_obj = pd.to_datetime(date_str)
            except:
                pass

            today = pd.to_datetime(date.today())
            
            for col_name, cell_value in row.items():
                style = ""
                
                # Date-based styling
                if date_obj is not None and not pd.isna(date_obj):
                    if date_obj.date() == today.date():
                        style = 'background-color: #dc2626; color: white; font-weight: bold;'
                    elif date_obj.month == 3 and date_obj.day == 31:
                        style = 'background-color: #1e40af; color: white; font-weight: bold;'
                    elif date_obj == date_obj + pd.offsets.MonthEnd(0):
                        style = 'background-color: #60a5fa; color: white;'
                    elif date_obj.weekday() in (5, 6):
                        style = 'background-color: #e5e7eb;'
                
                # Visit-specific styling
                if style == "" and col_name not in ["Date", "Day"] and str(cell_value) != "":
                    cell_str = str(cell_value)
                    if "✅ Visit" in cell_str:
                        style = 'background-color: #d4edda; color: #155724; font-weight: bold;'
                    elif "⚠️ Visit" in cell_str:
                        style = 'background-color: #fff3cd; color: #856404; font-weight: bold;'
                    elif "❌ Screen Fail" in cell_str:
                        style = 'background-color: #f8d7da; color: #721c24; font-weight: bold;'
                    elif "Visit " in cell_str and not cell_str.startswith(("✅", "⚠️")):
                        style = 'background-color: #e2e3e5; color: #383d41;'
                    elif cell_str in ["+", "-"]:
                        style = 'background-color: #f1f5f9; color: #64748b; font-style: italic; font-size: 0.9em;'
                
                styles.append(style)
            
            return styles

    try:
        styled_df = display_with_header.style.apply(highlight_calendar, axis=1)
        html_table = styled_df.to_html(escape=False)
        
        components.html(f"""
        <div style='max-height: 700px; overflow: auto; border: 1px solid #ddd;'>
            {html_table}
        </div>
        """, height=720, scrolling=True)
    except Exception as e:
        st.write(f"Styling error: {e}")
        st.dataframe(display_with_header, use_container_width=True)

def display_financial_analysis(stats, visits_df):
    st.subheader("💰 Financial Analysis")
    
    # Filter for relevant visits
    financial_df = visits_df[
        (visits_df['Visit'].str.startswith("✅")) |
        (visits_df['Visit'].str.startswith("❌ Screen Fail")) |
        (visits_df['Visit'].str.contains('Visit', na=False) & (~visits_df.get('IsActual', False)))
    ].copy()
    
    if not financial_df.empty:
        actual_financial = financial_df[financial_df.get('IsActual', False)]
        scheduled_financial = financial_df[~financial_df.get('IsActual', True)]
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            actual_income = actual_financial['Payment'].sum() if not actual_financial.empty else 0
            st.metric("Actual Income", f"£{actual_income:,.2f}")
        with col2:
            scheduled_income = scheduled_financial['Payment'].sum() if not scheduled_financial.empty else 0
            st.metric("Scheduled Income", f"£{scheduled_income:,.2f}")
        with col3:
            total_income = actual_income + scheduled_income
            st.metric("Total Income", f"£{total_income:,.2f}")
        with col4:
            screen_fail_count = len(actual_financial[actual_financial.get('IsScreenFail', False)]) if not actual_financial.empty else 0
            st.metric("Screen Failures", screen_fail_count)

        # Monthly analysis
        if not financial_df.empty:
            financial_df['MonthYear'] = financial_df['Date'].dt.to_period('M')
            monthly_income = financial_df.groupby(['SiteofVisit', 'MonthYear'])['Payment'].sum().reset_index()
            monthly_pivot = monthly_income.pivot(index='MonthYear', columns='SiteofVisit', values='Payment').fillna(0)
            
            if not monthly_pivot.empty:
                st.subheader("📊 Monthly Income Chart")
                monthly_pivot.index = monthly_pivot.index.astype(str)
                st.bar_chart(monthly_pivot)
    else:
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total Visits", stats.get("total_visits", 0))
        with col2:
            st.metric("Total Income", f"£{stats.get('total_income', 0):,.2f}")

def display_enhanced_downloads(calendar_df, site_column_mapping, unique_sites):
    st.subheader("💾 Download Options")
    
    try:
        import openpyxl
        from openpyxl.styles import PatternFill, Font, Alignment
        from openpyxl.utils import get_column_letter
        
        # Prepare display columns
        final_ordered_columns = ["Date", "Day"]
        for site in unique_sites:
            site_columns = site_column_mapping.get(site, [])
            for col in site_columns:
                if col in calendar_df.columns:
                    final_ordered_columns.append(col)
        
        # Create Excel with formatting
        excel_df = calendar_df[final_ordered_columns].copy()
        excel_df["Date"] = excel_df["Date"].dt.strftime("%d/%m/%Y")
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            excel_df.to_excel(writer, index=False, sheet_name="VisitCalendar", startrow=1)
            ws = writer.sheets["VisitCalendar"]

            # Add site headers
            for col_idx, col_name in enumerate(excel_df.columns, 1):
                col_letter = get_column_letter(col_idx)
                if col_name not in ["Date", "Day"]:
                    for site in unique_sites:
                        if col_name in site_column_mapping.get(site, []):
                            ws[f"{col_letter}1"] = site
                            ws[f"{col_letter}1"].font = Font(bold=True, size=12)
                            ws[f"{col_letter}1"].fill = PatternFill(start_color="FFE6F3FF", end_color="FFE6F3FF", fill_type="solid")
                            ws[f"{col_letter}1"].alignment = Alignment(horizontal="center")
                            break

            # Auto-adjust column widths
            for idx, col in enumerate(excel_df.columns, 1):
                col_letter = get_column_letter(idx)
                max_length = max([len(str(cell)) for cell in excel_df[col].tolist()] + [len(col)])
                ws.column_dimensions[col_letter].width = max(10, max_length + 2)

        st.download_button(
            "📅 Excel with Site Headers & Formatting",
            data=output.getvalue(),
            file_name="VisitCalendar_Formatted.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except ImportError:
        st.warning("Excel formatting unavailable - install openpyxl for enhanced features")
        # Basic Excel download
        buf = io.BytesIO()
        calendar_df.to_excel(buf, index=False)
        st.download_button(
            "💾 Download Basic Calendar Excel", 
            data=buf.getvalue(), 
            file_name="VisitCalendar.xlsx"
        )

def extract_site_summary(patients_df, screen_failures=None):
    """Extract site summary statistics from patients dataframe"""
    if patients_df.empty:
        return pd.DataFrame()
    
    unique_sites = sorted(patients_df["Site"].unique())
    site_summary_data = []
    
    for site in unique_sites:
        site_patients = patients_df[patients_df["Site"] == site]
        site_studies = site_patients["Study"].unique()
        
        site_screen_fails = 0
        if screen_failures:
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
    
    return pd.DataFrame(site_summary_data)

def main():
    st.set_page_config(page_title="Clinical Trial Calendar Generator", layout="wide")
    st.title("🏥 Clinical Trial Calendar Generator")

    # File uploaders
    patients_file = st.sidebar.file_uploader("Upload Patients File", type=['csv', 'xls', 'xlsx'])
    trials_file = st.sidebar.file_uploader("Upload Trials File", type=['csv', 'xls', 'xlsx'])
    actual_visits_file = st.sidebar.file_uploader("Upload Actual Visits File (Optional)", type=['csv', 'xls', 'xlsx'])

    if not (patients_file and trials_file):
        st.info("Please upload both Patients and Trials files to get started.")
        return

    try:
        # Load and process files
        patients_df = normalize_columns(load_file(patients_file))
        trials_df = normalize_columns(load_file(trials_file))
        actual_visits_df = normalize_columns(load_file(actual_visits_file)) if actual_visits_file else None

        # Date parsing
        patients_df, failed_patients = parse_dates_column(patients_df, "StartDate")
        if failed_patients:
            st.error(f"Unparseable StartDate values: {failed_patients}")

        if actual_visits_df is not None:
            actual_visits_df, failed_actuals = parse_dates_column(actual_visits_df, "ActualDate")
            if failed_actuals:
                st.error(f"Unparseable ActualDate values: {failed_actuals}")

        # Data type conversion
        patients_df["PatientID"] = patients_df["PatientID"].astype(str)
        if "VisitNo" in trials_df.columns:
            trials_df["VisitNo"] = trials_df["VisitNo"].astype(str)
        if actual_visits_df is not None and "VisitNo" in actual_visits_df.columns:
            actual_visits_df["VisitNo"] = actual_visits_df["VisitNo"].astype(str)

        # Check missing studies
        missing_studies = set(patients_df["Study"].astype(str)) - set(trials_df["Study"].astype(str))
        if missing_studies:
            st.error(f"❌ Missing Study Definitions: {missing_studies}")
            st.stop()

        # Build calendar
        visits_df, calendar_df, stats, messages, site_column_mapping, unique_sites = build_calendar(
            patients_df, trials_df, actual_visits_df
        )
        
        # Extract screen failures for site summary
        screen_failures = {}
        if actual_visits_df is not None:
            screen_fail_visits = actual_visits_df[
                actual_visits_df["Notes"].str.contains("ScreenFail", case=False, na=False)
            ]
            for _, visit in screen_fail_visits.iterrows():
                patient_study_key = f"{visit['PatientID']}_{visit['Study']}"
                screen_fail_date = visit['ActualDate']
                if patient_study_key not in screen_failures or screen_fail_date < screen_failures[patient_study_key]:
                    screen_failures[patient_study_key] = screen_fail_date

        # Show processing messages
        if messages:
            with st.expander("📋 Processing Log", expanded=False):
                for message in messages:
                    st.write(message)

        # Site summary
        site_summary_df = extract_site_summary(patients_df, screen_failures)
        if not site_summary_df.empty:
            st.subheader("Site Summary")
            st.dataframe(site_summary_df, use_container_width=True)

        # Display components
        show_legend(actual_visits_df)
        display_styled_calendar(calendar_df, site_column_mapping, unique_sites)
        display_financial_analysis(stats, visits_df)
        display_enhanced_downloads(calendar_df, site_column_mapping, unique_sites)
            
    except Exception as e:
        st.error(f"Error processing files: {e}")
        st.exception(e)

if __name__ == "__main__":
    main()
