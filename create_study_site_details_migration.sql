CREATE TABLE IF NOT EXISTS study_site_details (
    "Study" TEXT NOT NULL,
    "SiteforVisit" TEXT NOT NULL,
    "FPFV" DATE,
    "LPFV" DATE,
    "LPLV" DATE,
    "StudyStatus" TEXT DEFAULT 'active',
    "RecruitmentTarget" INTEGER,
    "Description" TEXT,
    "EOIDate" DATE,
    "StudyURL" TEXT,
    "DocumentLinks" JSONB,
    PRIMARY KEY ("Study", "SiteforVisit"),
    CONSTRAINT valid_study_status CHECK ("StudyStatus" IN ('active', 'contracted', 'in_setup', 'expression_of_interest', 'eoi_didnt_get'))
);

CREATE INDEX IF NOT EXISTS idx_study_site_details_study ON study_site_details("Study");
CREATE INDEX IF NOT EXISTS idx_study_site_details_status ON study_site_details("StudyStatus");
CREATE INDEX IF NOT EXISTS idx_study_site_details_eoi_date ON study_site_details("EOIDate") WHERE "EOIDate" IS NOT NULL;

INSERT INTO study_site_details ("Study", "SiteforVisit", "StudyStatus")
SELECT DISTINCT ON ("Study", "SiteforVisit")
    "Study",
    "SiteforVisit",
    'active' AS "StudyStatus"
FROM trial_schedules ts1
WHERE "Study" IS NOT NULL 
  AND "SiteforVisit" IS NOT NULL
  AND "Study" != ''
  AND "SiteforVisit" != ''
ON CONFLICT ("Study", "SiteforVisit") DO NOTHING;
