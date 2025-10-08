import streamlit as st
import pandas as pd
import io
from datetime import date
import re
import streamlit.components.v1 as components
from helpers import log_activity

# Import only from modules that don't import back to us
from calculations import (
    prepare_financial_data, build_profit_sharing_analysis, 
    build_ratio_breakdown_data, get_list_ratios,
    calculate_income_realization_metrics, calculate_monthly_realization_breakdown,
    calculate_study_pipeline_breakdown, calculate_site_realization_breakdown
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
        if financial_df.empty:
            st.info("No financial data available")
            return
        
        # Debug: Log the data we're working with
        log_activity(f"Financial data shape: {financial_df.shape}", level='info')
        log_activity(f"Date column type: {financial_df['Date'].dtype}", level='info')
        log_activity(f"Sample dates: {financial_df['Date'].head().tolist()}", level='info')
        log_activity(f"MonthYear column type: {financial_df['MonthYear'].dtype}", level='info')
        log_activity(f"Unique MonthYear values: {financial_df['MonthYear'].unique()}", level='info')
        log_activity(f"Payment column sample: {financial_df['Payment'].head().tolist()}", level='info')
            
        # Convert MonthYear to string for proper grouping
        financial_df = financial_df.copy()
        financial_df['MonthYearStr'] = financial_df['MonthYear'].astype(str)
        
        # Debug: Log after conversion
        log_activity(f"Unique MonthYearStr values: {financial_df['MonthYearStr'].unique()}", level='info')
        
        # Group by month and sum payments
        monthly_totals = financial_df.groupby('MonthYearStr')['Payment'].fillna(0).sum()
        
        # Debug: Log grouping result
        log_activity(f"Monthly totals type: {type(monthly_totals)}", level='info')
        log_activity(f"Monthly totals: {monthly_totals}", level='info')
        
        # Handle both Series and scalar results
        if hasattr(monthly_totals, 'empty'):
            # It's a Series
            if not monthly_totals.empty:
                monthly_df = monthly_totals.reset_index()
                monthly_df.columns = ['Month', 'Total Income']
                monthly_df['Total Income'] = monthly_df['Total Income'].apply(format_currency)
                
                # Sort by month (convert back to period for sorting, then back to string)
                monthly_df['MonthPeriod'] = pd.to_datetime(monthly_df['Month']).dt.to_period('M')
                monthly_df = monthly_df.sort_values('MonthPeriod')
                monthly_df = monthly_df.drop('MonthPeriod', axis=1)
                
                log_activity(f"Final monthly breakdown: {monthly_df.to_dict('records')}", level='info')
                st.dataframe(monthly_df, width='stretch')
            else:
                st.info("No monthly data available")
        else:
            # It's a scalar (single value) - convert to DataFrame
            if pd.notna(monthly_totals) and monthly_totals != 0:
                # Get the month from the original data
                month = financial_df['MonthYearStr'].iloc[0] if not financial_df.empty else 'Unknown'
                monthly_df = pd.DataFrame({
                    'Month': [month],
                    'Total Income': [monthly_totals]
                })
                monthly_df['Total Income'] = monthly_df['Total Income'].apply(format_currency)
                log_activity(f"Single month breakdown: {monthly_df.to_dict('records')}", level='info')
                st.dataframe(monthly_df, width='stretch')
            else:
                st.info("No monthly data available")
    except Exception as e:
        st.error(f"Error displaying monthly income: {e}")
        log_activity(f"Error details: {str(e)}", level='error')

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
            st.dataframe(styled_df, width='stretch', hide_index=True)
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
            st.dataframe(df, width='stretch', hide_index=True)
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
        
        st.dataframe(combined_breakdown, width='stretch')
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
                st.dataframe(quarterly_display, width='stretch')
    except Exception as e:
        st.error(f"Error displaying time analysis: {e}")

def display_actual_and_predicted_income_by_site(site_income_df):
    """Display actual and predicted income by site for current financial year"""
    if site_income_df.empty:
        st.info("No visits found for the current financial year.")
        return
    
    st.markdown("---")
    st.subheader("💰 Income by Site - Current Financial Year")
    st.caption("Actual income earned and predicted income for the current financial year")
    
    try:
        # Format the data for display
        display_df = site_income_df.copy()
        
        # Format currency columns
        currency_columns = ['Actual Income', 'Predicted Income', 'Total Income']
        for col in currency_columns:
            if col in display_df.columns:
                display_df[col] = display_df[col].apply(lambda x: f"£{x:,.2f}")
        
        # Rename columns for display
        display_df = display_df.rename(columns={
            'SiteofVisit': 'Site',
            'Actual Income': 'Actual Income',
            'Actual Visits': 'Actual Visits',
            'Predicted Income': 'Predicted Income',
            'Predicted Visits': 'Predicted Visits',
            'Total Income': 'Total Income',
            'Total Visits': 'Total Visits',
            'Financial Year': 'Financial Year'
        })
        
        # Display the table
        st.dataframe(
            display_df[['Site', 'Actual Income', 'Actual Visits', 'Predicted Income', 'Predicted Visits', 'Total Income', 'Total Visits']], 
            width='stretch', 
            hide_index=True,
            column_config={
                "Site": st.column_config.TextColumn("Site", width="medium"),
                "Actual Income": st.column_config.TextColumn("Actual Income", width="medium"),
                "Actual Visits": st.column_config.NumberColumn("Actual Visits", width="small"),
                "Predicted Income": st.column_config.TextColumn("Predicted Income", width="medium"),
                "Predicted Visits": st.column_config.NumberColumn("Predicted Visits", width="small"),
                "Total Income": st.column_config.TextColumn("Total Income", width="medium"),
                "Total Visits": st.column_config.NumberColumn("Total Visits", width="small")
            }
        )
        
        # Show summary metrics
        total_actual_income = site_income_df['Actual Income'].sum()
        total_predicted_income = site_income_df['Predicted Income'].sum()
        total_income = site_income_df['Total Income'].sum()
        
        total_actual_visits = site_income_df['Actual Visits'].sum()
        total_predicted_visits = site_income_df['Predicted Visits'].sum()
        total_visits = site_income_df['Total Visits'].sum()
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Actual Income Earned", f"£{total_actual_income:,.2f}")
        with col2:
            st.metric("Predicted Income", f"£{total_predicted_income:,.2f}")
        with col3:
            st.metric("Total Income", f"£{total_income:,.2f}")
        with col4:
            actual_percentage = (total_actual_income / total_income * 100) if total_income > 0 else 0
            st.metric("Actual %", f"{actual_percentage:.1f}%")
            
    except Exception as e:
        st.error(f"Error displaying income by site: {e}")

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
            st.dataframe(monthly_df, width='stretch', hide_index=True)
        
        # Study pipeline breakdown
        study_pipeline = calculate_study_pipeline_breakdown(visits_df, trials_df)
        if not study_pipeline.empty:
            st.write("**Pipeline by Study**")
            study_display = study_pipeline.copy()
            study_display['Pipeline_Value'] = study_display['Pipeline_Value'].apply(format_currency)
            st.dataframe(study_display, width='stretch', hide_index=True)
        
        # Site realization breakdown
        site_data = calculate_site_realization_breakdown(visits_df, trials_df)
        if site_data:
            st.write("**Site Realization Summary**")
            site_df = pd.DataFrame(site_data)
            site_df['Completed_Income'] = site_df['Completed_Income'].apply(format_currency)
            site_df['Total_Scheduled_Income'] = site_df['Total_Scheduled_Income'].apply(format_currency)
            site_df['Pipeline_Income'] = site_df['Pipeline_Income'].apply(format_currency)
            site_df['Realization_Rate'] = site_df['Realization_Rate'].apply(lambda x: f"{x:.1f}%")
            st.dataframe(site_df, width='stretch', hide_index=True)
            
    except Exception as e:
        st.error(f"Error in realization analysis: {e}")

def show_legend(actual_visits_df):
    """Display legend for calendar interpretation"""
    legend_text = """
    **Legend with Color Coding:**

    **Actual Visits:**
    - ✅ VisitName (Green background) = Completed Visit (shows when visit actually happened)
    - ⚠️ Screen Fail VisitName (Dark red background) = Screen failure (no future visits - only valid up to Day 1)

    **Predicted Visits:**
    - 📋 VisitName (Predicted) (Gray background) = Predicted Visit (no actual visit recorded yet)
    - 📅 VisitName (Planned) (Light gray background) = Planned Visit (actual visit also exists - shows original schedule)

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
    
    **Note:** All actual visits are shown on the calendar on the date they actually occurred, regardless of the original schedule. No tolerance window checking is performed.
    """ if actual_visits_df is not None else """
    **Legend:** 
    - VisitName (Gray) = Scheduled Visit
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
            log_activity(f"Applying styling to DataFrame with shape: {display_with_headers.shape}", level='info')
            today = pd.to_datetime(date.today())
            
            # Test styling on first few rows
            log_activity(f"Testing styling on first row: {display_with_headers.iloc[0].to_dict()}", level='info')
            
            styled_df = display_with_headers.style.apply(
                lambda row: style_calendar_row(row, today), axis=1
            )
            
            log_activity(f"Styling applied successfully", level='info')
            
            # Generate HTML with month separators
            html_table = _generate_calendar_html_with_separators(styled_df)
            log_activity(f"HTML generation successful, length: {len(html_table)}", level='info')
            
            components.html(html_table, height=800, scrolling=True)  # Increased height for extra headers
            
        except Exception as e:
            st.warning(f"Calendar styling unavailable: {e}")
            log_activity(f"Styling error details: {str(e)}", level='error')
            st.dataframe(display_with_headers, width='stretch')

        if excluded_visits and len(excluded_visits) > 0:
            st.warning("Some visits were excluded due to screen failure:")
            st.dataframe(pd.DataFrame(excluded_visits))
            
    except Exception as e:
        st.error(f"Error displaying calendar: {e}")
        log_activity(f"Calendar display error: {str(e)}", level='error')
        
        # Try to show basic calendar without headers
        try:
            st.write("**Fallback Calendar Display (Basic)**")
            st.dataframe(calendar_df, width='stretch')
        except Exception as fallback_error:
            st.error(f"Even basic display failed: {fallback_error}")
            log_activity(f"Basic display also failed: {str(fallback_error)}", level='error')
            
            # Show raw data info
            st.write("**Raw Calendar Data Info:**")
            st.write(f"Shape: {calendar_df.shape}")
            st.write(f"Columns: {list(calendar_df.columns)}")
            st.write(f"First few rows:")
            st.dataframe(calendar_df.head(), width='stretch')

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
    st.dataframe(site_summary_df, width='stretch')

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
    if st.button("⚙️ Adjust Profit Sharing Weights", width='content'):
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
        
        # Always create tabs for all visit sites, even if they have no visits
        # This ensures sites like Kiltearn are visible even when they only have patient recruitment income
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
        
        # If no patients with visits at this site, check if there are patients recruited by this site
        if site_related_patients.empty:
            # Look for patients recruited by this site (based on patient origin)
            site_col = None
            for candidate in ['PatientPractice', 'PatientSite', 'Practice', 'HomeSite']:
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
            st.dataframe(origin_breakdown, width='stretch')
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
            st.dataframe(pd.DataFrame(site_screen_failures), width='stretch', hide_index=True)
    except Exception as e:
        st.error(f"Error displaying screen failures: {e}")

def display_download_buttons(calendar_df, site_column_mapping, unique_visit_sites, patients_df=None, visits_df=None):
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

        col1, col2, col3 = st.columns(3)
        
        with col1:
            # CSV download
            csv = excel_df.to_csv(index=False)
            st.download_button(
                "📄 Download as CSV",
                data=csv,
                file_name="VisitCalendar.csv",
                mime="text/csv"
            )

        with col2:
            # Basic Excel download with Period handling
            buf = io.BytesIO()
            try:
                excel_df.to_excel(buf, index=False, engine='openpyxl')
                st.download_button(
                    "💾 Download Basic Excel", 
                    data=buf.getvalue(), 
                    file_name="VisitCalendar.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            except Exception as excel_error:
                st.error(f"Excel export failed: {excel_error}")
                # Fallback to CSV with xlsx extension
                csv_fallback = excel_df.to_csv(index=False)
                st.download_button(
                    "💾 Download as CSV (Excel failed)", 
                    data=csv_fallback, 
                    file_name="VisitCalendar.csv",
                    mime="text/csv"
                )
            
        with col3:
            # Enhanced Excel from table_builders
            try:
                from table_builders import create_enhanced_excel_export
                # Use actual data instead of empty DataFrames
                patients_data = patients_df if patients_df is not None else pd.DataFrame()
                visits_data = visits_df if visits_df is not None else pd.DataFrame()
                
                enhanced_excel = create_enhanced_excel_export(
                    excel_df, patients_data, visits_data, site_column_mapping, unique_visit_sites
                )
                
                if enhanced_excel:
                    st.download_button(
                        "✨ Enhanced Excel with Headers",
                        data=enhanced_excel.getvalue(),
                        file_name="VisitCalendar_Enhanced.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        help="Includes explanatory headers, data dictionary, and summary"
                    )
                else:
                    st.info("Enhanced Excel generation failed")
            except Exception as e:
                st.warning(f"Enhanced Excel unavailable: {e}")
                # Provide basic Excel as fallback
                try:
                    buf2 = io.BytesIO()
                    excel_df.to_excel(buf2, index=False, engine='openpyxl')
                    st.download_button(
                        "📊 Download Excel (Basic)",
                        data=buf2.getvalue(),
                        file_name="VisitCalendar_Basic.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                except:
                    st.info("Excel export requires openpyxl library")

    except Exception as e:
        st.error(f"Error creating download options: {e}")
        # Ultimate fallback - CSV only
        try:
            csv_fallback = calendar_df.astype(str).to_csv(index=False)
            st.download_button(
                "📄 Download as CSV (Fallback)",
                data=csv_fallback,
                file_name="VisitCalendar_Fallback.csv",
                mime="text/csv"
            )
        except Exception as fallback_error:
            st.error(f"All download methods failed: {fallback_error}")

