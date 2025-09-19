import streamlit as st
import pandas as pd

def show_legend(actual_visits_df):
    if actual_visits_df is not None:
        st.info("""
        **Legend with Color Coding:**
        - ✅ Visit X (Green) = Completed Visit (within tolerance window)
        - ⚠️ Visit X (Yellow) = Completed Visit (outside tolerance window)
        - ❌ Screen Fail X (Red) = Screen failure (no future visits)
        - Visit X (Gray) = Scheduled/Planned Visit
        - - / + (Blue-gray, italic) = Tolerance period
        """)
    else:
        st.info("""
        **Legend:** 
        - Visit X (Gray) = Scheduled Visit
        - - / + (Blue-gray, italic) = Tolerance period
        """)

def display_calendar(calendar_df, site_column_mapping, unique_sites, excluded_visits=None):
    st.subheader("Generated Visit Calendar")
    st.dataframe(calendar_df, use_container_width=True)
    if excluded_visits and len(excluded_visits) > 0:
        st.warning("Some visits were excluded due to screen failure:")
        st.dataframe(pd.DataFrame(excluded_visits))

def display_financial_tables(stats, visits_df):
    st.subheader("💰 Financial Analysis")
    st.metric("Total Visits", stats.get("total_visits", 0))
    st.metric("Total Income", f"£{stats.get('total_income', 0):,.2f}")

def display_site_statistics(site_summary_df):
    st.subheader("Site Summary")
    st.dataframe(site_summary_df, use_container_width=True)

def display_download_buttons(calendar_df):
    import io
    buf = io.BytesIO()
    calendar_df.to_excel(buf, index=False)
    st.download_button("💾 Download Calendar Excel", data=buf.getvalue(), file_name="VisitCalendar.xlsx")