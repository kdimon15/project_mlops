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
    kafka_diarization_topic: str = "diarization-topic"
    kafka_transcription_topic: str = "transcription-topic"
    
    # LLM (OpenAI-compatible API via Ollama)
    llm_api_base_url: str = "http://ollama:11434/v1"
    llm_api_key: str = "ollama"  # Ollama не требует реального ключа
    llm_model: str = "gemma:2b"
    
    # Diarization (pyannote.audio)
    pyannote_model: str = "pyannote/speaker-diarization-3.1"
    pyannote_hf_token: str = ""  # Hugging Face token для доступа к моделям
    diarization_min_speakers: int = 1
    diarization_max_speakers: int = 10
    
    # Kontur Talk Integration
    kontur_talk_api_url: str = ""
    kontur_talk_api_key: str = ""
    kontur_talk_webhook_secret: str = ""

    # Zoom Integration
    zoom_account_id: str = ""
    zoom_client_id: str = ""
    zoom_client_secret: str = ""
    zoom_user_id: str = "me"
    zoom_base_url: str = "https://api.zoom.us"
    zoom_auth_url: str = "https://zoom.us/oauth/token"
    zoom_recording_days_back: int = 30
    
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
