"""
Роутер для интеграции с Kontur Talk (ручные действия и листинг).
Webhook убран за ненадобностью.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import logging
import os
from starlette.concurrency import run_in_threadpool

from api.models.schemas import (
    TaskCreateResponse,
    TaskSource,
    TaskStatus,
    ErrorResponse,
)
from api.services.database import get_db, DatabaseService
from api.services.kafka_producer import get_kafka_producer
from api.services.kontur_talk_client import get_kontur_talk_client
from api.utils.file_utils import delete_file
from api.config import get_settings
from api.metrics import inc_task_created, inc_kafka_enqueue

settings = get_settings()
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/kontur-talk", tags=["kontur-talk"])


@router.get(
    "/recordings",
    summary="Получить список записей из Kontur Talk",
    description="Возвращает список доступных записей из Kontur Talk за последние N дней."
)
async def list_kontur_talk_recordings(
    days_back: int = 7,
    limit: int = 100,
    query: str = None
):
    kontur_client = get_kontur_talk_client()
    recordings = await kontur_client.list_recordings(
        limit=limit,
        days_back=days_back,
        query=query
    )

    return {
        "recordings": [
            {
                "key": r.key,
                "recording_id": r.key,  # Алиас для обратной совместимости с UI
                "title": r.title,
                "created_date": r.created_date,
                "room_name": r.room_name,
                "duration": r.duration
            }
            for r in recordings
        ],
        "total": len(recordings)
    }


@router.post(
    "/recordings/{recording_id}/process",
    response_model=TaskCreateResponse,
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    summary="Запустить обработку записи вручную",
    description="Запускает обработку конкретной записи из Kontur Talk по ID."
)
async def process_kontur_talk_recording(
    recording_id: str,
    quality: str = "900p",
    db: Session = Depends(get_db)
):
    kontur_client = get_kontur_talk_client()
    recording = await kontur_client.get_recording(recording_id)
    if not recording:
        raise HTTPException(status_code=404, detail="Recording not found")

    db_service = DatabaseService(db)
    existing = db_service.get_task_by_recording(recording_id)
    if existing:
        return TaskCreateResponse(
            task_id=existing.id,
            status=existing.status,
            created_at=existing.created_at,
        )

    success = False
    file_path = ""
    try:
        task = db_service.create_task(
            source=TaskSource.KONTUR_TALK,
            meeting_id=recording.meeting_id,
            recording_id=recording.recording_id,
            language="auto"
        )
        inc_task_created(TaskSource.KONTUR_TALK.value)

        upload_dir = settings.upload_dir
        os.makedirs(upload_dir, exist_ok=True)
        file_path = os.path.join(upload_dir, f"{task.id}.mp4")

        download_success = await kontur_client.download_recording(
            recording_id,
            file_path,
            quality=quality
        )
        if not download_success:
            db_service.update_task_status(
                task.id,
                TaskStatus.FAILED,
                error_message="Failed to download recording"
            )
            raise HTTPException(status_code=500, detail="Failed to download recording")

        task.file_path = file_path
        task.duration_seconds = recording.duration
        db.commit()

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
                error_message="Failed to queue task"
            )
            raise HTTPException(status_code=500, detail="Failed to queue task")

        logger.info("Task created from manual request: %s (recording: %s)", task.id, recording_id)
        return TaskCreateResponse(
            task_id=task.id,
            status=TaskStatus.QUEUED,
            created_at=task.created_at
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error processing recording %s: %s", recording_id, e)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if not success and file_path:
            delete_file(file_path)
