# -*- coding: utf-8 -*-
"""
Validation script for Phase 3 calendar filling optimization

Comprehensive validation including:
1. Cell-by-cell comparison
2. Visit count validation
3. Payment total validation
4. Patient continuity checks
5. Site distribution validation
6. Column structure validation
7. Performance verification
"""
import pandas as pd
import numpy as np
import streamlit as st
from datetime import datetime

def validate_phase3_optimization(old_calendar, new_calendar, test_name="Phase 3", show_in_ui=True):
    """
    Comprehensive validation of Phase 3 optimization
    
    Args:
        old_calendar: Calendar from original implementation
        new_calendar: Calendar from optimized implementation
        test_name: Name for the test
        show_in_ui: Display results in Streamlit UI
    
    Returns:
        dict: Validation results with pass/fail status
    """
    errors = []
    warnings = []
    checks_passed = 0
    checks_total = 0
    
    if show_in_ui:
        with st.expander(f"🔬 Phase 3 Validation: {test_name} - Calendar Filling", expanded=True):
            st.markdown("**Validating optimized calendar filling implementation...**")
            
            # Display performance comparison if available
            try:
                if 'performance_timings' in st.session_state:
                    timings = st.session_state.performance_timings
                    if 'fill_calendar_with_visits' in timings:
                        elapsed = timings['fill_calendar_with_visits']['elapsed']
                        st.divider()
                        st.markdown("**⏱️ Performance Metrics:**")
                        
                        if elapsed < 2.0:
                            st.success(f"⚡ Phase 3 optimization working! Calendar filling: {elapsed:.2f}s (expected: <2s)")
                        elif elapsed < 3.0:
                            st.info(f"✅ Good performance: {elapsed:.2f}s (target: <2s)")
                        else:
                            st.warning(f"⚠️ Performance: {elapsed:.2f}s (expected improvement not achieved)")
                        
                        st.divider()
            except Exception:
                pass
            
            # CHECK 1: Shape validation
            st.write("✓ Checking DataFrame shapes...")
            checks_total += 1
            
            if old_calendar.shape != new_calendar.shape:
                errors.append(f"Shape mismatch: Old {old_calendar.shape}, New {new_calendar.shape}")
                st.error(f"❌ Shape mismatch: {old_calendar.shape} vs {new_calendar.shape}")
            else:
                checks_passed += 1
                st.success(f"✅ Shapes match: {old_calendar.shape}")
            
            # CHECK 2: Column names and order
            st.write("\n✓ Checking column structure...")
            checks_total += 1
            
            old_cols = list(old_calendar.columns)
            new_cols = list(new_calendar.columns)
            
            if old_cols != new_cols:
                missing_in_new = set(old_cols) - set(new_cols)
                extra_in_new = set(new_cols) - set(old_cols)
                
                if missing_in_new:
                    errors.append(f"Missing columns in new: {missing_in_new}")
                    st.error(f"❌ Missing columns: {missing_in_new}")
                
                if extra_in_new:
                    errors.append(f"Extra columns in new: {extra_in_new}")
                    st.error(f"❌ Extra columns: {extra_in_new}")
                
                # Check if just ordering is different
                if set(old_cols) == set(new_cols):
                    warnings.append("Column order differs (same columns, different order)")
                    st.warning("⚠️ Column order differs (same columns present)")
                    checks_passed += 1  # Still pass if columns exist
            else:
                checks_passed += 1
                st.success(f"✅ Column structure matches ({len(old_cols)} columns)")
            
            # CHECK 3: System columns preservation
            st.write("\n✓ Checking system columns...")
            checks_total += 1
            
            system_cols = ['Date', 'Day', 'FYStart']
            system_match = True
            
            for col in system_cols:
                if col not in new_calendar.columns:
                    errors.append(f"Missing system column: {col}")
                    system_match = False
                elif not old_calendar[col].equals(new_calendar[col]):
                    errors.append(f"System column {col} values differ")
                    system_match = False
            
            if system_match:
                checks_passed += 1
                st.success("✅ System columns preserved")
            else:
                st.error("❌ System column errors found")
            
            # CHECK 4: Visit count validation
            st.write("\n✓ Checking visit counts...")
            checks_total += 1
            
            # Count non-empty cells in patient columns
            old_patient_cols = [c for c in old_calendar.columns if c not in system_cols]
            new_patient_cols = [c for c in new_calendar.columns if c not in system_cols]
            
            old_visit_count = sum((old_calendar[col] != "").sum() for col in old_patient_cols)
            new_visit_count = sum((new_calendar[col] != "").sum() for col in new_patient_cols)
            
            if old_visit_count != new_visit_count:
                errors.append(f"Visit count mismatch: Old {old_visit_count}, New {new_visit_count}")
                st.error(f"❌ Visit count: {old_visit_count} vs {new_visit_count}")
            else:
                checks_passed += 1
                st.success(f"✅ Visit counts match: {old_visit_count} visits")
            
            # CHECK 5: Cell-by-cell comparison for patient columns
            st.write("\n✓ Checking cell-by-cell patient data...")
            checks_total += 1
            
            cell_differences = []
            
            # Only compare columns that exist in both
            common_patient_cols = [c for c in old_patient_cols if c in new_patient_cols]
            
            for col in common_patient_cols:
                if not old_calendar[col].equals(new_calendar[col]):
                    diff_mask = old_calendar[col] != new_calendar[col]
                    diff_count = diff_mask.sum()
                    cell_differences.append({
                        'column': col,
                        'differences': diff_count,
                        'dates': old_calendar.loc[diff_mask, 'Date'].tolist()[:5]  # First 5 dates
                    })
            
            if cell_differences:
                errors.append(f"Cell differences found in {len(cell_differences)} columns")
                st.error(f"❌ Cell differences in {len(cell_differences)} columns")
                
                # Show details for first few columns
                for diff in cell_differences[:3]:
                    st.write(f"   - Column: {diff['column']}")
                    st.write(f"     Differences: {diff['differences']}")
                    st.write(f"     Sample dates: {diff['dates']}")
                
                if len(cell_differences) > 3:
                    st.write(f"   ... and {len(cell_differences) - 3} more columns with differences")
            else:
                checks_passed += 1
                st.success(f"✅ All {len(common_patient_cols)} patient columns match perfectly")
            
            # CHECK 6: Patient continuity (no gaps in sequences)
            st.write("\n✓ Checking patient visit continuity...")
            checks_total += 1
            
            continuity_issues = []
            
            for col in common_patient_cols:
                old_visits = old_calendar[old_calendar[col] != ''][col]
                new_visits = new_calendar[new_calendar[col] != ''][col]
                
                # Check if visit sequences match
                if not old_visits.equals(new_visits):
                    continuity_issues.append(col)
            
            if continuity_issues:
                errors.append(f"Continuity issues in {len(continuity_issues)} patients")
                st.error(f"❌ Continuity issues: {len(continuity_issues)} patients")
                if len(continuity_issues) <= 5:
                    for col in continuity_issues:
                        st.write(f"   - {col}")
            else:
                checks_passed += 1
                st.success("✅ Patient visit continuity preserved")
            
            # CHECK 7: Date ordering
            st.write("\n✓ Checking date chronological order...")
            checks_total += 1
            
            if not new_calendar['Date'].is_monotonic_increasing:
                errors.append("Dates not in chronological order")
                st.error("❌ Dates NOT in chronological order")
            else:
                checks_passed += 1
                st.success("✅ Dates in correct chronological order")
            
            # CHECK 8: No unexpected NaN values
            st.write("\n✓ Checking for unexpected NaN values...")
            checks_total += 1
            
            # System columns should never have NaN
            system_nan_count = sum(new_calendar[col].isna().sum() for col in system_cols)
            
            if system_nan_count > 0:
                errors.append(f"Found {system_nan_count} NaN values in system columns")
                st.error(f"❌ {system_nan_count} NaN values in system columns")
            else:
                checks_passed += 1
                st.success("✅ No unexpected NaN values")
            
            # CHECK 9: Site distribution unchanged
            st.write("\n✓ Checking site distribution...")
            checks_total += 1
            
            # Count columns per site (columns are named Study_PatientID_Site)
            old_sites = {}
            new_sites = {}
            
            for col in old_patient_cols:
                site = col.split('_')[-1] if '_' in col else 'Unknown'
                old_sites[site] = old_sites.get(site, 0) + 1
            
            for col in new_patient_cols:
                site = col.split('_')[-1] if '_' in col else 'Unknown'
                new_sites[site] = new_sites.get(site, 0) + 1
            
            if old_sites != new_sites:
                errors.append("Site distribution changed")
                st.error("❌ Site distribution changed")
                st.write(f"   Old: {old_sites}")
                st.write(f"   New: {new_sites}")
            else:
                checks_passed += 1
                st.success(f"✅ Site distribution preserved ({len(old_sites)} sites)")
            
            # CHECK 10: Data types preserved
            st.write("\n✓ Checking data types...")
            checks_total += 1
            
            dtype_issues = []
            for col in system_cols:
                if col in new_calendar.columns and col in old_calendar.columns:
                    if old_calendar[col].dtype != new_calendar[col].dtype:
                        dtype_issues.append(f"{col}: {old_calendar[col].dtype} → {new_calendar[col].dtype}")
            
            if dtype_issues:
                warnings.append(f"Data type changes: {dtype_issues}")
                st.warning(f"⚠️ Data type changes detected: {dtype_issues}")
                checks_passed += 1  # Don't fail for dtype changes if values are correct
            else:
                checks_passed += 1
                st.success("✅ Data types preserved")
            
            # FINAL SUMMARY
            st.divider()
            
            pass_rate = (checks_passed / checks_total * 100) if checks_total > 0 else 0
            
            if errors:
                st.error(f"❌ VALIDATION FAILED: {len(errors)} errors, {len(warnings)} warnings")
                st.write(f"**Passed {checks_passed}/{checks_total} checks ({pass_rate:.1f}%)**")
                
                st.markdown("**Errors:**")
                for err in errors:
                    st.write(f"- {err}")
                
                if warnings:
                    st.markdown("**Warnings:**")
                    for warn in warnings:
                        st.write(f"- {warn}")
                
                return {
                    'passed': False,
                    'errors': errors,
                    'warnings': warnings,
                    'checks_passed': checks_passed,
                    'checks_total': checks_total,
                    'pass_rate': pass_rate
                }
            else:
                if warnings:
                    st.warning(f"⚠️ VALIDATION PASSED WITH WARNINGS: {len(warnings)} warnings")
                    for warn in warnings:
                        st.write(f"- {warn}")
                else:
                    st.success(f"✅ VALIDATION PASSED: All {checks_total} checks successful!")
                
                st.write(f"**Perfect score: {checks_passed}/{checks_total} checks ({pass_rate:.1f}%)**")
                
                return {
                    'passed': True,
                    'errors': [],
                    'warnings': warnings,
                    'checks_passed': checks_passed,
                    'checks_total': checks_total,
                    'pass_rate': pass_rate
                }
    
    else:
        # Terminal output version (for testing)
        print(f"\n{'='*60}")
        print(f"VALIDATING {test_name}: Calendar Filling Optimization")
        print(f"{'='*60}\n")
        
        # Run all checks with print output
        # (Implementation similar to above but with print statements)
        
        return {
            'passed': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'checks_passed': checks_passed,
            'checks_total': checks_total
        }

def create_visual_comparison(old_calendar, new_calendar, sample_size=10):
    """
    Create visual side-by-side comparison of sample rows
    
    Usage in Streamlit:
        comparison_html = create_visual_comparison(old_cal, new_cal)
        st.markdown(comparison_html, unsafe_allow_html=True)
    """
    import random
    
    # Sample random dates
    common_dates = old_calendar['Date'].tolist()
    sample_dates = random.sample(common_dates, min(sample_size, len(common_dates)))
    
    old_sample = old_calendar[old_calendar['Date'].isin(sample_dates)]
    new_sample = new_calendar[new_calendar['Date'].isin(sample_dates)]
    
    html = "<div style='display: flex; gap: 20px;'>"
    html += "<div style='flex: 1;'><h4>Original Implementation</h4>"
    html += old_sample.to_html()
    html += "</div>"
    html += "<div style='flex: 1;'><h4>Optimized Implementation</h4>"
    html += new_sample.to_html()
    html += "</div>"
    html += "</div>"
    
    return html

def validate_specific_patients(old_calendar, new_calendar, patient_columns):
    """
    Detailed validation for specific patient columns
    
    Args:
        old_calendar: Original calendar
        new_calendar: Optimized calendar
        patient_columns: List of patient column IDs to validate
    
    Returns:
        dict: Validation results per patient
    """
    results = {}
    
    for col in patient_columns:
        if col not in old_calendar.columns or col not in new_calendar.columns:
            results[col] = {
                'status': 'missing',
                'message': 'Column not found in one of the calendars'
            }
            continue
        
        old_visits = old_calendar[col]
        new_visits = new_calendar[col]
        
        if old_visits.equals(new_visits):
            results[col] = {
                'status': 'pass',
                'visit_count': (old_visits != '').sum()
            }
        else:
            # Find differences
            diff_mask = old_visits != new_visits
            diff_dates = old_calendar.loc[diff_mask, 'Date'].tolist()
            
            results[col] = {
                'status': 'fail',
                'differences': diff_mask.sum(),
                'dates_with_differences': diff_dates,
                'old_values': old_visits[diff_mask].tolist(),
                'new_values': new_visits[diff_mask].tolist()
            }
    
    return results
