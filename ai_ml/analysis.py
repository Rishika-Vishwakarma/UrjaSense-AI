"""Outage pattern analysis with pandas/NumPy (explainable statistics, no black box)."""
import numpy as np
import pandas as pd


def analyze(df: pd.DataFrame, area_names: dict | None = None) -> dict:
    """df columns: area_id, category, started_at, duration_minutes, affected_count."""
    if df.empty:
        return {"n_records": 0, "frequent_areas": [], "avg_duration_by_area": [], "peak_hours": [],
                "peak_weekdays": [], "repeated_patterns": [], "anomalies": [], "category_mix": []}
    d = df.copy()
    d["started_at"] = pd.to_datetime(d["started_at"])
    d["area_name"] = d["area_id"].map(area_names or {}).fillna(d["area_id"].astype(str))
    d["hour"] = d["started_at"].dt.hour
    d["weekday"] = d["started_at"].dt.day_name()
    d["date"] = d["started_at"].dt.date

    freq = d.groupby("area_name").size().sort_values(ascending=False)
    avg = d.groupby("area_name")["duration_minutes"].agg(["mean", "count"]).sort_values("mean", ascending=False)
    hours = d.groupby("hour").size()
    wdays = d.groupby("weekday").size().sort_values(ascending=False)
    mix = d.groupby("category").size().sort_values(ascending=False)

    # repeated patterns: areas whose outages recur at short intervals
    repeated = []
    for name, g in d.sort_values("started_at").groupby("area_name"):
        if len(g) < 4:
            continue
        gaps = g["started_at"].diff().dropna().dt.total_seconds() / 86400
        med = float(gaps.median())
        top_hour = int(g["hour"].mode().iloc[0])
        top_cat = g["category"].mode().iloc[0]
        repeated.append({"area": name, "outages": int(len(g)), "median_gap_days": round(med, 1),
                         "common_hour": top_hour, "common_category": top_cat})
    repeated.sort(key=lambda r: r["median_gap_days"])

    # anomalies: area-days with an unusually high outage count (robust z-score)
    daily = d.groupby(["area_name", "date"]).size().rename("n").reset_index()
    anomalies = []
    for name, g in daily.groupby("area_name"):
        med = g["n"].median()
        mad = np.median(np.abs(g["n"] - med)) or 0.5
        g = g.assign(z=0.6745 * (g["n"] - med) / mad)
        for _, r in g[(g["z"] >= 3.5) & (g["n"] >= 3)].iterrows():
            anomalies.append({"area": name, "date": str(r["date"]), "outages": int(r["n"]),
                              "score": round(float(r["z"]), 1),
                              "note": "Unusually many outages on one day compared with this area's normal"})
    anomalies.sort(key=lambda a: -a["score"])

    return {
        "n_records": int(len(d)),
        "frequent_areas": [{"area": k, "outages": int(v)} for k, v in freq.items()],
        "avg_duration_by_area": [{"area": k, "avg_minutes": round(float(r["mean"]), 1), "outages": int(r["count"])}
                                 for k, r in avg.iterrows()],
        "overall_avg_minutes": round(float(d["duration_minutes"].mean()), 1),
        "peak_hours": [{"hour": int(h), "outages": int(c)} for h, c in hours.sort_values(ascending=False).head(5).items()],
        "hourly_distribution": [int(hours.get(h, 0)) for h in range(24)],
        "peak_weekdays": [{"weekday": k, "outages": int(v)} for k, v in wdays.items()],
        "repeated_patterns": repeated[:5],
        "anomalies": anomalies[:10],
        "category_mix": [{"category": k, "outages": int(v)} for k, v in mix.items()],
    }
