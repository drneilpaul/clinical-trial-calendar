# Overdue Visit Export Logic Fix
**Date:** 2026-01-23

## Problem

The "Overdue Predicted Visits" export was showing visits from 2022-2024 that should not be considered "overdue" because:
1. These patients had later actual visits recorded
2. If a patient came for V5 but missed V3, V3 shouldn't show as "overdue needing completion"
3. Missed visits are different from overdue visits - missed visits are in the past with later visits completed

## Example

**Before Fix:**
- Patient 38260010: V16 scheduled 01/05/2024 (shows as overdue)
- Patient 38260010: V21/FU2 completed 05/06/2024
- **Problem**: V16 shows as "overdue" even though patient already came for later visit V21/FU2

**After Fix:**
- V16 is suppressed because it's BEFORE the latest actual visit (V21/FU2)
- V16 is considered a "missed visit", not an "overdue visit"
- Only visits AFTER V21/FU2 that are before today would show as overdue

## Solution

Added **Rule 4** to predicted visit suppression logic in `patient_processor.py`:

### New Suppression Rule

```python
# Rule 4: Suppress predicted visits in the PAST if there's a LATER actual visit
# This handles "missed visits" - if patient came for V5 but missed V3, don't show V3 as overdue
elif predicted_date < today and latest_actual_date is not None:
    if predicted_date < latest_actual_date:
        should_suppress = True
        suppress_reason = f"missed visit (before latest actual visit on {latest_actual_date.strftime('%Y-%m-%d')})"
```

## Complete Suppression Logic

The system now has 4 rules for suppressing predicted visits:

### Rule 1: Proposed Visit Exists
- If a predicted visit name matches a proposed (future) visit, suppress the predicted one
- Example: V-EOT scheduled for Feb 10, but proposed for Mar 15 → suppress Feb 10 predicted

### Rule 2: Between Today and Latest Proposed
- Suppress ALL predicted visits between today and the latest proposed date
- Prevents showing gaps when patient has rescheduled visits
- Example: Proposed visit on Apr 1 → suppress all predicted visits Mar-Apr

### Rule 3: After Terminal Proposed Visit
- If proposed visit is one of the last visits (terminal), suppress ALL visits after it
- Handles early study completion
- Example: V-EOT proposed Mar 15 → suppress all visits after Mar 15

### Rule 4: Missed Visits (NEW)
- Suppress predicted visits that occurred BEFORE the latest actual visit
- Distinguishes "missed" from "overdue"
- Example: V3 scheduled Feb 1, V5 completed Feb 15 → suppress V3 (missed)

## What Shows as "Overdue" Now

**Overdue visits** are predicted visits that:
1. ✅ Are scheduled BEFORE today (in the past)
2. ✅ Have NOT been completed (IsActual != True)
3. ✅ Are AFTER the most recent actual visit (or no actual visits exist)
4. ✅ Are patient visits (not study events like SIV, monitoring)
5. ✅ Don't have proposed visits scheduled

## Impact on Export

The "Overdue Predicted Visits" export will now:

**Include:**
- Visits that are truly overdue (before today, after latest actual visit)
- Recent visits the patient hasn't attended yet
- Visits for patients still active in the study

**Exclude:**
- Visits from 2022-2023 if patient has had visits since then
- "Missed" visits that occurred before the most recent actual visit
- Visits for inactive patients (if hide_inactive is enabled)
- Study events (SIV, monitoring, etc.)

## Example Scenarios

### Scenario 1: Patient with Regular Visits
- V1: 01/01/2024 (actual)
- V2: 15/01/2024 (predicted, missed - patient didn't come)
- V3: 01/02/2024 (actual)
- V4: 15/02/2024 (predicted, overdue - before today 23/01/2026)
- V5: 01/03/2026 (predicted, future)

**Export shows:**
- ✅ V4 (overdue - after V3, before today)

**Export doesn't show:**
- ❌ V2 (missed - before V3)
- ❌ V5 (future - after today)

### Scenario 2: Patient with Long Gap
- V1: 01/01/2022 (actual)
- V2: 15/01/2022 (predicted, missed)
- V3: 01/02/2022 (predicted, missed)
- V4: 15/02/2022 (predicted, missed)
- ... (no visits for 3 years)
- V10: 01/01/2024 (actual - patient came back!)
- V11: 15/01/2024 (predicted, overdue)

**Export shows:**
- ✅ V11 (overdue - after V10, before today)

**Export doesn't show:**
- ❌ V2, V3, V4 (all missed - before V10)

### Scenario 3: Patient Just Started
- V1: 01/01/2026 (actual)
- V2: 15/01/2026 (predicted, overdue - 8 days ago)
- V3: 01/02/2026 (predicted, future)

**Export shows:**
- ✅ V2 (overdue - after V1, before today)

**Export doesn't show:**
- ❌ V3 (future - after today)

## Files Modified

### patient_processor.py
**Lines 524-551**: Added tracking of actual visit dates
```python
actual_visit_dates = []  # List of all completed (past) actual visit dates
# ... collect actual visit dates ...
latest_actual_date = max(actual_visit_dates) if actual_visit_dates else None
```

**Lines 625-647**: Added Rule 4 to suppression logic
```python
# Rule 4: NEW - Suppress predicted visits in the PAST if there's a LATER actual visit
elif predicted_date < today and latest_actual_date is not None:
    if predicted_date < latest_actual_date:
        should_suppress = True
        suppress_reason = f"missed visit (before latest actual visit...)"
```

### bulk_visits.py
**Lines 35-95**: Improved filtering and added logging
- Better comments explaining what "overdue predicted" means
- Added VisitType filtering (patient, extra only)
- Added PatientStatus filtering (when available)
- Added logging for debugging

## Testing

To verify the fix works:

1. **Check a patient with gaps:**
   - Find a patient who had visits in 2022, stopped, then resumed in 2024
   - Export overdue visits
   - Verify only visits AFTER the most recent 2024 visit show as overdue

2. **Check a patient with missed visits:**
   - Find a patient who skipped V3 but came for V5
   - Verify V3 doesn't show in overdue export

3. **Check a recently started patient:**
   - Find a patient who started in last 3 months
   - Verify overdue visits appear correctly (visits between V1 and today)

## Benefits

1. **Cleaner Export**: No longer cluttered with years-old "missed" visits
2. **Actionable Data**: Secretary can focus on truly overdue visits that need follow-up
3. **Correct Semantics**: Distinguishes "missed" (patient came for later visits) from "overdue" (patient hasn't been seen since)
4. **Better Workflow**: Export reflects visits that actually need to be scheduled/completed

## Notes

- This logic applies to the **calendar display** and **overdue export**
- Missed visits are still tracked in the system (they exist in the schedule)
- They just don't appear as "overdue needing completion"
- If you need to see missed visits, use the full calendar view (they'll show in patient columns as empty predicted visits)

---

**Status:** ✅ IMPLEMENTED
**Testing:** Recommended before production use
