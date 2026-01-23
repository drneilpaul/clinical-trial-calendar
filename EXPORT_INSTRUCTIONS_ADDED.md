# Excel Export Instructions Enhancement
**Date:** 2026-01-23

## Overview

Added comprehensive instructions sheets to Excel exports for unconfirmed/proposed visits and overdue predicted visits to help users understand how to complete and re-upload the files.

## Changes Made

### 1. Proposed Visits Export - Instructions Added

**File:** `bulk_visits.py` - `build_proposed_visits_export()` function

**New Sheet Added:** "Instructions"

**Content:**
- Workflow explanation (what proposed visits are)
- How to use the file
- Status options (Confirmed, Rescheduled, Cancelled, DNA)
- Patient status context (8 statuses explained)
- Notes field guidance
- After completion instructions
- Important notes and validation rules
- Examples for each scenario

**Status Options Explained:**
- **Confirmed** = Visit occurred as scheduled
- **Rescheduled** = Visit moved to different date (update ActualDate)
- **Cancelled** = Visit cancelled (patient withdrew, study ended)
- **DNA** = Did Not Attend (no show)
- **[Blank]** = Still proposed/tentative (no change)

**Patient Statuses Documented:**
1. `screening` - Patient in screening phase
2. `screen_failed` - Patient failed screening criteria
3. `dna_screening` - Patient did not attend screening
4. `randomized` - Patient successfully randomized
5. `withdrawn` - Patient withdrew from study
6. `deceased` - Patient passed away
7. `completed` - Patient completed all visits
8. `lost_to_followup` - Patient lost contact

### 2. Overdue Predicted Visits Export - Instructions Added

**File:** `bulk_visits.py` - `build_overdue_predicted_export()` function

**New Sheet Added:** "Instructions"

**Content:**
- What are overdue predicted visits?
- Why some visits are excluded (missed vs overdue logic)
- How to use the file
- Required fields (ActualDate, Outcome)
- Outcome options explained
- Patient status context
- Notes field guidance
- After completion instructions
- Important validation notes
- 4 detailed examples

**Outcome Options Explained:**
- **Completed** = Visit occurred and completed normally
- **DNA** = Patient Did Not Attend
- **Withdrawn** = Patient withdrew at/after this visit
- **ScreenFail** = Patient failed screening
- **Deceased** = Patient passed away
- **Cancelled** = Visit cancelled
- **Rescheduled** = Visit moved to different date

**Key Concepts Explained:**
1. **Overdue vs Missed**: Only visits AFTER the patient's most recent visit are shown
2. **Patient Status Impact**: How outcomes update patient status
3. **Date Format**: DD/MM/YYYY required
4. **Future Visits**: How Withdrawn/Deceased suppresses future visits

## Benefits

### For Users:
1. **Clear Guidance** - No confusion about what fields mean or what to fill in
2. **Reference Documentation** - Patient statuses explained in context
3. **Examples** - Real scenarios showing how to fill out the file
4. **Error Prevention** - Validation rules explained upfront

### For System:
1. **Fewer Import Errors** - Users understand format requirements
2. **Consistent Data** - Status values used correctly
3. **Better Adoption** - Users more confident using bulk features
4. **Reduced Support** - Self-service documentation in the file

## File Structure

### Proposed Visits Export
```
📄 proposed_visits_YYYYMMDD.xlsx
  └─ Sheet 1: ProposedVisits (data)
       Columns: PatientID, Study, VisitName, ActualDate, ProposedType, Status, Notes
  └─ Sheet 2: Instructions (guidance)
```

### Overdue Predicted Visits Export
```
📄 Overdue_Predicted_Visits_DD-MM-YYYY.xlsx
  └─ Sheet 1: OverduePredicted (data)
       Columns: PatientID, Study, VisitName, ScheduledDate, SiteofVisit,
                ContractSite, PatientOrigin, VisitType, ActualDate, Outcome, Notes
  └─ Sheet 2: Instructions (guidance)
```

## Instructions Content Summary

### Proposed Visits Instructions Include:
- ✅ Workflow explanation
- ✅ Status options (4 options + blank)
- ✅ Patient status context (8 statuses)
- ✅ Field-by-field guidance
- ✅ Upload instructions
- ✅ Important notes
- ✅ 4 examples (Confirmed, DNA, Rescheduled, Cancelled)

### Overdue Visits Instructions Include:
- ✅ What overdue visits are
- ✅ Missed vs overdue logic explained
- ✅ Outcome options (7 options)
- ✅ Patient status context (8 statuses)
- ✅ Field-by-field guidance
- ✅ Upload instructions
- ✅ Validation rules
- ✅ 4 detailed examples

## Patient Status Documentation

Both instruction sheets now include complete documentation of the 8 patient statuses:

| Status | Description | Category |
|--------|-------------|----------|
| screening | Patient in screening phase | Not Recruited |
| screen_failed | Patient failed screening criteria | Not Recruited |
| dna_screening | Patient did not attend screening | Not Recruited |
| randomized | Patient successfully randomized | Recruited |
| withdrawn | Patient withdrew from study | Recruited |
| deceased | Patient passed away | Recruited |
| completed | Patient completed all visits | Recruited |
| lost_to_followup | Patient lost contact | Recruited |

This helps users understand:
1. What each status means
2. How their Outcome selection affects patient status
3. The patient journey through the study

## Examples Provided

### Proposed Visits Examples:
1. **Confirmed Visit** - Visit occurred as scheduled
2. **DNA Visit** - Patient didn't attend
3. **Rescheduled Visit** - Visit moved to new date
4. **Cancelled Visit** - Study terminated early

### Overdue Visits Examples:
1. **Completed Visit** - Visit completed on time
2. **DNA Visit** - Patient forgot appointment
3. **Rescheduled Visit** - Patient on vacation, rescheduled
4. **Withdrawn Visit** - Patient moved cities

Each example shows:
- All required columns
- Correct date format
- Appropriate outcome
- Helpful notes

## User Workflow

### For Proposed Visits:
1. Export proposed visits → Get Excel with 2 sheets
2. Open file → See data + instructions
3. Read instructions → Understand status options
4. Fill Status column → Confirmed/Rescheduled/Cancelled/DNA/Blank
5. Save file → Upload back to system
6. System processes → Converts to actual visits

### For Overdue Visits:
1. Export overdue visits → Get Excel with 2 sheets
2. Open file → See data + instructions
3. Read instructions → Understand outcome options
4. Fill ActualDate + Outcome → Complete required fields
5. Add Notes (optional) → Document details
6. Save file → Upload back to system
7. System validates → Shows errors/warnings
8. System imports → Adds actual visits

## Technical Implementation

### Instructions Sheet Format:
- Single column table
- No header row
- Text-only content
- Easy to read layout
- Numbered steps
- Bullet points for options
- Examples formatted as tables

### Sheet Creation:
```python
instructions_data = {
    "Instructions": [
        "TITLE",
        "",
        "Section content...",
        "• Bullet point",
        ...
    ]
}
instructions_df = pd.DataFrame(instructions_data)
instructions_df.to_excel(writer, sheet_name="Instructions", index=False, header=False)
```

## Files Modified

| File | Function | Changes |
|------|----------|---------|
| bulk_visits.py | build_proposed_visits_export() | Added "Instructions" sheet with 40+ lines of guidance |
| bulk_visits.py | build_overdue_predicted_export() | Added "Instructions" sheet with 90+ lines of guidance |

## Testing Checklist

- [ ] Proposed visits export creates 2 sheets (ProposedVisits, Instructions)
- [ ] Overdue visits export creates 2 sheets (OverduePredicted, Instructions)
- [ ] Instructions sheet is readable and properly formatted
- [ ] Status options match what system accepts
- [ ] Patient statuses documented correctly
- [ ] Examples are accurate and helpful
- [ ] Date format specified correctly (DD/MM/YYYY)
- [ ] Validation rules explained clearly

## Data Validation Dropdowns ✅ ADDED

Both exports now include dropdown menus for easy selection:

### Proposed Visits Export - Status Column Dropdown:
- Confirmed
- Rescheduled
- Cancelled
- DNA
- [Can also leave blank]

### Overdue Visits Export - Outcome Column Dropdown:
- Completed
- DNA
- Withdrawn
- ScreenFail
- Deceased
- Cancelled
- Rescheduled
- [Can also leave blank]

**Benefits:**
- ✅ No typing errors
- ✅ Consistent values
- ✅ Faster data entry
- ✅ Clear options visible
- ✅ Error message if invalid entry typed

**Technical Implementation:**
```python
from openpyxl.worksheet.datavalidation import DataValidation

status_options = '"Confirmed,Rescheduled,Cancelled,DNA"'
status_validation = DataValidation(
    type="list",
    formula1=status_options,
    allow_blank=True,
    showErrorMessage=True,
    error="Please select a valid status from the dropdown",
    errorTitle="Invalid Status"
)
worksheet.add_data_validation(status_validation)
```

## Future Enhancements

Potential improvements:

1. **Conditional Formatting** - Highlight required fields in data sheet
2. ~~**Data Validation** - Add dropdowns for Status/Outcome columns~~ ✅ DONE
3. **Formula Protection** - Lock instruction sheet from editing
4. **Color Coding** - Use colors to indicate field importance
5. **Video Link** - Add link to video tutorial
6. **FAQ Sheet** - Add third sheet with common questions
7. **Version Number** - Add file format version for tracking

## User Feedback Integration

The instructions address common user questions:
- ❓ "What status should I use?" → Status options explained
- ❓ "What date format?" → DD/MM/YYYY specified
- ❓ "Can I leave fields blank?" → Blank handling explained
- ❓ "What happens after upload?" → System behavior documented
- ❓ "What are patient statuses?" → All 8 statuses documented

---

**Status:** ✅ IMPLEMENTED
**User Impact:** Improved understanding and fewer errors
**Support Impact:** Reduced questions about file format
