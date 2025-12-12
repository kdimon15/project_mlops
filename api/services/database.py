"""
Сервис работы с базой данных PostgreSQL.
"""
from sqlalchemy import create_engine, Column, String, Integer, Text, DateTime, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime
from typing import Optional
import uuid

from api.config import get_settings
from api.models.schemas import TaskStatus, TaskSource
from api.metrics import inc_task_status

settings = get_settings()

# SQLAlchemy setup
engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class TaskModel(Base):
    """Модель задачи в БД."""
    __tablename__ = "tasks"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    status = Column(
        SQLEnum(TaskStatus, values_callable=lambda obj: [e.value for e in obj], name="taskstatus"),
        default=TaskStatus.QUEUED.value,
    )
    source = Column(
        SQLEnum(TaskSource, values_callable=lambda obj: [e.value for e in obj], name="tasksource"),
        default=TaskSource.UPLOAD.value,
    )
    progress = Column(Integer, default=0)
    
    # Kontur Talk metadata
    meeting_id = Column(String(255), nullable=True)
    recording_id = Column(String(255), nullable=True)
    
    # File info
    filename = Column(String(255), nullable=True)
    file_path = Column(String(500), nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    language = Column(String(10), default="auto")
    
    # Results
    transcription = Column(Text, nullable=True)
    transcription_segments = Column(Text, nullable=True)  # JSON
    summary = Column(Text, nullable=True)
    key_points = Column(Text, nullable=True)  # JSON
    action_items = Column(Text, nullable=True)  # JSON
    
    # Error handling
    error_message = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)


def get_db() -> Session:
    """Получить сессию БД (dependency injection)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class DatabaseService:
    """Сервис для работы с задачами в БД."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create_task(
        self,
        source: TaskSource,
        filename: Optional[str] = None,
        file_path: Optional[str] = None,
        meeting_id: Optional[str] = None,
        recording_id: Optional[str] = None,
        language: str = "auto"
    ) -> TaskModel:
        """Создать новую задачу."""
        task = TaskModel(
            status=TaskStatus.QUEUED.value,
            source=source.value if isinstance(source, TaskSource) else source,
            filename=filename,
            file_path=file_path,
            meeting_id=meeting_id,
            recording_id=recording_id,
            language=language
        )
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        return task
    
    def get_task(self, task_id: str) -> Optional[TaskModel]:
        """Получить задачу по ID."""
        return self.db.query(TaskModel).filter(TaskModel.id == task_id).first()
    
    def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        progress: int = None,
        error_message: str = None
    ) -> Optional[TaskModel]:
        """Обновить статус задачи."""
        task = self.get_task(task_id)
        if task:
            task.status = status.value if isinstance(status, TaskStatus) else status
            if progress is not None:
                task.progress = progress
            if error_message:
                task.error_message = error_message
            if status == TaskStatus.COMPLETED:
                task.completed_at = datetime.utcnow()
            self.db.commit()
            self.db.refresh(task)
            inc_task_status(status.value if isinstance(status, TaskStatus) else str(status))
        return task
    
    def save_transcription(
        self,
        task_id: str,
        transcription: str,
        segments: str = None,
        duration_seconds: int = None,
        language: str = None
    ) -> Optional[TaskModel]:
        """Сохранить результат транскрибации."""
        task = self.get_task(task_id)
        if task:
            task.transcription = transcription
            task.transcription_segments = segments
            if duration_seconds:
                task.duration_seconds = duration_seconds
            if language:
                task.language = language
            self.db.commit()
            self.db.refresh(task)
        return task
    
    def save_summary(
        self,
        task_id: str,
        summary: str,
        key_points: str,
        action_items: str
    ) -> Optional[TaskModel]:
        """Сохранить результат суммаризации."""
        task = self.get_task(task_id)
        if task:
            task.summary = summary
            task.key_points = key_points
            task.action_items = action_items
            self.db.commit()
            self.db.refresh(task)
        return task
    
    def list_tasks(
        self,
        page: int = 1,
        page_size: int = 20,
        source: Optional[TaskSource] = None,
        status: Optional[TaskStatus] = None
    ) -> tuple[list[TaskModel], int]:
        """Получить список задач с пагинацией."""
        query = self.db.query(TaskModel)
        
        if source:
            query = query.filter(TaskModel.source == source)
        if status:
            query = query.filter(TaskModel.status == status)
        
        total = query.count()
        tasks = query.order_by(TaskModel.created_at.desc())\
            .offset((page - 1) * page_size)\
            .limit(page_size)\
            .all()
        
        return tasks, total


def init_db():
    """Инициализация БД (создание таблиц)."""
    Base.metadata.create_all(bind=engine)
