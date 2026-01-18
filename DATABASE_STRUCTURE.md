# Database Structure

This document describes the Supabase tables and the meaning of key columns.

## Tables

### patients
Tracks enrolled patients and their origin/visit location.

Key columns:
- `PatientID` (text): unique patient identifier.
- `Study` (text): study name/code (must match `trial_schedules.Study`).
- `StartDate` (date): enrollment/baseline date (Day 1).
- `PatientPractice` (text): recruitment origin (where patient comes from).
- `SiteSeenAt` (text): visit location (where patient is seen).

Notes:
- `PatientPractice` drives recruitment origin metrics.
- `SiteSeenAt` drives visit scheduling and activity locations.

### trial_schedules
Defines the visit schedule and payments for each study.

Key columns:
- `Study` (text): study name/code.
- `Day` (int): visit day offset; Day 1 is the baseline.
- `VisitName` (text): visit identifier.
- `SiteforVisit` (text): contract holder for the study (ContractSite).
- `Payment` (numeric): per‑visit payment amount.
- `ToleranceBefore`, `ToleranceAfter` (int): day window around the expected visit.
- `VisitType` (text): `patient`, `siv`, `monitor`, etc.
- Optional: `IntervalUnit`, `IntervalValue` for month‑based schedules.
- Optional: `FPFV`, `LPFV`, `LPLV`, `StudyStatus`, `RecruitmentTarget`.

Notes:
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

