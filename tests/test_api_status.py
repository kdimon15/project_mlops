import os
import pathlib

import pytest
from fastapi.testclient import TestClient

# Настраиваем SQLite до импорта приложения
os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/test.db")

from api.main import app  # noqa: E402
from api.services.database import Base, engine  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    db_path = pathlib.Path("/tmp/test.db")
    if db_path.exists():
        db_path.unlink()
    Base.metadata.create_all(bind=engine)
    yield
    if db_path.exists():
        db_path.unlink()


client = TestClient(app)


def test_results_not_found():
    resp = client.get("/api/v1/results/non-existent-id")
    assert resp.status_code == 404


def test_task_status_not_found():
    resp = client.get("/api/v1/tasks/non-existent-id")
    assert resp.status_code == 404

