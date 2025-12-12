import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.services.database import Base, DatabaseService  # noqa: E402
from api.models.schemas import TaskStatus, TaskSource  # noqa: E402


def test_create_task_enums_lowercase():
    engine = sa.create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)

    db = TestingSession()
    try:
        service = DatabaseService(db)
        task = service.create_task(source=TaskSource.UPLOAD, filename="test.wav")
        assert task.status == TaskStatus.QUEUED
        assert task.source == TaskSource.UPLOAD
        row = db.execute(sa.text("SELECT status, source FROM tasks WHERE id = :id"), {"id": task.id}).fetchone()
        assert row[0] == "queued"
        assert row[1] == "upload"
    finally:
        db.close()

