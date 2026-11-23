"""Dashboard statistics + pattern analysis (wraps ai_ml.analysis)."""
import pandas as pd
from sqlalchemy import text

from ai_ml.analysis import analyze
from ai_ml.prediction import model_info
from backend.services.common import one, rows


def overview_stats(conn) -> dict:
    s = one(conn, "SELECT "
            "SUM(CASE WHEN status <> 'RESOLVED' THEN 1 ELSE 0 END) AS active, "
            "SUM(CASE WHEN status = 'RESOLVED' THEN 1 ELSE 0 END) AS resolved, "
            "COUNT(*) AS total FROM outage_incidents") or {}
    users = conn.execute(text("SELECT COUNT(*) FROM users WHERE role='public'")).scalar()
    linemen = conn.execute(text("SELECT COUNT(*) FROM linemen WHERE approval_status='APPROVED'")).scalar()
    affected_areas = conn.execute(text(
        "SELECT COUNT(DISTINCT area_id) FROM outage_incidents WHERE status <> 'RESOLVED'")).scalar()
    affected_people = conn.execute(text(
        "SELECT COALESCE(SUM(affected_count),0) FROM outage_incidents WHERE status <> 'RESOLVED'")).scalar()
    res = rows(conn, "SELECT outage_start_time, resolved_at FROM outage_incidents WHERE status='RESOLVED' "
                     "AND resolved_at IS NOT NULL")
    avg_min = None
    if res:
        d = pd.DataFrame(res)
        mins = (pd.to_datetime(d["resolved_at"]) - pd.to_datetime(d["outage_start_time"])).dt.total_seconds() / 60
        avg_min = round(float(mins.mean()), 1)
    avg_rating = conn.execute(text("SELECT AVG(rating) FROM ratings")).scalar()
    return {"active_outages": int(s.get("active") or 0), "resolved_incidents": int(s.get("resolved") or 0),
            "total_incidents": int(s.get("total") or 0), "total_users": int(users or 0),
            "total_linemen": int(linemen or 0), "affected_areas": int(affected_areas or 0),
            "residents_affected_now": int(affected_people or 0),
            "avg_restoration_minutes": avg_min,
            "avg_rating": round(float(avg_rating), 2) if avg_rating is not None else None}


def area_stats(conn) -> list[dict]:
    return rows(conn,
        "SELECT a.id AS area_id, a.name AS area_name, COUNT(i.id) AS incidents, "
        "SUM(CASE WHEN i.status <> 'RESOLVED' THEN 1 ELSE 0 END) AS active, "
        "COALESCE(SUM(i.affected_count),0) AS total_affected "
        "FROM areas a LEFT JOIN outage_incidents i ON i.area_id=a.id GROUP BY a.id, a.name ORDER BY incidents DESC")


def pattern_analysis(conn) -> dict:
    hist = rows(conn, "SELECT area_id, category, started_at, duration_minutes, affected_count, is_sample "
                      "FROM historical_outages")
    live = rows(conn, "SELECT area_id, COALESCE(verified_category, suggested_category) AS category, "
                      "outage_start_time AS started_at, resolved_at, affected_count FROM outage_incidents "
                      "WHERE status='RESOLVED' AND resolved_at IS NOT NULL AND is_sample = 0")
    frames = []
    if hist:
        frames.append(pd.DataFrame(hist)[["area_id", "category", "started_at", "duration_minutes", "affected_count"]])
    if live:
        d = pd.DataFrame(live)
        d["duration_minutes"] = (pd.to_datetime(d["resolved_at"]) - pd.to_datetime(d["started_at"])).dt.total_seconds() / 60
        frames.append(d[["area_id", "category", "started_at", "duration_minutes", "affected_count"]])
    names = {a["id"]: a["name"] for a in rows(conn, "SELECT id, name FROM areas")}
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["area_id", "category", "started_at", "duration_minutes", "affected_count"])
    result = analyze(df, names)
    sample_rows = int(sum(1 for h in hist if h["is_sample"]))
    result["data_notice"] = (f"{sample_rows} of {len(df)} analysed records are SIMULATED sample data, "
                             "not real department records." if sample_rows else
                             "Analysis is based on resolved incidents recorded in this system.")
    result["model"] = model_info()
    return result
