-- SQL UPDATE statements to correct actual visit dates for BI-Synchronize Study
-- Generated to fix incorrect dates in actual_visits table
-- Dates use UK format (DD/MM/YYYY) with TO_DATE() function
-- Dates extracted from Excel file

-- ============================================
-- UPDATE PATIENT VISIT DATES
-- ============================================

-- Patient 3826001001
UPDATE public.actual_visits
SET "ActualDate" = TO_DATE('23/04/2025', 'DD/MM/YYYY')
WHERE "PatientID" = '3826001001'
  AND "Study" = 'BI-Synchronize'
  AND "VisitName" = 'V17 Remote';

UPDATE public.actual_visits
SET "ActualDate" = TO_DATE('04/06/2025', 'DD/MM/YYYY')
WHERE "PatientID" = '3826001001'
  AND "Study" = 'BI-Synchronize'
  AND "VisitName" = 'V18';

UPDATE public.actual_visits
SET "ActualDate" = TO_DATE('03/07/2025', 'DD/MM/YYYY')
WHERE "PatientID" = '3826001001'
  AND "Study" = 'BI-Synchronize'
  AND "VisitName" = 'V19/EOT';

UPDATE public.actual_visits
SET "ActualDate" = TO_DATE('23/07/2025', 'DD/MM/YYYY')
WHERE "PatientID" = '3826001001'
  AND "Study" = 'BI-Synchronize'
  AND "VisitName" = 'V20/EOS';

-- Patient 3826001002
UPDATE public.actual_visits
SET "ActualDate" = TO_DATE('02/05/2025', 'DD/MM/YYYY')
WHERE "PatientID" = '3826001002'
  AND "Study" = 'BI-Synchronize'
  AND "VisitName" = 'V17 Remote';

UPDATE public.actual_visits
SET "ActualDate" = TO_DATE('12/06/2025', 'DD/MM/YYYY')
WHERE "PatientID" = '3826001002'
  AND "Study" = 'BI-Synchronize'
  AND "VisitName" = 'V18';

UPDATE public.actual_visits
SET "ActualDate" = TO_DATE('11/07/2025', 'DD/MM/YYYY')
WHERE "PatientID" = '3826001002'
  AND "Study" = 'BI-Synchronize'
  AND "VisitName" = 'V19/EOT';

UPDATE public.actual_visits
SET "ActualDate" = TO_DATE('31/07/2025', 'DD/MM/YYYY')
WHERE "PatientID" = '3826001002'
  AND "Study" = 'BI-Synchronize'
  AND "VisitName" = 'V20/EOS';

-- Patient 3826001003
UPDATE public.actual_visits
SET "ActualDate" = TO_DATE('09/04/2025', 'DD/MM/YYYY')
WHERE "PatientID" = '3826001003'
  AND "Study" = 'BI-Synchronize'
  AND "VisitName" = 'V16';

UPDATE public.actual_visits
SET "ActualDate" = TO_DATE('19/05/2025', 'DD/MM/YYYY')
WHERE "PatientID" = '3826001003'
  AND "Study" = 'BI-Synchronize'
  AND "VisitName" = 'V17 Remote';

UPDATE public.actual_visits
SET "ActualDate" = TO_DATE('01/07/2025', 'DD/MM/YYYY')
WHERE "PatientID" = '3826001003'
  AND "Study" = 'BI-Synchronize'
  AND "VisitName" = 'V18';

UPDATE public.actual_visits
SET "ActualDate" = TO_DATE('29/07/2025', 'DD/MM/YYYY')
WHERE "PatientID" = '3826001003'
  AND "Study" = 'BI-Synchronize'
  AND "VisitName" = 'V19/EOT';

UPDATE public.actual_visits
SET "ActualDate" = TO_DATE('02/09/2025', 'DD/MM/YYYY')
WHERE "PatientID" = '3826001003'
  AND "Study" = 'BI-Synchronize'
  AND "VisitName" = 'V20/EOS';

-- Patient 3826001004
UPDATE public.actual_visits
SET "ActualDate" = TO_DATE('29/04/2025', 'DD/MM/YYYY')
WHERE "PatientID" = '3826001004'
  AND "Study" = 'BI-Synchronize'
  AND "VisitName" = 'V16';

UPDATE public.actual_visits
SET "ActualDate" = TO_DATE('06/06/2025', 'DD/MM/YYYY')
WHERE "PatientID" = '3826001004'
  AND "Study" = 'BI-Synchronize'
  AND "VisitName" = 'V17 Remote';

UPDATE public.actual_visits
SET "ActualDate" = TO_DATE('18/07/2025', 'DD/MM/YYYY')
WHERE "PatientID" = '3826001004'
  AND "Study" = 'BI-Synchronize'
  AND "VisitName" = 'V18';

UPDATE public.actual_visits
SET "ActualDate" = TO_DATE('14/08/2025', 'DD/MM/YYYY')
WHERE "PatientID" = '3826001004'
  AND "Study" = 'BI-Synchronize'
  AND "VisitName" = 'V19/EOT';

UPDATE public.actual_visits
SET "ActualDate" = TO_DATE('05/09/2025', 'DD/MM/YYYY')
WHERE "PatientID" = '3826001004'
  AND "Study" = 'BI-Synchronize'
  AND "VisitName" = 'V20/EOS';

UPDATE public.actual_visits
SET "ActualDate" = TO_DATE('09/12/2025', 'DD/MM/YYYY')
WHERE "PatientID" = '3826001004'
  AND "Study" = 'BI-Synchronize'
  AND "VisitName" = 'V21/FU2';

-- ============================================
-- UPDATE MONITORING EVENT DATES AND NOTES
-- ============================================
-- Note: Monitoring events may need to be deleted and re-inserted if the count doesn't match
-- Excel shows: 4 On Site Monitoring events, 2 Remote Monitoring events

-- First, delete all existing monitoring events to start fresh
DELETE FROM public.actual_visits
WHERE "PatientID" LIKE '%MONITOR_BI-Synchronize%'
  AND "Study" = 'BI-Synchronize'
  AND "VisitType" = 'monitor';

-- Insert On Site Monitoring events with correct dates from Excel
INSERT INTO public.actual_visits ("PatientID", "Study", "VisitName", "ActualDate", "Notes", "VisitType")
VALUES
('MONITOR_BI-Synchronize', 'BI-Synchronize', 'On Site Monitoring', TO_DATE('14/06/2025', 'DD/MM/YYYY'), 'Invoiced £210', 'monitor'),
('MONITOR_BI-Synchronize', 'BI-Synchronize', 'On Site Monitoring', TO_DATE('23/07/2025', 'DD/MM/YYYY'), 'Invoiced £346.5', 'monitor'),
('MONITOR_BI-Synchronize', 'BI-Synchronize', 'On Site Monitoring', TO_DATE('09/09/2025', 'DD/MM/YYYY'), 'Invoiced £346.5', 'monitor'),
('MONITOR_BI-Synchronize', 'BI-Synchronize', 'On Site Monitoring', TO_DATE('10/09/2025', 'DD/MM/YYYY'), 'Invoiced £346.5', 'monitor');

-- Insert Remote Monitoring events with correct dates from Excel
INSERT INTO public.actual_visits ("PatientID", "Study", "VisitName", "ActualDate", "Notes", "VisitType")
VALUES
('MONITOR_BI-Synchronize', 'BI-Synchronize', 'Remote Monitoring', TO_DATE('28/10/2025', 'DD/MM/YYYY'), 'Invoiced £199', 'monitor'),
('MONITOR_BI-Synchronize', 'BI-Synchronize', 'Remote Monitoring', TO_DATE('12/01/2026', 'DD/MM/YYYY'), 'Pending', 'monitor');

-- ============================================
-- DELETE VISITS THAT DON'T EXIST IN EXCEL
-- ============================================
-- Remove visits that were incorrectly added but don't exist in the Excel file

-- Patient 3826001001: Delete V16 and V21/FU2 (not in Excel)
DELETE FROM public.actual_visits
WHERE "PatientID" = '3826001001'
  AND "Study" = 'BI-Synchronize'
  AND "VisitName" IN ('V16', 'V21/FU2');

-- Patient 3826001002: Delete V16 and V21/FU2 (not in Excel)
DELETE FROM public.actual_visits
WHERE "PatientID" = '3826001002'
  AND "Study" = 'BI-Synchronize'
  AND "VisitName" IN ('V16', 'V21/FU2');

-- Patient 3826001003: Delete V21/FU2 (not in Excel)
DELETE FROM public.actual_visits
WHERE "PatientID" = '3826001003'
  AND "Study" = 'BI-Synchronize'
  AND "VisitName" = 'V21/FU2';

-- ============================================
-- VERIFICATION QUERIES
-- ============================================
-- Run these queries to verify the dates before and after updates

-- Check all BI-Synchronize patient visits (ordered by patient and date)
SELECT "PatientID", "VisitName", "ActualDate", "Notes"
FROM public.actual_visits
WHERE "Study" = 'BI-Synchronize'
  AND "VisitType" = 'patient'
ORDER BY "PatientID", "ActualDate";

-- Check all BI-Synchronize monitoring events (ordered by date)
SELECT "PatientID", "VisitName", "ActualDate", "Notes"
FROM public.actual_visits
WHERE "Study" = 'BI-Synchronize'
  AND "VisitType" = 'monitor'
ORDER BY "ActualDate";

-- Count visits per patient to verify all visits are present
SELECT "PatientID", COUNT(*) as visit_count
FROM public.actual_visits
WHERE "Study" = 'BI-Synchronize'
  AND "VisitType" = 'patient'
GROUP BY "PatientID"
ORDER BY "PatientID";

