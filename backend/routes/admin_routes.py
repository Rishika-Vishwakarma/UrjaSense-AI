"""Administrator endpoints."""
import csv
import io

from flask import Blueprint, Response, current_app, g, request
from sqlalchemy import text
from werkzeug.security import generate_password_hash

from backend.models.enums import PRIORITIES, STATUSES
from backend.routes.auth_routes import PW_METHOD
from backend.services import analytics_service, audit_service, incident_service as svc, notification_service
from backend.services.common import one, rows
from backend.utils.api import body, ok, page_args
from backend.utils.auth import login_required
from backend.utils.validation import (ValidationError, require_int, require_str, validate_email,
                                      validate_password, validate_phone)

bp = Blueprint("admin", __name__, url_prefix="/api/admin")
A = "admin"


@bp.get("/overview")
@login_required(A)
def overview():
    with current_app.engine.connect() as c:
        return ok(stats=analytics_service.overview_stats(c), areas=analytics_service.area_stats(c),
                  status_breakdown=rows(c, "SELECT status, COUNT(*) AS n FROM outage_incidents GROUP BY status"))


# ---------------- users & linemen ----------------
@bp.get("/users")
@login_required(A)
def users():
    limit, offset = page_args()
    role = request.args.get("role")
    where, params = "", {"l": limit, "o": offset}
    if role in ("public", "lineman", "admin"):
        where, params["r"] = "WHERE u.role=:r", role
    with current_app.engine.connect() as c:
        return ok(users=rows(c, "SELECT u.id, u.full_name, u.email, u.phone, u.role, u.is_active, u.is_sample, "
                                "u.created_at, a.name AS area_name FROM users u LEFT JOIN areas a ON a.id=u.area_id "
                                f"{where} ORDER BY u.id DESC LIMIT :l OFFSET :o", params))


@bp.post("/users/<int:uid>/active")
@login_required(A)
def set_active(uid):
    d = body()
    active = 1 if d.get("is_active") else 0
    if uid == g.user["id"] and not active:
        raise ValidationError("You cannot deactivate your own account")
    with current_app.engine.begin() as c:
        r = c.execute(text("UPDATE users SET is_active=:a WHERE id=:i"), {"a": active, "i": uid})
        if not r.rowcount:
            return ok(error="User not found"), 404
        audit_service.log_action(c, g.user["id"], "USER_ACTIVE_SET", "user", uid, f"is_active={active}")
    return ok(message="Updated")


@bp.get("/linemen")
@login_required(A)
def linemen():
    with current_app.engine.connect() as c:
        return ok(linemen=rows(c,
            "SELECT l.id, l.employee_code, l.designation, l.approval_status, u.full_name, u.email, u.phone, u.is_active, "
            "a.name AS area_name, "
            "(SELECT COUNT(*) FROM assignments s JOIN outage_incidents i ON i.id=s.incident_id "
            " WHERE s.lineman_id=l.id AND s.is_active=1 AND i.status<>'RESOLVED') AS open_incidents "
            "FROM linemen l JOIN users u ON u.id=l.user_id LEFT JOIN areas a ON a.id=l.area_id ORDER BY l.id"))


@bp.post("/linemen")
@login_required(A)
def create_lineman():
    """Only administrators can create employee accounts."""
    d = body()
    name = require_str(d, "full_name", 2, 120)
    email = validate_email(require_str(d, "email", 5, 160))
    phone = validate_phone(require_str(d, "phone", 10, 20, required=False))
    pw = validate_password(d.get("password"))
    code = require_str(d, "employee_code", 3, 30)
    area_id = require_int(d, "area_id", 1, required=False)
    with current_app.engine.begin() as c:
        if one(c, "SELECT id FROM users WHERE email=:e", {"e": email}):
            return ok(error="Email already registered"), 409
        if one(c, "SELECT id FROM linemen WHERE employee_code=:c", {"c": code}):
            return ok(error="Employee code already exists"), 409
        uid = c.execute(text("INSERT INTO users (full_name, email, phone, password_hash, role, area_id) "
                             "VALUES (:n,:e,:p,:h,'lineman',:a)"),
                        {"n": name, "e": email, "p": phone, "h": generate_password_hash(pw, method=PW_METHOD),
                         "a": area_id}).lastrowid
        lid = c.execute(text("INSERT INTO linemen (user_id, employee_code, designation, area_id, approval_status, approved_by) "
                             "VALUES (:u,:c,:d,:a,'APPROVED',:ad)"),
                        {"u": uid, "c": code, "d": require_str(d, "designation", 2, 80, required=False) or "Lineman",
                         "a": area_id, "ad": g.user["id"]}).lastrowid
        audit_service.log_action(c, g.user["id"], "LINEMAN_CREATED", "lineman", lid, code)
    return ok(id=lid, user_id=uid), 201


@bp.post("/linemen/<int:lid>/approval")
@login_required(A)
def lineman_approval(lid):
    status = (body().get("approval_status") or "").upper()
    if status not in ("PENDING", "APPROVED", "SUSPENDED"):
        raise ValidationError("approval_status must be PENDING, APPROVED or SUSPENDED")
    with current_app.engine.begin() as c:
        r = c.execute(text("UPDATE linemen SET approval_status=:s, approved_by=:a WHERE id=:i"),
                      {"s": status, "a": g.user["id"], "i": lid})
        if not r.rowcount:
            return ok(error="Lineman not found"), 404
        audit_service.log_action(c, g.user["id"], "LINEMAN_APPROVAL", "lineman", lid, status)
    return ok(message="Updated")


# ---------------- areas ----------------
@bp.get("/areas")
@login_required(A)
def areas():
    with current_app.engine.connect() as c:
        return ok(areas=rows(c, "SELECT * FROM areas ORDER BY name"))


def _area_fields(d):
    try:
        lat, lng = float(d.get("latitude")), float(d.get("longitude"))
    except (TypeError, ValueError):
        raise ValidationError("Valid latitude and longitude are required", "latitude")
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise ValidationError("Valid latitude and longitude are required", "latitude")
    try:
        radius = float(d.get("radius_km", 1.5))
    except (TypeError, ValueError):
        raise ValidationError("radius_km must be a number", "radius_km")
    if not 0.1 <= radius <= 20:
        raise ValidationError("radius_km must be between 0.1 and 20", "radius_km")
    return {"n": require_str(d, "name", 2, 120), "c": require_str(d, "city", 2, 80),
            "d": require_str(d, "district", 2, 80), "w": require_str(d, "ward_code", 2, 20),
            "lat": lat, "lng": lng, "r": radius}


@bp.post("/areas")
@login_required(A)
def create_area():
    f = _area_fields(body())
    with current_app.engine.begin() as c:
        if one(c, "SELECT id FROM areas WHERE ward_code=:w", {"w": f["w"]}):
            return ok(error="Ward code already exists"), 409
        aid = c.execute(text("INSERT INTO areas (name, city, district, ward_code, latitude, longitude, radius_km) "
                             "VALUES (:n,:c,:d,:w,:lat,:lng,:r)"), f).lastrowid
        audit_service.log_action(c, g.user["id"], "AREA_CREATED", "area", aid, f["n"])
    return ok(id=aid), 201


@bp.put("/areas/<int:aid>")
@login_required(A)
def update_area(aid):
    d = body()
    f = _area_fields(d)
    f["i"], f["act"] = aid, 0 if d.get("is_active") is False else 1
    with current_app.engine.begin() as c:
        r = c.execute(text("UPDATE areas SET name=:n, city=:c, district=:d, ward_code=:w, latitude=:lat, "
                           "longitude=:lng, radius_km=:r, is_active=:act WHERE id=:i"), f)
        if not r.rowcount:
            return ok(error="Area not found"), 404
        audit_service.log_action(c, g.user["id"], "AREA_UPDATED", "area", aid, f["n"])
    return ok(message="Updated")


# ---------------- incidents ----------------
@bp.get("/incidents")
@login_required(A)
def incidents():
    limit, offset = page_args()
    where, params = [], {"l": limit, "o": offset}
    st = request.args.get("status")
    if st == "ACTIVE":
        where.append("i.status<>'RESOLVED'")
    elif st in STATUSES:
        where.append("i.status=:st"); params["st"] = st
    if request.args.get("area_id", "").isdigit():
        where.append("i.area_id=:a"); params["a"] = int(request.args["area_id"])
    sql = svc.INCIDENT_SELECT + (("WHERE " + " AND ".join(where)) if where else "") + \
        " ORDER BY CASE i.status WHEN 'RESOLVED' THEN 1 ELSE 0 END, i.id DESC LIMIT :l OFFSET :o"
    with current_app.engine.connect() as c:
        return ok(incidents=rows(c, sql, params))


@bp.get("/incidents/<int:iid>")
@login_required(A)
def incident_detail(iid):
    with current_app.engine.connect() as c:
        inc = svc.get_incident(c, iid)
        if not inc:
            return ok(error="Incident not found"), 404
        return ok(incident=inc, updates=svc.get_updates(c, iid),
                  reports=rows(c, "SELECT r.report_code, r.location_text, r.issue_details, r.matched_existing, "
                                  "r.match_score, r.created_at, u.full_name FROM outage_reports r "
                                  "JOIN users u ON u.id=r.user_id WHERE r.incident_id=:i ORDER BY r.id", {"i": iid}))


@bp.post("/incidents/<int:iid>/verify")
@login_required(A)
def verify(iid):
    inc = svc.change_status(current_app.engine, g.user, iid, "VERIFIED", require_str(body(), "remarks", 0, 1000, required=False)
                            or "Verified by administrator.")
    return ok(incident=inc)


@bp.post("/incidents/<int:iid>/assign")
@login_required(A)
def assign(iid):
    d = body()
    inc = svc.assign_incident(current_app.engine, g.user, iid, require_int(d, "lineman_id", 1),
                              require_str(d, "remarks", 0, 500, required=False))
    return ok(incident=inc)


@bp.post("/incidents/<int:iid>/status")
@login_required(A)
def admin_status(iid):
    d = body()
    new = require_str(d, "status", 1, 30)
    if new not in STATUSES:
        raise ValidationError("Unknown status", "status")
    return ok(incident=svc.change_status(current_app.engine, g.user, iid, new,
                                         require_str(d, "remarks", 0, 1000, required=False)))


# ---------------- analytics, reports, feedback, logs ----------------
@bp.get("/analytics")
@login_required(A)
def analytics():
    with current_app.engine.connect() as c:
        return ok(**analytics_service.pattern_analysis(c))


@bp.get("/reports")
@login_required(A)
def complaint_reports():
    limit, offset = page_args(100, 500)
    with current_app.engine.connect() as c:
        return ok(reports=rows(c,
            "SELECT r.report_code, r.created_at, r.location_text, r.issue_details, r.suggested_category, "
            "r.matched_existing, r.match_score, i.incident_code, i.status, a.name AS area_name, u.full_name "
            "FROM outage_reports r JOIN outage_incidents i ON i.id=r.incident_id JOIN areas a ON a.id=r.area_id "
            "JOIN users u ON u.id=r.user_id ORDER BY r.id DESC LIMIT :l OFFSET :o", {"l": limit, "o": offset}),
            duplicates_prevented=int(c.execute(text("SELECT COUNT(*) FROM outage_reports WHERE matched_existing=1")).scalar()))


@bp.get("/reports.csv")
@login_required(A)
def reports_csv():
    with current_app.engine.connect() as c:
        data = rows(c, "SELECT r.report_code, r.created_at, a.name AS area, r.location_text, i.incident_code, i.status, "
                       "r.matched_existing FROM outage_reports r JOIN outage_incidents i ON i.id=r.incident_id "
                       "JOIN areas a ON a.id=r.area_id ORDER BY r.id DESC")
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["report_code", "created_at", "area", "location", "incident_code", "status", "linked_to_existing"])
    for r in data:
        # neutralise spreadsheet formula injection
        w.writerow([("'" + str(v)) if str(v).startswith(("=", "+", "-", "@")) else v for v in r.values()])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=urjasense_reports.csv"})


@bp.get("/feedback")
@login_required(A)
def feedback():
    with current_app.engine.connect() as c:
        data = rows(c, "SELECT r.id, r.rating, r.feedback, r.created_at, i.incident_code, a.name AS area_name, u.full_name "
                       "FROM ratings r JOIN outage_incidents i ON i.id=r.incident_id JOIN areas a ON a.id=i.area_id "
                       "JOIN users u ON u.id=r.user_id ORDER BY r.id DESC LIMIT 200")
        avg = c.execute(text("SELECT AVG(rating) FROM ratings")).scalar()
    return ok(feedback=data, average=round(float(avg), 2) if avg is not None else None)


@bp.get("/logs")
@login_required(A)
def logs():
    limit, offset = page_args(100, 500)
    with current_app.engine.connect() as c:
        return ok(logs=rows(c, "SELECT l.id, l.created_at, l.action, l.entity_type, l.entity_id, l.details, l.ip_address, "
                               "u.full_name FROM audit_logs l LEFT JOIN users u ON u.id=l.user_id "
                               "ORDER BY l.id DESC LIMIT :l OFFSET :o", {"l": limit, "o": offset}))


# ---------------- notifications management ----------------
@bp.get("/notifications")
@login_required(A)
def notifications():
    with current_app.engine.connect() as c:
        return ok(notifications=rows(c,
            "SELECT n.id, n.title, n.message, n.is_read, n.created_at, u.full_name, i.incident_code "
            "FROM notifications n JOIN users u ON u.id=n.user_id LEFT JOIN outage_incidents i ON i.id=n.incident_id "
            "ORDER BY n.id DESC LIMIT 200"))


@bp.post("/notifications/broadcast")
@login_required(A)
def broadcast():
    """Send an announcement to every active resident (optionally one area)."""
    d = body()
    title = require_str(d, "title", 3, 200)
    msg = require_str(d, "message", 3, 1000)
    area_id = require_int(d, "area_id", 1, required=False)
    with current_app.engine.begin() as c:
        sql = "SELECT id FROM users WHERE role='public' AND is_active=1" + (" AND area_id=:a" if area_id else "")
        ids = [r[0] for r in c.execute(text(sql), {"a": area_id} if area_id else {})]
        for uid in ids:
            notification_service.notify_user(c, uid, None, title, msg, d.get("title_hi") or None, d.get("message_hi") or None)
        audit_service.log_action(c, g.user["id"], "BROADCAST_SENT", "notification", None, f"{title} -> {len(ids)} users")
    return ok(sent=len(ids))
