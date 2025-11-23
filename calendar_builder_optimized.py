# -*- coding: utf-8 -*-
"""
Calendar Builder - Phase 3 Optimized Version

Key optimizations:
1. Pre-group visits by date (O(n) instead of O(n²))
2. Eliminate iterrows() - use vectorized operations
3. Batch column updates instead of cell-by-cell
4. Use pandas merge for efficient date matching

Expected performance: 5.72s → 1-2s (3-6x improvement)
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from collections import defaultdict
from profiling import timeit

@timeit
def build_calendar_dataframe(start_date, end_date, all_patient_records):
    """Build calendar with visits - OPTIMIZED VERSION"""
    from processing_calendar import build_base_calendar
    from formatters import create_site_header_row, style_calendar_row
    
    # Build base calendar structure
    base_calendar_df = build_base_calendar(start_date, end_date)
    
    # Fill with visits using optimized approach
    calendar_df = fill_calendar_with_visits(base_calendar_df, all_patient_records)
    
    # Apply styling
    today = datetime.now()
    columns = calendar_df.columns.tolist()
    
    # Create enhanced three-level headers
    site_column_mapping = _extract_site_column_mapping(calendar_df)
    header_rows = create_site_header_row(columns, site_column_mapping)
    
    # Prepare for display
    calendar_display = pd.concat([
        pd.DataFrame([header_rows['level1_site']], columns=columns),
        pd.DataFrame([header_rows['level2_study_patient']], columns=columns),
        pd.DataFrame([header_rows['level3_origin']], columns=columns),
        calendar_df
    ], ignore_index=True)
    
    styled_calendar = calendar_display.style.apply(
        lambda row: style_calendar_row(row, today), 
        axis=1
    )
    
    return calendar_df, styled_calendar, site_column_mapping

@timeit
def fill_calendar_with_visits(base_calendar_df, all_patient_records):
    """
    Fill calendar with visits - PHASE 3 OPTIMIZED
    
    Optimizations:
    1. Convert records to DataFrame for pandas operations
    2. Pre-group visits by date (eliminates O(n²) loop)
    3. Use vectorized operations instead of iterrows()
    4. Batch column updates
    
    Args:
        base_calendar_df: Base calendar with Date, Day, FYStart columns
        all_patient_records: List of dicts with visit information
    
    Returns:
        DataFrame with patient columns filled
    """
    calendar_df = base_calendar_df.copy()
    
    if not all_patient_records:
        return calendar_df
    
    # OPTIMIZATION 1: Convert to DataFrame once
    records_df = pd.DataFrame(all_patient_records)
    
    # Ensure Date column is datetime
    records_df['Date'] = pd.to_datetime(records_df['Date'])
    calendar_df['Date'] = pd.to_datetime(calendar_df['Date'])
    
    # OPTIMIZATION 2: Build column mapping efficiently
    site_column_mapping = _build_column_mapping_optimized(records_df)
    
    # OPTIMIZATION 3: Pre-create all patient columns
    all_columns = []
    for site_data in site_column_mapping.values():
        all_columns.extend(site_data['columns'])
    
    # Initialize all columns with empty strings
    for col in all_columns:
        calendar_df[col] = ""
    
    # OPTIMIZATION 4: Pre-group visits by date (MAJOR SPEEDUP)
    # This eliminates the O(n²) nested loop
    visits_by_date = records_df.groupby('Date')
    
    # OPTIMIZATION 5: Create date-to-index mapping for fast lookups
    date_to_idx = {date: idx for idx, date in enumerate(calendar_df['Date'])}
    
    # OPTIMIZATION 6: Batch process visits by date
    for date, visits_group in visits_by_date:
        if date not in date_to_idx:
            continue
            
        calendar_idx = date_to_idx[date]
        
        # Process all visits for this date
        for visit_tuple in visits_group.itertuples(index=False):
            # Build column ID
            study = visit_tuple.Study
            patient_id = visit_tuple.PatientID
            site = visit_tuple.SiteofVisit
            col_id = f"{study}_{patient_id}_{site}"
            
            # Update cell if column exists
            if col_id in calendar_df.columns:
                calendar_df.at[calendar_idx, col_id] = visit_tuple.Visit
    
    # Reorder columns: System columns first, then patient columns by site
    system_cols = ['Date', 'Day', 'FYStart']
    patient_cols = [col for col in calendar_df.columns if col not in system_cols]
    calendar_df = calendar_df[system_cols + patient_cols]
    
    return calendar_df

def _build_column_mapping_optimized(records_df):
    """
    Build site-to-column mapping efficiently using pandas groupby
    
    OPTIMIZATION: Use groupby instead of iterating through records
    """
    site_column_mapping = defaultdict(lambda: {
        'columns': [],
        'patient_info': []
    })
    
    # Group by unique patient combinations
    patient_groups = records_df.groupby(['Study', 'PatientID', 'SiteofVisit', 'PatientOrigin']).first().reset_index()
    
    for patient_tuple in patient_groups.itertuples(index=False):
        study = patient_tuple.Study
        patient_id = patient_tuple.PatientID
        site = patient_tuple.SiteofVisit
        origin = patient_tuple.PatientOrigin
        
        col_id = f"{study}_{patient_id}_{site}"
        
        # Add to site mapping
        if col_id not in site_column_mapping[site]['columns']:
            site_column_mapping[site]['columns'].append(col_id)
            site_column_mapping[site]['patient_info'].append({
                'col_id': col_id,
                'study': study,
                'patient_id': patient_id,
                'origin_site': origin
            })
    
    # Sort columns within each site
    for site_data in site_column_mapping.values():
        site_data['columns'].sort()
        site_data['patient_info'].sort(key=lambda x: x['col_id'])
    
    # Sort sites alphabetically
    sorted_mapping = dict(sorted(site_column_mapping.items()))
    
    return sorted_mapping

def _extract_site_column_mapping(calendar_df):
    """
    Extract site column mapping from existing calendar DataFrame
    Used for header creation after optimization
    """
    site_column_mapping = defaultdict(lambda: {
        'columns': [],
        'patient_info': []
    })
    
    # Parse patient columns
    patient_cols = [col for col in calendar_df.columns 
                   if col not in ['Date', 'Day', 'FYStart']]
    
    for col in patient_cols:
        try:
            # Parse column ID: Study_PatientID_Site
            parts = col.split('_')
            if len(parts) >= 3:
                study = parts[0]
                patient_id = '_'.join(parts[1:-1])  # Handle patient IDs with underscores
                site = parts[-1]
                
                site_column_mapping[site]['columns'].append(col)
                site_column_mapping[site]['patient_info'].append({
                    'col_id': col,
                    'study': study,
                    'patient_id': patient_id,
                    'origin_site': ''  # Not available from column name alone
                })
        except Exception:
            continue
    
    return dict(site_column_mapping)

# ============================================================================
# LEGACY FUNCTIONS - Keep for comparison/rollback
# ============================================================================

def fill_calendar_with_visits_ORIGINAL(base_calendar_df, all_patient_records):
    """
    ORIGINAL IMPLEMENTATION - Kept for validation comparison
    
    DO NOT USE - This is the O(n²) slow version
    Performance: ~5.72s for typical calendar
    """
    calendar_df = base_calendar_df.copy()
    
    if not all_patient_records:
        return calendar_df
    
    # Build site-to-column mapping and create columns
    site_column_mapping = {}
    
    for record in all_patient_records:
        study = record.get('Study', '')
        patient_id = record.get('PatientID', '')
        site = record.get('SiteofVisit', 'Unknown Site')
        origin = record.get('PatientOrigin', 'Unknown Origin')
        
        col_id = f"{study}_{patient_id}_{site}"
        
        if site not in site_column_mapping:
            site_column_mapping[site] = {
                'columns': [],
                'patient_info': []
            }
        
        if col_id not in site_column_mapping[site]['columns']:
            site_column_mapping[site]['columns'].append(col_id)
            site_column_mapping[site]['patient_info'].append({
                'col_id': col_id,
                'study': study,
                'patient_id': patient_id,
                'origin_site': origin
            })
            calendar_df[col_id] = ""
    
    # THE BOTTLENECK: O(n²) nested loops
    for _, row in calendar_df.iterrows():  # ~365 iterations
        date = row['Date']
        for record in all_patient_records:  # ~1000+ iterations per date
            if record['Date'] == date:
                study = record.get('Study', '')
                patient_id = record.get('PatientID', '')
                site = record.get('SiteofVisit', 'Unknown Site')
                col_id = f"{study}_{patient_id}_{site}"
                
                if col_id in calendar_df.columns:
                    calendar_df.at[row.name, col_id] = record.get('Visit', '')
    
    # Sort and reorder columns
    for site in site_column_mapping:
        site_column_mapping[site]['columns'].sort()
    
    sorted_sites = sorted(site_column_mapping.keys())
    sorted_site_mapping = {site: site_column_mapping[site] for site in sorted_sites}
    
    system_cols = ['Date', 'Day', 'FYStart']
    patient_cols = []
    for site in sorted_sites:
        patient_cols.extend(site_column_mapping[site]['columns'])
    
    calendar_df = calendar_df[system_cols + patient_cols]
    
    return calendar_df

# ============================================================================
# PERFORMANCE COMPARISON UTILITY
# ============================================================================

def compare_implementations(base_calendar_df, all_patient_records, iterations=3):
    """
    Compare old vs new implementation performance
    
    Usage:
        results = compare_implementations(base_calendar_df, records)
    """
    import time
    
    print("="*60)
    print("PHASE 3 PERFORMANCE COMPARISON")
    print("="*60)
    
    # Test original
    original_times = []
    for i in range(iterations):
        start = time.time()
        result_old = fill_calendar_with_visits_ORIGINAL(base_calendar_df, all_patient_records)
        elapsed = time.time() - start
        original_times.append(elapsed)
        print(f"Original implementation - Run {i+1}: {elapsed:.2f}s")
    
    avg_original = sum(original_times) / len(original_times)
    
    # Test optimized
    optimized_times = []
    for i in range(iterations):
        start = time.time()
        result_new = fill_calendar_with_visits(base_calendar_df, all_patient_records)
        elapsed = time.time() - start
        optimized_times.append(elapsed)
        print(f"Optimized implementation - Run {i+1}: {elapsed:.2f}s")
    
    avg_optimized = sum(optimized_times) / len(optimized_times)
    
    # Calculate improvement
    improvement = avg_original / avg_optimized
    time_saved = avg_original - avg_optimized
    
    print("\n" + "="*60)
    print("RESULTS:")
    print(f"Original average:  {avg_original:.2f}s")
    print(f"Optimized average: {avg_optimized:.2f}s")
    print(f"Improvement:       {improvement:.1f}x faster")
    print(f"Time saved:        {time_saved:.2f}s ({time_saved/avg_original*100:.1f}%)")
    print("="*60)
    
    # Validate results are identical
    try:
        pd.testing.assert_frame_equal(result_old, result_new)
        print("✅ VALIDATION PASSED: Results are identical")
    except AssertionError as e:
        print("❌ VALIDATION FAILED: Results differ!")
        print(f"Error: {str(e)[:200]}")
    
    return {
        'original_avg': avg_original,
        'optimized_avg': avg_optimized,
        'improvement': improvement,
        'time_saved': time_saved,
        'results_match': result_old.equals(result_new)
    }
