"""
Kafka Producer для отправки задач на обработку.
"""
from kafka import KafkaProducer
from kafka.errors import KafkaError
import json
import logging
from typing import Optional

from api.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


class KafkaProducerService:
    """Сервис для отправки сообщений в Kafka."""
    
    _instance: Optional['KafkaProducerService'] = None
    _producer: Optional[KafkaProducer] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._producer is None:
            self._connect()
    
    def _connect(self):
        """Подключение к Kafka."""
        try:
            self._producer = KafkaProducer(
                bootstrap_servers=settings.kafka_bootstrap_servers.split(','),
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                key_serializer=lambda k: k.encode('utf-8') if k else None,
                acks='all',
                retries=3,
                retry_backoff_ms=1000
            )
            logger.info(f"Connected to Kafka: {settings.kafka_bootstrap_servers}")
        except KafkaError as e:
            logger.error(f"Failed to connect to Kafka: {e}")
            raise
    
    def send_audio_task(self, task_id: str, file_path: str, language: str = "auto") -> bool:
        """
        Отправить задачу на транскрибацию в audio-topic.
        
        Args:
            task_id: ID задачи
            file_path: Путь к аудио файлу
            language: Язык для распознавания
            
        Returns:
            True если сообщение отправлено успешно
        """
        message = {
            "task_id": task_id,
            "file_path": file_path,
            "language": language,
            "action": "transcribe"
        }
        
        return self._send(settings.kafka_audio_topic, task_id, message)
    
    def send_transcription_task(self, task_id: str, transcription: str) -> bool:
        """
        Отправить задачу на суммаризацию в transcription-topic.
        
        Args:
            task_id: ID задачи
            transcription: Текст транскрипции
            
        Returns:
            True если сообщение отправлено успешно
        """
        message = {
            "task_id": task_id,
            "transcription": transcription,
            "action": "summarize"
        }
        
        return self._send(settings.kafka_transcription_topic, task_id, message)
    
    def _send(self, topic: str, key: str, message: dict) -> bool:
        """Отправить сообщение в топик."""
        try:
            future = self._producer.send(topic, key=key, value=message)
            # Ждем подтверждения
            record_metadata = future.get(timeout=10)
            logger.info(
                f"Message sent to {topic}: partition={record_metadata.partition}, "
                f"offset={record_metadata.offset}"
            )
            return True
        except KafkaError as e:
            logger.error(f"Failed to send message to {topic}: {e}")
            return False
    
    def close(self):
        """Закрыть соединение."""
        if self._producer:
            self._producer.close()
            self._producer = None
            logger.info("Kafka producer closed")


# Singleton instance
def get_kafka_producer() -> KafkaProducerService:
    """Получить экземпляр Kafka producer."""
    return KafkaProducerService()
