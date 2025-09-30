import pandas as pd
from datetime import timedelta
from helpers import safe_string_conversion, format_site_events, log_activity

def build_calendar_dataframe(visits_df, patients_df):
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
        # Fallback: use patient start dates to create a reasonable date range
        if not patients_df.empty and 'StartDate' in patients_df.columns:
            patient_min = patients_df["StartDate"].min()
            patient_max = patients_df["StartDate"].max()
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
    
    calendar_dates = pd.date_range(start=min_date, end=max_date)
    calendar_df = pd.DataFrame({"Date": calendar_dates})
    calendar_df["Day"] = calendar_df["Date"].dt.day_name()
    
    log_activity(f"Created calendar with date range: {min_date} to {max_date} ({len(calendar_dates)} days)", level='info')

    # Group patients by visit site for three-level headers
    patients_df["ColumnID"] = patients_df["Study"] + "_" + patients_df["PatientID"]
    
    # Get unique visit sites (filter out None values)
    site_values = visits_df["SiteofVisit"].dropna().unique()
    
    # Also include sites that have recruited patients (even if they have no visits)
    patient_sites = set()
    for candidate in ['Site', 'PatientPractice', 'PatientSite', 'OriginSite', 'Practice', 'HomeSite']:
        if candidate in patients_df.columns:
            patient_sites.update(patients_df[candidate].dropna().unique())
    
    # Combine visit sites and patient recruitment sites
    all_sites = set(site_values) | patient_sites
    unique_visit_sites = sorted([site for site in all_sites if site and str(site) != 'nan'])
    
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
            log_activity(f"Processing {len(unique_patient_studies)} unique patient-study combinations for site {visit_site}", level='info')
            
            for patient_study in unique_patient_studies.itertuples():
                patient_id = patient_study.PatientID
                study = patient_study.Study
                
                # Skip study event pseudo-patients
                if patient_id.startswith(('SIV_', 'MONITOR_')):
                    continue
                
                patient_row = patients_df[
                    (patients_df['PatientID'] == patient_id) & 
                    (patients_df['Study'] == study)
                ]
                
                if not patient_row.empty:
                    # Try to get origin site from various possible columns
                    origin_site = ""
                    for candidate in ['Site', 'PatientPractice', 'PatientSite', 'OriginSite', 'Practice', 'HomeSite']:
                        if candidate in patient_row.columns and not pd.isna(patient_row.iloc[0][candidate]):
                            origin_site = str(patient_row.iloc[0][candidate]).strip()
                            if origin_site and origin_site != 'nan':
                                break
                    
                    # If still empty, use a default
                    if not origin_site:
                        origin_site = "Unknown Origin"
                    
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

def fill_calendar_with_visits(calendar_df, visits_df, trials_df):
    """Fill the calendar with visit information"""
    
    # DEBUG: Check visits data
    log_activity(f"Filling calendar with {len(visits_df)} visits", level='info')
    
    # Debug: Check for actual visits
    if 'IsActual' in visits_df.columns:
        actual_count = len(visits_df[visits_df['IsActual'] == True])
        log_activity(f"DEBUG: Found {actual_count} actual visits in visits_df", level='info')
        
        # NEW: Show ALL actual visits before placing them
        actual_visits = visits_df[visits_df['IsActual'] == True].copy()
        for idx, actual in actual_visits.iterrows():
            log_activity(f"  Actual visit to place: {actual['Study']}_{actual['PatientID']} - {actual['Visit']} on {actual['Date'].strftime('%Y-%m-%d')}", level='info')
        
    else:
        log_activity(f"DEBUG: No IsActual column in visits_df", level='warning')
    
    # Create income tracking columns
    for study in trials_df["Study"].unique():
        income_col = f"{study} Income"
        calendar_df[income_col] = 0.0
    
    calendar_df["Daily Total"] = 0.0

    # Fill calendar with visits
    for i, row in calendar_df.iterrows():
        date = row["Date"]
        
        # FIX: Ensure consistent Timestamp comparison
        calendar_date = pd.Timestamp(date.date())  # Normalize to date-only Timestamp
        visits_today = visits_df[visits_df["Date"] == calendar_date]
        
        
        # DEBUG: Log matches (first few only to avoid spam)
        if len(visits_today) > 0 and i < 3:
            log_activity(f"Found {len(visits_today)} visits for {calendar_date.strftime('%Y-%m-%d')}", level='info')
        daily_total = 0.0

        # Group events by site for the events columns
        site_events = {}

        for _, visit in visits_today.iterrows():
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
                event_display = f"{event_type}_{study_name}"
                if "PROPOSED" in visit_info:
                    event_display += " (PROPOSED)"
                elif "CANCELLED" in visit_info:
                    event_display += " (CANCELLED)"
                else:
                    event_display = f"✅ {event_display}"
                
                site_events[visit_site].append(event_display)
                
                # Add to study income
                income_col = f"{study_name} Income"
                if income_col in calendar_df.columns and payment > 0:
                    calendar_df.at[i, income_col] += payment
                    daily_total += payment

            else:
                # Handle regular patient visits
                base_col_id = f"{study}_{pid}"
                
                # Find the actual column ID (may have site suffix)
                col_id = None
                if base_col_id in calendar_df.columns:
                    col_id = base_col_id
                else:
                    # Look for suffixed version
                    for col in calendar_df.columns:
                        if col.startswith(base_col_id + "_"):
                            col_id = col
                            break
                
                if col_id and col_id in calendar_df.columns:
                    current_value = calendar_df.at[i, col_id]
                    
                    # NEW: Log when placing actual visits
                    if is_actual:
                        log_activity(f"  Placing actual visit in col '{col_id}' on {calendar_date.strftime('%Y-%m-%d')}: '{visit_info}' (current: '{current_value}')", level='info')
                    
                    if current_value == "":
                        calendar_df.at[i, col_id] = visit_info
                        if is_actual:
                            log_activity(f"    -> Placed in empty cell", level='info')
                    else:
                        # Handle multiple visits on same day - IMPROVED LOGIC
                        
                        # If this is a tolerance marker
                        if visit_info in ["-", "+"]:
                            # Only add if there's no actual visit already there
                            if not any(symbol in str(current_value) for symbol in ["✅", "🔴", "⚠️", "📅", "📋"]):
                                if current_value in ["-", "+", ""]:
                                    calendar_df.at[i, col_id] = visit_info
                                else:
                                    calendar_df.at[i, col_id] = f"{current_value}, {visit_info}"
                        # If this is a planned visit (📅)
                        elif "📅" in visit_info and "(Planned)" in visit_info:
                            # Only add if there's no actual visit on this date
                            if not any(symbol in str(current_value) for symbol in ["✅", "🔴", "⚠️"]):
                                if current_value in ["-", "+", ""]:
                                    calendar_df.at[i, col_id] = visit_info
                                else:
                                    calendar_df.at[i, col_id] = f"{current_value}\n{visit_info}"
                        # If this is a predicted visit (📋) 
                        elif "📋" in visit_info and "(Predicted)" in visit_info:
                            # Only add if cell is empty or has tolerance markers
                            if current_value in ["-", "+", ""]:
                                calendar_df.at[i, col_id] = visit_info
                            elif not any(symbol in str(current_value) for symbol in ["✅", "🔴", "⚠️", "📅"]):
                                calendar_df.at[i, col_id] = f"{current_value}\n{visit_info}"
                        # If this is an actual visit (✅, 🔴, ⚠️)
                        else:
                            # Actual visits take priority - always add them
                            if current_value in ["-", "+", ""]:
                                calendar_df.at[i, col_id] = visit_info
                                if is_actual:
                                    log_activity(f"    -> Placed in cell with tolerance markers", level='info')
                            else:
                                # Check if there's already an actual visit
                                if any(symbol in str(current_value) for symbol in ["✅", "🔴", "⚠️"]):
                                    # Multiple actual visits on same day
                                    calendar_df.at[i, col_id] = f"{current_value}\n{visit_info}"
                                    if is_actual:
                                        log_activity(f"    -> Added to existing actual visit", level='info')
                                else:
                                    # Replace predicted/planned with actual
                                    calendar_df.at[i, col_id] = visit_info
                                    if is_actual:
                                        log_activity(f"    -> Replaced predicted/planned with actual", level='info')

                # Count payments for actual visits and scheduled main visits
                if (is_actual) or (not is_actual and visit_info not in ("-", "+")):
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
    if 'IsActual' in visits_df.columns:
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
