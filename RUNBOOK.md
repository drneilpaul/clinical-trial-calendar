# Runbook

Operational notes for running and maintaining the app.

## Local Run
1. Create a venv and install `requirements.txt`.
2. Run: `streamlit run app.py`.
3. Provide Supabase secrets in `.streamlit/secrets.toml`.

## Database Connection
- Tables: `patients`, `trial_schedules`, `actual_visits`, `study_site_details`.
- `database.py` uses Supabase client and caches fetches.
- Use “Load from Database” in the sidebar to switch to DB data.

## Cache / Refresh
- `clear_build_calendar_cache()` clears calendar computations.
- `clear_database_cache()` clears Supabase fetch caches.
- `trigger_data_refresh()` toggles a session flag for reload.

## Deploy
1. Commit changes.
2. Deploy to Streamlit Cloud (or existing hosting).
3. Verify that `secrets.toml` is configured and DB tables exist.

## Schema Changes
If you add a new column:
1. Update DB schema (Supabase).
2. Update `database.py` export/import handling.
3. Update `file_validation.py` if file uploads need it.
4. Update docs in `DATABASE_STRUCTURE.md`.

## Data Recovery
- Use download exports from “Download Options”.
- Use `create_backup_zip()` in `database.py` for full table CSV backups.

