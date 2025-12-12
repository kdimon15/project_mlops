"""
Роутер для работы с задачами.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
import logging

from api.models.schemas import (
    TaskStatusResponse,
    TaskListResponse,
    TaskStatus,
    TaskSource,
    ErrorResponse
)
from api.services.database import get_db, DatabaseService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["tasks"])


@router.get(
    "/tasks/{task_id}",
    response_model=TaskStatusResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Task not found"}
    },
    summary="Получить статус задачи",
    description="Возвращает текущий статус задачи по её ID."
)
async def get_task_status(
    task_id: str,
    db: Session = Depends(get_db)
):
    """
    Получить статус задачи.
    
    - **task_id**: ID задачи, полученный при создании
    """
    db_service = DatabaseService(db)
    task = db_service.get_task(task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return TaskStatusResponse(
        task_id=task.id,
        status=task.status,
        progress=task.progress,
        source=task.source,
        created_at=task.created_at,
        updated_at=task.updated_at,
        completed_at=task.completed_at,
        error_message=task.error_message
    )


@router.get(
    "/tasks",
    response_model=TaskListResponse,
    summary="Получить список задач",
    description="Возвращает список задач с пагинацией и фильтрацией."
)
async def list_tasks(
    page: int = Query(default=1, ge=1, description="Номер страницы"),
    page_size: int = Query(default=20, ge=1, le=100, description="Размер страницы"),
    source: Optional[TaskSource] = Query(default=None, description="Фильтр по источнику"),
    status: Optional[TaskStatus] = Query(default=None, description="Фильтр по статусу"),
    db: Session = Depends(get_db)
):
    """
    Получить список задач.
    
    - **page**: Номер страницы (начиная с 1)
    - **page_size**: Количество задач на странице (1-100)
    - **source**: Фильтр по источнику (upload, kontur_talk)
    - **status**: Фильтр по статусу (queued, processing, completed, failed)
    """
    db_service = DatabaseService(db)
    tasks, total = db_service.list_tasks(
        page=page,
        page_size=page_size,
        source=source,
        status=status
    )
    
    task_responses = [
        TaskStatusResponse(
            task_id=task.id,
            status=task.status,
            progress=task.progress,
            source=task.source,
            created_at=task.created_at,
            updated_at=task.updated_at,
            completed_at=task.completed_at,
            error_message=task.error_message
        )
        for task in tasks
    ]
    
    return TaskListResponse(
        tasks=task_responses,
        total=total,
        page=page,
        page_size=page_size
    )
