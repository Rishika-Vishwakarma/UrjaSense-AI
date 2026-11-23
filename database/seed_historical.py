"""Load the SIMULATED historical outage CSV into historical_outages (is_sample = 1)."""
from pathlib import Path

import pandas as pd
from sqlalchemy import text

CSV = Path(__file__).resolve().parent.parent / "ai_ml" / "data" / "sample_historical_outages.csv"


def seed_historical(engine, csv_path: Path = CSV) -> int:
    with engine.begin() as conn:
        if conn.execute(text("SELECT COUNT(*) FROM historical_outages")).scalar():
            return 0
        df = pd.read_csv(csv_path)
        valid = {r[0] for r in conn.execute(text("SELECT id FROM areas"))}
        df = df[df["area_id"].isin(valid)]
        recs = [{"a": int(r.area_id), "c": r.category, "s": str(r.started_at)[:19],
                 "d": int(r.duration_minutes), "n": int(r.affected_count)} for r in df.itertuples()]
        conn.execute(text("INSERT INTO historical_outages (area_id, category, started_at, duration_minutes, "
                          "affected_count, is_sample) VALUES (:a, :c, :s, :d, :n, 1)"), recs)
        return len(recs)
