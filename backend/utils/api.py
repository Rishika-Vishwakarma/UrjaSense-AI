from flask import jsonify, request

from backend.utils.validation import ValidationError


def body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValidationError("Request body must be a JSON object")
    return data


def page_args(default=50, maximum=200) -> tuple[int, int]:
    try:
        limit = min(max(int(request.args.get("limit", default)), 1), maximum)
        offset = max(int(request.args.get("offset", 0)), 0)
    except ValueError:
        raise ValidationError("limit/offset must be numbers")
    return limit, offset


def ok(**payload):
    return jsonify(payload)
