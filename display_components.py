import streamlit as st
import pandas as pd
import io
from datetime import date
import re
import streamlit.components.v1 as components

def show_legend(actual_visits_df):
    if actual_visits_df is not None:
        st.info("""
        **Legend with Color Coding:**

        **Actual Visits:**
        - ✅ Visit X (Green background) = Completed Visit (within tolerance window)  
        - 🔴 OUT OF PROTOCOL Visit X (Red background) = Completed Visit (outside tolerance window - protocol deviation)
        - ❌ Screen Fail X (Dark red background) = Screen failure (no future visits)

        **Scheduled Visits:**
        - Visit X (Gray background) = Scheduled/Planned Visit
        - \\- (Light blue-gray, italic) = Before tolerance period
        - \\+ (Light blue-gray, italic) = After tolerance period

        **Date Formatting:**
        - Red background = Today's date
        - Light blue background = Month end (softer highlighting)
        - Dark blue background = Financial year end (31 March)
        - Gray background = Weekend
        - Blue separator lines = Month boundaries (screen only)
        
        **Note:** Visit 1 establishes the baseline for all future visits regardless of timing - it's never a protocol deviation. Only visits 2+ can be marked as OUT OF PROTOCOL when outside tolerance windows.
        """)
    else:
        st.info("""
        **Legend:** 
        - Visit X (Gray) = Scheduled Visit
        - - (Light blue-gray) = Before tolerance period
        - + (Light blue-gray) = After tolerance period
        - Light blue background = Month end (softer highlighting)
        - Dark blue background = Financial year end (31 March)
        - Gray background = Weekend
        - Blue separator lines = Month boundaries (screen only)
        """)

def display_calendar(calendar_df, site_column_mapping, unique_sites, excluded_visits=None):
    st.subheader("Generated Visit Calendar")

    # Create display dataframe and prepare columns
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

    # Create styling function with improved colors
    def highlight_with_header_fixed(row):
        if row.name == 0:  # Site header row
            styles = []
            for col_name in row.index:
                if row[col_name] != "":
                    styles.append('background-color: #e6f3ff; font-weight: bold; text-align: center; border: 1px solid #ccc;')
                else:
                    styles.append('background-color: #f8f9fa; border: 1px solid #ccc;')
            return styles
        else:
            # Data rows - first apply date-based styling, then visit-specific styling
            styles = []

            # Get the actual date for this row
            date_str = row.get("Date", "")
            date_obj = None
            try:
                if date_str:
                    date_obj = pd.to_datetime(date_str)
            except:
                pass

            # Get today's date for comparison
            today = pd.to_datetime(date.today())

            for col_idx, (col_name, cell_value) in enumerate(row.items()):
                style = ""

                # First check for date-based styling (applies to entire row)
                if date_obj is not None and not pd.isna(date_obj):
                    # Today's date - highest priority (RED)
                    if date_obj.date() == today.date():
                        style = 'background-color: #dc2626; color: white; font-weight: bold;'
                    # Financial year end (31 March) - second priority
                    elif date_obj.month == 3 and date_obj.day == 31:
                        style = 'background-color: #1e40af; color: white; font-weight: bold;'
                    # Month end - softer blue, third priority  
                    elif date_obj == date_obj + pd.offsets.MonthEnd(0):
                        style = 'background-color: #60a5fa; color: white; font-weight: normal;'
                    # Weekend - more obvious gray, fourth priority
                    elif date_obj.weekday() in (5, 6):  # Saturday=5, Sunday=6
                        style = 'background-color: #e5e7eb;'

                # Only apply visit-specific styling if no date styling was applied
                if style == "" and col_name not in ["Date", "Day"] and str(cell_value) != "":
                    cell_str = str(cell_value)

                    # Visit-specific color coding with updated emoji matching
                    if '✅ Visit' in cell_str:
                        style = 'background-color: #d4edda; color: #155724; font-weight: bold;'
                    elif '🔴 OUT OF PROTOCOL' in cell_str:
                        style = 'background-color: #f5c6cb; color: #721c24; font-weight: bold; border: 2px solid #dc3545;'
                    elif '❌ Screen Fail' in cell_str:
                        style = 'background-color: #f8d7da; color: #721c24; font-weight: bold;'
                    elif "Visit " in cell_str and not any(symbol in cell_str for symbol in ["✅", "🔴", "❌"]):  # Scheduled
                        style = 'background-color: #e2e3e5; color: #383d41; font-weight: normal;'
                    elif cell_str in ["+", "-"]:  # Tolerance periods - different from weekends
                        style = 'background-color: #f1f5f9; color: #64748b; font-style: italic; font-size: 0.9em;'

                styles.append(style)

            return styles

    try:
        styled_df = display_with_header.style.apply(highlight_with_header_fixed, axis=1)
        
        # Add month separators by modifying the HTML
        html_table_base = styled_df.to_html(escape=False)

        # Add month separators in the HTML by finding month boundaries
        html_lines = html_table_base.split('\n')
        modified_html_lines = []

        prev_month = None
        for i, line in enumerate(html_lines):
            # Check if this is a data row with a date
            if '<td>' in line and len(html_lines) > i+1:
                # Try to extract date from the line
                date_pattern = r'<td>(\d{4}-\d{2}-\d{2})</td>'
                match = re.search(date_pattern, line)
                if match:
                    try:
                        date_obj = pd.to_datetime(match.group(1))
                        current_month = date_obj.to_period('M')

                        # Add separator line if month changed
                        if prev_month is not None and current_month != prev_month:
                            # Count columns for proper separator
                            col_count = line.count('<td>')
                            separator_line = f'<tr style="border-top: 3px solid #3b82f6; background-color: #eff6ff;"><td colspan="{col_count}" style="text-align: center; font-weight: bold; color: #1e40af; padding: 2px;">{current_month}</td></tr>'
                            modified_html_lines.append(separator_line)

                        prev_month = current_month
                    except:
                        pass

            modified_html_lines.append(line)

        html_table_with_separators = '\n'.join(modified_html_lines)

        html_table = f"""
        <div style='max-height: 700px; overflow: auto; border: 1px solid #ddd;'>
            {html_table_with_separators}
        </div>
        """
        components.html(html_table, height=720, scrolling=True)
    except Exception as e:
        st.write(f"Styling error: {e}")
        st.dataframe(display_with_header, use_container_width=True)

    if excluded_visits and len(excluded_visits) > 0:
        st.warning("Some visits were excluded due to screen failure:")
        st.dataframe(pd.DataFrame(excluded_visits))

def display_site_statistics(site_summary_df):
    st.subheader("Site Summary")
    st.dataframe(site_summary_df, use_container_width=True)

def display_monthly_income_tables(visits_df):
    """Display monthly income analysis with tables only - NO CHARTS"""
    st.subheader("📊 Monthly Income Analysis")

    # Filter for relevant visits (exclude tolerance periods) - updated for new emoji
    financial_df = visits_df[
        (visits_df['Visit'].str.startswith("✅")) |
        (visits_df['Visit'].str.startswith("❌ Screen Fail")) |
        (visits_df['Visit'].str.startswith("🔴")) |
        (visits_df['Visit'].str.contains('Visit', na=False) & (~visits_df.get('IsActual', False)))
    ].copy()

    if not financial_df.empty:
        financial_df['MonthYear'] = financial_df['Date'].dt.to_period('M')
        financial_df['Quarter'] = financial_df['Date'].dt.quarter
        financial_df['Year'] = financial_df['Date'].dt.year
        financial_df['QuarterYear'] = financial_df['Year'].astype(str) + '-Q' + financial_df['Quarter'].astype(str)

        # Add financial year calculation
        financial_df['FinancialYear'] = financial_df['Date'].apply(
            lambda d: f"{d.year}-{d.year+1}" if d.month >= 4 else f"{d.year-1}-{d.year}"
        )

        # Monthly analysis with financial year totals
        monthly_income_by_site = financial_df.groupby(['SiteofVisit', 'MonthYear'])['Payment'].sum().reset_index()
        if not monthly_income_by_site.empty:
            monthly_pivot = monthly_income_by_site.pivot(index='MonthYear', columns='SiteofVisit', values='Payment').fillna(0)
            monthly_pivot['Total'] = monthly_pivot.sum(axis=1)

            # Add financial year totals to monthly data
            fy_monthly_totals = []
            for fy in sorted(financial_df['FinancialYear'].unique()):
                fy_data = financial_df[financial_df['FinancialYear'] == fy]
                fy_income_by_site = fy_data.groupby('SiteofVisit')['Payment'].sum()

                fy_row = {}
                for site in monthly_pivot.columns:
                    if site == 'Total':
                        fy_row[site] = fy_income_by_site.sum()
                    else:
                        fy_row[site] = fy_income_by_site.get(site, 0)

                fy_monthly_totals.append((f"FY {fy}", fy_row))

            # Quarterly analysis with financial year totals  
            quarterly_income_by_site = financial_df.groupby(['SiteofVisit', 'QuarterYear'])['Payment'].sum().reset_index()
            if not quarterly_income_by_site.empty:
                quarterly_pivot = quarterly_income_by_site.pivot(index='QuarterYear', columns='SiteofVisit', values='Payment').fillna(0)
                quarterly_pivot['Total'] = quarterly_pivot.sum(axis=1)

                # Display financial tables with FY totals
                col1, col2 = st.columns(2)

                with col1:
                    st.write("**Monthly Income by Visit Site**")
                    monthly_display = monthly_pivot.copy()
                    monthly_display.index = monthly_display.index.astype(str)

                    # Format currency
                    for col in monthly_display.columns:
                        monthly_display[col] = monthly_display[col].apply(lambda x: f"£{x:,.2f}" if x != 0 else "£0.00")

                    st.dataframe(monthly_display, use_container_width=True)

                    # Add financial year totals for monthly
                    if fy_monthly_totals:
                        st.write("**Financial Year Totals (Monthly)**")
                        fy_monthly_data = []
                        for fy_name, fy_row in fy_monthly_totals:
                            formatted_row = {"Financial Year": fy_name}
                            for col, val in fy_row.items():
                                formatted_row[col] = f"£{val:,.2f}" if val != 0 else "£0.00"
                            fy_monthly_data.append(formatted_row)

                        fy_monthly_df = pd.DataFrame(fy_monthly_data)
                        st.dataframe(fy_monthly_df, use_container_width=True)

                with col2:
                    st.write("**Quarterly Income by Visit Site**")
                    quarterly_display = quarterly_pivot.copy()

                    # Format currency
                    for col in quarterly_display.columns:
                        quarterly_display[col] = quarterly_display[col].apply(lambda x: f"£{x:,.2f}" if x != 0 else "£0.00")

                    st.dataframe(quarterly_display, use_container_width=True)

def display_quarterly_profit_sharing_tables(financial_df, patients_df):
    """Display quarterly profit sharing analysis with tables and calculations - NO CHARTS"""
    st.subheader("📊 Quarterly Profit Sharing Analysis")

    # Weighting adjustment button
    if st.button("⚙️ Adjust Profit Sharing Weights", use_container_width=False):
        st.session_state.show_weights_form = True

    # Initialize default weights
    if 'list_weight' not in st.session_state:
        st.session_state.list_weight = 35
    if 'work_weight' not in st.session_state:
        st.session_state.work_weight = 35
    if 'recruitment_weight' not in st.session_state:
        st.session_state.recruitment_weight = 30

    # Modal for weight adjustment
    if st.session_state.get('show_weights_form', False):
        st.write("**Adjust Profit Sharing Weights**")
        st.write("Current Formula: List Sizes + Work Done + Patient Recruitment = 100%")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            new_list_weight = st.slider("List Size %", 0, 100, st.session_state.list_weight, key="list_weight_slider")
        with col2:
            new_work_weight = st.slider("Work Done %", 0, 100, st.session_state.work_weight, key="work_weight_slider")
        with col3:
            new_recruitment_weight = st.slider("Recruitment %", 0, 100, st.session_state.recruitment_weight, key="recruitment_weight_slider")
        
        total_weight = new_list_weight + new_work_weight + new_recruitment_weight
        
        if total_weight == 100:
            st.success(f"✅ Total: {total_weight}% (Perfect!)")
        else:
            st.error(f"❌ Total: {total_weight}% - Must equal 100%")
        
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

    # Use current weights from session state
    list_weight = st.session_state.list_weight / 100
    work_weight = st.session_state.work_weight / 100
    recruitment_weight = st.session_state.recruitment_weight / 100

    # Display current weights
    st.info(f"**Current Weights:** List Sizes {st.session_state.list_weight}% • Work Done {st.session_state.work_weight}% • Patient Recruitment {st.session_state.recruitment_weight}%")

    # Fixed list sizes and calculations using current weights
    ashfields_list_size = 28500
    kiltearn_list_size = 12500
    total_list_size = ashfields_list_size + kiltearn_list_size
    ashfields_list_ratio = ashfields_list_size / total_list_size
    kiltearn_list_ratio = kiltearn_list_size / total_list_size

    # Create quarterly profit sharing analysis
    quarters = sorted(financial_df['QuarterYear'].unique()) if 'QuarterYear' in financial_df.columns else []
    financial_years = sorted(financial_df['FinancialYear'].unique()) if 'FinancialYear' in financial_df.columns else []

    if len(quarters) > 0 and len(financial_years) > 0:
        # Quarterly ratios calculation
        quarterly_ratios = []

        for quarter in quarters:
            quarter_data = financial_df[financial_df['QuarterYear'] == quarter]
            
            if len(quarter_data) == 0:
                continue
            
            # Work done ratios for this quarter
            quarter_site_work = quarter_data.groupby('SiteofVisit').size()
            quarter_total_work = quarter_site_work.sum()
            
            q_ashfields_work_ratio = quarter_site_work.get('Ashfields', 0) / quarter_total_work if quarter_total_work > 0 else 0
            q_kiltearn_work_ratio = quarter_site_work.get('Kiltearn', 0) / quarter_total_work if quarter_total_work > 0 else 0
            
            # Recruitment ratios for this quarter (patients recruited)
            quarter_patients = patients_df[patients_df['StartDate'].dt.to_period('Q').astype(str) == quarter.replace('-Q', 'Q')]
            quarter_recruitment = quarter_patients.groupby('Site')['PatientID'].count()
            quarter_total_recruitment = quarter_recruitment.sum()
            
            q_ashfields_recruitment_ratio = quarter_recruitment.get('Ashfields', 0) / quarter_total_recruitment if quarter_total_recruitment > 0 else 0
            q_kiltearn_recruitment_ratio = quarter_recruitment.get('Kiltearn', 0) / quarter_total_recruitment if quarter_total_recruitment > 0 else 0
            
            # Combined ratios using current weights
            q_ashfields_final_ratio = (ashfields_list_ratio * list_weight + 
                                     q_ashfields_work_ratio * work_weight + 
                                     q_ashfields_recruitment_ratio * recruitment_weight)
            q_kiltearn_final_ratio = (kiltearn_list_ratio * list_weight + 
                                    q_kiltearn_work_ratio * work_weight + 
                                    q_kiltearn_recruitment_ratio * recruitment_weight)
            
            # Normalize
            q_total_ratio = q_ashfields_final_ratio + q_kiltearn_final_ratio
            if q_total_ratio > 0:
                q_ashfields_final_ratio = q_ashfields_final_ratio / q_total_ratio
                q_kiltearn_final_ratio = q_kiltearn_final_ratio / q_total_ratio
            
            # Calculate quarter income
            quarter_total_income = quarter_data['Payment'].sum()
            ashfields_quarter_share_amount = quarter_total_income * q_ashfields_final_ratio
            kiltearn_quarter_share_amount = quarter_total_income * q_kiltearn_final_ratio
            
            # Extract financial year for sorting
            year_part = int(quarter.split('-Q')[0])
            quarter_num = int(quarter.split('-Q')[1])
            fy_year = year_part if quarter_num >= 2 else year_part - 1  # Q2,Q3,Q4 = same FY, Q1 = previous FY
            
            quarterly_ratios.append({
                'Period': quarter,
                'Financial Year': fy_year,
                'Type': 'Quarter',
                'Total Visits': quarter_total_work,
                'Ashfields Visits': quarter_site_work.get('Ashfields', 0),
                'Kiltearn Visits': quarter_site_work.get('Kiltearn', 0),
                'Ashfields Patients': quarter_recruitment.get('Ashfields', 0),
                'Kiltearn Patients': quarter_recruitment.get('Kiltearn', 0),
                'Ashfields Share': f"{q_ashfields_final_ratio:.1%}",
                'Kiltearn Share': f"{q_kiltearn_final_ratio:.1%}",
                'Total Income': f"£{quarter_total_income:,.2f}",
                'Ashfields Income': f"£{ashfields_quarter_share_amount:,.2f}",
                'Kiltearn Income': f"£{kiltearn_quarter_share_amount:,.2f}"
            })

        # Add financial year summaries
        for fy in financial_years:
            fy_data = financial_df[financial_df['FinancialYear'] == fy]
            
            if len(fy_data) == 0:
                continue
            
            # Work done ratios for this financial year
            fy_site_work = fy_data.groupby('SiteofVisit').size()
            fy_total_work = fy_site_work.sum()
            
            fy_ashfields_work_ratio = fy_site_work.get('Ashfields', 0) / fy_total_work if fy_total_work > 0 else 0
            fy_kiltearn_work_ratio = fy_site_work.get('Kiltearn', 0) / fy_total_work if fy_total_work > 0 else 0
            
            # Recruitment ratios for this financial year
            fy_start_date = pd.to_datetime(f"{fy.split('-')[0]}-04-01")
            fy_end_date = pd.to_datetime(f"{fy.split('-')[1]}-03-31")
            fy_patients = patients_df[(patients_df['StartDate'] >= fy_start_date) & (patients_df['StartDate'] <= fy_end_date)]
            fy_recruitment = fy_patients.groupby('Site')['PatientID'].count()
            fy_total_recruitment = fy_recruitment.sum()
            
            fy_ashfields_recruitment_ratio = fy_recruitment.get('Ashfields', 0) / fy_total_recruitment if fy_total_recruitment > 0 else 0
            fy_kiltearn_recruitment_ratio = fy_recruitment.get('Kiltearn', 0) / fy_total_recruitment if fy_total_recruitment > 0 else 0
            
            # Combined ratios using current weights
            fy_ashfields_final_ratio = (ashfields_list_ratio * list_weight + 
                                      fy_ashfields_work_ratio * work_weight + 
                                      fy_ashfields_recruitment_ratio * recruitment_weight)
            fy_kiltearn_final_ratio = (kiltearn_list_ratio * list_weight + 
                                     fy_kiltearn_work_ratio * work_weight + 
                                     fy_kiltearn_recruitment_ratio * recruitment_weight)

            # Normalize
            fy_total_ratio = fy_ashfields_final_ratio + fy_kiltearn_final_ratio
            if fy_total_ratio > 0:
                fy_ashfields_final_ratio = fy_ashfields_final_ratio / fy_total_ratio
                fy_kiltearn_final_ratio = fy_kiltearn_final_ratio / fy_total_ratio

            # Calculate total financial year income
            fy_total_income = fy_data['Payment'].sum()

            # Calculate income based on profit sharing percentages
            ashfields_fy_share_amount = fy_total_income * fy_ashfields_final_ratio
            kiltearn_fy_share_amount = fy_total_income * fy_kiltearn_final_ratio

            quarterly_ratios.append({
                'Period': f"FY {fy}",
                'Financial Year': int(fy.split('-')[0]),
                'Type': 'Financial Year',
                'Total Visits': fy_total_work,
                'Ashfields Visits': fy_site_work.get('Ashfields', 0),
                'Kiltearn Visits': fy_site_work.get('Kiltearn', 0),
                'Ashfields Patients': fy_recruitment.get('Ashfields', 0) if not fy_recruitment.empty else 0,
                'Kiltearn Patients': fy_recruitment.get('Kiltearn', 0) if not fy_recruitment.empty else 0,
                'Ashfields Share': f"{fy_ashfields_final_ratio:.1%}",
                'Kiltearn Share': f"{fy_kiltearn_final_ratio:.1%}",
                'Total Income': f"£{fy_total_income:,.2f}",
                'Ashfields Income': f"£{ashfields_fy_share_amount:,.2f}",
                'Kiltearn Income': f"£{kiltearn_fy_share_amount:,.2f}"
            })

        if quarterly_ratios:
            # Sort by financial year and type (FY summaries at end of each year)
            quarterly_ratios.sort(key=lambda x: (x['Financial Year'], x['Type'] == 'Financial Year', x['Period']))

            quarterly_df = pd.DataFrame(quarterly_ratios)

            # Style the dataframe to highlight financial year rows
            def highlight_fy_rows(row):
                if row['Type'] == 'Financial Year':
                    return ['background-color: #e6f3ff; font-weight: bold;'] * len(row)
                else:
                    return [''] * len(row)

            styled_quarterly_df = quarterly_df.style.apply(highlight_fy_rows, axis=1)

            st.write("**Quarterly Profit Sharing Analysis**")
            st.dataframe(styled_quarterly_df, use_container_width=True)

            # Analysis summary
            st.write("**Analysis Notes:**")
            st.info(f"""
            **Profit Sharing Formula:** 
            - List Sizes: {st.session_state.list_weight}% (Ashfields: {ashfields_list_ratio:.1%}, Kiltearn: {kiltearn_list_ratio:.1%})
            - Work Done: {st.session_state.work_weight}% (Based on actual visits completed per quarter)
            - Patient Recruitment: {st.session_state.recruitment_weight}% (Based on patients recruited per quarter)
            
            **Highlighted rows** show Financial Year totals. Individual quarters show the detailed breakdown.
            """)

    else:
        st.warning("No quarterly data available for analysis. Upload visit data with dates to generate quarterly profit sharing calculations.")

    # Add detailed ratio breakdowns for bookkeepers
    if len(quarters) > 0 and len(financial_years) > 0:
        st.divider()
        display_profit_sharing_ratio_breakdowns(financial_df, patients_df)

def display_profit_sharing_ratio_breakdowns(financial_df, patients_df):
    """Display detailed ratio breakdowns for profit sharing calculations"""
    st.subheader("📊 Profit Sharing Ratio Breakdowns")
    
    # Use current weights from session state
    list_weight = st.session_state.list_weight / 100
    work_weight = st.session_state.work_weight / 100
    recruitment_weight = st.session_state.recruitment_weight / 100
    
    # Fixed list sizes
    ashfields_list_size = 28500
    kiltearn_list_size = 12500
    total_list_size = ashfields_list_size + kiltearn_list_size
    ashfields_list_ratio = ashfields_list_size / total_list_size
    kiltearn_list_ratio = kiltearn_list_size / total_list_size
    
    st.info(f"**Formula:** List Sizes {st.session_state.list_weight}% + Work Done {st.session_state.work_weight}% + Patient Recruitment {st.session_state.recruitment_weight}%")
    st.info(f"**Fixed List Ratios:** Ashfields {ashfields_list_ratio:.1%} ({ashfields_list_size:,}) | Kiltearn {kiltearn_list_ratio:.1%} ({kiltearn_list_size:,})")
    
    # Get all periods
    quarters = sorted(financial_df['QuarterYear'].unique()) if 'QuarterYear' in financial_df.columns else []
    financial_years = sorted(financial_df['FinancialYear'].unique()) if 'FinancialYear' in financial_df.columns else []
    
    # Monthly breakdown
    if not financial_df.empty:
        financial_df['MonthYear'] = financial_df['Date'].dt.to_period('M')
        months = sorted(financial_df['MonthYear'].unique())
        
        st.write("**Monthly Ratio Breakdowns**")
        
        monthly_ratio_data = []
        
        for month in months:
            month_data = financial_df[financial_df['MonthYear'] == month]
            
            if len(month_data) == 0:
                continue
            
            # Work done ratios for this month
            month_site_work = month_data.groupby('SiteofVisit').size()
            month_total_work = month_site_work.sum()
            
            ashfields_work_ratio = month_site_work.get('Ashfields', 0) / month_total_work if month_total_work > 0 else 0
            kiltearn_work_ratio = month_site_work.get('Kiltearn', 0) / month_total_work if month_total_work > 0 else 0
            
            # Recruitment ratios for this month
            month_patients = patients_df[patients_df['StartDate'].dt.to_period('M') == month]
            month_recruitment = month_patients.groupby('Site')['PatientID'].count()
            month_total_recruitment = month_recruitment.sum()
            
            ashfields_recruitment_ratio = month_recruitment.get('Ashfields', 0) / month_total_recruitment if month_total_recruitment > 0 else 0
            kiltearn_recruitment_ratio = month_recruitment.get('Kiltearn', 0) / month_total_recruitment if month_total_recruitment > 0 else 0
            
            # Combined ratios using current weights
            ashfields_final_ratio = (ashfields_list_ratio * list_weight + 
                                   ashfields_work_ratio * work_weight + 
                                   ashfields_recruitment_ratio * recruitment_weight)
            kiltearn_final_ratio = (kiltearn_list_ratio * list_weight + 
                                  kiltearn_work_ratio * work_weight + 
                                  kiltearn_recruitment_ratio * recruitment_weight)
            
            # Normalize
            total_ratio = ashfields_final_ratio + kiltearn_final_ratio
            if total_ratio > 0:
                ashfields_final_ratio = ashfields_final_ratio / total_ratio
                kiltearn_final_ratio = kiltearn_final_ratio / total_ratio
            
            monthly_ratio_data.append({
                'Month': str(month),
                'Ashfields List %': f"{ashfields_list_ratio:.1%}",
                'Kiltearn List %': f"{kiltearn_list_ratio:.1%}",
                'Ashfields Work %': f"{ashfields_work_ratio:.1%}",
                'Kiltearn Work %': f"{kiltearn_work_ratio:.1%}",
                'Ashfields Recruit %': f"{ashfields_recruitment_ratio:.1%}",
                'Kiltearn Recruit %': f"{kiltearn_recruitment_ratio:.1%}",
                'Ashfields Final %': f"{ashfields_final_ratio:.1%}",
                'Kiltearn Final %': f"{kiltearn_final_ratio:.1%}",
                'Total Visits': month_total_work,
                'Total Recruits': month_total_recruitment
            })
        
        if monthly_ratio_data:
            monthly_df = pd.DataFrame(monthly_ratio_data)
            st.dataframe(monthly_df, use_container_width=True)
    
    # Quarterly breakdown
    st.write("**Quarterly Ratio Breakdowns**")
    
    quarterly_ratio_data = []
    
    for quarter in quarters:
        quarter_data = financial_df[financial_df['QuarterYear'] == quarter]
        
        if len(quarter_data) == 0:
            continue
        
        # Work done ratios for this quarter
        quarter_site_work = quarter_data.groupby('SiteofVisit').size()
        quarter_total_work = quarter_site_work.sum()
        
        ashfields_work_ratio = quarter_site_work.get('Ashfields', 0) / quarter_total_work if quarter_total_work > 0 else 0
        kiltearn_work_ratio = quarter_site_work.get('Kiltearn', 0) / quarter_total_work if quarter_total_work > 0 else 0
        
        # Recruitment ratios for this quarter
        quarter_patients = patients_df[patients_df['StartDate'].dt.to_period('Q').astype(str) == quarter.replace('-Q', 'Q')]
        quarter_recruitment = quarter_patients.groupby('Site')['PatientID'].count()
        quarter_total_recruitment = quarter_recruitment.sum()
        
        ashfields_recruitment_ratio = quarter_recruitment.get('Ashfields', 0) / quarter_total_recruitment if quarter_total_recruitment > 0 else 0
        kiltearn_recruitment_ratio = quarter_recruitment.get('Kiltearn', 0) / quarter_total_recruitment if quarter_total_recruitment > 0 else 0
        
        # Combined ratios using current weights
        ashfields_final_ratio = (ashfields_list_ratio * list_weight + 
                               ashfields_work_ratio * work_weight + 
                               ashfields_recruitment_ratio * recruitment_weight)
        kiltearn_final_ratio = (kiltearn_list_ratio * list_weight + 
                              kiltearn_work_ratio * work_weight + 
                              kiltearn_recruitment_ratio * recruitment_weight)
        
        # Normalize
        total_ratio = ashfields_final_ratio + kiltearn_final_ratio
        if total_ratio > 0:
            ashfields_final_ratio = ashfields_final_ratio / total_ratio
            kiltearn_final_ratio = kiltearn_final_ratio / total_ratio
        
        quarterly_ratio_data.append({
            'Quarter': quarter,
            'Ashfields List %': f"{ashfields_list_ratio:.1%}",
            'Kiltearn List %': f"{kiltearn_list_ratio:.1%}",
            'Ashfields Work %': f"{ashfields_work_ratio:.1%}",
            'Kiltearn Work %': f"{kiltearn_work_ratio:.1%}",
            'Ashfields Recruit %': f"{ashfields_recruitment_ratio:.1%}",
            'Kiltearn Recruit %': f"{kiltearn_recruitment_ratio:.1%}",
            'Ashfields Final %': f"{ashfields_final_ratio:.1%}",
            'Kiltearn Final %': f"{kiltearn_final_ratio:.1%}",
            'Total Visits': quarter_total_work,
            'Total Recruits': quarter_total_recruitment
        })
    
    if quarterly_ratio_data:
        quarterly_df = pd.DataFrame(quarterly_ratio_data)
        st.dataframe(quarterly_df, use_container_width=True)
    
    # Financial Year breakdown
    st.write("**Financial Year Ratio Breakdowns**")
    
    fy_ratio_data = []
    
    for fy in financial_years:
        fy_data = financial_df[financial_df['FinancialYear'] == fy]
        
        if len(fy_data) == 0:
            continue
        
        # Work done ratios for this financial year
        fy_site_work = fy_data.groupby('SiteofVisit').size()
        fy_total_work = fy_site_work.sum()
        
        ashfields_work_ratio = fy_site_work.get('Ashfields', 0) / fy_total_work if fy_total_work > 0 else 0
        kiltearn_work_ratio = fy_site_work.get('Kiltearn', 0) / fy_total_work if fy_total_work > 0 else 0
        
        # Recruitment ratios for this financial year
        fy_start_date = pd.to_datetime(f"{fy.split('-')[0]}-04-01")
        fy_end_date = pd.to_datetime(f"{fy.split('-')[1]}-03-31")
        fy_patients = patients_df[(patients_df['StartDate'] >= fy_start_date) & (patients_df['StartDate'] <= fy_end_date)]
        fy_recruitment = fy_patients.groupby('Site')['PatientID'].count()
        fy_total_recruitment = fy_recruitment.sum()
        
        ashfields_recruitment_ratio = fy_recruitment.get('Ashfields', 0) / fy_total_recruitment if fy_total_recruitment > 0 else 0
        kiltearn_recruitment_ratio = fy_recruitment.get('Kiltearn', 0) / fy_total_recruitment if fy_total_recruitment > 0 else 0
        
        # Combined ratios using current weights
        ashfields_final_ratio = (ashfields_list_ratio * list_weight + 
                               ashfields_work_ratio * work_weight + 
                               ashfields_recruitment_ratio * recruitment_weight)
        kiltearn_final_ratio = (kiltearn_list_ratio * list_weight + 
                              kiltearn_work_ratio * work_weight + 
                              kiltearn_recruitment_ratio * recruitment_weight)
        
        # Normalize
        total_ratio = ashfields_final_ratio + kiltearn_final_ratio
        if total_ratio > 0:
            ashfields_final_ratio = ashfields_final_ratio / total_ratio
            kiltearn_final_ratio = kiltearn_final_ratio / total_ratio
        
        fy_ratio_data.append({
            'Financial Year': f"FY {fy}",
            'Ashfields List %': f"{ashfields_list_ratio:.1%}",
            'Kiltearn List %': f"{kiltearn_list_ratio:.1%}",
            'Ashfields Work %': f"{ashfields_work_ratio:.1%}",
            'Kiltearn Work %': f"{kiltearn_work_ratio:.1%}",
            'Ashfields Recruit %': f"{ashfields_recruitment_ratio:.1%}",
            'Kiltearn Recruit %': f"{kiltearn_recruitment_ratio:.1%}",
            'Ashfields Final %': f"{ashfields_final_ratio:.1%}",
            'Kiltearn Final %': f"{kiltearn_final_ratio:.1%}",
            'Total Visits': fy_total_work,
            'Total Recruits': fy_total_recruitment
        })
    
    if fy_ratio_data:
        fy_df = pd.DataFrame(fy_ratio_data)
        st.dataframe(fy_df, use_container_width=True)
    
    # Explanation for bookkeepers
    st.info("""
    **For Bookkeepers:**
    - **List %**: Fixed ratios based on practice list sizes (never changes)
    - **Work %**: Variable ratios based on actual visits completed in the period
    - **Recruit %**: Variable ratios based on patients recruited in the period
    - **Final %**: Combined weighted percentage for profit sharing calculations
    - Apply the Final % to the total income for each period to determine profit share amounts
    """)

def display_download_buttons(calendar_df, site_column_mapping, unique_sites):
    """Display comprehensive download options with Excel formatting"""
    st.subheader("💾 Download Options")

    # Excel exports with formatting
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

        excel_financial_cols = ["Daily Total", "Monthly Total", "FY Total"] + [c for c in calendar_df.columns if "Income" in c]
        excel_full_df = calendar_df[final_ordered_columns + [col for col in excel_financial_cols if col in calendar_df.columns]].copy()

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

            # Add site headers
            for col_idx, col_name in enumerate(excel_full_df.columns, 1):
                col_letter = get_column_letter(col_idx)
                if col_name not in ["Date", "Day"] and not any(x in col_name for x in ["Income", "Total"]):
                    for site in unique_sites:
                        if col_name in site_column_mapping.get(site, []):
                            ws[f"{col_letter}1"] = site
                            ws[f"{col_letter}1"].font = Font(bold=True, size=12)
                            ws[f"{col_letter}1"].fill = PatternFill(start_color="FFE6F3FF", end_color="FFE6F3FF", fill_type="solid")
                            ws[f"{col_letter}1"].alignment = Alignment(horizontal="center")
                            break

            # Auto-adjust column widths
            for idx, col in enumerate(excel_full_df.columns, 1):
                col_letter = get_column_letter(idx)
                max_length = max([len(str(cell)) if cell is not None else 0 for cell in excel_full_df[col].tolist()] + [len(col)])
                ws.column_dimensions[col_letter].width = max(10, max_length + 2)

        st.download_button(
            "💰 Excel with Finances & Site Headers",
            data=output.getvalue(),
            file_name="VisitCalendar_WithFinances_SiteGrouped.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except ImportError:
        st.warning("Excel formatting unavailable - install openpyxl for enhanced features")
        buf = io.BytesIO()
        calendar_df.to_excel(buf, index=False)
        st.download_button("💾 Download Basic Excel", data=buf.getvalue(), file_name="VisitCalendar.xlsx")
