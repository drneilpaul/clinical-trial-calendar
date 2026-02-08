# How Visit Scheduling Works

## Visit Schedules
Visit schedules are defined per study in the **trial_schedules** database table. Each visit has a **Day number** relative to the patient's screening date (Day 1). For example, if screening is Day 1, a visit at Day 28 means 27 days after screening.

Some studies have **pathways** (e.g. "standard" vs "with_run_in"). Patients are assigned a pathway at enrollment, and only see visits from their pathway's schedule.

## How Visit Dates Are Calculated
All future visit dates are predicted from the patient's **Screening Date** (Day 1 baseline):

```
Expected date = Screening Date + (Visit Day - 1) days
```

Some visits use **month-based intervals** instead (e.g. "3 months") for longer-term scheduling.

## Tolerance Windows
Each visit can have a **tolerance window** defined in the schedule (e.g. -5 / +7 days). This means the visit is acceptable anywhere within that range around the expected date. These appear as +/- numbers alongside predicted visits on the calendar.

## Day 0 Visits (Extras)
Visits at **Day 0** (e.g. Unscheduled, V1.1, Extra Visit) are optional and do **not** appear as predicted visits on the calendar. They only appear once they are actually recorded. These are selected as "Extras" when recording a visit.

## Visit States on the Calendar

| Display | Meaning |
|---------|---------|
| ✅ Green | **Completed** — actual visit recorded, date has passed |
| ❌ Red | **Did Not Attend (DNA)** — actual visit recorded with "DNA" in notes |
| 📋 Grey | **Predicted** — no actual visit recorded yet; future dates show tolerance windows |
| 📋 Grey + ? | **Not Input Yet** — predicted visit date has passed but no actual visit recorded |
| 📅 Yellow | **Proposed** — a specific date has been booked but not yet confirmed as completed |

## Recording a Visit
Use the **"Record Patient Visit"** button. Select the patient, visit, and date:

- If the date is **today or in the past** → saved as an actual completed visit
- If the date is **in the future** → automatically saved as a **Proposed** visit

You can also record **extras** (Day 0 activities) performed at the same visit, and flag if a patient has **withdrawn** or **died** (which stops all future predicted visits).

## Proposed Visits
Proposed visits are tentative bookings for future dates. They are useful when you know a specific visit date in advance rather than relying on the predicted date from the schedule.

**To create:** Record a visit with a future date — it's automatically marked as proposed.

**To confirm:** Use the **"Proposed Visits Confirmation"** section in the sidebar (admin only):
1. Export proposed visits to Excel
2. Update the Status column to "Confirmed" for visits that have happened
3. Upload the file back — confirmed visits are converted to actual completed visits

**Important:** Once a proposed visit's date passes, it stays as proposed (yellow) until you confirm it. It does **not** automatically become a completed visit.

## Study Events (SIV / Monitor)
Site Initiation Visits and Monitoring Visits are **site-wide events**, not patient-specific. Record these via the **"Record Site Event"** button. They appear in a separate Events column on the calendar, not in patient columns.

## Patient Statuses That Affect Visits
- **Screen Failed / Withdrawn / Died** — all future predicted visits are suppressed after the stoppage date
- These are detected from visit Notes (e.g. "ScreenFail", "Withdrawn", "Died")

## Income
Visit payments are defined in the trial schedule. Only **confirmed actual visits** count towards income — proposed visits are excluded until confirmed.
