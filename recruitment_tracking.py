"""
Recruitment tracking view - showing recruitment progress vs targets per site per study
"""

import pandas as pd
import streamlit as st
from typing import Optional, Dict
from helpers import log_activity
import plotly.graph_objects as go
import plotly.express as px

def build_recruitment_data(patients_df: pd.DataFrame, trials_df: pd.DataFrame) -> pd.DataFrame:
    """
    Build recruitment tracking data grouped by Study + SiteforVisit.
    
    Args:
        patients_df: Patients dataframe (with PatientPractice column)
        trials_df: Trial schedules dataframe (for getting Study+Site combinations, but prefers study_site_details for targets)
    
    Returns:
        DataFrame with columns: Study, Site, Target, Actual, Progress, Status
    """
    import database as db
    recruitment_rows = []
    
    # Get unique study-site combinations - try study_site_details first, fallback to trials_df
    study_details_df = db.fetch_all_study_site_details()
    
    if study_details_df is not None and not study_details_df.empty:
        # Use study_site_details as primary source
        # Rename ContractedSite to SiteforVisit for consistency with rest of code
        study_details_df = study_details_df.rename(columns={'ContractedSite': 'SiteforVisit'})
        study_site_combos = study_details_df[['Study', 'SiteforVisit']].drop_duplicates()
    elif 'SiteforVisit' in trials_df.columns:
        # Fallback to trials_df
        study_site_combos = trials_df.groupby(['Study', 'SiteforVisit']).first().reset_index()[['Study', 'SiteforVisit']]
    else:
        log_activity("No SiteforVisit column in trials_df and no study_site_details, cannot build recruitment data", level='error')
        return pd.DataFrame(columns=['Study', 'Site', 'Target', 'Actual', 'Progress', 'Status'])
    
    for _, row in study_site_combos.iterrows():
        study = row['Study']
        site = row['SiteforVisit']
        
        # Get target and status from study_site_details (preferred) or fallback to trials_df
        target = None
        study_status = 'active'
        
        if study_details_df is not None and not study_details_df.empty:
            # Try to get from study_site_details
            study_detail = study_details_df[
                (study_details_df['Study'] == study) & 
                (study_details_df['SiteforVisit'] == site)
            ]
            if not study_detail.empty:
                target = study_detail.iloc[0].get('RecruitmentTarget')
                if pd.notna(target):
                    target = int(target) if target else None
                study_status = study_detail.iloc[0].get('StudyStatus', 'active')
        
        # Fallback to trials_df if not found in study_site_details
        if target is None and 'RecruitmentTarget' in trials_df.columns:
            target_rows = trials_df[(trials_df['Study'] == study) & (trials_df['SiteforVisit'] == site)]
            if not target_rows.empty:
                target_values = target_rows['RecruitmentTarget'].dropna().unique()
                if len(target_values) > 0:
                    target = int(target_values[0]) if pd.notna(target_values[0]) else None
        
        if study_status == 'active' and 'StudyStatus' in trials_df.columns:
            status_rows = trials_df[(trials_df['Study'] == study) & (trials_df['SiteforVisit'] == site)]
            if not status_rows.empty:
                status_values = status_rows['StudyStatus'].dropna().unique()
                if len(status_values) > 0:
                    study_status = str(status_values[0]).lower()
        
        # Calculate actual recruitment count
        actual = 0
        if 'PatientPractice' in patients_df.columns:
            study_patients = patients_df[
                (patients_df['Study'] == study) & 
                (patients_df['PatientPractice'] == site)
            ]
            actual = len(study_patients)
        
        # Calculate progress percentage
        progress = None
        if target and target > 0:
            progress = (actual / target) * 100
        
        # Determine status
        status = 'no_target'
        if target:
            if actual >= target:
                status = 'at_or_over'
            elif progress and progress >= 75:
                status = 'near_target'
            else:
                status = 'under_target'
        
        recruitment_rows.append({
            'Study': study,
            'Site': site,
            'Target': target,
            'Actual': actual,
            'Progress': progress,
            'Status': status,
            'StudyStatus': study_status
        })
    
    recruitment_df = pd.DataFrame(recruitment_rows)
    return recruitment_df

def get_progress_color(status: str) -> str:
    """Get color for recruitment progress status"""
    status_colors = {
        'at_or_over': '#2ecc71',  # Green
        'near_target': '#f39c12',  # Yellow/Orange
        'under_target': '#e74c3c',  # Red
        'no_target': '#95a5a6'  # Gray
    }
    return status_colors.get(status, '#95a5a6')

def display_recruitment_dashboard(recruitment_data: pd.DataFrame):
    """
    Display recruitment tracking dashboard with table and chart views.
    
    Args:
        recruitment_data: DataFrame from build_recruitment_data()
    """
    if recruitment_data.empty:
        st.info("No recruitment data available to display.")
        return
    
    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        selected_studies = st.multiselect(
            "Filter by Study",
            options=sorted(recruitment_data['Study'].unique()),
            default=[]
        )
    with col2:
        selected_sites = st.multiselect(
            "Filter by Site",
            options=sorted(recruitment_data['Site'].unique()),
            default=[]
        )
    with col3:
        selected_statuses = st.multiselect(
            "Filter by Study Status",
            options=['active', 'contracted', 'in_setup', 'expression_of_interest'],
            default=[]
        )
    
    # Apply filters
    filtered_data = recruitment_data.copy()
    if selected_studies:
        filtered_data = filtered_data[filtered_data['Study'].isin(selected_studies)]
    if selected_sites:
        filtered_data = filtered_data[filtered_data['Site'].isin(selected_sites)]
    if selected_statuses:
        filtered_data = filtered_data[filtered_data['StudyStatus'].isin(selected_statuses)]
    
    if filtered_data.empty:
        st.info("No data matches the selected filters.")
        return
    
    # Summary metrics
    st.markdown("### Recruitment Summary")
    col1, col2, col3, col4 = st.columns(4)
    
    total_studies = len(filtered_data)
    studies_with_targets = len(filtered_data[filtered_data['Target'].notna()])
    total_target = filtered_data['Target'].sum() if 'Target' in filtered_data.columns else 0
    total_actual = filtered_data['Actual'].sum()
    
    with col1:
        st.metric("Total Studies", total_studies)
    with col2:
        st.metric("Studies with Targets", studies_with_targets)
    with col3:
        st.metric("Total Target", int(total_target) if total_target else "N/A")
    with col4:
        st.metric("Total Actual", total_actual)
    
    # Table view
    st.markdown("### Recruitment Table")
    display_df = filtered_data.copy()
    display_df['Progress'] = display_df['Progress'].apply(
        lambda x: f"{x:.1f}%" if pd.notna(x) else "N/A"
    )
    display_df['Target'] = display_df['Target'].apply(
        lambda x: int(x) if pd.notna(x) else "No target"
    )
    
    # Add color coding
    def style_row(row):
        colors = {
            'at_or_over': 'background-color: #d4edda;',
            'near_target': 'background-color: #fff3cd;',
            'under_target': 'background-color: #f8d7da;',
            'no_target': 'background-color: #e2e3e5;'
        }
        return [colors.get(row['Status'], '')] * len(row)
    
    styled_df = display_df.style.apply(style_row, axis=1)
    st.dataframe(
        styled_df,
        width='stretch',
        hide_index=True,
        column_config={
            'Study': st.column_config.TextColumn('Study', width='medium'),
            'Site': st.column_config.TextColumn('Site', width='small'),
            'Target': st.column_config.TextColumn('Target', width='small'),
            'Actual': st.column_config.NumberColumn('Actual', width='small'),
            'Progress': st.column_config.TextColumn('Progress %', width='small'),
            'Status': st.column_config.TextColumn('Status', width='small'),
            'StudyStatus': st.column_config.TextColumn('Study Status', width='small')
        }
    )
    
    # Chart view
    st.markdown("### Recruitment Chart")
    
    # Filter to only studies with targets for chart
    chart_data = filtered_data[filtered_data['Target'].notna()].copy()
    
    if not chart_data.empty:
        # Create bar chart
        fig = go.Figure()
        
        # Add target bars
        fig.add_trace(go.Bar(
            name='Target',
            x=[f"{row['Study']} - {row['Site']}" for _, row in chart_data.iterrows()],
            y=chart_data['Target'],
            marker_color='lightblue',
            opacity=0.7
        ))
        
        # Add actual bars
        fig.add_trace(go.Bar(
            name='Actual',
            x=[f"{row['Study']} - {row['Site']}" for _, row in chart_data.iterrows()],
            y=chart_data['Actual'],
            marker_color=[get_progress_color(row['Status']) for _, row in chart_data.iterrows()],
            opacity=0.9
        ))
        
        fig.update_layout(
            title="Recruitment: Target vs Actual",
            xaxis_title="Study - Site",
            yaxis_title="Number of Patients",
            barmode='group',
            height=400,
            xaxis=dict(tickangle=-45)
        )
        
        st.plotly_chart(fig, width='stretch')
    else:
        st.info("No studies with targets available for chart display.")
    
    # Progress indicators legend
    st.markdown("### Progress Status Legend")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(f"<span style='color: #2ecc71; font-weight: bold;'>●</span> At/Over Target", unsafe_allow_html=True)
    with col2:
        st.markdown(f"<span style='color: #f39c12; font-weight: bold;'>●</span> Near Target (75-99%)", unsafe_allow_html=True)
    with col3:
        st.markdown(f"<span style='color: #e74c3c; font-weight: bold;'>●</span> Under Target (<75%)", unsafe_allow_html=True)
    with col4:
        st.markdown(f"<span style='color: #95a5a6; font-weight: bold;'>●</span> No Target Set", unsafe_allow_html=True)

def overlay_recruitment_on_gantt(gantt_data: pd.DataFrame, recruitment_data: pd.DataFrame) -> pd.DataFrame:
    """
    Add recruitment progress indicators to Gantt data.
    
    Args:
        gantt_data: Gantt chart data
        recruitment_data: Recruitment tracking data
    
    Returns:
        Enhanced gantt_data with recruitment columns
    """
    # Rename 'Status' to 'RecruitmentStatus' to avoid conflict with study Status column
    recruitment_data_renamed = recruitment_data.rename(columns={'Status': 'RecruitmentStatus'})
    
    # Merge recruitment data into gantt data
    enhanced_gantt = gantt_data.merge(
        recruitment_data_renamed[['Study', 'Site', 'Target', 'Actual', 'Progress', 'RecruitmentStatus']],
        on=['Study', 'Site'],
        how='left'
    )
    
    return enhanced_gantt
