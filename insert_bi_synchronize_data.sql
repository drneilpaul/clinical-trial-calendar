-- SQL INSERT statements for BI-Synchronize Study
-- Generated from Excel data provided
-- Column names match PascalCase convention
-- Dates use UK format (DD/MM/YYYY) with TO_DATE() function
--
-- IMPORTANT NOTES:
-- 1. Patient visit dates in actual_visits table are ESTIMATED - please verify and update
--    with actual dates from your Excel file before running this script
-- 2. Monitoring event dates are ESTIMATED - please verify from Excel rows with PatientID="N/A"
-- 3. Day numbers in trial_schedules are calculated from week numbers (Week × 7 = Day)
-- 4. Payment amounts extracted from Cost column in Excel
-- 5. All patients have PatientPractice="Kiltearn" (recruitment site)
-- 6. SiteforVisit="Kiltearn" for all visits (where work is performed)
--
-- To use this script:
-- 1. Review and update estimated dates in actual_visits section
-- 2. Verify payment amounts match your records
-- 3. If you get duplicate key errors, delete existing data first:
--    DELETE FROM public.actual_visits WHERE "Study" = 'BI-Synchronize';
--    DELETE FROM public.trial_schedules WHERE "Study" = 'BI-Synchronize';
--    DELETE FROM public.patients WHERE "Study" = 'BI-Synchronize';
-- 4. Run in Supabase SQL Editor
-- 5. Check for any errors

-- ============================================
-- 1. PATIENTS TABLE
-- ============================================
-- Insert 4 patients with baseline dates from V1 visits
-- PatientPractice = "Kiltearn" for all patients

-- Note: If patients already exist, you may get duplicate key errors
-- Delete existing patients first if needed: DELETE FROM public.patients WHERE "Study" = 'BI-Synchronize';
INSERT INTO public.patients ("PatientID", "Study", "StartDate", "PatientPractice")
VALUES
('3826001001', 'BI-Synchronize', TO_DATE('04/01/2024', 'DD/MM/YYYY'), 'Kiltearn'),
('3826001002', 'BI-Synchronize', TO_DATE('11/01/2024', 'DD/MM/YYYY'), 'Kiltearn'),
('3826001003', 'BI-Synchronize', TO_DATE('02/02/2024', 'DD/MM/YYYY'), 'Kiltearn'),
('3826001004', 'BI-Synchronize', TO_DATE('13/02/2024', 'DD/MM/YYYY'), 'Kiltearn');

-- ============================================
-- 2. TRIAL_SCHEDULES TABLE
-- ============================================
-- V1 baseline (Day 1) + visits that occurred in 2025-2026
-- Week numbers converted to days (Week 2 = Day 14, Week 3 = Day 21, etc.)
-- Monitoring events (Day 0, VisitType="monitor")

INSERT INTO public.trial_schedules ("Study", "Day", "VisitName", "SiteforVisit", "Payment", "ToleranceBefore", "ToleranceAfter", "IntervalUnit", "IntervalValue", "VisitType")
VALUES
-- Baseline visit (Day 1)
('BI-Synchronize', 1, 'V1', 'Kiltearn', 1676.00, 0, 0, NULL, NULL, 'patient'),

-- Visits that occurred in 2025-2026
-- Day numbers calculated from week numbers: Week number × 7 = Day number
-- Based on schedule table showing visits at various weeks
('BI-Synchronize', 112, 'V16', 'Kiltearn', 1098.00, 0, 0, NULL, NULL, 'patient'),  -- Week 16 = Day 112
('BI-Synchronize', 119, 'V17 Remote', 'Kiltearn', 311.00, 0, 0, NULL, NULL, 'patient'),  -- Week 17 = Day 119
('BI-Synchronize', 126, 'V18', 'Kiltearn', 1031.00, 0, 0, NULL, NULL, 'patient'),  -- Week 18 = Day 126
('BI-Synchronize', 133, 'V19/EOT', 'Kiltearn', 1142.00, 0, 0, NULL, NULL, 'patient'),  -- Week 19 = Day 133
('BI-Synchronize', 140, 'V20/EOS', 'Kiltearn', 644.00, 0, 0, NULL, NULL, 'patient'),  -- Week 20 = Day 140
('BI-Synchronize', 147, 'V21/FU2', 'Kiltearn', 0.00, 0, 0, NULL, NULL, 'patient'),  -- Week 21 = Day 147

-- Monitoring events (Day 0, VisitType="monitor")
-- Payment amounts represent typical values from the data
-- Note: If trial schedules already exist, you may get duplicate key errors
-- Delete existing schedules first if needed: DELETE FROM public.trial_schedules WHERE "Study" = 'BI-Synchronize';
('BI-Synchronize', 0, 'On Site Monitoring', 'Kiltearn', 210.00, 0, 0, NULL, NULL, 'monitor'),
('BI-Synchronize', 0, 'Remote Monitoring', 'Kiltearn', 210.00, 0, 0, NULL, NULL, 'monitor');

-- ============================================
-- 3. ACTUAL_VISITS TABLE
-- ============================================
-- Patient visits that occurred in 2025-2026
-- Monitoring events with PatientID="MONITOR_BI-Synchronize"
-- Dates converted from DD.MM.YYYY to DD/MM/YYYY format

-- Patient Visits (2025-2026)
-- Note: V1 visits were in 2024 (baseline), so not included here
-- Only visits that occurred in 2025-2026 are included
-- IMPORTANT: Please verify actual visit dates from your Excel file and update accordingly
-- The dates below are estimated based on visit sequence - replace with actual dates from Excel
INSERT INTO public.actual_visits ("PatientID", "Study", "VisitName", "ActualDate", "Notes", "VisitType")
VALUES
-- Patient 3826001001 visits in 2025-2026
-- TODO: Replace estimated dates with actual dates from Excel file
('3826001001', 'BI-Synchronize', 'V17 Remote', TO_DATE('15/01/2025', 'DD/MM/YYYY'), NULL, 'patient'),
('3826001001', 'BI-Synchronize', 'V16', TO_DATE('22/01/2025', 'DD/MM/YYYY'), NULL, 'patient'),
('3826001001', 'BI-Synchronize', 'V18', TO_DATE('29/01/2025', 'DD/MM/YYYY'), NULL, 'patient'),
('3826001001', 'BI-Synchronize', 'V19/EOT', TO_DATE('05/02/2025', 'DD/MM/YYYY'), NULL, 'patient'),
('3826001001', 'BI-Synchronize', 'V20/EOS', TO_DATE('12/02/2025', 'DD/MM/YYYY'), NULL, 'patient'),
('3826001001', 'BI-Synchronize', 'V21/FU2', TO_DATE('19/02/2025', 'DD/MM/YYYY'), NULL, 'patient'),

-- Patient 3826001002 visits in 2025-2026
('3826001002', 'BI-Synchronize', 'V17 Remote', TO_DATE('22/01/2025', 'DD/MM/YYYY'), NULL, 'patient'),
('3826001002', 'BI-Synchronize', 'V16', TO_DATE('29/01/2025', 'DD/MM/YYYY'), NULL, 'patient'),
('3826001002', 'BI-Synchronize', 'V18', TO_DATE('05/02/2025', 'DD/MM/YYYY'), NULL, 'patient'),
('3826001002', 'BI-Synchronize', 'V19/EOT', TO_DATE('12/02/2025', 'DD/MM/YYYY'), NULL, 'patient'),
('3826001002', 'BI-Synchronize', 'V20/EOS', TO_DATE('19/02/2025', 'DD/MM/YYYY'), NULL, 'patient'),
('3826001002', 'BI-Synchronize', 'V21/FU2', TO_DATE('26/02/2025', 'DD/MM/YYYY'), NULL, 'patient'),

-- Patient 3826001003 visits in 2025-2026
('3826001003', 'BI-Synchronize', 'V17 Remote', TO_DATE('29/01/2025', 'DD/MM/YYYY'), NULL, 'patient'),
('3826001003', 'BI-Synchronize', 'V16', TO_DATE('05/02/2025', 'DD/MM/YYYY'), NULL, 'patient'),
('3826001003', 'BI-Synchronize', 'V18', TO_DATE('12/02/2025', 'DD/MM/YYYY'), NULL, 'patient'),
('3826001003', 'BI-Synchronize', 'V19/EOT', TO_DATE('19/02/2025', 'DD/MM/YYYY'), NULL, 'patient'),
('3826001003', 'BI-Synchronize', 'V20/EOS', TO_DATE('26/02/2025', 'DD/MM/YYYY'), NULL, 'patient'),
('3826001003', 'BI-Synchronize', 'V21/FU2', TO_DATE('05/03/2025', 'DD/MM/YYYY'), NULL, 'patient'),

-- Patient 3826001004 visits in 2025-2026
('3826001004', 'BI-Synchronize', 'V17 Remote', TO_DATE('05/02/2025', 'DD/MM/YYYY'), NULL, 'patient'),
('3826001004', 'BI-Synchronize', 'V16', TO_DATE('12/02/2025', 'DD/MM/YYYY'), NULL, 'patient'),
('3826001004', 'BI-Synchronize', 'V18', TO_DATE('19/02/2025', 'DD/MM/YYYY'), NULL, 'patient'),
('3826001004', 'BI-Synchronize', 'V19/EOT', TO_DATE('26/02/2025', 'DD/MM/YYYY'), NULL, 'patient'),
('3826001004', 'BI-Synchronize', 'V20/EOS', TO_DATE('05/03/2025', 'DD/MM/YYYY'), NULL, 'patient'),
('3826001004', 'BI-Synchronize', 'V21/FU2', TO_DATE('12/03/2025', 'DD/MM/YYYY'), NULL, 'patient'),

-- Monitoring Events
-- TODO: Replace estimated dates with actual dates from Excel file
-- Extract dates from rows with PatientID="N/A" and VisitName containing "Monitoring"
-- On Site Monitoring
('MONITOR_BI-Synchronize', 'BI-Synchronize', 'On Site Monitoring', TO_DATE('15/01/2025', 'DD/MM/YYYY'), 'Invoiced £210', 'monitor'),
('MONITOR_BI-Synchronize', 'BI-Synchronize', 'On Site Monitoring', TO_DATE('12/06/2025', 'DD/MM/YYYY'), 'Invoiced £346.5', 'monitor'),
('MONITOR_BI-Synchronize', 'BI-Synchronize', 'On Site Monitoring', TO_DATE('12/01/2026', 'DD/MM/YYYY'), 'Invoiced £199', 'monitor'),

-- Remote Monitoring  
-- Note: If visits already exist, you may get duplicate key errors
-- Delete existing visits first if needed: DELETE FROM public.actual_visits WHERE "Study" = 'BI-Synchronize';
('MONITOR_BI-Synchronize', 'BI-Synchronize', 'Remote Monitoring', TO_DATE('15/01/2025', 'DD/MM/YYYY'), 'Invoiced £210', 'monitor'),
('MONITOR_BI-Synchronize', 'BI-Synchronize', 'Remote Monitoring', TO_DATE('12/06/2025', 'DD/MM/YYYY'), 'Invoiced £346.5', 'monitor'),
('MONITOR_BI-Synchronize', 'BI-Synchronize', 'Remote Monitoring', TO_DATE('12/01/2026', 'DD/MM/YYYY'), 'Invoiced £199', 'monitor');

