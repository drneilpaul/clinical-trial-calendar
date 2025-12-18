"""
Database validation utilities for clinical trial calendar
Validates data integrity on startup and after database operations
"""

import pandas as pd
from typing import Dict, List, Tuple
from helpers import log_activity, get_visit_type_series

class DatabaseValidator:
    """Validates database integrity and data quality"""
    
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.info = []
    
    def validate_all(self, patients_df, trials_df, actual_visits_df=None) -> Dict:
        """
        Run all validation checks
        
        Returns:
            Dict with structure:
            {
                'valid': bool,
                'errors': List[str],
                'warnings': List[str],
                'info': List[str],
                'error_count': int,
                'warning_count': int
            }
        """
        self.errors = []
        self.warnings = []
        self.info = []
        
        # Validate each table
        self.validate_patients_table(patients_df, trials_df)
        self.validate_trials_table(trials_df)
        if actual_visits_df is not None and not actual_visits_df.empty:
            self.validate_actual_visits_table(actual_visits_df, patients_df, trials_df)
        
        # Cross-table validation
        self.validate_cross_table_relationships(patients_df, trials_df, actual_visits_df)
        
        return {
            'valid': len(self.errors) == 0,
            'errors': self.errors,
            'warnings': self.warnings,
            'info': self.info,
            'error_count': len(self.errors),
            'warning_count': len(self.warnings)
        }
    
    def validate_patients_table(self, patients_df, trials_df):
        """Validate patients table integrity"""
        if patients_df is None or patients_df.empty:
            self.warnings.append("📋 Patients table is empty")
            return
        
        log_activity(f"🔍 Validating {len(patients_df)} patient records...", level='info')
        
        # Check 1: Valid PatientPractice (recruitment site)
        if 'PatientPractice' not in patients_df.columns:
            self.errors.append("❌ CRITICAL: PatientPractice column missing from patients table")
        else:
            invalid_sites = ['', 'nan', 'None', 'null', 'NULL', 'Unknown Site', 'unknown site', 'UNKNOWN SITE']
            patients_df['_TempPractice'] = patients_df['PatientPractice'].fillna('').astype(str).str.strip()
            invalid_mask = patients_df['_TempPractice'].isin(invalid_sites)
            
            if invalid_mask.any():
                invalid_patients = patients_df[invalid_mask]['PatientID'].tolist()
                self.errors.append(
                    f"❌ {len(invalid_patients)} patient(s) missing PatientPractice (recruitment site): "
                    f"{', '.join(map(str, invalid_patients[:5]))}"
                    + (f" and {len(invalid_patients) - 5} more" if len(invalid_patients) > 5 else "")
                )
            else:
                self.info.append(f"✅ All {len(patients_df)} patients have valid recruitment sites")
            
            # Check site value distribution
            site_counts = patients_df['PatientPractice'].value_counts()
            self.info.append(f"📊 Patient recruitment: {dict(site_counts)}")
        
        # Check 2: Valid StartDate
        if 'StartDate' not in patients_df.columns:
            self.errors.append("❌ CRITICAL: StartDate column missing from patients table")
        else:
            invalid_dates = patients_df['StartDate'].isna().sum()
            if invalid_dates > 0:
                self.warnings.append(f"⚠️ {invalid_dates} patient(s) have invalid/missing start dates")
            else:
                self.info.append(f"✅ All patients have valid start dates")
        
        # Check 3: Duplicate PatientIDs
        duplicates = patients_df['PatientID'].duplicated().sum()
        if duplicates > 0:
            duplicate_ids = patients_df[patients_df['PatientID'].duplicated()]['PatientID'].unique()
            self.errors.append(
                f"❌ {duplicates} duplicate PatientID(s) found: {', '.join(map(str, duplicate_ids[:5]))}"
            )
        else:
            self.info.append(f"✅ No duplicate PatientIDs")
        
        # Check 4: Studies exist in trials table
        if not trials_df.empty:
            patient_studies = set(patients_df['Study'].unique())
            trial_studies = set(trials_df['Study'].unique())
            missing_studies = patient_studies - trial_studies
            
            if missing_studies:
                self.errors.append(
                    f"❌ {len(missing_studies)} study/studies referenced by patients but not defined in trials: "
                    f"{', '.join(missing_studies)}"
                )
            else:
                self.info.append(f"✅ All patient studies have trial definitions")
    
    def validate_trials_table(self, trials_df):
        """Validate trials table integrity"""
        if trials_df is None or trials_df.empty:
            self.errors.append("❌ CRITICAL: Trials table is empty")
            return
        
        log_activity(f"🔍 Validating {len(trials_df)} trial schedule records...", level='info')
        
        # Check 1: Valid SiteforVisit
        if 'SiteforVisit' not in trials_df.columns:
            self.errors.append("❌ CRITICAL: SiteforVisit column missing from trials table")
        else:
            invalid_sites = ['', 'nan', 'None', 'null', 'NULL', 'Unknown Site', 'unknown site', 'UNKNOWN SITE', 'Default Site']
            trials_df['_TempSite'] = trials_df['SiteforVisit'].fillna('').astype(str).str.strip()
            invalid_mask = trials_df['_TempSite'].isin(invalid_sites)
            
            if invalid_mask.any():
                invalid_count = invalid_mask.sum()
                invalid_trials = trials_df[invalid_mask][['Study', 'VisitName']].head(5)
                self.errors.append(
                    f"❌ {invalid_count} trial visit(s) missing SiteforVisit: "
                    f"{invalid_trials.to_dict('records')}"
                )
            else:
                self.info.append(f"✅ All {len(trials_df)} trial visits have valid sites")
            
            # Check site distribution for trials
            site_counts = trials_df['SiteforVisit'].value_counts()
            self.info.append(f"📊 Trial visit sites: {dict(site_counts)}")
        
        # Check 2: Each study has exactly one Day 1 visit
        for study in trials_df['Study'].unique():
            study_visits = trials_df[trials_df['Study'] == study]
            day_1_visits = study_visits[study_visits['Day'] == 1]
            
            if len(day_1_visits) == 0:
                self.errors.append(f"❌ Study '{study}' has no Day 1 visit (baseline required)")
            elif len(day_1_visits) > 1:
                visit_names = day_1_visits['VisitName'].tolist()
                self.errors.append(
                    f"❌ Study '{study}' has multiple Day 1 visits: {visit_names} (only one allowed)"
                )
            else:
                pass  # Valid - exactly one Day 1 visit
        
        # Summary for Day 1 validation
        studies_with_valid_day1 = 0
        for study in trials_df['Study'].unique():
            day_1_count = len(trials_df[(trials_df['Study'] == study) & (trials_df['Day'] == 1)])
            if day_1_count == 1:
                studies_with_valid_day1 += 1
        
        if studies_with_valid_day1 == len(trials_df['Study'].unique()):
            self.info.append(f"✅ All {studies_with_valid_day1} studies have exactly one Day 1 baseline visit")
        
        # Check 3: Valid Payment values
        if 'Payment' in trials_df.columns:
            invalid_payments = trials_df['Payment'].isna().sum()
            negative_payments = (trials_df['Payment'] < 0).sum()
            
            if invalid_payments > 0:
                self.warnings.append(f"⚠️ {invalid_payments} trial visit(s) have invalid payment values")
            if negative_payments > 0:
                self.warnings.append(f"⚠️ {negative_payments} trial visit(s) have negative payment values")
            
            if invalid_payments == 0 and negative_payments == 0:
                total_payment = trials_df['Payment'].sum()
                self.info.append(f"✅ All payment values valid. Total trial value: £{total_payment:,.2f}")
        
        # Check 4: Duplicate Study+Day combinations
        duplicates = trials_df.duplicated(subset=['Study', 'Day', 'VisitName']).sum()
        if duplicates > 0:
            self.warnings.append(f"⚠️ {duplicates} duplicate Study+Day+Visit combination(s) found")
        else:
            self.info.append(f"✅ No duplicate visit definitions")
        
        # Check 5: Study events have valid sites
        from helpers import get_visit_type_series
        visit_types = get_visit_type_series(trials_df, default='patient')
        if not visit_types.empty:
            study_events = trials_df[visit_types.isin(['siv', 'monitor'])]
            if not study_events.empty:
                invalid_event_sites = study_events['_TempSite'].isin(invalid_sites).sum()
                if invalid_event_sites > 0:
                    self.errors.append(
                        f"❌ {invalid_event_sites} study event(s) (SIV/Monitor) missing valid SiteforVisit"
                    )
                else:
                    self.info.append(f"✅ All {len(study_events)} study events have valid sites")
    
    def validate_actual_visits_table(self, actual_visits_df, patients_df, trials_df):
        """Validate actual visits table integrity"""
        if actual_visits_df is None or actual_visits_df.empty:
            self.info.append("📋 No actual visits recorded yet")
            return
        
        log_activity(f"🔍 Validating {len(actual_visits_df)} actual visit records...", level='info')
        
        # Check 1: Valid PatientIDs
        if not patients_df.empty:
            valid_patient_ids = set(patients_df['PatientID'].astype(str))
            visit_patient_ids = set(actual_visits_df['PatientID'].astype(str))
            
            # Exclude study event pseudo-patients
            visit_patient_ids = {pid for pid in visit_patient_ids if not pid.startswith(('SIV_', 'MONITOR_'))}
            
            invalid_patients = visit_patient_ids - valid_patient_ids
            if invalid_patients:
                self.errors.append(
                    f"❌ {len(invalid_patients)} visit(s) reference unknown PatientID(s): "
                    f"{', '.join(list(invalid_patients)[:5])}"
                )
            else:
                self.info.append(f"✅ All visits reference valid patients")
        
        # Check 2: Valid Studies
        if not trials_df.empty:
            valid_studies = set(trials_df['Study'].unique())
            visit_studies = set(actual_visits_df['Study'].unique())
            invalid_studies = visit_studies - valid_studies
            
            if invalid_studies:
                self.errors.append(
                    f"❌ {len(invalid_studies)} visit(s) reference unknown study: {', '.join(invalid_studies)}"
                )
            else:
                self.info.append(f"✅ All visits reference valid studies")
        
        # Check 3: Valid VisitNames
        if not trials_df.empty:
            for _, visit in actual_visits_df.iterrows():
                study = visit['Study']
                visit_name = visit['VisitName']
                
                visit_type = get_visit_type_series(pd.DataFrame([visit]), default='patient').iloc[0]
                if visit_type in ['siv', 'monitor']:
                    continue
                
                matching = trials_df[
                    (trials_df['Study'] == study) & 
                    (trials_df['VisitName'] == visit_name)
                ]
                
                if matching.empty:
                    self.warnings.append(
                        f"⚠️ Visit '{visit_name}' for patient {visit['PatientID']} not found in {study} trial schedule"
                    )
        
        # Check 4: Valid ActualDate
        invalid_dates = actual_visits_df['ActualDate'].isna().sum()
        if invalid_dates > 0:
            self.errors.append(f"❌ {invalid_dates} visit(s) have invalid/missing ActualDate")
        else:
            self.info.append(f"✅ All visits have valid dates")
        
        # Check 5: Duplicate visits
        duplicates = actual_visits_df.duplicated(
            subset=['PatientID', 'Study', 'VisitName', 'ActualDate']
        ).sum()
        if duplicates > 0:
            self.warnings.append(f"⚠️ {duplicates} duplicate visit record(s) found")
        else:
            self.info.append(f"✅ No duplicate visits")
        
        # Check 6: Screen failures, withdrawals, and deaths
        screen_fails = actual_visits_df[
            actual_visits_df['Notes'].str.contains('ScreenFail', case=False, na=False)
        ]
        withdrawals = actual_visits_df[
            actual_visits_df['Notes'].str.contains('Withdrawn', case=False, na=False)
        ]
        deaths = actual_visits_df[
            actual_visits_df['Notes'].str.contains('Died', case=False, na=False)
        ]
        if not screen_fails.empty:
            self.info.append(f"📊 {len(screen_fails)} screen failure(s) recorded")
        if not withdrawals.empty:
            self.info.append(f"📊 {len(withdrawals)} withdrawal(s) recorded")
        if not deaths.empty:
            self.info.append(f"📊 {len(deaths)} death(s) recorded")
    
    def validate_cross_table_relationships(self, patients_df, trials_df, actual_visits_df):
        """Validate relationships between tables"""
        log_activity("🔍 Validating cross-table relationships...", level='info')
        
        # Check: All patient studies have trial schedules
        if not patients_df.empty and not trials_df.empty:
            patient_studies = set(patients_df['Study'].unique())
            trial_studies = set(trials_df['Study'].unique())
            
            studies_ok = patient_studies.issubset(trial_studies)
            if studies_ok:
                self.info.append(f"✅ All {len(patient_studies)} patient studies have complete trial schedules")
        
        # Check: Actual visits coverage
        if actual_visits_df is not None and not actual_visits_df.empty and not patients_df.empty:
            patients_with_visits = actual_visits_df['PatientID'].nunique()
            total_patients = len(patients_df)
            coverage = (patients_with_visits / total_patients * 100) if total_patients > 0 else 0
            
            self.info.append(
                f"📊 Visit coverage: {patients_with_visits}/{total_patients} patients "
                f"({coverage:.1f}%) have recorded visits"
            )


def run_startup_validation(patients_df, trials_df, actual_visits_df=None) -> Dict:
    """
    Run complete database validation on startup
    
    Returns validation results dictionary
    """
    log_activity("=" * 60, level='info')
    log_activity("🔍 DATABASE VALIDATION STARTED", level='info')
    log_activity("=" * 60, level='info')
    
    validator = DatabaseValidator()
    results = validator.validate_all(patients_df, trials_df, actual_visits_df)
    
    # Log all results
    for info_msg in results['info']:
        log_activity(info_msg, level='info')
    
    for warning_msg in results['warnings']:
        log_activity(warning_msg, level='warning')
    
    for error_msg in results['errors']:
        log_activity(error_msg, level='error')
    
    # Summary
    log_activity("=" * 60, level='info')
    if results['valid']:
        log_activity(
            f"✅ VALIDATION PASSED - {len(results['info'])} checks OK, "
            f"{results['warning_count']} warnings",
            level='success'
        )
    else:
        log_activity(
            f"❌ VALIDATION FAILED - {results['error_count']} error(s), "
            f"{results['warning_count']} warning(s)",
            level='error'
        )
    log_activity("=" * 60, level='info')
    
    return results





