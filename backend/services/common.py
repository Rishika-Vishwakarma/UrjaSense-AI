from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import text


def clean(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat(sep="T", timespec="seconds") if isinstance(value, datetime) else value.isoformat()
    if isinstance(value, str) and len(value) == 19 and value[10] == " " and value[4] == "-":
        return value.replace(" ", "T")  # SQLite returns datetimes as text
    return value


def row_to_dict(row) -> dict:
    return {k: clean(v) for k, v in dict(row).items()}


def rows(conn, sql: str, params: dict | None = None) -> list[dict]:
    return [row_to_dict(r) for r in conn.execute(text(sql), params or {}).mappings().all()]


def one(conn, sql: str, params: dict | None = None) -> dict | None:
    r = conn.execute(text(sql), params or {}).mappings().first()
    return row_to_dict(r) if r else None


def dt_param(dt: datetime) -> str:
    """Datetimes are bound as 'YYYY-MM-DD HH:MM:SS' strings: valid for MySQL and SQLite."""
    return dt.strftime("%Y-%m-%d %H:%M:%S")
