# Сервис транскрибации и суммаризации звонков

## Бизнес-ценность

### Проблема
- **40% рабочего времени** тратится на встречи и созвоны
- Сотрудники не могут присутствовать на всех релевантных встречах
- Важная информация теряется или передается неточно
- Отсутствует единая база знаний по обсуждениям и решениям

### Решение
**CallScribe** — MLOps-сервис, который автоматически:
1. **Транскрибирует** аудио/видео звонки в текст (Whisper)
2. **Суммаризирует** содержание через LLM (Gemma 1.5B на Ollama)
3. **Сохраняет** результаты для поиска и аналитики

### Ценность для бизнеса
| Метрика | До внедрения | После внедрения |
|---------|--------------|-----------------|
| Время на обработку 1 часа записи | 2-3 часа | 5-10 минут |
| Охват информации сотрудником | 30-40% встреч | 100% |
| Поиск информации по прошлым встречам | Затруднен | Мгновенный |

---

## Функциональные требования

### Загрузка и обработка файлов
- Поддержка аудио: MP3, WAV, OGG, M4A
- Поддержка видео: MP4, MKV, WebM
- Максимальный размер файла — 500 МБ
- Автоматическое извлечение аудио из видео

### Транскрибация (ASR)
- Распознавание речи на русском и английском языках
- Транскрипция с временными метками
- Точность (WER) ≤ 15% на чистых записях

### Суммаризация (LLM)
- Генерация краткого саммари (до 500 слов)
- Выделение ключевых тезисов и решений
- Определение участников и их высказываний
- Формирование списка action items

### Хранение и поиск
- Сохранение транскрипций и саммари в PostgreSQL
- Полнотекстовый поиск по транскрипциям
- Хранение метаданных: дата, длительность, язык
- Фильтрация по дате и статусу

### API
- POST /api/v1/transcribe — загрузка файлов
- GET /api/v1/tasks/{id} — статус задачи
- GET /api/v1/results/{id} — получение результатов
- Swagger/OpenAPI документация

### UI
- Drag-and-drop загрузка файлов
- Отображение статуса обработки в реальном времени
- История обработанных файлов
- Аналитическая панель с графиками


## Архитектура

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CallScribe Architecture                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────┐     ┌──────────────┐     ┌─────────────────────────────────┐  │
│  │          │     │              │     │           Kafka                 │  │
│  │ Streamlit│────▶│   FastAPI    │────▶│  ┌─────────┐  ┌─────────────┐   │  │
│  │    UI    │     │   Gateway    │     │  │ audio   │  │transcription│   │  │
│  │          │◀────│              │◀────│  │ -topic  │  │   -topic    │   │  │
│  └──────────┘     └──────────────┘     │  └─────────┘  └─────────────┘   │  │
│                          │             └──────┬──────────────┬───────────┘  │
│                          │                    │              │              │
│                          ▼                    ▼              ▼              │
│                   ┌──────────────┐     ┌──────────┐   ┌──────────┐          │
│                   │              │     │  ASR     │   │   LLM    │          │
│                   │  PostgreSQL  │◀────│  Worker  │   │  Worker  │          │
│                   │              │     │ (Whisper)│   │ (Gemma)  │          │
│                   └──────────────┘     └──────────┘   └──────────┘          │
│                          │                                 │                │
│                          │                                 ▼                │
│                          │                          ┌──────────┐            │
│                          │                          │  Ollama  │            │
│                          │                          │(Gemma1.5B)│           │
│                          │                          └──────────┘            │
│                          ▼                                                  │
│                   ┌──────────────┐     ┌──────────────┐                     │
│                   │  Prometheus  │────▶│   Grafana    │                     │
│                   │              │     │  Dashboards  │                     │
│                   └──────────────┘     └──────────────┘                     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Компоненты системы

| Компонент | Технология | Назначение |
|-----------|------------|------------|
| **UI** | Streamlit | Веб-интерфейс для загрузки и просмотра |
| **API Gateway** | FastAPI | REST API, валидация, маршрутизация |
| **Message Broker** | Kafka | Асинхронная очередь задач |
| **ASR Worker** | Whisper | Транскрибация аудио в текст |
| **LLM Worker** | Gemma 1.5B (Ollama) | Суммаризация и извлечение тезисов |
| **Database** | PostgreSQL | Хранение данных |
| **Monitoring** | Prometheus + Grafana | Метрики и визуализация |

---

## Технологический стек

### Backend
- **Python 3.10+** — основной язык
- **FastAPI** — веб-фреймворк
- **Pydantic** — валидация данных
- **SQLAlchemy** — ORM

### ML/AI
- **Whisper** (OpenAI) — ASR модель
- **Gemma 1.5B** — LLM для суммаризации (локально через Ollama)
- **Ollama** — локальный inference сервер для LLM
- **FFmpeg** — обработка аудио/видео

### Infrastructure
- **Docker & Docker Compose** — контейнеризация
- **Kafka** — брокер сообщений
- **PostgreSQL** — СУБД
- **Ollama** — локальный LLM сервер

### Monitoring
- **Prometheus** — сбор метрик
- **Grafana** — визуализация

### Frontend
- **Streamlit** — веб-интерфейс

---

## Структура проекта

```
project_mlops/
├── docker-compose.yml
├── .env.example
├── .gitignore
├── readme.md
│
├── api/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py
│   ├── config.py
│   ├── models/
│   │   └── schemas.py
│   ├── routers/
│   │   ├── transcribe.py
│   │   ├── tasks.py
│   │   └── results.py
│   ├── services/
│   │   ├── kafka_producer.py
│   │   └── database.py
│   └── utils/
│       └── file_utils.py
│
├── workers/
│   ├── asr/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── worker.py
│   │   └── whisper_model.py
│   └── llm/
│       ├── Dockerfile
│       ├── requirements.txt
│       ├── worker.py
│       └── ollama_client.py
│
├── ui/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app.py
│   ├── pages/
│   │   ├── upload.py
│   │   ├── history.py
│   │   └── analytics.py
│   └── components/
│       └── sidebar.py
│
├── monitoring/
│   ├── prometheus/
│   │   └── prometheus.yml
│   └── grafana/
│       ├── provisioning/
│       │   ├── dashboards/
│       │   │   └── dashboard.yml
│       │   └── datasources/
│       │       └── datasource.yml
│       └── dashboards/
│           ├── system.json
│           └── ml_metrics.json
│
├── database/
│   └── init.sql
│
└── docs/
    └── architecture.md
```

---

## Запуск

```bash
# Клонирование репозитория
git clone https://github.com/kdimon15/project_mlops.git
cd project_mlops

# Копирование конфигурации
cp .env.example .env

# Запуск Ollama и загрузка модели Gemma
docker run -d --name ollama -p 11434:11434 ollama/ollama
docker exec ollama ollama pull gemma:2b

# Запуск всех сервисов
docker-compose up -d

# Проверка статуса
docker-compose ps
```

### Доступ к сервисам

| Сервис | URL |
|--------|-----|
| **UI** | http://localhost:8501 |
| **API** | http://localhost:8000 |
| **Swagger** | http://localhost:8000/docs |
| **Grafana** | http://localhost:3000 |
| **Ollama** | http://localhost:11434 |

---

## API примеры

### Загрузка файла
```http
POST /api/v1/transcribe
Content-Type: multipart/form-data

file: <audio/video file>
language: ru
```

### Получение результатов
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "transcription": "Полный текст транскрипции...",
  "summary": "Краткое содержание звонка...",
  "key_points": ["Тезис 1", "Тезис 2"],
  "action_items": ["Задача 1", "Задача 2"]
}
```

---

## Prometheus метрики

```
callscribe_files_processed_total
callscribe_processing_duration_seconds
callscribe_queue_size
callscribe_errors_total
callscribe_ollama_inference_seconds
```
