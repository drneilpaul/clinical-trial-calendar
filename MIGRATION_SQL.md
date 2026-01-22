# Database Migration SQL - Screening-Based Day System

## Complete Status List

### Status Values:
- **'screening'** - Currently being screened, not yet randomized (NOT recruited, ACTIVE)
- **'screen_failed'** - Failed screening criteria (NOT recruited, INACTIVE)
- **'dna_screening'** - Did not attend screening appointment (NOT recruited, INACTIVE)
- **'randomized'** - Active in study (RECRUITED, ACTIVE)
- **'withdrawn'** - Withdrew after randomization (RECRUITED, INACTIVE)
- **'deceased'** - Died after randomization (RECRUITED, INACTIVE)
- **'completed'** - Finished study successfully (RECRUITED, INACTIVE)
- **'lost_to_followup'** - Lost contact after randomization (RECRUITED, INACTIVE)

### Recruitment Definition:
**RECRUITED** = Status IN ('randomized', 'withdrawn', 'deceased', 'completed', 'lost_to_followup')

**NOT RECRUITED** = Status IN ('screening', 'screen_failed', 'dna_screening')

## Step 1: Add New Columns

```sql
ALTER TABLE patients ADD COLUMN "ScreeningDate" DATE;
ALTER TABLE patients ADD COLUMN "RandomizationDate" DATE;
ALTER TABLE patients ADD COLUMN "Status" TEXT DEFAULT 'screening';
```

## Step 2: Migrate Existing Data

```sql
UPDATE patients
SET "ScreeningDate" = "StartDate",
    "RandomizationDate" = "StartDate",
    "Status" = 'randomized'
WHERE "StartDate" IS NOT NULL;
```

## Step 3: Update Patient Statuses from Notes

### Screen Failures
```sql
UPDATE patients p
SET "Status" = 'screen_failed',
    "RandomizationDate" = NULL
FROM actual_visits av
WHERE p."PatientID" = av."PatientID"
  AND p."Study" = av."Study"
  AND av."Notes" ILIKE '%ScreenFail%';
```

### Withdrawals
```sql
UPDATE patients p
SET "Status" = 'withdrawn'
FROM actual_visits av
WHERE p."PatientID" = av."PatientID"
  AND p."Study" = av."Study"
  AND av."Notes" ILIKE '%Withdrawn%'
  AND p."Status" != 'screen_failed';
```

### Deceased
```sql
UPDATE patients p
SET "Status" = 'deceased'
FROM actual_visits av
WHERE p."PatientID" = av."PatientID"
  AND p."Study" = av."Study"
  AND av."Notes" ILIKE '%Died%'
  AND p."Status" NOT IN ('screen_failed', 'withdrawn');
```

### DNA Screening
```sql
UPDATE patients p
SET "Status" = 'dna_screening',
    "RandomizationDate" = NULL
FROM actual_visits av
WHERE p."PatientID" = av."PatientID"
  AND p."Study" = av."Study"
  AND av."Notes" ILIKE '%DNA%'
  AND p."Status" NOT IN ('screen_failed', 'withdrawn', 'deceased', 'randomized');
```

## Step 4: Add Constraints and Indexes

```sql
ALTER TABLE patients ADD CONSTRAINT check_status
CHECK ("Status" IN ('screening', 'screen_failed', 'dna_screening', 'randomized', 'withdrawn', 'deceased', 'completed', 'lost_to_followup'));

CREATE INDEX idx_patients_status ON patients("Status");
CREATE INDEX idx_patients_screening_date ON patients("ScreeningDate");
CREATE INDEX idx_patients_randomization_date ON patients("RandomizationDate");
```

## Step 5: Update Trial Schedules

### Find Offsets for Each Study/Pathway

```sql
SELECT
  "Study",
  "Pathway",
  MIN("Day") as min_day,
  CASE
    WHEN MIN("Day") < 0 THEN (ABS(MIN("Day")) + 1)
    ELSE 0
  END as offset_to_add
FROM trial_schedules
WHERE "VisitType" = 'patient' OR "VisitType" IS NULL
GROUP BY "Study", "Pathway"
ORDER BY "Study", "Pathway";
```

### Apply Offset (Run for EACH study/pathway)

Replace `STUDY_NAME`, `PATHWAY_NAME`, and `OFFSET_VALUE`:

```sql
UPDATE trial_schedules
SET "Day" = "Day" + OFFSET_VALUE
WHERE "Study" = 'STUDY_NAME'
  AND "Pathway" = 'PATHWAY_NAME';
```

Example for BaxDuo standard pathway (offset = 7):
```sql
UPDATE trial_schedules
SET "Day" = "Day" + 7
WHERE "Study" = 'BaxDuo'
  AND "Pathway" = 'standard';
```

### Verify No Negative Days

```sql
SELECT "Study", "Pathway", "VisitName", "Day"
FROM trial_schedules
WHERE "Day" < 0
ORDER BY "Study", "Pathway", "Day";
```

Should return 0 rows.

## Verification Queries

### Check Patient Status Distribution

```sql
SELECT "Status", COUNT(*) as count
FROM patients
GROUP BY "Status"
ORDER BY count DESC;
```

### Check for Patients Without Screening Date

```sql
SELECT "PatientID", "Study", "ScreeningDate", "Status"
FROM patients
WHERE "ScreeningDate" IS NULL;
```

### Check Recruited Patients Have Randomization Date

```sql
SELECT "PatientID", "Study", "Status", "RandomizationDate"
FROM patients
WHERE "Status" IN ('randomized', 'withdrawn', 'deceased', 'completed', 'lost_to_followup')
  AND "RandomizationDate" IS NULL;
```

### Check V1 Visits in Schedules

```sql
SELECT "Study", "Pathway", "VisitName", "Day"
FROM trial_schedules
WHERE "VisitName" ILIKE 'V1%'
ORDER BY "Study", "Pathway", "Day";
```

### DNA Screening Rate by Site

```sql
SELECT
  p."PatientPractice" as site,
  COUNT(*) FILTER (WHERE p."Status" = 'dna_screening') as dna_count,
  COUNT(*) FILTER (WHERE p."Status" IN ('randomized', 'withdrawn', 'deceased', 'completed', 'lost_to_followup')) as recruited_count,
  COUNT(*) FILTER (WHERE p."Status" = 'screen_failed') as screen_failed_count,
  COUNT(*) as total_patients,
  ROUND(100.0 * COUNT(*) FILTER (WHERE p."Status" = 'dna_screening') / NULLIF(COUNT(*), 0), 2) as dna_percentage
FROM patients p
GROUP BY p."PatientPractice"
ORDER BY dna_count DESC;
```

## Optional: Drop Old StartDate Column

**ONLY run this after verifying everything works!**

```sql
ALTER TABLE patients DROP COLUMN "StartDate";
```

## Rollback Plan

If issues occur:

1. Restore from backup in Supabase dashboard
2. Revert code changes: `git revert HEAD`
3. Investigate issues before retrying
