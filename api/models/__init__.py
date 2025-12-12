"""Модели данных и схемы для API."""

# Импортируем для удобства внешних модулей
from api.models.schemas import (  # noqa: F401
    Language,
    TaskStatus,
    TaskSource,
    HealthResponse,
    ErrorResponse,
    TaskCreateResponse,
    TaskStatusResponse,
    TaskListResponse,
    TaskResultResponse,
    TranscriptionSegment,
    KonturTalkWebhookRequest,
)

