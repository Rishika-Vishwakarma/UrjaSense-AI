-- ============================================================================
-- UrjaSense AI - SAMPLE / DEMO DATA ONLY
-- Everything below is simulated for demonstration and testing. It is NOT
-- information from any electricity department. Rows carry is_sample = 1.
-- Area coordinates are approximate. Demo password for every account: Demo@1234
-- ============================================================================

INSERT INTO areas (id, name, city, district, ward_code, latitude, longitude, radius_km) VALUES
 (1, 'Arera Colony',       'Bhopal', 'Bhopal', 'BPL-W01', 23.213600, 77.435000, 1.50),
 (2, 'MP Nagar',           'Bhopal', 'Bhopal', 'BPL-W02', 23.233000, 77.434000, 1.50),
 (3, 'New Market',         'Bhopal', 'Bhopal', 'BPL-W03', 23.232500, 77.401000, 1.20),
 (4, 'Kolar Road',         'Bhopal', 'Bhopal', 'BPL-W04', 23.182000, 77.418000, 2.00),
 (5, 'Shahpura',           'Bhopal', 'Bhopal', 'BPL-W05', 23.196000, 77.435000, 1.50),
 (6, 'Bairagarh',          'Bhopal', 'Bhopal', 'BPL-W06', 23.279000, 77.338000, 2.00),
 (7, 'Hoshangabad Road',   'Bhopal', 'Bhopal', 'BPL-W07', 23.165000, 77.460000, 2.00);

-- Admin / linemen / residents (password: Demo@1234)
INSERT INTO users (id, full_name, email, phone, password_hash, role, preferred_language, area_id, is_sample) VALUES
 (1, 'Demo Admin',      'admin@urjasense.demo',   '9000000001', 'pbkdf2:sha256:260000$5Dn3qaM4suMMtA6a$536b37ec347da8b79b462ba3c0bd98507c908c13e3feea806bc37a7469429cdb', 'admin',   'en', NULL, 1),
 (2, 'Demo Lineman A',  'lineman1@urjasense.demo','9000000002', 'pbkdf2:sha256:260000$5Dn3qaM4suMMtA6a$536b37ec347da8b79b462ba3c0bd98507c908c13e3feea806bc37a7469429cdb', 'lineman', 'hi', 1, 1),
 (3, 'Demo Lineman B',  'lineman2@urjasense.demo','9000000003', 'pbkdf2:sha256:260000$5Dn3qaM4suMMtA6a$536b37ec347da8b79b462ba3c0bd98507c908c13e3feea806bc37a7469429cdb', 'lineman', 'en', 4, 1),
 (4, 'Demo Resident 1', 'resident1@urjasense.demo','9000000004','pbkdf2:sha256:260000$5Dn3qaM4suMMtA6a$536b37ec347da8b79b462ba3c0bd98507c908c13e3feea806bc37a7469429cdb', 'public',  'en', 1, 1),
 (5, 'Demo Resident 2', 'resident2@urjasense.demo','9000000005','pbkdf2:sha256:260000$5Dn3qaM4suMMtA6a$536b37ec347da8b79b462ba3c0bd98507c908c13e3feea806bc37a7469429cdb', 'public',  'hi', 1, 1),
 (6, 'Demo Resident 3', 'resident3@urjasense.demo','9000000006','pbkdf2:sha256:260000$5Dn3qaM4suMMtA6a$536b37ec347da8b79b462ba3c0bd98507c908c13e3feea806bc37a7469429cdb', 'public',  'en', 2, 1),
 (7, 'Demo Resident 4', 'resident4@urjasense.demo','9000000007','pbkdf2:sha256:260000$5Dn3qaM4suMMtA6a$536b37ec347da8b79b462ba3c0bd98507c908c13e3feea806bc37a7469429cdb', 'public',  'en', 4, 1);

INSERT INTO linemen (id, user_id, employee_code, designation, area_id, approval_status, approved_by) VALUES
 (1, 2, 'SAMPLE-EMP-001', 'Lineman', 1, 'APPROVED', 1),
 (2, 3, 'SAMPLE-EMP-002', 'Senior Lineman', 4, 'APPROVED', 1);

-- One SAMPLE resolved incident (so rating / history screens have something to show)
INSERT INTO outage_incidents (id, incident_code, area_id, location_text, latitude, longitude, suggested_category, official_cause, status, priority, affected_count, outage_start_time, predicted_minutes, repair_progress_pct, resolved_at, is_sample, created_at, updated_at) VALUES
 (1, 'INC-20261120-0001', 2, 'Near MP Nagar Zone 1 (sample)', 23.233000, 77.434000, 'line_fault', 'Cable joint replaced (sample record)', 'RESOLVED', 'MEDIUM', 2, '2026-11-20 18:10:00', 95, 100, '2026-11-20 19:45:00', 1, '2026-11-20 18:15:00', '2026-11-20 19:45:00');

INSERT INTO outage_reports (id, report_code, user_id, incident_id, area_id, location_text, latitude, longitude, outage_start_time, issue_details, suggested_category, matched_existing, match_score, created_at) VALUES
 (1, 'RPT-20261120-0001', 6, 1, 2, 'Near MP Nagar Zone 1 (sample)', 23.233000, 77.434000, '2026-11-20 18:10:00', 'Light gone since evening (sample)', 'unknown', 0, NULL, '2026-11-20 18:15:00');

INSERT INTO incident_updates (incident_id, previous_status, new_status, updated_by, remarks, created_at) VALUES
 (1, NULL,                 'REPORTED',           6, 'Incident created from first resident report (sample).', '2026-11-20 18:15:00'),
 (1, 'REPORTED',           'VERIFIED',           1, 'Verified by admin (sample).',                          '2026-11-20 18:30:00'),
 (1, 'VERIFIED',           'ASSIGNED',           1, 'Assigned to a field lineman (sample).',                 '2026-11-20 18:35:00'),
 (1, 'ASSIGNED',           'REPAIR_IN_PROGRESS', 2, 'Crew on site (sample).',                               '2026-11-20 19:00:00'),
 (1, 'REPAIR_IN_PROGRESS', 'RESOLVED',           2, 'Power restored (sample).',                             '2026-11-20 19:45:00');

INSERT INTO assignments (incident_id, lineman_id, assigned_by, is_active, assigned_at) VALUES
 (1, 1, 1, 1, '2026-11-20 18:35:00');

INSERT INTO notifications (user_id, incident_id, title, message, title_hi, message_hi, is_read, created_at) VALUES
 (6, 1, 'Power restored', 'Incident INC-20261120-0001 has been resolved (sample data).', 'बिजली बहाल', 'घटना INC-20261120-0001 का समाधान हो गया है (नमूना डेटा)।', 0, '2026-11-20 19:45:00');
