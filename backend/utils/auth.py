"""JWT authentication + role-based access control."""
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import current_app, g, jsonify, request
from sqlalchemy import text


def issue_token(user: dict) -> str:
    payload = {"sub": str(user["id"]), "role": user["role"],
               "exp": datetime.now(timezone.utc) + timedelta(hours=current_app.config["JWT_EXPIRY_HOURS"])}
    return jwt.encode(payload, current_app.config["SECRET_KEY"], algorithm="HS256")


def _unauth(msg="Authentication required", code=401):
    resp = jsonify(error=msg)
    resp.status_code = code
    return resp


def login_required(*roles):
    """@login_required() any logged-in user; @login_required('admin') only admins."""
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            header = request.headers.get("Authorization", "")
            if not header.startswith("Bearer "):
                return _unauth()
            try:
                claims = jwt.decode(header[7:], current_app.config["SECRET_KEY"], algorithms=["HS256"])
            except jwt.PyJWTError:
                return _unauth("Invalid or expired token")
            with current_app.engine.connect() as c:
                row = c.execute(text("SELECT id, full_name, email, role, preferred_language, is_active, area_id "
                                     "FROM users WHERE id = :i"), {"i": int(claims["sub"])}).mappings().first()
            # role is re-read from DB so a demoted/disabled user loses access immediately
            if not row or not row["is_active"]:
                return _unauth("Account disabled or not found", 403)
            if roles and row["role"] not in roles:
                return _unauth("You do not have permission to access this resource", 403)
            g.user = dict(row)
            return fn(*a, **kw)
        return wrapper
    return deco
