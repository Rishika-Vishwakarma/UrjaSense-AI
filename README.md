# UrjaSense AI — *Report Smartly. Restore Faster. Stay Informed.*
**Team SparkX** · AI-powered electricity outage reporting, tracking and management (hackathon prototype)

Residents report outages, the system **groups duplicate reports into one incident**, linemen update verified causes and
restoration times, and admins monitor everything. Three role-based dashboards, English + Hindi, MySQL, Flask, scikit-learn.

## Honesty notes (please read before demoing)
- **Sample data:** demo accounts, 1 demo incident and the 3,018-row historical dataset are **SIMULATED** (`is_sample=1`, `data_source=SIMULATED_SAMPLE`). They are not electricity-department records, and the UI says so.
- **Predictions are estimates.** The restoration model is trained on the simulated CSV; its error figures (MAE ≈ 24 min) describe the *simulation*, not real-world accuracy. A lineman's confirmed ETA always takes priority in the UI. To use real data, replace `ai_ml/data/sample_historical_outages.csv` (same columns) and run `python -m ai_ml.training`.
- **Categories are suggestions.** The keyword categoriser never claims a verified cause; only linemen/admins can set `verified_category` / `official_cause`.
- **AWS:** configuration only (`aws/`). Nothing is deployed to or tested against a live AWS account. SNS is off unless `SNS_ENABLED=1`.
- **MySQL:** `database/schema.sql` targets MySQL 8. The automated tests and the zero-setup demo run the same schema on SQLite (auto-translated); I did not have a MySQL server in my build environment, so run it once against MySQL before relying on it.

## Quick start (local)
```bash
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                     # set SECRET_KEY (32+ random chars)
python -m ai_ml.training                                 # trains the restoration model (auto-runs if missing)
python -m database.database_config                       # creates tables + sample data (SQLite by default)
python -m backend.app                                    # open http://localhost:5000
```
**MySQL:** create a user/database, set `DATABASE_URL=mysql+pymysql://user:pass@localhost:3306/urjasense?charset=utf8mb4` in `.env`, rerun `python -m database.database_config`.
Production: `gunicorn "backend.app:create_app()"` behind HTTPS, `FORCE_HTTPS=1`, restricted `CORS_ORIGINS`.

**Demo logins** (password `Demo@1234`, sample data): `resident1@urjasense.demo`, `resident2@urjasense.demo` (Hindi), `lineman1@urjasense.demo`, `lineman2@urjasense.demo`, `admin@urjasense.demo`.

### 3-minute demo script
1. Log in as **resident1** → *Report Power Outage* (Arera Colony, "transformer sparking") → new incident + report ID + estimate.
2. Log in as **resident2** (Hindi UI) → report the same outage → *"linked to existing incident"*, affected count 2, own report ID kept.
3. **Admin** → *Assignments* → assign to Lineman A (auto-verifies). *Analytics* shows frequent areas, peak hours, anomaly (Bairagarh spike), model info + data notice.
4. **Lineman A** → *Update Restoration Time* (cause, ETA, progress) → *Update Status* → Repair in progress → Resolved.
5. **Resident** → notifications (EN/HI), tracker timeline, then *Ratings and Feedback*. **Admin** → Feedback, System Logs.

## Tests
```bash
python -m pytest tests -q          # 33 API/logic/DB tests
BASE=http://localhost:5000 python tests/e2e_smoke.py          # optional browser flow (needs playwright + Chrome)
BASE=http://localhost:5000 python tests/responsive_smoke.py   # every dashboard view, desktop + 390px mobile, console errors, overflow
```
Covered: registration/login, RBAC for all 3 roles, outage reporting, duplicate detection (match / no-match by place and time / same-user re-report), assignment & reassignment, full status workflow + history rows, notifications (EN/HI), ratings, rate limits, SQL-injection inertness, FK/CHECK constraints, prediction behaviour, pattern/anomaly analysis, API responses. Screenshots (desktop + mobile): `reports/screenshots/`.

## Architecture
`frontend/` (HTML/CSS/vanilla JS, Chart.js + Leaflet vendored in `vendor/` so charts work offline; map *tiles* need internet) →
`backend/` Flask REST (`routes/` HTTP + RBAC, `services/` business logic, `models/` enums, `utils/` auth/validation/rate-limit) →
`database/` (schema.sql, sample_data.sql, config) · `ai_ml/` · `aws/`. Diagrams: `reports/diagrams/architecture.md`.
(There is no separate `controllers/` folder: route functions are thin and call `services/`.)

**Duplicate detection** (`backend/services/duplicate_service.py`): compares a new report with open incidents in the same area. Score = proximity (0.5; GPS distance if both have coordinates, otherwise same-area 0.35) + start-time closeness (0.3; ≤60 min full, ≤180 min partial) + issue category (0.2). Score ≥ 0.55 links the report. Individual reports are always stored; affected count = distinct residents; one resident can't inflate the count; a per-user hourly cap and per-IP limits stop spam.

## Implementation status vs. the brief
| Area | Status |
|---|---|
| Resident: register/login, report (area, location, time, details, optional GPS), report ID, track by code, status + ETA, notifications, map, my reports, history, ratings, profile + language | ✅ working |
| Lineman: secure login, assigned incidents, location/affected/priority, status updates, verified cause, ETA, progress notes, resolve, repair history | ✅ working |
| Lineman accounts only created/approved by admin; public registration is resident-only | ✅ enforced server-side |
| Admin: users, linemen, areas, incidents, assignments, area stats, complaint reports (+CSV), avg restoration, feedback, broadcast notifications, audit logs | ✅ working |
| Workflow REPORTED→VERIFIED→ASSIGNED→REPAIR_IN_PROGRESS→RESOLVED with history (prev/new/by/time/remarks) | ✅ working, sequential only |
| AI: restoration prediction, pattern/anomaly analysis, categorisation | ✅ working on **simulated** data (labelled) |
| i18n English + Hindi (nav, key labels, statuses, notifications); add languages in `frontend/js/i18n.js` | ✅ partial translation: untranslated strings fall back to English |
| Security: PBKDF2 hashing, JWT, RBAC re-checked in DB each request, parameterised SQL, validation, rate limiting, audit log, security headers, HTTPS-ready | ✅ implemented |
| In-app notifications | ✅ working · SMS/email via SNS: ⚙️ code present, off by default |
| AWS (API Gateway, Lambda, RDS, SNS, S3, CloudWatch) | 📄 SAM template (cfn-lint clean) + Lambda handlers + guide; **not deployed** |
| Not built | Password reset by email, map marker clustering, admin editing of user roles, real SMS provider, automated retraining schedule |

## Known limitations
- Rate limiter is in-memory (single process); use API Gateway throttling / Redis in production.
- Priority/duplicate thresholds are heuristics tuned on sample data; calibrate with real incidents (`DUP_*` env vars).
- Admins/linemen see resident names in reports; consider a privacy policy before real use.
