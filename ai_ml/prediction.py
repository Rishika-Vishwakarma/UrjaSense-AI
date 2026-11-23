"""Restoration-time estimation. Always returns an ESTIMATE, never a promise."""
import json
from datetime import datetime, timedelta, timezone

import joblib
import pandas as pd

from ai_ml import training
from ai_ml.preprocessing.features import build_frame, normalise_category

_model = None
_meta = None

DISCLAIMER_EN = ("Estimated by a statistical model. Not an official commitment; "
                 "the lineman's confirmed time takes priority.")
DISCLAIMER_HI = ("यह एक सांख्यिकीय मॉडल का अनुमान है, आधिकारिक वादा नहीं; "
                 "लाइनमैन द्वारा दिया गया समय अंतिम माना जाएगा।")


def _load():
    global _model, _meta
    if _model is None:
        if not training.MODEL_PATH.exists():
            training.train()
        _model = joblib.load(training.MODEL_PATH)
        _meta = json.loads(training.META_PATH.read_text())
    return _model, _meta


def predict_restoration(area_id: int, category: str | None, affected_count: int,
                        started_at: datetime, repair_progress_pct: int = 0,
                        now: datetime | None = None) -> dict:
    model, meta = _load()
    row = pd.DataFrame([{
        "area_id": area_id, "category": normalise_category(category),
        "affected_count": max(1, affected_count), "started_at": started_at,
        "repair_progress_pct": repair_progress_pct,
    }])
    import numpy as np
    minutes = float(np.expm1(model.predict(build_frame(row))[0]))
    minutes = max(10.0, minutes)
    low = max(5.0, minutes * meta["ratio_p10"])
    high = minutes * meta["ratio_p90"]
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    return {
        "is_estimate": True,
        "remaining_minutes": int(round(minutes)),
        "range_minutes": [int(round(low)), int(round(high))],
        "estimated_restoration_at": (now + timedelta(minutes=minutes)).isoformat(timespec="minutes"),
        "model_basis": meta["data_source"],
        "model_mae_minutes": meta["mae_minutes"],
        "disclaimer_en": DISCLAIMER_EN,
        "disclaimer_hi": DISCLAIMER_HI,
    }


def model_info() -> dict:
    return _load()[1]
