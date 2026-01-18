# Changelog

All notable changes to this project are documented here.

## [Unreleased]

### Added
- `SiteSeenAt` handling for patient visit location in validation, processing, and exports.
- `ContractSite` support for contract-holder attribution and Gantt/recruitment logic.
- Admin download reports: activity summary and overdue/proposed visit workflows.
- New documentation: database structure, architecture, UI scrolling notes, troubleshooting, runbook.
- Calendar debug toggle in admin UI.
- `bulk_visits.py` module for overdue/proposed visit export/import.

### Changed
- App version updated to `v1.2`.
- Calendar filters now show nothing when no sites/studies are selected.
- Financial rollups group income by `ContractSite` where available.
- Calendar build performance improved with cached lookups and fewer per-cell checks.

### Fixed
- Gantt chart KeyError by normalizing contract site column names.
- Syntax errors from unexpected indentation in `database.py` and `patient_processor.py`.
- Recruitment target table Arrow conversion by coercing Target to string.
- Payment conversion during DB saves now safe against non-numeric values.
- Monthly realization sums now coerce non-numeric Payment values.
- Calendar debug loop gated to avoid overhead in normal runs.

### Removed
- 

