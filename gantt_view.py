"""
Gantt chart view for clinical trials - showing studies by site with timeline visualization
"""

import pandas as pd
import streamlit as st
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
from helpers import log_activity
import plotly.graph_objects as go
from plotly.subplots import make_subplots

def calculate_study_dates(study: str, site: str, patients_df: pd.DataFrame, 
                         visits_df: pd.DataFrame, trials_df: pd.DataFrame) -> Dict[str, Optional[date]]:
    """
    Calculate study dates (start, end, last enrollment) for a study at a specific site.
    Prefers calculated dates, but uses FPFV/LPFV/LPLV overrides if available.
    
    Args:
        study: Study name
        site: Site name (SiteforVisit)
        patients_df: Patients dataframe
        visits_df: Visits dataframe (with Date column)
        trials_df: Trial schedules dataframe (may contain FPFV/LPFV/LPLV overrides)
    
    Returns:
        dict with keys: 'start_date', 'end_date', 'last_enrollment', 'status'
    """
    # Get status and date overrides from trials_df
    study_trials = trials_df[(trials_df['Study'] == study) & (trials_df['SiteforVisit'] == site)]
    
    # Get status (default to 'active' if not found)
    status = 'active'
    if not study_trials.empty and 'StudyStatus' in study_trials.columns:
        status_values = study_trials['StudyStatus'].dropna().unique()
        if len(status_values) > 0:
            status = str(status_values[0]).lower()
    
    # Get date overrides
    fpfv_override = None
    lpfv_override = None
    lplv_override = None
    
    if not study_trials.empty:
        if 'FPFV' in study_trials.columns:
            fpfv_values = study_trials['FPFV'].dropna()
            if not fpfv_values.empty:
                fpfv_override = pd.to_datetime(fpfv_values.iloc[0]).date() if pd.notna(fpfv_values.iloc[0]) else None
        
        if 'LPFV' in study_trials.columns:
            lpfv_values = study_trials['LPFV'].dropna()
            if not lpfv_values.empty:
                lpfv_override = pd.to_datetime(lpfv_values.iloc[0]).date() if pd.notna(lpfv_values.iloc[0]) else None
        
        if 'LPLV' in study_trials.columns:
            lplv_values = study_trials['LPLV'].dropna()
            if not lplv_values.empty:
                lplv_override = pd.to_datetime(lplv_values.iloc[0]).date() if pd.notna(lplv_values.iloc[0]) else None
    
    # Calculate dates from patient/visit data if overrides not available
    start_date = fpfv_override
    last_enrollment = lpfv_override
    end_date = lplv_override
    
    # Calculate start date (FPFV) from patients
    if start_date is None:
        study_patients = patients_df[
            (patients_df['Study'] == study) & 
            (patients_df['PatientPractice'] == site)
        ]
        if not study_patients.empty and 'StartDate' in study_patients.columns:
            start_dates = pd.to_datetime(study_patients['StartDate'], errors='coerce').dropna()
            if not start_dates.empty:
                start_date = start_dates.min().date()
    
    # Calculate last enrollment (LPFV) from patients
    if last_enrollment is None:
        study_patients = patients_df[
            (patients_df['Study'] == study) & 
            (patients_df['PatientPractice'] == site)
        ]
        if not study_patients.empty and 'StartDate' in study_patients.columns:
            start_dates = pd.to_datetime(study_patients['StartDate'], errors='coerce').dropna()
            if not start_dates.empty:
                last_enrollment = start_dates.max().date()
    
    # Calculate end date (LPLV) from visits
    if end_date is None:
        study_visits = visits_df[
            (visits_df['Study'] == study) & 
            (visits_df['SiteofVisit'] == site)
        ]
        if not study_visits.empty and 'Date' in study_visits.columns:
            visit_dates = pd.to_datetime(study_visits['Date'], errors='coerce').dropna()
            if not visit_dates.empty:
                end_date = visit_dates.max().date()
    
    return {
        'start_date': start_date,
        'end_date': end_date,
        'last_enrollment': last_enrollment,
        'status': status
    }

def build_gantt_data(patients_df: pd.DataFrame, trials_df: pd.DataFrame, 
                    visits_df: pd.DataFrame, actual_visits_df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """
    Build Gantt data structure grouped by site, with studies and their timelines.
    
    Args:
        patients_df: Patients dataframe
        trials_df: Trial schedules dataframe
        visits_df: Visits dataframe (with Date column)
        actual_visits_df: Optional actual visits dataframe
    
    Returns:
        DataFrame with columns: Site, Study, StartDate, EndDate, LastEnrollment, Status, Duration
    """
    gantt_rows = []
    
    # Get unique sites from trials_df (SiteforVisit)
    if 'SiteforVisit' not in trials_df.columns:
        log_activity("No SiteforVisit column in trials_df, cannot build Gantt data", level='error')
        return pd.DataFrame(columns=['Site', 'Study', 'StartDate', 'EndDate', 'LastEnrollment', 'Status', 'Duration'])
    
    unique_sites = trials_df['SiteforVisit'].dropna().unique()
    unique_studies = trials_df['Study'].dropna().unique()
    
    for site in unique_sites:
        site_studies = trials_df[trials_df['SiteforVisit'] == site]['Study'].unique()
        
        for study in site_studies:
            dates = calculate_study_dates(study, site, patients_df, visits_df, trials_df)
            
            # Calculate duration in days
            duration = None
            if dates['start_date'] and dates['end_date']:
                duration = (dates['end_date'] - dates['start_date']).days
            
            gantt_rows.append({
                'Site': site,
                'Study': study,
                'StartDate': dates['start_date'],
                'EndDate': dates['end_date'],
                'LastEnrollment': dates['last_enrollment'],
                'Status': dates['status'],
                'Duration': duration
            })
    
    gantt_df = pd.DataFrame(gantt_rows)
    
    # Filter out rows with no dates (studies with no patients/visits yet)
    # But keep them if status is 'expression_of_interest' or 'in_setup'
    gantt_df = gantt_df[
        (gantt_df['StartDate'].notna()) | 
        (gantt_df['Status'].isin(['expression_of_interest', 'in_setup']))
    ]
    
    return gantt_df

def get_status_color(status: str) -> str:
    """Get color for study status"""
    status_colors = {
        'active': '#2ecc71',  # Green
        'contracted': '#3498db',  # Blue
        'in_setup': '#f39c12',  # Orange/Yellow
        'expression_of_interest': '#95a5a6'  # Gray
    }
    return status_colors.get(status.lower(), '#95a5a6')

def display_gantt_chart(gantt_data: pd.DataFrame, show_recruitment_overlay: bool = False, 
                       recruitment_data: Optional[pd.DataFrame] = None):
    """
    Display Gantt chart visualization using Plotly.
    
    Args:
        gantt_data: DataFrame from build_gantt_data()
        show_recruitment_overlay: Whether to overlay recruitment progress
        recruitment_data: Optional recruitment data for overlay
    """
    if gantt_data.empty:
        st.info("No Gantt data available to display.")
        return
    
    # Filter out rows without dates for visualization
    gantt_filtered = gantt_data[gantt_data['StartDate'].notna()].copy()
    
    if gantt_filtered.empty:
        st.info("No studies with date information available for Gantt chart.")
        return
    
    # Sort by site and start date
    gantt_filtered = gantt_filtered.sort_values(['Site', 'StartDate'])
    
    # Create figure using timeline approach with shapes
    fig = go.Figure()
    
    # Create y-axis labels
    gantt_filtered['Label'] = gantt_filtered.apply(lambda row: f"{row['Site']} - {row['Study']}", axis=1)
    y_labels = gantt_filtered['Label'].tolist()
    y_positions = list(range(len(y_labels)))
    
    # Add shapes for Gantt bars
    for idx, (_, row) in enumerate(gantt_filtered.iterrows()):
        start = row['StartDate']
        if pd.isna(start):
            continue
        
        end = row['EndDate'] if pd.notna(row['EndDate']) else start + timedelta(days=30)  # Default 30 days if no end
        
        # Get color based on status
        color = get_status_color(row['Status'])
        
        # Add rectangle shape for Gantt bar
        fig.add_shape(
            type="rect",
            x0=start,
            x1=end,
            y0=idx - 0.4,
            y1=idx + 0.4,
            fillcolor=color,
            opacity=0.7,
            line=dict(color=color, width=1),
            layer="below"
        )
        
        # Add invisible scatter trace for hover info
        fig.add_trace(go.Scatter(
            x=[start + (end - start) / 2],
            y=[idx],
            mode='markers',
            marker=dict(size=1, opacity=0),
            name=row['Study'],
            hovertemplate=(
                f"<b>{row['Study']}</b><br>"
                f"Site: {row['Site']}<br>"
                f"Status: {row['Status']}<br>"
                f"Start: {start.strftime('%d/%m/%Y')}<br>"
                f"End: {end.strftime('%d/%m/%Y') if pd.notna(row['EndDate']) else 'TBD'}<br>"
                f"Last Enrollment: {row['LastEnrollment'].strftime('%d/%m/%Y') if pd.notna(row['LastEnrollment']) else 'N/A'}<br>"
                f"<extra></extra>"
            ),
            showlegend=False
        ))
    
    # Update layout
    fig.update_layout(
        title="Gantt Chart: Studies by Site",
        xaxis_title="Timeline",
        yaxis_title="Study",
        height=max(400, len(gantt_filtered) * 40),
        xaxis=dict(
            type='date',
            showgrid=True,
            gridcolor='lightgray'
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor='lightgray',
            tickmode='array',
            tickvals=y_positions,
            ticktext=y_labels
        ),
        hovermode='closest',
        barmode='overlay'
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    # Show legend
    st.markdown("### Status Legend")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(f"<span style='color: #2ecc71; font-weight: bold;'>●</span> Active", unsafe_allow_html=True)
    with col2:
        st.markdown(f"<span style='color: #3498db; font-weight: bold;'>●</span> Contracted", unsafe_allow_html=True)
    with col3:
        st.markdown(f"<span style='color: #f39c12; font-weight: bold;'>●</span> In Setup", unsafe_allow_html=True)
    with col4:
        st.markdown(f"<span style='color: #95a5a6; font-weight: bold;'>●</span> Expression of Interest", unsafe_allow_html=True)
    
    # Show capacity summary
    st.markdown("### Site Capacity Summary")
    capacity_df = gantt_filtered.groupby('Site').agg({
        'Study': 'count',
        'Status': lambda x: (x == 'active').sum()
    }).rename(columns={'Study': 'Total Studies', 'Status': 'Active Studies'})
    capacity_df = capacity_df.reset_index()
    st.dataframe(capacity_df, use_container_width=True, hide_index=True)
