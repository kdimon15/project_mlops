"""
Роутер для загрузки и транскрибации файлов.
"""
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.orm import Session
import logging
from starlette.concurrency import run_in_threadpool

from api.models.schemas import (
    TaskCreateResponse, 
    Language, 
    TaskSource,
    TaskStatus,
    ErrorResponse
)
from api.services.database import get_db, DatabaseService
from api.services.kafka_producer import get_kafka_producer
from api.utils.file_utils import save_upload_file, delete_file
from api.config import get_settings
from api.metrics import inc_task_created, inc_kafka_enqueue

settings = get_settings()
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["transcribe"])


@router.post(
    "/transcribe",
    response_model=TaskCreateResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid file"},
        500: {"model": ErrorResponse, "description": "Server error"}
    },
    summary="Загрузить файл на транскрибацию",
    description="Загружает аудио/видео файл и создает задачу на транскрибацию и суммаризацию."
)
async def transcribe_file(
    file: UploadFile = File(..., description="Аудио или видео файл"),
    language: Language = Form(default=Language.AUTO, description="Язык для распознавания"),
    db: Session = Depends(get_db)
):
    """
    Загрузить файл на транскрибацию.
    
    - **file**: Аудио (mp3, wav, ogg, m4a) или видео (mp4, mkv, webm) файл
    - **language**: Язык для распознавания (ru, en, auto)
    
    Возвращает ID задачи для отслеживания статуса.
    """
    logger.info(f"Received file: {file.filename}, language: {language}")
    
    # Создаем сервис БД
    db_service = DatabaseService(db)
    
    task = None
    file_path = ""
    try:
        # Создаем задачу в БД
        task = db_service.create_task(
            source=TaskSource.UPLOAD,
            filename=file.filename,
            language=language.value
        )
        inc_task_created(TaskSource.UPLOAD.value)
        
        # Сохраняем файл
        file_path = await save_upload_file(file, task.id)
        
        # Обновляем путь к файлу в БД
        task.file_path = file_path
        db.commit()
        
        # Отправляем задачу в Kafka (блокирующий клиент уводим в threadpool)
        kafka_producer = get_kafka_producer()
        success = await run_in_threadpool(
            kafka_producer.send_audio_task,
            task.id,
            file_path,
            language.value
        )
        inc_kafka_enqueue("audio-topic", success)
        
        if not success:
            logger.error(f"Failed to send task {task.id} to Kafka")
            db_service.update_task_status(
                task.id, 
                TaskStatus.FAILED, 
                error_message="Failed to queue task"
            )
            raise HTTPException(status_code=500, detail="Failed to queue task for processing")
        
        logger.info(f"Task created: {task.id}")
        
        return TaskCreateResponse(
            task_id=task.id,
            status=TaskStatus.QUEUED,
            created_at=task.created_at
        )
        
    except HTTPException:
        # Чистим артефакты при ошибке валидации/публикации
        if task:
            if file_path:
                delete_file(file_path)
            db_service.delete_task(task.id)
        raise
    except Exception as e:
        if task:
            if file_path:
                delete_file(file_path)
            db_service.delete_task(task.id)
        logger.exception(f"Error processing file: {e}")
        raise HTTPException(status_code=500, detail=str(e))
