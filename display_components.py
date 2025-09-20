import streamlit as st
import pandas as pd
import io
from datetime import date  # FIX: Added missing import
import re
import streamlit.components.v1 as components

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
        - Light blue background = Month end (softer highlighting)
        - Dark blue background = Financial year end (31 March)
        - Gray background = Weekend
        - Blue separator lines = Month boundaries (screen only)
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

    # Create styling function with improved colors matching the working version
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

                    # FIX: Visit-specific color coding with consistent emoji matching
                    if '✅ Visit' in cell_str:
                        style = 'background-color: #d4edda; color: #155724; font-weight: bold;'
                    elif '⚠️ Visit' in cell_str:
                        style = 'background-color: #fff3cd; color: #856404; font-weight: bold;'
                    elif '❌ Screen Fail' in cell_str:
                        style = 'background-color: #f8d7da; color: #721c24; font-weight: bold;'
                    elif "Visit " in cell_str and not any(symbol in cell_str for symbol in ["✅", "⚠️", "❌"]):  # Scheduled
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

def display_financial_analysis(stats, visits_df):
    st.subheader("💰 Financial Analysis")

    # Filter for relevant visits (exclude tolerance periods) with consistent emoji symbols
    financial_df = visits_df[
        (visits_df['Visit'].str.startswith("✅")) |
        (visits_df['Visit'].str.startswith("❌ Screen Fail")) |
        (visits_df['Visit'].str.startswith("⚠️")) |
        (visits_df['Visit'].str.contains('Visit', na=False) & (~visits_df.get('IsActual', False)))
    ].copy()

    actual_financial = financial_df[financial_df.get('IsActual', False)]
    scheduled_financial = financial_df[~financial_df.get('IsActual', True)]

    if not actual_financial.empty:
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            actual_income = actual_financial['Payment'].sum()
            st.metric("Actual Income (Completed)", f"£{actual_income:,.2f}")
        with col2:
            scheduled_income = scheduled_financial['Payment'].sum()
            st.metric("Scheduled Income (Pending)", f"£{scheduled_income:,.2f}")
        with col3:
            total_income = actual_income + scheduled_income
            st.metric("Total Income", f"£{total_income:,.2f}")
        with col4:
            screen_fail_count = len(actual_financial[actual_financial.get('IsScreenFail', False)])
            st.metric("Screen Failures", screen_fail_count)

        # FIX: Safe division for completion rate
        try:
            completion_rate = (len(actual_financial) / len(financial_df)) * 100 if len(financial_df) > 0 else 0
            st.metric("Visit Completion Rate", f"{completion_rate:.1f}%")
        except (ZeroDivisionError, TypeError):
            st.metric("Visit Completion Rate", "0.0%")
    else:
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total Visits", stats.get("total_visits", 0))
        with col2:
            st.metric("Total Income", f"£{stats.get('total_income', 0):,.2f}")

    # Monthly income analysis
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
        quarterly_pivot = quarterly_income_by_site.pivot(index='QuarterYear', columns='SiteofVisit', values='Payment').fillna(0)
        quarterly_pivot['Total'] = quarterly_pivot.sum(axis=1)

        # Monthly Income Chart
        st.subheader("📊 Monthly Income Chart")
        monthly_chart_data = monthly_pivot[[col for col in monthly_pivot.columns if col != 'Total']]
        monthly_chart_data.index = monthly_chart_data.index.astype(str)
        st.bar_chart(monthly_chart_data)

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
                st.write("**Financial Year Totals**")
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

def display_site_statistics(site_summary_df):
    st.subheader("Site Summary")
    st.dataframe(site_summary_df, use_container_width=True)

def display_quarterly_profit_sharing(financial_df, patients_df):
    """Display quarterly profit sharing analysis with adjustable weights"""
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
        try:
            @st.dialog("Adjust Profit Sharing Weights")
            def weights_adjustment_form():
                st.write("**Current Formula:** List Sizes + Work Done + Patient Recruitment = 100%")
                st.write("Adjust the weightings below (must total 100%):")

                col1, col2, col3 = st.columns(3)

                with col1:
                    st.write("**List Sizes Weight**")
                    new_list_weight = st.slider(
                        "List Size %", 
                        min_value=0, 
                        max_value=100, 
                        value=st.session_state.list_weight,
                        step=5,
                        key="list_slider"
                    )
                    list_input = st.number_input(
                        "Or enter exact %:",
                        min_value=0,
                        max_value=100,
                        value=new_list_weight,
                        step=1,
                        key="list_input"
                    )

                with col2:
                    st.write("**Work Done Weight**")
                    new_work_weight = st.slider(
                        "Work Done %", 
                        min_value=0, 
                        max_value=100, 
                        value=st.session_state.work_weight,
                        step=5,
                        key="work_slider"
                    )
                    work_input = st.number_input(
                        "Or enter exact %:",
                        min_value=0,
                        max_value=100,
                        value=new_work_weight,
                        step=1,
                        key="work_input"
                    )

                with col3:
                    st.write("**Patient Recruitment Weight**")
                    new_recruitment_weight = st.slider(
                        "Recruitment %", 
                        min_value=0, 
                        max_value=100, 
                        value=st.session_state.recruitment_weight,
                        step=5,
                        key="recruitment_slider"
                    )
                    recruitment_input = st.number_input(
                        "Or enter exact %:",
                        min_value=0,
                        max_value=100,
                        value=new_recruitment_weight,
                        step=1,
                        key="recruitment_input"
                    )

                # Use input values if they differ from sliders
                final_list = list_input
                final_work = work_input  
                final_recruitment = recruitment_input

                # Calculate total and validate
                total_weight = final_list + final_work + final_recruitment

                # Show current total with color coding
                if total_weight == 100:
                    st.success(f"✅ Total: {total_weight}% (Perfect!)")
                elif total_weight < 100:
                    st.warning(f"⚠️ Total: {total_weight}% (Need {100 - total_weight}% more)")
                else:
                    st.error(f"❌ Total: {total_weight}% (Reduce by {total_weight - 100}%)")

                # Show preview of what this means
                st.write("**Weight Breakdown:**")
                preview_data = {
                    "Component": ["List Sizes", "Work Done", "Patient Recruitment"],
                    "Current %": [f"{st.session_state.list_weight}%", f"{st.session_state.work_weight}%", f"{st.session_state.recruitment_weight}%"],
                    "New %": [f"{final_list}%", f"{final_work}%", f"{final_recruitment}%"],
                    "Change": [
                        f"{final_list - st.session_state.list_weight:+d}%",
                        f"{final_work - st.session_state.work_weight:+d}%", 
                        f"{final_recruitment - st.session_state.recruitment_weight:+d}%"
                    ]
                }
                preview_df = pd.DataFrame(preview_data)
                st.dataframe(preview_df, use_container_width=True)

                # Action buttons
                col1, col2, col3 = st.columns(3)

                with col1:
                    if st.button("✅ Apply Changes", 
                                disabled=(total_weight != 100),
                                use_container_width=True):
                        st.session_state.list_weight = final_list
                        st.session_state.work_weight = final_work
                        st.session_state.recruitment_weight = final_recruitment
                        st.session_state.show_weights_form = False
                        st.success("Weights updated!")
                        st.rerun()

                with col2:
                    if st.button("🔄 Reset to Default (35/35/30)", use_container_width=True):
                        st.session_state.list_weight = 35
                        st.session_state.work_weight = 35
                        st.session_state.recruitment_weight = 30
                        st.session_state.show_weights_form = False
                        st.success("Reset to default weights!")
                        st.rerun()

                with col3:
                    if st.button("❌ Cancel", use_container_width=True):
                        st.session_state.show_weights_form = False
                        st.rerun()

            weights_adjustment_form()
        except AttributeError:
            st.error("Modal dialogs require Streamlit version 1.28 or newer.")
            st.session_state.show_weights_form = False

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

    if len(quarters) > 0:
        quarterly_ratios = []

        # Process quarterly data
        for quarter in quarters:
            quarter_data = financial_df[financial_df['QuarterYear'] == quarter]

            if len(quarter_data) == 0:
                continue

            # Work done ratios for this quarter with safe division
            quarter_site_work = quarter_data.groupby('SiteofVisit').size()
            quarter_total_work = quarter_site_work.sum()

            # FIX: Safe division for ratios
            q_ashfields_work_ratio = quarter_site_work.get('Ashfields', 0) / quarter_total_work if quarter_total_work > 0 else 0
            q_kiltearn_work_ratio = quarter_site_work.get('Kiltearn', 0) / quarter_total_work if quarter_total_work > 0 else 0

            # Patient recruitment ratios for this quarter with safe division
            quarter_recruitment = quarter_data.groupby('PatientOrigin').agg({'PatientID': 'nunique'})
            quarter_total_patients = quarter_recruitment['PatientID'].sum()

            q_ashfields_recruitment_ratio = 0
            q_kiltearn_recruitment_ratio = 0
            if quarter_total_patients > 0:
                q_ashfields_recruitment_ratio = quarter_recruitment.loc['Ashfields', 'PatientID'] / quarter_total_patients if 'Ashfields' in quarter_recruitment.index else 0
                q_kiltearn_recruitment_ratio = quarter_recruitment.loc['Kiltearn', 'PatientID'] / quarter_total_patients if 'Kiltearn' in quarter_recruitment.index else 0

            # Calculate weighted ratios (list sizes remain constant)
            q_ashfields_final_ratio = (ashfields_list_ratio * list_weight + 
                                      q_ashfields_work_ratio * work_weight + 
                                      q_ashfields_recruitment_ratio * recruitment_weight)

            q_kiltearn_final_ratio = (kiltearn_list_ratio * list_weight + 
                                     q_kiltearn_work_ratio * work_weight + 
                                     q_kiltearn_recruitment_ratio * recruitment_weight)

            # Normalize to ensure they sum to 100%
            q_total_ratio = q_ashfields_final_ratio + q_kiltearn_final_ratio
            if q_total_ratio > 0:
                q_ashfields_final_ratio = q_ashfields_final_ratio / q_total_ratio
                q_kiltearn_final_ratio = q_kiltearn_final_ratio / q_total_ratio

            # Calculate quarterly income
            quarter_income = quarter_data['Payment'].sum()

            # Calculate profit sharing amounts
            ashfields_quarter_share_amount = quarter_income * q_ashfields_final_ratio
            kiltearn_quarter_share_amount = quarter_income * q_kiltearn_final_ratio

            # Get financial year for this quarter
            fy = quarter_data['FinancialYear'].iloc[0] if len(quarter_data) > 0 else ""

            quarterly_ratios.append({
                'Period': quarter,
                'Financial Year': fy,
                'Type': 'Quarter',
                'Total Visits': quarter_total_work,
                'Ashfields Visits': quarter_site_work.get('Ashfields', 0),
                'Kiltearn Visits': quarter_site_work.get('Kiltearn', 0),
                'Ashfields Patients': quarter_recruitment.loc['Ashfields', 'PatientID'] if 'Ashfields' in quarter_recruitment.index else 0,
                'Kiltearn Patients': quarter_recruitment.loc['Kiltearn', 'PatientID'] if 'Kiltearn' in quarter_recruitment.index else 0,
                'Ashfields Share': f"{q_ashfields_final_ratio:.1%}",
                'Kiltearn Share': f"{q_kiltearn_final_ratio:.1%}",
                'Total Income': f"£{quarter_income:,.2f}",
                'Ashfields Income': f"£{ashfields_quarter_share_amount:,.2f}",
                'Kiltearn Income': f"£{kiltearn_quarter_share_amount:,.2f}"
            })

        # Add financial year summaries with same safe division logic
        for fy in financial_years:
            fy_data = financial_df[financial_df['FinancialYear'] == fy]

            if len(fy_data) == 0:
                continue

            # Work done ratios for this financial year
            fy_site_work = fy_data.groupby('SiteofVisit').size()
            fy_total_work = fy_site_work.sum()

            fy_ashfields_work_ratio = fy_site_work.get('Ashfields', 0) / fy_total_work if fy_total_work > 0 else 0
            fy_kiltearn_work_ratio = fy_site_work.get('Kiltearn', 0) / fy_total_work if fy_total_work > 0 else 0

            # Patient recruitment ratios for this financial year
            fy_recruitment = fy_data.groupby('PatientOrigin').agg({'PatientID': 'nunique'})
            fy_total_patients = fy_recruitment['PatientID'].sum()

            fy_ashfields_recruitment_ratio = 0
            fy_kiltearn_recruitment_ratio = 0
            if fy_total_patients > 0:
                fy_ashfields_recruitment_ratio = fy_recruitment.loc['Ashfields', 'PatientID'] / fy_total_patients if 'Ashfields' in fy_recruitment.index else 0
                fy_kiltearn_recruitment_ratio = fy_recruitment.loc['Kiltearn', 'PatientID'] / fy_total_patients if 'Kiltearn' in fy_recruitment.index else 0

            # Calculate weighted ratios for financial year
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
                'Financial Year': fy,
                'Type': 'Financial Year',
                'Total Visits': fy_total_work,
                'Ashfields Visits': fy_site_work.get('Ashfields', 0),
                'Kiltearn Visits': fy_site_work.get('Kiltearn', 0),
                'Ashfields Patients': fy_recruitment.loc['Ashfields', 'PatientID'] if 'Ashfields' in fy_recruitment.index else 0,
                'Kiltearn Patients': fy_recruitment.loc['Kiltearn', 'PatientID'] if 'Kiltearn' in fy_recruitment.index else 0,
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
                    return ['background-color: #e6f3ff; font-weight: bold'] * len(row)
                else:
                    return [''] * len(row)

            styled_quarterly_df = quarterly_df.style.apply(highlight_fy_rows, axis=1)
            st.dataframe(styled_quarterly_df, use_container_width=True)

            # Visual chart of quarterly ratios (quarters only, not FY summaries)
            st.write("**Quarterly Profit Sharing Trends**")

            # Prepare chart data - quarters only
            chart_data = []
            for ratio in quarterly_ratios:
                if ratio['Type'] == 'Quarter':
                    # FIX: Safe percentage conversion
                    try:
                        ashfields_pct = float(ratio['Ashfields Share'].rstrip('%')) / 100
                        kiltearn_pct = float(ratio['Kiltearn Share'].rstrip('%')) / 100

                        chart_data.append({
                            'Quarter': ratio['Period'],
                            'Ashfields': ashfields_pct,
                            'Kiltearn': kiltearn_pct
                        })
                    except (ValueError, AttributeError):
                        continue

            if chart_data:
                chart_df = pd.DataFrame(chart_data).set_index('Quarter')
                st.bar_chart(chart_df)

            st.info("""
            **Analysis Notes:**
            - **Blue highlighted rows** = Financial Year totals (April to March)
            - Use **Financial Year ratios** for annual profit sharing decisions
            - **Total Income** = Combined clinical trial income from all studies
            - **Ashfields/Kiltearn Income** = Calculated profit share based on weighted formula (not raw income generation)
            - Quarterly ratios show seasonal variations within each financial year
            - List sizes remain constant; work done and recruitment vary by period
            - **Income Distribution:** Shows what each practice should receive according to the profit sharing formula
            """)
        else:
            st.warning("No quarterly data available for profit sharing analysis.")
    else:
        st.warning("No financial data available for quarterly analysis.")

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
