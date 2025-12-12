import json
import logging
import os
import time
from datetime import datetime
from urllib.parse import urlparse

import psycopg2
import requests
from kafka import KafkaConsumer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("llm-worker")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@postgres:5432/callscribe")
KAFKA_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
TRANSCRIPTION_TOPIC = os.getenv("KAFKA_TRANSCRIPTION_TOPIC", "transcription-topic")
LLM_API_BASE_URL = os.getenv("LLM_API_BASE_URL", "http://ollama:11434")
LLM_MODEL = os.getenv("LLM_MODEL", "gemma:2b")
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "120"))

PROMPT = """Ты — ассистент, который кратко пересказывает встречу и формирует ключевые пункты и action items.
Верни строго JSON следующего формата:
{
  "summary": "краткое резюме в 3-5 предложениях",
  "key_points": ["пункт 1", "пункт 2"],
  "action_items": ["дело 1", "дело 2"]
}
Транскрипт:
{transcription}
"""


def db_connect():
    parsed = urlparse(DATABASE_URL)
    return psycopg2.connect(
        dbname=parsed.path.lstrip("/"),
        user=parsed.username,
        password=parsed.password,
        host=parsed.hostname,
        port=parsed.port,
    )


def update_task(task_id: str, status: str = None, progress: int = None, summary: str = None, key_points=None, action_items=None):
    conn = db_connect()
    try:
        with conn:
            with conn.cursor() as cur:
                fields = []
                params = {}
                if status:
                    fields.append("status = %(status)s")
                    params["status"] = status
                if progress is not None:
                    fields.append("progress = %(progress)s")
                    params["progress"] = progress
                if summary is not None:
                    fields.append("summary = %(summary)s")
                    params["summary"] = summary
                if key_points is not None:
                    fields.append("key_points = %(key_points)s")
                    params["key_points"] = json.dumps(key_points)
                if action_items is not None:
                    fields.append("action_items = %(action_items)s")
                    params["action_items"] = json.dumps(action_items)
                if fields:
                    params["task_id"] = task_id
                    cur.execute(
                        f"UPDATE tasks SET {', '.join(fields)}, updated_at = %(updated_at)s, completed_at = CASE WHEN %(status)s = 'completed' THEN %(updated_at)s ELSE completed_at END WHERE id = %(task_id)s",
                        {**params, "updated_at": datetime.utcnow()},
                    )
    finally:
        conn.close()


def call_ollama(transcription: str):
    url = LLM_API_BASE_URL.rstrip("/") + "/api/chat"
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": "Ты лаконичный ассистент для встречи."},
            {"role": "user", "content": PROMPT.format(transcription=transcription[:4000])},
        ],
        "stream": False,
        "options": {"temperature": 0.2},
    }
    resp = requests.post(url, json=payload, timeout=LLM_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    content = data.get("message", {}).get("content", "").strip()

    summary = ""
    key_points = []
    action_items = []

    try:
        parsed = json.loads(content)
        summary = parsed.get("summary", "").strip()
        key_points = parsed.get("key_points") or []
        action_items = parsed.get("action_items") or []
    except json.JSONDecodeError:
        summary = content
        lines = [ln.strip("-• ").strip() for ln in content.splitlines() if ln.strip()]
        key_points = lines[:3]
        action_items = lines[3:6]

    return summary, key_points, action_items


def main():
    logger.info("Starting LLM worker. Subscribing to %s", TRANSCRIPTION_TOPIC)
    consumer = KafkaConsumer(
        TRANSCRIPTION_TOPIC,
        bootstrap_servers=KAFKA_SERVERS.split(","),
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        auto_offset_reset="earliest",
        enable_auto_commit=True,
    )

    for msg in consumer:
        payload = msg.value
        task_id = payload.get("task_id")
        transcription = payload.get("transcription", "")
        logger.info("Received transcription task %s", task_id)

        if not task_id:
            logger.error("Invalid payload (missing task_id): %s", payload)
            continue

        try:
            update_task(task_id, status="processing", progress=90)
            summary, key_points, action_items = call_ollama(transcription)

            update_task(
                task_id,
                status="completed",
                progress=100,
                summary=summary,
                key_points=key_points,
                action_items=action_items,
            )
            logger.info("Task %s completed by LLM", task_id)
        except Exception as e:
            logger.exception("Failed to process task %s: %s", task_id, e)
            update_task(task_id, status="failed")
        time.sleep(0.1)


if __name__ == "__main__":
    main()

