import pandas as pd
from datetime import timedelta
from helpers import safe_string_conversion, format_site_events, log_activity
from profiling import timeit

CALENDAR_DEBUG = False

def is_patient_inactive(patient_id, study, visits_df, actual_visits_df=None):
    """
    Determine if a patient is inactive (withdrawn, screen failed, or finished).
    
    Args:
        patient_id: Patient ID
        study: Study name
        visits_df: DataFrame with all visits (actual and predicted)
        actual_visits_df: Optional DataFrame with actual visits (for checking Notes)
    
    Returns:
        tuple: (is_inactive: bool, reason: str)
    """
    patient_key = f"{patient_id}_{study}"
    
    # Check for withdrawals or screen failures in actual visits
    if actual_visits_df is not None and not actual_visits_df.empty:
        patient_actuals = actual_visits_df[
            (actual_visits_df['PatientID'].astype(str) == str(patient_id)) &
            (actual_visits_df['Study'].astype(str) == str(study))
        ]
        
        if not patient_actuals.empty:
            notes_combined = ' '.join(patient_actuals['Notes'].fillna('').astype(str))
            if 'Withdrawn' in notes_combined:
                return True, 'withdrawn'
            if 'ScreenFail' in notes_combined:
                return True, 'screen_failed'
            if 'Died' in notes_combined:
                return True, 'died'
    
    # Check if patient has any predicted visits remaining
    if visits_df is not None and not visits_df.empty:
        patient_visits = visits_df[
            (visits_df['PatientID'].astype(str) == str(patient_id)) &
            (visits_df['Study'].astype(str) == str(study))
        ]
        
        if not patient_visits.empty:
            # Check if there are any predicted visits (not actual, not tolerance markers)
            predicted = patient_visits[
                (patient_visits.get('IsActual', False) == False) &
                (~patient_visits['Visit'].isin(['-', '+']))
            ]
            
            # Check if there are any proposed visits (IsProposed=True)
            is_proposed = patient_visits.get('IsProposed', False) == True if 'IsProposed' in patient_visits.columns else pd.Series([False] * len(patient_visits))
            proposed = patient_visits[is_proposed & (~patient_visits['Visit'].isin(['-', '+']))]
            
            # Patient is only "finished" if no predicted visits AND no proposed visits remain
            if predicted.empty and proposed.empty:
                return True, 'finished'
    
    return False, 'active'

@timeit
def build_calendar_dataframe(visits_df, patients_df, hide_inactive=False, actual_visits_df=None):
    """Build the basic calendar dataframe structure"""
    log_activity(f"Building calendar - visits_df empty: {visits_df.empty}, len: {len(visits_df)}", level='info')
    
    # DEBUG: Check visits_df state when calendar is built
    if not visits_df.empty:
        log_activity(f"Visits_df has data - date range: {visits_df['Date'].min()} to {visits_df['Date'].max()}", level='info')
    else:
        log_activity(f"Visits_df is empty when building calendar!", level='warning')
    
    # Create date range based on visits if available, otherwise use patient dates
    if not visits_df.empty and 'Date' in visits_df.columns and len(visits_df) > 0:
        min_date = visits_df["Date"].min() - timedelta(days=1)
        max_date = visits_df["Date"].max() + timedelta(days=1)
        log_activity(f"Using visits date range: {min_date} to {max_date}", level='info')
    else:
        # Fallback: use patient screening dates to create a reasonable date range
        if not patients_df.empty and 'ScreeningDate' in patients_df.columns:
            patient_min = patients_df["ScreeningDate"].min()
            patient_max = patients_df["ScreeningDate"].max()
            # Create a range from 30 days before first patient to 2 years after last patient
            min_date = patient_min - timedelta(days=30)
            max_date = patient_max + timedelta(days=730)  # 2 years
            log_activity(f"Using patient date range: {min_date} to {max_date}", level='info')
        else:
            # Ultimate fallback: use current date range
            from datetime import date
            today = date.today()
            min_date = today - timedelta(days=30)
            max_date = today + timedelta(days=365)
            log_activity(f"Using fallback date range: {min_date} to {max_date}", level='info')
    
    # IMPORTANT: Extend calendar range to include actual visits from database
    # This ensures all actual visits are visible even if they're outside the predicted visit range
    if not visits_df.empty and 'IsActual' in visits_df.columns:
        actual_visits = visits_df[visits_df['IsActual'] == True]
        if not actual_visits.empty and 'Date' in actual_visits.columns:
            actual_min = actual_visits["Date"].min()
            actual_max = actual_visits["Date"].max()
            
            # Extend calendar range to include all actual visits
            if actual_min < min_date:
                min_date = actual_min - timedelta(days=1)
                log_activity(f"Extended min_date to include actual visits: {min_date}", level='info')
            if actual_max > max_date:
                max_date = actual_max + timedelta(days=1)
                log_activity(f"Extended max_date to include actual visits: {max_date}", level='info')
            
            log_activity(f"Final calendar date range: {min_date} to {max_date}", level='info')
    
    calendar_dates = pd.date_range(start=min_date, end=max_date)
    calendar_df = pd.DataFrame({"Date": calendar_dates})
    calendar_df["Day"] = calendar_df["Date"].dt.day_name()
    
    log_activity(f"Created calendar with date range: {min_date} to {max_date} ({len(calendar_dates)} days)", level='info')
    

    # Group patients by visit site for three-level headers
    patients_df["ColumnID"] = patients_df["Study"] + "_" + patients_df["PatientID"]
    
    # Pre-index patient origin sites to avoid repeated DataFrame scans
    origin_candidates = ['Site', 'PatientPractice', 'PatientSite', 'OriginSite', 'Practice', 'HomeSite']
    origin_lookup = {}
    if not patients_df.empty:
        for row in patients_df.itertuples(index=False):
            patient_id = str(getattr(row, 'PatientID', '')).strip()
            study = str(getattr(row, 'Study', '')).strip()
            if not patient_id or not study:
                continue
            origin_site = ""
            for candidate in origin_candidates:
                if hasattr(row, candidate):
                    value = getattr(row, candidate)
                    if pd.notna(value):
                        value_str = str(value).strip()
                        if value_str and value_str.lower() != 'nan':
                            origin_site = value_str
                            break
            if origin_site:
                origin_lookup[(patient_id, study)] = origin_site
    
    # Get unique visit sites from actual visit data only
    # This ensures only sites that perform work get calendar sections
    
    unique_visit_sites = sorted([
        site for site in visits_df["SiteofVisit"].dropna().unique()
        if site and str(site) not in ['nan', 'Unknown Site', 'None', '', 'null', 'unknown site', 'UNKNOWN SITE', 'Default Site']
    ])
    
    # Create enhanced column structure with site events
    ordered_columns = ["Date", "Day"]
    site_column_mapping = {}
    global_seen_columns = {"Date", "Day"}  # Track all columns across all sites
    
    for visit_site in unique_visit_sites:
        site_visits = visits_df[visits_df["SiteofVisit"] == visit_site]
        site_patients_info = []
        
        # Get unique patient-study combinations at this visit site (exclude study events)
        if not site_visits.empty:
            # Site has visits - get patients from visits
            unique_patient_studies = site_visits[['PatientID', 'Study']].drop_duplicates()
            # Reduced logging - only log if CALENDAR_DEBUG is enabled
            if CALENDAR_DEBUG:
                log_activity(f"Processing {len(unique_patient_studies)} unique patient-study combinations for site {visit_site}", level='info')
            
            for patient_study in unique_patient_studies.itertuples():
                patient_id = patient_study.PatientID
                study = patient_study.Study
                
                # Skip study event pseudo-patients
                if patient_id.startswith(('SIV_', 'MONITOR_')):
                    continue
                
                # Filter inactive patients if hide_inactive is enabled
                if hide_inactive:
                    is_inactive, reason = is_patient_inactive(patient_id, study, visits_df, actual_visits_df)
                    if is_inactive:
                        log_activity(f"Filtering inactive patient {patient_id} ({study}) - reason: {reason}", level='info')
                        continue
                
                origin_site = origin_lookup.get((patient_id, study), "")
                
                # If still empty, this is a data error - skip this patient column
                if not origin_site:
                    log_activity(
                        f"⚠️ Patient {patient_id} has no valid origin site - skipping from calendar display", 
                        level='warning'
                    )
                    continue  # Skip this patient - don't add their column
                
                col_id = f"{study}_{patient_id}"
                
                site_patients_info.append({
                    'col_id': col_id,
                    'study': study,
                    'patient_id': patient_id,
                    'origin_site': origin_site
                })
        else:
            # Site has no visits - only track recruitment income, don't create visit columns
            log_activity(f"Site {visit_site} has no visits, will only track recruitment income", level='info')
            # Don't add any patient columns for sites with no visits
        
        # Sort by study then patient ID for consistent ordering
        site_patients_info.sort(key=lambda x: (x['study'], x['patient_id']))
        
        # Initialize site_columns for this site
        site_columns = []
        
        # Debug: Log patient info for this site
        # Process patients for this site
        if CALENDAR_DEBUG:
            for patient_info in site_patients_info:
                log_activity(f"  - {patient_info['col_id']} (origin: {patient_info['origin_site']})", level='info')
        
        # Add patient columns for this visit site (handle duplicates with suffixes)
        # Only process if there are patients with visits at this site
        for patient_info in site_patients_info:
            col_id = patient_info['col_id']
            final_col_id = col_id
            
            # Handle duplicates by adding site suffix
            if col_id in global_seen_columns:
                final_col_id = f"{col_id}_{visit_site}"
                if CALENDAR_DEBUG:
                    log_activity(f"Patient {col_id} appears in multiple sites. Using column name: {final_col_id}", level='info')
            
            ordered_columns.append(final_col_id)
            site_columns.append(final_col_id)
            calendar_df[final_col_id] = ""
            global_seen_columns.add(final_col_id)
            
            # Update the patient info with the final column ID
            patient_info['col_id'] = final_col_id
        
        # Add site events column (avoid duplicates) - ALL sites get events column
        events_col = f"{visit_site}_Events"
        if events_col not in global_seen_columns:
            ordered_columns.append(events_col)
            site_columns.append(events_col)
            calendar_df[events_col] = ""
            global_seen_columns.add(events_col)
        else:
            log_activity(f"Warning: Duplicate events column {events_col} found. Skipping duplicate.", level='warning')
        
        site_column_mapping[visit_site] = {
            'columns': site_columns,
            'patient_info': site_patients_info,
            'events_column': events_col
        }

    return calendar_df, site_column_mapping, unique_visit_sites

@timeit
def fill_calendar_with_visits(calendar_df, visits_df, trials_df):
    """Fill the calendar with visit information"""
    
    
    # Check for actual visits
    if 'IsActual' in visits_df.columns and CALENDAR_DEBUG:
        actual_count = len(visits_df[visits_df['IsActual'] == True])
        if actual_count > 0:
            log_activity(f"📅 Processing {actual_count} actual visits", level='info')
    
    # Create income tracking columns
    for study in trials_df["Study"].unique():
        income_col = f"{study} Income"
        calendar_df[income_col] = 0.0
    
    calendar_df["Daily Total"] = 0.0

    # OPTIMIZED: Pre-filter visits to calendar date range and group by date for fast lookup
    if visits_df.empty:
        log_activity("No visits to process", level='info')
        return calendar_df
    
    # Normalize dates to date-only for consistent comparison
    calendar_min_date = calendar_df["Date"].min()
    calendar_max_date = calendar_df["Date"].max()
    
    # Filter visits to only those in calendar range (much faster than filtering in loop)
    visits_in_range = visits_df[
        (visits_df["Date"] >= calendar_min_date) & 
        (visits_df["Date"] <= calendar_max_date)
    ].copy()
    
    # Normalize visit dates to date-only Timestamps for matching
    visits_in_range["Date"] = pd.to_datetime(visits_in_range["Date"]).dt.normalize()
    
    # Group visits by date for O(1) lookup instead of O(n) filtering in loop
    visits_by_date = {}
    for date, group in visits_in_range.groupby("Date"):
        visits_by_date[date] = group
    
    # OPTIMIZED: Pre-compute column ID mappings to avoid repeated column searches
    # Create mapping from base_col_id to actual column IDs (handles site suffixes)
    col_id_mapping = {}
    for col in calendar_df.columns:
        if col not in ["Date", "Day"] and not col.endswith("_Events") and not col.endswith(" Income") and col != "Daily Total":
            # Extract base_col_id (Study_PatientID) from column name
            if "_" in col:
                parts = col.split("_")
                if len(parts) >= 2:
                    # Try to find base pattern (Study_PatientID)
                    for i in range(1, len(parts)):
                        base_col_id = "_".join(parts[:i+1])
                        if base_col_id not in col_id_mapping:
                            col_id_mapping[base_col_id] = []
                        col_id_mapping[base_col_id].append(col)
    
    # PHASE 3 OPTIMIZATION: Create date-to-index mapping for O(1) lookup
    # This eliminates the need to iterate through calendar_df
    calendar_dates = pd.to_datetime(calendar_df['Date']).dt.normalize()
    date_to_idx = {date: idx for idx, date in enumerate(calendar_dates)}
    
    # Initialize Daily Total for all dates (dates without visits will remain 0.0)
    # Income columns are already initialized above
    
    # OPTIMIZED: Process visits by date (only iterate through dates that have visits)
    # This reduces iterations from 365 (all dates) to ~100-200 (dates with visits)
    for visit_date, visits_group in visits_by_date.items():
        if visit_date not in date_to_idx:
            continue
            
        i = date_to_idx[visit_date]
        visits_today = visits_group
        
        
        daily_total = 0.0

        # Group events by site for the events columns
        site_events = {}

        # OPTIMIZED: Use itertuples for visit iteration (faster than iterrows)
        if not visits_today.empty:
            for visit_tuple in visits_today.itertuples(index=True):
                # Convert tuple to dict-like for compatibility with existing code
                visit = visits_today.loc[visit_tuple.Index]
                study = str(visit["Study"])
                pid = str(visit["PatientID"])
                visit_info = visit["Visit"]
                payment = float(visit["Payment"]) if pd.notna(visit["Payment"]) else 0.0
                is_actual = visit.get("IsActual", False)
                visit_site = visit["SiteofVisit"]
                

                # Handle study events - FIXED: Properly handle NaN values
                is_study_event = visit.get("IsStudyEvent", False)
                # Convert NaN to False (pandas NaN evaluates to True in if statements)
                if pd.isna(is_study_event):
                    is_study_event = False
                
                if is_study_event:
                    if visit_site not in site_events:
                        site_events[visit_site] = []
                    
                    # Validate event data before formatting
                    event_type = safe_string_conversion(visit.get("EventType", "")).upper()
                    study_name = safe_string_conversion(visit.get("Study", ""))
                    
                    # Skip if essential data is missing or invalid
                    if not event_type or event_type in ['NAN', 'NONE', '']:
                        continue
                    if not study_name or study_name in ['NAN', 'NONE', ''] or study_name.upper() == 'NAN':
                        continue
                    
                    # Format event for display
                    event_display = f"✅ {event_type}_{study_name}"
                    
                    site_events[visit_site].append(event_display)
                    
                    # Add to study income
                    income_col = f"{study_name} Income"
                    if income_col in calendar_df.columns and payment > 0:
                        calendar_df.at[i, income_col] += payment
                        daily_total += payment

                else:
                    # Handle regular patient visits
                    base_col_id = f"{study}_{pid}"
                    
                    # OPTIMIZED: Use pre-computed mapping for O(1) lookup instead of O(n) search
                    col_id = None
                    if base_col_id in calendar_df.columns:
                        col_id = base_col_id
                    elif base_col_id in col_id_mapping:
                        # Use first matching column from mapping
                        col_id = col_id_mapping[base_col_id][0]
                    
                    if col_id and col_id in calendar_df.columns:
                        current_value = calendar_df.at[i, col_id]
                        
                        if current_value == "":
                            calendar_df.at[i, col_id] = visit_info
                        else:
                            # Handle multiple visits on same day - IMPROVED LOGIC
                            current_str = str(current_value)
                            has_actual = any(symbol in current_str for symbol in ["✅", "🔴", "⚠️"])
                            has_planned = "📅" in current_str
                            has_predicted = "📋" in current_str
                            has_proposed = "❓" in current_str
                            
                            # If this is a tolerance marker
                            if visit_info in ["-", "+"]:
                                # Only add if there's no actual or scheduled visit already there
                                if not (has_actual or has_planned or has_predicted):
                                    if current_value in ["-", "+", ""]:
                                        calendar_df.at[i, col_id] = visit_info
                                    else:
                                        calendar_df.at[i, col_id] = f"{current_value}, {visit_info}"
                            # If this is a planned visit (📅)
                            elif "📅" in visit_info and "(Planned)" in visit_info:
                                # Only add if there's no actual visit on this date
                                if not has_actual:
                                    if current_value in ["-", "+", ""]:
                                        calendar_df.at[i, col_id] = visit_info
                                    else:
                                        calendar_df.at[i, col_id] = f"{current_value}\n{visit_info}"
                            # If this is a proposed visit (❓)
                            elif "❓" in visit_info and "(Proposed)" in visit_info:
                                # Proposed visits can replace predicted/planned, but not actual
                                if current_value in ["-", "+", ""]:
                                    calendar_df.at[i, col_id] = visit_info
                                elif not has_actual:
                                    # Replace predicted/planned with proposed, but keep existing actual
                                    calendar_df.at[i, col_id] = visit_info
                                else:
                                    # Actual visit exists - don't replace, but can append if multiple actual visits
                                    if has_actual:
                                        calendar_df.at[i, col_id] = f"{current_value}\n{visit_info}"
                            # If this is a predicted visit (📋) 
                            elif "📋" in visit_info and "(Predicted)" in visit_info:
                                # Only add if cell is empty or has tolerance markers
                                if current_value in ["-", "+", ""]:
                                    calendar_df.at[i, col_id] = visit_info
                                elif not (has_actual or has_planned or has_proposed):
                                    calendar_df.at[i, col_id] = f"{current_value}\n{visit_info}"
                            # If this is an actual visit (✅, 🔴, ⚠️)
                            else:
                                # Actual visits take priority - always add them (replace proposed/predicted)
                                if current_value in ["-", "+", ""]:
                                    calendar_df.at[i, col_id] = visit_info
                                    if is_actual:
                                        if CALENDAR_DEBUG:
                                            log_activity(f"    -> Placed in cell with tolerance markers", level='info')
                                else:
                                    # Check if there's already an actual visit
                                    if has_actual:
                                        # Multiple actual visits on same day
                                        calendar_df.at[i, col_id] = f"{current_value}\n{visit_info}"
                                        if is_actual:
                                            if CALENDAR_DEBUG:
                                                log_activity(f"    -> Added to existing actual visit", level='info')
                                    else:
                                        # Replace predicted/proposed/planned with actual
                                        calendar_df.at[i, col_id] = visit_info
                                        if is_actual:
                                            if CALENDAR_DEBUG:
                                                log_activity(f"    -> Replaced predicted/proposed/planned with actual", level='info')
                    else:
                        # NEW: Log when column not found
                        if is_actual:
                            available_cols = [c for c in calendar_df.columns if study in c or pid in c]
                            log_activity(f"  ERROR: Could not find column for actual visit {base_col_id}. Available similar columns: {available_cols}", level='error')

                    # Count payments for actual visits and scheduled main visits
                    # CRITICAL: Exclude proposed visits from income (they're future dates, not earned yet)
                    is_proposed = visit.get('IsProposed', False)
                    if (is_actual and not is_proposed) or (not is_actual and visit_info not in ("-", "+")):
                        income_col = f"{study} Income"
                        if income_col in calendar_df.columns:
                            calendar_df.at[i, income_col] += payment
                            daily_total += payment

        # Fill site events columns
        for site, events in site_events.items():
            events_col = f"{site}_Events"
            if events_col in calendar_df.columns:
                calendar_df.at[i, events_col] = format_site_events(events)

        calendar_df.at[i, "Daily Total"] = daily_total
    
    # Check for duplicate indices before returning
    if not calendar_df.index.is_unique:
        log_activity(f"Reset duplicate indices in calendar DataFrame", level='info')
        calendar_df = calendar_df.reset_index(drop=True)
    
    # Check for duplicate column names
    if not calendar_df.columns.is_unique:
        log_activity(f"Removed duplicate column names in calendar DataFrame", level='info')
        # Keep first occurrence of each column name
        calendar_df = calendar_df.loc[:, ~calendar_df.columns.duplicated()]
    
    # Final validation: ensure no duplicate columns
    if not calendar_df.columns.is_unique:
        log_activity(f"Error: Still have duplicate columns after cleanup: {calendar_df.columns[calendar_df.columns.duplicated()].tolist()}", level='error')
        # Force unique column names by adding suffixes
        calendar_df.columns = pd.io.common.dedup_names(calendar_df.columns, is_potential_multiindex=False)
    
    # Debug: Count actual vs predicted visits placed by checking the visits_df
    if 'IsActual' in visits_df.columns and CALENDAR_DEBUG:
        total_actual = len(visits_df[visits_df['IsActual'] == True])
        total_predicted = len(visits_df[visits_df['IsActual'] == False])
        log_activity(f"Calendar filled: {total_actual} actual visits, {total_predicted} predicted visits", level='info')
        
        # Debug: Check how many actual visits ended up in the calendar
        actual_visits_in_calendar = 0
        for col in calendar_df.columns:
            if col not in ["Date", "Day"] and not col.endswith("_Events") and not col.endswith(" Income") and not col in ["Daily Total", "MonthPeriod", "Monthly Total", "FYStart", "FY Total"]:
                for val in calendar_df[col]:
                    if "✅" in str(val):
                        actual_visits_in_calendar += 1
        
        log_activity(f"DEBUG: {actual_visits_in_calendar} actual visit markers placed in calendar", level='info')
    
    return calendar_df

@timeit
def build_site_busy_calendar(visits_df, trials_df=None, actual_visits_df=None, date_range=None):
    """Build a site-busy calendar view showing all visits/events per site per day
    
    Args:
        visits_df: DataFrame with all visits (actual, predicted, proposed)
        trials_df: Optional DataFrame with trial schedules (for tolerance lookup)
        actual_visits_df: Optional DataFrame with actual visits (for Notes/DNA detection)
        date_range: Optional tuple (min_date, max_date) to limit date range
    
    Returns:
        site_busy_df: DataFrame with Date, Day, and one column per site
    """
    from datetime import date
    from helpers import log_activity
    
    if visits_df.empty:
        log_activity("No visits to build site busy calendar", level='warning')
        return pd.DataFrame(columns=['Date', 'Day'])
    
    # Determine date range
    if date_range:
        min_date, max_date = date_range
        # If max_date is None, use visits_df max date
        if max_date is None:
            max_date = visits_df["Date"].max() + timedelta(days=1)
        # Ensure min_date is not None (shouldn't happen, but be safe)
        if min_date is None:
            min_date = visits_df["Date"].min() - timedelta(days=1)
    else:
        min_date = visits_df["Date"].min() - timedelta(days=1)
        max_date = visits_df["Date"].max() + timedelta(days=1)
    
    # Create calendar date range
    calendar_dates = pd.date_range(start=min_date, end=max_date)
    site_busy_df = pd.DataFrame({"Date": calendar_dates})
    site_busy_df["Day"] = site_busy_df["Date"].dt.day_name()
    
    # Get unique sites from SiteofVisit
    unique_sites = sorted([
        site for site in visits_df["SiteofVisit"].dropna().unique()
        if site and str(site) not in ['nan', 'Unknown Site', 'None', '', 'null', 'unknown site', 'UNKNOWN SITE', 'Default Site']
    ])
    
    if not unique_sites:
        log_activity("No valid sites found for site busy calendar", level='warning')
        return site_busy_df
    
    # Initialize site columns
    for site in unique_sites:
        site_busy_df[site] = ""
    
    # Normalize dates for matching
    visits_df = visits_df.copy()
    visits_df["Date"] = pd.to_datetime(visits_df["Date"]).dt.normalize()
    site_busy_df["Date"] = pd.to_datetime(site_busy_df["Date"]).dt.normalize()
    
    # Create date-to-index mapping
    date_to_idx = {date: idx for idx, date in enumerate(site_busy_df['Date'])}
    
    # Create tolerance lookup from trials_df if available - OPTIMIZED: use itertuples
    tolerance_lookup = {}
    if trials_df is not None and not trials_df.empty:
        for trial in trials_df.itertuples(index=False):
            key = (str(getattr(trial, 'Study', '')), str(getattr(trial, 'VisitName', '')))
            tolerance_before = int(getattr(trial, 'ToleranceBefore', 0) or 0)
            tolerance_after = int(getattr(trial, 'ToleranceAfter', 0) or 0)
            tolerance_lookup[key] = (tolerance_before, tolerance_after)
    
    # Create Notes lookup from actual_visits_df if available (for DNA detection) - OPTIMIZED
    notes_lookup = {}
    if actual_visits_df is not None and not actual_visits_df.empty:
        for visit in actual_visits_df.itertuples(index=False):
            actual_date = getattr(visit, 'ActualDate', None)
            normalized_date = pd.to_datetime(actual_date).normalize() if pd.notna(actual_date) else None
            key = (
                str(getattr(visit, 'PatientID', '')),
                str(getattr(visit, 'Study', '')),
                str(getattr(visit, 'VisitName', '')),
                normalized_date
            )
            notes = str(getattr(visit, 'Notes', '') or '')
            if key[3] is not None:
                notes_lookup[key] = notes
    
    today = pd.Timestamp(date.today()).normalize()
    
    # Group visits by date and site
    for visit_date, date_group in visits_df.groupby('Date'):
        if visit_date not in date_to_idx:
            continue
        
        idx = date_to_idx[visit_date]
        
        # Group by site
        for site, site_group in date_group.groupby('SiteofVisit'):
            if site not in unique_sites:
                continue
            
            # Separate events from patient visits
            events = []
            patient_visits = []
            
            for _, visit in site_group.iterrows():
                is_study_event = visit.get('IsStudyEvent', False)
                if pd.isna(is_study_event):
                    is_study_event = False
                
                if is_study_event:
                    events.append(visit)
                else:
                    # Skip tolerance markers
                    visit_display = str(visit.get('Visit', ''))
                    if visit_display not in ['-', '+']:
                        patient_visits.append(visit)
            
            # Format and combine visits
            formatted_items = []
            
            # Format events first (at top of cell)
            for event in events:
                event_type = str(event.get('EventType', '')).upper()
                study = str(event.get('Study', ''))
                is_proposed = event.get('IsProposed', False)
                
                if is_proposed:
                    formatted_items.append(f"📅 {event_type}_{study} (Proposed)")
                else:
                    formatted_items.append(f"✅ {event_type}_{study}")
            
            # Format patient visits
            for visit in patient_visits:
                label = format_visit_label_for_site_busy(
                    visit, today, tolerance_lookup, notes_lookup
                )
                if label:
                    formatted_items.append(label)
            
            # Combine all items with newlines
            if formatted_items:
                site_busy_df.at[idx, site] = "\n".join(formatted_items)
    
    return site_busy_df

def format_visit_label_for_site_busy(visit_row, today, tolerance_lookup=None, notes_lookup=None):
    """Format a visit label for site busy view
    
    Args:
        visit_row: Series with visit data
        today: Timestamp for today's date
        tolerance_lookup: Dict mapping (Study, VisitName) -> (tolerance_before, tolerance_after)
        notes_lookup: Dict mapping (PatientID, Study, VisitName, Date) -> Notes
    
    Returns:
        Formatted label string
    """
    visit_name = str(visit_row.get('VisitName', ''))
    study = str(visit_row.get('Study', ''))
    patient_id = str(visit_row.get('PatientID', ''))
    
    if not visit_name or not study or not patient_id:
        return None
    
    visit_date = pd.to_datetime(visit_row.get('Date')).normalize() if pd.notna(visit_row.get('Date')) else None
    if visit_date is None:
        return None
    
    is_actual = visit_row.get('IsActual', False)
    is_proposed = visit_row.get('IsProposed', False)
    
    # Check for DNA in Notes
    is_dna = False
    if notes_lookup and visit_date < today and is_actual:
        lookup_key = (patient_id, study, visit_name, visit_date)
        notes = notes_lookup.get(lookup_key, '')
        if 'DNA' in str(notes).upper():
            is_dna = True
    
    # Format based on state
    if is_proposed:
        return f"📅 {visit_name} {study} {patient_id} (Proposed)"
    elif is_actual and visit_date < today:
        if is_dna:
            return f"❌ {visit_name} {study} {patient_id} DNA"
        else:
            return f"✅ {visit_name} {study} {patient_id}"
    elif not is_actual and visit_date < today:
        return f"📋 {visit_name} {study} {patient_id} ?"
    elif not is_actual and visit_date >= today:
        # Future predicted - include tolerance if available
        tolerance_str = ""
        if tolerance_lookup:
            key = (study, visit_name)
            tolerance = tolerance_lookup.get(key)
            if tolerance:
                tolerance_before, tolerance_after = tolerance
                if tolerance_before > 0 or tolerance_after > 0:
                    tolerance_str = f" +{tolerance_after} -{tolerance_before}"
        return f"📋 {visit_name} {study} {patient_id}{tolerance_str}"
    else:
        return f"✅ {visit_name} {study} {patient_id}"
