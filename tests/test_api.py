from datetime import timedelta

from sqlalchemy import text

from conftest import login, report_payload
from backend.utils.timeutil import now_local


# ---------- auth ----------
def test_register_and_login(client):
    r = client.post("/api/auth/register", json={"full_name": "Asha Verma", "email": "asha@example.com",
                                                "password": "Secret123", "preferred_language": "hi"})
    assert r.status_code == 201 and r.get_json()["user"]["role"] == "public"
    assert client.post("/api/auth/login", json={"email": "asha@example.com", "password": "Secret123"}).status_code == 200
    assert client.post("/api/auth/login", json={"email": "asha@example.com", "password": "wrong"}).status_code == 401


def test_register_validation_and_duplicates(client):
    bad = client.post("/api/auth/register", json={"full_name": "A", "email": "nope", "password": "x"})
    assert bad.status_code == 400
    ok = {"full_name": "Ravi Kumar", "email": "ravi@example.com", "password": "Secret123"}
    assert client.post("/api/auth/register", json=ok).status_code == 201
    assert client.post("/api/auth/register", json=ok).status_code == 409


def test_cannot_self_register_as_lineman_or_admin(client):
    for role in ("lineman", "admin"):
        r = client.post("/api/auth/register", json={"full_name": "Eve Evil", "email": f"{role}@x.com",
                                                    "password": "Secret123", "role": role})
        assert r.status_code == 400


def test_passwords_are_hashed(app):
    with app.engine.connect() as c:
        h = c.execute(text("SELECT password_hash FROM users WHERE id=1")).scalar()
    assert h.startswith("pbkdf2:") and "Demo@1234" not in h


# ---------- RBAC ----------
def test_role_based_access(client, admin, lineman, resident):
    assert client.get("/api/admin/overview").status_code == 401
    assert client.get("/api/admin/overview", headers=resident).status_code == 403
    assert client.get("/api/admin/overview", headers=lineman).status_code == 403
    assert client.get("/api/lineman/incidents", headers=resident).status_code == 403
    assert client.get("/api/lineman/incidents", headers=admin).status_code == 403
    assert client.get("/api/user/reports", headers=admin).status_code == 403
    assert client.get("/api/admin/overview", headers=admin).status_code == 200
    assert client.get("/api/lineman/incidents", headers=lineman).status_code == 200
    assert client.get("/api/user/reports", headers=resident).status_code == 200


def test_invalid_token_rejected(client):
    r = client.get("/api/user/reports", headers={"Authorization": "Bearer abc.def.ghi"})
    assert r.status_code == 401


def test_unapproved_lineman_cannot_login(client, admin):
    r = client.post("/api/admin/linemen", headers=admin, json={
        "full_name": "New Lineman", "email": "newlm@x.com", "password": "Secret123", "employee_code": "EMP-900"})
    assert r.status_code == 201
    lid = r.get_json()["id"]
    client.post(f"/api/admin/linemen/{lid}/approval", headers=admin, json={"approval_status": "SUSPENDED"})
    r = client.post("/api/auth/login", json={"email": "newlm@x.com", "password": "Secret123"})
    assert r.status_code == 403


# ---------- reporting + duplicate detection ----------
def test_report_creates_incident(client, app, resident):
    r = client.post("/api/user/reports", headers=resident, json=report_payload(app))
    assert r.status_code == 201
    j = r.get_json()
    assert j["report_code"].startswith("RPT-") and j["incident"]["incident_code"].startswith("INC-")
    assert j["linked_to_existing"] is False and j["incident"]["affected_count"] == 1
    assert j["prediction"]["is_estimate"] is True
    assert j["incident"]["category_is_verified"] is False


def test_duplicate_reports_link_to_same_incident(client, app, resident, resident2):
    a = client.post("/api/user/reports", headers=resident, json=report_payload(app)).get_json()
    b = client.post("/api/user/reports", headers=resident2,
                    json=report_payload(app, location_text="Near Arera Colony market", latitude=23.2140, longitude=77.4355,
                                        issue_details="light gone, transformer noise"))
    assert b.status_code == 200
    b = b.get_json()
    assert b["linked_to_existing"] is True
    assert b["incident"]["incident_code"] == a["incident"]["incident_code"]
    assert b["incident"]["affected_count"] == 2
    assert b["report_code"] != a["report_code"]             # individual report preserved
    with app.engine.connect() as c:
        assert c.execute(text("SELECT COUNT(*) FROM outage_incidents WHERE incident_code=:c"),
                         {"c": a["incident"]["incident_code"]}).scalar() == 1
        assert c.execute(text("SELECT COUNT(*) FROM outage_reports WHERE incident_id=:i"),
                         {"i": a["incident"]["id"]}).scalar() == 2


def test_same_user_re_reporting_is_not_double_counted(client, app, resident):
    first = client.post("/api/user/reports", headers=resident, json=report_payload(app)).get_json()
    again = client.post("/api/user/reports", headers=resident, json=report_payload(app)).get_json()
    assert again["already_reported"] is True
    assert again["report_code"] == first["report_code"]
    assert again["incident"]["affected_count"] == 1


def test_far_location_or_other_area_creates_new_incident(client, app, resident, resident2):
    a = client.post("/api/user/reports", headers=resident, json=report_payload(app)).get_json()
    far = client.post("/api/user/reports", headers=resident2,
                      json=report_payload(app, latitude=23.2400, longitude=77.4800))   # > radius away, same area
    assert far.get_json()["incident"]["incident_code"] != a["incident"]["incident_code"]
    other = client.post("/api/user/reports", headers=resident2,
                        json=report_payload(app, area_id=3, latitude=None, longitude=None))
    assert other.get_json()["linked_to_existing"] is False


def test_old_start_time_does_not_match(client, app, resident, resident2):
    a = client.post("/api/user/reports", headers=resident, json=report_payload(app, latitude=None, longitude=None)).get_json()
    old = (now_local(330) - timedelta(hours=10)).strftime("%Y-%m-%dT%H:%M")
    b = client.post("/api/user/reports", headers=resident2,
                    json=report_payload(app, outage_start_time=old, latitude=None, longitude=None, issue_details="no power"))
    assert b.get_json()["incident"]["incident_code"] != a["incident"]["incident_code"]


def test_report_validation(client, app, resident):
    assert client.post("/api/user/reports", headers=resident, json=report_payload(app, area_id=999)).status_code == 404
    future = (now_local(330) + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M")
    assert client.post("/api/user/reports", headers=resident,
                       json=report_payload(app, outage_start_time=future)).status_code == 400
    assert client.post("/api/user/reports", headers=resident, json=report_payload(app, latitude=999, longitude=1)).status_code == 400
    assert client.post("/api/user/reports", headers=resident, json={"area_id": 1}).status_code == 400
    assert client.post("/api/user/reports", json=report_payload(app)).status_code == 401


def test_sql_injection_is_inert(client, app, resident):
    evil = "x'); DROP TABLE users;--"
    r = client.post("/api/user/reports", headers=resident, json=report_payload(app, location_text=evil, issue_details=evil))
    assert r.status_code in (200, 201)
    assert client.get("/api/admin/overview").status_code == 401   # tables still exist (no 500)
    assert client.post("/api/auth/login", json={"email": "' OR 1=1 --", "password": "x"}).status_code == 401


def test_per_user_hourly_report_cap(app, client, resident):
    app.config["MAX_REPORTS_PER_USER_PER_HOUR"] = 2
    for a in (1, 2):
        assert client.post("/api/user/reports", headers=resident,
                           json=report_payload(app, area_id=a, latitude=None, longitude=None)).status_code in (200, 201)
    assert client.post("/api/user/reports", headers=resident,
                       json=report_payload(app, area_id=3, latitude=None, longitude=None)).status_code == 429


def test_rate_limiting_on_login(app, client):
    app.config["RATE_LIMIT_ENABLED"] = True
    codes = [client.post("/api/auth/login", json={"email": "a@b.co", "password": "x"}).status_code for _ in range(12)]
    assert 429 in codes


# ---------- workflow ----------
def _new_incident(client, app, resident):
    return client.post("/api/user/reports", headers=resident, json=report_payload(app)).get_json()["incident"]


def test_full_incident_lifecycle(client, app, resident, admin, lineman):
    inc = _new_incident(client, app, resident)
    iid = inc["id"]
    # lineman cannot touch unassigned incident
    assert client.post(f"/api/lineman/incidents/{iid}/status", headers=lineman,
                       json={"status": "REPAIR_IN_PROGRESS"}).status_code == 400
    # skipping steps is rejected
    assert client.post(f"/api/admin/incidents/{iid}/status", headers=admin, json={"status": "RESOLVED"}).status_code == 400
    assert client.post(f"/api/admin/incidents/{iid}/verify", headers=admin, json={}).status_code == 200
    a = client.post(f"/api/admin/incidents/{iid}/assign", headers=admin, json={"lineman_id": 1})
    assert a.status_code == 200 and a.get_json()["incident"]["status"] == "ASSIGNED"
    assert client.get(f"/api/lineman/incidents/{iid}", headers=lineman).status_code == 200
    # progress update: verified cause + ETA
    eta = (now_local(330) + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
    p = client.post(f"/api/lineman/incidents/{iid}/progress", headers=lineman, json={
        "official_cause": "Transformer fuse replaced", "verified_category": "transformer_fault",
        "lineman_eta_at": eta, "repair_progress_pct": 40, "remarks": "Crew on site"})
    assert p.status_code == 200
    pi = p.get_json()["incident"]
    assert pi["official_cause"] == "Transformer fuse replaced" and pi["category_is_verified"] is True
    assert client.post(f"/api/lineman/incidents/{iid}/status", headers=lineman, json={"status": "REPAIR_IN_PROGRESS"}).status_code == 200
    assert client.post(f"/api/lineman/incidents/{iid}/status", headers=lineman,
                       json={"status": "RESOLVED", "remarks": "Power restored"}).status_code == 200
    # history stored with prev/new/by/time/remarks
    with app.engine.connect() as c:
        ups = c.execute(text("SELECT previous_status, new_status, updated_by, created_at, remarks "
                             "FROM incident_updates WHERE incident_id=:i ORDER BY id"), {"i": iid}).all()
    flow = [u[1] for u in ups if u[0] != u[1]]
    assert flow == ["REPORTED", "VERIFIED", "ASSIGNED", "REPAIR_IN_PROGRESS", "RESOLVED"]
    assert all(u[2] is not None and u[3] for u in ups)
    # resident sees latest status
    t = client.get(f"/api/user/incidents/{iid}", headers=resident).get_json()
    assert t["incident"]["status"] == "RESOLVED" and t["incident"]["resolved_at"]


def test_lineman_cannot_work_on_other_linemans_incident(client, app, resident, admin, lineman):
    iid = _new_incident(client, app, resident)["id"]
    client.post(f"/api/admin/incidents/{iid}/assign", headers=admin, json={"lineman_id": 2})   # lineman B
    r = client.post(f"/api/lineman/incidents/{iid}/progress", headers=lineman, json={"remarks": "hi"})
    assert r.status_code == 403


def test_reassignment_keeps_one_active_assignment(client, app, resident, admin):
    iid = _new_incident(client, app, resident)["id"]
    client.post(f"/api/admin/incidents/{iid}/assign", headers=admin, json={"lineman_id": 1})
    client.post(f"/api/admin/incidents/{iid}/assign", headers=admin, json={"lineman_id": 2})
    with app.engine.connect() as c:
        assert c.execute(text("SELECT COUNT(*) FROM assignments WHERE incident_id=:i AND is_active=1"), {"i": iid}).scalar() == 1


def test_assign_unknown_lineman(client, app, resident, admin):
    iid = _new_incident(client, app, resident)["id"]
    assert client.post(f"/api/admin/incidents/{iid}/assign", headers=admin, json={"lineman_id": 999}).status_code == 404


# ---------- notifications / feedback ----------
def test_notifications_and_feedback(client, app, resident, admin, lineman):
    iid = _new_incident(client, app, resident)["id"]
    client.post(f"/api/admin/incidents/{iid}/assign", headers=admin, json={"lineman_id": 1})
    client.post(f"/api/lineman/incidents/{iid}/status", headers=lineman, json={"status": "REPAIR_IN_PROGRESS"})
    # cannot rate before resolution
    assert client.post("/api/user/ratings", headers=resident, json={"incident_id": iid, "rating": 5}).status_code == 400
    client.post(f"/api/lineman/incidents/{iid}/status", headers=lineman, json={"status": "RESOLVED"})
    notes = client.get("/api/user/notifications", headers=resident).get_json()["notifications"]
    assert len(notes) >= 4 and any("Resolved" in n["title"] for n in notes)
    assert all(n["title_hi"] for n in notes)                      # Hindi text stored
    ov = client.get("/api/user/overview", headers=resident).get_json()
    assert ov["unread_notifications"] >= 4
    client.post("/api/user/notifications/read-all", headers=resident)
    assert client.get("/api/user/overview", headers=resident).get_json()["unread_notifications"] == 0
    # rating
    assert client.get("/api/user/rateable", headers=resident).get_json()["incidents"]
    assert client.post("/api/user/ratings", headers=resident, json={"incident_id": iid, "rating": 9}).status_code == 400
    assert client.post("/api/user/ratings", headers=resident,
                       json={"incident_id": iid, "rating": 4, "feedback": "Quick fix"}).status_code == 201
    assert client.post("/api/user/ratings", headers=resident, json={"incident_id": iid, "rating": 4}).status_code == 409
    fb = client.get("/api/admin/feedback", headers=admin).get_json()
    assert fb["average"] is not None and fb["feedback"][0]["rating"] == 4


def test_only_reporter_can_rate(client, app, resident, resident2, admin, lineman):
    iid = _new_incident(client, app, resident)["id"]
    client.post(f"/api/admin/incidents/{iid}/assign", headers=admin, json={"lineman_id": 1})
    client.post(f"/api/lineman/incidents/{iid}/status", headers=lineman, json={"status": "REPAIR_IN_PROGRESS"})
    client.post(f"/api/lineman/incidents/{iid}/status", headers=lineman, json={"status": "RESOLVED"})
    assert client.post("/api/user/ratings", headers=resident2, json={"incident_id": iid, "rating": 1}).status_code == 403


def test_user_cannot_read_other_users_notifications(client, app, resident, resident2):
    _new_incident(client, app, resident)
    assert client.get("/api/user/notifications", headers=resident2).get_json()["notifications"] == []
    nid = client.get("/api/user/notifications", headers=resident).get_json()["notifications"][0]["id"]
    assert client.post(f"/api/user/notifications/{nid}/read", headers=resident2).get_json()["updated"] == 0


# ---------- public / map / tracking ----------
def test_public_endpoints_hide_personal_data(client, app, resident):
    inc = _new_incident(client, app, resident)
    act = client.get("/api/incidents/active").get_json()["incidents"]
    assert any(i["incident_code"] == inc["incident_code"] for i in act)
    assert "Demo Resident" not in str(act)
    t = client.get("/api/incidents/track", query_string={"code": inc["incident_code"]})
    assert t.status_code == 200 and t.get_json()["incident"]["status"] == "REPORTED"
    assert client.get("/api/incidents/track", query_string={"code": "INC-NOPE"}).status_code == 404
    assert len(client.get("/api/areas").get_json()["areas"]) >= 7


# ---------- admin ----------
def test_admin_dashboard_endpoints(client, app, resident, admin):
    _new_incident(client, app, resident)
    ov = client.get("/api/admin/overview", headers=admin).get_json()
    assert ov["stats"]["active_outages"] >= 1 and ov["stats"]["total_users"] >= 1
    for ep in ("users", "linemen", "areas", "incidents", "reports", "feedback", "logs", "notifications"):
        assert client.get(f"/api/admin/{ep}", headers=admin).status_code == 200, ep
    assert client.get("/api/admin/reports.csv", headers=admin).mimetype == "text/csv"
    logs = client.get("/api/admin/logs", headers=admin).get_json()["logs"]
    assert any(l["action"] == "REPORT_SUBMITTED" for l in logs)


def test_admin_area_management(client, admin):
    new = {"name": "Test Nagar", "city": "Bhopal", "district": "Bhopal", "ward_code": "BPL-W99",
           "latitude": 23.2, "longitude": 77.4, "radius_km": 1.0}
    r = client.post("/api/admin/areas", headers=admin, json=new)
    assert r.status_code == 201
    assert client.post("/api/admin/areas", headers=admin, json=new).status_code == 409
    assert client.put(f"/api/admin/areas/{r.get_json()['id']}", headers=admin, json={**new, "name": "Test Nagar 2"}).status_code == 200
    assert client.post("/api/admin/areas", headers=admin, json={**new, "ward_code": "X1", "latitude": 500}).status_code == 400


def test_admin_broadcast_and_deactivate(client, admin):
    r = client.post("/api/admin/notifications/broadcast", headers=admin,
                    json={"title": "Planned shutdown", "message": "Maintenance 10-12 Sunday", "area_id": 1})
    assert r.get_json()["sent"] >= 2
    assert client.post("/api/admin/users/4/active", headers=admin, json={"is_active": False}).status_code == 200
    assert client.post("/api/auth/login", json={"email": "resident1@urjasense.demo", "password": "Demo@1234"}).status_code == 401
    assert client.post("/api/admin/users/1/active", headers=admin, json={"is_active": False}).status_code == 400


def test_deactivated_user_token_stops_working(client, admin, resident):
    client.post("/api/admin/users/4/active", headers=admin, json={"is_active": False})
    assert client.get("/api/user/reports", headers=resident).status_code == 403


# ---------- AI ----------
def test_analytics_pattern_analysis(client, admin):
    a = client.get("/api/admin/analytics", headers=admin).get_json()
    assert a["n_records"] > 1000 and a["frequent_areas"] and a["peak_hours"]
    assert "SIMULATED" in a["data_notice"]
    assert any(x["area"] == "Bairagarh" for x in a["anomalies"])      # injected abnormal day detected
    assert a["model"]["data_source"] == "SIMULATED_SAMPLE"


def test_prediction_is_labelled_estimate_and_sensible():
    from datetime import datetime
    from ai_ml.prediction import predict_restoration
    quick = predict_restoration(3, "local_fault", 2, datetime(2026, 11, 22, 14), 0)
    slow = predict_restoration(6, "transformer_fault", 40, datetime(2026, 11, 22, 14), 0)
    nearly = predict_restoration(6, "transformer_fault", 40, datetime(2026, 11, 22, 14), 75)
    assert quick["is_estimate"] and "not an official" in quick["disclaimer_en"].lower()
    assert quick["remaining_minutes"] < slow["remaining_minutes"]
    assert nearly["remaining_minutes"] < slow["remaining_minutes"]       # repair progress lowers estimate
    assert quick["range_minutes"][0] <= quick["remaining_minutes"] <= quick["range_minutes"][1]


def test_categorizer_never_claims_verified():
    from ai_ml.categorizer import suggest_category
    r = suggest_category("तेज आंधी में पेड़ गिर गया")
    assert r["category"] == "weather_related" and r["verified"] is False
    assert suggest_category("")["category"] == "unknown"


# ---------- database relationships ----------
def test_foreign_keys_enforced(app):
    import pytest
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        with app.engine.begin() as c:
            c.execute(text("INSERT INTO outage_reports (report_code, user_id, incident_id, area_id, location_text, "
                           "outage_start_time) VALUES ('X1', 999, 999, 1, 'loc', '2026-11-22 10:00:00')"))
    with pytest.raises(IntegrityError):
        with app.engine.begin() as c:
            c.execute(text("INSERT INTO ratings (incident_id, user_id, rating) VALUES (1, 6, 7)"))   # CHECK 1..5


def test_security_headers_and_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.headers["X-Content-Type-Options"] == "nosniff"
