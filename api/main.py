"""
CallScribe API - Главный модуль приложения.

Сервис транскрибации и суммаризации звонков.
Использует Whisper для ASR и Gemma 1.5B (Ollama) для суммаризации.
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from prometheus_client import make_asgi_app, Counter, Histogram
import logging
import time
import sys
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH для запуска из корня
ROOT_DIR = Path(__file__).parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from api.config import get_settings
from api.models.schemas import HealthResponse, ErrorResponse
from api.services.database import init_db
from api.routers import transcribe, tasks, results, kontur_talk, zoom

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": "%(message)s"}',
    datefmt='%Y-%m-%dT%H:%M:%S'
)
logger = logging.getLogger(__name__)

settings = get_settings()

# Prometheus метрики
REQUEST_COUNT = Counter(
    'callscribe_requests_total',
    'Total number of requests',
    ['method', 'endpoint', 'status']
)
REQUEST_LATENCY = Histogram(
    'callscribe_request_latency_seconds',
    'Request latency in seconds',
    ['method', 'endpoint']
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager для приложения."""
    # Startup
    logger.info("Starting CallScribe API...")
    init_db()
    logger.info("Database initialized")
    
    yield
    
    # Shutdown
    logger.info("Shutting down CallScribe API...")


# Создание приложения
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="""
## CallScribe API

Сервис автоматической транскрибации и суммаризации звонков.

### Возможности:
- 📤 Загрузка аудио/видео файлов
- 🎙️ Транскрибация с помощью Whisper
- 📝 Суммаризация с помощью Gemma 1.5B (Ollama)
- 🔗 Интеграция с Kontur Talk
- 📊 Prometheus метрики

### Источники данных:
- Прямая загрузка через API
- Webhook интеграция с Kontur Talk
    """,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене указать конкретные домены
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Middleware для метрик
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """Middleware для сбора метрик запросов."""
    start_time = time.time()
    
    response = await call_next(request)
    
    # Записываем метрики
    duration = time.time() - start_time
    endpoint = request.url.path
    method = request.method
    status = response.status_code
    
    REQUEST_COUNT.labels(method=method, endpoint=endpoint, status=status).inc()
    REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(duration)
    
    return response


# Обработчик ошибок
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Глобальный обработчик исключений."""
    logger.exception(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="Internal Server Error",
            detail=str(exc) if settings.debug else None
        ).model_dump()
    )


# Подключение роутеров
app.include_router(transcribe.router)
app.include_router(tasks.router)
app.include_router(results.router)
app.include_router(kontur_talk.router)
app.include_router(zoom.router)

# Prometheus metrics endpoint
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


# Health check endpoints
@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["health"],
    summary="Health check",
    description="Проверка работоспособности сервиса."
)
async def health_check():
    """Проверка здоровья сервиса."""
    return HealthResponse(
        status="healthy",
        version=settings.app_version
    )


@app.get(
    "/",
    tags=["health"],
    summary="Root endpoint",
    description="Корневой endpoint с информацией о сервисе."
)
async def root():
    """Корневой endpoint."""
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/health",
        "metrics": "/metrics"
    }


if __name__ == "__main__":
    import uvicorn
    # Запуск из корня проекта: python -m api.main
    # или: uvicorn api.main:app --reload
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug
    )
