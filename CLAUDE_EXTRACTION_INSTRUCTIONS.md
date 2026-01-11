# Instructions for Claude: Extract Study Information from Protocols

## Purpose
Extract study information from clinical trial protocols to populate the Gantt chart and recruitment tracking features in the Clinical Trial Calendar application.

## Critical Rules

1. **DO NOT INVENT DATA** - Only extract information that is explicitly stated in the protocol documents
2. **Mark missing information clearly** - Use "N/A" or leave blank if information is not available
3. **Use exact study names** - Copy study names exactly as they appear in protocols
4. **Verify site names** - Use exact site names (typically "Ashfields" or "Kiltearn" but verify from protocol)
5. **Date format** - Use DD/MM/YYYY format (e.g., 15/03/2024)

## Information to Extract

For each study, extract the following information **per site** (if the study involves multiple sites, create a separate row for each site):

### Required Fields

1. **Study** - Study name/code (exact name from protocol)
2. **SiteforVisit** - Site name where visits are performed (e.g., "Ashfields", "Kiltearn")
3. **StudyStatus** - Current status of the study at this site:
   - `active` - Study is actively running
   - `contracted` - Study is contracted but not yet active
   - `in_setup` - Study is in setup/preparation phase
   - `expression_of_interest` - Expression of interest, not yet contracted

### Optional Fields (Extract if Available)

4. **FPFV (First Patient First Visit)** - Date when first patient was enrolled/started
   - Look for: "First patient enrolled", "FPFV", "First patient first visit", enrollment start date
   - Format: DD/MM/YYYY or leave blank if not found

5. **LPFV (Last Patient First Visit)** - Date when last patient was enrolled
   - Look for: "Last patient enrolled", "LPFV", "Last patient first visit", enrollment end date
   - Format: DD/MM/YYYY or leave blank if not found

6. **LPLV (Last Patient Last Visit)** - Date when last patient's final visit is expected/completed
   - Look for: "Last patient last visit", "LPLV", "Study end date", "Final visit date"
   - Format: DD/MM/YYYY or leave blank if not found

7. **RecruitmentTarget** - Target number of patients for this study at this site
   - Look for: "Target enrollment", "Recruitment target", "N=", "Sample size"
   - Format: Integer number (e.g., 50) or leave blank if not found

## Output Format

Provide the extracted data as a **CSV table** with the following columns:

```
Study,SiteforVisit,StudyStatus,FPFV,LPFV,LPLV,RecruitmentTarget
```

### Example Output

```csv
Study,SiteforVisit,StudyStatus,FPFV,LPFV,LPLV,RecruitmentTarget
STUDY-2024-001,Ashfields,active,15/03/2024,30/06/2024,15/12/2025,25
STUDY-2024-001,Kiltearn,active,20/03/2024,15/07/2024,20/12/2025,25
STUDY-2024-002,Ashfields,contracted,N/A,N/A,N/A,50
BI-Synchronize,Kiltearn,active,01/04/2024,N/A,N/A,30
```

## Extraction Guidelines

### Study Name
- Extract the exact study name/code as it appears in the protocol
- Common formats: Protocol numbers, study codes, abbreviated names
- If multiple names are used, use the primary/formal study identifier

### Site Information
- Identify which sites are involved in the study
- If protocol mentions "multi-site" or lists sites, extract each site separately
- If site is not explicitly mentioned, you may need to infer from context or mark as "N/A"
- **DO NOT** invent site names - only use names explicitly mentioned

### Dates (FPFV, LPFV, LPLV)
- Look for specific date fields in protocol documents
- Check study timelines, milestones, or enrollment sections
- If dates are given as "Q1 2024" or "March 2024", convert to a specific date (e.g., 01/03/2024) or mark as N/A
- If only year is given, use first day of year (e.g., "2024" → "01/01/2024") and note this in comments
- **DO NOT** calculate or estimate dates - only use explicitly stated dates

### Recruitment Target
- Look for sample size, enrollment target, or "N=" in protocol
- Extract the number only (not text like "approximately 50")
- If target is per site, use that number
- If target is total across sites, you may need to divide or mark as "see notes"
- **DO NOT** estimate or calculate targets

### Study Status
- Determine current status based on protocol information:
  - **active**: Study is currently enrolling or in follow-up
  - **contracted**: Contract signed but enrollment not started
  - **in_setup**: Protocol approved, site setup in progress
  - **expression_of_interest**: Initial interest expressed, no contract yet
- If status is unclear, use "active" as default or mark as "N/A"

## What to Do When Information is Missing

- **Leave field blank** in the CSV (empty cell)
- **OR** use "N/A" if you want to explicitly mark as not available
- **Add a comment column** if helpful to note why information is missing
- **DO NOT** fill in with estimated, calculated, or assumed values

## Quality Checks Before Submitting

1. ✅ All study names are exact matches from protocols (no typos)
2. ✅ All site names are valid (Ashfields, Kiltearn, or other verified sites)
3. ✅ All dates are in DD/MM/YYYY format
4. ✅ No invented or estimated data
5. ✅ Missing information is clearly marked (blank or "N/A")
6. ✅ Each Study+Site combination has its own row
7. ✅ Recruitment targets are integers (no decimals, no text)

## Example Protocol Analysis

**If protocol says:**
- "Study ABC-123 will enroll 50 patients across 2 sites (Ashfields and Kiltearn)"
- "Enrollment period: March 2024 - June 2024"
- "Study duration: 12 months from first patient enrollment"
- "Target: 25 patients per site"

**Extract as:**
```csv
Study,SiteforVisit,StudyStatus,FPFV,LPFV,LPLV,RecruitmentTarget
ABC-123,Ashfields,active,01/03/2024,30/06/2024,N/A,25
ABC-123,Kiltearn,active,01/03/2024,30/06/2024,N/A,25
```

**Note:** LPLV would be calculated as approximately 12 months after FPFV, but since it's not explicitly stated, leave as N/A.

## Final Output

Provide the extracted data as a **CSV table** that can be directly imported into the Clinical Trial Calendar application. Include a brief summary of:
- Number of studies extracted
- Number of Study+Site combinations
- Which fields were commonly missing
- Any notes about ambiguous information
