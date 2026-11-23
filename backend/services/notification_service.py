from flask import current_app
from sqlalchemy import text

from aws import sns_publisher


def notify_user(conn, user_id: int, incident_id: int | None, title: str, message: str,
                title_hi: str | None = None, message_hi: str | None = None):
    conn.execute(text(
        "INSERT INTO notifications (user_id, incident_id, title, message, title_hi, message_hi) "
        "VALUES (:u, :i, :t, :m, :th, :mh)"),
        {"u": user_id, "i": incident_id, "t": title[:200], "m": message[:1000],
         "th": title_hi, "mh": message_hi})


def notify_incident_reporters(conn, incident_id: int, title: str, message: str,
                              title_hi: str | None = None, message_hi: str | None = None,
                              exclude_user_id: int | None = None) -> int:
    """In-app notification for every resident who reported this incident."""
    ids = [r[0] for r in conn.execute(text(
        "SELECT DISTINCT user_id FROM outage_reports WHERE incident_id = :i"), {"i": incident_id})]
    n = 0
    for uid in ids:
        if uid == exclude_user_id:
            continue
        notify_user(conn, uid, incident_id, title, message, title_hi, message_hi)
        n += 1
    if n:
        # optional extra channel; returns False (no-op) unless SNS is configured
        sns_publisher.publish(current_app.config, title, message)
    return n
