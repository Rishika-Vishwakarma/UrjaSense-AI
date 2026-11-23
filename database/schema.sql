-- ============================================================================
-- UrjaSense AI - MySQL 8 schema (Team SparkX)
-- Primary database: MySQL (Amazon RDS for MySQL in the cloud setup).
-- The statements stick to a portable subset so the same file can also be
-- loaded into SQLite for automated tests (database/database_config.py
-- translates the few MySQL-only keywords). Production target is MySQL.
-- ============================================================================

CREATE DATABASE IF NOT EXISTS urjasense CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE urjasense;

-- ---------------------------------------------------------------------------
-- 1. Areas: electricity service areas / localities
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS areas (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    name          VARCHAR(120) NOT NULL,
    city          VARCHAR(80)  NOT NULL,
    district      VARCHAR(80)  NOT NULL,
    ward_code     VARCHAR(20)  NOT NULL UNIQUE,
    latitude      DECIMAL(9,6) NOT NULL,
    longitude     DECIMAL(9,6) NOT NULL,
    radius_km     DECIMAL(4,2) NOT NULL DEFAULT 1.50,
    is_active     TINYINT      NOT NULL DEFAULT 1,
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_area_lat CHECK (latitude BETWEEN -90 AND 90),
    CONSTRAINT chk_area_lng CHECK (longitude BETWEEN -180 AND 180),
    CONSTRAINT chk_area_radius CHECK (radius_km > 0)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------------
-- 2. Users: residents, linemen and admins (role-based access)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    full_name           VARCHAR(120) NOT NULL,
    email               VARCHAR(160) NOT NULL UNIQUE,
    phone               VARCHAR(20),
    password_hash       VARCHAR(300) NOT NULL,
    role                VARCHAR(10)  NOT NULL DEFAULT 'public',
    preferred_language  VARCHAR(5)   NOT NULL DEFAULT 'en',
    area_id             INT NULL,
    address             VARCHAR(255),
    is_active           TINYINT      NOT NULL DEFAULT 1,
    is_sample           TINYINT      NOT NULL DEFAULT 0,
    created_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_user_role CHECK (role IN ('public','lineman','admin')),
    CONSTRAINT chk_user_lang CHECK (preferred_language IN ('en','hi')),
    CONSTRAINT fk_user_area FOREIGN KEY (area_id) REFERENCES areas(id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------------
-- 3. Linemen: employee profile. Rows are created ONLY by administrators.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS linemen (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    user_id        INT NOT NULL UNIQUE,
    employee_code  VARCHAR(30) NOT NULL UNIQUE,
    designation    VARCHAR(80) NOT NULL DEFAULT 'Lineman',
    area_id        INT NULL,
    approval_status VARCHAR(12) NOT NULL DEFAULT 'APPROVED',
    approved_by    INT NULL,
    created_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_lineman_status CHECK (approval_status IN ('PENDING','APPROVED','SUSPENDED')),
    CONSTRAINT fk_lineman_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_lineman_area FOREIGN KEY (area_id) REFERENCES areas(id) ON DELETE SET NULL,
    CONSTRAINT fk_lineman_approver FOREIGN KEY (approved_by) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------------
-- 4. Outage incidents: one row per real-world outage (many reports -> 1 incident)
--    suggested_category = automated suggestion (NOT verified)
--    verified_category / official_cause = set only by an authorised lineman / admin
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS outage_incidents (
    id                      INT AUTO_INCREMENT PRIMARY KEY,
    incident_code           VARCHAR(30) NOT NULL UNIQUE,
    area_id                 INT NOT NULL,
    location_text           VARCHAR(255),
    latitude                DECIMAL(9,6) NULL,
    longitude               DECIMAL(9,6) NULL,
    suggested_category      VARCHAR(40) NOT NULL DEFAULT 'unknown',
    verified_category       VARCHAR(40) NULL,
    official_cause          VARCHAR(255) NULL,
    status                  VARCHAR(24) NOT NULL DEFAULT 'REPORTED',
    priority                VARCHAR(10) NOT NULL DEFAULT 'LOW',
    affected_count          INT NOT NULL DEFAULT 1,
    outage_start_time       DATETIME NOT NULL,
    predicted_minutes       INT NULL,
    predicted_restoration_at DATETIME NULL,
    lineman_eta_at          DATETIME NULL,
    repair_progress_pct     INT NOT NULL DEFAULT 0,
    resolved_at             DATETIME NULL,
    is_sample               TINYINT NOT NULL DEFAULT 0,
    created_at              DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at              DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_inc_status CHECK (status IN ('REPORTED','VERIFIED','ASSIGNED','REPAIR_IN_PROGRESS','RESOLVED')),
    CONSTRAINT chk_inc_priority CHECK (priority IN ('LOW','MEDIUM','HIGH','CRITICAL')),
    CONSTRAINT chk_inc_affected CHECK (affected_count >= 1),
    CONSTRAINT chk_inc_progress CHECK (repair_progress_pct BETWEEN 0 AND 100),
    CONSTRAINT fk_inc_area FOREIGN KEY (area_id) REFERENCES areas(id)
) ENGINE=InnoDB;
CREATE INDEX idx_inc_area_status ON outage_incidents (area_id, status);
CREATE INDEX idx_inc_start ON outage_incidents (outage_start_time);

-- ---------------------------------------------------------------------------
-- 5. Outage reports: every individual resident report is preserved
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS outage_reports (
    id                 INT AUTO_INCREMENT PRIMARY KEY,
    report_code        VARCHAR(30) NOT NULL UNIQUE,
    user_id            INT NOT NULL,
    incident_id        INT NOT NULL,
    area_id            INT NOT NULL,
    location_text      VARCHAR(255) NOT NULL,
    latitude           DECIMAL(9,6) NULL,
    longitude          DECIMAL(9,6) NULL,
    outage_start_time  DATETIME NOT NULL,
    issue_details      VARCHAR(1000),
    suggested_category VARCHAR(40) NOT NULL DEFAULT 'unknown',
    matched_existing   TINYINT NOT NULL DEFAULT 0,
    match_score        DECIMAL(4,2) NULL,
    created_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_report_user_incident UNIQUE (user_id, incident_id),
    CONSTRAINT fk_rep_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_rep_incident FOREIGN KEY (incident_id) REFERENCES outage_incidents(id) ON DELETE CASCADE,
    CONSTRAINT fk_rep_area FOREIGN KEY (area_id) REFERENCES areas(id)
) ENGINE=InnoDB;
CREATE INDEX idx_rep_user ON outage_reports (user_id, created_at);

-- ---------------------------------------------------------------------------
-- 6. Incident updates: status history + progress notes
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS incident_updates (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    incident_id      INT NOT NULL,
    previous_status  VARCHAR(24) NULL,
    new_status       VARCHAR(24) NOT NULL,
    updated_by       INT NULL,
    remarks          VARCHAR(1000),
    created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_upd_incident FOREIGN KEY (incident_id) REFERENCES outage_incidents(id) ON DELETE CASCADE,
    CONSTRAINT fk_upd_user FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB;
CREATE INDEX idx_upd_incident ON incident_updates (incident_id, created_at);

-- ---------------------------------------------------------------------------
-- 7. Assignments: incident <-> lineman (history kept; one active at a time)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS assignments (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    incident_id  INT NOT NULL,
    lineman_id   INT NOT NULL,
    assigned_by  INT NULL,
    is_active    TINYINT NOT NULL DEFAULT 1,
    assigned_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_asg_incident FOREIGN KEY (incident_id) REFERENCES outage_incidents(id) ON DELETE CASCADE,
    CONSTRAINT fk_asg_lineman FOREIGN KEY (lineman_id) REFERENCES linemen(id) ON DELETE CASCADE,
    CONSTRAINT fk_asg_admin FOREIGN KEY (assigned_by) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB;
CREATE INDEX idx_asg_lineman ON assignments (lineman_id, is_active);

-- ---------------------------------------------------------------------------
-- 8. Notifications (in-app; optionally mirrored to Amazon SNS)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS notifications (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    user_id      INT NOT NULL,
    incident_id  INT NULL,
    title        VARCHAR(200) NOT NULL,
    message      VARCHAR(1000) NOT NULL,
    title_hi     VARCHAR(300) NULL,
    message_hi   VARCHAR(1500) NULL,
    is_read      TINYINT NOT NULL DEFAULT 0,
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_not_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_not_incident FOREIGN KEY (incident_id) REFERENCES outage_incidents(id) ON DELETE SET NULL
) ENGINE=InnoDB;
CREATE INDEX idx_not_user ON notifications (user_id, is_read, created_at);

-- ---------------------------------------------------------------------------
-- 9. Ratings and feedback after resolution
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ratings (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    incident_id  INT NOT NULL,
    user_id      INT NOT NULL,
    rating       INT NOT NULL,
    feedback     VARCHAR(1000),
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_rating CHECK (rating BETWEEN 1 AND 5),
    CONSTRAINT uq_rating UNIQUE (incident_id, user_id),
    CONSTRAINT fk_rat_incident FOREIGN KEY (incident_id) REFERENCES outage_incidents(id) ON DELETE CASCADE,
    CONSTRAINT fk_rat_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------------
-- 10. Audit logs
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_logs (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    user_id      INT NULL,
    action       VARCHAR(60) NOT NULL,
    entity_type  VARCHAR(40),
    entity_id    INT NULL,
    ip_address   VARCHAR(45),
    details      VARCHAR(1000),
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_aud_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB;
CREATE INDEX idx_aud_created ON audit_logs (created_at);

-- ---------------------------------------------------------------------------
-- 11. Historical outages (supporting table for analytics).
--     is_sample = 1 means SIMULATED demonstration data, not department records.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS historical_outages (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    area_id           INT NOT NULL,
    category          VARCHAR(40) NOT NULL,
    started_at        DATETIME NOT NULL,
    duration_minutes  INT NOT NULL,
    affected_count    INT NOT NULL,
    is_sample         TINYINT NOT NULL DEFAULT 1,
    CONSTRAINT chk_hist_duration CHECK (duration_minutes > 0),
    CONSTRAINT fk_hist_area FOREIGN KEY (area_id) REFERENCES areas(id)
) ENGINE=InnoDB;
CREATE INDEX idx_hist_area ON historical_outages (area_id, started_at);
