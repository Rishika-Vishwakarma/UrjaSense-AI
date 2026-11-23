import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.app import create_app                      # noqa: E402
from backend.utils import rate_limit                    # noqa: E402
from database.database_config import init_database, make_engine  # noqa: E402
from database.seed_historical import seed_historical    # noqa: E402

PW = "Demo@1234"


@pytest.fixture()
def app(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path/'test.db'}")
    init_database(engine)
    seed_historical(engine)
    rate_limit.reset()
    return create_app({"TESTING": True, "SECRET_KEY": "test-secret-key-test-secret-key-12345",
                       "RATE_LIMIT_ENABLED": False}, engine=engine)


@pytest.fixture()
def client(app):
    return app.test_client()


def login(client, email, pw=PW):
    r = client.post("/api/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.get_json()
    return {"Authorization": "Bearer " + r.get_json()["token"]}


@pytest.fixture()
def admin(client):
    return login(client, "admin@urjasense.demo")


@pytest.fixture()
def lineman(client):
    return login(client, "lineman1@urjasense.demo")


@pytest.fixture()
def resident(client):
    return login(client, "resident1@urjasense.demo")


@pytest.fixture()
def resident2(client):
    return login(client, "resident2@urjasense.demo")


def report_payload(app, **over):
    from backend.utils.timeutil import now_local
    from datetime import timedelta
    start = (now_local(330) - timedelta(minutes=20)).strftime("%Y-%m-%dT%H:%M")
    p = {"area_id": 1, "location_text": "Block C, Arera Colony", "outage_start_time": start,
         "issue_details": "Transformer sparking, power gone", "latitude": 23.2136, "longitude": 77.4350}
    p.update(over)
    return p
