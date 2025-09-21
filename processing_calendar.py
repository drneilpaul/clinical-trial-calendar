# Add this improved section around line 180-250 in your processing_calendar.py

        # Get all actual visits for this patient - FIXED LOGIC
        patient_actual_visits = {}
        if actual_visits_df is not None:
            print(f"Looking for actual visits: PatientID='{patient_id}' AND Study='{study}'")
            
            # Use consistent string comparison
            patient_actuals = actual_visits_df[
                (actual_visits_df["PatientID"] == patient_id) & 
                (actual_visits_df["Study"] == study)
            ].sort_values('VisitNo')
            
            print(f"Found {len(patient_actuals)} actual visits for this patient")
            
            for _, actual_visit in patient_actuals.iterrows():
                visit_no = str(actual_visit["VisitNo"])
                patient_actual_visits[visit_no] = actual_visit
                print(f"  Added actual visit: VisitNo={visit_no}, Notes='{actual_visit.get('Notes', '')}'")
        
        # Process each visit with IMPROVED validation
        current_baseline_date = start_date
        current_baseline_visit = "0"
        patient_needs_recalc = False
        
        for _, visit in study_visits.iterrows():
            try:
                visit_day = int(visit["Day"])
                visit_no = str(visit.get("VisitNo", ""))
            except Exception:
                continue
            
            # Check if we have an actual visit for this visit number
            actual_visit_data = patient_actual_visits.get(visit_no)
            print(f"  Checking visit {visit_no}: actual_visit_data = {actual_visit_data is not None}")
            
            if actual_visit_data is not None:
                # This is an actual visit
                visit_date = actual_visit_data["ActualDate"]
                payment = float(actual_visit_data.get("ActualPayment") or visit.get("Payment", 0) or 0.0)
                notes = actual_visit_data.get("Notes", "")
                
                # VALIDATION: Check for impossible scenarios
                is_screen_fail = "ScreenFail" in str(notes)
                this_patient_screen_fail_key = f"{patient_id}_{study}"
                
                # Check if this visit is after a screen failure for THIS SPECIFIC PATIENT
                this_patient_screen_fail_date = screen_failures.get(this_patient_screen_fail_key)
                
                if this_patient_screen_fail_date is not None and visit_date > this_patient_screen_fail_date:
                    # DATA VALIDATION ERROR - warn instead of silently excluding
                    error_msg = (f"DATA ERROR: Patient {patient_id} has a visit on {visit_date.strftime('%Y-%m-%d')} "
                               f"AFTER their screen failure date ({this_patient_screen_fail_date.strftime('%Y-%m-%d')}). "
                               f"This should not happen - please check your data.")
                    processing_messages.append(f"⚠️ {error_msg}")
                    print(f"WARNING: {error_msg}")
                    
                    # Continue processing but mark as data error
                    visit_status = f"❌ DATA ERROR Visit {visit_no}"
                    
                else:
                    # Normal processing
                    # Calculate expected date for validation
                    if current_baseline_visit == "0":
                        expected_date = start_date + timedelta(days=visit_day)
                    else:
                        baseline_visit_data = study_visits[study_visits["VisitNo"] == current_baseline_visit]
                        if len(baseline_visit_data) > 0:
                            baseline_day = int(baseline_visit_data.iloc[0]["Day"])
                            day_diff = visit_day - baseline_day
                            expected_date = current_baseline_date + timedelta(days=day_diff)
                        else:
                            expected_date = start_date + timedelta(days=visit_day)
                    
                    # Safe tolerance handling
                    tolerance_before = 0
                    tolerance_after = 0
                    try:
                        tolerance_before = int(visit.get("ToleranceBefore", 0) or 0)
                        tolerance_after = int(visit.get("ToleranceAfter", 0) or 0)
                    except (ValueError, TypeError):
                        pass
                    
                    earliest_acceptable = expected_date - timedelta(days=tolerance_before)
                    latest_acceptable = expected_date + timedelta(days=tolerance_after)
                    
                    is_out_of_window = visit_date < earliest_acceptable or visit_date > latest_acceptable
                    if is_out_of_window:
                        days_early = max(0, (earliest_acceptable - visit_date).days)
                        days_late = max(0, (visit_date - latest_acceptable).days)
                        deviation = days_early + days_late
                        out_of_window_visits.append({
                            'patient': f"{patient_id} ({study})",
                            'visit': f"V{visit_no}",
                            'expected': expected_date.strftime('%Y-%m-%d'),
                            'actual': visit_date.strftime('%Y-%m-%d'),
                            'deviation': f"{deviation} days {'early' if days_early > 0 else 'late'}",
                            'tolerance': f"+{tolerance_after}/-{tolerance_before} days"
                        })
                    
                    # Update baseline for future calculations
                    original_scheduled_date = start_date + timedelta(days=visit_day)
                    if visit_date != original_scheduled_date:
                        patient_needs_recalc = True
                    
                    current_baseline_date = visit_date
                    current_baseline_visit = visit_no
                    
                    # Safe visit number formatting
                    try:
                        visit_no_clean = int(float(visit_no)) if pd.notna(visit_no) else visit_no
                    except:
                        visit_no_clean = visit_no
                    
                    # Use consistent emoji symbols
                    if is_screen_fail:
                        visit_status = f"❌ Screen Fail {visit_no_clean}"
                    elif is_out_of_window:
                        visit_status = f"⚠️ Visit {visit_no_clean}"
                    else:
                        visit_status = f"✅ Visit {visit_no_clean}"
                
                # Count this as a used actual visit (regardless of data errors)
                actual_visits_used += 1
                
                print(f"    Recording ACTUAL visit: {visit_status}")
                
                # Record the actual visit
                site = visit.get("SiteforVisit", "Unknown Site")
                
                visit_records.append({
                    "Date": visit_date,
                    "PatientID": patient_id,
                    "Visit": visit_status,
                    "Study": study,
                    "Payment": payment,
                    "SiteofVisit": site,
                    "PatientOrigin": patient_origin,
                    "IsActual": True,
                    "IsScreenFail": is_screen_fail,
                    "IsOutOfWindow": is_out_of_window
                })
                
            else:
                # This is a scheduled visit - check if we should skip due to screen failure
                if current_baseline_visit == "0":
                    scheduled_date = start_date + timedelta(days=visit_day)
                else:
                    baseline_visit_data = study_visits[study_visits["VisitNo"] == current_baseline_visit]
                    if len(baseline_visit_data) > 0:
                        baseline_day = int(baseline_visit_data.iloc[0]["Day"])
                        day_diff = visit_day - baseline_day
                        scheduled_date = current_baseline_date + timedelta(days=day_diff)
                    else:
                        scheduled_date = start_date + timedelta(days=visit_day)
                
                # Check if this SCHEDULED visit is after THIS PATIENT's screen failure
                this_patient_screen_fail_key = f"{patient_id}_{study}"
                this_patient_screen_fail_date = screen_failures.get(this_patient_screen_fail_key)
                
                if this_patient_screen_fail_date is not None and scheduled_date > this_patient_screen_fail_date:
                    screen_fail_exclusions += 1
                    print(f"    Skipping SCHEDULED visit {visit_no} - after patient's screen failure")
                    continue
                
                # Normal scheduled visit processing
                visit_date = scheduled_date
                payment = float(visit.get("Payment", 0) or 0.0)
                
                try:
                    visit_no_clean = int(float(visit_no)) if pd.notna(visit_no) else visit_no
                except:
                    visit_no_clean = visit_no
                
                visit_status = f"Visit {visit_no_clean}"
                
                # Safe tolerance handling
                tol_before = 0
                tol_after = 0
                try:
                    tol_before = int(visit.get("ToleranceBefore", 0) or 0)
                    tol_after = int(visit.get("ToleranceAfter", 0) or 0)
                except (ValueError, TypeError):
                    pass
                
                site = visit.get("SiteforVisit", "Unknown Site")
                
                print(f"    Recording SCHEDULED visit: {visit_status}")
                
                # Add main visit + tolerance periods
                visit_records.append({
                    "Date": visit_date,
                    "PatientID": patient_id,
                    "Visit": visit_status,
                    "Study": study,
                    "Payment": payment,
                    "SiteofVisit": site,
                    "PatientOrigin": patient_origin,
                    "IsActual": False,
                    "IsScreenFail": False,
                    "IsOutOfWindow": False
                })

                # Add tolerance periods (with same screen failure check)
                for i in range(1, tol_before + 1):
                    tolerance_date = visit_date - timedelta(days=i)
                    if this_patient_screen_fail_date is not None and tolerance_date > this_patient_screen_fail_date:
                        continue
                    visit_records.append({
                        "Date": tolerance_date,
                        "PatientID": patient_id,
                        "Visit": "-",
                        "Study": study,
                        "Payment": 0,
                        "SiteofVisit": site,
                        "PatientOrigin": patient_origin,
                        "IsActual": False,
                        "IsScreenFail": False,
                        "IsOutOfWindow": False
                    })

                for i in range(1, tol_after + 1):
                    tolerance_date = visit_date + timedelta(days=i)
                    if this_patient_screen_fail_date is not None and tolerance_date > this_patient_screen_fail_date:
                        continue
                    visit_records.append({
                        "Date": tolerance_date,
                        "PatientID": patient_id,
                        "Visit": "+",
                        "Study": study,
                        "Payment": 0,
                        "SiteofVisit": site,
                        "PatientOrigin": patient_origin,
                        "IsActual": False,
                        "IsScreenFail": False,
                        "IsOutOfWindow": False
                    })
