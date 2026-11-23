import re

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^\+?\d{10,13}$")


class ValidationError(Exception):
    def __init__(self, message: str, field: str | None = None):
        super().__init__(message)
        self.message, self.field = message, field


def require_str(data: dict, key: str, min_len=1, max_len=255, required=True) -> str | None:
    v = data.get(key)
    if v is None or (isinstance(v, str) and not v.strip()):
        if required:
            raise ValidationError(f"{key} is required", key)
        return None
    if not isinstance(v, str):
        raise ValidationError(f"{key} must be text", key)
    v = v.strip()
    if not (min_len <= len(v) <= max_len):
        raise ValidationError(f"{key} must be {min_len}-{max_len} characters", key)
    return v


def require_int(data: dict, key: str, lo=None, hi=None, required=True):
    v = data.get(key)
    if v is None or v == "":
        if required:
            raise ValidationError(f"{key} is required", key)
        return None
    try:
        v = int(v)
    except (TypeError, ValueError):
        raise ValidationError(f"{key} must be a number", key)
    if (lo is not None and v < lo) or (hi is not None and v > hi):
        raise ValidationError(f"{key} must be between {lo} and {hi}", key)
    return v


def optional_coord(data: dict):
    lat, lng = data.get("latitude"), data.get("longitude")
    if lat in (None, "") or lng in (None, ""):
        return None, None
    try:
        lat, lng = float(lat), float(lng)
    except (TypeError, ValueError):
        raise ValidationError("latitude/longitude must be numbers", "latitude")
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise ValidationError("latitude/longitude out of range", "latitude")
    return lat, lng


def validate_email(email: str) -> str:
    email = email.strip().lower()
    if not EMAIL_RE.match(email) or len(email) > 160:
        raise ValidationError("Invalid email address", "email")
    return email


def validate_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    p = re.sub(r"[\s-]", "", phone)
    if not PHONE_RE.match(p):
        raise ValidationError("Invalid phone number", "phone")
    return p


def validate_password(pw: str) -> str:
    if not isinstance(pw, str) or len(pw) < 8 or not re.search(r"[A-Za-z]", pw) or not re.search(r"\d", pw):
        raise ValidationError("Password must be at least 8 characters with letters and digits", "password")
    if len(pw) > 128:
        raise ValidationError("Password too long", "password")
    return pw
