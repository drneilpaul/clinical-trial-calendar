# Gantt Chart Fix - 2026-01-22

## Problem

Gantt chart was not showing all studies because it was looking for the old `StartDate` column instead of the new `ScreeningDate` column.

## Root Cause

The `gantt_view.py` file had hardcoded references to `StartDate` in three locations:
1. Line 47: `get_patient_recruitment_data()` function
2. Line 134: `calculate_study_dates()` function
3. Line 359: `display_gantt_chart()` function for FY filtering

Additionally, the patient recruitment markers were counting ALL patients (including those in screening) rather than only recruited patients.

## Changes Made

### 1. Updated get_patient_recruitment_data() (Lines 30-62)

**Before:**
- Looked for `StartDate` column only
- Counted all patients regardless of status
- Used StartDate for all patients

**After:**
- ✅ Uses Status-based recruitment filtering (only recruited patients)
- ✅ Uses `RandomizationDate` for recruited patients (when they were actually recruited)
- ✅ Falls back to `ScreeningDate`, then `StartDate` for backward compatibility
- ✅ Filters for recruited statuses: `randomized`, `withdrawn`, `deceased`, `completed`, `lost_to_followup`

```python
# REFACTOR: Filter for recruited patients only (not screening/screen_failed)
if 'Status' in study_patients.columns:
    recruited_statuses = ['randomized', 'withdrawn', 'deceased', 'completed', 'lost_to_followup']
    study_patients = study_patients[study_patients['Status'].isin(recruited_statuses)]

# REFACTOR: Use RandomizationDate for recruited patients (when randomized), with fallbacks
date_column = None
if 'RandomizationDate' in study_patients.columns:
    date_column = 'RandomizationDate'
elif 'ScreeningDate' in study_patients.columns:
    date_column = 'ScreeningDate'
elif 'StartDate' in study_patients.columns:
    date_column = 'StartDate'
```

### 2. Updated calculate_study_dates() (Lines 129-148)

**Before:**
- Only checked for `StartDate` column

**After:**
- ✅ Checks for `ScreeningDate` first
- ✅ Falls back to `StartDate` if `ScreeningDate` not found
- ✅ Provides backward compatibility

```python
# REFACTOR: Use ScreeningDate (with StartDate fallback for backward compatibility)
if not study_patients.empty:
    if 'ScreeningDate' in study_patients.columns:
        start_dates = pd.to_datetime(study_patients['ScreeningDate'], errors='coerce').dropna()
    elif 'StartDate' in study_patients.columns:
        start_dates = pd.to_datetime(study_patients['StartDate'], errors='coerce').dropna()
    else:
        start_dates = pd.Series(dtype='datetime64[ns]')
```

### 3. Updated display_gantt_chart() (Lines 358-374)

**Before:**
- Hardcoded `StartDate` for FY filtering

**After:**
- ✅ Checks for `ScreeningDate` first
- ✅ Falls back to `StartDate` if needed
- ✅ Handles missing date column gracefully

```python
# REFACTOR: Use ScreeningDate (with StartDate fallback for backward compatibility)
if patients_df is not None and not patients_df.empty:
    date_column = None
    if 'ScreeningDate' in patients_df.columns:
        date_column = 'ScreeningDate'
    elif 'StartDate' in patients_df.columns:
        date_column = 'StartDate'

    if date_column:
        patients_df_dates = pd.to_datetime(patients_df[date_column], errors='coerce')
        fy_patients = patients_df[
            (patients_df_dates >= pd.Timestamp(fy_start)) &
            (patients_df_dates <= pd.Timestamp(fy_end))
        ]
```

## Impact

### What Now Works:
1. ✅ Gantt chart shows all studies with patients (uses ScreeningDate)
2. ✅ Patient recruitment markers show only recruited patients (not screening patients)
3. ✅ Recruitment numbers use RandomizationDate (actual recruitment date)
4. ✅ FY filtering works correctly with new schema
5. ✅ Backward compatibility maintained for old data with StartDate

### What Changed:
- **Patient count on Gantt**: Now shows only recruited patients, not patients in screening
- **Recruitment markers**: Now appear on RandomizationDate (V1 date) instead of ScreeningDate
- **More accurate**: Reflects true recruitment timeline, not screening timeline

## Example

**Before:**
- Patient screened on 2024-01-15 → marker appears on 2024-01-15
- Patient failed screening → still counted and shown on chart
- Patient still screening → counted as "recruited"

**After:**
- Patient screened on 2024-01-15, randomized on 2024-01-22 → marker appears on 2024-01-22
- Patient failed screening → NOT counted or shown
- Patient still screening → NOT counted as recruited

## Testing

To verify the fix works:

1. **Check Gantt shows all studies:**
   - Navigate to Gantt Chart view
   - Verify all studies from database appear
   - Verify studies with only screening patients (no recruited yet) still show timeline

2. **Check recruitment markers:**
   - Look for white circles with numbers on Gantt bars
   - Numbers should match recruited patient count, not total patient count
   - Markers should appear on randomization dates

3. **Check FY filtering:**
   - Studies with activity in current FY should appear
   - Studies with no activity should be filtered out
   - EOI/contracted studies should always appear

## Files Changed

- `gantt_view.py` - Updated 3 functions to use ScreeningDate/RandomizationDate/Status

## Related Documentation

- See `DATABASE_GUIDE.md` for full schema documentation
- See `MIGRATION_SQL.md` for database migration details
- See `REVIEW_SUMMARY.md` for overall system review

---

**Fix Date:** 2026-01-22
**Issue:** Gantt not showing all studies
**Root Cause:** Hardcoded StartDate references
**Resolution:** Updated to use ScreeningDate/RandomizationDate with Status filtering
**Status:** ✅ FIXED
