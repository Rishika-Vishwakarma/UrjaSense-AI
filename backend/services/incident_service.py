"""Incident business logic: report intake, duplicate linking, workflow, assignment."""
import uuid
from datetime import datetime, timedelta

from flask import current_app
from sqlalchemy import text

from ai_ml.categorizer import suggest_category
from ai_ml.prediction import predict_restoration
from backend.models.enums import (ACTIVE_STATUSES, PRIORITIES, STATUS_LABELS_EN,
                                  STATUS_LABELS_HI, TRANSITIONS)
from backend.services import audit_service, notification_service
from backend.services.common import dt_param, one, rows
from backend.services.duplicate_service import best_match
from backend.utils.timeutil import now_local, parse_dt


class ServiceError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message, self.status = message, status


def _lock_suffix(conn) -> str:
    return " FOR UPDATE" if conn.dialect.name == "mysql" else ""


def compute_priority(affected: int, category: str | None) -> str:
    level = 0 if affected < 8 else 1 if affected < 20 else 2 if affected < 50 else 3
    if affected >= 5 and category in ("transformer_fault", "line_fault"):
        level = min(3, level + 1)
    return PRIORITIES[level]


def _now() -> datetime:
    return now_local(current_app.config["APP_TZ_OFFSET_MINUTES"])


def refresh_prediction(conn, incident_id: int) -> dict:
    inc = one(conn, "SELECT * FROM outage_incidents WHERE id = :i", {"i": incident_id})
    cat = inc["verified_category"] or inc["suggested_category"]
    now = _now()
    pred = predict_restoration(inc["area_id"], cat, inc["affected_count"],
                               parse_dt(inc["outage_start_time"]), inc["repair_progress_pct"], now=now)
    conn.execute(text("UPDATE outage_incidents SET predicted_minutes=:m, predicted_restoration_at=:r, "
                      "updated_at=:n WHERE id=:i"),
                 {"m": pred["remaining_minutes"], "r": dt_param(parse_dt(pred["estimated_restoration_at"])),
                  "n": dt_param(now), "i": incident_id})
    return pred


def _assign_code(conn, table: str, prefix: str, row_id: int, col: str):
    code = f"{prefix}-{_now():%Y%m%d}-{row_id:04d}"
    conn.execute(text(f"UPDATE {table} SET {col}=:c WHERE id=:i"), {"c": code, "i": row_id})
    return code


def submit_report(engine, user: dict, area_id: int, location_text: str, lat, lng,
                  outage_start: datetime, issue_details: str | None) -> dict:
    cfg = current_app.config
    now = _now()
    if outage_start > now + timedelta(minutes=5):
        raise ServiceError("Outage start time cannot be in the future")
    if outage_start < now - timedelta(days=2):
        raise ServiceError("Outage start time is more than 2 days ago; please contact the helpline")

    with engine.begin() as conn:                     # single transaction
        area = one(conn, "SELECT * FROM areas WHERE id=:a AND is_active=1", {"a": area_id})
        if not area:
            raise ServiceError("Unknown area", 404)

        recent = conn.execute(text(
            "SELECT COUNT(*) FROM outage_reports WHERE user_id=:u AND created_at >= :t"),
            {"u": user["id"], "t": dt_param(now - timedelta(hours=1))}).scalar()
        if recent >= cfg["MAX_REPORTS_PER_USER_PER_HOUR"]:
            raise ServiceError("Report limit reached for this hour. Please track your existing reports.", 429)

        cat = suggest_category(issue_details)["category"]
        candidates = rows(conn,
            "SELECT id, incident_code, latitude, longitude, suggested_category, verified_category, "
            "outage_start_time, status, affected_count FROM outage_incidents "
            "WHERE area_id=:a AND status <> 'RESOLVED'" + _lock_suffix(conn), {"a": area_id})
        for c in candidates:
            c["start"] = parse_dt(c["outage_start_time"])
            c["category"] = c["verified_category"] or c["suggested_category"]
            c["latitude"], c["longitude"] = c["latitude"], c["longitude"]
        report = {"lat": lat, "lng": lng, "start": outage_start, "category": cat}
        match, score = best_match(candidates, report, float(area["radius_km"]),
                                  cfg["DUP_TIME_WINDOW_MIN"], cfg["DUP_MATCH_THRESHOLD"])

        if match:
            incident_id, matched = match["id"], True
            existing = one(conn, "SELECT id, report_code FROM outage_reports WHERE user_id=:u AND incident_id=:i",
                           {"u": user["id"], "i": incident_id})
            if existing:   # same resident reporting the same incident again: no double counting
                inc = get_incident(conn, incident_id)
                return {"report_code": existing["report_code"], "incident": inc,
                        "linked_to_existing": True, "already_reported": True,
                        "message": "You have already reported this outage. It is being tracked."}
        else:
            incident_id, matched = None, False
            res = conn.execute(text(
                "INSERT INTO outage_incidents (incident_code, area_id, location_text, latitude, longitude, "
                "suggested_category, status, priority, affected_count, outage_start_time, created_at, updated_at) "
                "VALUES (:code, :a, :loc, :lat, :lng, :cat, 'REPORTED', 'LOW', 1, :st, :n, :n)"),
                {"code": "TMP-" + uuid.uuid4().hex[:20], "a": area_id, "loc": location_text,
                 "lat": lat, "lng": lng, "cat": cat, "st": dt_param(outage_start), "n": dt_param(now)})
            incident_id = res.lastrowid
            _assign_code(conn, "outage_incidents", "INC", incident_id, "incident_code")
            conn.execute(text(
                "INSERT INTO incident_updates (incident_id, previous_status, new_status, updated_by, remarks, created_at) "
                "VALUES (:i, NULL, 'REPORTED', :u, 'Incident created from first resident report.', :n)"),
                {"i": incident_id, "u": user["id"], "n": dt_param(now)})

        res = conn.execute(text(
            "INSERT INTO outage_reports (report_code, user_id, incident_id, area_id, location_text, latitude, longitude, "
            "outage_start_time, issue_details, suggested_category, matched_existing, match_score, created_at) "
            "VALUES (:code, :u, :i, :a, :loc, :lat, :lng, :st, :det, :cat, :m, :sc, :n)"),
            {"code": "TMPR-" + uuid.uuid4().hex[:20], "u": user["id"], "i": incident_id, "a": area_id,
             "loc": location_text, "lat": lat, "lng": lng, "st": dt_param(outage_start), "det": issue_details,
             "cat": cat, "m": 1 if matched else 0, "sc": score if matched else None, "n": dt_param(now)})
        report_id = res.lastrowid
        report_code = _assign_code(conn, "outage_reports", "RPT", report_id, "report_code")

        # affected-user count = distinct residents who reported this incident
        count = conn.execute(text("SELECT COUNT(DISTINCT user_id) FROM outage_reports WHERE incident_id=:i"),
                             {"i": incident_id}).scalar()
        inc_row = one(conn, "SELECT suggested_category, verified_category FROM outage_incidents WHERE id=:i",
                      {"i": incident_id})
        new_cat = inc_row["suggested_category"]
        if new_cat == "unknown" and cat != "unknown":
            new_cat = cat                                   # refine a still-unknown suggestion
        conn.execute(text("UPDATE outage_incidents SET affected_count=:c, priority=:p, suggested_category=:cat, "
                          "updated_at=:n WHERE id=:i"),
                     {"c": count, "p": compute_priority(count, inc_row["verified_category"] or new_cat),
                      "cat": new_cat, "n": dt_param(now), "i": incident_id})
        pred = refresh_prediction(conn, incident_id)
        inc = get_incident(conn, incident_id)

        title = "Outage report received"
        msg = (f"Your report {report_code} is linked to existing incident {inc['incident_code']}."
               if matched else f"Your report {report_code} created incident {inc['incident_code']}.")
        msg_hi = (f"आपकी रिपोर्ट {report_code} मौजूदा घटना {inc['incident_code']} से जोड़ी गई है।"
                  if matched else f"आपकी रिपोर्ट {report_code} से घटना {inc['incident_code']} बनाई गई है।")
        notification_service.notify_user(conn, user["id"], incident_id, title, msg, "रिपोर्ट प्राप्त हुई", msg_hi)
        audit_service.log_action(conn, user["id"], "REPORT_SUBMITTED", "outage_report", report_id,
                                 f"incident={inc['incident_code']} linked={matched} score={score}")
    return {"report_code": report_code, "incident": inc, "linked_to_existing": matched,
            "already_reported": False, "prediction": pred,
            "message": ("Your report was linked to an existing outage incident." if matched
                        else "A new outage incident was created.")}


INCIDENT_SELECT = (
    "SELECT i.*, a.name AS area_name, "
    "(SELECT u.full_name FROM assignments s JOIN linemen l ON l.id=s.lineman_id JOIN users u ON u.id=l.user_id "
    " WHERE s.incident_id=i.id AND s.is_active=1 ORDER BY s.id DESC LIMIT 1) AS assigned_to, "
    "(SELECT s.lineman_id FROM assignments s WHERE s.incident_id=i.id AND s.is_active=1 "
    " ORDER BY s.id DESC LIMIT 1) AS assigned_lineman_id "
    "FROM outage_incidents i JOIN areas a ON a.id=i.area_id ")


def get_incident(conn, incident_id: int) -> dict | None:
    inc = one(conn, INCIDENT_SELECT + "WHERE i.id=:i", {"i": incident_id})
    if inc:
        inc["status_label_en"] = STATUS_LABELS_EN[inc["status"]]
        inc["status_label_hi"] = STATUS_LABELS_HI[inc["status"]]
        inc["category_is_verified"] = bool(inc["verified_category"])
        inc["prediction_note"] = ("ESTIMATE from a statistical model (sample-data trained); "
                                  "not an official commitment.")
    return inc


def get_updates(conn, incident_id: int) -> list[dict]:
    return rows(conn,
        "SELECT u.id, u.previous_status, u.new_status, u.remarks, u.created_at, "
        "x.full_name AS updated_by_name FROM incident_updates u LEFT JOIN users x ON x.id=u.updated_by "
        "WHERE u.incident_id=:i ORDER BY u.id", {"i": incident_id})


def _lineman_for_user(conn, user_id: int) -> dict | None:
    return one(conn, "SELECT * FROM linemen WHERE user_id=:u", {"u": user_id})


def _ensure_can_work(conn, actor: dict, incident_id: int):
    if actor["role"] == "admin":
        return
    lm = _lineman_for_user(conn, actor["id"])
    if not lm or lm["approval_status"] != "APPROVED":
        raise ServiceError("Lineman account is not approved", 403)
    ok = conn.execute(text("SELECT 1 FROM assignments WHERE incident_id=:i AND lineman_id=:l AND is_active=1"),
                      {"i": incident_id, "l": lm["id"]}).first()
    if not ok:
        raise ServiceError("This incident is not assigned to you", 403)


def _record_update(conn, incident_id, prev, new, user_id, remarks, now):
    conn.execute(text("INSERT INTO incident_updates (incident_id, previous_status, new_status, updated_by, remarks, created_at) "
                      "VALUES (:i, :p, :n, :u, :r, :t)"),
                 {"i": incident_id, "p": prev, "n": new, "u": user_id, "r": remarks, "t": dt_param(now)})


def _notify_status(conn, inc: dict, new_status: str, exclude=None):
    en, hi = STATUS_LABELS_EN[new_status], STATUS_LABELS_HI[new_status]
    notification_service.notify_incident_reporters(
        conn, inc["id"], f"Incident {inc['incident_code']}: {en}",
        f"Status of your outage incident {inc['incident_code']} ({inc['area_name']}) is now: {en}.",
        f"घटना {inc['incident_code']}: {hi}",
        f"आपकी बिजली कटौती की घटना {inc['incident_code']} ({inc['area_name']}) की स्थिति अब: {hi}।", exclude)


def change_status(engine, actor: dict, incident_id: int, new_status: str, remarks: str | None) -> dict:
    now = _now()
    with engine.begin() as conn:
        inc = one(conn, "SELECT * FROM outage_incidents WHERE id=:i" + _lock_suffix(conn), {"i": incident_id})
        if not inc:
            raise ServiceError("Incident not found", 404)
        cur = inc["status"]
        allowed = TRANSITIONS.get(cur, {}).get(new_status)
        if allowed is None:
            raise ServiceError(f"Invalid transition {cur} -> {new_status}. Workflow is "
                               "REPORTED → VERIFIED → ASSIGNED → REPAIR_IN_PROGRESS → RESOLVED")
        if actor["role"] not in allowed:
            raise ServiceError("You are not allowed to perform this status change", 403)
        if new_status == "ASSIGNED":
            raise ServiceError("Use the assignment endpoint to assign an incident to a lineman")
        if actor["role"] == "lineman":
            _ensure_can_work(conn, actor, incident_id)
        progress = inc["repair_progress_pct"]
        if new_status == "REPAIR_IN_PROGRESS":
            progress = max(progress, 10)
        sets = "status=:s, repair_progress_pct=:p, updated_at=:n"
        params = {"s": new_status, "p": progress, "n": dt_param(now), "i": incident_id}
        if new_status == "RESOLVED":
            sets += ", repair_progress_pct=100, resolved_at=:n"
        conn.execute(text(f"UPDATE outage_incidents SET {sets} WHERE id=:i"), params)
        _record_update(conn, incident_id, cur, new_status, actor["id"], remarks, now)
        if new_status != "RESOLVED":
            refresh_prediction(conn, incident_id)
        full = get_incident(conn, incident_id)
        _notify_status(conn, full, new_status)
        audit_service.log_action(conn, actor["id"], "STATUS_CHANGED", "incident", incident_id, f"{cur}->{new_status}")
    return full


def assign_incident(engine, admin: dict, incident_id: int, lineman_id: int, remarks: str | None) -> dict:
    now = _now()
    with engine.begin() as conn:
        inc = one(conn, "SELECT * FROM outage_incidents WHERE id=:i" + _lock_suffix(conn), {"i": incident_id})
        if not inc:
            raise ServiceError("Incident not found", 404)
        if inc["status"] == "RESOLVED":
            raise ServiceError("Incident is already resolved")
        lm = one(conn, "SELECT l.*, u.full_name FROM linemen l JOIN users u ON u.id=l.user_id WHERE l.id=:l",
                 {"l": lineman_id})
        if not lm or lm["approval_status"] != "APPROVED":
            raise ServiceError("Lineman not found or not approved", 404)
        cur = inc["status"]
        conn.execute(text("UPDATE assignments SET is_active=0 WHERE incident_id=:i"), {"i": incident_id})
        conn.execute(text("INSERT INTO assignments (incident_id, lineman_id, assigned_by, is_active, assigned_at) "
                          "VALUES (:i, :l, :a, 1, :n)"),
                     {"i": incident_id, "l": lineman_id, "a": admin["id"], "n": dt_param(now)})
        note = remarks or "Assigned to a field lineman."   # staff identity stays out of public timeline
        if cur == "REPORTED":
            _record_update(conn, incident_id, "REPORTED", "VERIFIED", admin["id"], "Verified on assignment by admin.", now)
            cur = "VERIFIED"
        if cur == "VERIFIED":
            _record_update(conn, incident_id, "VERIFIED", "ASSIGNED", admin["id"], note, now)
            conn.execute(text("UPDATE outage_incidents SET status='ASSIGNED', updated_at=:n WHERE id=:i"),
                         {"n": dt_param(now), "i": incident_id})
            full = get_incident(conn, incident_id)
            _notify_status(conn, full, "ASSIGNED")
        else:   # reassignment while already ASSIGNED / REPAIR_IN_PROGRESS keeps status
            _record_update(conn, incident_id, cur, cur, admin["id"], "Reassigned. " + note, now)
            full = get_incident(conn, incident_id)
        notification_service.notify_user(conn, lm["user_id"], incident_id, "New incident assigned",
                                         f"Incident {full['incident_code']} in {full['area_name']} was assigned to you.",
                                         "नई घटना सौंपी गई",
                                         f"{full['area_name']} में घटना {full['incident_code']} आपको सौंपी गई है।")
        audit_service.log_action(conn, admin["id"], "INCIDENT_ASSIGNED", "incident", incident_id, f"lineman={lineman_id} ({lm['employee_code']})")
    return full


def lineman_progress_update(engine, actor: dict, incident_id: int, official_cause: str | None,
                            verified_category: str | None, eta: datetime | None,
                            progress: int | None, remarks: str | None) -> dict:
    now = _now()
    with engine.begin() as conn:
        inc = one(conn, "SELECT * FROM outage_incidents WHERE id=:i" + _lock_suffix(conn), {"i": incident_id})
        if not inc:
            raise ServiceError("Incident not found", 404)
        if inc["status"] == "RESOLVED":
            raise ServiceError("Incident is already resolved")
        _ensure_can_work(conn, actor, incident_id)
        if eta and eta <= now - timedelta(minutes=1):
            raise ServiceError("Estimated restoration time must be in the future")
        sets, params = ["updated_at=:n"], {"n": dt_param(now), "i": incident_id}
        notes = []
        if official_cause:
            sets.append("official_cause=:oc"); params["oc"] = official_cause
            notes.append(f"Verified cause: {official_cause}")
        if verified_category:
            sets.append("verified_category=:vc"); params["vc"] = verified_category
        if eta:
            sets.append("lineman_eta_at=:eta"); params["eta"] = dt_param(eta)
            notes.append(f"Restoration ETA set to {eta:%d %b %H:%M}")
        if progress is not None:
            sets.append("repair_progress_pct=:p"); params["p"] = progress
            notes.append(f"Repair progress {progress}%")
        if remarks:
            notes.append(remarks)
        if len(sets) == 1 and not remarks:
            raise ServiceError("Nothing to update")
        conn.execute(text(f"UPDATE outage_incidents SET {', '.join(sets)} WHERE id=:i"), params)
        _record_update(conn, incident_id, inc["status"], inc["status"], actor["id"], " | ".join(notes), now)
        refresh_prediction(conn, incident_id)
        full = get_incident(conn, incident_id)
        notification_service.notify_incident_reporters(
            conn, incident_id, f"Update on {full['incident_code']}", " | ".join(notes)[:900],
            f"{full['incident_code']} पर अपडेट", " | ".join(notes)[:900])
        audit_service.log_action(conn, actor["id"], "INCIDENT_PROGRESS", "incident", incident_id, " | ".join(notes))
    return full


def submit_rating(engine, user: dict, incident_id: int, rating: int, feedback: str | None) -> int:
    with engine.begin() as conn:
        inc = one(conn, "SELECT status FROM outage_incidents WHERE id=:i", {"i": incident_id})
        if not inc:
            raise ServiceError("Incident not found", 404)
        if inc["status"] != "RESOLVED":
            raise ServiceError("You can rate an incident only after it is resolved")
        if not conn.execute(text("SELECT 1 FROM outage_reports WHERE incident_id=:i AND user_id=:u"),
                            {"i": incident_id, "u": user["id"]}).first():
            raise ServiceError("Only residents who reported this incident can rate it", 403)
        if conn.execute(text("SELECT 1 FROM ratings WHERE incident_id=:i AND user_id=:u"),
                        {"i": incident_id, "u": user["id"]}).first():
            raise ServiceError("You have already rated this incident", 409)
        res = conn.execute(text("INSERT INTO ratings (incident_id, user_id, rating, feedback) VALUES (:i,:u,:r,:f)"),
                           {"i": incident_id, "u": user["id"], "r": rating, "f": feedback})
        audit_service.log_action(conn, user["id"], "RATING_SUBMITTED", "incident", incident_id, f"rating={rating}")
        return res.lastrowid
