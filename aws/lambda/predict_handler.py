"""Standalone Lambda: restoration-time estimate (invoked by other services or API Gateway).

Event: {"area_id": 1, "category": "line_fault", "affected_count": 12,
        "started_at": "2026-11-22T18:30:00", "repair_progress_pct": 0}
Returns the same estimate structure as ai_ml.prediction (always flagged is_estimate).
"""
import json
from datetime import datetime

from ai_ml.prediction import predict_restoration


def handler(event, _context):
    body = event.get("body")
    data = json.loads(body) if isinstance(body, str) else (body or event)
    try:
        result = predict_restoration(int(data["area_id"]), data.get("category"), int(data.get("affected_count", 1)),
                                     datetime.fromisoformat(data["started_at"]), int(data.get("repair_progress_pct", 0)))
    except (KeyError, ValueError) as exc:
        return {"statusCode": 400, "body": json.dumps({"error": f"Invalid input: {exc}"})}
    return {"statusCode": 200, "headers": {"Content-Type": "application/json"}, "body": json.dumps(result, ensure_ascii=False)}
