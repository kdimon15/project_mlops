# Сервис транскрибации и суммаризации звонков

## Бизнес-ценность

### Проблема
- **40% рабочего времени** тратится на встречи и созвоны
- Сотрудники не могут присутствовать на всех релевантных встречах
- Важная информация теряется или передается неточно
- Отсутствует единая база знаний по обсуждениям и решениям

### Решение
**CallScribe** — MLOps-сервис, который автоматически:
1. **Транскрибирует** аудио/видео звонки в текст (GigaAM)
2. **Суммаризирует** содержание через LLM (Gemma 1.5B на Ollama)
3. **Сохраняет** результаты для поиска и аналитики

### Интеграция с Kontur Talk
Сервис интегрируется с **Kontur Talk** — корпоративной платформой для видеоконференций. Записи звонков автоматически передаются на обработку через API интеграцию.

### Ценность для бизнеса
| Метрика | До внедрения | После внедрения |
|---------|--------------|-----------------|
| Время на обработку 1 часа записи | 2-3 часа | 5-10 минут |
| Охват информации сотрудником | 30-40% встреч | 100% |
| Поиск информации по прошлым встречам | Затруднен | Мгновенный |

---

## Функциональные требования

### Источники данных
- Загрузка файлов через веб-интерфейс (Streamlit)
- Автоматическое получение записей через API Kontur Talk
- Webhook-интеграция для новых записей из Kontur Talk

### Загрузка и обработка файлов
- Поддержка аудио: MP3, WAV, OGG, M4A
- Поддержка видео: MP4, MKV, WebM
- Максимальный размер файла — 500 МБ
- Автоматическое извлечение аудио из видео

### Транскрибация (ASR)
- Распознавание речи на русском и английском языках
- Транскрипция с временными метками
- Точность (WER) ≤ 15% на чистых записях
- В выводе явно указывать сегменты, пронумерованные как `Спикер 1`, `Спикер 2` и т.д., чтобы сохранить связь между голосом и текстом.

### Диаризация
- Обнаружение смены голоса, объединение кусочков одного участника и привязка к обозначениям «Спикер N»
- Использование `pydub` для нормализации аудио, разбиения на фреймы и подсчета длительности сегментов перед передачей в модель ASR
- Отдельный `diarization worker` берет аудиофайл из Kafka, выполняет сегментацию через `pydub`, затем публикует сегменты с метками спикеров в очередь ASR
- Поддержка фоновых шумов и перекрывающихся голосов через короткие перекрывающиеся окна при нарезке, оценка громкости и частоты для стабильного распознавания

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
- POST /api/v1/kontur-talk/webhook — webhook для Kontur Talk
- GET /api/v1/tasks/{id} — статус задачи
- GET /api/v1/results/{id} — получение результатов
- Swagger/OpenAPI документация

### UI
- Drag-and-drop загрузка файлов
- Просмотр записей из Kontur Talk
- Отображение статуса обработки в реальном времени
- История обработанных файлов
- Аналитическая панель с графиками

---

## Нефункциональные требования

### Производительность
- Обработка 1 мин аудио ≤ 30 сек
- Генерация саммари ≤ 60 сек
- Пропускная способность ≥ 10 файлов/час
- Время отклика API (p95) ≤ 500 мс

### Надежность
- Uptime ≥ 99%
- Персистентное хранилище данных
- Автоматический перезапуск при падении
- Graceful degradation при недоступности LLM

### Масштабируемость
- Горизонтальное масштабирование через Kafka consumer groups
- Независимое масштабирование ASR и LLM сервисов
- Очередь до 1000 задач

### Безопасность
- Валидация MIME-type и размера файлов
- Docker network isolation
- Конфигурация через .env файлы
- Аутентификация webhook-запросов от Kontur Talk

### Мониторинг
- Prometheus metrics endpoint
- Grafana dashboards
- Structured logging (JSON)
- Алертинг при критических ошибках

### Воспроизводимость
- Запуск одной командой: docker-compose up
- Фиксация версий в requirements.txt
- Документация по развертыванию

---

## Архитектура

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              CallScribe Architecture                            │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ┌──────────────┐                                                               │
│  │              │                                                               │
│  │ Kontur Talk  │──────────┐                                                    │
│  │    (API)     │          │ webhook / polling                                  │
│  │              │          │                                                    │
│  └──────────────┘          │                                                    │
│                            ▼                                                    │
│  ┌──────────┐     ┌──────────────┐     ┌───────────────────────────────────────┐│
│  │          │     │              │     │                Kafka                  ││
│  │ Streamlit│────▶│   FastAPI    │────▶│ ┌─────────┐  ┌─────────┐  ┌─────────┐ ││
│  │    UI    │     │   Gateway    │     │ │ audio   │  │diarizat.│  │transcrip│ ││
│  │          │◀────│              │◀────│ │ -topic  │  │ -topic  │  │ -topic  │ ││
│  └──────────┘     └──────────────┘     │ └─────────┘  └─────────┘  └─────────┘ ││
│       │                  │             └─────┬──────────┬──────────┬───────────┘│
│       │                  │                   │          │          │            │
│       │ upload           ▼                   ▼          ▼          ▼            │
│       │           ┌──────────────┐     ┌──────────┐ ┌──────────┐   ┌──────────┐ │
│       │           │              │     │Diarizat. │ │   ASR    │   │   LLM    │ │
│       └──────────▶│  PostgreSQL  │◀────│  Worker  │ │  Worker  │   │  Worker  │ │
│                   │              │     │ (Pyannote)││ (GigaAM) │   │ (Gemma)  │ │
│                   └──────────────┘     └──────────┘ └──────────┘   └──────────┘ │
│                          │                                 │                    │
│                          │                                 ▼                    │
│                          │                          ┌──────────┐                │
│                          │                          │  Ollama  │                │
│                          │                          │(Gemma1.5B)│               │
│                          │                          └──────────┘                │
│                          ▼                                                      │
│                   ┌──────────────┐     ┌──────────────┐                         │
│                   │  Prometheus  │────▶│   Grafana    │                         │
│                   │              │     │  Dashboards  │                         │
│                   └──────────────┘     └──────────────┘                         │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Источники данных

| Источник | Способ интеграции | Описание |
|----------|-------------------|----------|
| **Streamlit UI** | Прямая загрузка | Пользователь загружает файл через веб-интерфейс |
| **Kontur Talk** | Webhook + API | Автоматическое получение новых записей звонков |

### Компоненты системы

| Компонент | Технология | Назначение |
|-----------|------------|------------|
| **UI** | Streamlit | Веб-интерфейс для загрузки и просмотра |
| **API Gateway** | FastAPI | REST API, валидация, маршрутизация, webhook |
| **Kontur Talk Client** | Python | Интеграция с API Kontur Talk |
| **Message Broker** | Kafka | Асинхронная очередь задач |
| **ASR Worker** | GigaAM | Транскрибация аудио в текст |
| **Diarization Worker** | Python + pydub | Сегментация по спикерам, упорядочивание потоков перед ASR |
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
- **httpx** — HTTP клиент для Kontur Talk API

### ML/AI
- **GigaAM** (OpenAI) — ASR модель
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
│   │   ├── results.py
│   │   └── kontur_talk.py
│   ├── services/
│   │   ├── kafka_producer.py
│   │   ├── database.py
│   │   └── kontur_talk_client.py
│   └── utils/
│       └── file_utils.py
│
├── workers/
│   ├── asr/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── worker.py
│   │   └── GigaAM_model.py
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
│   │   ├── kontur_talk.py
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
    ├── architecture.md
    └── kontur_talk_integration.md
```

---

## Интеграция с Kontur Talk

### Настройка

1. Получите API ключ в настройках Kontur Talk
2. Добавьте в `.env`:
```env
KONTUR_TALK_API_URL=https://api.kontur.ru/talk/v1
KONTUR_TALK_API_KEY=your_api_key
```


### Режимы работы

| Режим | Описание |
|-------|----------|
| **Polling** | Периодический опрос API для получения новых записей |
| **Manual** | Ручной запрос записи по ID через UI |

---

## Запуск

```bash
# Клонирование репозитория
git clone https://github.com/kdimon15/project_mlops.git
cd project_mlops

cp .env.example .env
# Отредактируйте .env, добавив KONTUR_TALK_API_KEY, HF_TOKEN

# Запуск всех сервисов
docker compose up -d

# Проверка статуса
docker compose ps
```

**Важно:** Перед запуском необходимо принять соглашения на Hugging Face для следующих репозиториев:

- [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1)
- [pyannote/segmentation-3.0](https://huggingface.co/pyannote/segmentation-3.0)
- [pyannote/speaker-diarization-community-1](https://huggingface.co/pyannote/speaker-diarization-community-1)

После этого добавьте `HF_TOKEN` в `.env` файл.


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

### Загрузка файла (ручная)
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
  "source": "kontur_talk",
  "meeting_id": "meet_789",
  "transcription": "Полный текст транскрипции...",
  "summary": "Краткое содержание звонка...",
  "key_points": ["Тезис 1", "Тезис 2"],
  "action_items": ["Задача 1", "Задача 2"]
}
```

---

## Prometheus метрики

```
callscribe_files_processed_total{source="upload|kontur_talk"}
callscribe_processing_duration_seconds
callscribe_queue_size
callscribe_errors_total
callscribe_ollama_inference_seconds
callscribe_kontur_talk_webhooks_total
```
