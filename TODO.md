# TODO

## Phase 1 — Cleanup & Reorganisation

- [x] **Remove "Switch Patient Study" button and functionality** — Removed button, modal, handler, and database function.

- [x] **Move "Restore from CSV Backup" into Database Operations expander** — Now under "Database Operations & Debug" in the sidebar.

- [x] **Move "Proposed Visits Confirmation" from sidebar to Import/Export page** — Now a section on the Import/Export page with a count of pending proposed visits in the header.

- [x] **Move Study Settings modal to DB Admin page** — Button moved from top action bar to DB Admin page. Top bar now has 3 buttons (Add Patient, Record Visit, Record Event).

## Phase 2 — Auth: Two-Level Login

- [ ] **Implement User vs Superuser login** — Three access levels:
  - **Public (not logged in):** View anonymised calendars only (current behaviour)
  - **User:** Can record visits, add proposed visits, use Import/Export, view Financials, run the secretary confirmation wizard
  - **Superuser:** Everything User can do, plus DB Admin, Study Settings, Database Operations, Restore from backup

## Phase 3 — Proposed Visits Modal

- [ ] **Create "Add Proposed Visit" modal** — Separate from "Record Patient Visit". Simpler workflow focused on booking future appointments:
  - Select Patient, Visit, Date (must be future), optional Extras (e.g. reconsent)
  - No withdrawn/died flags, no DNA — those don't apply to proposed visits
  - Always saves as `patient_proposed`
  - Concept: staff look at predicted visit windows → book a slot with the patient → record it as proposed

## Phase 4 — Unified Confirmation Workflow

- [ ] **Merge overdue predicted + proposed confirmation into one view** — Both are "visits needing attention". The combined list is: (a) predicted visits that are past due with no date entered, and (b) proposed visits that were booked but need confirming whether they happened. Frame this as "Visits Awaiting Confirmation".

- [ ] **Build secretary confirmation wizard modal** — A single-item-at-a-time wizard for working through outstanding visits:
  - Shows one visit at a time (patient, study, visit name, expected/proposed date)
  - Secretary confirms: Happened as planned / Happened on different date / DNA / Rescheduled / Cancelled
  - Forward/back buttons to navigate between items
  - Each confirmation saves immediately
  - Accessible to User-level login (not just superuser)

- [ ] **Consider Excel export as alternative** — Keep the export/import Excel workflow as a fallback for bulk operations, but the wizard becomes the primary day-to-day tool.

## Standalone Items

- [ ] **Import/Export page: lazy-load Excel exports** — All Excel files generated eagerly on page load (~3-6s). Switch to generate-on-demand pattern.

- [ ] **V-EOT ZEUS visits: fix data + investigate cause** — Rows in actual_visits have VisitType='patient' instead of 'patient_proposed'. Fix the data in Supabase. Investigate how they were entered to prevent recurrence.

- [ ] **Add visit logic help text to the app** — Draft in VISIT_LOGIC_DRAFT.md. Review, finalise, add as collapsible section or help page.
