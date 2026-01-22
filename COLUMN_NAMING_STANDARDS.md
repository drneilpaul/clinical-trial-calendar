# Column Naming Standards & Legacy Compatibility
**Date:** 2026-01-22

## Overview

This document describes the **canonical column names** used throughout the system and how legacy column names are handled for backward compatibility.

---

## Canonical Column Names (Current Standard)

### Patients Table

| Column | Type | Description | Required |
|--------|------|-------------|----------|
| **PatientID** | text | Unique patient identifier | Yes |
| **Study** | text | Study name/code | Yes |
| **ScreeningDate** | date | First screening visit (Day 1 baseline) | Yes |
| **RandomizationDate** | date | Randomization date (V1) | No |
| **Status** | text | Patient journey status (8 values) | No (default: 'screening') |
| **PatientPractice** | text | **Recruitment origin** (where patient comes from) | Yes |
| **SiteSeenAt** | text | **Visit location** (where patient is seen) | Yes |
| **Pathway** | text | Study pathway variant (standard, with_run_in, etc.) | No (default: 'standard') |

**Status Values:**
- Not Recruited: `screening`, `screen_failed`, `dna_screening`
- Recruited: `randomized`, `withdrawn`, `deceased`, `completed`, `lost_to_followup`

**Key Concepts:**
- **PatientPractice** = Recruitment site (drives recruitment metrics)
- **SiteSeenAt** = Visit location (drives visit scheduling and activity)
- These can be the same or different (e.g., patient from Practice A seen at Practice B)

### Trial Schedules Table

| Column | Type | Description | Required |
|--------|------|-------------|----------|
| **Study** | text | Study name/code | Yes |
| **Pathway** | text | Study pathway variant | No (default: 'standard') |
| **Day** | int | Visit day relative to screening (Day 1 = screening) | Yes |
| **VisitName** | text | Visit identifier | Yes |
| **SiteforVisit** | text | **Contract holder** (ContractSite) | Yes |
| **Payment** | numeric | Per-visit payment amount | No |
| **ToleranceBefore** | int | Days before visit window | No |
| **ToleranceAfter** | int | Days after visit window | No |
| **IntervalUnit** | text | Interval unit (days, weeks, months) | No |
| **IntervalValue** | int | Interval value | No |
| **VisitType** | text | Visit type (patient, siv, monitor) | No |
| **FPFV** | date | First patient first visit override | No |
| **LPFV** | date | Last patient first visit override | No |
| **LPLV** | date | Last patient last visit override | No |
| **StudyStatus** | text | Study status (active, completed, etc.) | No |
| **RecruitmentTarget** | int | Target recruitment number | No |

**Key Concepts:**
- **SiteforVisit** = Contract holder (the site that holds the contract)
- **Day 1** = Screening visit (baseline)
- **Days are positive** (no negative days)
- **Payment** = Per-visit payment (not "Income")

### Actual Visits Table

| Column | Type | Description | Required |
|--------|------|-------------|----------|
| **PatientID** | text | Patient identifier | Yes |
| **Study** | text | Study name/code | Yes |
| **VisitName** | text | Visit identifier | Yes |
| **ActualDate** | date | Date visit occurred | Yes |
| **Notes** | text | Visit notes (ScreenFail, Withdrawn, Died, DNA) | No |
| **VisitType** | text | Visit type (patient, siv, monitor, extra) | No |
| **ActualPayment** | numeric | Actual payment received | No |

**Special Notes Values:**
- `ScreenFail` - Patient failed screening
- `Withdrawn` - Patient withdrew
- `Died` - Patient deceased
- `DNA` - Did not attend

### Study Site Details Table

| Column | Type | Description | Required |
|--------|------|-------------|----------|
| **Study** | text | Study name/code | Yes |
| **ContractSite** | text | **Contract holder** (same as SiteforVisit) | Yes |
| **StudyStatus** | text | Study status | No |
| **RecruitmentTarget** | int | Target recruitment | No |
| **FPFV** | date | First patient first visit | No |
| **LPFV** | date | Last patient first visit | No |
| **LPLV** | date | Last patient last visit | No |
| **Description** | text | Study description | No |
| **EOIDate** | date | Expression of interest date | No |
| **StudyURL** | text | Study URL | No |
| **DocumentLinks** | text | Document links | No |

---

## Generated Calendar Columns (Runtime)

The calendar-building process generates these columns:

| Column | Description |
|--------|-------------|
| **Date** | Visit date |
| **Visit** | Visit name |
| **Study** | Study name |
| **PatientID** | Patient identifier (or blank for unscheduled) |
| **SiteofVisit** | **Visit location** (from patient's SiteSeenAt) |
| **ContractSite** | **Contract holder** (from trial_schedules SiteforVisit) |
| **PatientOrigin** | **Recruitment site** (from patient's PatientPractice) |
| **Payment** | Visit payment |
| **IsActual** | True if visit actually occurred |
| **IsProposed** | True if visit is scheduled but not yet occurred |
| **FYStart** | Financial year start date |
| **MonthYear** | Month and year |
| **QuarterYear** | Quarter and year |
| **FinancialYear** | Financial year (e.g., "FY25/26") |

**Three Key Site Columns:**
1. **ContractSite** - Who holds the contract (from trial_schedules.SiteforVisit)
2. **SiteofVisit** - Where the visit happens (from patients.SiteSeenAt)
3. **PatientOrigin** - Where the patient was recruited from (from patients.PatientPractice)

---

## Legacy Column Names (Deprecated but Supported)

### Legacy Patient Columns

| Legacy Name | Canonical Name | Status | Notes |
|-------------|---------------|--------|-------|
| **StartDate** | **ScreeningDate** | ⚠️ Deprecated | System converts StartDate → ScreeningDate on load |
| **Site** | **PatientPractice** | ⚠️ Deprecated | Ambiguous - use PatientPractice (origin) |
| **PatientSite** | **PatientPractice** | ⚠️ Deprecated | Use PatientPractice |
| **OriginSite** | **PatientPractice** | ⚠️ Deprecated | Use PatientPractice |
| **Practice** | **PatientPractice** | ⚠️ Deprecated | Use PatientPractice |
| **HomeSite** | **PatientPractice** | ⚠️ Deprecated | Use PatientPractice |

**How System Handles Legacy Names:**
```python
# System searches for origin site in this order:
origin_candidates = ['PatientPractice', 'PatientSite', 'Site', 'OriginSite', 'Practice', 'HomeSite']
```

### Legacy Visit Columns

| Legacy Name | Canonical Name | Status | Notes |
|-------------|---------------|--------|-------|
| **Income** | **Payment** | ⚠️ Deprecated | Use Payment (per-visit amount) |
| **VisitSite** | **SiteofVisit** | ⚠️ Deprecated | Use SiteofVisit |
| **Visit Site** | **SiteofVisit** | ⚠️ Deprecated | Use SiteofVisit (no space) |

### Legacy Contract Holder Columns

| Legacy Name | Canonical Name | Status | Notes |
|-------------|---------------|--------|-------|
| **ContractedSite** | **ContractSite** | ⚠️ Deprecated | Use ContractSite |

**How System Handles Contract Site:**
```python
# In trial_schedules table, column is SiteforVisit
# In study_site_details table, column is ContractSite
# In generated calendar, column is ContractSite
# These all refer to the same concept: contract holder
```

---

## Column Naming Philosophy

### Why These Names?

1. **PatientPractice** (not "Site")
   - Explicit: clearly indicates the patient's recruitment origin
   - Avoids ambiguity with visit location
   - Drives recruitment metrics

2. **SiteSeenAt** (not "VisitSite")
   - Explicit: clearly indicates where patient is seen
   - Distinguishes from recruitment origin
   - Drives visit scheduling

3. **SiteforVisit** (not "ContractSite" in trial_schedules)
   - Historical naming in trial_schedules table
   - Maps to ContractSite in study_site_details
   - Same concept, different table

4. **ContractSite** (in study_site_details and generated calendar)
   - Clear: indicates contract holder
   - Used in financial calculations
   - Determines payment attribution

5. **ScreeningDate** (not "StartDate")
   - Explicit: clearly indicates Day 1 (screening)
   - Removes ambiguity (was it screening or randomization?)
   - Aligns with Day 1 baseline architecture

6. **RandomizationDate** (new column)
   - Explicit: actual recruitment date (V1)
   - Used for recruitment timing metrics
   - Separates screening from recruitment

7. **Payment** (not "Income")
   - Clearer: payment per visit
   - "Income" implies received money
   - "Payment" is the scheduled/expected amount

---

## Migration Strategy

### For Old Data (CSV Uploads)

**System automatically handles:**
1. `StartDate` → `ScreeningDate` conversion
2. Legacy site columns → `PatientPractice`
3. `Income` → `Payment` (if present)

**Code Pattern:**
```python
# Check for ScreeningDate first, fallback to StartDate
date_column = None
if 'ScreeningDate' in df.columns:
    date_column = 'ScreeningDate'
elif 'StartDate' in df.columns:
    date_column = 'StartDate'
```

### For Database Exports

**Patient CSV Export includes:**
- PatientID, Study, ScreeningDate, RandomizationDate, Status
- PatientPractice, SiteSeenAt, Pathway

**Backward compatibility:**
- If old data has only `StartDate`, exports as `ScreeningDate`
- System adds column rename: `StartDate` → `ScreeningDate`

---

## Common Confusion Points

### 1. "Site" is Ambiguous

❌ **DON'T use:**
- `Site` (too vague)

✅ **DO use:**
- `PatientPractice` (recruitment origin)
- `SiteSeenAt` (visit location)
- `ContractSite` (contract holder)

### 2. PatientPractice vs SiteSeenAt

**Example:**
- Patient recruited from **Practice A** (PatientPractice = "Practice A")
- Patient seen at **Practice B** (SiteSeenAt = "Practice B")

**When they differ:**
- Practice A gets credit for recruitment
- Practice B handles the visits
- Contract holder (SiteforVisit) determines payment

### 3. SiteforVisit vs ContractSite

**These are the same concept:**
- In **trial_schedules**: Column is `SiteforVisit`
- In **study_site_details**: Column is `ContractSite`
- In **generated calendar**: Column is `ContractSite`

**Why different names?**
- Historical: `SiteforVisit` used in trial schedules
- Clearer: `ContractSite` used elsewhere
- Both mean: who holds the contract

### 4. StartDate vs ScreeningDate vs RandomizationDate

**Old system:**
- `StartDate` = ambiguous (was it screening or randomization?)
- System used V1 as Day 0 baseline
- Negative days for pre-randomization visits

**New system:**
- `ScreeningDate` = Day 1 baseline (first screening visit)
- `RandomizationDate` = actual recruitment date (V1)
- `Status` = patient journey tracking
- All days are positive

---

## Verification Commands

### Check for Legacy Column Usage

```bash
# Find StartDate references
grep -n "StartDate" *.py

# Find legacy Site references
grep -n "'Site'" *.py

# Find Income references (should be Payment)
grep -n "Income" *.py | grep -v "# "

# Find legacy patient site columns
grep -n "PatientSite\|OriginSite\|HomeSite" *.py
```

### Check Database Schema

```sql
-- Check patients table columns
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'patients';

-- Check trial_schedules columns
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'trial_schedules';
```

---

## Best Practices

### When Writing New Code

1. **Always use canonical names:**
   - PatientPractice (not Site)
   - SiteSeenAt (not VisitSite)
   - ScreeningDate (not StartDate)
   - Payment (not Income)

2. **Add fallback for backward compatibility:**
   ```python
   # Good pattern
   date_column = None
   if 'ScreeningDate' in df.columns:
       date_column = 'ScreeningDate'
   elif 'StartDate' in df.columns:
       date_column = 'StartDate'
   ```

3. **Document legacy support:**
   ```python
   # REFACTOR: Use ScreeningDate (with StartDate fallback for backward compatibility)
   ```

### When Reading Documentation

- If you see "Site" alone → check context for which site type
- "Contract holder" = ContractSite = SiteforVisit
- "Recruitment site" = PatientPractice
- "Visit location" = SiteSeenAt

---

## Files With Column Name Handling

### Files That Handle Legacy Patient Site Names
- `app.py` (line 44)
- `calendar_builder.py` (line 125)
- `display_components.py` (lines 1853, 1901)
- `helpers.py` (line 17)

### Files That Handle StartDate → ScreeningDate
- `database.py` (export functions)
- `app.py` (multiple locations)
- `data_analysis.py` (line 328+)
- `display_components.py` (line 78)
- `gantt_view.py` (multiple locations)
- `patient_processor.py` (line 447)

### Files That Clean Up Legacy Columns
- `processing_calendar.py` (lines 378-388) - Removes redundant 'Site' and 'OriginSite' columns

---

## Summary Table: Canonical vs Legacy

| Concept | Canonical Name | Legacy Names | Table | Status |
|---------|---------------|--------------|-------|--------|
| Day 1 baseline | ScreeningDate | StartDate | patients | ✅ Current |
| Actual recruitment | RandomizationDate | - | patients | ✅ Current |
| Patient journey | Status | - | patients | ✅ Current |
| Recruitment origin | PatientPractice | Site, PatientSite, OriginSite, Practice, HomeSite | patients | ✅ Current |
| Visit location | SiteSeenAt | VisitSite, Visit Site | patients | ✅ Current |
| Study pathway | Pathway | - | patients, trial_schedules | ✅ Current |
| Contract holder (schedules) | SiteforVisit | ContractedSite | trial_schedules | ✅ Current |
| Contract holder (details) | ContractSite | ContractedSite | study_site_details | ✅ Current |
| Visit payment | Payment | Income | trial_schedules, actual_visits | ✅ Current |

---

## FAQ

**Q: Why do we have both SiteforVisit and ContractSite?**
A: Historical reasons. They mean the same thing (contract holder). SiteforVisit is used in trial_schedules, ContractSite is used in study_site_details and generated calendar.

**Q: When should I use PatientPractice vs SiteSeenAt?**
A: Use PatientPractice for recruitment metrics (who recruited the patient). Use SiteSeenAt for visit scheduling (where the patient is seen).

**Q: Can PatientPractice and SiteSeenAt be different?**
A: Yes! A patient recruited from Practice A can be seen at Practice B.

**Q: What if my old CSV has only StartDate?**
A: System automatically converts StartDate → ScreeningDate. It will work.

**Q: Should I still include StartDate in new uploads?**
A: No. Use ScreeningDate and RandomizationDate instead. StartDate is deprecated.

**Q: What's the difference between Payment and Income?**
A: Payment = scheduled per-visit payment amount. Income = total money received. Use "Payment" in data, display as "Income" in reports if needed.

---

**Last Updated:** 2026-01-22
**Status:** ✅ Active Standard
