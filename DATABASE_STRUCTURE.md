# Database Structure

This document describes the Supabase tables and the meaning of key columns.

## Tables

### patients
Tracks enrolled patients and their origin/visit location.

Key columns:
- `PatientID` (text): unique patient identifier.
- `Study` (text): study name/code (must match `trial_schedules.Study`).
- `ScreeningDate` (date): date of first screening visit (Day 1 baseline).
- `RandomizationDate` (date): date of randomization (V1), null if not yet randomized.
- `Status` (text): patient journey status - one of: 'screening', 'screen_failed', 'dna_screening', 'randomized', 'withdrawn', 'deceased', 'completed', 'lost_to_followup'.
- `PatientPractice` (text): recruitment origin (where patient comes from).
- `SiteSeenAt` (text): visit location (where patient is seen).
- `Pathway` (text): study pathway variant (e.g., 'standard', 'with_run_in').

Notes:
- `PatientPractice` drives recruitment origin metrics.
- `SiteSeenAt` drives visit scheduling and activity locations.
- **Recruitment definition**: Patients are counted as recruited when `Status` IN ('randomized', 'withdrawn', 'deceased', 'completed', 'lost_to_followup').
- Patients with `Status` = 'screening' are in the screening pipeline but not yet recruited.
- Patients with `Status` = 'screen_failed' failed screening and are not counted as recruited.
- Patients with `Status` = 'dna_screening' did not attend screening appointment and are not counted as recruited.
- For backward compatibility, code supports old `StartDate` column (maps to `ScreeningDate`).

### trial_schedules
Defines the visit schedule and payments for each study.

Key columns:
- `Study` (text): study name/code.
- `Day` (int): visit day offset from screening; **Day 1 = screening visit (baseline)**.
- `VisitName` (text): visit identifier.
- `Pathway` (text): pathway variant (e.g., 'standard', 'with_run_in').
- `SiteforVisit` (text): contract holder for the study (ContractSite).
- `Payment` (numeric): per‑visit payment amount.
- `ToleranceBefore`, `ToleranceAfter` (int): day window around the expected visit.
- `VisitType` (text): `patient`, `siv`, `monitor`, etc.
- Optional: `IntervalUnit`, `IntervalValue` for month‑based schedules.
- Optional: `FPFV`, `LPFV`, `LPLV`, `StudyStatus`, `RecruitmentTarget`.

Notes:
- **Day 1 = screening visit** (the baseline for all calculations).
- **Day 0 = optional unplanned visits** (not used for predicted visits).
- All visit days should be positive (no negative day numbers).
- Standard pathway example: Day 1 (Screening), Day 7 (V1/Randomization), Day 14 (V2).
- Run-in pathway example: Day 1 (Screening), Day 10 (Run-in), Day 28 (V1/Randomization), Day 35 (V2).
- `SiteforVisit` is treated as the contract holder.
- Visit type `siv`/`monitor` are study‑level events.

### actual_visits
Actual or proposed visits recorded against patients/studies.

Key columns:
- `PatientID` (text)
- `Study` (text)
- `VisitName` (text)
- `ActualDate` (date)
- `VisitType` (text): `patient`, `siv`, `monitor`, `patient_proposed`, `event_proposed`
- `Notes` (text): use `ScreenFail`, `Withdrawn`, `Died`, `DNA` markers

Notes:
- Proposed visits use `VisitType` suffixes and/or future dates.
- VisitType may be auto‑corrected on load based on `VisitName`.

### study_site_details
Contract‑site study metadata (preferred source for Gantt/recruitment).

Key columns:
- `Study` (text)
- `ContractSite` (text): contract holder site.
- `StudyStatus` (text): `active`, `contracted`, `in_setup`, `expression_of_interest`, `eoi_didnt_get`
- `RecruitmentTarget` (int)
- `FPFV`, `LPFV`, `LPLV` (date)
- `EOIDate` (date)
- `Description`, `StudyURL`, `DocumentLinks`

Notes:
- Contract holder is the grouping key for Gantt and recruitment targets.

## Semantics Summary

- Contract holder: `ContractSite` (and `SiteforVisit` as legacy alias).
- Recruitment origin: `PatientPractice`.
- Visit location: `SiteSeenAt` (for scheduling) and `SiteofVisit` (for activity metrics).

