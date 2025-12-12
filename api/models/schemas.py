"""Pydantic-схемы и перечисления для API."""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class Language(str, Enum):
    """Поддерживаемые языки распознавания."""

    RU = "ru"
    EN = "en"
    AUTO = "auto"


class TaskStatus(str, Enum):
    """Статусы задачи обработки."""

    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskSource(str, Enum):
    """Источники создания задачи."""

    UPLOAD = "upload"
    KONTUR_TALK = "kontur_talk"


class HealthResponse(BaseModel):
    """Ответ для health-check."""

    status: str = "healthy"
    version: str

    model_config = ConfigDict(use_enum_values=True)


class ErrorResponse(BaseModel):
    """Единый ответ об ошибке."""

    error: str
    detail: Optional[str] = None


class TaskCreateResponse(BaseModel):
    """Ответ при создании задачи."""

    task_id: str
    status: TaskStatus
    created_at: Optional[datetime] = None

    model_config = ConfigDict(use_enum_values=True)


class TaskStatusResponse(BaseModel):
    """Состояние задачи."""

    task_id: str
    status: TaskStatus
    progress: Optional[int] = None
    source: TaskSource
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None

    model_config = ConfigDict(use_enum_values=True)


class TaskListResponse(BaseModel):
    """Список задач с пагинацией."""

    tasks: List[TaskStatusResponse]
    total: int
    page: int
    page_size: int

    model_config = ConfigDict(use_enum_values=True)


class TranscriptionSegment(BaseModel):
    """Сегмент транскрипции."""

    start: Optional[float] = None
    end: Optional[float] = None
    text: str
    speaker: Optional[str] = None

    model_config = ConfigDict(extra="allow")


class TaskResultResponse(BaseModel):
    """Результат обработки задачи."""

    task_id: str
    source: TaskSource
    meeting_id: Optional[str] = None
    transcription: str
    segments: Optional[List[TranscriptionSegment]] = None
    summary: str
    key_points: List[str] = Field(default_factory=list)
    action_items: List[str] = Field(default_factory=list)
    duration_seconds: int = 0
    language: str = "unknown"
    created_at: Optional[datetime] = None

    model_config = ConfigDict(use_enum_values=True)


class KonturTalkWebhookRequest(BaseModel):
    """Запрос от webhook Kontur Talk."""

    event: str
    recording_id: str
    meeting_id: str
    duration: int

    model_config = ConfigDict(use_enum_values=True)

