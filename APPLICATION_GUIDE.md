# Clinical Trial Calendar Application - Complete Guide

## Table of Contents
1. [Overview](#overview)
2. [Key Features](#key-features)
3. [Database Structure](#database-structure)
4. [Visit Types](#visit-types)
5. [Getting Started](#getting-started)
6. [Core Functionality](#core-functionality)
7. [Financial Features](#financial-features)
8. [Data Management](#data-management)
9. [Export Capabilities](#export-capabilities)
10. [User Interface](#user-interface)

---

## Overview

The **Clinical Trial Calendar Application** is a comprehensive web-based system designed to manage, visualize, and analyze clinical trial visit schedules with integrated payment tracking and financial reporting. Built with Streamlit and powered by Supabase, it provides a centralized platform for tracking patient visits, study events, and financial metrics across multiple clinical trials.

### Primary Purpose
- **Schedule Management**: Generate and maintain visit calendars for multiple patients across multiple studies
- **Visit Tracking**: Record actual visits as they occur and compare against scheduled visits
- **Financial Analysis**: Track payments, calculate income realization, and generate financial reports
- **Site Management**: Organize visits by site (where work is performed) and track recruitment by origin site
- **Data Export**: Export calendars and financial data to Excel and CSV formats

---

## Key Features

### 1. **Interactive Calendar View**
- **Multi-study calendar** displaying all patient visits across all studies
- **Three-level column headers**:
  - Level 1: Visit site (where work is performed)
  - Level 2: Study_PatientID combination
  - Level 3: Origin site (where patient was recruited)
- **Color-coded visit status**:
  - ✅ Completed visits (actual visits recorded)
  - ⚠️ Out of protocol visits
  - 🔴 Screen failures
  - ⚠️ Withdrawn patients
  - ⚠️ Patient deaths
  - Plain text: Scheduled visits (not yet completed)
- **Date highlighting**:
  - Financial year end (31 March) - dark blue
  - Month end - light blue
  - Weekends - gray
- **Filtering options**: Filter by date range, study, or site

### 2. **Database Integration**
- **Supabase backend** for persistent data storage
- **Real-time synchronization** between database and application
- **Data validation** on upload and import
- **Automatic backup** and export capabilities
- **Selective table overwrite** (patients, trials, or visits independently)

### 3. **Visit Management**
- **Scheduled visits**: Automatically calculated from trial schedules and patient start dates
- **Actual visits**: Record visits as they occur with dates and notes
- **Study events**: Track Site Initiation Visits (SIVs) and Monitor visits
- **Day 0 visits**: Support for unscheduled, extra, and optional visits
- **Visit status tracking**: Screen failures, withdrawals, deaths, out-of-protocol visits

### 4. **Financial Tracking & Reporting**
- **Payment tracking**: Associate payment amounts with each visit type
- **Income realization analysis**: Compare completed vs. scheduled income
- **Monthly/Quarterly/Annual reports**: Financial breakdowns by time period
- **Site-based analysis**: Income and work distribution by site
- **Study-based analysis**: Financial metrics per study
- **Profit sharing calculations**: Work ratio analysis between sites

### 5. **Data Entry Modals**
- **Add Patient**: Enroll new patients with study assignment and start date
- **Record Visit**: Log actual patient visits with date and notes (future dates automatically marked as "Proposed")
- **Record Site Event**: Add SIVs and Monitor visits (future dates automatically marked as "Proposed")
- **Switch Patient Study**: Transfer patients between studies
- **Proposed Visits Confirmation**: Export proposed visits, mark as confirmed in Excel, import back to update status

### 6. **Export Capabilities**
- **Excel export**: Enhanced formatting with multiple sheets
  - Main calendar view
  - Patients data
  - Actual visits data
  - Financial reports (if enabled)
  - Data dictionary
- **CSV export**: Database backups for all three tables
- **Basic/Enhanced modes**: Choose to include or exclude financial columns

### 7. **Data Validation**
- **Startup validation**: Checks data integrity on application load
- **File upload validation**: Validates CSV/Excel files before import
- **Real-time error reporting**: Clear error messages with specific issues
- **Duplicate detection**: Prevents duplicate patient IDs and visits

---

## Database Structure

The application uses three main database tables, all using **PascalCase** column naming:

### 1. **patients** Table
Stores patient enrollment information.

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| PatientID | text | Yes | Unique patient identifier |
| Study | text | Yes | Study name/code (must exist in trial_schedules) |
| StartDate | date | Yes | Patient enrollment/baseline date (Day 1) |
| PatientPractice | text | Yes | Recruitment site (e.g., "Ashfields", "Kiltearn") |

**Key Constraints:**
- PatientID must be unique
- Study must exist in trial_schedules table
- PatientPractice cannot be empty or invalid placeholder

### 2. **trial_schedules** Table
Defines visit schedules for each study.

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| Study | text | Yes | Study name/code |
| Day | integer | Yes | Visit day number (Day 1 = baseline, can be negative for screening) |
| VisitName | text | Yes | Visit identifier (e.g., "V1", "Screening", "SIV") |
| SiteforVisit | text | Yes | Where the visit takes place |
| Payment | numeric(10,2) | No | Payment amount for this visit |
| ToleranceBefore | integer | No | Days before expected date allowed (default: 0) |
| ToleranceAfter | integer | No | Days after expected date allowed (default: 0) |
| IntervalUnit | text | No | "month" or "day" for interval calculation |
| IntervalValue | smallint | No | Number of interval units |
| VisitType | text | No | "patient", "siv", "monitor", or "extra" |

**Key Constraints:**
- Unique constraint on (Study, VisitName)
- Each study must have exactly one Day 1 visit
- SiteforVisit cannot be empty

**Scheduling Types:**
- **Day-based**: Uses Day number from baseline (default)
- **Month-based**: Uses IntervalUnit="month" and IntervalValue (e.g., every 3 months)

### 3. **actual_visits** Table
Records visits that have actually occurred.

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| PatientID | text | Yes | Patient identifier (or pseudo-ID for study events) |
| Study | text | Yes | Study name/code |
| VisitName | text | Yes | Visit identifier |
| ActualDate | date | Yes | Date visit actually occurred |
| Notes | text | No | Additional notes (can indicate screen failure, withdrawal, death) |
| VisitType | text | No | "patient", "siv", "monitor", "extra", "patient_proposed", or "event_proposed" |

**Key Constraints:**
- Unique constraint on (PatientID, Study, VisitName, ActualDate)
- PatientID should exist in patients table (unless study event)
- Future dates automatically set VisitType to `patient_proposed` or `event_proposed`

---

## Visit Types

The application supports four types of visits, identified by the **VisitType** column:

### 1. **Patient Visits** (`VisitType = "patient"`)
- **Default type** for all regular patient visits
- Scheduled visits calculated from trial schedules
- Actual visits recorded when they occur
- Examples: V1, V2, Screening, Randomisation, Follow-up visits

### 2. **Site Initiation Visits (SIV)** (`VisitType = "siv"`)
- **Study-level events**, not patient-specific
- Typically scheduled for Day 0
- Appears in the site column (where work is performed)
- PatientID format: `SIV_STUDY-NAME` or just the study name
- Examples: "SIV" visit for study setup

### 3. **Monitor Visits** (`VisitType = "monitor"`)
- **Study-level events** for monitoring/audit visits
- Not patient-specific
- Appears in the site column
- PatientID format: `MONITOR_STUDY-NAME` or study name
- Examples: "Monitor Visit 1", "Audit Visit"

### 4. **Extra Visits** (`VisitType = "extra"`)
- **Optional patient visits** that may or may not occur
- Typically Day 0 visits (unscheduled)
- Examples: "Unscheduled", "V1.1", "Extra Visit"

### Visit Status Indicators

Visits can have additional status indicators based on notes or timing:

- **✅ Completed**: Actual visit recorded and date matches or is close to scheduled date
- **⚠️ Out of Protocol**: Visit occurred outside tolerance window (if tolerance checking enabled)
- **🔴 Screen Failure**: Notes contain "ScreenFail"
- **⚠️ Withdrawn**: Notes contain "Withdrawn"
- **⚠️ Died**: Notes contain "Died"
- **📅 Proposed**: Future-dated visit/event (tentative booking) - marked with `patient_proposed` or `event_proposed` VisitType

---

## Getting Started

### Prerequisites
- Web browser (Chrome, Firefox, Safari, Edge)
- Admin access for data entry (password-protected)
- Database connection (Supabase) configured

### Initial Setup

1. **Database Connection**
   - Ensure Supabase connection is configured
   - Verify database tables exist with correct schema
   - Run column rename SQL if migrating from old schema

2. **Load Data**
   - Option A: Load from database (if data already exists)
   - Option B: Upload CSV files (patients, trials, optional visits)

3. **Generate Calendar**
   - Click "Generate Calendar" button
   - Calendar will display all scheduled visits

### First-Time Data Entry

1. **Add Trial Schedules**
   - Upload trials CSV or use database import
   - Ensure each study has Day 1 visit defined
   - Include payment amounts if financial tracking needed

2. **Add Patients**
   - Use "Add Patient" modal or upload CSV
   - Provide: PatientID, Study, StartDate, PatientPractice
   - System validates study exists and start date is valid

3. **Record Visits**
   - Use "Record Visit" modal as visits occur
   - Or upload actual visits CSV file
   - Add notes for special status (screen failure, withdrawal, etc.)

---

## Core Functionality

### Calendar Generation

The calendar is generated through a multi-step process:

1. **Data Preparation**
   - Load patients, trial schedules, and actual visits
   - Validate data integrity
   - Separate patient visits from study events

2. **Visit Calculation**
   - Calculate scheduled visit dates from patient start dates
   - Support day-based and month-based scheduling
   - Apply tolerance windows if configured

3. **Calendar Building**
   - Create date range covering all visits
   - Group patients by visit site
   - Create three-level column structure
   - Fill calendar with visit information

4. **Status Assignment**
   - Compare scheduled vs. actual visits
   - Assign status indicators
   - Highlight special dates (FY end, month end, weekends)

### Visit Scheduling Logic

**Day-Based Scheduling:**
- Day 1 = Patient StartDate (baseline)
- Day 7 = StartDate + 7 days
- Day 30 = StartDate + 30 days
- Negative days = Before baseline (screening visits)

**Month-Based Scheduling:**
- Day 1 = Patient StartDate (baseline)
- IntervalValue=1, IntervalUnit="month" = StartDate + 1 calendar month
- IntervalValue=3, IntervalUnit="month" = StartDate + 3 calendar months
- Uses calendar-aware date calculation (handles different month lengths)

### Site Organization

The application distinguishes between:

- **Visit Site** (SiteforVisit): Where the work/visit is performed
- **Origin Site** (PatientPractice): Where the patient was recruited

This allows tracking:
- Work distribution across sites
- Recruitment patterns
- Site-specific financial metrics

---

## Financial Features

### Payment Tracking

- Each visit type in trial_schedules can have an associated Payment amount
- Payments are tracked per visit, per patient, per study
- Supports currency formatting (£)

### Income Realization

**Completed Income**: Sum of payments for visits that have actually occurred
**Scheduled Income**: Sum of payments for all scheduled visits
**Pipeline Income**: Scheduled income minus completed income

**Realization Rate**: (Completed Income / Scheduled Income) × 100%

### Financial Reports

1. **Monthly Income Analysis**
   - Total income by month
   - Completed vs. scheduled breakdown
   - Realization rates

2. **Quarterly Profit Sharing**
   - Work ratios between sites
   - Income distribution
   - Quarterly comparisons

3. **Site Realization Analysis**
   - Income by site
   - Work distribution
   - Site-specific metrics

4. **Study Income Summary**
   - Financial metrics per study
   - Completed vs. scheduled
   - Study comparison

5. **Financial Year Analysis**
   - FY-to-date totals
   - Year-over-year comparisons
   - FY end highlighting (31 March)

---

## Data Management

### Adding Data

**Via Modals (Admin Only):**
- Add Patient: Enroll new patient
- Record Visit: Log actual visit (future dates automatically marked as "Proposed")
- Record Site Event: Add SIV or Monitor visit (future dates automatically marked as "Proposed")
- Switch Patient Study: Transfer patient between studies
- Proposed Visits Confirmation: Export proposed visits, mark as confirmed in Excel, import back

**Proposed Visits Confirmation Workflow:**
1. Secretary adds visit/event with future date → automatically marked as "Proposed" (📅 indicator)
2. Export proposed visits from sidebar → Excel file with Status column (defaults to "Proposed")
3. Secretary marks items as "Confirmed" in Excel Status column
4. Import confirmed Excel → updates VisitType from `patient_proposed`/`event_proposed` to `patient`/`siv`/`monitor`
5. Calendar refreshes showing confirmed visits with ✅ indicator

**Via File Upload:**
- Upload CSV/Excel files
- System validates before import
- Can overwrite entire tables or append

**Via Database:**
- Direct database access (Supabase)
- SQL import scripts
- CSV export/import cycle

### Data Validation

**Startup Validation:**
- Checks all three tables for data integrity
- Validates required columns
- Checks for missing studies
- Verifies site names

**Upload Validation:**
- Required columns present
- Data types correct
- No invalid site names
- Date formats valid
- No duplicate patient IDs

### Data Export

**CSV Export:**
- Export all three tables separately
- Includes all columns
- Ready for backup or re-import
- Column names match database exactly

**Excel Export:**
- Enhanced formatting
- Multiple sheets
- Financial reports included (optional)
- Data dictionary included

---

## Export Capabilities

### CSV Export
- **Patients**: PatientID, Study, StartDate, PatientPractice
- **Trials**: All trial schedule columns
- **Visits**: PatientID, Study, VisitName, ActualDate, Notes, VisitType

### Excel Export

**Basic Mode** (Financial columns excluded):
- Main calendar sheet
- Patients sheet
- Actual visits sheet
- Data dictionary

**Enhanced Mode** (Financial columns included):
- All basic sheets plus:
- Monthly income tables
- Quarterly profit sharing
- Site realization analysis
- Study income summary
- Pipeline analysis

**Excel Features:**
- Formatted headers
- Color-coded cells
- Currency formatting
- Date highlighting
- Multiple worksheets
- Data validation notes

---

## User Interface

### Main Components

1. **Sidebar**
   - Data source selection (Database vs. Files)
   - File upload options (Admin only)
   - Database table viewer
   - Activity log
   - Debug options

2. **Main Area**
   - Calendar display
   - Filter controls
   - Statistics panels
   - Financial reports
   - Download buttons

3. **Modals** (Admin only)
   - Patient entry form
   - Visit entry form
   - Study event form
   - Patient study switch form

### Navigation

- **Calendar View**: Main interactive calendar
- **Statistics**: Site and study statistics
- **Financial Reports**: Income and realization analysis
- **Data Management**: Add/edit data (Admin)
- **Export**: Download calendars and reports

### Access Levels

- **Public**: View calendar and reports
- **Admin**: Full access including data entry and exports
  - Password-protected login
  - Session-based authentication

---

## Technical Details

### Technology Stack
- **Frontend**: Streamlit (Python web framework)
- **Backend**: Supabase (PostgreSQL database)
- **Data Processing**: Pandas
- **Export**: openpyxl (Excel), CSV

### Data Flow
1. Load data from database or files
2. Validate and clean data
3. Process visits and calculate dates
4. Build calendar DataFrame
5. Generate financial metrics
6. Display in interactive interface
7. Export to Excel/CSV as needed

### Performance
- Caching for database queries (5-minute TTL)
- Caching for calendar generation
- Optimized pandas operations
- Efficient date calculations

---

## Best Practices

### Data Entry
1. **Always validate** before saving
2. **Use consistent naming** for studies and sites
3. **Record visits promptly** as they occur
4. **Add notes** for special circumstances
5. **Export backups** regularly

### Visit Scheduling
1. **Define Day 1 clearly** in trial schedules
2. **Use month-based scheduling** for monthly visits
3. **Set tolerance windows** appropriately
4. **Include payment amounts** for financial tracking

### Financial Tracking
1. **Keep payment amounts updated** in trial schedules
2. **Review realization rates** regularly
3. **Export financial reports** monthly/quarterly
4. **Verify site assignments** for accurate reporting

---

## Troubleshooting

### Common Issues

**Calendar not displaying:**
- Check data is loaded (patients and trials)
- Verify database connection
- Check for validation errors

**Visits not appearing:**
- Verify VisitType is correct
- Check SiteforVisit is set
- Ensure study exists in trial_schedules

**Financial reports empty:**
- Verify Payment column has values
- Check visit dates are valid
- Ensure financial columns enabled in export

**Import errors:**
- Check column names match exactly (PascalCase)
- Verify required columns present
- Check for duplicate keys
- Review validation error messages

---

## Support & Maintenance

### Database Maintenance
- Regular backups via CSV export
- Monitor database size
- Review validation reports
- Clean up inactive patients (optional)

### Application Updates
- Check for new features
- Review changelog
- Test exports after updates
- Verify data integrity

---

## Version Information

This documentation covers the current version with:
- PascalCase column naming convention
- Supabase database integration
- Enhanced Excel export
- Financial reporting features
- Study event support (SIVs, Monitors)
- Multi-site management

For specific version details or change history, refer to the application's version control system.

