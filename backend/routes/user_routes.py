"""Resident (public user) endpoints."""
from flask import Blueprint, current_app, g, request
from sqlalchemy import text

from backend.services import incident_service as svc
from backend.services.common import one, rows
from backend.utils.api import body, ok, page_args
from backend.utils.auth import login_required
from backend.utils.rate_limit import rate_limit
from backend.utils.timeutil import parse_dt
from backend.utils.validation import (ValidationError, optional_coord, require_int, require_str)
from backend.routes.public_routes import public_view
from ai_ml.categorizer import suggest_category

bp = Blueprint("user", __name__, url_prefix="/api/user")
R = "public"


@bp.post("/reports")
@login_required(R)
@rate_limit(10, 600, scope="user")
def create_report():
    d = body()
    area_id = require_int(d, "area_id", 1)
    location = require_str(d, "location_text", 3, 255)
    details = require_str(d, "issue_details", 0, 1000, required=False)
    lat, lng = optional_coord(d)
    try:
        start = parse_dt(require_str(d, "outage_start_time", 8, 30))
    except ValueError:
        raise ValidationError("outage_start_time must look like 2026-11-22T18:30", "outage_start_time")
    result = svc.submit_report(current_app.engine, g.user, area_id, location, lat, lng, start, details)
    result["incident"] = public_view(result["incident"])
    return ok(**result), (200 if result["linked_to_existing"] else 201)


@bp.post("/reports/suggest-category")
@login_required(R)
def suggest():
    """Preview of the automatic category SUGGESTION (never verified)."""
    d = body()
    return ok(**suggest_category(d.get("issue_details")))


@bp.get("/reports")
@login_required(R)
def my_reports():
    limit, offset = page_args()
    with current_app.engine.connect() as c:
        data = rows(c,
            "SELECT r.id, r.report_code, r.location_text, r.outage_start_time, r.issue_details, r.matched_existing, "
            "r.created_at, i.id AS incident_id, i.incident_code, i.status, i.priority, i.affected_count, "
            "i.predicted_restoration_at, i.lineman_eta_at, i.official_cause, a.name AS area_name, "
            "(SELECT rating FROM ratings x WHERE x.incident_id=i.id AND x.user_id=:u) AS my_rating "
            "FROM outage_reports r JOIN outage_incidents i ON i.id=r.incident_id JOIN areas a ON a.id=r.area_id "
            "WHERE r.user_id=:u ORDER BY r.id DESC LIMIT :l OFFSET :o", {"u": g.user["id"], "l": limit, "o": offset})
    return ok(reports=data)


@bp.get("/overview")
@login_required(R)
def overview():
    with current_app.engine.connect() as c:
        mine = one(c, "SELECT COUNT(*) AS total, "
                      "SUM(CASE WHEN i.status<>'RESOLVED' THEN 1 ELSE 0 END) AS active "
                      "FROM outage_reports r JOIN outage_incidents i ON i.id=r.incident_id WHERE r.user_id=:u",
                   {"u": g.user["id"]})
        unread = c.execute(text("SELECT COUNT(*) FROM notifications WHERE user_id=:u AND is_read=0"),
                           {"u": g.user["id"]}).scalar()
        area_active = c.execute(text("SELECT COUNT(*) FROM outage_incidents WHERE status<>'RESOLVED' AND area_id=:a"),
                                {"a": g.user["area_id"] or 0}).scalar()
        city_active = c.execute(text("SELECT COUNT(*) FROM outage_incidents WHERE status<>'RESOLVED'")).scalar()
        recent = rows(c,
            "SELECT u.created_at, u.new_status, u.remarks, i.incident_code, a.name AS area_name "
            "FROM incident_updates u JOIN outage_incidents i ON i.id=u.incident_id JOIN areas a ON a.id=i.area_id "
            "WHERE u.incident_id IN (SELECT incident_id FROM outage_reports WHERE user_id=:u) "
            "ORDER BY u.id DESC LIMIT 6", {"u": g.user["id"]})
    return ok(my_reports=int(mine["total"] or 0), my_active=int(mine["active"] or 0), unread_notifications=int(unread),
              active_in_my_area=int(area_active), active_citywide=int(city_active), recent_updates=recent)


@bp.get("/incidents/<int:incident_id>")
@login_required(R)
def incident_detail(incident_id):
    with current_app.engine.connect() as c:
        inc = svc.get_incident(c, incident_id)
        if not inc:
            return ok(error="Incident not found"), 404
        updates = [{"new_status": u["new_status"], "remarks": u["remarks"], "created_at": u["created_at"]}
                   for u in svc.get_updates(c, incident_id)]
        mine = bool(c.execute(text("SELECT 1 FROM outage_reports WHERE incident_id=:i AND user_id=:u"),
                              {"i": incident_id, "u": g.user["id"]}).first())
    return ok(incident=public_view(inc), updates=updates, reported_by_me=mine)


@bp.get("/history")
@login_required(R)
def history():
    """Resolved incidents: mine first, plus resolved incidents in my area."""
    limit, offset = page_args()
    with current_app.engine.connect() as c:
        data = rows(c,
            "SELECT i.id, i.incident_code, a.name AS area_name, i.outage_start_time, i.resolved_at, i.official_cause, "
            "i.affected_count, "
            "(SELECT COUNT(*) FROM outage_reports r WHERE r.incident_id=i.id AND r.user_id=:u) AS reported_by_me, "
            "(SELECT rating FROM ratings x WHERE x.incident_id=i.id AND x.user_id=:u) AS my_rating "
            "FROM outage_incidents i JOIN areas a ON a.id=i.area_id "
            "WHERE i.status='RESOLVED' AND (i.area_id=:a OR i.id IN (SELECT incident_id FROM outage_reports WHERE user_id=:u)) "
            "ORDER BY i.resolved_at DESC LIMIT :l OFFSET :o",
            {"u": g.user["id"], "a": g.user["area_id"] or 0, "l": limit, "o": offset})
    return ok(history=data)


@bp.get("/notifications")
@login_required(R)
def notifications():
    limit, offset = page_args()
    with current_app.engine.connect() as c:
        data = rows(c, "SELECT id, incident_id, title, message, title_hi, message_hi, is_read, created_at "
                       "FROM notifications WHERE user_id=:u ORDER BY id DESC LIMIT :l OFFSET :o",
                    {"u": g.user["id"], "l": limit, "o": offset})
    return ok(notifications=data)


@bp.post("/notifications/<int:nid>/read")
@login_required(R)
def mark_read(nid):
    with current_app.engine.begin() as c:
        r = c.execute(text("UPDATE notifications SET is_read=1 WHERE id=:n AND user_id=:u"), {"n": nid, "u": g.user["id"]})
    return ok(updated=r.rowcount)


@bp.post("/notifications/read-all")
@login_required(R)
def mark_all_read():
    with current_app.engine.begin() as c:
        r = c.execute(text("UPDATE notifications SET is_read=1 WHERE user_id=:u AND is_read=0"), {"u": g.user["id"]})
    return ok(updated=r.rowcount)


@bp.post("/ratings")
@login_required(R)
@rate_limit(20, 600, scope="user")
def rate():
    d = body()
    rid = svc.submit_rating(current_app.engine, g.user, require_int(d, "incident_id", 1),
                            require_int(d, "rating", 1, 5), require_str(d, "feedback", 0, 1000, required=False))
    return ok(id=rid, message="Thank you for your feedback"), 201


@bp.get("/ratings")
@login_required(R)
def my_ratings():
    with current_app.engine.connect() as c:
        return ok(ratings=rows(c, "SELECT r.id, r.rating, r.feedback, r.created_at, i.incident_code "
                                  "FROM ratings r JOIN outage_incidents i ON i.id=r.incident_id "
                                  "WHERE r.user_id=:u ORDER BY r.id DESC", {"u": g.user["id"]}))


@bp.get("/rateable")
@login_required(R)
def rateable():
    """Resolved incidents I reported but have not rated yet."""
    with current_app.engine.connect() as c:
        return ok(incidents=rows(c,
            "SELECT i.id, i.incident_code, a.name AS area_name, i.resolved_at FROM outage_incidents i "
            "JOIN areas a ON a.id=i.area_id WHERE i.status='RESOLVED' "
            "AND i.id IN (SELECT incident_id FROM outage_reports WHERE user_id=:u) "
            "AND i.id NOT IN (SELECT incident_id FROM ratings WHERE user_id=:u)", {"u": g.user["id"]}))
