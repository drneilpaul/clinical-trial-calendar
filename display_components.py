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

                    #
