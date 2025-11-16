# Clinical Trial Calendar Database Structure Guide

## IMPORTANT INSTRUCTIONS FOR AI ANALYSIS

**CRITICAL: Do NOT hallucinate or invent data. Only use information that is explicitly present in the source data. If a field is missing, empty, or unclear, mark it as such rather than making assumptions. Follow the exact field names, data types, and validation rules specified below. Do not create data that doesn't exist in the source files.**

---

## OVERVIEW

This system uses three database tables/files to manage clinical trial data:

1. **patients** table - Contains patient enrollment information
2. **trial_schedules** table - Contains the visit schedule definitions for each study
3. **actual_visits** table - Contains records of visits that have actually occurred

---

## 1. PATIENTS TABLE

### Purpose
Stores information about enrolled patients in clinical trials.

### Required Columns
- **PatientID** (string): Unique patient identifier. Must be unique across all patients.
- **Study** (string): Study name/code. Must match a study in the trial_schedules table.
- **StartDate** (date): Patient enrollment/baseline date. Format: DD/MM/YYYY or YYYY-MM-DD. Cannot be null.
- **PatientPractice** (string): Recruitment site where the patient was recruited. **REQUIRED** - cannot be empty, null, or invalid placeholder values.

### Valid Site Values for PatientPractice
- Must be a valid site name (typically "Ashfields" or "Kiltearn", but can be other valid site names)
- **INVALID values** that will cause errors: `''`, `'nan'`, `'None'`, `'null'`, `'NULL'`, `'Unknown Site'`, `'unknown site'`, `'UNKNOWN SITE'`, `'Default Site'`

### Data Validation Rules
1. **PatientID must be unique** - no duplicate PatientIDs allowed
2. **StartDate must be valid** - cannot be null or invalid date
3. **PatientPractice must be valid** - cannot be empty or invalid placeholder
4. **Study must exist in trial_schedules** - every patient's Study must have a corresponding trial schedule

### Example Row
```
PatientID: "P001"
Study: "STUDY-2024-001"
StartDate: "15/03/2024"  (or "2024-03-15")
PatientPractice: "Ashfields"
```

---

## 2. TRIAL_SCHEDULES TABLE

### Purpose
Defines the visit schedule for each study, including visit names, timing, locations, and payment information.

### Required Columns
- **Study** (string): Study name/code. Must match Study values in patients table.
- **Day** (integer): Visit day number. Day 1 = baseline visit. Can be negative (screening), 0 (optional visits), or positive (scheduled visits).
- **VisitName** (string): Name/identifier for the visit (e.g., "V1", "Screening", "Follow-up 1").
- **SiteforVisit** (string): Where the visit takes place. **REQUIRED** - cannot be empty or invalid placeholder.

### Optional Columns
- **Payment** (float/numeric): Payment amount for this visit. Default: 0 if not provided.
- **ToleranceBefore** (integer): Days before expected date that visit is allowed. Default: 0.
- **ToleranceAfter** (integer): Days after expected date that visit is allowed. Default: 0.
- **IntervalUnit** (string): Unit for interval calculation - "month" or "day". Used when visits are scheduled monthly rather than daily.
- **IntervalValue** (integer): Number of interval units. Used with IntervalUnit for month-based scheduling.
- **VisitType** (string): Type of visit - "patient" (default), "extra" (optional add-on activity), "siv", or "monitor" for study-level events.

### Month-Based vs Day-Based Scheduling

#### When to Use Month-Based Scheduling
- Use **month-based scheduling** (`IntervalUnit="month"`) when visits are scheduled at regular monthly intervals (e.g., every 1 month, every 3 months, every 6 months)
- Use **day-based scheduling** (default, no IntervalUnit or `IntervalUnit=""`) when visits are scheduled at specific day intervals (e.g., Day 7, Day 14, Day 30)

#### How Month-Based Scheduling Works
When `IntervalUnit="month"` and `IntervalValue` is set:
- The system calculates the expected visit date using **calendar months** from the baseline date (Day 1)
- Date calculation uses `pd.DateOffset(months=IntervalValue)` which is calendar-aware (handles different month lengths correctly)
- The **Day column is still used for ordering/sequencing visits** but the actual date calculation uses months
- Example: If baseline is 01/03/2024 and `IntervalValue=3`, the visit date would be 01/06/2024 (3 months later)

#### Day Column with Month-Based Scheduling
- The **Day column should still be populated** to maintain visit sequence/ordering
- For month-based visits, Day numbers can be sequential (1, 2, 3...) or represent months (1, 3, 6, 12...)
- The Day number is used for ordering, but the actual date calculation ignores it when `IntervalUnit="month"` is set
- **Important**: Day 1 baseline visit always uses the patient's StartDate, regardless of IntervalUnit

#### IntervalUnit and IntervalValue Validation
- **IntervalUnit** must be either `"month"`, `"day"`, or empty/blank
- If `IntervalUnit="month"`, **IntervalValue must be a positive integer** (e.g., 1, 3, 6, 12)
- If `IntervalUnit` is empty or `"day"`, the system uses day-based calculation (Day number from baseline)
- If `IntervalUnit="month"` but `IntervalValue` is missing/invalid, the system falls back to day-based calculation

#### Example Month-Based Schedule
```
Study: "STUDY-2024-002", Day: 1, VisitName: "Baseline", SiteforVisit: "Ashfields", Payment: 150.00, IntervalUnit: "", IntervalValue: ""
Study: "STUDY-2024-002", Day: 2, VisitName: "Month 1 Follow-up", SiteforVisit: "Kiltearn", Payment: 100.00, IntervalUnit: "month", IntervalValue: 1
Study: "STUDY-2024-002", Day: 3, VisitName: "Month 3 Follow-up", SiteforVisit: "Kiltearn", Payment: 100.00, IntervalUnit: "month", IntervalValue: 3
Study: "STUDY-2024-002", Day: 4, VisitName: "Month 6 Follow-up", SiteforVisit: "Ashfields", Payment: 125.00, IntervalUnit: "month", IntervalValue: 6
Study: "STUDY-2024-002", Day: 5, VisitName: "Month 12 Follow-up", SiteforVisit: "Ashfields", Payment: 125.00, IntervalUnit: "month", IntervalValue: 12
```

**Date Calculation Example:**
- Patient StartDate (Day 1): 15/03/2024
- Month 1 Follow-up (Day 2, IntervalValue=1): 15/04/2024 (1 month later)
- Month 3 Follow-up (Day 3, IntervalValue=3): 15/06/2024 (3 months later)
- Month 6 Follow-up (Day 4, IntervalValue=6): 15/09/2024 (6 months later)
- Month 12 Follow-up (Day 5, IntervalValue=12): 15/03/2025 (12 months later)

#### Optional Extras (VisitType = "extra")
- Define add-on activities (e.g., Re-consent, ECG) as `VisitType="extra"` in the trial schedule.
- Set `Day = 0` so extras are not predicted; they appear only when an actual visit records them.
- Provide a clear `VisitName`, valid `SiteforVisit`, and the additional `Payment` value.
- Staff can select one or more extras when recording an actual visit; each extra generates its own actual visit row and payment.
- Extras are treated as patient-level work in analytics and exports.

### Valid Site Values for SiteforVisit
- Must be a valid site name (typically "Ashfields" or "Kiltearn", but can be other valid site names)
- **INVALID values** that will cause errors: `''`, `'nan'`, `'None'`, `'null'`, `'NULL'`, `'Unknown Site'`, `'unknown site'`, `'UNKNOWN SITE'`, `'Default Site'`

### Critical Rules for Day Column
1. **Each study must have exactly ONE Day 1 visit** - this is the baseline visit
2. **Day 1 is required** - cannot have a study without a Day 1 baseline
3. **Day < 0** = Screening visits (before baseline)
4. **Day 0** = Optional visits (SIV, Monitor, unscheduled visits) - these only appear when actual, not predicted
5. **Day >= 1** = Scheduled patient visits (Day 1 = baseline, Day 2+ = follow-up visits)

### Data Validation Rules
1. **SiteforVisit must be valid** - cannot be empty or invalid placeholder
2. **Each study must have exactly one Day 1 visit** - this is the baseline requirement
3. **Payment values** - should be numeric, non-negative (0 or positive)
4. **Tolerance values** - should be non-negative integers
5. **IntervalUnit and IntervalValue** - if IntervalUnit="month", IntervalValue must be a positive integer; if IntervalUnit is empty or "day", IntervalValue is ignored
6. **IntervalUnit values** - must be "month", "day", or empty/blank (case-insensitive, but stored as lowercase)

### Example Rows

**Day-Based Scheduling:**
```
Study: "STUDY-2024-001", Day: 1, VisitName: "Baseline", SiteforVisit: "Ashfields", Payment: 100.00, ToleranceBefore: 0, ToleranceAfter: 0, IntervalUnit: "", IntervalValue: ""
Study: "STUDY-2024-001", Day: 7, VisitName: "Follow-up 1", SiteforVisit: "Kiltearn", Payment: 75.00, ToleranceBefore: 2, ToleranceAfter: 2, IntervalUnit: "", IntervalValue: ""
Study: "STUDY-2024-001", Day: 0, VisitName: "SIV", SiteforVisit: "Ashfields", Payment: 500.00, VisitType: "siv", IntervalUnit: "", IntervalValue: ""
```

**Month-Based Scheduling:**
```
Study: "STUDY-2024-002", Day: 1, VisitName: "Baseline", SiteforVisit: "Ashfields", Payment: 150.00, ToleranceBefore: 0, ToleranceAfter: 0, IntervalUnit: "", IntervalValue: ""
Study: "STUDY-2024-002", Day: 2, VisitName: "Month 1 Follow-up", SiteforVisit: "Kiltearn", Payment: 100.00, ToleranceBefore: 0, ToleranceAfter: 0, IntervalUnit: "month", IntervalValue: 1
Study: "STUDY-2024-002", Day: 3, VisitName: "Month 3 Follow-up", SiteforVisit: "Kiltearn", Payment: 100.00, ToleranceBefore: 0, ToleranceAfter: 0, IntervalUnit: "month", IntervalValue: 3
Study: "STUDY-2024-002", Day: 4, VisitName: "Month 6 Follow-up", SiteforVisit: "Ashfields", Payment: 125.00, ToleranceBefore: 0, ToleranceAfter: 0, IntervalUnit: "month", IntervalValue: 6
```

---

## 3. ACTUAL_VISITS TABLE

### Purpose
Records visits that have actually occurred, including patient visits and study-level events (SIVs, Monitor visits).

### Required Columns
- **PatientID** (string): Patient identifier. Must match a PatientID in patients table (unless it's a study event).
- **Study** (string): Study name/code. Must match Study in patients and trial_schedules tables.
- **VisitName** (string): Name of the visit that occurred. Should match a VisitName in trial_schedules for that study.
- **ActualDate** (date): Date the visit actually occurred. Format: DD/MM/YYYY or YYYY-MM-DD. **REQUIRED** - cannot be null.

### Optional Columns
- **Notes** (string): Additional notes about the visit. Used to mark screen failures (see below).
- **VisitType** (string): Type of visit - "patient" (default), "extra" (optional add-on activity), "siv", or "monitor". Used to identify the visit category.

### How to Identify Different Visit Types

#### A. VISITS THAT HAVE HAPPENED (Completed Visits)
**Identification:**
- Record exists in actual_visits table
- ActualDate is populated (not null)
- IsActual = True (when processed)

**Key Points:**
- If a visit has an ActualDate in actual_visits, it has happened
- The visit is marked as completed/actual
- Payment is recorded for completed visits

#### B. SCREEN FAILURES
**Identification:**
- Record exists in actual_visits table
- **Notes column contains "ScreenFail"** (case-insensitive match)
- ActualDate is populated

**Important Rules:**
- Screen failures are detected by searching for "ScreenFail" in the Notes column (case-insensitive)
- Once a patient has a screen failure, NO future visits should be scheduled for that patient
- The screen failure date is the earliest date where Notes contains "ScreenFail" for that patient+study combination
- Screen failures stop all future visit predictions for that patient

**Example:**
```
PatientID: "P001"
Study: "STUDY-2024-001"
VisitName: "Screening"
ActualDate: "20/03/2024"
Notes: "ScreenFail - Patient did not meet inclusion criteria"
VisitType: "patient"
```

#### C. PATIENT WITHDRAWALS
**Identification:**
- Record exists in actual_visits table
- **Notes column contains "Withdrawn"** (case-insensitive match)
- ActualDate is populated

**Important Rules:**
- Withdrawals are detected by searching for "Withdrawn" in the Notes column (case-insensitive)
- Once a patient has withdrawn, NO future visits should be scheduled for that patient
- The withdrawal date is the earliest date where Notes contains "Withdrawn" for that patient+study combination
- Withdrawals stop all future visit predictions for that patient (same behavior as screen failures)

**Example:**
```
PatientID: "P002"
Study: "STUDY-2024-001"
VisitName: "V3"
ActualDate: "15/05/2024"
Notes: "Withdrawn - Patient withdrew consent"
VisitType: "patient"
```

#### D. VISITS THAT ARE DUE (Scheduled/Upcoming Visits)
**Identification:**
- **NO matching record in actual_visits table** for that PatientID + Study + VisitName combination
- OR IsActual = False (when processed)
- The visit is defined in trial_schedules for that study
- The expected date is calculated from the patient's StartDate + Day number

**Key Points:**
- If a visit is in trial_schedules but NOT in actual_visits, it is due/upcoming
- These are predicted/scheduled visits
- They show the expected date based on the patient's StartDate + visit Day number

#### D. OPTIONAL EXTRAS (Add-On Activities)
**Identification:**
- VisitType = "extra"
- Day = 0 in trial schedule

**Key Points:**
- Extras represent additional billable work (e.g., Re-consent, ECG) performed during a patient visit.
- They are entered alongside a primary visit and generate their own actual visit row with payment.
- Extras are treated as patient visits in analytics (included in income and workload summaries).
- Not predicted in advance; they only appear when recorded as actual visits.

#### E. ONE-OFF EVENTS (SIVs, Monitor Visits)
**Identification:**
- **VisitType = "siv"** OR **VisitType = "monitor"**
- OR **VisitName = "SIV"** (case-insensitive, exact match)
- OR **VisitName contains "Monitor"** (case-insensitive substring match)
- These are study-level events, not patient visits
- They appear in actual_visits table when they occur
- They may have Day = 0 in trial_schedules

**Auto-Detection Rules:**
- If VisitName (uppercase, trimmed) equals "SIV" → VisitType should be "siv"
- If VisitName contains "Monitor" (case-insensitive) → VisitType should be "monitor"
- These auto-detections happen even if VisitType column is missing or incorrect

**Important for SIVs:**
- SIV = Site Initiation Visit (study setup event, not a patient visit)
- PatientID for study events may be a pseudo-ID like "SIV_STUDY-2024-001" or just the study name
- Must have a valid SiteforVisit in trial_schedules to be processed

**Important for Monitor Visits:**
- Monitor visits = monitoring/audit visits (study-level events)
- Similar to SIVs - not patient visits
- Must have valid SiteforVisit in trial_schedules

**Example SIV:**
```
PatientID: "SIV_STUDY-2024-001"  (or just the Study name)
Study: "STUDY-2024-001"
VisitName: "SIV"
ActualDate: "01/03/2024"
VisitType: "siv"
Notes: ""
```

**Example Monitor Visit:**
```
PatientID: "MONITOR_STUDY-2024-001"
Study: "STUDY-2024-001"
VisitName: "Monitor Visit 1"
ActualDate: "15/04/2024"
VisitType: "monitor"
Notes: ""
```

### Data Validation Rules
1. **ActualDate must be valid** - cannot be null or invalid date
2. **PatientID should exist in patients table** - unless it's a study event (SIV/Monitor)
3. **Study must exist in trial_schedules** - every visit's Study must have a trial schedule
4. **VisitName should match trial_schedules** - visit names should exist in the trial schedule for that study (warnings if not found, but allowed for Day 0 optional visits)

### Special Cases

#### Day 0 Visits (Optional/Unscheduled)
- These are visits that may or may not occur
- They only appear in actual_visits when they actually happen
- They are NOT predicted/scheduled in advance
- Examples: Extra visits, unscheduled follow-ups, optional procedures

#### Unmatched Visits
- If a visit in actual_visits doesn't match a VisitName in trial_schedules, it's "unmatched"
- This is allowed but generates a warning
- May be Day 0 optional visits or data entry variations
- The system will still try to process them if a site can be determined

---

## KEY RELATIONSHIPS BETWEEN TABLES

### Patient → Trial Schedule
- Every patient's **Study** must exist in **trial_schedules**
- The trial_schedules table defines what visits are possible for that study

### Patient → Actual Visits
- Every visit in **actual_visits** should have a **PatientID** that exists in **patients** (unless it's a study event)
- Every visit in **actual_visits** should have a **Study** that matches the patient's **Study**

### Trial Schedule → Actual Visits
- Visits in **actual_visits** should have **VisitName** that matches **VisitName** in **trial_schedules** for that **Study**
- The **SiteforVisit** from **trial_schedules** is used to determine where visits occur

---

## DATE FORMATS

### Accepted Formats
- **DD/MM/YYYY** (e.g., "15/03/2024")
- **YYYY-MM-DD** (e.g., "2024-03-15")
- ISO date format

### Processing
- Dates are parsed with day-first priority (DD/MM/YYYY is primary format)
- Invalid dates are rejected and logged as errors
- Null dates are not allowed for StartDate (patients) or ActualDate (actual_visits)

---

## VISIT STATUS IDENTIFICATION SUMMARY

### Completed Visit (Has Happened)
- ✅ Record in actual_visits table
- ✅ ActualDate populated
- ✅ IsActual = True
- ✅ May have payment recorded

### Screen Failure
- ⚠️ Record in actual_visits table
- ⚠️ Notes contains "ScreenFail" (case-insensitive)
- ⚠️ ActualDate populated
- ⚠️ Stops all future visits for that patient

### Due/Upcoming Visit
- 📋 No record in actual_visits table
- 📋 Exists in trial_schedules for that study
- 📋 Expected date calculated from StartDate + Day
- 📋 IsActual = False

### Study Event (SIV/Monitor)
- 🔵 VisitType = "siv" or "monitor"
- 🔵 OR VisitName = "SIV" or contains "Monitor"
- 🔵 Study-level, not patient-specific
- 🔵 Must have valid SiteforVisit in trial_schedules

---

## HANDLING HISTORICAL DAY 1 BASELINE (STUDIES WITH OLD BASELINE DATES)

### Scenario: Day 1 Baseline Occurred Years Ago

When extracting data for the current year and moving forward, you may encounter patients whose Day 1 baseline visit occurred years ago (e.g., 2020, 2021, 2022). In these cases, you don't want to list all historical visits between Day 1 and the current year.

### Strategy for Historical Studies

#### 1. Day 1 Baseline as Reference Point
- **Include the Day 1 baseline visit** as a reference point, even if it occurred years ago
- This provides context for when the patient started the study
- **Payment for Day 1 can be set to £0** if it's being used purely as a reference point for current year analysis
- Alternatively, use the actual payment amount if historical payments are relevant

#### 2. Current Year Visits Only
- **Only include visits from the current year onward** for the main calendar/analysis
- Skip all historical visits between Day 1 and the start of the current year
- This keeps the calendar focused on current and future work

#### 3. Data Extraction Approach
When building the data files:
- **patients table**: Include the patient with their original StartDate (even if years ago)
- **trial_schedules table**: Include all visit definitions (Day 1, Day 2, etc.) as normal
- **actual_visits table**: 
  - Include Day 1 baseline visit (with ActualDate from years ago, Payment: £0 or actual amount)
  - Include only actual visits from current year onward
  - Skip historical visits between Day 1 and current year

#### 4. Example: Historical Day 1 with Current Year Visits

**Patient Data:**
```
PatientID: "P100"
Study: "STUDY-2020-001"
StartDate: "15/05/2020"  (Day 1 was 4 years ago)
PatientPractice: "Ashfields"
```

**Trial Schedule:**
```
Day: 1, VisitName: "Baseline", IntervalUnit: "month", IntervalValue: ""
Day: 2, VisitName: "Month 1", IntervalUnit: "month", IntervalValue: 1
Day: 3, VisitName: "Month 3", IntervalUnit: "month", IntervalValue: 3
Day: 4, VisitName: "Month 6", IntervalUnit: "month", IntervalValue: 6
Day: 5, VisitName: "Month 12", IntervalUnit: "month", IntervalValue: 12
Day: 6, VisitName: "Month 24", IntervalUnit: "month", IntervalValue: 24
Day: 7, VisitName: "Month 36", IntervalUnit: "month", IntervalValue: 36
Day: 8, VisitName: "Month 48", IntervalUnit: "month", IntervalValue: 48
```

**Actual Visits (for 2024 extraction):**
```
# Day 1 baseline (reference, years ago)
PatientID: "P100", Study: "STUDY-2020-001", VisitName: "Baseline", ActualDate: "15/05/2020", Payment: £0 (or actual if needed)

# Current year visits only (2024 onward)
PatientID: "P100", Study: "STUDY-2020-001", VisitName: "Month 48", ActualDate: "15/05/2024", Payment: 125.00
PatientID: "P100", Study: "STUDY-2020-001", VisitName: "Month 36", ActualDate: "15/05/2023" (if including 2023)
```

**Result:**
- Day 1 baseline (15/05/2020) shown as reference point
- Historical visits (Month 1, Month 3, Month 6, Month 12, Month 24, Month 36 from 2020-2023) are NOT listed
- Only current year visits (Month 48 from 2024) are included
- Future scheduled visits (after current date) will be predicted normally

#### 5. Future Feature: Screen Filtering by Date

**Note**: The current approach is for **data extraction and analysis**. A future feature may add on-screen filtering to show/hide visits based on date ranges. This guide focuses on how to structure the data files correctly for extraction purposes.

---

## VALIDATION RULES SUMMARY

### Critical Errors (Will Prevent Data Loading)
1. Missing required columns (PatientID, Study, StartDate, PatientPractice in patients)
2. Missing required columns (Study, Day, VisitName, SiteforVisit in trial_schedules)
3. Missing required columns (PatientID, Study, VisitName, ActualDate in actual_visits)
4. Invalid PatientPractice values (empty, null, or invalid placeholders)
5. Invalid SiteforVisit values (empty, null, or invalid placeholders)
6. Missing Day 1 baseline visit for a study
7. Multiple Day 1 visits for a study (must be exactly one)
8. Duplicate PatientIDs

### Warnings (Will Allow Loading but Should Be Fixed)
1. Visit in actual_visits doesn't match VisitName in trial_schedules
2. ActualDate is null (should never happen, but handled gracefully)
3. Payment values are negative or invalid
4. Duplicate visit records (same PatientID + Study + VisitName + ActualDate)

---

## INSTRUCTIONS FOR DATA ANALYSIS

### When Building These Files:

1. **Be Precise with Field Names**
   - Use exact column names as specified
   - Do not invent or rename columns
   - If a column doesn't exist in source data, mark it clearly rather than creating it

2. **Validate Site Names**
   - Only use actual site names from source data
   - Do not use placeholder values
   - Common sites: "Ashfields", "Kiltearn" (but verify from source data)

3. **Screen Failures**
   - Only mark as screen failure if Notes explicitly contains "ScreenFail"
   - Do not infer screen failures from other data
   - Case-insensitive matching for "ScreenFail"

4. **Study Events (SIV/Monitor)**
   - Only mark as SIV if VisitName is exactly "SIV" (case-insensitive) OR VisitType is "siv"
   - Only mark as Monitor if VisitName contains "Monitor" OR VisitType is "monitor"
   - Do not infer study events from other patterns

5. **Date Handling**
   - Preserve original date format if possible
   - Convert to DD/MM/YYYY or YYYY-MM-DD format
   - Do not invent dates - if date is missing, mark as null/invalid

6. **Day Numbers**
   - Day 1 = baseline (required, exactly one per study)
   - Day < 0 = screening visits
   - Day 0 = optional visits (SIV, Monitor, unscheduled)
   - Day >= 1 = follow-up visits
   - Do not invent Day numbers - use actual values from source data

7. **Missing Data**
   - If a field is missing, use empty string "" for text fields
   - Use 0 for numeric fields (Payment, ToleranceBefore, ToleranceAfter)
   - Use null/empty for dates only if truly not available
   - Do not invent or infer missing data

8. **Visit Matching**
   - Match VisitName exactly (case-sensitive matching preferred, but case-insensitive fallback allowed)
   - If visit name doesn't match trial schedule, it may be an unmatched/optional visit
   - Do not force matches - if unclear, mark as unmatched

### Bulk Overdue Visit Workflow
- **Export**: Use “Export Overdue Predicted Visits” in the app to download a CSV of overdue scheduled visits for the current financial year (excludes tolerance markers and Day 0 optional events).
- **Secretary Completion**:
  - Fill `ActualDate` for visits that happened (format `YYYY-MM-DD`).
  - Populate `Outcome` (e.g., “Happened”, “Did not happen”); rows marked as negative or left without an ActualDate are ignored on import.
  - Add any notes in `Notes`.
  - For extras performed at the same visit, list the extra visit names in `ExtrasPerformed` separated by commas (must match `VisitType="extra"` entries in the trial schedule).
- **Import**: Upload the completed CSV via the “Import Completed Visits” section.
  - The system validates each row against current predictions and the trial schedule.
  - Valid rows create new actual visits (extras generate additional rows with `VisitType="extra"`).
  - In database mode, the visits are appended automatically; in file mode, a new actual_visits CSV is generated for manual merge.

---

## EXAMPLE SCENARIOS

### Scenario 1: Normal Patient Journey
1. Patient enrolled: P001, Study: STUDY-A, StartDate: 01/03/2024, PatientPractice: Ashfields
2. Trial schedule: Day 1 = Baseline, Day 7 = Follow-up 1, Day 14 = Follow-up 2
3. Actual visits:
   - Baseline (Day 1) occurred on 01/03/2024 → COMPLETED
   - Follow-up 1 (Day 7) occurred on 08/03/2024 → COMPLETED
   - Follow-up 2 (Day 14) not in actual_visits → DUE/UPCOMING (expected 15/03/2024)

### Scenario 2: Screen Failure
1. Patient enrolled: P002, Study: STUDY-A, StartDate: 05/03/2024, PatientPractice: Kiltearn
2. Actual visit: Screening on 10/03/2024 with Notes: "ScreenFail - exclusion criteria"
3. Result: All future visits for P002 in STUDY-A are cancelled (no scheduled visits after 10/03/2024)

### Scenario 3: Study Event (SIV)
1. Trial schedule: Day 0, VisitName: "SIV", SiteforVisit: Ashfields, VisitType: "siv"
2. Actual visit: PatientID: "SIV_STUDY-A", Study: STUDY-A, VisitName: "SIV", ActualDate: 28/02/2024, VisitType: "siv"
3. Result: Study-level event recorded, not a patient visit

### Scenario 4: Optional Visit (Day 0)
1. Actual visit: PatientID: P003, Study: STUDY-A, VisitName: "Extra Blood Draw", ActualDate: 12/03/2024
2. This visit may not exist in trial_schedules (unmatched)
3. Result: Visit is recorded but marked as unmatched/optional

### Scenario 5: Month-Based Scheduling
1. Patient enrolled: P004, Study: STUDY-B, StartDate: 01/06/2024, PatientPractice: Kiltearn
2. Trial schedule (month-based):
   - Day 1: Baseline (IntervalUnit: "", IntervalValue: "") - uses StartDate
   - Day 2: Month 1 Follow-up (IntervalUnit: "month", IntervalValue: 1) - 1 month after baseline
   - Day 3: Month 3 Follow-up (IntervalUnit: "month", IntervalValue: 3) - 3 months after baseline
   - Day 4: Month 6 Follow-up (IntervalUnit: "month", IntervalValue: 6) - 6 months after baseline
3. Actual visits:
   - Baseline (Day 1) occurred on 01/06/2024 → COMPLETED
   - Month 1 Follow-up (Day 2) occurred on 01/07/2024 → COMPLETED
   - Month 3 Follow-up (Day 3) not yet occurred → DUE/UPCOMING (expected 01/09/2024)
   - Month 6 Follow-up (Day 4) not yet occurred → DUE/UPCOMING (expected 01/12/2024)
4. Result: Visits scheduled using calendar months rather than fixed day counts

### Scenario 6: Historical Day 1 with Current Year Visits
1. Patient enrolled: P005, Study: STUDY-C, StartDate: 10/03/2020 (4 years ago), PatientPractice: Ashfields
2. Trial schedule: Monthly visits from Month 1 to Month 48 (4 years)
3. Actual visits (for 2024 extraction):
   - Baseline (Day 1) from 10/03/2020 → Included as reference point (Payment: £0)
   - Historical visits (Month 1-36 from 2020-2023) → NOT included in extraction
   - Month 48 visit from 10/03/2024 → Included (current year)
4. Result: Day 1 shown as reference, only current year visits included, historical visits skipped

---

## FINAL CHECKLIST

Before submitting data, verify:

- [ ] All required columns are present
- [ ] No invalid site placeholders (empty, 'nan', 'None', etc.)
- [ ] Each study has exactly one Day 1 visit
- [ ] All PatientIDs are unique
- [ ] All dates are valid and in correct format
- [ ] Screen failures are marked with "ScreenFail" in Notes
- [ ] Study events (SIV/Monitor) have correct VisitType or identifiable VisitName
- [ ] No invented or hallucinated data - only use actual source data
- [ ] Missing data is marked as empty/null rather than invented

---

**END OF GUIDE**


