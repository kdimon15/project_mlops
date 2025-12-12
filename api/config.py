"""
Конфигурация приложения.
Использует переменные окружения для настройки.
"""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Настройки приложения."""
    
    # API Settings
    app_name: str = "CallScribe API"
    app_version: str = "1.0.0"
    debug: bool = False
    
    # Database
    database_url: str = "postgresql://postgres:postgres@postgres:5432/callscribe"
    
    # Kafka
    kafka_bootstrap_servers: str = "kafka:9092"
    kafka_audio_topic: str = "audio-topic"
    kafka_transcription_topic: str = "transcription-topic"
    
    # LLM (OpenAI-compatible API via Ollama)
    llm_api_base_url: str = "http://ollama:11434/v1"
    llm_api_key: str = "ollama"  # Ollama не требует реального ключа
    llm_model: str = "gemma:2b"
    
    # Kontur Talk Integration
    kontur_talk_api_url: str = "https://api.kontur.ru/talk/v1"
    kontur_talk_api_key: str = ""
    kontur_talk_webhook_secret: str = ""
    
    # File Upload
    max_file_size_mb: int = 500
    allowed_audio_extensions: list[str] = [".mp3", ".wav", ".ogg", ".m4a"]
    allowed_video_extensions: list[str] = [".mp4", ".mkv", ".webm"]
    upload_dir: str = "/tmp/uploads"
    
    # Prometheus
    metrics_enabled: bool = True
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """Получить настройки приложения (кэшируется)."""
    return Settings()
