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

def detect_study_phase(lpfv_date: Optional[date], lplv_date: Optional[date], today: date) -> str:
    """
    Detect if study is in follow-up phase based on LPFV and LPLV dates.
    
    Args:
        lpfv_date: Last Patient First Visit date (last enrollment)
        lplv_date: Last Patient Last Visit date (study end)
        today: Today's date
    
    Returns:
        'in_followup' if past LPFV but before LPLV, otherwise 'active'
    """
    if lpfv_date and lpfv_date < today:
        if not lplv_date or lplv_date >= today:
            return 'in_followup'
    return 'active'

def get_patient_recruitment_data(study: str, site: str, patients_df: pd.DataFrame) -> List[Tuple[date, int]]:
    """
    Get sorted list of patient recruitment dates with sequential numbers.
    
    Args:
        study: Study name
        site: Site name (PatientPractice)
        patients_df: Patients dataframe
    
    Returns:
        List of tuples: [(recruitment_date, patient_number), ...] sorted by date
    """
    study_patients = patients_df[
        (patients_df['Study'] == study) & 
        (patients_df['PatientPractice'] == site)
    ]
    
    if study_patients.empty or 'StartDate' not in study_patients.columns:
        return []
    
    # Get and sort by StartDate
    patient_dates = []
    for _, patient in study_patients.iterrows():
        start_date = pd.to_datetime(patient['StartDate'], errors='coerce')
        if pd.notna(start_date):
            patient_dates.append(start_date.date())
    
    # Sort by date and number sequentially
    patient_dates.sort()
    return [(date, idx + 1) for idx, date in enumerate(patient_dates)]

def calculate_study_dates(study: str, site: str, patients_df: pd.DataFrame, 
                         visits_df: pd.DataFrame, trials_df: pd.DataFrame) -> Dict[str, Optional[date]]:
    """
    Calculate study dates (start, end, last enrollment) for a study at a specific site.
    Prefers calculated dates, but uses FPFV/LPFV/LPLV overrides if available.
    Auto-detects "in_followup" status if past LPFV but before LPLV.
    
    Args:
        study: Study name
        site: Site name (SiteforVisit)
        patients_df: Patients dataframe
        visits_df: Visits dataframe (with Date column)
        trials_df: Trial schedules dataframe (for backward compatibility, but prefers study_site_details)
    
    Returns:
        dict with keys: 'start_date', 'end_date', 'last_enrollment', 'status', 'lpfv_date'
    """
    today = date.today()
    
    # Try to get status and date overrides from study_site_details first
    import database as db
    study_details = db.fetch_study_site_details(study, site)
    
    # Get status (default to 'active' if not found)
    status = 'active'
    fpfv_override = None
    lpfv_override = None
    lplv_override = None
    
    if study_details:
        # Use study_site_details (preferred)
        status = study_details.get('StudyStatus', 'active')
        if study_details.get('FPFV'):
            fpfv_override = pd.to_datetime(study_details['FPFV'], errors='coerce').date() if pd.notna(pd.to_datetime(study_details['FPFV'], errors='coerce')) else None
        if study_details.get('LPFV'):
            lpfv_override = pd.to_datetime(study_details['LPFV'], errors='coerce').date() if pd.notna(pd.to_datetime(study_details['LPFV'], errors='coerce')) else None
        if study_details.get('LPLV'):
            lplv_override = pd.to_datetime(study_details['LPLV'], errors='coerce').date() if pd.notna(pd.to_datetime(study_details['LPLV'], errors='coerce')) else None
    else:
        # Fallback to trial_schedules for backward compatibility
        study_trials = trials_df[(trials_df['Study'] == study) & (trials_df['SiteforVisit'] == site)] if trials_df is not None and not trials_df.empty else pd.DataFrame()
        
        if not study_trials.empty and 'StudyStatus' in study_trials.columns:
            status_values = study_trials['StudyStatus'].dropna().unique()
            if len(status_values) > 0:
                status = str(status_values[0]).lower()
        
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
    # BUT: LPFV should ONLY come from override, never calculated from patient dates
    start_date = fpfv_override
    end_date = lplv_override
    
    # Calculate start date (FPFV) from patients if override not set
    if start_date is None:
        study_patients = patients_df[
            (patients_df['Study'] == study) & 
            (patients_df['PatientPractice'] == site)
        ]
        if not study_patients.empty and 'StartDate' in study_patients.columns:
            start_dates = pd.to_datetime(study_patients['StartDate'], errors='coerce').dropna()
            if not start_dates.empty:
                start_date = start_dates.min().date()
    
    # Calculate end date (LPLV) from visits if override not set
    if end_date is None:
        study_visits = visits_df[
            (visits_df['Study'] == study) & 
            (visits_df['SiteofVisit'] == site)
        ]
        if not study_visits.empty and 'Date' in study_visits.columns:
            visit_dates = pd.to_datetime(study_visits['Date'], errors='coerce').dropna()
            if not visit_dates.empty:
                end_date = visit_dates.max().date()
    
    # LPFV should ONLY come from override in trials_df, never calculated from patient dates
    # Recruitment phase is FPFV to LPFV (if LPFV is set), otherwise show all as recruitment
    lpfv_date = lpfv_override  # Only use override, never calculate from patients
    
    return {
        'start_date': start_date,
        'end_date': end_date,
        'last_enrollment': lpfv_date,  # For backward compatibility, but should use lpfv_date
        'status': status,
        'lpfv_date': lpfv_date
    }

def build_gantt_data(patients_df: pd.DataFrame, trials_df: pd.DataFrame, 
                    visits_df: pd.DataFrame, actual_visits_df: Optional[pd.DataFrame] = None) -> Tuple[pd.DataFrame, Dict[Tuple[str, str], List[Tuple[date, int]]]]:
    """
    Build Gantt data structure grouped by site, with studies and their timelines.
    Also builds patient recruitment data for markers.
    
    Args:
        patients_df: Patients dataframe
        trials_df: Trial schedules dataframe
        visits_df: Visits dataframe (with Date column)
        actual_visits_df: Optional actual visits dataframe
    
    Returns:
        Tuple of:
        - DataFrame with columns: Site, Study, StartDate, EndDate, LastEnrollment, Status, Duration, LPFVDate, SIVDate
        - Dict mapping (Study, Site) -> List of (recruitment_date, patient_number) tuples
    """
    gantt_rows = []
    patient_recruitment_data = {}
    
    # Get unique sites from trials_df (SiteforVisit)
    if 'SiteforVisit' not in trials_df.columns:
        log_activity("No SiteforVisit column in trials_df, cannot build Gantt data", level='error')
        return pd.DataFrame(columns=['Site', 'Study', 'StartDate', 'EndDate', 'LastEnrollment', 'Status', 'Duration', 'LPFVDate', 'SIVDate']), {}
    
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
            
            # Get patient recruitment data
            recruitment_list = get_patient_recruitment_data(study, site, patients_df)
            patient_recruitment_data[(study, site)] = recruitment_list
            
            # Extract SIV date (only for active/contracted studies, not EOI)
            siv_date = None
            if dates['status'] not in ['expression_of_interest'] and actual_visits_df is not None:
                siv_date = extract_siv_dates(study, site, actual_visits_df)
            
            gantt_rows.append({
                'Site': site,
                'Study': study,
                'StartDate': dates['start_date'],
                'EndDate': dates['end_date'],
                'LastEnrollment': dates['last_enrollment'],
                'Status': dates['status'],
                'Duration': duration,
                'LPFVDate': dates['lpfv_date'],
                'SIVDate': siv_date
            })
    
    gantt_df = pd.DataFrame(gantt_rows)
    
    # Filter out rows with no dates (studies with no patients/visits yet)
    # But keep them if status is 'expression_of_interest' or 'in_setup'
    gantt_df = gantt_df[
        (gantt_df['StartDate'].notna()) | 
        (gantt_df['Status'].isin(['expression_of_interest', 'in_setup']))
    ]
    
    return gantt_df, patient_recruitment_data

def get_status_color(status: str) -> str:
    """Get color for study status"""
    status_colors = {
        'active': '#2ecc71',  # Green (for recruitment phase)
        'contracted': '#3498db',  # Blue
        'in_setup': '#f39c12',  # Orange/Yellow
        'expression_of_interest': '#95a5a6',  # Gray
        'in_followup': '#9b59b6'  # Purple (for follow-up phase)
    }
    return status_colors.get(status.lower(), '#95a5a6')

def extract_siv_dates(study: str, site: str, actual_visits_df: Optional[pd.DataFrame]) -> Optional[date]:
    """
    Extract SIV (Site Initiation Visit) date for a study at a specific site.
    
    Args:
        study: Study name
        site: Site name (SiteforVisit)
        actual_visits_df: Actual visits dataframe
    
    Returns:
        SIV date or None if not found
    """
    if actual_visits_df is None or actual_visits_df.empty:
        return None
    
    # Filter for SIV events for this study
    siv_visits = actual_visits_df[
        (actual_visits_df['Study'] == study) &
        (actual_visits_df.get('VisitType', '').astype(str).str.lower() == 'siv')
    ]
    
    if siv_visits.empty:
        return None
    
    # Get SiteforVisit from actual_visits if available, or match by site
    # SIVs may not have SiteforVisit in actual_visits, so we check if it matches
    if 'SiteforVisit' in siv_visits.columns:
        site_matched = siv_visits[siv_visits['SiteforVisit'] == site]
        if not site_matched.empty:
            siv_visits = site_matched
    
    # Get the earliest SIV date (in case there are multiple)
    if 'ActualDate' in siv_visits.columns:
        siv_dates = pd.to_datetime(siv_visits['ActualDate'], errors='coerce').dropna()
        if not siv_dates.empty:
            return siv_dates.min().date()
    
    return None

def display_gantt_chart(gantt_data: pd.DataFrame, patient_recruitment_data: Dict[Tuple[str, str], List[Tuple[date, int]]],
                       show_recruitment_overlay: bool = False, 
                       recruitment_data: Optional[pd.DataFrame] = None,
                       visits_df: Optional[pd.DataFrame] = None,
                       patients_df: Optional[pd.DataFrame] = None):
    """
    Display Gantt chart visualization using Plotly.
    
    Args:
        gantt_data: DataFrame from build_gantt_data()
        patient_recruitment_data: Dict mapping (Study, Site) -> List of (recruitment_date, patient_number) tuples
        show_recruitment_overlay: Whether to overlay recruitment progress
        recruitment_data: Optional recruitment data for overlay
    """
    if gantt_data.empty:
        st.info("No Gantt data available to display.")
        return
    
    # Filter out rows without dates for visualization (except EOI which may not have dates)
    gantt_filtered = gantt_data[
        (gantt_data['StartDate'].notna()) | 
        (gantt_data['Status'] == 'expression_of_interest')
    ].copy()
    
    if gantt_filtered.empty:
        st.info("No studies with date information available for Gantt chart.")
        return
    
    # Filter out studies with no activity in current financial year
    from helpers import get_current_financial_year_boundaries
    fy_start, fy_end = get_current_financial_year_boundaries()
    
    # Check each study for activity in current FY
    studies_with_activity = set()
    
    # Check visits_df (predicted visits) for activity in current FY
    if visits_df is not None and not visits_df.empty and 'Date' in visits_df.columns:
        visits_df_dates = pd.to_datetime(visits_df['Date'], errors='coerce')
        fy_visits = visits_df[
            (visits_df_dates >= pd.Timestamp(fy_start)) & 
            (visits_df_dates <= pd.Timestamp(fy_end))
        ]
        if not fy_visits.empty and 'Study' in fy_visits.columns:
            studies_with_activity.update(fy_visits['Study'].dropna().unique())
    
    # Check patients_df for recruitment in current FY
    if patients_df is not None and not patients_df.empty and 'StartDate' in patients_df.columns:
        patients_df_dates = pd.to_datetime(patients_df['StartDate'], errors='coerce')
        fy_patients = patients_df[
            (patients_df_dates >= pd.Timestamp(fy_start)) & 
            (patients_df_dates <= pd.Timestamp(fy_end))
        ]
        if not fy_patients.empty and 'Study' in fy_patients.columns:
            studies_with_activity.update(fy_patients['Study'].dropna().unique())
    
    # Filter: Keep studies with activity in current FY, or EOI/contracted/in_setup studies
    # (EOI, contracted, in_setup are future/potential studies and should still be shown)
    gantt_filtered = gantt_filtered[
        (gantt_filtered['Study'].isin(studies_with_activity)) |
        (gantt_filtered['Status'] == 'expression_of_interest') |
        (gantt_filtered['Status'] == 'contracted') |
        (gantt_filtered['Status'] == 'in_setup')
    ].copy()
    
    if gantt_filtered.empty:
        st.info("No studies with activity in the current financial year available for Gantt chart.")
        return
    
    # Sort: EOI at bottom, others grouped by Site, then by StartDate ascending (oldest first)
    # Separate EOI and non-EOI studies
    eoi_studies = gantt_filtered[gantt_filtered['Status'] == 'expression_of_interest'].copy()
    non_eoi_studies = gantt_filtered[gantt_filtered['Status'] != 'expression_of_interest'].copy()
    
    # Sort non-EOI by Site first (to group same site together), then by StartDate ascending
    non_eoi_studies = non_eoi_studies.sort_values(['Site', 'StartDate'], na_position='last', kind='stable')
    
    # Sort EOI by Site, then StartDate if available
    if not eoi_studies.empty:
        eoi_studies = eoi_studies.sort_values(['Site', 'StartDate'], na_position='last', kind='stable')
    
    # Combine: non-EOI first, then EOI at bottom
    gantt_filtered = pd.concat([non_eoi_studies, eoi_studies], ignore_index=True)
    
    # Create figure using timeline approach with shapes
    fig = go.Figure()
    
    # Create y-axis labels
    gantt_filtered['Label'] = gantt_filtered.apply(lambda row: f"{row['Site']} - {row['Study']}", axis=1)
    y_labels = gantt_filtered['Label'].tolist()
    y_positions = list(range(len(y_labels)))
    
    today = date.today()
    today_datetime = datetime.combine(today, datetime.min.time())
    
    # Add today's date vertical line using add_shape (works better with datetime axes)
    fig.add_shape(
        type="line",
        x0=today_datetime,
        x1=today_datetime,
        y0=-0.5,
        y1=len(y_labels) - 0.5,
        line=dict(color="#e74c3c", width=2, dash="dash"),
        layer="above"
    )
    
    # Add "Today" annotation
    fig.add_annotation(
        x=today_datetime,
        y=len(y_labels) - 0.5,
        text="Today",
        showarrow=False,
        font=dict(color="#e74c3c", size=12),
        bgcolor="white",
        bordercolor="#e74c3c",
        borderwidth=1,
        borderpad=2
    )
    
    # Collect patient marker data and SIV marker data
    patient_marker_x = []
    patient_marker_y = []
    patient_marker_text = []
    siv_marker_x = []
    siv_marker_y = []
    
    # Collect recruitment overlay data (for annotations)
    recruitment_annotations = []  # List of (x, y, text) tuples
    
    # Check if recruitment overlay is enabled and data is available
    has_recruitment_overlay = show_recruitment_overlay and recruitment_data is not None
    recruitment_status_colors = {
        'at_or_over': '#2ecc71',  # Green
        'near_target': '#f39c12',  # Yellow/Orange
        'under_target': '#e74c3c',  # Red
        'no_target': '#95a5a6'  # Gray
    }
    
    # Track previous site for visual grouping and get date range
    prev_site = None
    site_changes = []  # Track where site changes occur for separators
    min_date = None
    max_date = None
    
    # Add shapes for Gantt bars (split at LPFV if exists)
    for idx, (_, row) in enumerate(gantt_filtered.iterrows()):
        start = row['StartDate']
        status = str(row.get('Status', 'active')).lower()
        
        # Handle EOI studies without dates - use approximate dates or skip
        if pd.isna(start):
            if status == 'expression_of_interest':
                # EOI without dates - use a default short bar or skip visualization
                # For now, skip visualization if no dates
                continue
            else:
                continue
        
        end = row['EndDate'] if pd.notna(row['EndDate']) else start + timedelta(days=365)  # Default 1 year if no end
        lpfv_date = row.get('LPFVDate') if 'LPFVDate' in row else None
        siv_date = row.get('SIVDate') if 'SIVDate' in row else None
        
        # Track date range for separator lines
        if min_date is None or start < min_date:
            min_date = start
        if max_date is None or end > max_date:
            max_date = end
        
        # Get base color based on status
        base_color = get_status_color(status)
        recruitment_color = '#2ecc71'  # Green for recruitment phase
        followup_color = '#9b59b6'  # Purple for follow-up phase
        
        # Get recruitment overlay info if enabled
        recruitment_border_color = None
        recruitment_text = None
        if has_recruitment_overlay:
            # Check if recruitment columns exist in the row
            if 'Target' in row.index and 'Actual' in row.index and 'RecruitmentStatus' in row.index:
                target = row.get('Target')
                actual = row.get('Actual', 0)
                recruitment_status = row.get('RecruitmentStatus', 'no_target')
                
                # Handle NaN values
                if pd.isna(actual):
                    actual = 0
                else:
                    actual = int(actual)
                
                # Format recruitment text
                if pd.notna(target) and target > 0:
                    recruitment_text = f"{actual}/{int(target)}"
                else:
                    recruitment_text = f"{actual}/No target"
                
                # Get border color based on recruitment status
                if pd.notna(recruitment_status):
                    recruitment_border_color = recruitment_status_colors.get(str(recruitment_status).lower(), '#95a5a6')
                else:
                    recruitment_border_color = '#95a5a6'
        
        # Determine bar drawing logic based on status
        # Use recruitment border color if overlay is enabled, otherwise use base color
        bar_border_color = recruitment_border_color if (has_recruitment_overlay and recruitment_border_color) else base_color
        bar_border_width = 2 if (has_recruitment_overlay and recruitment_border_color) else 1
        
        if status == 'contracted':
            # Contracted: Single blue bar (no split)
            fig.add_shape(
                type="rect",
                x0=start,
                x1=end,
                y0=idx - 0.4,
                y1=idx + 0.4,
                fillcolor=base_color,
                opacity=0.7,
                line=dict(color=bar_border_color, width=bar_border_width),
                layer="below"
            )
        elif status == 'expression_of_interest':
            # EOI: Single gray bar (no split)
            fig.add_shape(
                type="rect",
                x0=start,
                x1=end,
                y0=idx - 0.4,
                y1=idx + 0.4,
                fillcolor=base_color,
                opacity=0.7,
                line=dict(color=bar_border_color, width=bar_border_width),
                layer="below"
            )
        elif status == 'active':
            # Active studies: Split at LPFV if exists (green recruitment, purple follow-up)
            # Even if LPFV is in future, show recruitment phase up to LPFV
            if lpfv_date and pd.notna(lpfv_date) and start <= lpfv_date:
                # First segment: StartDate to LPFV (recruitment phase - green)
                # Show this even if LPFV is in future (helps with planning)
                recruitment_end = min(lpfv_date, end)  # Don't exceed end date
                fig.add_shape(
                    type="rect",
                    x0=start,
                    x1=recruitment_end,
                    y0=idx - 0.4,
                    y1=idx + 0.4,
                    fillcolor=recruitment_color,
                    opacity=0.7,
                    line=dict(color=bar_border_color, width=bar_border_width),
                    layer="below"
                )
                
                # Second segment: LPFV to EndDate (follow-up phase - purple) - only if LPFV has passed
                if lpfv_date < today and lpfv_date < end:
                    fig.add_shape(
                        type="rect",
                        x0=lpfv_date,
                        x1=end,
                        y0=idx - 0.4,
                        y1=idx + 0.4,
                        fillcolor=followup_color,
                        opacity=0.7,
                        line=dict(color=bar_border_color, width=bar_border_width),
                        layer="below"
                    )
            else:
                # No LPFV: Single green bar (assume recruiting till end)
                fig.add_shape(
                    type="rect",
                    x0=start,
                    x1=end,
                    y0=idx - 0.4,
                    y1=idx + 0.4,
                    fillcolor=recruitment_color,
                    opacity=0.7,
                    line=dict(color=bar_border_color, width=bar_border_width),
                    layer="below"
                )
        else:
            # Other statuses (in_setup, etc.): Single bar with status color
            fig.add_shape(
                type="rect",
                x0=start,
                x1=end,
                y0=idx - 0.4,
                y1=idx + 0.4,
                fillcolor=base_color,
                opacity=0.7,
                line=dict(color=bar_border_color, width=bar_border_width),
                layer="below"
            )
        
        # Add recruitment text annotation if overlay is enabled
        if has_recruitment_overlay and recruitment_text:
            # Position annotation at the middle of the bar
            bar_center_x = start + (end - start) / 2
            bar_center_datetime = datetime.combine(bar_center_x, datetime.min.time()) if isinstance(bar_center_x, date) else bar_center_x
            recruitment_annotations.append({
                'x': bar_center_datetime,
                'y': idx,
                'text': recruitment_text,
                'color': recruitment_border_color if recruitment_border_color else '#000000'
            })
        
        # Add SIV marker if exists (only for active/contracted studies)
        if siv_date and pd.notna(siv_date) and status in ['active', 'contracted']:
            # SIV usually appears before FPFV, so show marker ahead of bar
            siv_marker_x.append(siv_date)
            siv_marker_y.append(idx)
        
        # Track site changes for visual grouping
        current_site = row['Site']
        if prev_site is not None and current_site != prev_site:
            site_changes.append(idx)
        prev_site = current_site
    
    # Add visual separators between site groups
    if min_date and max_date:
        for change_idx in site_changes:
            fig.add_shape(
                type="line",
                x0=datetime.combine(min_date, datetime.min.time()),
                x1=datetime.combine(max_date, datetime.min.time()),
                y0=change_idx - 0.5,
                y1=change_idx - 0.5,
                line=dict(color="#d0d0d0", width=1, dash="dot"),
                layer="below"
            )
        
        # Add patient recruitment markers
        study_site_key = (row['Study'], row['Site'])
        if study_site_key in patient_recruitment_data:
            for rec_date, patient_num in patient_recruitment_data[study_site_key]:
                if start <= rec_date <= end:
                    patient_marker_x.append(rec_date)
                    patient_marker_y.append(idx)
                    patient_marker_text.append(str(patient_num))
        
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
                f"Status: {status}<br>"
                f"Start: {start.strftime('%d/%m/%Y')}<br>"
                f"End: {end.strftime('%d/%m/%Y') if pd.notna(row['EndDate']) else 'TBD'}<br>"
                f"Last Enrollment: {row['LastEnrollment'].strftime('%d/%m/%Y') if pd.notna(row['LastEnrollment']) else 'N/A'}<br>"
                f"LPFV: {lpfv_date.strftime('%d/%m/%Y') if lpfv_date and pd.notna(lpfv_date) else 'N/A'}<br>"
                f"<extra></extra>"
            ),
            showlegend=False
        ))
    
    # Add patient recruitment markers as scatter plot
    if patient_marker_x:
        # Convert date objects to datetime for Plotly
        patient_marker_x_datetime = [datetime.combine(d, datetime.min.time()) if isinstance(d, date) else d for d in patient_marker_x]
        fig.add_trace(go.Scatter(
            x=patient_marker_x_datetime,
            y=patient_marker_y,
            mode='markers+text',
            marker=dict(
                size=8,
                color='white',
                line=dict(color='black', width=1),
                opacity=0.9
            ),
            text=patient_marker_text,
            textposition="middle center",
            textfont=dict(size=8, color='black'),
            name='Patient Recruitment',
            hovertemplate='Patient #%{text}<br>Recruited: %{x|%d/%m/%Y}<extra></extra>',
            showlegend=False
        ))
    
    # Add SIV markers as icons before FPFV
    if siv_marker_x:
        # Convert date objects to datetime for Plotly
        siv_marker_x_datetime = [datetime.combine(d, datetime.min.time()) if isinstance(d, date) else d for d in siv_marker_x]
        fig.add_trace(go.Scatter(
            x=siv_marker_x_datetime,
            y=siv_marker_y,
            mode='markers',
            marker=dict(
                size=12,
                symbol='star',
                color='#e67e22',  # Orange color for SIV
                line=dict(color='white', width=1),
                opacity=0.9
            ),
            name='SIV',
            hovertemplate='SIV (Site Initiation Visit)<br>Date: %{x|%d/%m/%Y}<extra></extra>',
            showlegend=True
        ))
    
    # Add recruitment progress text annotations if overlay is enabled
    if has_recruitment_overlay and recruitment_annotations:
        for ann in recruitment_annotations:
            fig.add_annotation(
                x=ann['x'],
                y=ann['y'],
                text=ann['text'],
                showarrow=False,
                font=dict(color=ann['color'], size=10, family='Arial Black'),
                bgcolor='white',
                bordercolor=ann['color'],
                borderwidth=1,
                borderpad=3,
                xref='x',
                yref='y'
            )
    
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
    
    st.plotly_chart(fig, width='stretch')
    
    # Show legend
    st.markdown("### Status Legend")
    if has_recruitment_overlay:
        # Show recruitment overlay legend
        col1, col2, col3, col4, col5, col6 = st.columns(6)
        with col1:
            st.markdown(f"<span style='color: #2ecc71; font-weight: bold;'>●</span> Active (Recruitment)", unsafe_allow_html=True)
        with col2:
            st.markdown(f"<span style='color: #9b59b6; font-weight: bold;'>●</span> Active (Follow-Up)", unsafe_allow_html=True)
        with col3:
            st.markdown(f"<span style='color: #3498db; font-weight: bold;'>●</span> Contracted", unsafe_allow_html=True)
        with col4:
            st.markdown(f"<span style='color: #f39c12; font-weight: bold;'>●</span> In Setup", unsafe_allow_html=True)
        with col5:
            st.markdown(f"<span style='color: #95a5a6; font-weight: bold;'>●</span> Expression of Interest", unsafe_allow_html=True)
        with col6:
            st.markdown(f"<span style='color: #e67e22; font-weight: bold;'>★</span> SIV", unsafe_allow_html=True)
        
        st.markdown("### Recruitment Overlay Legend")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.markdown(f"<span style='color: #2ecc71; font-weight: bold;'>■</span> At/Over Target", unsafe_allow_html=True)
        with col2:
            st.markdown(f"<span style='color: #f39c12; font-weight: bold;'>■</span> Near Target (75-99%)", unsafe_allow_html=True)
        with col3:
            st.markdown(f"<span style='color: #e74c3c; font-weight: bold;'>■</span> Under Target (<75%)", unsafe_allow_html=True)
        with col4:
            st.markdown(f"<span style='color: #95a5a6; font-weight: bold;'>■</span> No Target Set", unsafe_allow_html=True)
        st.caption("Bar border colors indicate recruitment status. Text annotations show 'Actual/Target' (e.g., '15/20').")
    else:
        # Standard legend without recruitment overlay
        col1, col2, col3, col4, col5, col6 = st.columns(6)
        with col1:
            st.markdown(f"<span style='color: #2ecc71; font-weight: bold;'>●</span> Active (Recruitment)", unsafe_allow_html=True)
        with col2:
            st.markdown(f"<span style='color: #9b59b6; font-weight: bold;'>●</span> Active (Follow-Up)", unsafe_allow_html=True)
        with col3:
            st.markdown(f"<span style='color: #3498db; font-weight: bold;'>●</span> Contracted", unsafe_allow_html=True)
        with col4:
            st.markdown(f"<span style='color: #f39c12; font-weight: bold;'>●</span> In Setup", unsafe_allow_html=True)
        with col5:
            st.markdown(f"<span style='color: #95a5a6; font-weight: bold;'>●</span> Expression of Interest", unsafe_allow_html=True)
        with col6:
            st.markdown(f"<span style='color: #e67e22; font-weight: bold;'>★</span> SIV", unsafe_allow_html=True)
    
    # Show capacity summary
    st.markdown("### Site Capacity Summary")
    capacity_df = gantt_filtered.groupby('Site').agg({
        'Study': 'count',
        'Status': lambda x: (x == 'active').sum()
    }).rename(columns={'Study': 'Total Studies', 'Status': 'Active Studies'})
    capacity_df = capacity_df.reset_index()
    st.dataframe(capacity_df, width='stretch', hide_index=True)
