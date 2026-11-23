"""Train the restoration-time model.

Trained on whatever is in data/sample_historical_outages.csv. The bundled file is
SIMULATED. Swap in real restoration records (same columns) to retrain.
Usage:  python -m ai_ml.training
"""
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from ai_ml.preprocessing.features import CAT_FEATURES, NUM_FEATURES, build_frame

DATA = Path(__file__).parent / "data" / "sample_historical_outages.csv"
MODEL_PATH = Path(__file__).parent / "models" / "restoration_model.joblib"
META_PATH = Path(__file__).parent / "models" / "restoration_model_meta.json"


def make_pipeline() -> Pipeline:
    pre = ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore"), CAT_FEATURES),
        ("num", "passthrough", NUM_FEATURES),
    ])
    reg = GradientBoostingRegressor(n_estimators=250, max_depth=3, learning_rate=0.06,
                                    subsample=0.9, random_state=7)
    return Pipeline([("pre", pre), ("reg", reg)])


def train(data_path: Path = DATA, save: bool = True) -> dict:
    df = pd.read_csv(data_path)
    X = build_frame(df)
    y = np.log1p(df["remaining_minutes"])          # log target stabilises skew
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=7)
    model = make_pipeline().fit(Xtr, ytr)
    pred = np.expm1(model.predict(Xte)); true = np.expm1(yte)
    # naive baseline: mean remaining minutes per category
    base = df.loc[Xtr.index].groupby("category")["remaining_minutes"].mean()
    base_pred = Xte["category"].map(base).fillna(base.mean())
    ratio = true / np.maximum(pred, 1)
    meta = {
        "data_source": str(df["data_source"].iloc[0]) if "data_source" in df else "UNKNOWN",
        "n_rows": int(len(df)),
        "mae_minutes": round(float(mean_absolute_error(true, pred)), 1),
        "r2": round(float(r2_score(true, pred)), 3),
        "baseline_mae_minutes": round(float(mean_absolute_error(true, base_pred)), 1),
        "ratio_p10": round(float(np.quantile(ratio, 0.10)), 3),
        "ratio_p90": round(float(np.quantile(ratio, 0.90)), 3),
    }
    if save:
        model = make_pipeline().fit(X, y)      # refit on all data for serving
        MODEL_PATH.parent.mkdir(exist_ok=True)
        joblib.dump(model, MODEL_PATH)
        META_PATH.write_text(json.dumps(meta, indent=2))
    return meta


if __name__ == "__main__":
    print(json.dumps(train(), indent=2))
