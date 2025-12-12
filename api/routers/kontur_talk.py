"""
Роутер для интеграции с Kontur Talk.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
import logging
import os

from api.models.schemas import (
    TaskCreateResponse,
    KonturTalkWebhookRequest,
    TaskSource,
    TaskStatus,
    ErrorResponse
)
from api.services.database import get_db, DatabaseService
from api.services.kafka_producer import get_kafka_producer
from api.services.kontur_talk_client import get_kontur_talk_client
from api.config import get_settings
from api.metrics import inc_task_created, inc_kafka_enqueue

settings = get_settings()
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/kontur-talk", tags=["kontur-talk"])


@router.post(
    "/webhook",
    response_model=TaskCreateResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        500: {"model": ErrorResponse, "description": "Server error"}
    },
    summary="Webhook от Kontur Talk",
    description="Принимает уведомления о новых записях от Kontur Talk."
)
async def kontur_talk_webhook(
    request: Request,
    webhook_data: KonturTalkWebhookRequest,
    db: Session = Depends(get_db)
):
    """
    Webhook endpoint для Kontur Talk.
    
    Принимает события:
    - **recording.completed**: Новая запись готова к обработке
    """
    logger.info(f"Received webhook: event={webhook_data.event}, recording_id={webhook_data.recording_id}")
    
    # Обрабатываем только события завершения записи
    if webhook_data.event != "recording.completed":
        logger.info(f"Ignoring event: {webhook_data.event}")
        return TaskCreateResponse(
            task_id="ignored",
            status=TaskStatus.QUEUED,
        )
    
    kontur_client = get_kontur_talk_client()
    db_service = DatabaseService(db)
    
    try:
        # Создаем задачу в БД
        task = db_service.create_task(
            source=TaskSource.KONTUR_TALK,
            meeting_id=webhook_data.meeting_id,
            recording_id=webhook_data.recording_id,
            language="auto"
        )
        inc_task_created(TaskSource.KONTUR_TALK.value)
        
        # Скачиваем запись
        upload_dir = settings.upload_dir
        os.makedirs(upload_dir, exist_ok=True)
        file_path = os.path.join(upload_dir, f"{task.id}.mp4")
        
        download_success = await kontur_client.download_recording(
            webhook_data.recording_id,
            file_path,
            quality="900p"
        )
        
        if not download_success:
            logger.error(f"Failed to download recording {webhook_data.recording_id}")
            db_service.update_task_status(
                task.id,
                TaskStatus.FAILED,
                error_message="Failed to download recording from Kontur Talk"
            )
            raise HTTPException(status_code=500, detail="Failed to download recording")
        
        # Обновляем путь к файлу
        task.file_path = file_path
        task.duration_seconds = webhook_data.duration
        db.commit()
        
        # Отправляем задачу в Kafka
        kafka_producer = get_kafka_producer()
        success = kafka_producer.send_audio_task(
            task_id=task.id,
            file_path=file_path,
            language="auto"
        )
        inc_kafka_enqueue("audio-topic", success)
        
        if not success:
            logger.error(f"Failed to send task {task.id} to Kafka")
            db_service.update_task_status(
                task.id,
                TaskStatus.FAILED,
                error_message="Failed to queue task"
            )
            raise HTTPException(status_code=500, detail="Failed to queue task")
        
        logger.info(f"Task created from Kontur Talk webhook: {task.id}")
        
        return TaskCreateResponse(
            task_id=task.id,
            status=TaskStatus.QUEUED,
            created_at=task.created_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error processing webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
    """
    Получить список записей из Kontur Talk.
    
    - **days_back**: Количество дней назад для поиска (по умолчанию 7)
    - **limit**: Количество записей на страницу (по умолчанию 100)
    - **query**: Поисковый запрос (опционально)
    """
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
    summary="Запустить обработку записи вручную",
    description="Запускает обработку конкретной записи из Kontur Talk по ID."
)
async def process_kontur_talk_recording(
    recording_id: str,
    quality: str = "900p",
    db: Session = Depends(get_db)
):
    """
    Запустить обработку записи из Kontur Talk вручную.
    
    - **recording_id**: ID (ключ) записи в Kontur Talk
    - **quality**: Качество видео для скачивания (900p, 720p, 480p)
    """
    kontur_client = get_kontur_talk_client()
    
    # Получаем информацию о записи
    recording = await kontur_client.get_recording(recording_id)
    
    if not recording:
        raise HTTPException(status_code=404, detail="Recording not found")
    
    db_service = DatabaseService(db)
    
    try:
        # Создаем задачу
        task = db_service.create_task(
            source=TaskSource.KONTUR_TALK,
            meeting_id=recording.meeting_id,
            recording_id=recording.recording_id,
            language="auto"
        )
        inc_task_created(TaskSource.KONTUR_TALK.value)
        
        # Скачиваем запись
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
        
        # Обновляем задачу
        task.file_path = file_path
        task.duration_seconds = recording.duration
        db.commit()
        
        # Отправляем в Kafka
        kafka_producer = get_kafka_producer()
        success = kafka_producer.send_audio_task(task.id, file_path, "auto")
        inc_kafka_enqueue("audio-topic", success)
        
        if not success:
            db_service.update_task_status(
                task.id,
                TaskStatus.FAILED,
                error_message="Failed to queue task"
            )
            raise HTTPException(status_code=500, detail="Failed to queue task")
        
        logger.info(f"Task created from manual request: {task.id} (recording: {recording_id})")
        
        return TaskCreateResponse(
            task_id=task.id,
            status=TaskStatus.QUEUED,
            created_at=task.created_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error processing recording {recording_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
