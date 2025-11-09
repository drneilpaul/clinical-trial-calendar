import streamlit as st
import pandas as pd
import io
from datetime import date
import re
import streamlit.components.v1 as components
from helpers import log_activity, generate_financial_year_options

def render_calendar_start_selector(years_back: int = 4):
    """
    Render a financial year selectbox for filtering the calendar view.
    
    Returns:
        dict: The selected option with keys label/start/end.
    """
    options = generate_financial_year_options(
        years_back=years_back, include_future=False, include_show_all=True
    )
    labels = [opt["label"] for opt in options]
    
    session_key = "calendar_start_year"
    default_index = 1 if len(labels) > 1 else 0
    
    # If Streamlit has a stale value that's no longer valid, clear it before rendering
    if session_key in st.session_state and st.session_state[session_key] not in labels:
        del st.session_state[session_key]
    
    selected_label = st.selectbox(
        "Calendar view from",
        labels,
        index=default_index,
        key=session_key,
        help="Filter the calendar to show visits from the selected financial year onward."
    )
    
    selected_option = next(opt for opt in options if opt["label"] == selected_label)
    st.session_state["calendar_start_selection"] = selected_option
    return selected_option

def get_calendar_start_date(default_start=None):
    option = st.session_state.get("calendar_start_selection")
    if isinstance(option, dict):
        return option.get("start") or default_start
    return default_start

def apply_calendar_start_filter(df, start_date):
    """
    Filter a visits/calendar dataframe to only include rows on/after start_date.
    """
    if df is None or df.empty or start_date is None:
        return df
    
    if 'Date' not in df.columns:
        return df
    
    filtered_df = df[df['Date'] >= start_date].copy()
    return filtered_df


# Import only from modules that don't import back to us
from calculations import (
    prepare_financial_data, build_profit_sharing_analysis, 
    build_ratio_breakdown_data, get_list_ratios,
    calculate_income_realization_metrics, calculate_monthly_realization_breakdown,
    calculate_study_pipeline_breakdown, calculate_site_realization_breakdown,
    calculate_study_realization_by_study
)
from formatters import (
    format_currency, create_site_header_row, style_calendar_row,
    apply_currency_formatting, apply_currency_or_empty_formatting,
    create_fy_highlighting_function
)

# Move table builder functions directly into this file to avoid circular imports
def display_income_table_pair(financial_df):
    """Display monthly income analysis tables"""
    try:
        monthly_totals = financial_df.groupby('MonthYear')['Payment'].sum()
        if not monthly_totals.empty:
            monthly_df = monthly_totals.reset_index()
            monthly_df.columns = ['Month', 'Total Income']
            monthly_df['Total Income'] = monthly_df['Total Income'].apply(format_currency)
            st.dataframe(monthly_df, width="stretch")
        else:
            st.info("No monthly data available")
    except Exception as e:
        st.error(f"Error displaying monthly income: {e}")

def display_profit_sharing_table(quarterly_ratios):
    """Display profit sharing analysis table"""
    try:
        if quarterly_ratios:
            df = pd.DataFrame(quarterly_ratios)
            # Apply highlighting for Financial Year rows
            styled_df = df.style.apply(
                lambda x: ['background-color: #e6f3ff; font-weight: bold;' if x['Type'] == 'Financial Year' else '' for _ in x], 
                axis=1
            )
            st.dataframe(styled_df, width="stretch", hide_index=True)
        else:
            st.info("No quarterly data available for profit sharing analysis")
    except Exception as e:
        st.error(f"Error displaying profit sharing table: {e}")

def display_ratio_breakdown_table(ratio_data, title):
    """Display ratio breakdown table"""
    try:
        if ratio_data:
            st.write(f"**{title}**")
            df = pd.DataFrame(ratio_data)
            st.dataframe(df, width="stretch", hide_index=True)
        else:
            st.info(f"No data available for {title}")
    except Exception as e:
        st.error(f"Error displaying {title}: {e}")

def create_summary_metrics_row(metrics_data, columns=4):
    """Create a row of metrics using Streamlit columns"""
    try:
        cols = st.columns(columns)
        for i, (label, value) in enumerate(metrics_data.items()):
            with cols[i % columns]:
                st.metric(label, value)
    except Exception as e:
        st.error(f"Error creating metrics row: {e}")

def display_breakdown_by_study(site_visits, site_patients, site_name):
    """Display study breakdown for a site"""
    try:
        study_breakdown = site_patients.groupby('Study').agg({
            'PatientID': 'count'
        }).rename(columns={'PatientID': 'Patient Count'})
        
        if len(site_visits) > 0:
            visit_breakdown = site_visits.groupby('Study').agg({
                'Visit': 'count',
                'Payment': 'sum'
            }).rename(columns={'Visit': 'Visit Count', 'Payment': 'Total Income'})
            
            combined_breakdown = study_breakdown.join(visit_breakdown, how='left').fillna(0)
            combined_breakdown['Total Income'] = combined_breakdown['Total Income'].apply(format_currency)
        else:
            # Just show patient recruitment data
            combined_breakdown = study_breakdown.copy()
            combined_breakdown['Visit Count'] = 0
            combined_breakdown['Total Income'] = "£0.00"
        
        st.dataframe(combined_breakdown, width="stretch")
    except Exception as e:
        st.error(f"Error displaying study breakdown: {e}")

def create_time_period_config():
    """Create time period configuration dictionary"""
    return {
        'monthly': {'column': 'MonthYear', 'name': 'Month', 'title': 'Monthly Ratio Breakdown'},
        'quarterly': {'column': 'QuarterYear', 'name': 'Quarter', 'title': 'Quarterly Ratio Breakdown'},
        'yearly': {'column': 'FinancialYear', 'name': 'Financial Year', 'title': 'Financial Year Ratio Breakdown'}
    }

def display_site_time_analysis(site_visits, site_patients, site_name, enhanced_visits_df):
    """Display time-based analysis for a site"""
    try:
        st.write("**Time-based Analysis**")
        
        # Quarterly analysis
        if 'QuarterYear' in enhanced_visits_df.columns:
            quarterly_stats = site_visits.groupby(enhanced_visits_df['QuarterYear']).agg({
                'Visit': 'count',
                'Payment': 'sum'
            }).rename(columns={'Visit': 'Visit Count', 'Payment': 'Income'})
            
            if not quarterly_stats.empty:
                quarterly_display = quarterly_stats.copy()
                quarterly_display['Income'] = quarterly_display['Income'].apply(format_currency)
                st.write("*Quarterly Summary*")
                st.dataframe(quarterly_display, width="stretch")
    except Exception as e:
        st.error(f"Error displaying time analysis: {e}")

def display_complete_realization_analysis(visits_df, trials_df, patients_df):
    """Display complete income realization analysis"""
    try:
        st.subheader("Income Realization Analysis")
        
        # Calculate metrics
        metrics = calculate_income_realization_metrics(visits_df, trials_df, patients_df)
        
        # Display summary metrics
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Completed Income", format_currency(metrics['completed_income']))
        with col2:
            st.metric("Total Scheduled", format_currency(metrics['total_scheduled_income']))
        with col3:
            st.metric("Pipeline Remaining", format_currency(metrics['pipeline_income']))
        with col4:
            st.metric("Realization Rate", f"{metrics['realization_rate']:.1f}%")
        
        # Monthly breakdown
        monthly_data = calculate_monthly_realization_breakdown(visits_df, trials_df)
        if monthly_data:
            st.write("**Monthly Realization Breakdown**")
            monthly_df = pd.DataFrame(monthly_data)
            monthly_df['Completed_Income'] = monthly_df['Completed_Income'].apply(format_currency)
            monthly_df['Scheduled_Income'] = monthly_df['Scheduled_Income'].apply(format_currency)
            monthly_df['Realization_Rate'] = monthly_df['Realization_Rate'].apply(lambda x: f"{x:.1f}%")
            st.dataframe(monthly_df, width="stretch", hide_index=True)
        
        # Study pipeline breakdown
        study_pipeline = calculate_study_pipeline_breakdown(visits_df, trials_df)
        if not study_pipeline.empty:
            st.write("**Pipeline by Study**")
            study_display = study_pipeline.copy()
            study_display['Pipeline_Value'] = study_display['Pipeline_Value'].apply(format_currency)
            st.dataframe(study_display, width="stretch", hide_index=True)
        
        # Site realization breakdown
        site_data = calculate_site_realization_breakdown(visits_df, trials_df)
        if site_data:
            st.write("**Site Realization Summary**")
            site_df = pd.DataFrame(site_data)
            site_df['Completed_Income'] = site_df['Completed_Income'].apply(format_currency)
            site_df['Total_Scheduled_Income'] = site_df['Total_Scheduled_Income'].apply(format_currency)
            site_df['Pipeline_Income'] = site_df['Pipeline_Income'].apply(format_currency)
            site_df['Realization_Rate'] = site_df['Realization_Rate'].apply(lambda x: f"{x:.1f}%")
            st.dataframe(site_df, width="stretch", hide_index=True)
            
    except Exception as e:
        st.error(f"Error in realization analysis: {e}")

def display_study_income_summary(visits_df):
    """Display by-study income summary for current FY by default, with optional all-time toggle."""
    try:
        st.subheader("📚 By Study Income (Current FY)")

        if visits_df is None or visits_df.empty:
            st.info("No visit data available")
            return

        # Period control (default Current FY)
        period_choice = st.radio(
            "Period",
            options=["Current FY", "All time"],
            horizontal=True,
            index=0,
            help="Switch to All time if needed"
        )
        period_key = 'current_fy' if period_choice == "Current FY" else 'all_time'

        df = calculate_study_realization_by_study(visits_df, period=period_key)

        if df.empty:
            st.info("No data for selected period")
            return

        # Format display copy
        display_df = df.copy()
        for c in ["Completed Income", "Scheduled Income", "Pipeline Income"]:
            if c in display_df.columns:
                display_df[c] = display_df[c].apply(format_currency)
        for c in ["Completed Visits", "Scheduled Visits", "Remaining Visits"]:
            if c in display_df.columns:
                display_df[c] = display_df[c].astype(int)
        if "Realization Rate" in display_df.columns:
            display_df["Realization Rate"] = display_df["Realization Rate"].apply(lambda v: f"{v:.1f}%")

        st.dataframe(display_df, width="stretch", hide_index=True)
    except Exception as e:
        st.error(f"Error displaying by-study income summary: {e}")

def display_site_income_by_fy(visits_df, trials_df):
    """Display site income breakdown by financial year (actual vs predicted)"""
    try:
        from calculations import calculate_actual_and_predicted_income_by_site
        from formatters import format_currency
        
        st.subheader("💰 Site Income by Financial Year")
        st.caption("Income earned by site performing the work (where visits happen)")
        
        # Get the site income data
        site_income_df = calculate_actual_and_predicted_income_by_site(visits_df, trials_df)
        
        if site_income_df.empty:
            st.info("No visit data available for current financial year")
            return
        
        # Format the display
        display_df = site_income_df.copy()
        
        # Format currency columns
        display_df['Actual Income'] = display_df['Actual Income'].apply(format_currency)
        display_df['Predicted Income'] = display_df['Predicted Income'].apply(format_currency)
        display_df['Total Income'] = display_df['Total Income'].apply(format_currency)
        
        # Rename columns for better display
        display_df = display_df.rename(columns={
            'SiteofVisit': 'Site',
            'Actual Visits': 'Completed Visits',
            'Predicted Visits': 'Scheduled Visits',
            'Total Visits': 'Total Visits'
        })
        
        # Reorder columns for better display
        column_order = ['Site', 'Actual Income', 'Completed Visits', 'Predicted Income', 'Scheduled Visits', 'Total Income', 'Total Visits']
        display_df = display_df[column_order]
        
        # Display the table
        st.dataframe(display_df, width="stretch", hide_index=True)
        
        # Show financial year info
        if 'Financial Year' in site_income_df.columns:
            fy_info = site_income_df['Financial Year'].iloc[0]
            st.caption(f"Financial Year: {fy_info}")
        
    except Exception as e:
        st.error(f"Error displaying site income by financial year: {e}")

def show_legend(actual_visits_df):
    """Display legend for calendar interpretation"""
    legend_text = """
    **Legend with Color Coding:**

    **Actual Visits:**
    - ✅ VisitName (Green background) = Completed Visit (within tolerance window)  
    - 🔴 OUT OF PROTOCOL VisitName (Red background) = Completed Visit (outside tolerance window - protocol deviation)
    - ⚠️ Screen Fail VisitName (Dark red background) = Screen failure (no future visits - only valid up to Day 1)

    **Predicted Visits:**
    - 📋 VisitName (Predicted) (Gray background) = Predicted Visit (no actual visit recorded yet)
    - 📅 VisitName (Planned) (Light gray background) = Planned Visit (actual visit also exists - shows original schedule)
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
        # Debug: Log calendar DataFrame info
        log_activity(f"Calendar DataFrame shape: {calendar_df.shape}", level='info')
        log_activity(f"Calendar columns: {list(calendar_df.columns)}", level='info')
        log_activity(f"Calendar has unique columns: {calendar_df.columns.is_unique}", level='info')
        log_activity(f"Site column mapping keys: {list(site_column_mapping.keys())}", level='info')
        log_activity(f"Unique visit sites: {unique_visit_sites}", level='info')
        # Prepare display columns (avoid duplicates)
        final_ordered_columns = ["Date", "Day"]
        seen_columns = {"Date", "Day"}
        log_activity(f"Building display columns for {len(unique_visit_sites)} sites", level='info')
        
        for visit_site in unique_visit_sites:
            site_data = site_column_mapping.get(visit_site, {})
            site_columns = site_data.get('columns', [])
            log_activity(f"Site {visit_site}: {len(site_columns)} columns - {site_columns}", level='info')
            
            for col in site_columns:
                if col in calendar_df.columns and col not in seen_columns:
                    final_ordered_columns.append(col)
                    seen_columns.add(col)
                    log_activity(f"Added column: {col}", level='info')
                elif col not in calendar_df.columns:
                    log_activity(f"Warning: Column {col} not found in calendar DataFrame", level='warning')
                elif col in seen_columns:
                    log_activity(f"Warning: Duplicate column {col} skipped", level='warning')
        
        log_activity(f"Final ordered columns ({len(final_ordered_columns)}): {final_ordered_columns}", level='info')

        display_df = calendar_df[final_ordered_columns].copy()
        display_df_for_view = display_df.copy()
        display_df_for_view["Date"] = display_df_for_view["Date"].dt.strftime("%Y-%m-%d")

        # Create three-level header rows
        log_activity(f"Creating headers for {len(display_df_for_view.columns)} columns", level='info')
        header_rows = create_site_header_row(display_df_for_view.columns, site_column_mapping)
        
        # Debug header rows
        log_activity(f"Level 1 headers: {header_rows['level1_site']}", level='info')
        log_activity(f"Level 2 headers: {header_rows['level2_study_patient']}", level='info')
        log_activity(f"Level 3 headers: {header_rows['level3_origin']}", level='info')
        
        # Create header dataframes
        level1_df = pd.DataFrame([header_rows['level1_site']])  # Visit sites
        level2_df = pd.DataFrame([header_rows['level2_study_patient']])  # Study_Patient
        level3_df = pd.DataFrame([header_rows['level3_origin']])  # Origin sites
        
        log_activity(f"Header DataFrames created - Level1: {level1_df.shape}, Level2: {level2_df.shape}, Level3: {level3_df.shape}", level='info')
        
        # Check for duplicate indices before concatenation
        if not display_df_for_view.index.is_unique:
            st.warning(f"Found duplicate indices in calendar data. Resetting index...")
            display_df_for_view = display_df_for_view.reset_index(drop=True)
        
        # Combine all headers with data
        try:
            log_activity(f"Concatenating DataFrames - Level1: {level1_df.shape}, Level2: {level2_df.shape}, Level3: {level3_df.shape}, Data: {display_df_for_view.shape}", level='info')
            
            # Check for column alignment
            all_columns = set(level1_df.columns) | set(level2_df.columns) | set(level3_df.columns) | set(display_df_for_view.columns)
            log_activity(f"All columns in concatenation: {sorted(all_columns)}", level='info')
            
            display_with_headers = pd.concat([
                level1_df,      # Level 1: Visit sites (ASHFIELDS, KILTEARN)
                level2_df,      # Level 2: Study_PatientID (Alpha_P001, Beta_P003)
                level3_df,      # Level 3: Origin sites ((Kiltearn), (Ashfields))
                display_df_for_view  # Actual visit data
            ], ignore_index=True)
            
            log_activity(f"Concatenation successful - Final shape: {display_with_headers.shape}", level='info')
            
        except Exception as concat_error:
            st.error(f"Error concatenating calendar data: {concat_error}")
            log_activity(f"Concatenation error details: {str(concat_error)}", level='error')
            # Fallback: just show the calendar data without headers
            display_with_headers = display_df_for_view

        # Apply styling for three header rows
        try:
            calendar_filter_option = render_calendar_start_selector()
            calendar_start_date = calendar_filter_option.get("start")
            calendar_df_filtered = apply_calendar_start_filter(calendar_df, calendar_start_date)
            visits_df_filtered = apply_calendar_start_filter(visits_df, calendar_start_date)

            filter_row = st.columns([1, 2, 2])
            with filter_row[0]:
                st.button("Scroll to Today", key="scroll_calendar_today", help="Re-center the calendar on today's date.")
            unique_sites = sorted(calendar_df_filtered['Site'].unique()) if 'Site' in calendar_df_filtered.columns else []
            unique_studies = sorted(calendar_df_filtered['Study'].unique()) if 'Study' in calendar_df_filtered.columns else []
            with filter_row[1]:
                selected_sites = st.multiselect(
                    "Sites",
                    options=unique_sites,
                    default=unique_sites,
                    help="Filter calendar columns by site."
                )
            with filter_row[2]:
                selected_studies = st.multiselect(
                    "Studies",
                    options=unique_studies,
                    default=unique_studies,
                    help="Filter calendar columns by study."
                )

            if selected_studies and 'Study' in visits_df_filtered.columns:
                visits_df_filtered = visits_df_filtered[visits_df_filtered['Study'].isin(selected_studies)]
            if selected_sites and 'SiteofVisit' in visits_df_filtered.columns:
                visits_df_filtered = visits_df_filtered[visits_df_filtered['SiteofVisit'].isin(selected_sites)]

            if selected_sites:
                base_cols = [col for col in ['Date', 'Day'] if col in calendar_df_filtered.columns]
                matching_cols = [col for col in calendar_df_filtered.columns if any(site in col for site in selected_sites)]
                calendar_df_filtered = calendar_df_filtered[base_cols + matching_cols]

            log_activity(f"Applying styling to DataFrame with shape: {display_with_headers.shape}", level='info')
            today = pd.to_datetime(date.today())
            
            # Test styling on first few rows
            log_activity(f"Testing styling on first row: {display_with_headers.iloc[0].to_dict()}", level='info')
            
            styled_df = display_with_headers.style.apply(
                lambda row: style_calendar_row(row, today), axis=1
            )
            
            log_activity(f"Styling applied successfully", level='info')
            
            # Generate HTML with month separators, frozen headers, and auto-scroll
            html_table = _generate_calendar_html_with_frozen_headers(styled_df)
            log_activity(f"HTML generation successful, length: {len(html_table)}", level='info')
            
            components.html(html_table, height=800, scrolling=True)  # Increased height for extra headers
            
        except Exception as e:
            st.warning(f"Calendar styling unavailable: {e}")
            log_activity(f"Styling error details: {str(e)}", level='error')
            st.dataframe(display_with_headers, width="stretch")

        if excluded_visits and len(excluded_visits) > 0:
            st.warning("Some visits were excluded due to screen failure:")
            st.dataframe(pd.DataFrame(excluded_visits))
            
    except Exception as e:
        st.error(f"Error displaying calendar: {e}")
        log_activity(f"Calendar display error: {str(e)}", level='error')
        
        # Try to show basic calendar without headers
        try:
            st.write("**Fallback Calendar Display (Basic)**")
            st.dataframe(calendar_df, width="stretch")
        except Exception as fallback_error:
            st.error(f"Even basic display failed: {fallback_error}")
            log_activity(f"Basic display also failed: {str(fallback_error)}", level='error')
            
            # Show raw data info
            st.write("**Raw Calendar Data Info:**")
            st.write(f"Shape: {calendar_df.shape}")
            st.write(f"Columns: {list(calendar_df.columns)}")
            st.write(f"First few rows:")
            st.dataframe(calendar_df.head(), width="stretch")

def _generate_calendar_html_with_frozen_headers(styled_df):
    """Generate HTML calendar with frozen headers, month separators, and auto-scroll to today"""
    try:
        html_table_base = styled_df.to_html(escape=False)
        html_lines = html_table_base.split('\n')
        modified_html_lines = []

        prev_month = None
        row_index = 0
        
        for line in html_lines:
            # Look for data rows with dates
            if '<tr>' in line and '<td>' in line:
                # Track row index for header identification
                row_index += 1
                
                # Skip header rows
                if line.count('<th>') > 0:
                    modified_html_lines.append(line)
                    continue
                
                # Add class to first 3 data rows (header rows) for sticky positioning
                if row_index <= 3:
                    line = line.replace('<tr', f'<tr class="header-row-{row_index}"', 1)
                    
                # Add month separators (skip for header rows)
                if row_index > 3:
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

        html_table_with_features = '\n'.join(modified_html_lines)
        
        from textwrap import dedent
        html_doc = f"""
        <!DOCTYPE html>
        <html>
            <head>
                <meta charset="utf-8">
                <style>
                    .calendar-container {{
                        max-height: 800px;
                        overflow-y: auto;
                        overflow-x: auto;
                        border: 1px solid #ddd;
                    }}
                </style>
            </head>
            <body>
                <div class="calendar-container" id="calendar-scroll-container">
                    {html_table_with_features}
                </div>
                <script>
                    // Auto-scroll to position today's date approximately 1/3 down the visible area
                    setTimeout(function() {{
                        const today = new Date().toISOString().split('T')[0];
                        const container = document.getElementById('calendar-scroll-container');
                        
                        if (container) {{
                            const rows = container.getElementsByTagName('tr');
                            
                            for (let i = 0; i < rows.length; i++) {{
                                const cells = rows[i].getElementsByTagName('td');
                                
                                if (cells.length > 0) {{
                                    const cellText = cells[0].textContent || cells[0].innerText;
                                    
                                    if (cellText.includes(today)) {{
                                        const rowTop = rows[i].offsetTop;
                                        const containerHeight = container.clientHeight;
                                        const scrollPosition = rowTop - (containerHeight / 3);
                                        container.scrollTop = Math.max(0, scrollPosition);
                                        break;
                                    }}
                                }}
                            }}
                        }}
                    }}, 100);
                </script>
            </body>
        </html>
        """
        return dedent(html_doc).strip()
    except Exception as e:
        st.warning(f"Calendar HTML generation failed: {e}")
        return styled_df.to_html(escape=False)

def display_site_statistics(site_summary_df):
    """Display basic site summary statistics"""
    st.subheader("Site Summary")
    st.dataframe(site_summary_df, width="stretch")

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
    if st.button("⚙️ Adjust Profit Sharing Weights", width="content"):
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

# NOTE: display_site_wise_statistics function removed - it was a duplicate
# The actual function used by the app is in data_analysis.py (imported in app.py line 21)
# This duplicate was never imported or called anywhere

def _display_single_site_analysis(visits_df, patients_df, enhanced_visits_df, site, screen_failures):
    """Display comprehensive analysis for a single site"""
    try:
        # Filter for visits that actually happen at this site
        site_visits = visits_df[visits_df['SiteofVisit'] == site]
        
        # Find patients who have visits at this site (may be from different origin sites)
        patients_with_visits_here = visits_df[visits_df['SiteofVisit'] == site]['PatientID'].unique()
        site_related_patients = patients_df[patients_df['PatientID'].isin(patients_with_visits_here)]
        
        # If no patients with visits at this site, check if there are patients recruited by this site
        if site_related_patients.empty:
            # Look for patients recruited by this site (based on patient origin)
            site_col = None
            for candidate in ['Site', 'PatientPractice', 'PatientSite', 'OriginSite', 'Practice', 'HomeSite']:
                if candidate in patients_df.columns:
                    site_col = candidate
                    break
            
            if site_col:
                site_related_patients = patients_df[patients_df[site_col] == site]
            
            if site_related_patients.empty:
                st.warning(f"No patients found for site: {site}")
                return
            else:
                st.info(f"ℹ️ No visits performed at {site}, but showing patient recruitment data")
        
        st.subheader(f"🏥 {site} - Visit Site Analysis")
        
        # Overall statistics
        st.write("**Overall Statistics**")
        if len(site_visits) > 0:
            metrics_data = {
                "Patients with visits here": len(site_related_patients),
                "Total Visits at this site": len(site_visits),
                "Completed Visits": len(site_visits[site_visits.get('IsActual', False)]),
                "Total Income": format_currency(site_visits['Payment'].sum())
            }
        else:
            metrics_data = {
                "Patients recruited by this site": len(site_related_patients),
                "Total Visits at this site": 0,
                "Recruitment Income": "See below",
                "Visit Income": "£0.00"
            }
        create_summary_metrics_row(metrics_data, 4)
        
        # Study breakdown at this site
        if len(site_visits) > 0:
            st.write("**Studies performed at this site:**")
        else:
            st.write("**Studies recruited by this site:**")
        display_breakdown_by_study(site_visits, site_related_patients, site)
        
        # Time-based analysis for work done at this site
        display_site_time_analysis(site_visits, site_related_patients, site, enhanced_visits_df)
        
        # Patient origin analysis
        st.write("**Patient Origins (Who Recruited):**")
        # Find the appropriate site column for patient origins
        site_col = None
        for candidate in ['Site', 'PatientPractice', 'PatientSite', 'OriginSite', 'Practice', 'HomeSite']:
            if candidate in site_related_patients.columns:
                site_col = candidate
                break
        
        if site_col:
            origin_breakdown = site_related_patients.groupby(site_col)['PatientID'].count().reset_index()
            origin_breakdown.columns = ['Origin Site', 'Patients Recruited']
            st.dataframe(origin_breakdown, width="stretch")
        else:
            st.info("No patient origin site information available")
        
        # Screen failures for patients with visits at this site
        _display_site_screen_failures(site_related_patients, screen_failures)
    except Exception as e:
        st.error(f"Error displaying analysis for site {site}: {e}")

def _display_site_screen_failures(site_patients, screen_failures):
    """Display screen failures for patients related to a site"""
    try:
        site_screen_failures = []
        for patient in site_patients.itertuples():
            patient_study_key = f"{patient.PatientID}_{patient.Study}"
            if patient_study_key in screen_failures:
                site_screen_failures.append({
                    'Patient': patient.PatientID,
                    'Study': patient.Study,
                    'Screen Fail Date': screen_failures[patient_study_key].strftime('%Y-%m-%d')
                })
        
        if site_screen_failures:
            st.write("**Screen Failures**")
            st.dataframe(pd.DataFrame(site_screen_failures), width="stretch", hide_index=True)
    except Exception as e:
        st.error(f"Error displaying screen failures: {e}")

def display_download_buttons(calendar_df, site_column_mapping, unique_visit_sites, patients_df=None, visits_df=None, trials_df=None):
    """Display comprehensive download options with Excel formatting"""
    st.subheader("💾 Download Options")

    try:
        # Prepare Excel-safe dataframe by converting Period objects to strings
        excel_df = calendar_df.copy()
        
        # Convert any Period columns to strings for Excel compatibility
        for col in excel_df.columns:
            if hasattr(excel_df[col].dtype, 'name') and 'period' in str(excel_df[col].dtype).lower():
                excel_df[col] = excel_df[col].astype(str)
            elif excel_df[col].dtype == 'object':
                # Check if any values are Period objects
                sample_vals = excel_df[col].dropna().head(5)
                if len(sample_vals) > 0 and any(str(type(val)).find('Period') != -1 for val in sample_vals):
                    excel_df[col] = excel_df[col].astype(str)
        
        # Format dates properly for Excel
        if 'Date' in excel_df.columns:
            if excel_df['Date'].dtype == 'datetime64[ns]':
                excel_df['Date'] = excel_df['Date'].dt.strftime('%d/%m/%Y')

        # CSV download - Commented out (may remove later)
        # col_csv = st.columns(1)[0]
        # with col_csv:
        #     csv = excel_df.to_csv(index=False)
        #     st.download_button(
        #         "📄 Download as CSV",
        #         data=csv,
        #         file_name="VisitCalendar.csv",
        #         mime="text/csv"
        #     )
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Calendar Only - Formatted Excel WITHOUT financials (PUBLIC ACCESS)
            try:
                from table_builders import create_enhanced_excel_export
                from datetime import timedelta
                
                # Filter calendar for planning view: 2 weeks prior to today onwards
                # This excludes historic visits but keeps recent and all future visits
                calendar_only_df = excel_df.copy()
                if 'Date' in calendar_only_df.columns:
                    # Ensure Date column is datetime for filtering
                    if calendar_only_df['Date'].dtype == 'object':
                        # If already formatted as string, parse it back
                        calendar_only_df['Date'] = pd.to_datetime(calendar_only_df['Date'], format='%d/%m/%Y', errors='coerce')
                    
                    # Calculate cutoff date: today - 14 days
                    today = pd.Timestamp(date.today())
                    cutoff_date = today - timedelta(days=14)
                    
                    # Filter to keep dates >= cutoff_date
                    calendar_only_df = calendar_only_df[calendar_only_df['Date'] >= cutoff_date].copy()
                    
                    # Restore date formatting for Excel export
                    if calendar_only_df['Date'].dtype == 'datetime64[ns]':
                        calendar_only_df['Date'] = calendar_only_df['Date'].dt.strftime('%d/%m/%Y')
                
                # Use actual data instead of empty DataFrames
                patients_data = patients_df if patients_df is not None else pd.DataFrame()
                visits_data = visits_df if visits_df is not None else pd.DataFrame()
                
                calendar_only = create_enhanced_excel_export(
                    calendar_only_df, patients_data, visits_data, site_column_mapping, unique_visit_sites,
                    include_financial=False
                )
                
                if calendar_only:
                    st.download_button(
                        "📅 Calendar Only",
                        data=calendar_only.getvalue(),
                        file_name="VisitCalendar_CalendarOnly.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        help="Calendar with visit schedule - no financial data",
                        width="stretch"
                    )
                else:
                    st.info("Calendar export generation failed")
            except Exception as e:
                st.warning(f"Calendar export unavailable: {e}")
            
        with col2:
            # Calendar and Financials - Formatted Excel WITH financials (ADMIN ONLY)
            if st.session_state.get('auth_level') == 'admin':
                try:
                    from table_builders import create_enhanced_excel_export
                    # Use actual data instead of empty DataFrames
                    patients_data = patients_df if patients_df is not None else pd.DataFrame()
                    visits_data = visits_df if visits_df is not None else pd.DataFrame()
                    
                    calendar_financials = create_enhanced_excel_export(
                        excel_df, patients_data, visits_data, site_column_mapping, unique_visit_sites,
                        include_financial=True
                    )
                    
                    if calendar_financials:
                        st.download_button(
                            "💰 Calendar and Financials",
                            data=calendar_financials.getvalue(),
                            file_name="VisitCalendar_WithFinancials.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            help="Complete calendar with income tracking and financial analysis",
                            width="stretch"
                        )
                    else:
                        st.info("Enhanced Excel generation failed")
                except Exception as e:
                    st.warning(f"Financial export unavailable: {e}")
            else:
                st.info("🔒 Login as admin to download financial data")
        
        st.markdown("---")
        st.subheader("📊 Activity Summary Report")
        st.caption("Download activity counts by financial year, site, and study (actuals vs. predicted).")
        
        from activity_report import create_activity_summary_workbook
        try:
            report_workbook = create_activity_summary_workbook(
                visits_df if visits_df is not None else pd.DataFrame()
            )
            st.download_button(
                "📈 Activity Summary (Excel)",
                data=report_workbook.getvalue(),
                file_name="Activity_Summary.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                help="Activity counts by FY/site/study with current-year actual vs predicted split",
                width="stretch"
            )
        except Exception as e:
            st.warning(f"Activity summary not available: {e}")

        if st.session_state.get('auth_level') == 'admin':
            st.markdown("---")
            st.subheader("📥 Overdue Predicted Visits")
            st.caption("Export overdue predicted visits for secretary review and bulk update.")

            from bulk_visits import build_overdue_predicted_export, parse_bulk_upload
            try:
                calendar_start = get_calendar_start_date()
                export_workbook, message = build_overdue_predicted_export(
                    visits_df if visits_df is not None else pd.DataFrame(),
                    trials_df if trials_df is not None else pd.DataFrame(),
                    calendar_start
                )
                if export_workbook is None:
                    st.info(message or "No overdue predicted visits found for the selected date range.")
                else:
                    st.download_button(
                        "📄 Export Overdue Predicted Visits (Excel)",
                        data=export_workbook.getvalue(),
                        file_name="Overdue_Predicted_Visits.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        help="Download Excel with overdue predicted visits, including dropdowns for extras.",
                        width="stretch"
                    )
                    st.caption(
                        "The Excel file includes dropdowns per row for study-specific extras, plus fields for ActualDate and Outcome."
                    )
            except Exception as e:
                st.warning(f"Overdue visit export unavailable: {e}")

            st.subheader("⬆️ Import Completed Visits")
            st.caption("Upload the completed overdue visit Excel file to add actual visits in bulk.")

            uploaded_file = st.file_uploader(
                "Upload completed overdue visit workbook",
                type=["xlsx", "xls"],
                key="bulk_overdue_upload"
            )

            if uploaded_file is not None:
                parsing = parse_bulk_upload(
                    uploaded_file,
                    visits_df if visits_df is not None else pd.DataFrame(),
                    trials_df if trials_df is not None else pd.DataFrame(),
                    calendar_start
                )

                errors = parsing.get("errors", [])
                warnings = parsing.get("warnings", [])
                records = parsing.get("records", [])

                if errors:
                    for err in errors:
                        st.error(err)
                else:
                    if warnings:
                        for warn in warnings:
                            st.warning(warn)

                    if not records:
                        st.info("No completed visits detected in the uploaded file.")
                    else:
                        records_df = pd.DataFrame(records)
                        records_df_display = records_df.copy()
                        if 'ActualDate' in records_df_display.columns and not pd.api.types.is_string_dtype(records_df_display['ActualDate']):
                            records_df_display['ActualDate'] = records_df_display['ActualDate'].dt.strftime('%d/%m/%Y')

                        st.success(f"Parsed {len(records_df)} visit record(s) ready for import.")
                        with st.expander("Preview import records", expanded=False):
                            st.dataframe(records_df_display, width="stretch", hide_index=True)

                        if st.session_state.get('use_database'):
                            if st.button("Apply Bulk Update", type="primary", key="apply_bulk_update"):
                                try:
                                    import database as db
                                    success, message, code = db.append_visit_to_database(records_df)
                                    if success:
                                        st.success(message)
                                        st.session_state.data_refresh_needed = True
                                    else:
                                        st.error(message)
                                except Exception as e:
                                    st.error(f"Failed to append visits: {e}")
                        else:
                            csv_update = records_df_display.to_csv(index=False)
                            st.download_button(
                                "⬇️ Download Actual Visits CSV (append to actual_visits file)",
                                data=csv_update,
                                file_name="actual_visits_updates.csv",
                                mime="text/csv",
                                help="Download the prepared actual visits for manual merging.",
                                width="stretch",
                                key="bulk_overdue_download_updates"
                            )

    except Exception as e:
        st.error(f"Error creating download options: {e}")
        # Fallback removed - Excel export is primary method
        st.info("Please report this error if Excel export fails")

