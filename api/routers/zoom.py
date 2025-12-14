"""
Роутер для интеграции с Zoom (получение записей и запуск обработки).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import logging
import os
from urllib.parse import urlparse
from starlette.concurrency import run_in_threadpool

from api.models.schemas import (
    ZoomRecordingsResponse,
    ZoomProcessRequest,
    TaskCreateResponse,
    TaskStatus,
    TaskSource,
    ErrorResponse,
)
from api.services.database import get_db, DatabaseService
from api.services.kafka_producer import get_kafka_producer
from api.services.zoom_client import get_zoom_client
from api.config import get_settings
from api.metrics import inc_task_created, inc_kafka_enqueue
from api.utils.file_utils import delete_file

settings = get_settings()
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/zoom", tags=["zoom"])


@router.get(
    "/recordings",
    response_model=ZoomRecordingsResponse,
    summary="Получить список записей Zoom",
)
async def list_zoom_recordings():
    client = get_zoom_client()
    try:
        recordings = await client.list_recordings()
        return ZoomRecordingsResponse(recordings=recordings)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(f"Failed to list zoom recordings: {exc}")
        raise HTTPException(status_code=500, detail="Failed to fetch zoom recordings")


@router.post(
    "/recordings/{recording_id}/process",
    response_model=TaskCreateResponse,
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    summary="Запустить обработку файла записи Zoom",
)
async def process_zoom_recording(
    recording_id: str,
    request: ZoomProcessRequest,
    db: Session = Depends(get_db),
):
    parsed = urlparse(request.download_url or "")
    if parsed.scheme not in {"https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="Invalid download_url")
    if not parsed.netloc.endswith("zoom.us"):
        raise HTTPException(status_code=400, detail="download_url must point to zoom.us")

    if not request.download_url:
        raise HTTPException(status_code=400, detail="download_url is required")

    # Не создаем дубликаты
    db_service = DatabaseService(db)
    existing = db_service.get_task_by_recording(recording_id)
    if existing:
        return TaskCreateResponse(
            task_id=existing.id,
            status=existing.status,
            created_at=existing.created_at,
        )

    # Создаем задачу
    db_service = DatabaseService(db)
    task = db_service.create_task(
        source=TaskSource.ZOOM,
        meeting_id=request.meeting_id or recording_id,
        recording_id=recording_id,
        language="auto",
    )
    inc_task_created(TaskSource.ZOOM.value)

    # Скачиваем файл
    upload_dir = settings.upload_dir
    os.makedirs(upload_dir, exist_ok=True)
    ext = request.file_extension or ".mp4"
    if not ext.startswith("."):
        ext = f".{ext}"
    file_path = os.path.join(upload_dir, f"{task.id}{ext}")

    zoom_client = get_zoom_client()
    success = False
    download_ok = await zoom_client.download_recording(request.download_url, file_path)
    if not download_ok:
        db_service.update_task_status(
            task.id,
            TaskStatus.FAILED,
            error_message="Failed to download Zoom recording",
        )
        raise HTTPException(status_code=500, detail="Failed to download recording")

    # Обновляем задачу
    task.file_path = file_path
    task.duration_seconds = request.duration_seconds
    db.commit()

    # Отправляем в Kafka
    kafka_producer = get_kafka_producer()
    success = await run_in_threadpool(
        kafka_producer.send_audio_task,
        task.id,
        file_path,
        "auto",
    )
    inc_kafka_enqueue("audio-topic", success)
    if not success:
        db_service.update_task_status(
            task.id,
            TaskStatus.FAILED,
            error_message="Failed to queue task",
        )
        delete_file(file_path)
        raise HTTPException(status_code=500, detail="Failed to queue task")

    return TaskCreateResponse(
        task_id=task.id,
        status=TaskStatus.QUEUED,
        created_at=task.created_at,
    )
