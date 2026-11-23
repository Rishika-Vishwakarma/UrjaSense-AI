"""Database configuration and helpers.

Primary target: MySQL (Amazon RDS for MySQL in the cloud setup).
SQLite is supported only so the automated tests and a zero-setup local demo
can run without a MySQL server. Select with the DATABASE_URL env variable:

    mysql+pymysql://user:password@host:3306/urjasense?charset=utf8mb4
    sqlite:///urjasense_local.db
"""
import os
import re
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

BASE_DIR = Path(__file__).resolve().parent
SCHEMA_FILE = BASE_DIR / "schema.sql"
SAMPLE_FILE = BASE_DIR / "sample_data.sql"


def get_database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    host = os.getenv("DB_HOST")
    if host:
        user = os.getenv("DB_USER", "root")
        pwd = os.getenv("DB_PASSWORD", "")
        port = os.getenv("DB_PORT", "3306")
        name = os.getenv("DB_NAME", "urjasense")
        return f"mysql+pymysql://{user}:{pwd}@{host}:{port}/{name}?charset=utf8mb4"
    return "sqlite:///" + str(BASE_DIR / "urjasense_local.db")


def make_engine(url: str | None = None) -> Engine:
    url = url or get_database_url()
    kwargs = {"future": True, "pool_pre_ping": True}
    if url.startswith("mysql"):
        kwargs.update(pool_size=10, pool_recycle=1800)
    else:
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):
        from sqlalchemy import event

        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _):
            dbapi_conn.execute("PRAGMA foreign_keys=ON")
    return engine


def is_mysql(engine: Engine) -> bool:
    return engine.dialect.name == "mysql"


def _split_statements(sql: str) -> list[str]:
    sql = re.sub(r"--[^\n]*", "", sql)  # strip line comments
    return [s.strip() for s in sql.split(";") if s.strip()]


def _to_sqlite(stmt: str) -> str | None:
    """Translate the portable MySQL subset to SQLite (tests / local demo only)."""
    upper = stmt.upper()
    if upper.startswith("CREATE DATABASE") or upper.startswith("USE "):
        return None
    stmt = re.sub(r"\)\s*ENGINE=\w+.*$", ")", stmt, flags=re.S)
    stmt = re.sub(r"INT AUTO_INCREMENT PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT", stmt)
    stmt = re.sub(r"DECIMAL\(\d+,\d+\)", "REAL", stmt)
    return stmt


def run_sql_file(engine: Engine, path: Path) -> None:
    statements = _split_statements(path.read_text(encoding="utf-8"))
    with engine.begin() as conn:
        for stmt in statements:
            if not is_mysql(engine):
                stmt = _to_sqlite(stmt)
                if stmt is None:
                    continue
            elif stmt.upper().startswith(("CREATE DATABASE", "USE ")):
                continue  # database is chosen through the connection URL
            conn.execute(text(stmt))


def init_database(engine: Engine | None = None, with_sample_data: bool = True) -> Engine:
    engine = engine or make_engine()
    run_sql_file(engine, SCHEMA_FILE)
    if with_sample_data:
        run_sql_file(engine, SAMPLE_FILE)
    return engine


if __name__ == "__main__":
    eng = make_engine()
    sample = os.getenv("LOAD_SAMPLE_DATA", "1") == "1"
    init_database(eng, with_sample_data=sample)
    if sample:
        from database.seed_historical import seed_historical
        print("Seeded", seed_historical(eng), "SIMULATED historical outage rows")
    print("Database initialised:", eng.url.render_as_string(hide_password=True))
