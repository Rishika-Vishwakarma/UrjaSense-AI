from flask import has_request_context, request
from sqlalchemy import text


def log_action(conn, user_id, action: str, entity_type: str | None = None,
               entity_id: int | None = None, details: str | None = None):
    ip = request.remote_addr if has_request_context() else None
    conn.execute(text(
        "INSERT INTO audit_logs (user_id, action, entity_type, entity_id, ip_address, details) "
        "VALUES (:u, :a, :t, :e, :ip, :d)"),
        {"u": user_id, "a": action, "t": entity_type, "e": entity_id, "ip": ip,
         "d": (details or "")[:1000]})
