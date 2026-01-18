# Troubleshooting

## App fails to start

- **IndentationError**: check recent edits in `database.py` or `patient_processor.py`.
- **ModuleNotFoundError**:
  - `activity_report` → verify `activity_report.py` exists.
  - other missing files → check import paths in `app.py` and `display_components.py`.

## Recruitment table Arrow conversion errors

Symptoms: pyarrow conversion errors in Streamlit logs.

Fix:
- Ensure table columns have consistent types.
- In `recruitment_tracking.py`, `Target` is rendered as a string to avoid mixed numeric/text values.

## Gantt chart errors

Symptoms: `KeyError: ContractedSite` or missing contract site.

Fix:
- `study_site_details` must have `ContractSite`.
- `database.py` normalizes `ContractSite`, `ContractedSite`, and legacy `SiteforVisit`.

## Calendar filter shows all when nothing selected

Expected behavior: empty selection shows nothing.

Fix:
- Check `app.py` filter logic:
  - empty `active_site_filter` or `active_study_filter` should remain empty.
  - no fallback to “show all”.

## Scroll/sticky headers not working

Fixes:
- Ensure iframe uses `scrolling=False` in `components.html`.
- Ensure `.calendar-container` has fixed height and `overflow` enabled.
- Safari needs `-webkit-sticky` and JS fallback in `display_components.py`.

## Data mismatches

Common causes:
- Patient `Study` not found in `trial_schedules`.
- Multiple Day 1 visits in a study.
- Invalid `PatientPractice` or missing `SiteSeenAt`.

Run:
- `database_validator.run_startup_validation(...)` (triggered from `app.py` on load).

