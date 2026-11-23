"""Endpoints that expose NO personal data: health, areas, public incident tracking and the outage map."""
from flask import Blueprint, current_app, request
from sqlalchemy import text

from backend.services import incident_service as svc
from backend.services.common import one, rows
from backend.utils.api import ok
from backend.utils.rate_limit import rate_limit

bp = Blueprint("public", __name__, url_prefix="/api")

PUBLIC_FIELDS = ("id", "incident_code", "area_id", "area_name", "location_text", "latitude", "longitude",
                 "suggested_category", "verified_category", "category_is_verified", "official_cause", "status",
                 "status_label_en", "status_label_hi", "priority", "affected_count", "outage_start_time",
                 "predicted_minutes", "predicted_restoration_at", "lineman_eta_at", "repair_progress_pct",
                 "resolved_at", "is_sample", "prediction_note")


def public_view(inc: dict) -> dict:
    return {k: inc.get(k) for k in PUBLIC_FIELDS}


@bp.get("/health")
def health():
    with current_app.engine.connect() as c:
        c.execute(text("SELECT 1"))
    return ok(status="ok", service="UrjaSense AI API")


@bp.get("/areas")
def areas():
    with current_app.engine.connect() as c:
        return ok(areas=rows(c, "SELECT id, name, city, district, ward_code, latitude, longitude, radius_km "
                                "FROM areas WHERE is_active=1 ORDER BY name"))


@bp.get("/incidents/active")
@rate_limit(60, 60)
def active_incidents():
    """Data behind the live outage map (no resident details)."""
    with current_app.engine.connect() as c:
        data = rows(c, svc.INCIDENT_SELECT + "WHERE i.status <> 'RESOLVED' ORDER BY i.affected_count DESC")
    out = []
    for inc in data:
        inc["status_label_en"] = svc.STATUS_LABELS_EN[inc["status"]]
        inc["status_label_hi"] = svc.STATUS_LABELS_HI[inc["status"]]
        inc["category_is_verified"] = bool(inc["verified_category"])
        inc["prediction_note"] = "ESTIMATE from a statistical model; not an official commitment."
        out.append(public_view(inc))
    return ok(incidents=out)


@bp.get("/incidents/track")
@rate_limit(60, 60)
def track():
    """Track by incident code (INC-...) or report code (RPT-...). Returns incident info only."""
    code = (request.args.get("code") or "").strip().upper()
    if not code:
        return ok(error="code is required"), 400
    with current_app.engine.connect() as c:
        if code.startswith("RPT-"):
            r = one(c, "SELECT incident_id FROM outage_reports WHERE report_code=:c", {"c": code})
            inc = svc.get_incident(c, r["incident_id"]) if r else None
        else:
            r = one(c, "SELECT id FROM outage_incidents WHERE incident_code=:c", {"c": code})
            inc = svc.get_incident(c, r["id"]) if r else None
        if not inc:
            return ok(error="No incident found for that code"), 404
        updates = [{"new_status": u["new_status"], "remarks": u["remarks"], "created_at": u["created_at"]}
                   for u in svc.get_updates(c, inc["id"])]
    return ok(incident=public_view(inc), updates=updates)
