# Definitive Column Naming Convention

## Standard: PascalCase for All Database Columns and CSV Files

All columns use **PascalCase** naming consistently across:
- Database tables (Supabase)
- CSV export/import files
- Python code (DataFrame column names)

---

## 1. PATIENTS TABLE

### Column Names:
- **PatientID** (text, NOT NULL) - Unique patient identifier
- **Study** (text, NOT NULL) - Study name/code
- **StartDate** (date, NOT NULL) - Patient enrollment/baseline date
- **PatientPractice** (text, NOT NULL) - Recruitment site (e.g., "Ashfields", "Kiltearn")

### CSV Format:
```csv
PatientID,Study,StartDate,PatientPractice
P001,STUDY-2024-001,15/03/2024,Ashfields
```

---

## 2. TRIAL_SCHEDULES TABLE

### Column Names:
- **Study** (text, NOT NULL) - Study name/code
- **Day** (integer, NOT NULL) - Visit day number (Day 1 = baseline)
- **VisitName** (text, NOT NULL) - Visit identifier (e.g., "V1", "Screening", "SIV")
- **SiteforVisit** (text, NULL) - Where visit takes place
- **Payment** (numeric(10,2), NULL) - Payment amount
- **ToleranceBefore** (integer, NULL, default 0) - Days before expected date allowed
- **ToleranceAfter** (integer, NULL, default 0) - Days after expected date allowed
- **IntervalUnit** (text, NULL) - "month" or "day" for interval calculation
- **IntervalValue** (smallint, NULL) - Number of interval units
- **VisitType** (text, NULL) - "patient", "siv", "monitor", or "extra"

### CSV Format:
```csv
Study,Day,VisitName,SiteforVisit,Payment,ToleranceBefore,ToleranceAfter,IntervalUnit,IntervalValue,VisitType
STUDY-2024-001,1,V1,Ashfields,100,0,0,,,patient
STUDY-2024-001,0,SIV,Ashfields,1000,0,0,,,siv
```

---

## 3. ACTUAL_VISITS TABLE

### Column Names:
- **PatientID** (text, NOT NULL) - Patient identifier (or pseudo-ID for study events)
- **Study** (text, NOT NULL) - Study name/code
- **VisitName** (text, NOT NULL) - Visit identifier
- **ActualDate** (date, NOT NULL) - Date visit actually occurred
- **Notes** (text, NULL) - Additional notes
- **VisitType** (text, NULL) - "patient", "siv", "monitor", or "extra"

### CSV Format:
```csv
PatientID,Study,VisitName,ActualDate,Notes,VisitType
P001,STUDY-2024-001,V1,15/03/2024,,patient
SIV_STUDY-2024-001,STUDY-2024-001,SIV,01/03/2024,,siv
```

---

## Key Rules:

1. **All column names use PascalCase** - No snake_case, no lowercase
2. **CSV files match database exactly** - Same column names, same order
3. **No renaming needed** - Export/import uses same names as database
4. **Quoted identifiers** - In SQL, use double quotes: `"PatientID"`, `"VisitType"`

## Benefits:

- ✅ No column name conversion needed
- ✅ CSV files can be imported directly
- ✅ Exported CSV files match database schema exactly
- ✅ Consistent naming throughout the entire system
- ✅ Easier to understand and maintain

