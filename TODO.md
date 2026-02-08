# TODO

## Performance
- [ ] **Import/Export page: lazy-load Excel exports** — Currently all Excel files (Calendar Only, Active Calendar, Calendar+Financials, Activity Summary, Overdue Predicted) are generated eagerly on page load (~3-6s). Switch to a two-step pattern: "Generate" button → spinner → download button appears. Only build each export when requested.

## Bug Fixes
- [ ] **V-EOT ZEUS visits showing as completed instead of proposed** — Rows in actual_visits have VisitType='patient' instead of 'patient_proposed'. Need to either: (a) fix the data in Supabase, or (b) investigate how they were originally entered to prevent recurrence.

## Documentation
- [ ] **Add visit logic help text to the app** — Draft written in VISIT_LOGIC_DRAFT.md. Review, finalise, then add to the app (collapsible section or help page).
