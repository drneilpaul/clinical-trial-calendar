# Schema Migration - Complete File Review
**Date:** 2026-01-22

## Summary

Comprehensive review and update of ALL Python files to ensure they use the new schema (ScreeningDate, RandomizationDate, Status) instead of the old StartDate column.

## Migration Overview

### Old Schema
- **StartDate** - Ambiguous date (was randomization date in old system)
- No Status tracking
- No distinction between screening and recruitment dates

### New Schema
- **ScreeningDate** - Day 1 baseline (first screening visit)
- **RandomizationDate** - Actual recruitment date (V1)
- **Status** - Patient journey tracking (8 values)
  - Not recruited: `screening`, `screen_failed`, `dna_screening`
  - Recruited: `randomized`, `withdrawn`, `deceased`, `completed`, `lost_to_followup`
- **Pathway** - Study pathway variant (standard, with_run_in, etc.)

## Files Updated in This Review

### 1. app.py ✅ UPDATED

**Changes Made:**

**Line 1005-1010: Patient date range display**
- OLD: Used `StartDate` only
- NEW: Checks for `ScreeningDate` first, falls back to `StartDate`
```python
# REFACTOR: Use ScreeningDate (with StartDate fallback for backward compatibility)
if not patients_df.empty:
    date_column = None
    if 'ScreeningDate' in patients_df.columns:
        date_column = 'ScreeningDate'
    elif 'StartDate' in patients_df.columns:
        date_column = 'StartDate'
```

**Lines 1601-1606: Recruitment dashboard filtering**
- OLD: Used `StartDate` for FY filtering
- NEW: Uses `RandomizationDate` (actual recruitment date) with fallbacks
```python
# REFACTOR: Use RandomizationDate for recruited patients, with fallbacks
date_column = None
if 'RandomizationDate' in recruitment_patients_df.columns:
    date_column = 'RandomizationDate'
elif 'ScreeningDate' in recruitment_patients_df.columns:
    date_column = 'ScreeningDate'
elif 'StartDate' in recruitment_patients_df.columns:
    date_column = 'StartDate'
```

**Lines 1636-1641: Financial dashboard filtering**
- OLD: Used `StartDate` for FY filtering
- NEW: Uses `RandomizationDate` with fallbacks

**Lines 1681-1687: UI help text**
- OLD: Listed `StartDate` as required column
- NEW: Lists `ScreeningDate` as required, `RandomizationDate`/`Status`/`Pathway` as optional

### 2. data_analysis.py ✅ UPDATED

**Lines 328-344: Patient recruitment analysis**
- OLD: Used `StartDate` for quarterly/FY recruitment analysis
- NEW: Uses `RandomizationDate` first (actual recruitment date), then `ScreeningDate`, then `StartDate`
```python
# REFACTOR: Use RandomizationDate for recruited patients, with fallbacks
date_column = None
if 'RandomizationDate' in site_patients_enhanced.columns:
    date_column = 'RandomizationDate'
elif 'ScreeningDate' in site_patients_enhanced.columns:
    date_column = 'ScreeningDate'
elif 'StartDate' in site_patients_enhanced.columns:
    date_column = 'StartDate'
```

**Impact:**
- Recruitment timing analysis now uses actual recruitment date (RandomizationDate)
- More accurate quarterly/FY recruitment counts
- Properly distinguishes between screening and recruitment dates

### 3. display_components.py ✅ UPDATED

**Lines 78-79: Financial year selector date range**
- OLD: Used only `StartDate` for patients
- NEW: Uses `ScreeningDate` first, then `StartDate` as fallback, PLUS includes `RandomizationDate`
```python
# REFACTOR: Use ScreeningDate/RandomizationDate with StartDate fallback
if patients_df is not None and not patients_df.empty:
    if 'ScreeningDate' in patients_df.columns:
        date_series.append(pd.to_datetime(patients_df['ScreeningDate'], errors='coerce'))
    elif 'StartDate' in patients_df.columns:
        date_series.append(pd.to_datetime(patients_df['StartDate'], errors='coerce'))
    if 'RandomizationDate' in patients_df.columns:
        date_series.append(pd.to_datetime(patients_df['RandomizationDate'], errors='coerce'))
```

**Impact:**
- FY selector now includes both screening and randomization dates in range calculation
- More accurate date ranges for filtering

### 4. processing_calendar.py ✅ UPDATED

**Line 148: Error message**
- OLD: `"Check that... StartDate is populated"`
- NEW: `"Check that... ScreeningDate is populated"`

**Impact:**
- Error message now correctly references the new schema

### 5. config.py ✅ UPDATED

**Lines 64-81: File structure documentation**
- OLD: Minimal docs with `StartDate`
- NEW: Comprehensive docs with all new schema fields
```python
**Patients File:**
- PatientID, Study, ScreeningDate (first screening visit, Day 1)
- PatientPractice (recruitment site - where patient comes from)
- SiteSeenAt (visit location - where patient is seen)
- Status (screening, randomized, withdrawn, completed, etc.)
- RandomizationDate (optional - when patient was randomized)
- Pathway (optional - standard, with_run_in, etc.)
```

**Impact:**
- Users now see correct schema in help text
- Explains purpose of each field

## Files Already Updated (Previous Sessions)

### 6. database.py ✅ ALREADY UPDATED
- `export_patients_to_csv()` - Exports ScreeningDate, RandomizationDate, Status, Pathway
- `export_trials_to_csv()` - Exports Pathway column
- `fetch_all_patients()` - Has fallback: `StartDate` → `ScreeningDate`
- `update_patient_status()` - New function for Status updates

### 7. gantt_view.py ✅ ALREADY UPDATED
- `get_patient_recruitment_data()` - Uses Status filtering + RandomizationDate
- `calculate_study_dates()` - Uses ScreeningDate with StartDate fallback
- `display_gantt_chart()` - Uses ScreeningDate for FY filtering

### 8. patient_processor.py ✅ ALREADY UPDATED
- Uses `ScreeningDate` as Day 1 baseline
- Has `StartDate` fallback for backward compatibility (lines 447-448)
- Updates Status on visit recording

### 9. calculations.py ✅ ALREADY UPDATED
- `calculate_recruitment_ratios()` - Uses Status-based recruitment filtering
- Uses RandomizationDate for recruited patients (lines 162-168)
- All financial functions use Status column correctly

### 10. modal_forms.py ✅ ALREADY UPDATED
- All 8 status values supported (line 314)
- Status-based recruitment counting (line 1219)
- Has intentional `StartDate` fallback logic for backward compatibility

## Files NOT Requiring Changes

### 11. processing_calendar.py
- Already optimized with caching
- Uses patient_processor.py which handles ScreeningDate correctly
- No direct StartDate references except in error message (now fixed)

### 12. database_validator.py
- Validation logic is generic and schema-agnostic
- No hardcoded column name dependencies

### 13. helpers.py
- Utility functions work with any date column
- No schema-specific logic

## Backward Compatibility Strategy

All updated files implement this fallback pattern:

```python
# Preferred: Use new schema columns
date_column = None
if 'RandomizationDate' in df.columns:  # For recruited patients
    date_column = 'RandomizationDate'
elif 'ScreeningDate' in df.columns:    # For all patients
    date_column = 'ScreeningDate'
elif 'StartDate' in df.columns:        # Legacy fallback
    date_column = 'StartDate'

if date_column:
    # Use the date column
```

**Why this works:**
- Old data with only `StartDate` → Falls back to `StartDate`
- New data with `ScreeningDate` → Uses `ScreeningDate`
- New recruited patients with `RandomizationDate` → Uses `RandomizationDate` (most accurate)

## Testing Recommendations

### 1. Test Backward Compatibility
- Upload old CSV with only `StartDate` column
- Verify system works without errors
- Verify dates display correctly

### 2. Test New Schema
- Upload new CSV with `ScreeningDate`, `RandomizationDate`, `Status`
- Verify recruitment counting uses Status correctly
- Verify Gantt chart shows all studies
- Verify financial reports use RandomizationDate

### 3. Test Mixed Data
- Database with some old patients (StartDate) and some new (ScreeningDate)
- Verify both display correctly
- Verify filtering works across both types

### 4. Test Date Filtering
- Filter by Financial Year on Recruitment dashboard
- Verify uses RandomizationDate for recruited patients
- Filter by FY on Financials page
- Verify date ranges include both screening and randomization dates

### 5. Test Documentation
- Check help text in UI shows correct columns
- Verify error messages reference ScreeningDate
- Check file upload instructions match new schema

## Verification Checklist

- [x] app.py - Updated date filtering and help text
- [x] data_analysis.py - Updated recruitment analysis to use RandomizationDate
- [x] display_components.py - Updated FY selector date range
- [x] processing_calendar.py - Updated error message
- [x] config.py - Updated file structure documentation
- [x] database.py - Already updated (previous session)
- [x] gantt_view.py - Already updated (previous session)
- [x] patient_processor.py - Already updated (previous session)
- [x] calculations.py - Already updated (previous session)
- [x] modal_forms.py - Already updated (previous session)

## Impact Summary

### What Now Works Better:

1. **More Accurate Recruitment Tracking**
   - Recruitment counts use RandomizationDate (actual recruitment date)
   - Not StartDate (which could be screening or randomization)

2. **Clearer Date Filtering**
   - Financial Year filtering uses appropriate date column
   - Recruitment dashboard uses RandomizationDate
   - Gantt chart uses ScreeningDate for study timelines

3. **Better Documentation**
   - UI help text matches actual schema
   - Error messages reference correct columns
   - File structure docs explain purpose of each field

4. **Consistent Backward Compatibility**
   - All files use same fallback pattern
   - Old data still works
   - Gradual migration supported

### What Changed for Users:

1. **Recruitment Reports**
   - Now based on RandomizationDate instead of StartDate
   - More accurate timing of when patients were actually recruited

2. **Financial Year Filtering**
   - Uses appropriate date based on context
   - Recruitment page: RandomizationDate
   - Study timeline: ScreeningDate

3. **Help Text**
   - Now shows ScreeningDate as primary date field
   - Explains optional fields (Status, RandomizationDate, Pathway)

## Files Summary

| File | Status | Changes | Impact |
|------|--------|---------|--------|
| app.py | ✅ Updated | 4 locations: date display, recruitment filter, financial filter, help text | High - User-facing |
| data_analysis.py | ✅ Updated | 1 location: recruitment analysis date column | Medium - Analytics |
| display_components.py | ✅ Updated | 1 location: FY selector date range | Medium - UI component |
| processing_calendar.py | ✅ Updated | 1 location: error message | Low - Error handling |
| config.py | ✅ Updated | 1 location: help text documentation | Medium - Documentation |
| database.py | ✅ Already Done | Export functions, status updates | High - Data layer |
| gantt_view.py | ✅ Already Done | 3 functions updated | High - Gantt chart |
| patient_processor.py | ✅ Already Done | Core processing logic | High - Critical path |
| calculations.py | ✅ Already Done | Recruitment/financial calcs | High - Analytics |
| modal_forms.py | ✅ Already Done | Status support, forms | High - Data entry |

## Completion Status

**ALL FILES REVIEWED AND UPDATED** ✅

- Total files with StartDate references: 10
- Files updated in this session: 5
- Files already updated (previous sessions): 5
- Files requiring no changes: 3+

**No remaining StartDate references that need updating.**

All files now:
1. Use ScreeningDate/RandomizationDate/Status as primary schema
2. Have appropriate StartDate fallback for backward compatibility
3. Are consistent in their approach to date column selection
4. Have correct documentation and error messages

---

**Migration Status:** ✅ COMPLETE

**Date Completed:** 2026-01-22

**Verified By:** Comprehensive grep search + systematic file-by-file review

**Next Steps:**
1. Test with old data (StartDate only)
2. Test with new data (ScreeningDate + RandomizationDate + Status)
3. Verify recruitment counts match expectations
4. Verify Gantt chart shows all studies
5. Verify financial reports use correct dates
