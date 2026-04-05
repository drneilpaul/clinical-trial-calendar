# Trial Setup Guide — Schema Reference & AI Prompt

This document has two purposes:

1. **Schema Reference** — the exact database structure, column names, data types, allowed values, and validation rules for every table in the Clinical Trial Calendar app
2. **AI Prompt** — a ready-to-use prompt you can paste into Claude (or another AI) alongside a study protocol PDF and financial agreement, to generate accurate trial schedule entries

---

## Part 1: Schema Reference

### How the system works

The app manages clinical trial visit schedules. It predicts future visit dates for patients based on a trial schedule template, displays them on a calendar, and replaces predictions with actual dates as visits are completed.

**Four database tables:**

| Table | Purpose | When populated |
|-------|---------|----------------|
| `trial_schedules` | Defines the visit schedule template for each study | At study setup (from protocol) |
| `study_site_details` | Study-level metadata, dates, financials, regulatory refs | At study setup (from protocol + financial agreement) |
| `patients` | Tracks enrolled patients | When patients are screened |
| `actual_visits` | Records completed or proposed visits | As visits happen |

When setting up a new trial, you need to create entries for **trial_schedules** and **study_site_details**. The other two tables are populated later as patients enrol and visits occur.

---

### Table 1: trial_schedules

Each row defines one visit in a study's schedule. A study with 10 visits has 10 rows.

#### Columns

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| `Study` | text | YES | Study name/code. Case-sensitive. Must be identical across all tables. |
| `Day` | integer | YES | Visit day number relative to screening. Day 1 = screening (the anchor date). |
| `VisitName` | text | YES | Human-readable visit label. Must be unique within a Study+Pathway combination. |
| `SiteforVisit` | text | YES | The contract-holding site name (e.g. "Ashfields", "Kiltearn"). |
| `Payment` | numeric | no | Per-visit payment in GBP. Must be >= 0. Defaults to 0 if blank. |
| `ToleranceBefore` | integer | no | Days before the target date that the visit is still acceptable. Defaults to 0. |
| `ToleranceAfter` | integer | no | Days after the target date that the visit is still acceptable. Defaults to 0. |
| `IntervalUnit` | text | no | Either `month` or `day`. Leave blank for standard day-based scheduling. |
| `IntervalValue` | integer | no | Number of months/days when IntervalUnit is set. Only used when IntervalUnit is populated. |
| `VisitType` | text | no | One of: `patient`, `siv`, `monitor`, `extra`. Defaults to `patient`. |
| `Pathway` | text | no | Study pathway variant. Defaults to `standard`. See Pathway section below. |

#### Day numbering rules

- **Day 1 is always screening** — the first time the site sees the patient
- All subsequent visits are numbered relative to Day 1
- Day numbers must be positive integers (no negative days, no Day 0 for scheduled visits)
- **Day 0 is reserved** for optional/unscheduled visits (SIV, Monitor, extras) that only appear when actually recorded — they are never predicted on the calendar

#### How visit dates are calculated

```
predicted_date = patient_screening_date + (Day - 1) days
```

Example: If a patient screens on 1 July and a visit is Day 14:
```
predicted_date = 1 July + (14 - 1) = 1 July + 13 days = 14 July
```

For month-based intervals (when `IntervalUnit = month`):
```
predicted_date = patient_screening_date + IntervalValue calendar months
```

Example: IntervalUnit=month, IntervalValue=3, screening on 1 Jan:
```
predicted_date = 1 Jan + 3 months = 1 April
```

The Day column must still have a value even when using month-based intervals (it serves as a fallback and for sorting).

#### Converting protocol day numbering to system day numbering

Protocols often number their visits differently from this system. The protocol may call screening "Day -14" and randomisation "Day 1". You must convert to the system where **Day 1 = screening**.

**Example conversion:**

| Protocol name | Protocol day | System Day | Calculation |
|---------------|-------------|------------|-------------|
| Screening | Day -14 | 1 | Always 1 (anchor) |
| Randomisation | Day 1 | 15 | 1 + abs(-14) = 15 |
| Visit 2 | Day 29 | 43 | 15 + (29 - 1) = 43 |
| Visit 3 | Day 57 | 71 | 15 + (57 - 1) = 71 |

The formula: `system_day = screening_system_day + (protocol_day - protocol_randomisation_day) + (randomisation_system_day - 1)`

Or more simply: work out the gap in days between each visit and screening, then add 1.

#### Tolerance windows

Each visit can have a window of acceptable dates defined by `ToleranceBefore` and `ToleranceAfter`:

```
earliest_acceptable = predicted_date - ToleranceBefore days
latest_acceptable   = predicted_date + ToleranceAfter days
```

Example: Day 14 visit with ToleranceBefore=3, ToleranceAfter=7:
- Predicted: 14 July
- Earliest: 11 July (14 July - 3 days)
- Latest: 21 July (14 July + 7 days)

If a visit occurs outside this window, it is flagged as out of protocol.

Day 1 (screening) never has tolerance windows — it is the anchor and cannot be early or late.

#### VisitType values

| Value | Meaning | Appears on calendar as |
|-------|---------|----------------------|
| `patient` | Regular patient visit (default) | One predicted entry per enrolled patient |
| `extra` | Optional extra visit | Same as patient — only shown when actually recorded |
| `siv` | Site Initiation Visit | One entry per study, not per patient. Day should be 0. |
| `monitor` | Monitoring visit | One entry per study, not per patient. Day should be 0. |

SIV and Monitor visits are study-level events, not patient-level. They use pseudo-patient IDs like `SIV_BaxDuo` or `MONITOR_BaxDuo`.

#### Pathways

Some studies have variant schedules. For example, a study might have a "standard" pathway and a "with_run_in" pathway with extra visits before randomisation.

- Each pathway has its own complete set of visits in `trial_schedules`
- Patients are assigned a pathway when enrolled
- If a study has only one pathway, use `standard` (or leave blank — it defaults to `standard`)
- Pathway names are case-sensitive

#### Validation rules (enforced on upload)

1. Every Study (+Pathway combination) must have exactly one Day 1 visit
2. Day values must be integers >= 1 (except Day 0 for SIV/Monitor/extras)
3. SiteforVisit cannot be empty, null, or "Unknown Site"
4. Payment must be >= 0 (no negative values)
5. Duplicate Study+Day combinations trigger a warning
6. IntervalUnit only accepts `month` or `day` (anything else is ignored)

---

### Table 2: study_site_details

Each row holds metadata for one study at one site. A study running at two sites has two rows.

#### Columns

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| `Study` | text | YES | Study name/code. Must match trial_schedules exactly. |
| `ContractSite` | text | YES | Contract-holding site name. Same concept as SiteforVisit in trial_schedules. |
| `StudyStatus` | text | no | One of: `active`, `contracted`, `in_setup`, `expression_of_interest`. Defaults to `active`. |
| `RecruitmentTarget` | integer | no | Number of patients to recruit at this site. Must be >= 1 or blank. |
| `FPFV` | date | no | First Patient First Visit — date recruitment opens. Format: YYYY-MM-DD. |
| `LPFV` | date | no | Last Patient First Visit — date recruitment closes. |
| `LPLV` | date | no | Last Patient Last Visit — date the last patient completes their last visit. |
| `Description` | text | no | Brief study description. |
| `EOIDate` | date | no | Date the Expression of Interest was submitted. |
| `StudyURL` | text | no | URL to study registry or website. |
| `DocumentLinks` | text | no | Links to study documents (protocol, ICF, etc.). |
| `ProtocolNumber` | text | no | Protocol number / study code from the sponsor. |
| `IRASNumber` | text | no | IRAS application number (UK regulatory). |
| `ISRCTNNumber` | text | no | ISRCTN registry number. |
| `RECReference` | text | no | Research Ethics Committee reference. |
| `Sponsor` | text | no | Sponsoring company or institution. |
| `ChiefInvestigator` | text | no | Name of the Chief Investigator. |
| `StudyPopulation` | text | no | Target population description. |
| `SampleSize` | integer | no | Total study sample size (all sites globally). |
| `SetupFee` | numeric | no | One-off setup fee in GBP. |
| `PerPatientFee` | numeric | no | Per-patient fee in GBP (separate from per-visit payments). |
| `AnnualFee` | numeric | no | Annual site fee in GBP. |
| `FinancialNotes` | text | no | Free text notes about payment terms, invoicing, etc. |
| `AnchorVisitName` | text | no | The VisitName of the visit to use as the rebasing anchor. See below. |

#### AnchorVisitName (rebasing)

In some studies, screening and randomisation are separate visits, and all subsequent visits are defined in the protocol relative to randomisation — not screening. Since the screening-to-randomisation gap can vary, predictions would be wrong unless the system recalculates downstream visits from the actual randomisation date.

- If `AnchorVisitName` is blank or NULL: the system uses Day 1 (screening) as the anchor for all predictions. This is the default and correct for most studies.
- If `AnchorVisitName` is set to a VisitName (e.g. `"V1 / Randomisation"`): once that visit has an actual date recorded, all visits at or after that visit's Day value are recalculated relative to the actual date.

**Example:** AnchorVisitName = "Randomisation" (Day 7). Patient screens 1 July, randomisation predicted 7 July. Randomisation actually happens 4 July. V2 (Day 14) shifts from 14 July to 11 July (4 July + 7 days).

Set this for any study where there is a variable gap between screening and randomisation, and the protocol defines subsequent visits relative to randomisation.

---

### Table 3: patients

Each row is one patient enrolled in one study.

#### Columns

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| `PatientID` | text | YES | Unique patient identifier within a study. |
| `Study` | text | YES | Study name. Must match trial_schedules. |
| `ScreeningDate` | date | YES | Date of the screening visit. This is Day 1 — the anchor for all visit predictions. |
| `PatientPractice` | text | YES | Recruitment origin — which practice recruited this patient. |
| `SiteSeenAt` | text | YES | Visit location — where the patient is seen for visits. Defaults to PatientPractice. |
| `Pathway` | text | no | Study pathway variant. Defaults to `standard`. Must match a Pathway in trial_schedules. |
| `RandomizationDate` | date | no | Date randomised. Auto-set when a V1 actual visit is recorded. |
| `Status` | text | no | Patient status. Defaults to `screening`. |
| `notes` | text | no | Free-text notes about the patient. |

#### Patient Status values

| Status | Counts as recruited? | Active? |
|--------|---------------------|---------|
| `screening` | No | Yes |
| `screen_failed` | No | No |
| `dna_screening` | No | No |
| `randomized` | Yes | Yes |
| `withdrawn` | Yes | No |
| `deceased` | Yes | No |
| `completed` | Yes | No |
| `lost_to_followup` | Yes | No |

Only "recruited" statuses count toward recruitment targets.

#### PatientPractice vs SiteSeenAt

- **PatientPractice** = "Where were they recruited from?" — drives recruitment metrics
- **SiteSeenAt** = "Where do they go for visits?" — drives visit scheduling
- These can be different (e.g. patient recruited from Kiltearn but seen at Ashfields)

---

### Table 4: actual_visits

Each row is one recorded visit (completed or proposed).

#### Columns

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| `PatientID` | text | YES | Patient identifier. Must exist in patients table (or be a pseudo-patient like `SIV_StudyName`). |
| `Study` | text | YES | Study name. Must match trial_schedules. |
| `VisitName` | text | YES | Visit name. Should match a VisitName in trial_schedules. |
| `ActualDate` | date | YES | Date the visit occurred (or is proposed for). |
| `Notes` | text | no | Free text. Special markers trigger status updates (see below). |
| `VisitType` | text | no | Auto-detected from VisitName if not provided. Values: `patient`, `siv`, `monitor`, `patient_proposed`, `event_proposed`. |

#### Special Notes markers

| Marker in Notes | Effect |
|-----------------|--------|
| `ScreenFail` | Sets patient Status to `screen_failed`, suppresses all future predicted visits |
| `Withdrawn` | Sets patient Status to `withdrawn`, suppresses all future predicted visits |
| `Died` | Sets patient Status to `deceased`, suppresses all future predicted visits |
| `DNA` | Informational only (Did Not Attend) |

#### Actual vs Proposed

- If ActualDate is today or in the past: visit is treated as **completed**
- If ActualDate is in the future: visit is treated as **proposed** (a tentative booking)

---

## Part 2: Worked Example

Here is a complete example for a fictional study called "EXAMPLE-01".

### Protocol summary

- Screening at Day -7 (protocol numbering)
- Randomisation at Day 1 (protocol numbering)
- V2 at Day 29, V3 at Day 57, V4 at Day 85
- Tolerance: +/- 3 days for randomisation, +/- 7 days for V2-V4
- Contract site: Ashfields
- Recruitment target: 25 patients
- Sponsor: Pharma Corp Ltd

### Converting protocol days to system days

| Protocol visit | Protocol day | Days after screening | System Day |
|----------------|-------------|---------------------|------------|
| Screening | -7 | 0 | 1 |
| Randomisation | 1 | 8 | 9 |
| V2 | 29 | 36 | 37 |
| V3 | 57 | 64 | 65 |
| V4 | 85 | 92 | 93 |

Calculation: days_after_screening = protocol_day - (-7) = protocol_day + 7. System Day = days_after_screening + 1.

### trial_schedules output (pipe-delimited)

```
Study|Day|VisitName|SiteforVisit|Payment|ToleranceBefore|ToleranceAfter|IntervalUnit|IntervalValue|VisitType|Pathway
EXAMPLE-01|1|Screening|Ashfields|150.00|0|0|||patient|standard
EXAMPLE-01|9|Randomisation|Ashfields|200.00|3|3|||patient|standard
EXAMPLE-01|37|V2|Ashfields|175.00|7|7|||patient|standard
EXAMPLE-01|65|V3|Ashfields|175.00|7|7|||patient|standard
EXAMPLE-01|93|V4|Ashfields|175.00|7|7|||patient|standard
EXAMPLE-01|0|SIV|Ashfields|500.00|0|0|||siv|standard
```

### study_site_details output (pipe-delimited)

```
Study|ContractSite|StudyStatus|RecruitmentTarget|FPFV|LPFV|LPLV|Description|ProtocolNumber|Sponsor|AnchorVisitName
EXAMPLE-01|Ashfields|active|25|2025-06-01|2026-12-31|2027-06-30|Phase 3 randomised controlled trial|EX-2025-001|Pharma Corp Ltd|Randomisation
```

Note: `AnchorVisitName` is set to `Randomisation` because the protocol defines V2-V4 relative to randomisation, not screening. This means when a patient's actual randomisation date is recorded, all downstream predictions shift to match.

---

## Part 3: AI Prompt

Copy everything below the line and paste it into a new conversation with Claude (or another AI), along with the study protocol PDF and financial agreement.

---

### PROMPT START

You are a clinical trial data entry assistant. Your job is to read a study protocol and financial agreement and produce accurate database entries for a clinical trial calendar application.

**YOUR CRITICAL RULES:**

1. **ONLY extract information that is explicitly stated in the provided documents.** Do not infer, assume, or invent any data.
2. **For every value you output, you must be able to point to where in the document it comes from.** If you cannot find a value, leave the field blank.
3. **Never guess visit names, day numbers, payment amounts, tolerance windows, or any other values.** If the protocol is ambiguous, flag it and ask.
4. **After your output, provide a source table** showing where each value came from (document name, section/page).
5. **After your source table, provide a checklist of items the human must verify** before uploading.

**STUDY NAME:**
[INSERT THE STUDY NAME YOU WANT TO USE IN THE APP — this must be consistent across all tables]

**CONTRACT SITE:**
[INSERT THE SITE NAME — e.g. "Ashfields" or "Kiltearn"]

**WHAT TO PRODUCE:**

Generate two pipe-delimited CSV outputs:

#### Output 1: trial_schedules

One row per visit in the study schedule. Columns (in this exact order):

```
Study|Day|VisitName|SiteforVisit|Payment|ToleranceBefore|ToleranceAfter|IntervalUnit|IntervalValue|VisitType|Pathway
```

**Column rules:**

- `Study`: Use the study name provided above. Identical for every row.
- `Day`: Integer. Day 1 = screening (the first time the site sees the patient). Convert from protocol numbering — see conversion rules below.
- `VisitName`: Use the visit name from the protocol (e.g. "Screening", "V1 / Randomisation", "V2 / D29 / W4"). Keep it recognisable.
- `SiteforVisit`: Use the contract site name provided above. Identical for every row.
- `Payment`: Per-visit payment in GBP from the financial agreement. If not specified for a visit, leave blank.
- `ToleranceBefore`: Days before target date. From the protocol's visit window. If not specified, use 0.
- `ToleranceAfter`: Days after target date. From the protocol's visit window. If not specified, use 0.
- `IntervalUnit`: Use `month` if the protocol defines this visit in months (e.g. "Month 6 visit"). Otherwise leave blank.
- `IntervalValue`: The number of months if IntervalUnit is `month`. Otherwise leave blank.
- `VisitType`: Use `patient` for all regular visits. Use `siv` for Site Initiation Visit (Day 0). Use `monitor` for monitoring visits (Day 0).
- `Pathway`: Use `standard` unless the protocol has multiple visit schedule variants (e.g. a run-in arm). If there are variants, create separate rows for each pathway with different pathway names.

**Day numbering conversion:**

The system uses Day 1 = screening. Protocols often use different conventions. Convert as follows:

1. Identify the screening visit in the protocol. This becomes Day 1 in the system.
2. For every other visit, count the number of days between it and screening, then add 1.
3. If the protocol says "Day -14 = Screening, Day 1 = Randomisation, Day 29 = Visit 2":
   - Screening: Day 1 (always)
   - Randomisation: 14 days after screening + 1 = Day 15
   - Visit 2: Randomisation is Day 15, plus (29-1) = Day 43
4. Show your working in the source table.

**Important:** Also add a row for SIV with Day=0, VisitType=siv if the financial agreement includes an SIV payment. Add a Monitor row with Day=0, VisitType=monitor if monitoring visit payments are listed.

#### Output 2: study_site_details

One row per site. Columns (in this exact order):

```
Study|ContractSite|StudyStatus|RecruitmentTarget|FPFV|LPFV|LPLV|Description|EOIDate|StudyURL|DocumentLinks|ProtocolNumber|IRASNumber|ISRCTNNumber|RECReference|Sponsor|ChiefInvestigator|StudyPopulation|SampleSize|SetupFee|PerPatientFee|AnnualFee|FinancialNotes|AnchorVisitName
```

**Column rules:**

- `Study`: Same study name as trial_schedules.
- `ContractSite`: Same as SiteforVisit.
- `StudyStatus`: Use `contracted` if the study hasn't started recruiting yet. Use `active` if it has.
- `RecruitmentTarget`: Site-level recruitment target from the financial agreement. Leave blank if not found.
- `FPFV`, `LPFV`, `LPLV`: Dates in YYYY-MM-DD format. From the protocol or agreement. Leave blank if not found.
- `Description`: One-line study description from the protocol synopsis.
- `ProtocolNumber`: The sponsor's protocol number.
- `Sponsor`: Sponsor name.
- `ChiefInvestigator`: CI name if in the protocol.
- `StudyPopulation`: Target population from inclusion criteria.
- `SampleSize`: Global sample size target (all sites). Leave blank if not found.
- `SetupFee`, `PerPatientFee`, `AnnualFee`: From the financial agreement. In GBP. Leave blank if not found.
- `FinancialNotes`: Any relevant payment terms (e.g. "Invoiced quarterly", "Per-patient fee paid on completion").
- `AnchorVisitName`: Set this to the VisitName of the randomisation visit IF the protocol defines subsequent visits relative to randomisation (not screening). If all visits are defined relative to screening, leave blank.
- All other columns: Fill from documents if available, otherwise leave blank.

#### Output 3: Source table

After your CSV outputs, provide a table showing the source for each value:

```
| Field | Value | Source |
|-------|-------|--------|
| Day for V2 | 37 | Protocol Section 5.1, Table 2: "Visit 2 at Day 29" → 29 + 8 days offset from screening = Day 37 |
| Payment for Screening | 150.00 | Financial Agreement, Appendix A, Visit Payment Schedule |
| ToleranceBefore for V2 | 7 | Protocol Section 5.1: "Visit window: +/- 7 days" |
| ... | ... | ... |
```

#### Output 4: Verification checklist

List anything the human must check before uploading:

- [ ] Confirm the study name matches what's used in the app
- [ ] Confirm the contract site name matches exactly (case-sensitive)
- [ ] Verify Day numbering conversion is correct (show your arithmetic)
- [ ] Verify payment amounts match the financial agreement (list any visits where payment was unclear)
- [ ] List any visits where tolerance windows were not specified in the protocol
- [ ] Flag if the protocol has multiple arms/pathways that need separate visit schedules
- [ ] Flag any visits defined in months rather than days
- [ ] Confirm whether AnchorVisitName should be set (are visits defined relative to screening or randomisation?)
- [ ] List any values you left blank because you could not find them in the documents

**IMPORTANT REMINDERS:**

- Do NOT make up visit names that aren't in the protocol
- Do NOT invent payment amounts — if the financial agreement doesn't list a payment for a specific visit, leave it blank and flag it
- Do NOT guess tolerance windows — if the protocol doesn't specify a visit window, use 0 and flag it
- If the protocol is unclear about anything, say "UNCLEAR:" and explain what you need the human to clarify
- The pipe-delimited output must have NO spaces around the pipe characters
- Dates must be in YYYY-MM-DD format
- Payment amounts are in GBP with up to 2 decimal places (e.g. 150.00)

### PROMPT END

---

## Appendix: Quick reference for existing site names

When filling in SiteforVisit / ContractSite, use these exact names (case-sensitive):

- `Ashfields` — Ashfields Medical Practice
- `Kiltearn` — Kiltearn Medical Practice

If the study is at a different site, use the exact name as it appears in the contract.
