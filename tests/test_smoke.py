import os
import pathlib

# Устанавливаем SQLite БД до импорта приложения
os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/test.db")

from api.main import app  # noqa: E402
from api.services.database import Base, engine  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def setup_module(module):
    db_path = pathlib.Path("/tmp/test.db")
    if db_path.exists():
        db_path.unlink()
    Base.metadata.create_all(bind=engine)


client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json().get("status") == "healthy"


def test_tasks_empty():
    resp = client.get("/api/v1/tasks")
    assert resp.status_code == 200
    data = resp.json()
    assert "tasks" in data
    assert data["tasks"] == []

