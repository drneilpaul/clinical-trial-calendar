# Gantt Chart (Study Timeline) Documentation

## Purpose and Scope
The Gantt chart view visualizes study timelines by contract site. Each row represents a study-site pairing and shows the active timeline from the first patient first visit (FPFV) to the last patient last visit (LPLV), plus optional markers for recruitment and SIV events. This is used for high-level planning and recruitment tracking.

## Data Inputs
The Gantt chart is built in `gantt_view.py` using:
- `patients_df` — patient start dates (used for FPFV when no override is set)
- `visits_df` — visit dates (used for LPLV when no override is set)
- `trials_df` — trial schedule fallback for overrides (FPFV/LPFV/LPLV, StudyStatus)
- `actual_visits_df` — actual visit records (used for SIV markers)
- `study_site_details` — preferred source for overrides and study status

## Study/Site Combinations
Study-site pairs are assembled from two sources:
1) `trial_schedules` (via `trials_df`) — uses `SiteforVisit`
2) `study_site_details` — uses `ContractSite` as canonical, with fallbacks:
   - `ContractSite` (preferred)
   - `ContractedSite` (legacy)
   - `SiteforVisit` (legacy fallback)

This ensures EOI studies that do not have a full trial schedule are still included.

## Date Derivation Rules
Dates are resolved in `calculate_study_dates()`:
- **FPFV (start_date)**:
  - Prefer override from `study_site_details` (`FPFV`)
  - Fallback to earliest patient `StartDate`
- **LPFV (last_enrollment / lpfv_date)**:
  - **Only** from override (`LPFV`)
  - Never calculated from patient dates
- **LPLV (end_date)**:
  - Prefer override from `study_site_details` (`LPLV`)
  - Fallback to latest visit `Date` from `visits_df`

**Follow‑up detection**:
- If `LPFV < today` and `LPLV` is not passed, status becomes `in_followup`.

## Filtering and Ordering
The displayed dataset is filtered and ordered before rendering:
- **Filter**: Only studies with activity in the current FY are shown, plus:
  - `expression_of_interest`
  - `contracted`
  - `in_setup`
- **Ordering**:
  - Non‑EOI studies first, grouped by `Site`, then by `StartDate`
  - EOI studies grouped at the bottom

## Rendering (Plotly Timeline)
The Gantt view is rendered in `display_gantt_chart()` using Plotly:
- Each bar is labeled as: `Site - Study`
- Bars span `StartDate` → `EndDate`
- Status colors are applied via `get_status_color()`
- Optional overlays:
  - Recruitment markers (sequential patient recruitment dates)
  - SIV markers from `actual_visits_df` (earliest SIV date)

## Status Colors
Defined in `get_status_color()`:
```
status_colors = {
  'active': '#2ecc71',
  'contracted': '#3498db',
  'in_setup': '#f39c12',
  'expression_of_interest': '#95a5a6',
  'eoi_didnt_get': '#e74c3c',
  'in_followup': '#9b59b6'
}
```

## Notes
- The Gantt chart groups by **contract holder**, not visit location.
- Recruitment markers are numbered in the order of patient `StartDate` for each study.
- EOI studies may appear without dates, but are still shown by status.
