# Clinical Trial Calendar - Database Guide

## Overview

This guide provides comprehensive documentation for all database tables, columns, and their usage in the Clinical Trial Calendar system.

---

## Table of Contents

1. [patients](#patients-table)
2. [trial_schedules](#trial_schedules-table)
3. [actual_visits](#actual_visits-table)
4. [study_site_details](#study_site_details-table)
5. [Common Patterns](#common-patterns)
6. [Data Relationships](#data-relationships)

---

## patients Table

Tracks all enrolled patients, their recruitment status, and visit locations.

### Core Identification

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| `PatientID` | text | ✅ Yes | Unique patient identifier. Can be any format (numeric, alphanumeric, etc.) |
| `Study` | text | ✅ Yes | Study name/code. Must match a `Study` value in `trial_schedules` table |

### Dates and Status

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| `ScreeningDate` | date | ✅ Yes | Date of first screening visit (Day 1 baseline). All visit calculations are relative to this date |
| `RandomizationDate` | date | ❌ No | Date when patient was randomized (V1 visit). Null if patient hasn't been randomized yet. Auto-set when V1 actual visit is recorded |
| `Status` | text | ✅ Yes | Patient journey status. See [Patient Status Values](#patient-status-values) below |

### Patient Status Values

| Status | Recruited? | Active? | Description |
|--------|-----------|---------|-------------|
| `screening` | ❌ No | ✅ Yes | Currently being screened, not yet randomized |
| `screen_failed` | ❌ No | ❌ No | Failed screening criteria before randomization |
| `dna_screening` | ❌ No | ❌ No | Did Not Attend (DNA) screening appointment |
| `randomized` | ✅ Yes | ✅ Yes | Passed screening and randomized into study |
| `withdrawn` | ✅ Yes | ❌ No | Withdrew from study after randomization |
| `deceased` | ✅ Yes | ❌ No | Died after randomization |
| `completed` | ✅ Yes | ❌ No | Successfully completed all study visits |
| `lost_to_followup` | ✅ Yes | ❌ No | Lost contact after randomization |

**Recruitment Definition:** A patient is counted as "recruited" when Status is one of: `randomized`, `withdrawn`, `deceased`, `completed`, `lost_to_followup`.

**Important:** Only recruited patients count toward recruitment targets. Patients in screening or who screen-failed do NOT count as recruited.

### Site Information

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| `PatientPractice` | text | ✅ Yes | **Recruitment origin** - where the patient was recruited from (e.g., "Ashfields", "Kiltearn"). Used for recruitment metrics by site |
| `SiteSeenAt` | text | ✅ Yes | **Visit location** - where the patient has their visits (e.g., "Ashfields", "Kiltearn"). Defaults to `PatientPractice` if not specified |

**Key Distinction:**
- `PatientPractice` = "Where did they come from?" (recruitment tracking)
- `SiteSeenAt` = "Where do they go for visits?" (scheduling and activity tracking)

### Pathway

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| `Pathway` | text | ❌ No | Study pathway variant. Examples: `standard`, `with_run_in`, `fast_track`. Must match a pathway in `trial_schedules` for this study. Defaults to `standard` |

**Pathway Example:**
- **Standard pathway**: Screening → Day 7 V1 → Day 14 V2
- **Run-in pathway**: Screening → Day 10 Run-in → Day 28 V1 → Day 35 V2

### Legacy/Compatibility

| Column | Type | Description |
|--------|------|-------------|
| `StartDate` | date | **DEPRECATED** - Legacy column. If present, code treats it as `ScreeningDate` for backward compatibility. Do not use in new implementations |

### Usage Examples

**Create a new screening patient:**
```sql
INSERT INTO patients (PatientID, Study, ScreeningDate, Status, PatientPractice, SiteSeenAt, Pathway)
VALUES ('P001', 'BaxDuo', '2024-01-15', 'screening', 'Ashfields', 'Ashfields', 'standard');
```

**Update patient status when they fail screening:**
```sql
UPDATE patients
SET Status = 'screen_failed'
WHERE PatientID = 'P001' AND Study = 'BaxDuo';
```

**Update patient status when randomized (auto-triggered by V1 visit):**
```sql
UPDATE patients
SET Status = 'randomized',
    RandomizationDate = '2024-01-22'
WHERE PatientID = 'P001' AND Study = 'BaxDuo';
```

---

## trial_schedules Table

Defines the complete visit schedule for each study, including visit timing, payments, and tolerances.

### Core Identification

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| `Study` | text | ✅ Yes | Study name/code. Must match patient `Study` values |
| `VisitName` | text | ✅ Yes | Visit identifier (e.g., "V1", "V2", "Screening", "Run-in") |
| `Pathway` | text | ❌ No | Pathway variant. Allows multiple visit schedules for same study. Defaults to `standard` |

### Visit Timing

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| `Day` | integer | ✅ Yes | Visit day offset from screening. **Day 1 = screening visit (baseline)**. All days should be positive (≥1) |
| `ToleranceBefore` | integer | ❌ No | Days before expected date that visit is still in protocol window (default: 0) |
| `ToleranceAfter` | integer | ❌ No | Days after expected date that visit is still in protocol window (default: 0) |

**Day Numbering System:**
- **Day 1** = Screening visit (the baseline for all calculations)
- **Day 0** = Special case for unplanned/ad-hoc visits (not used for scheduling)
- **Day 7, 14, 21...** = Days relative to screening

**Example Standard Pathway:**
- Day 1: Screening (VS) - baseline
- Day 7: Randomization (V1)
- Day 14: Follow-up (V2)
- Day 28: Follow-up (V3)

**Example Run-in Pathway:**
- Day 1: Screening (VS) - baseline
- Day 10: Run-in visit
- Day 28: Randomization (V1)
- Day 35: Follow-up (V2)

**Tolerance Windows:**
- If `ToleranceBefore = 3` and `ToleranceAfter = 7`, a Day 14 visit can occur between Day 11 and Day 21 and still be "in window"
- Visits outside tolerance windows are marked "OUT OF PROTOCOL"

### Month-Based Scheduling (Optional)

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| `IntervalUnit` | text | ❌ No | For month-based visits: `month` or `day`. Empty for standard day-based scheduling |
| `IntervalValue` | integer | ❌ No | For month-based visits: number of months/days. Used with `IntervalUnit` |

**Use Case:** Long-term follow-up visits that occur monthly rather than at specific day offsets.

### Financial

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| `Payment` | numeric | ❌ No | Per-visit payment amount in GBP (default: 0) |
| `SiteforVisit` | text | ✅ Yes | **Contract holder** - the site that holds the contract for this study (e.g., "Ashfields", "Kiltearn"). Used for financial reporting |

**Important:** `SiteforVisit` represents the contract holder, not necessarily where individual patients are seen. Use patient's `SiteSeenAt` for visit location.

### Visit Types

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| `VisitType` | text | ❌ No | Type of visit. See [Visit Type Values](#visit-type-values) below |

#### Visit Type Values

| Value | Description | Scheduled Per... |
|-------|-------------|-----------------|
| `patient` | Regular patient visit (default) | Per patient |
| `extra` | Extra patient visit | Per patient |
| `siv` | Site Initiation Visit | Per study (not per patient) |
| `monitor` | Monitoring visit | Per study (not per patient) |

**Study Events vs Patient Visits:**
- **Patient visits** (`patient`, `extra`) are scheduled for each patient
- **Study events** (`siv`, `monitor`) are scheduled once per study, not per patient

### Study Metadata (Optional)

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| `FPFV` | date | ❌ No | First Patient First Visit date |
| `LPFV` | date | ❌ No | Last Patient First Visit date |
| `LPLV` | date | ❌ No | Last Patient Last Visit date |
| `StudyStatus` | text | ❌ No | Study status (see `study_site_details` for primary source) |
| `RecruitmentTarget` | integer | ❌ No | Target number of patients to recruit |

**Note:** For Gantt chart and recruitment tracking, use `study_site_details` table as the primary source. These columns exist for backward compatibility.

### Usage Examples

**Define a standard pathway visit schedule:**
```sql
-- Screening visit (Day 1)
INSERT INTO trial_schedules (Study, Pathway, Day, VisitName, SiteforVisit, Payment, ToleranceBefore, ToleranceAfter, VisitType)
VALUES ('BaxDuo', 'standard', 1, 'Screening', 'Ashfields', 150.00, 0, 7, 'patient');

-- Randomization visit (Day 7)
INSERT INTO trial_schedules (Study, Pathway, Day, VisitName, SiteforVisit, Payment, ToleranceBefore, ToleranceAfter, VisitType)
VALUES ('BaxDuo', 'standard', 7, 'V1', 'Ashfields', 200.00, 3, 7, 'patient');

-- Follow-up visit (Day 14)
INSERT INTO trial_schedules (Study, Pathway, Day, VisitName, SiteforVisit, Payment, ToleranceBefore, ToleranceAfter, VisitType)
VALUES ('BaxDuo', 'standard', 14, 'V2', 'Ashfields', 175.00, 3, 7, 'patient');
```

**Define study events (SIV and monitoring):**
```sql
-- Site initiation visit (study-level, not patient-specific)
INSERT INTO trial_schedules (Study, Day, VisitName, SiteforVisit, Payment, VisitType)
VALUES ('BaxDuo', 0, 'SIV', 'Ashfields', 500.00, 'siv');

-- Monitoring visit
INSERT INTO trial_schedules (Study, Day, VisitName, SiteforVisit, Payment, VisitType)
VALUES ('BaxDuo', 0, 'Monitor', 'Ashfields', 300.00, 'monitor');
```

---

## actual_visits Table

Records all actual visits that have occurred or are proposed/planned for the future.

### Core Identification

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| `PatientID` | text | ✅ Yes | Patient identifier. Must match a patient in `patients` table for patient visits. For study events (SIV/Monitor), use a placeholder like `STUDY_EVENT` |
| `Study` | text | ✅ Yes | Study name/code |
| `VisitName` | text | ✅ Yes | Visit name. Should match a visit in `trial_schedules` for proper matching |
| `ActualDate` | date | ✅ Yes | Date the visit occurred or is planned to occur |

### Visit Classification

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| `VisitType` | text | ❌ No | Type of visit. Auto-detected from `VisitName` if not provided. Values: `patient`, `siv`, `monitor`, `patient_proposed`, `event_proposed` |

**Auto-Detection Rules:**
- If `VisitName` = "SIV" → `VisitType` = `siv`
- If `VisitName` contains "Monitor" → `VisitType` = `monitor`
- If `ActualDate` is in the future → appends `_proposed` suffix
- Otherwise → `VisitType` = `patient`

### Notes and Status Markers

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| `Notes` | text | ❌ No | Free-text notes about the visit. Use special markers (see below) to trigger status updates |

#### Special Markers in Notes

| Marker | Effect | Description |
|--------|--------|-------------|
| `ScreenFail` | Sets patient Status = `screen_failed` | Patient failed screening criteria at this visit |
| `Withdrawn` | Sets patient Status = `withdrawn` | Patient withdrew from study at this visit |
| `Died` | Sets patient Status = `deceased` | Patient died at this visit |
| `DNA` | Informational only | Patient Did Not Attend this visit |

**Important:** When you record a visit with `ScreenFail` in the Notes field, the system automatically updates the patient's Status to `screen_failed`. Similarly for `Withdrawn` and `Died`.

**DNA (Did Not Attend):** For patients who don't attend screening, set their Status to `dna_screening` directly in the patients table rather than using Notes.

### Proposed vs Actual Visits

| Date Condition | Treatment |
|----------------|-----------|
| `ActualDate` < today | **Actual visit** - already occurred |
| `ActualDate` = today | **Actual visit** - happening today |
| `ActualDate` > today | **Proposed visit** - planned for future |

**Proposed Visit Behavior:**
- Appears on calendar in future
- Suppresses predicted visits for that same visit name
- Can be used to show rescheduled visits
- Useful for showing study completion dates

### Usage Examples

**Record a completed screening visit:**
```sql
INSERT INTO actual_visits (PatientID, Study, VisitName, ActualDate, VisitType, Notes)
VALUES ('P001', 'BaxDuo', 'Screening', '2024-01-15', 'patient', 'Patient consented, all eligibility criteria met');
```

**Record a screen failure:**
```sql
INSERT INTO actual_visits (PatientID, Study, VisitName, ActualDate, VisitType, Notes)
VALUES ('P002', 'BaxDuo', 'Screening', '2024-01-16', 'patient', 'ScreenFail - BP too high');
-- This automatically sets patients.Status = 'screen_failed' for P002
```

**Record a randomization visit (triggers status update):**
```sql
INSERT INTO actual_visits (PatientID, Study, VisitName, ActualDate, VisitType, Notes)
VALUES ('P001', 'BaxDuo', 'V1', '2024-01-22', 'patient', 'Randomized to treatment arm A');
-- This automatically sets patients.Status = 'randomized' and RandomizationDate = '2024-01-22' for P001
```

**Record a patient withdrawal:**
```sql
INSERT INTO actual_visits (PatientID, Study, VisitName, ActualDate, VisitType, Notes)
VALUES ('P003', 'BaxDuo', 'V2', '2024-02-05', 'patient', 'Withdrawn - patient request');
-- This automatically sets patients.Status = 'withdrawn' for P003
```

**Record a proposed future visit:**
```sql
INSERT INTO actual_visits (PatientID, Study, VisitName, ActualDate, VisitType, Notes)
VALUES ('P001', 'BaxDuo', 'V5', '2024-06-15', 'patient_proposed', 'Final visit - study completion');
```

**Record a study event (SIV):**
```sql
INSERT INTO actual_visits (PatientID, Study, VisitName, ActualDate, VisitType, Notes)
VALUES ('STUDY_EVENT', 'BaxDuo', 'SIV', '2023-12-01', 'siv', 'Site initiation completed, ready for recruitment');
```

**Record a patient who didn't attend:**
```sql
INSERT INTO actual_visits (PatientID, Study, VisitName, ActualDate, VisitType, Notes)
VALUES ('P004', 'BaxDuo', 'V2', '2024-02-10', 'patient', 'DNA - patient did not attend, will reschedule');
```

---

## study_site_details Table

Stores contract-level study metadata and recruitment targets. This is the **primary source** for Gantt charts and recruitment tracking.

### Core Identification

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| `Study` | text | ✅ Yes | Study name/code |
| `ContractSite` | text | ✅ Yes | Contract holder site (e.g., "Ashfields", "Kiltearn"). This is the grouping key for Gantt and recruitment |

**Note:** One study can have multiple rows if multiple sites hold contracts for it.

### Study Status

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| `StudyStatus` | text | ❌ No | Current study status. See [Study Status Values](#study-status-values) below |

#### Study Status Values

| Status | Display Color | Description |
|--------|--------------|-------------|
| `active` | Green | Study is actively recruiting and conducting visits |
| `contracted` | Blue | Contract signed, study setup in progress |
| `in_setup` | Yellow | Site setup activities in progress |
| `expression_of_interest` | Orange | Expression of Interest submitted, awaiting approval |
| `eoi_didnt_get` | Gray | Expression of Interest was not successful |

### Key Dates

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| `FPFV` | date | ❌ No | First Patient First Visit - when the first patient had their first visit |
| `LPFV` | date | ❌ No | Last Patient First Visit - target date for last patient to start |
| `LPLV` | date | ❌ No | Last Patient Last Visit - target date for study completion |
| `EOIDate` | date | ❌ No | Expression of Interest submission date |

### Recruitment

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| `RecruitmentTarget` | integer | ❌ No | Target number of patients to recruit for this study at this site |

### Documentation

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| `Description` | text | ❌ No | Study description or notes |
| `StudyURL` | text | ❌ No | Link to study protocol or documentation |
| `DocumentLinks` | text | ❌ No | Additional document links (JSON or comma-separated) |

### Usage Examples

**Add a new active study:**
```sql
INSERT INTO study_site_details (Study, ContractSite, StudyStatus, RecruitmentTarget, FPFV, LPFV, LPLV, Description)
VALUES (
    'BaxDuo',
    'Ashfields',
    'active',
    50,
    '2024-01-15',
    '2024-12-31',
    '2025-06-30',
    'Phase 3 trial for treatment X vs Y'
);
```

**Update study status:**
```sql
UPDATE study_site_details
SET StudyStatus = 'active', FPFV = '2024-01-15'
WHERE Study = 'BaxDuo' AND ContractSite = 'Ashfields';
```

---

## Common Patterns

### Pattern 1: Adding a New Patient

```sql
-- Step 1: Add patient in screening
INSERT INTO patients (PatientID, Study, ScreeningDate, Status, PatientPractice, SiteSeenAt, Pathway)
VALUES ('P005', 'BaxDuo', '2024-01-20', 'screening', 'Ashfields', 'Ashfields', 'standard');

-- Step 2: Record screening visit
INSERT INTO actual_visits (PatientID, Study, VisitName, ActualDate, VisitType, Notes)
VALUES ('P005', 'BaxDuo', 'Screening', '2024-01-20', 'patient', 'Initial screening completed');

-- Step 3: Record randomization (auto-updates status)
INSERT INTO actual_visits (PatientID, Study, VisitName, ActualDate, VisitType, Notes)
VALUES ('P005', 'BaxDuo', 'V1', '2024-01-27', 'patient', 'Randomized successfully');
-- Patient status automatically becomes 'randomized' and RandomizationDate set to '2024-01-27'
```

### Pattern 2: Handling Screen Failures

```sql
-- Option A: Record screen failure visit (auto-updates status)
INSERT INTO actual_visits (PatientID, Study, VisitName, ActualDate, VisitType, Notes)
VALUES ('P006', 'BaxDuo', 'Screening', '2024-01-21', 'patient', 'ScreenFail - exclusion criteria');
-- Patient status automatically becomes 'screen_failed'

-- Option B: Manually update patient status
UPDATE patients
SET Status = 'screen_failed'
WHERE PatientID = 'P006' AND Study = 'BaxDuo';
```

### Pattern 3: Multi-Site Studies

```sql
-- Contract holders for a multi-site study
INSERT INTO study_site_details (Study, ContractSite, StudyStatus, RecruitmentTarget)
VALUES ('MultiSite', 'Ashfields', 'active', 30);

INSERT INTO study_site_details (Study, ContractSite, StudyStatus, RecruitmentTarget)
VALUES ('MultiSite', 'Kiltearn', 'active', 20);

-- Patient recruited at Kiltearn but seen at Ashfields
INSERT INTO patients (PatientID, Study, ScreeningDate, Status, PatientPractice, SiteSeenAt, Pathway)
VALUES ('P007', 'MultiSite', '2024-01-22', 'screening', 'Kiltearn', 'Ashfields', 'standard');
-- PatientPractice = 'Kiltearn' (for recruitment metrics)
-- SiteSeenAt = 'Ashfields' (for visit scheduling)
```

### Pattern 4: Multiple Pathways

```sql
-- Standard pathway schedule
INSERT INTO trial_schedules (Study, Pathway, Day, VisitName, SiteforVisit, Payment)
VALUES ('FlexStudy', 'standard', 1, 'Screening', 'Ashfields', 150.00);
INSERT INTO trial_schedules (Study, Pathway, Day, VisitName, SiteforVisit, Payment)
VALUES ('FlexStudy', 'standard', 7, 'V1', 'Ashfields', 200.00);

-- Run-in pathway schedule (longer timeline)
INSERT INTO trial_schedules (Study, Pathway, Day, VisitName, SiteforVisit, Payment)
VALUES ('FlexStudy', 'with_run_in', 1, 'Screening', 'Ashfields', 150.00);
INSERT INTO trial_schedules (Study, Pathway, Day, VisitName, SiteforVisit, Payment)
VALUES ('FlexStudy', 'with_run_in', 10, 'Run-in', 'Ashfields', 100.00);
INSERT INTO trial_schedules (Study, Pathway, Day, VisitName, SiteforVisit, Payment)
VALUES ('FlexStudy', 'with_run_in', 28, 'V1', 'Ashfields', 200.00);

-- Patient on run-in pathway
INSERT INTO patients (PatientID, Study, ScreeningDate, Status, PatientPractice, SiteSeenAt, Pathway)
VALUES ('P008', 'FlexStudy', '2024-01-23', 'screening', 'Ashfields', 'Ashfields', 'with_run_in');
```

---

## Data Relationships

### Primary Keys and Foreign Keys

```
patients
  ├─ PatientID + Study (composite primary key)
  ├─ Study → trial_schedules.Study
  ├─ Study + Pathway → trial_schedules.Study + Pathway
  └─ PatientPractice, SiteSeenAt → study_site_details.ContractSite (informal)

trial_schedules
  ├─ Study + Pathway + Day + VisitName (composite primary key)
  └─ SiteforVisit → study_site_details.ContractSite (informal)

actual_visits
  ├─ No formal primary key (can have multiple records per patient+visit if rescheduled)
  ├─ PatientID + Study → patients.PatientID + Study
  └─ Study + VisitName → trial_schedules.Study + VisitName (for matching)

study_site_details
  └─ Study + ContractSite (composite primary key)
```

### Data Flow for Visit Scheduling

```
1. Patient created with ScreeningDate
   ↓
2. System fetches trial_schedules for patient's Study + Pathway
   ↓
3. For each visit in schedule:
   Expected Date = ScreeningDate + (Day - 1) days
   ↓
4. Check actual_visits for this patient+visit
   ↓
5. If actual visit exists:
   - Show actual date on calendar
   - Check if within tolerance window
   ↓
6. If no actual visit:
   - Show predicted visit on expected date
   - Unless proposed visit exists for this visit name
```

### Data Flow for Status Updates

```
When actual_visit is created with Notes containing special markers:

ScreenFail in Notes → patients.Status = 'screen_failed'
Withdrawn in Notes → patients.Status = 'withdrawn'
Died in Notes → patients.Status = 'deceased'

When actual_visit is created for V1 (randomization):
→ patients.Status = 'randomized'
→ patients.RandomizationDate = actual_visit.ActualDate
```

---

## Best Practices

### 1. Patient Status Management

✅ **DO:**
- Let the system auto-update Status when recording V1 visits
- Use Notes markers (`ScreenFail`, `Withdrawn`, `Died`) to trigger status updates
- Set Status = `dna_screening` for patients who never attend screening

❌ **DON'T:**
- Manually set Status = `randomized` (let V1 visit trigger it)
- Forget to record screen failures (affects recruitment metrics)
- Use Status = `screening` for patients who screen-failed

### 2. Site Assignment

✅ **DO:**
- Set `PatientPractice` to where they were recruited from
- Set `SiteSeenAt` to where they actually have visits
- Keep `SiteforVisit` in trial_schedules as the contract holder

❌ **DON'T:**
- Mix up recruitment site with visit site
- Change `PatientPractice` after creation (affects historical recruitment metrics)

### 3. Visit Scheduling

✅ **DO:**
- Use Day 1 for screening visit as the baseline
- Make all visit days positive (≥1)
- Use Day 0 only for unplanned/ad-hoc visits
- Set appropriate tolerance windows

❌ **DON'T:**
- Use negative day numbers (old system - no longer supported)
- Skip Day 1 (screening must be Day 1)
- Use Day 0 for regular scheduled visits

### 4. Data Consistency

✅ **DO:**
- Ensure Study values match across patients, trial_schedules, actual_visits
- Use consistent Pathway names within a study
- Keep ContractSite values consistent across tables

❌ **DON'T:**
- Create patients for studies that don't exist in trial_schedules
- Use mismatched Study names (case-sensitive matching)
- Leave required fields NULL

---

## Troubleshooting

### Problem: Patient visits not showing on calendar

**Check:**
1. Does `patients.Study` exactly match `trial_schedules.Study`? (case-sensitive)
2. Does `patients.Pathway` match `trial_schedules.Pathway`?
3. Is `patients.ScreeningDate` set and valid?
4. Are there visits defined in trial_schedules for this Study+Pathway?

### Problem: Patient not counting as recruited

**Check:**
1. Is `patients.Status` one of: `randomized`, `withdrawn`, `deceased`, `completed`, `lost_to_followup`?
2. Status = `screening` or `screen_failed` patients do NOT count as recruited

### Problem: Visit marked as "OUT OF PROTOCOL"

**Reason:** Visit occurred outside the tolerance window.

**Check:**
1. `trial_schedules.ToleranceBefore` and `ToleranceAfter` values
2. Expected date vs actual date difference
3. If intentional, document reason in `actual_visits.Notes`

### Problem: Status not updating automatically

**Check:**
1. For screen failures: Is `ScreenFail` in `actual_visits.Notes`?
2. For randomization: Is `VisitName` matching the V1 pattern (^V1)?
3. For withdrawals: Is `Withdrawn` in `actual_visits.Notes`?

---

## Glossary

- **Baseline**: The starting point for visit calculations (Day 1 = ScreeningDate)
- **Contract Holder**: The site that holds the contract for a study (SiteforVisit / ContractSite)
- **DNA**: Did Not Attend - patient missed a scheduled visit
- **Pathway**: A variant visit schedule for the same study
- **Proposed Visit**: A future planned visit (ActualDate > today)
- **Recruited**: Patient has been randomized (Status IN recruited values)
- **Screening**: Pre-randomization evaluation period
- **Study Event**: Visit that occurs once per study (SIV, Monitor), not per patient
- **Tolerance Window**: Acceptable date range for a visit to be considered "in protocol"

---

## Migration from Old System

If migrating from the old V1-based (Day 0) system:

### Key Changes

| Old System | New System |
|------------|------------|
| Day 0 = V1 (randomization) | Day 1 = Screening |
| Negative days for pre-V1 visits | All days positive (≥1) |
| StartDate = randomization | ScreeningDate = screening |
| No Status column | Status tracks patient journey |
| N/A | RandomizationDate tracks actual V1 |

### Migration Steps

See `MIGRATION_SQL.md` for complete SQL migration scripts.

**Summary:**
1. Add new columns: ScreeningDate, RandomizationDate, Status
2. Migrate StartDate → ScreeningDate
3. Update trial_schedules Day values (shift by offset to make Day 1 = screening)
4. Update patient statuses based on notes
5. Add constraints and indexes

---

## Support

For questions or issues:
1. Check this guide first
2. Review `MIGRATION_SQL.md` for migration-specific issues
3. Check activity log in application for error messages
4. Contact system administrator

---

**Document Version:** 1.0
**Last Updated:** 2026-01-22
**Compatible with:** Clinical Trial Calendar v2.0+
