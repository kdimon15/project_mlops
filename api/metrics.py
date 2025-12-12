"""Прометеус-метрики для приложения."""
from prometheus_client import Counter, Histogram

# HTTP уже собираются в main.py (REQUEST_COUNT / REQUEST_LATENCY)

# Бизнесовые/продуктовые метрики
TASKS_CREATED = Counter(
    "callscribe_tasks_created_total",
    "Количество созданных задач по источнику",
    ["source"],
)

TASK_STATUS_UPDATES = Counter(
    "callscribe_task_status_total",
    "Изменения статусов задач",
    ["status"],
)

KAFKA_ENQUEUE = Counter(
    "callscribe_kafka_enqueue_total",
    "Попытки постановки задач в Kafka",
    ["topic", "result"],  # result: success|failure
)

UPLOAD_FILE_SIZE = Histogram(
    "callscribe_upload_file_size_bytes",
    "Размеры загружаемых файлов",
    buckets=(0.5e6, 2e6, 5e6, 10e6, 50e6, 100e6, 200e6, 500e6),
)


def inc_task_created(source: str) -> None:
    """Инкремент при создании задачи."""
    TASKS_CREATED.labels(source=source).inc()


def inc_task_status(status: str) -> None:
    """Инкремент при смене статуса."""
    TASK_STATUS_UPDATES.labels(status=status).inc()


def inc_kafka_enqueue(topic: str, ok: bool) -> None:
    """Зафиксировать попытку публикации в Kafka."""
    result = "success" if ok else "failure"
    KAFKA_ENQUEUE.labels(topic=topic, result=result).inc()


def observe_upload_size(size_bytes: int) -> None:
    """Зафиксировать размер загруженного файла."""
    UPLOAD_FILE_SIZE.observe(size_bytes)

