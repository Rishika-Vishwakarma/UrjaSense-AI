from datetime import datetime, timedelta, timezone


def now_local(offset_minutes: int = 330) -> datetime:
    """Naive 'wall-clock' datetime in the configured timezone (default IST)."""
    return (datetime.now(timezone.utc) + timedelta(minutes=offset_minutes)).replace(tzinfo=None, microsecond=0)


def parse_dt(value: str) -> datetime:
    value = value.strip().replace("Z", "")
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ValueError("Invalid datetime format")


def iso(dt) -> str | None:
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt.replace(" ", "T")[:19]
    return dt.isoformat(timespec="seconds")
