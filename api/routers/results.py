"""
Роутер для получения результатов обработки.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import json
import logging

from api.models.schemas import (
    TaskResultResponse,
    TaskStatus,
    TranscriptionSegment,
    ErrorResponse
)
from api.services.database import get_db, DatabaseService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["results"])


@router.get(
    "/results/{task_id}",
    response_model=TaskResultResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Task not found"},
        400: {"model": ErrorResponse, "description": "Task not completed"}
    },
    summary="Получить результаты обработки",
    description="Возвращает транскрипцию и саммари для завершенной задачи."
)
async def get_task_results(
    task_id: str,
    db: Session = Depends(get_db)
):
    """
    Получить результаты обработки задачи.
    
    - **task_id**: ID задачи
    
    Возвращает транскрипцию, саммари, ключевые тезисы и action items.
    Задача должна быть в статусе completed.
    """
    db_service = DatabaseService(db)
    task = db_service.get_task(task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if task.status != TaskStatus.COMPLETED:
        raise HTTPException(
            status_code=400, 
            detail=f"Task is not completed. Current status: {task.status.value}"
        )
    
    # Парсим JSON поля
    segments = None
    if task.transcription_segments:
        try:
            segments_data = json.loads(task.transcription_segments)
            segments = [TranscriptionSegment(**s) for s in segments_data]
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"Failed to parse segments for task {task_id}")
    
    key_points = []
    if task.key_points:
        try:
            key_points = json.loads(task.key_points)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse key_points for task {task_id}")
    
    action_items = []
    if task.action_items:
        try:
            action_items = json.loads(task.action_items)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse action_items for task {task_id}")
    
    return TaskResultResponse(
        task_id=task.id,
        source=task.source,
        meeting_id=task.meeting_id,
        transcription=task.transcription or "",
        segments=segments,
        summary=task.summary or "",
        key_points=key_points,
        action_items=action_items,
        duration_seconds=task.duration_seconds or 0,
        language=task.language or "unknown",
        created_at=task.created_at
    )
