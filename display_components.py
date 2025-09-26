import streamlit as st
import pandas as pd
import io
from datetime import date
import re
import streamlit.components.v1 as components

# Import our modular components
from calculations import (
    prepare_financial_data, build_profit_sharing_analysis, 
    build_ratio_breakdown_data, get_list_ratios
)
from formatters import (
    format_currency, create_site_header_row, style_calendar_row,
    apply_currency_formatting, apply_currency_or_empty_formatting
)
from table_builders import (
    display_income_table_pair, display_profit_sharing_table,
    display_ratio_breakdown_table, create_summary_metrics_row,
    display_breakdown_by_study, create_time_period_config,
    display_site_time_analysis, display_complete_realization_analysis
)

def show_legend(actual_visits_df):
    """Display legend for calendar interpretation"""
    legend_text = """
    **Legend with Color Coding:**

    **Actual Visits:**
    - ✅ VisitName (Green background) = Completed Visit (within tolerance window)  
    - 🔴 OUT OF PROTOCOL VisitName (Red background) = Completed Visit (outside tolerance window - protocol deviation)
    - ⚠️ Screen Fail VisitName (Dark red background) = Screen failure (no future visits - only valid up to Day 1)

    **Scheduled Visits:**
    - VisitName (Gray background) = Scheduled/Planned Visit
    - \\- (Light blue-gray, italic) = Before tolerance period
    - \\+ (Light blue-gray, italic) = After tolerance period

    **Date Formatting:**
    - Red background = Today's date
    - Light blue background = Month end (softer highlighting)
    - Dark blue background = Financial year end (31 March)
    - Gray background = Weekend
    - Blue separator lines = Month boundaries (screen only)
    
    **Three-Level Headers:**
    - Dark blue header = Visit site (where visits are performed)
    - Medium blue header = Study_PatientID
    - Light blue header = Patient origin site (who recruited patient)
    
    **Note:** Day 1 visit (baseline) establishes the timeline for all future visits regardless of timing - it's never a protocol deviation. Only visits after Day 1 can be marked as OUT OF PROTOCOL when outside tolerance windows.
    """ if actual_visits_df is not None else """
    **Legend:** 
    - VisitName (Gray) = Scheduled Visit
    - - (Light blue-gray) = Before tolerance period
    - + (Light blue-gray) = After tolerance period
    - Light blue background = Month end (softer highlighting)
    - Dark blue background = Financial year end (31 March)
    - Gray background = Weekend
    - Blue separator lines = Month boundaries (screen only)
    
    **Three-Level Headers:**
    - Dark blue header = Visit site (where visits are performed)
    - Medium blue header = Study_PatientID
    - Light blue header = Patient origin site (who recruited patient)
    
    **Note:** Day 1 visit is the baseline reference point for all visit scheduling.
    """
    
    st.info(legend_text)

def display_calendar(calendar_df, site_column_mapping, unique_visit_sites, excluded_visits=None):
    """Display the main visit calendar with three-level styling"""
    st.subheader("Generated Visit Calendar")

    try:
        # Prepare display columns
        final_ordered_columns = ["Date", "Day"]
        for visit_site in unique_visit_sites:
            site_data = site_column_mapping.get(visit_site, {})
            site_columns = site_data.get('columns', [])
            for col in site_columns:
                if col in calendar_df.columns:
                    final_ordered_columns.append(col)

        display_df = calendar_df[final_ordered_columns].copy()
        display_df_for_view = display_df.copy()
        display_df_for_view["Date"] = display_df_for_view["Date"].dt.strftime("%Y-%m-%d")

        # Create three-level header rows
        header_rows = create_site_header_row(display_df_for_view.columns, site_column_mapping)
        
        # Create header dataframes
        level1_df = pd.DataFrame([header_rows['level1_site']])  # Visit sites
        level2_df = pd.DataFrame([header_rows['level2_study_patient']])  # Study_Patient
        level3_df = pd.DataFrame([header_rows['level3_origin']])  # Origin sites
        
        # Combine all headers with data
        display_with_headers = pd.concat([
            level1_df,      # Level 1: Visit sites (ASHFIELDS, KILTEARN)
            level2_df,      # Level 2: Study_PatientID (Alpha_P001, Beta_P003)
            level3_df,      # Level 3: Origin sites ((Kiltearn), (Ashfields))
            display_df_for_view  # Actual visit data
        ], ignore_index=True)

        # Apply styling for three header rows
        try:
            today = pd.to_datetime(date.today())
            styled_df = display_with_headers.style.apply(
                lambda row: style_calendar_row(row, today), axis=1
            )
            
            # Generate HTML with month separators
            html_table = _generate_calendar_html_with_separators(styled_df)
            components.html(html_table, height=800, scrolling=True)  # Increased height for extra headers
            
        except Exception as e:
            st.warning(f"Calendar styling unavailable: {e}")
            st.dataframe(display_with_headers, use_container_width=True)

        if excluded_visits and len(excluded_visits) > 0:
            st.warning("Some visits were excluded due to screen failure:")
            st.dataframe(pd.DataFrame(excluded_visits))
            
    except Exception as e:
        st.error(f"Error displaying calendar: {e}")
        st.dataframe(calendar_df, use_container_width=True)

def _generate_calendar_html_with_separators(styled_df):
    """Generate HTML calendar with month separators"""
    try:
        html_table_base = styled_df.to_html(escape=False)
        html_lines = html_table_base.split('\n')
        modified_html_lines = []

        prev_month = None
        header_rows_passed = 0
        
        for i, line in enumerate(html_lines):
            # Skip month separator logic for header rows (first 3 data rows after table headers)
            if '<td>' in line:
                if header_rows_passed < 3:
                    header_rows_passed += 1
                    modified_html_lines.append(line)
                    continue
                    
                date_pattern = r'<td>(\d{4}-\d{2}-\d{2})</td>'
                match = re.search(date_pattern, line)
                if match:
                    try:
                        date_obj = pd.to_datetime(match.group(1))
                        current_month = date_obj.to_period('M')

                        if prev_month is not None and current_month != prev_month:
                            col_count = line.count('<td>')
                            separator_line = f'<tr style="border-top: 3px solid #3b82f6; background-color: #eff6ff;"><td colspan="{col_count}" style="text-align: center; font-weight: bold; color: #1e40af; padding: 2px;">{current_month}</td></tr>'
                            modified_html_lines.append(separator_line)

                        prev_month = current_month
                    except:
                        pass

            modified_html_lines.append(line)

        html_table_with_separators = '\n'.join(modified_html_lines)
        return f"""
        <div style='max-height: 700px; overflow: auto; border: 1px solid #ddd;'>
            {html_table_with_separators}
        </div>
        """
    except Exception as e:
        st.warning(f"Calendar HTML generation failed: {e}")
        return styled_df.to_html(escape=False)

def display_site_statistics(site_summary_df):
    """Display basic site summary statistics"""
    st.subheader("Site Summary")
    st.dataframe(site_summary_df, use_container_width=True)

def display_monthly_income_tables(visits_df):
    """Display monthly income analysis with tables only"""
    st.subheader("📊 Monthly Income Analysis")
    
    try:
        financial_df = prepare_financial_data(visits_df)
        if not financial_df.empty:
            display_income_table_pair(financial_df)
        else:
            st.warning("No financial data available for monthly analysis")
    except Exception as e:
        st.error(f"Error displaying monthly income tables: {e}")

def display_quarterly_profit_sharing_tables(financial_df, patients_df):
    """Display quarterly profit sharing analysis with tables and calculations"""
    st.subheader("📊 Quarterly Profit Sharing Analysis")

    try:
        # Weight adjustment interface
        _display_weight_adjustment_interface()

        # Get current weights
        weights = (
            st.session_state.get('list_weight', 35) / 100,
            st.session_state.get('work_weight', 35) / 100,
            st.session_state.get('recruitment_weight', 30) / 100
        )

        # Display current configuration
        list_ratios = get_list_ratios()
        list_weight = st.session_state.get('list_weight', 35)
        work_weight = st.session_state.get('work_weight', 35)
        recruitment_weight = st.session_state.get('recruitment_weight', 30)
        
        st.info(f"**Current Weights:** List Sizes {list_weight}% • Work Done {work_weight}% • Patient Recruitment {recruitment_weight}%")

        # Build and display main analysis
        quarterly_ratios = build_profit_sharing_analysis(financial_df, patients_df, weights)
        
        if quarterly_ratios:
            display_profit_sharing_table(quarterly_ratios)
            
            # Analysis summary
            st.write("**Analysis Notes:**")
            st.info(f"""
            **Profit Sharing Formula:** 
            - List Sizes: {list_weight}% (Ashfields: {list_ratios['ashfields']:.1%}, Kiltearn: {list_ratios['kiltearn']:.1%})
            - Work Done: {work_weight}% (Based on actual visits completed per quarter)
            - Patient Recruitment: {recruitment_weight}% (Based on patients recruited per quarter)
            
            **Highlighted rows** show Financial Year totals. Individual quarters show the detailed breakdown.
            """)
            
            # Add detailed ratio breakdowns
            st.divider()
            display_profit_sharing_ratio_breakdowns(financial_df, patients_df)
        else:
            st.warning("No quarterly data available for analysis. Upload visit data with dates to generate quarterly profit sharing calculations.")
    except Exception as e:
        st.error(f"Error displaying profit sharing analysis: {e}")

def _display_weight_adjustment_interface():
    """Display the weight adjustment interface"""
    if st.button("⚙️ Adjust Profit Sharing Weights", use_container_width=False):
        st.session_state.show_weights_form = True

    # Initialize default weights
    for weight_type, default_value in [('list_weight', 35), ('work_weight', 35), ('recruitment_weight', 30)]:
        if weight_type not in st.session_state:
            st.session_state[weight_type] = default_value

    # Weight adjustment modal
    if st.session_state.get('show_weights_form', False):
        st.write("**Adjust Profit Sharing Weights**")
        st.write("Current Formula: List Sizes + Work Done + Patient Recruitment = 100%")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            new_list_weight = st.slider("List Size %", 0, 100, st.session_state.get('list_weight', 35), key="list_weight_slider")
        with col2:
            new_work_weight = st.slider("Work Done %", 0, 100, st.session_state.get('work_weight', 35), key="work_weight_slider")
        with col3:
            new_recruitment_weight = st.slider("Recruitment %", 0, 100, st.session_state.get('recruitment_weight', 30), key="recruitment_weight_slider")
        
        total_weight = new_list_weight + new_work_weight + new_recruitment_weight
        
        if total_weight == 100:
            st.success(f"✅ Total: {total_weight}% (Perfect!)")
        else:
            st.error(f"⌛ Total: {total_weight}% - Must equal 100%")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Apply Changes", disabled=(total_weight != 100)):
                st.session_state.list_weight = new_list_weight
                st.session_state.work_weight = new_work_weight
                st.session_state.recruitment_weight = new_recruitment_weight
                st.session_state.show_weights_form = False
                st.success("Weights updated!")
                st.rerun()
        
        with col2:
            if st.button("Cancel"):
                st.session_state.show_weights_form = False
                st.rerun()

def display_profit_sharing_ratio_breakdowns(financial_df, patients_df):
    """Display detailed ratio breakdowns for profit sharing calculations"""
    st.subheader("📊 Profit Sharing Ratio Breakdowns")
    
    try:
        # Get current weights and configuration
        weights = (
            st.session_state.get('list_weight', 35) / 100,
            st.session_state.get('work_weight', 35) / 100,
            st.session_state.get('recruitment_weight', 30) / 100
        )
        
        list_ratios = get_list_ratios()
        list_weight = st.session_state.get('list_weight', 35)
        work_weight = st.session_state.get('work_weight', 35) 
        recruitment_weight = st.session_state.get('recruitment_weight', 30)
        
        # Display formula and fixed ratios
        st.info(f"**Formula:** List Sizes {list_weight}% + Work Done {work_weight}% + Patient Recruitment {recruitment_weight}%")
        st.info(f"**Fixed List Ratios:** Ashfields {list_ratios['ashfields']:.1%} ({list_ratios['ashfields_size']:,}) | Kiltearn {list_ratios['kiltearn']:.1%} ({list_ratios['kiltearn_size']:,})")
        
        # Display ratio breakdowns for each time period
        time_periods = create_time_period_config()
        
        for period_key, period_config in time_periods.items():
            ratio_data = build_ratio_breakdown_data(financial_df, patients_df, period_config, weights)
            if ratio_data:  # Only display if there's data
                display_ratio_breakdown_table(ratio_data, period_config['title'])
        
        # Explanation for bookkeepers
        st.info("""
        **For Bookkeepers:**
        - **List %**: Fixed ratios based on practice list sizes (never changes)
        - **Work %**: Variable ratios based on actual visits completed in the period
        - **Recruit %**: Variable ratios based on patients recruited in the period
        - **Final %**: Combined weighted percentage for profit sharing calculations
        - Apply the Final % to the total income for each period to determine profit share amounts
        """)
    except Exception as e:
        st.error(f"Error displaying ratio breakdowns: {e}")

def display_income_realization_analysis(visits_df, trials_df, patients_df):
    """Display income realization analysis section"""
    try:
        display_complete_realization_analysis(visits_df, trials_df, patients_df)
    except Exception as e:
        st.error(f"Error displaying income realization analysis: {e}")

def display_site_wise_statistics(visits_df, patients_df, unique_visit_sites, screen_failures):
    """Display detailed statistics for each site with quarterly and financial year analysis"""
    if visits_df.empty or patients_df.empty:
        return
    
    st.subheader("📊 Site-wise Analysis")
    
    try:
        # Prepare enhanced visits data
        enhanced_visits_df = prepare_financial_data(visits_df)
        
        # Create tabs for each visit site or display directly if single site
        if len(unique_visit_sites) > 1:
            tabs = st.tabs(unique_visit_sites)
            for i, visit_site in enumerate(unique_visit_sites):
                with tabs[i]:
                    _display_single_site_analysis(visits_df, patients_df, enhanced_visits_df, visit_site, screen_failures)
        else:
            _display_single_site_analysis(visits_df, patients_df, enhanced_visits_df, unique_visit_sites[0], screen_failures)
    except Exception as e:
        st.error(f"Error displaying site-wise statistics: {e}")

def _display_single_site_analysis(visits_df, patients_df, enhanced_visits_df, site, screen_failures):
    """Display comprehensive analysis for a single site"""
    try:
        # Filter for visits that actually happen at this site
        site_visits = visits_df[visits_df['SiteofVisit'] == site]
        
        # Find patients who have visits at this site (may be from different origin sites)
        patients_with_visits_here = visits_df[visits_df['SiteofVisit'] == site]['PatientID'].unique()
        site_related_patients = patients_df[patients_df['PatientID'].isin(patients_with_visits_here)]
        
        if site_related_patients.empty:
            st.warning(f"No patients found with visits at site: {site}")
            return
        
        st.subheader(f"🏥 {site} - Visit Site Analysis")
        
        # Overall statistics
        st.write("**Overall Statistics**")
        metrics_data = {
            "Patients with visits here": len(site_related_patients),
            "Total Visits at this site": len(site_visits),
            "Completed Visits": len(site_visits[site_visits.get('IsActual', False)]),
            "Total Income": format_currency(site_visits['Payment'].sum())
        }
        create_summary_metrics_row(metrics_data, 4)
        
        # Study breakdown at this site
        st.write("**Studies performed at this site:**")
        display_breakdown_by_study(site_visits, site_related_patients, site)
        
        # Time-based analysis for work done at this site
        display_site_time_analysis(site_visits, site_related_patients, site, enhanced_visits_df)
        
        # Patient origin analysis
        st.write("**Patient Origins (Who Recruited):**")
        origin_breakdown = site_related_patients.groupby('Site')['PatientID'].count().reset_index()
        origin_breakdown.columns = ['Origin Site', 'Patients Recruited']
        st.dataframe(origin_breakdown, use_container_width=True)
        
        # Screen failures for patients with visits at this site
        _display_site_screen_failures(site_related_patients, screen_failures)
    except Exception as e:
        st.error(f"Error displaying analysis for site {site}: {e}")

def _display_site_screen_failures(site_patients, screen_failures):
    """Display screen failures for patients related to a site"""
    try:
        from table_builders import display_site_screen_failures
        display_site_screen_failures(site_patients, screen_failures)
    except Exception as e:
        st.error(f"Error displaying screen failures: {e}")

def display_download_buttons(calendar_df, site_column_mapping, unique_visit_sites):
    """Display comprehensive download options with Excel formatting"""
    st.subheader("💾 Download Options")

    try:
        # Try to import openpyxl for enhanced Excel features
        try:
            import openpyxl
            from openpyxl.styles import PatternFill, Font, Alignment
            from openpyxl.utils import get_column_letter
            excel_available = True
        except ImportError:
            excel_available = False

        if excel_available:
            # Prepare data for Excel export
            from table_builders import create_excel_export_data, apply_excel_formatting
            excel_df = create_excel_export_data(calendar_df, site_column_mapping, unique_visit_sites)
            
            # Create Excel file
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                excel_df.to_excel(writer, index=False, sheet_name="VisitCalendar", startrow=1)
                ws = writer.sheets["VisitCalendar"]

                # Add site headers and formatting
                apply_excel_formatting(ws, excel_df, site_column_mapping, unique_visit_sites)

            st.download_button(
                "💰 Excel with Finances & Site Headers",
                data=output.getvalue(),
                file_name="VisitCalendar_WithFinances_SiteGrouped.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            # Basic Excel export without formatting
            st.warning("Excel formatting unavailable - install openpyxl for enhanced features")
            buf = io.BytesIO()
            calendar_df.to_excel(buf, index=False)
            st.download_button(
                "💾 Download Basic Excel", 
                data=buf.getvalue(), 
                file_name="VisitCalendar.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    except Exception as e:
        st.error(f"Error creating download options: {e}")
        # Fallback to CSV download
        csv = calendar_df.to_csv(index=False)
        st.download_button(
            "📄 Download as CSV",
            data=csv,
            file_name="VisitCalendar.csv",
            mime="text/csv"
        )

def display_verification_figures(visits_df, calendar_df, financial_df, patients_df):
    """Display verification figures for testing and validation"""
    st.subheader("🔍 Verification Figures")
    st.caption("Copy these figures to verify calculations are correct")
    
    try:
        # Calculate key metrics
        verification_data = []
        
        # Overall totals
        total_visits = len(visits_df)
        completed_visits = len(visits_df[visits_df.get('IsActual', False) == True])
        scheduled_visits = total_visits - completed_visits
        total_income = visits_df['Payment'].sum()
        completed_income = visits_df[visits_df.get('IsActual', False) == True]['Payment'].sum()
        scheduled_income = visits_df[visits_df.get('IsActual', False) == False]['Payment'].sum()
        
        verification_data.append({
            'Metric': 'Total Visits',
            'Value': total_visits,
            'Details': f"Completed: {completed_visits}, Scheduled: {scheduled_visits}"
        })
        
        verification_data.append({
            'Metric': 'Total Income',
            'Value': f"£{total_income:,.2f}",
            'Details': f"Completed: £{completed_income:,.2f}, Scheduled: £{scheduled_income:,.2f}"
        })
        
        # By study
        study_breakdown = visits_df.groupby('Study').agg({
            'Visit': 'count',
            'Payment': 'sum',
            'IsActual': lambda x: x.sum() if x.dtype == bool else (x == True).sum()
        }).rename(columns={'Visit': 'Total_Visits', 'Payment': 'Total_Income', 'IsActual': 'Completed_Visits'})
        
        for study, row in study_breakdown.iterrows():
            verification_data.append({
                'Metric': f'{study} - Visits',
                'Value': int(row['Total_Visits']),
                'Details': f"Completed: {int(row['Completed_Visits'])}, Income: £{row['Total_Income']:,.2f}"
            })
        
        # By visit site (where work is done)
        site_breakdown = visits_df.groupby('SiteofVisit').agg({
            'Visit': 'count',
            'Payment': 'sum',
            'IsActual': lambda x: x.sum() if x.dtype == bool else (x == True).sum()
        }).rename(columns={'Visit': 'Total_Visits', 'Payment': 'Total_Income', 'IsActual': 'Completed_Visits'})
        
        for site, row in site_breakdown.iterrows():
            verification_data.append({
                'Metric': f'{site} - Visit Site',
                'Value': int(row['Total_Visits']),
                'Details': f"Completed: {int(row['Completed_Visits'])}, Income: £{row['Total_Income']:,.2f}"
            })
        
        # Screen failures
        screen_failed_patients = visits_df[visits_df.get('IsScreenFail', False) == True]['PatientID'].nunique()
        verification_data.append({
            'Metric': 'Screen Failed Patients',
            'Value': screen_failed_patients,
            'Details': "Patients with screen failure visits"
        })
        
        # Out of protocol visits
        out_of_protocol_visits = len(visits_df[visits_df.get('IsOutOfProtocol', False) == True])
        verification_data.append({
            'Metric': 'Out of Protocol Visits',
            'Value': out_of_protocol_visits,
            'Details': "Visits outside tolerance windows"
        })
        
        # Financial year totals
        if not financial_df.empty and 'FinancialYear' in financial_df.columns:
            fy_breakdown = financial_df.groupby('FinancialYear')['Payment'].sum()
            for fy, total in fy_breakdown.items():
                verification_data.append({
                    'Metric': f'FY {fy} Income',
                    'Value': f"£{total:,.2f}",
                    'Details': f"Financial year total"
                })
        
        # Calendar totals verification
        calendar_daily_total = calendar_df['Daily Total'].sum()
        calendar_fy_total = calendar_df['FY Total'].sum() if 'FY Total' in calendar_df.columns else 0
        calendar_monthly_total = calendar_df['Monthly Total'].sum() if 'Monthly Total' in calendar_df.columns else 0
        
        verification_data.append({
            'Metric': 'Calendar Daily Total Sum',
            'Value': f"£{calendar_daily_total:,.2f}",
            'Details': "Sum of all daily totals in calendar"
        })
        
        if calendar_fy_total > 0:
            verification_data.append({
                'Metric': 'Calendar FY Total Sum',
                'Value': f"£{calendar_fy_total:,.2f}",
                'Details': "Sum of FY totals (should equal daily total)"
            })
        
        if calendar_monthly_total > 0:
            verification_data.append({
                'Metric': 'Calendar Monthly Total Sum', 
                'Value': f"£{calendar_monthly_total:,.2f}",
                'Details': "Sum of monthly totals (should equal daily total)"
            })
        
        # Patient recruitment by origin site
        patient_site_breakdown = patients_df.groupby('Site')['PatientID'].count()
        for site, count in patient_site_breakdown.items():
            verification_data.append({
                'Metric': f'{site} - Patients Recruited',
                'Value': int(count),
                'Details': "Total patients recruited at this origin site"
            })
        
        # Create verification dataframe
        verification_df = pd.DataFrame(verification_data)
        
        # Display in expandable section
        with st.expander("📊 Detailed Verification Figures", expanded=False):
            st.dataframe(verification_df, use_container_width=True, hide_index=True)
            
            # Create downloadable CSV
            csv_data = verification_df.to_csv(index=False)
            st.download_button(
                "📥 Download Verification Figures (CSV)",
                data=csv_data,
                file_name="verification_figures.csv",
                mime="text/csv"
            )
            
            # Copy-paste friendly format
            st.write("**Copy-Paste Format:**")
            copy_text = "\n".join([
                f"{row['Metric']}: {row['Value']} ({row['Details']})"
                for _, row in verification_df.iterrows()
            ])
            st.code(copy_text, language="text")
    
    except Exception as e:
        st.error(f"Error generating verification figures: {e}")
        st.exception(e)
