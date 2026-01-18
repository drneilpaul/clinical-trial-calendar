# Clinical Trial Calendar Generator

Streamlit app that generates visit calendars, recruitment tracking, and financial summaries for clinical trials.

## Quick Start
1. Load from database or upload Patients + Trials files (Actual Visits optional).
2. Apply filters if needed (sites/studies/date range).
3. Use calendar, site busy, or Gantt views.
4. Export calendar or reports from Download Options.

## Data Model (high level)
- `PatientPractice`: recruitment origin (where patient comes from).
- `SiteSeenAt`: visit location (where patient is seen).
- `ContractSite`: contract holder used for Gantt/recruitment/targets and income attribution.
- `SiteofVisit`: visit location used for activity metrics.

## Docs
- `DATABASE_STRUCTURE.md` — tables, fields, and semantics.
- `APP_ARCHITECTURE.md` — module map and data flow.
- `UI_SCROLLING_NOTES.md` — sticky header/scroll implementation details.
- `TROUBLESHOOTING.md` — common issues and fixes.
- `RUNBOOK.md` — operational steps and deployment notes.

Built with Streamlit.
