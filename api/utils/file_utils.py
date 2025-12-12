"""
Утилиты для работы с файлами.
"""
import os
import uuid
import magic
import logging
from pathlib import Path
from typing import Optional
from fastapi import UploadFile, HTTPException

from api.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

# MIME types mapping
AUDIO_MIME_TYPES = {
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/ogg": ".ogg",
    "audio/x-m4a": ".m4a",
    "audio/mp4": ".m4a",
}

VIDEO_MIME_TYPES = {
    "video/mp4": ".mp4",
    "video/x-matroska": ".mkv",
    "video/webm": ".webm",
}

ALLOWED_MIME_TYPES = {**AUDIO_MIME_TYPES, **VIDEO_MIME_TYPES}


def get_upload_dir() -> Path:
    """Получить директорию для загрузок, создать если не существует."""
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


def validate_file_type(file_content: bytes, filename: str) -> str:
    """
    Валидация типа файла по содержимому и расширению.
    
    Args:
        file_content: Первые байты файла для определения MIME type
        filename: Имя файла
        
    Returns:
        Определенный MIME type
        
    Raises:
        HTTPException: Если тип файла не поддерживается
    """
    # Определяем MIME type по содержимому
    mime = magic.Magic(mime=True)
    detected_mime = mime.from_buffer(file_content)
    
    # Проверяем расширение
    ext = Path(filename).suffix.lower()
    allowed_extensions = settings.allowed_audio_extensions + settings.allowed_video_extensions
    
    if detected_mime not in ALLOWED_MIME_TYPES:
        logger.warning(f"Unsupported MIME type: {detected_mime} for file {filename}")
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {detected_mime}. Allowed: audio (mp3, wav, ogg, m4a) and video (mp4, mkv, webm)"
        )
    
    if ext not in allowed_extensions:
        logger.warning(f"Unsupported extension: {ext} for file {filename}")
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file extension: {ext}. Allowed: {', '.join(allowed_extensions)}"
        )
    
    return detected_mime


def validate_file_size(file_size: int) -> None:
    """
    Валидация размера файла.
    
    Args:
        file_size: Размер файла в байтах
        
    Raises:
        HTTPException: Если файл слишком большой
    """
    max_size_bytes = settings.max_file_size_mb * 1024 * 1024
    
    if file_size > max_size_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size: {settings.max_file_size_mb} MB"
        )


async def save_upload_file(file: UploadFile, task_id: str) -> str:
    """
    Сохранить загруженный файл.
    
    Args:
        file: Загруженный файл
        task_id: ID задачи для именования
        
    Returns:
        Путь к сохраненному файлу
    """
    upload_dir = get_upload_dir()
    
    # Читаем первые байты для валидации
    content_start = await file.read(8192)
    await file.seek(0)
    
    # Валидация типа
    mime_type = validate_file_type(content_start, file.filename)
    
    # Определяем расширение
    ext = ALLOWED_MIME_TYPES.get(mime_type, Path(file.filename).suffix)
    
    # Генерируем уникальное имя файла
    safe_filename = f"{task_id}{ext}"
    file_path = upload_dir / safe_filename
    
    # Сохраняем файл
    total_size = 0
    with open(file_path, "wb") as f:
        while chunk := await file.read(1024 * 1024):  # 1MB chunks
            total_size += len(chunk)
            validate_file_size(total_size)
            f.write(chunk)
    
    logger.info(f"File saved: {file_path} ({total_size} bytes)")
    return str(file_path)


def delete_file(file_path: str) -> bool:
    """
    Удалить файл.
    
    Args:
        file_path: Путь к файлу
        
    Returns:
        True если файл удален
    """
    try:
        path = Path(file_path)
        if path.exists():
            path.unlink()
            logger.info(f"File deleted: {file_path}")
            return True
        return False
    except Exception as e:
        logger.error(f"Failed to delete file {file_path}: {e}")
        return False


def is_video_file(file_path: str) -> bool:
    """Проверить, является ли файл видео."""
    mime = magic.Magic(mime=True)
    mime_type = mime.from_file(file_path)
    return mime_type in VIDEO_MIME_TYPES


def get_file_extension(file_path: str) -> str:
    """Получить расширение файла."""
    return Path(file_path).suffix.lower()
