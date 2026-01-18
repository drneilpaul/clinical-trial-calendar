# App Architecture

High‑level module map and data flow for the Clinical Trial Calendar app.

## Entry Point
- `app.py` is the main Streamlit UI and orchestrator.

## Core Data Flow

1. **Data source**
   - `database.py` loads data from Supabase tables.
   - `file_validation.py` validates uploaded CSV/Excel files.

2. **Calendar building**
   - `processing_calendar.py` coordinates validation and processing.
   - `patient_processor.py` and `visit_processor.py` build visit records.
   - `calendar_builder.py` builds the calendar DataFrame.

3. **Views**
   - `display_components.py` renders calendar views, exports, and UI components.
   - `gantt_view.py` builds and displays Gantt charts.
   - `recruitment_tracking.py` builds recruitment data and dashboards.

4. **Analytics**
   - `calculations.py` provides financial/ratio calculations.
   - `data_analysis.py` provides site‑wise and summary analysis.

5. **Supporting**
   - `helpers.py` provides shared utilities, logging, and date helpers.
   - `formatters.py` formats values and styles for outputs.
   - `payment_handler.py` normalizes and validates payment columns.
   - `table_builders.py` creates enhanced Excel exports.
   - `database_validator.py` runs DB integrity checks.
   - `activity_report.py` builds the activity summary export.
   - `profiling.py` provides timing decorators.

## Module Responsibilities (by file)

- `app.py`: main UI, filters, view routing.
- `database.py`: Supabase CRUD and caching for all tables.
- `file_validation.py`: upload validation and cleaning.
- `processing_calendar.py`: calendar orchestration and validation gates.
- `patient_processor.py`: per‑patient schedule + actual visit merging.
- `visit_processor.py`: study events + tolerance handling.
- `calendar_builder.py`: calendar DataFrame + site busy view.
- `display_components.py`: rendering, export buttons, HTML calendar.
- `gantt_view.py`: Gantt build/display.
- `recruitment_tracking.py`: recruitment data + chart.
- `calculations.py`: financial metrics + ratios.
- `data_analysis.py`: site‑wise stats and summaries.
- `table_builders.py`: enhanced Excel export.
- `activity_report.py`: activity summary workbook.
- `helpers.py`: shared utilities/logging.
- `formatters.py`: formatting helpers.
- `payment_handler.py`: payment column normalization/validation.
- `database_validator.py`: DB consistency checks.
- `profiling.py`: timing helpers.
- `config.py`: session state defaults and UI config.

