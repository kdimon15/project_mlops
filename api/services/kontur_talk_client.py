"""
Клиент для интеграции с Kontur Talk API.
"""
import httpx
import logging
from pathlib import Path
from typing import Optional
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from api.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


@dataclass
class Recording:
    """Модель записи из Kontur Talk."""
    key: str
    title: str
    created_date: str
    room_name: str
    duration: int
    recording_id: Optional[str] = None  # Алиас для key
    meeting_id: Optional[str] = None  # Алиас для room_name


class KonturTalkClient:
    """
    Клиент для работы с API Kontur Talk.
    
    Методы:
    - list_recordings: получение списка записей с пагинацией
    - get_recording: получение информации о записи по ID
    - download_recording: скачивание записи в файл
    """
    
    def __init__(self):
        self.api_url = settings.kontur_talk_api_url
        self.api_key = settings.kontur_talk_api_key
        self._client: Optional[httpx.AsyncClient] = None
        
        if not self.api_url or not self.api_key:
            logger.warning("Kontur Talk API URL or API Key not configured")
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Получить HTTP клиент."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers={
                    "X-Auth-Token": self.api_key,
                },
                timeout=60.0
            )
        return self._client
    
    async def list_recordings(
        self,
        start_from: Optional[str] = None,
        start_to: Optional[str] = None,
        query: Optional[str] = None,
        limit: int = 100,
        days_back: int = 7
    ) -> list[Recording]:
        """
        Получить список записей из Kontur Talk.
        
        Проходит по всем страницам через nextPageToken и возвращает все записи.
        
        Args:
            start_from: Начальная дата (ISO format), например '2025-12-01T00:00:00Z'
            start_to: Конечная дата (ISO format)
            query: Поисковый запрос
            limit: Количество записей на страницу (max 1000)
            days_back: Количество дней назад (если start_from не указан)
            
        Returns:
            Список записей
        """
        if not self.api_url or not self.api_key:
            logger.error("Kontur Talk API not configured")
            return []
        
        # Если даты не указаны, берем последние N дней
        if not start_from:
            now = datetime.now(timezone.utc)
            start_from = (now - timedelta(days=days_back)).strftime("%Y-%m-%dT%H:%M:%SZ")
            start_to = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        url = f"{self.api_url.rstrip('/')}/api/Domain/recordings/v2"
        client = await self._get_client()
        
        page_token = None
        all_recordings = []
        page_count = 0
        
        try:
            while True:
                page_count += 1
                params = {"top": min(limit, 1000)}
                
                if start_from:
                    params["startFrom"] = start_from
                if start_to:
                    params["startTo"] = start_to
                if query:
                    params["query"] = query
                if page_token:
                    params["pageTokenString"] = page_token
                
                logger.info(f"Fetching Kontur Talk recordings (page {page_count})")
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()
                
                entities = data.get("entities", [])
                
                for entity in entities:
                    recording = Recording(
                        key=entity.get("key", ""),
                        title=entity.get("title", ""),
                        created_date=entity.get("createdDate", ""),
                        room_name=entity.get("roomName", ""),
                        duration=entity.get("duration", 0),
                        recording_id=entity.get("key", ""),  # Алиас
                        meeting_id=entity.get("roomName", "")  # Алиас
                    )
                    all_recordings.append(recording)
                    if len(all_recordings) >= limit:
                        break
                if len(all_recordings) >= limit:
                    break
                
                page_token = data.get("nextPageToken")
                if not page_token:
                    break
            
            logger.info(f"Fetched {len(all_recordings)} recordings from Kontur Talk ({page_count} pages)")
            return all_recordings
            
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching recordings: {e.response.status_code} - {e.response.text}")
            return []
        except Exception as e:
            logger.exception(f"Error fetching recordings from Kontur Talk: {e}")
            return []
    
    async def get_recording(self, recording_id: str) -> Optional[Recording]:
        """
        Получить информацию о записи по ID.
        
        Args:
            recording_id: ID (ключ) записи в Kontur Talk
            
        Returns:
            Recording или None если не найдена
        """
        # Используем list_recordings с фильтром, так как API может не иметь отдельного endpoint
        recordings = await self.list_recordings(limit=1000, days_back=90)
        
        for recording in recordings:
            if recording.recording_id == recording_id or recording.key == recording_id:
                return recording
        
        logger.warning(f"Recording not found: {recording_id}")
        return None
    
    async def download_recording(
        self,
        recording_key: str,
        destination_path: str,
        quality: str = "900p"
    ) -> bool:
        """
        Скачать запись по ключу.
        
        Args:
            recording_key: Ключ записи (key из API)
            destination_path: Путь для сохранения файла
            quality: Качество видео (например, "900p", "720p", "480p")
            
        Returns:
            True если скачивание успешно
        """
        if not self.api_url or not self.api_key:
            logger.error("Kontur Talk API not configured")
            return False
        
        url = f"{self.api_url.rstrip('/')}/api/Recordings/{recording_key}/file/{quality}"
        
        try:
            client = await self._get_client()
            
            logger.info(f"Downloading recording {recording_key} (quality: {quality})")
            
            # Создаем директорию если не существует
            Path(destination_path).parent.mkdir(parents=True, exist_ok=True)
            
            # Скачиваем файл с streaming
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                
                total_size = int(response.headers.get("content-length", 0))
                downloaded = 0
                
                with open(destination_path, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=1024 * 1024):  # 1MB chunks
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            
                            if total_size > 0:
                                percent = (downloaded / total_size) * 100
                                if downloaded % (10 * 1024 * 1024) == 0:  # Логируем каждые 10MB
                                    logger.debug(f"Downloaded {percent:.1f}% ({downloaded}/{total_size} bytes)")
            
            logger.info(f"Recording downloaded successfully: {destination_path} ({downloaded} bytes)")
            return True
            
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error downloading recording {recording_key}: {e.response.status_code} - {e.response.text}")
            return False
        except Exception as e:
            logger.exception(f"Error downloading recording {recording_key}: {e}")
            return False
    
    async def close(self):
        """Закрыть HTTP клиент."""
        if self._client:
            await self._client.aclose()
            self._client = None


# Singleton instance
_client_instance: Optional[KonturTalkClient] = None


def get_kontur_talk_client() -> KonturTalkClient:
    """Получить экземпляр клиента Kontur Talk."""
    global _client_instance
    if _client_instance is None:
        _client_instance = KonturTalkClient()
    return _client_instance
