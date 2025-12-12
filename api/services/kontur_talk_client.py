"""
Клиент для интеграции с Kontur Talk API.
ЗАГЛУШКА - реальная интеграция будет реализована позже.
"""
import httpx
import hmac
import hashlib
import logging
from typing import Optional
from dataclasses import dataclass

from api.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


@dataclass
class Recording:
    """Модель записи из Kontur Talk."""
    recording_id: str
    meeting_id: str
    duration: int
    download_url: str
    title: Optional[str] = None
    created_at: Optional[str] = None


class KonturTalkClient:
    """
    Клиент для работы с API Kontur Talk.
    
    ЗАГЛУШКА: Методы возвращают mock-данные.
    Для реальной интеграции необходимо:
    1. Получить документацию API Kontur Talk
    2. Реализовать аутентификацию
    3. Реализовать методы получения записей
    """
    
    def __init__(self):
        self.api_url = settings.kontur_talk_api_url
        self.api_key = settings.kontur_talk_api_key
        self.webhook_secret = settings.kontur_talk_webhook_secret
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Получить HTTP клиент."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.api_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                timeout=30.0
            )
        return self._client
    
    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """
        Проверить подпись webhook запроса от Kontur Talk.
        
        Args:
            payload: Тело запроса в байтах
            signature: Подпись из заголовка X-Kontur-Signature
            
        Returns:
            True если подпись валидна
        """
        if not self.webhook_secret:
            logger.warning("Webhook secret not configured, skipping verification")
            return True
        
        expected_signature = hmac.new(
            self.webhook_secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(expected_signature, signature)
    
    async def get_recording(self, recording_id: str) -> Optional[Recording]:
        """
        Получить информацию о записи по ID.
        
        ЗАГЛУШКА: Возвращает mock-данные.
        
        Args:
            recording_id: ID записи в Kontur Talk
            
        Returns:
            Recording или None если не найдена
        """
        logger.info(f"[STUB] Getting recording: {recording_id}")
        
        # TODO: Реализовать реальный запрос к API
        # client = await self._get_client()
        # response = await client.get(f"/recordings/{recording_id}")
        # ...
        
        # Mock response
        return Recording(
            recording_id=recording_id,
            meeting_id=f"meet_{recording_id[-6:]}",
            duration=3600,
            download_url=f"https://stub.kontur.ru/recordings/{recording_id}/download",
            title="Mock Meeting Recording",
            created_at="2025-12-12T18:00:00Z"
        )
    
    async def download_recording(self, recording_id: str, destination_path: str) -> bool:
        """
        Скачать запись по ID.
        
        ЗАГЛУШКА: Не выполняет реального скачивания.
        
        Args:
            recording_id: ID записи
            destination_path: Путь для сохранения файла
            
        Returns:
            True если скачивание успешно
        """
        logger.info(f"[STUB] Downloading recording {recording_id} to {destination_path}")
        
        # TODO: Реализовать реальное скачивание
        # recording = await self.get_recording(recording_id)
        # if not recording:
        #     return False
        # 
        # client = await self._get_client()
        # async with client.stream("GET", recording.download_url) as response:
        #     with open(destination_path, "wb") as f:
        #         async for chunk in response.aiter_bytes():
        #             f.write(chunk)
        
        return True
    
    async def list_recordings(
        self,
        limit: int = 20,
        offset: int = 0,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None
    ) -> list[Recording]:
        """
        Получить список записей.
        
        ЗАГЛУШКА: Возвращает пустой список.
        
        Args:
            limit: Максимальное количество записей
            offset: Смещение для пагинации
            from_date: Начальная дата (ISO format)
            to_date: Конечная дата (ISO format)
            
        Returns:
            Список записей
        """
        logger.info(f"[STUB] Listing recordings: limit={limit}, offset={offset}")
        
        # TODO: Реализовать реальный запрос к API
        # client = await self._get_client()
        # params = {"limit": limit, "offset": offset}
        # if from_date:
        #     params["from"] = from_date
        # if to_date:
        #     params["to"] = to_date
        # response = await client.get("/recordings", params=params)
        # ...
        
        return []
    
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
