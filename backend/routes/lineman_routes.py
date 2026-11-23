"""Lineman (authorised electricity department employee) endpoints."""
from flask import Blueprint, current_app, g
from sqlalchemy import text

from backend.models.enums import STATUSES
from backend.services import incident_service as svc
from backend.services.common import one, rows
from backend.utils.api import body, ok
from backend.utils.auth import login_required
from backend.utils.timeutil import parse_dt
from backend.utils.validation import ValidationError, require_int, require_str
from ai_ml.preprocessing.features import CATEGORIES

bp = Blueprint("lineman", __name__, url_prefix="/api/lineman")
L = "lineman"


def _my_lineman(conn):
    lm = one(conn, "SELECT l.*, u.full_name, u.email, u.phone, a.name AS area_name FROM linemen l "
                   "JOIN users u ON u.id=l.user_id LEFT JOIN areas a ON a.id=l.area_id WHERE l.user_id=:u",
             {"u": g.user["id"]})
    return lm


@bp.get("/profile")
@login_required(L)
def profile():
    with current_app.engine.connect() as c:
        return ok(profile=_my_lineman(c))


@bp.get("/overview")
@login_required(L)
def overview():
    with current_app.engine.connect() as c:
        lm = _my_lineman(c)
        s = one(c, "SELECT SUM(CASE WHEN i.status<>'RESOLVED' THEN 1 ELSE 0 END) AS active, "
                   "SUM(CASE WHEN i.status='RESOLVED' THEN 1 ELSE 0 END) AS resolved, "
                   "SUM(CASE WHEN i.status<>'RESOLVED' THEN i.affected_count ELSE 0 END) AS residents, "
                   "SUM(CASE WHEN i.status<>'RESOLVED' AND i.priority IN ('HIGH','CRITICAL') THEN 1 ELSE 0 END) AS urgent "
                   "FROM assignments s JOIN outage_incidents i ON i.id=s.incident_id "
                   "WHERE s.lineman_id=:l AND s.is_active=1", {"l": lm["id"]})
    return ok(active=int(s["active"] or 0), resolved=int(s["resolved"] or 0),
              residents_affected=int(s["residents"] or 0), urgent=int(s["urgent"] or 0))


@bp.get("/incidents")
@login_required(L)
def assigned():
    with current_app.engine.connect() as c:
        lm = _my_lineman(c)
        data = rows(c, svc.INCIDENT_SELECT + "WHERE i.id IN (SELECT incident_id FROM assignments "
                    "WHERE lineman_id=:l AND is_active=1) ORDER BY CASE i.status WHEN 'RESOLVED' THEN 1 ELSE 0 END, "
                    "CASE i.priority WHEN 'CRITICAL' THEN 0 WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END, "
                    "i.outage_start_time", {"l": lm["id"]})
    return ok(incidents=data)


@bp.get("/incidents/<int:incident_id>")
@login_required(L)
def detail(incident_id):
    with current_app.engine.connect() as c:
        lm = _my_lineman(c)
        if not c.execute(text("SELECT 1 FROM assignments WHERE incident_id=:i AND lineman_id=:l AND is_active=1"),
                         {"i": incident_id, "l": lm["id"]}).first():
            return ok(error="This incident is not assigned to you"), 403
        inc = svc.get_incident(c, incident_id)
        reports = rows(c, "SELECT report_code, location_text, issue_details, outage_start_time, matched_existing "
                          "FROM outage_reports WHERE incident_id=:i ORDER BY id", {"i": incident_id})
        updates = svc.get_updates(c, incident_id)
    return ok(incident=inc, reports=reports, updates=updates, categories=CATEGORIES)


@bp.post("/incidents/<int:incident_id>/status")
@login_required(L)
def status(incident_id):
    d = body()
    new = require_str(d, "status", 1, 30)
    if new not in STATUSES:
        raise ValidationError("Unknown status", "status")
    inc = svc.change_status(current_app.engine, g.user, incident_id, new, require_str(d, "remarks", 0, 1000, required=False))
    return ok(incident=inc)


@bp.post("/incidents/<int:incident_id>/progress")
@login_required(L)
def progress(incident_id):
    """Verified cause, restoration ETA, progress %, repair note (any subset)."""
    d = body()
    cause = require_str(d, "official_cause", 0, 255, required=False)
    cat = d.get("verified_category") or None
    if cat and cat not in CATEGORIES:
        raise ValidationError("Unknown category", "verified_category")
    eta = None
    if d.get("lineman_eta_at"):
        try:
            eta = parse_dt(str(d["lineman_eta_at"]))
        except ValueError:
            raise ValidationError("lineman_eta_at must look like 2026-11-22T21:30", "lineman_eta_at")
    pct = require_int(d, "repair_progress_pct", 0, 100, required=False)
    inc = svc.lineman_progress_update(current_app.engine, g.user, incident_id, cause, cat, eta, pct,
                                      require_str(d, "remarks", 0, 1000, required=False))
    return ok(incident=inc)


@bp.get("/history")
@login_required(L)
def history():
    with current_app.engine.connect() as c:
        lm = _my_lineman(c)
        data = rows(c,
            "SELECT i.incident_code, a.name AS area_name, i.official_cause, i.affected_count, i.outage_start_time, "
            "i.resolved_at, u.created_at AS update_at, u.new_status, u.remarks "
            "FROM incident_updates u JOIN outage_incidents i ON i.id=u.incident_id JOIN areas a ON a.id=i.area_id "
            "WHERE u.updated_by=:uid ORDER BY u.id DESC LIMIT 100", {"uid": g.user["id"]})
    return ok(history=data)
