"""Generate a SIMULATED historical outage dataset for demonstration/testing.

!! This is NOT real electricity department data. Every row is tagged
!! data_source = SIMULATED_SAMPLE. Replace sample_historical_outages.csv with
!! real restoration records (same columns) to train on real data.
"""
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent / "sample_historical_outages.csv"

AREAS = {1: "Arera Colony", 2: "MP Nagar", 3: "New Market", 4: "Kolar Road",
         5: "Shahpura", 6: "Bairagarh", 7: "Hoshangabad Road"}
# relative outage frequency and repair-difficulty factor per area (simulated)
AREA_FREQ = {1: 1.0, 2: 0.8, 3: 0.7, 4: 1.6, 5: 1.0, 6: 1.9, 7: 1.3}
AREA_FACTOR = {1: 0.9, 2: 0.85, 3: 0.8, 4: 1.25, 5: 1.0, 6: 1.35, 7: 1.15}
CATEGORY_BASE = {"transformer_fault": 190, "line_fault": 115, "weather_related": 160,
                 "planned_maintenance": 120, "local_fault": 45, "other": 90}
CATEGORY_P = {"transformer_fault": 0.15, "line_fault": 0.28, "weather_related": 0.17,
              "planned_maintenance": 0.10, "local_fault": 0.22, "other": 0.08}


def generate(n: int = 3000, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    area_ids = list(AREAS)
    ap = np.array([AREA_FREQ[a] for a in area_ids]); ap = ap / ap.sum()
    cats = list(CATEGORY_P)
    cp = np.array([CATEGORY_P[c] for c in cats])
    start = pd.Timestamp("2025-05-01")
    rows = []
    for i in range(n):
        area = int(rng.choice(area_ids, p=ap))
        cat = str(rng.choice(cats, p=cp))
        day = int(rng.integers(0, 540))
        ts = start + pd.Timedelta(days=day)
        # evening peak (load) and monsoon season (Jun-Sep) skew
        if ts.month in (6, 7, 8, 9) and rng.random() < 0.35:
            cat = "weather_related"
        hour = int(rng.choice(range(24), p=_hour_probs()))
        ts = ts.replace(hour=hour, minute=int(rng.integers(0, 60)))
        affected = int(max(1, rng.lognormal(mean=2.4, sigma=0.9)))
        total = CATEGORY_BASE[cat] * AREA_FACTOR[area] * (1 + 0.12 * np.log1p(affected))
        total *= rng.lognormal(0, 0.22)
        progress = int(rng.choice([0, 25, 50, 75], p=[0.4, 0.25, 0.2, 0.15]))
        remaining = max(5, total * (1 - progress / 100))
        rows.append((area, AREAS[area], cat, ts, affected, progress, int(total), int(remaining)))
    df = pd.DataFrame(rows, columns=["area_id", "area_name", "category", "started_at", "affected_count",
                                     "repair_progress_pct", "duration_minutes", "remaining_minutes"])
    # inject a simulated abnormal cluster: one bad day in Bairagarh
    spike = df.sample(18, random_state=1).copy()
    spike["area_id"], spike["area_name"] = 6, AREAS[6]
    spike["started_at"] = pd.Timestamp("2026-02-14") + pd.to_timedelta(rng.integers(8, 22, 18), unit="h")
    df = pd.concat([df, spike], ignore_index=True).sort_values("started_at").reset_index(drop=True)
    df.insert(0, "outage_id", range(1, len(df) + 1))
    df["data_source"] = "SIMULATED_SAMPLE"
    return df


def _hour_probs():
    p = np.ones(24)
    p[17:23] = 2.2   # evening peak load
    p[0:5] = 0.6
    return p / p.sum()


if __name__ == "__main__":
    data = generate()
    data.to_csv(OUT, index=False)
    print(f"Wrote {len(data)} SIMULATED rows to {OUT}")
