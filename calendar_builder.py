import pandas as pd
from datetime import timedelta
from helpers import safe_string_conversion, format_site_events, log_activity

def build_calendar_dataframe(visits_df, patients_df):
    """Build the basic calendar dataframe structure"""
    # Create date range
    min_date = visits_df["Date"].min() - timedelta(days=1)
    max_date = visits_df["Date"].max() + timedelta(days=1)
    calendar_dates = pd.date_range(start=min_date, end=max_date)
    calendar_df = pd.DataFrame({"Date": calendar_dates})
    calendar_df["Day"] = calendar_df["Date"].dt.day_name()

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
                    origin_site = patient_row.iloc[0]['Site']
                    col_id = f"{study}_{patient_id}"
                    
                    site_patients_info.append({
                        'col_id': col_id,
                        'study': study,
                        'patient_id': patient_id,
                        'origin_site': origin_site
                    })
        else:
            # Site has no visits - get patients recruited by this site
            log_activity(f"Site {visit_site} has no visits, checking for recruited patients", level='info')
            for candidate in ['Site', 'PatientPractice', 'PatientSite', 'OriginSite', 'Practice', 'HomeSite']:
                if candidate in patients_df.columns:
                    recruited_patients = patients_df[patients_df[candidate] == visit_site]
                    if not recruited_patients.empty:
                        log_activity(f"Found {len(recruited_patients)} patients recruited by {visit_site} via {candidate} column", level='info')
                        for _, patient in recruited_patients.iterrows():
                            patient_id = patient['PatientID']
                            study = patient['Study']
                            origin_site = patient['Site']
                            col_id = f"{study}_{patient_id}"
                            
                            site_patients_info.append({
                                'col_id': col_id,
                                'study': study,
                                'patient_id': patient_id,
                                'origin_site': origin_site
                            })
                        break  # Found the right column, stop looking
        
        # Sort by study then patient ID for consistent ordering
        site_patients_info.sort(key=lambda x: (x['study'], x['patient_id']))
        
        # Add patient columns for this visit site (avoid duplicates)
        site_columns = []
        seen_columns = set()
        for patient_info in site_patients_info:
            col_id = patient_info['col_id']
            if col_id not in seen_columns:
                ordered_columns.append(col_id)
                site_columns.append(col_id)
                calendar_df[col_id] = ""
                seen_columns.add(col_id)
            else:
                log_activity(f"Warning: Duplicate column {col_id} found for site {visit_site}. Skipping duplicate.", level='warning')
        
        # Add site events column (avoid duplicates)
        events_col = f"{visit_site}_Events"
        if events_col not in seen_columns:
            ordered_columns.append(events_col)
            site_columns.append(events_col)
            calendar_df[events_col] = ""
            seen_columns.add(events_col)
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
    # Create income tracking columns
    for study in trials_df["Study"].unique():
        income_col = f"{study} Income"
        calendar_df[income_col] = 0.0
    
    calendar_df["Daily Total"] = 0.0

    # Fill calendar with visits
    for i, row in calendar_df.iterrows():
        date = row["Date"]
        visits_today = visits_df[visits_df["Date"] == date]
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
                col_id = f"{study}_{pid}"
                
                if col_id in calendar_df.columns:
                    current_value = calendar_df.at[i, col_id]
                    
                    if current_value == "":
                        calendar_df.at[i, col_id] = visit_info
                    else:
                        # Handle multiple visits on same day
                        if visit_info in ["-", "+"]:
                            if not any(symbol in str(current_value) for symbol in ["✅", "🔴", "⚠️"]):
                                if current_value in ["-", "+", ""]:
                                    calendar_df.at[i, col_id] = visit_info
                                else:
                                    calendar_df.at[i, col_id] = f"{current_value}, {visit_info}"
                        else:
                            # This is a main visit
                            if current_value in ["-", "+", ""]:
                                calendar_df.at[i, col_id] = visit_info
                            else:
                                calendar_df.at[i, col_id] = f"{current_value}, {visit_info}"

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
        log_activity(f"Warning: Found duplicate indices in calendar DataFrame. Resetting index...", level='warning')
        calendar_df = calendar_df.reset_index(drop=True)
    
    # Check for duplicate column names
    if not calendar_df.columns.is_unique:
        log_activity(f"Warning: Found duplicate column names in calendar DataFrame. Removing duplicates...", level='warning')
        # Keep first occurrence of each column name
        calendar_df = calendar_df.loc[:, ~calendar_df.columns.duplicated()]
    
    return calendar_df
