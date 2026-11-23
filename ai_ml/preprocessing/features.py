"""Feature engineering shared by training and prediction."""
import pandas as pd

CATEGORIES = ["transformer_fault", "line_fault", "weather_related",
              "planned_maintenance", "local_fault", "other"]
CAT_FEATURES = ["area_id", "category"]
NUM_FEATURES = ["affected_count", "hour", "dayofweek", "month", "repair_progress_pct"]
FEATURES = CAT_FEATURES + NUM_FEATURES


def normalise_category(cat: str | None) -> str:
    return cat if cat in CATEGORIES else "other"


def build_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Expects started_at, area_id, category, affected_count, repair_progress_pct."""
    out = pd.DataFrame()
    ts = pd.to_datetime(df["started_at"])
    out["area_id"] = df["area_id"].astype(int).astype(str)
    out["category"] = df["category"].map(normalise_category)
    out["affected_count"] = df["affected_count"].clip(lower=1)
    out["hour"] = ts.dt.hour
    out["dayofweek"] = ts.dt.dayofweek
    out["month"] = ts.dt.month
    out["repair_progress_pct"] = df["repair_progress_pct"].clip(0, 100)
    return out[FEATURES]
