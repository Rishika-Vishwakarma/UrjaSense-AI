"""Duplicate outage detection.

A new report is scored against every OPEN incident in the same area:
  proximity (0.50)  GPS distance if both have coordinates, else same-area only (0.35)
  time      (0.30)  outage start within 60 min = 0.30, within the window (default 180) = 0.20
  issue     (0.20)  same category 0.20, one side unknown 0.10, conflicting categories 0.00
Best score >= threshold (default 0.55) -> link to that incident. Otherwise new incident.
The user's own report row is always kept, so genuine users are never blocked.
"""
from math import asin, cos, radians, sin, sqrt


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = radians(lat1), radians(lat2)
    dphi, dlmb = p2 - p1, radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(p1) * cos(p2) * sin(dlmb / 2) ** 2
    return 2 * 6371.0 * asin(sqrt(a))


def score_match(report: dict, incident: dict, area_radius_km: float, time_window_min: int) -> float:
    # --- proximity ---
    if None not in (report["lat"], report["lng"], incident["latitude"], incident["longitude"]):
        d = haversine_km(report["lat"], report["lng"], float(incident["latitude"]), float(incident["longitude"]))
        if d <= 0.5:
            prox = 0.50
        elif d <= area_radius_km:
            prox = 0.50 * (1 - (d - 0.5) / max(area_radius_km - 0.5, 0.1)) * 0.8 + 0.1
        else:
            return 0.0                      # clearly a different location in the same area
    else:
        prox = 0.35                         # same area, no GPS to refine
    # --- time ---
    gap = abs((report["start"] - incident["start"]).total_seconds()) / 60
    if gap <= 60:
        tscore = 0.30
    elif gap <= time_window_min:
        tscore = 0.20
    else:
        tscore = 0.0
    # --- issue ---
    rc, ic = report["category"], incident["category"]
    if "unknown" in (rc, ic) or not rc or not ic:
        iscore = 0.10
    elif rc == ic:
        iscore = 0.20
    else:
        iscore = 0.0
    return round(prox + tscore + iscore, 2)


def best_match(candidates: list[dict], report: dict, area_radius_km: float,
               time_window_min: int, threshold: float):
    best, best_score = None, 0.0
    for inc in candidates:
        s = score_match(report, inc, area_radius_km, time_window_min)
        if s > best_score:
            best, best_score = inc, s
    if best is not None and best_score >= threshold:
        return best, best_score
    return None, best_score
