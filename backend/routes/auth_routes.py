from flask import Blueprint, current_app, g, request
from sqlalchemy import text
from werkzeug.security import check_password_hash, generate_password_hash

from backend.models.enums import LANGUAGES
from backend.services import audit_service
from backend.services.common import one
from backend.utils.api import body, ok
from backend.utils.auth import issue_token, login_required
from backend.utils.rate_limit import rate_limit
from backend.utils.validation import (ValidationError, require_int, require_str, validate_email,
                                      validate_password, validate_phone)

bp = Blueprint("auth", __name__, url_prefix="/api/auth")
PW_METHOD = "pbkdf2:sha256:260000"


def _public(u: dict) -> dict:
    return {k: u[k] for k in ("id", "full_name", "email", "role", "preferred_language", "area_id") if k in u}


@bp.post("/register")
@rate_limit(5, 600)
def register():
    """Public self-registration creates RESIDENT accounts only. Linemen/admins are created by admins."""
    d = body()
    if d.get("role") not in (None, "public"):
        raise ValidationError("Employee accounts can only be created by administrators", "role")
    name = require_str(d, "full_name", 2, 120)
    email = validate_email(require_str(d, "email", 5, 160))
    phone = validate_phone(require_str(d, "phone", 10, 20, required=False))
    pw = validate_password(d.get("password"))
    lang = d.get("preferred_language", "en")
    if lang not in LANGUAGES:
        raise ValidationError("Unsupported language", "preferred_language")
    area_id = require_int(d, "area_id", 1, required=False)
    with current_app.engine.begin() as conn:
        if area_id and not one(conn, "SELECT id FROM areas WHERE id=:a", {"a": area_id}):
            raise ValidationError("Unknown area", "area_id")
        if one(conn, "SELECT id FROM users WHERE email=:e", {"e": email}):
            return ok(error="An account with this email already exists"), 409
        res = conn.execute(text(
            "INSERT INTO users (full_name, email, phone, password_hash, role, preferred_language, area_id) "
            "VALUES (:n, :e, :p, :h, 'public', :l, :a)"),
            {"n": name, "e": email, "p": phone, "h": generate_password_hash(pw, method=PW_METHOD),
             "l": lang, "a": area_id})
        uid = res.lastrowid
        audit_service.log_action(conn, uid, "USER_REGISTERED", "user", uid, email)
        user = one(conn, "SELECT id, full_name, email, role, preferred_language, area_id FROM users WHERE id=:i", {"i": uid})
    return ok(token=issue_token(user), user=_public(user)), 201


@bp.post("/login")
@rate_limit(10, 60)
def login():
    d = body()
    email = (d.get("email") or "").strip().lower()
    pw = d.get("password") or ""
    with current_app.engine.begin() as conn:
        u = one(conn, "SELECT * FROM users WHERE email=:e", {"e": email})
        good = bool(u) and u["is_active"] and check_password_hash(u["password_hash"], pw)
        if good and u["role"] == "lineman":
            lm = one(conn, "SELECT approval_status FROM linemen WHERE user_id=:u", {"u": u["id"]})
            if not lm or lm["approval_status"] != "APPROVED":
                audit_service.log_action(conn, u["id"], "LOGIN_BLOCKED_UNAPPROVED", "user", u["id"])
                return ok(error="Your lineman account is not approved. Contact an administrator."), 403
        audit_service.log_action(conn, u["id"] if u else None, "LOGIN_OK" if good else "LOGIN_FAILED",
                                 "user", u["id"] if u else None, None if good else email[:100])
    if not good:
        return ok(error="Invalid email or password"), 401     # same message for unknown user / wrong password
    return ok(token=issue_token(u), user=_public(u))


@bp.get("/me")
@login_required()
def me():
    return ok(user=_public(g.user))


@bp.put("/me")
@login_required()
def update_me():
    d = body()
    sets, params = [], {"i": g.user["id"]}
    if "full_name" in d:
        params["n"] = require_str(d, "full_name", 2, 120); sets.append("full_name=:n")
    if "phone" in d:
        params["p"] = validate_phone(d.get("phone")); sets.append("phone=:p")
    if "preferred_language" in d:
        if d["preferred_language"] not in LANGUAGES:
            raise ValidationError("Unsupported language", "preferred_language")
        params["l"] = d["preferred_language"]; sets.append("preferred_language=:l")
    if "area_id" in d:
        params["a"] = require_int(d, "area_id", 1, required=False); sets.append("area_id=:a")
    if "address" in d:
        params["ad"] = require_str(d, "address", 1, 255, required=False); sets.append("address=:ad")
    if not sets:
        raise ValidationError("Nothing to update")
    with current_app.engine.begin() as conn:
        conn.execute(text(f"UPDATE users SET {', '.join(sets)} WHERE id=:i"), params)
        audit_service.log_action(conn, g.user["id"], "PROFILE_UPDATED", "user", g.user["id"])
        u = one(conn, "SELECT id, full_name, email, phone, role, preferred_language, area_id, address FROM users WHERE id=:i",
                {"i": g.user["id"]})
    return ok(user=u)


@bp.post("/change-password")
@login_required()
@rate_limit(5, 600, scope="user")
def change_password():
    d = body()
    new = validate_password(d.get("new_password"))
    with current_app.engine.begin() as conn:
        u = one(conn, "SELECT password_hash FROM users WHERE id=:i", {"i": g.user["id"]})
        if not check_password_hash(u["password_hash"], d.get("current_password") or ""):
            return ok(error="Current password is incorrect"), 403
        conn.execute(text("UPDATE users SET password_hash=:h WHERE id=:i"),
                     {"h": generate_password_hash(new, method=PW_METHOD), "i": g.user["id"]})
        audit_service.log_action(conn, g.user["id"], "PASSWORD_CHANGED", "user", g.user["id"])
    return ok(message="Password updated")
