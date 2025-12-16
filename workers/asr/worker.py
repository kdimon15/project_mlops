import json
import logging
import math
import os
import time
from datetime import datetime
from urllib.parse import urlparse

import psycopg2
import torch
from huggingface_hub import login
from kafka import KafkaConsumer, KafkaProducer
from transformers import AutoModel

try:
    from api.metrics import inc_task_status
except Exception:
    def inc_task_status(_: str) -> None:  # fallback no-op
        return None

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("asr-worker")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@postgres:5432/callscribe")
KAFKA_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
DIARIZATION_TOPIC = os.getenv("KAFKA_DIARIZATION_TOPIC") or os.getenv("KAFKA_AUDIO_TOPIC", "audio-topic")
TRANSCRIPTION_TOPIC = os.getenv("KAFKA_TRANSCRIPTION_TOPIC", "transcription-topic")
HF_TOKEN = os.getenv("HF_TOKEN")
ASR_MODEL_ID = os.getenv("ASR_MODEL_ID", "ai-sage/GigaAM-v3")
ASR_MODEL_REVISION = os.getenv("ASR_MODEL_REVISION", "e2e_rnnt")

# GigaAM-v3 написан с кастомным .transcribe через trust_remote_code
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
DTYPE = torch.float16 if torch.cuda.is_available() else torch.float32

pending_transcriptions: dict[str, dict] = {}


def db_connect():
    parsed = urlparse(DATABASE_URL)
    return psycopg2.connect(
        dbname=parsed.path.lstrip("/"),
        user=parsed.username,
        password=parsed.password,
        host=parsed.hostname,
        port=parsed.port,
    )


def update_task(
    task_id: str,
    status: str = None,
    progress: int = None,
    transcription: str = None,
    language: str = None,
    duration_seconds: float = None,
    segments: str = None,
    error_message: str = None,
):
    conn = db_connect()
    try:
        with conn:
            with conn.cursor() as cur:
                fields = []
                params = {}
                if status:
                    fields.append("status = %(status)s")
                    params["status"] = status
                    inc_task_status(status)
                if progress is not None:
                    fields.append("progress = %(progress)s")
                    params["progress"] = progress
                if transcription is not None:
                    fields.append("transcription = %(transcription)s")
                    params["transcription"] = transcription
                if language is not None:
                    fields.append("language = %(language)s")
                    params["language"] = language
                if duration_seconds is not None:
                    fields.append("duration_seconds = %(duration_seconds)s")
                    params["duration_seconds"] = int(duration_seconds)
                if segments is not None:
                    fields.append("transcription_segments = %(segments)s")
                    params["segments"] = segments
                if error_message:
                    fields.append("error_message = %(error_message)s")
                    params["error_message"] = error_message
                if status in {"completed", "failed"}:
                    fields.append("completed_at = %(updated_at)s")
                if fields:
                    params["task_id"] = task_id
                    cur.execute(
                        f"UPDATE tasks SET {', '.join(fields)}, updated_at = %(updated_at)s WHERE id = %(task_id)s",
                        {**params, "updated_at": datetime.utcnow()},
                    )
    finally:
        conn.close()


def load_asr_pipeline():
    if HF_TOKEN:
        login(HF_TOKEN, add_to_git_credential=False)

    logger.info(
        "Loading ASR model: %s (rev=%s, device=%s)",
        ASR_MODEL_ID,
        ASR_MODEL_REVISION,
        DEVICE,
    )
    model = AutoModel.from_pretrained(
        ASR_MODEL_ID,
        revision=ASR_MODEL_REVISION,
        trust_remote_code=True,
        dtype=DTYPE,
        device_map="auto" if torch.cuda.is_available() else None,
    )
    model.to(DEVICE)
    return model


def finalize_transcription(task_id: str, producer: KafkaProducer):
    entry = pending_transcriptions.pop(task_id, None)
    if not entry or not entry["segments"]:
        return

    segments_data = sorted(entry["segments"].values(), key=lambda seg: seg["start_time"])
    final_lines = []
    segments_payload = []
    max_end = 0.0

    for segment in segments_data:
        speaker_label = segment.get("speaker_label") or "Спикер 1"
        text = segment.get("text", "").strip()
        final_lines.append(f"{speaker_label}: {text}")
        start = segment.get("start_time", 0.0)
        end = segment.get("end_time", start)
        segments_payload.append(
            {
                "start": start,
                "end": end,
                "text": text,
                "speaker": speaker_label,
            }
        )
        max_end = max(max_end, end)

    transcription_text = "\n".join(line for line in final_lines if line.strip())
    segments_json = json.dumps(segments_payload, ensure_ascii=False)
    duration_seconds = math.ceil(max_end) if segments_payload else 0

    update_task(
        task_id,
        status="processing",
        progress=70,
        transcription=transcription_text,
        segments=segments_json,
        duration_seconds=duration_seconds,
        language=entry.get("language", "auto"),
    )

    future = producer.send(
        TRANSCRIPTION_TOPIC,
        {
            "task_id": task_id,
            "transcription": transcription_text,
            "language": entry.get("language", "auto"),
        },
    )
    future.get(timeout=10)
    producer.flush()
    update_task(task_id, status="processing", progress=85)
    logger.info("Task %s sent to transcription-topic", task_id)


def main():
    asr_model = load_asr_pipeline()

    logger.info("Starting ASR worker. Subscribing to %s", DIARIZATION_TOPIC)
    consumer = KafkaConsumer(
        DIARIZATION_TOPIC,
        group_id="asr-worker",
        bootstrap_servers=KAFKA_SERVERS.split(","),
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        auto_offset_reset="earliest",
        enable_auto_commit=True,
    )
    producer = KafkaProducer(
        bootstrap_servers=KAFKA_SERVERS.split(","),
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    )

    for msg in consumer:
        payload = msg.value
        task_id = payload.get("task_id")
        segment_path = payload.get("file_path")
        language = payload.get("language", "auto")
        speaker_label = payload.get("speaker_label")
        start_time = float(payload.get("start_time", 0.0))
        end_time = float(payload.get("end_time", start_time))
        total_segments = int(payload.get("total_segments") or 0)
        segment_index = payload.get("segment_index")
        try:
            if segment_index is not None:
                segment_index = int(segment_index)
            else:
                segment_index = len(pending_transcriptions.get(task_id, {}).get("segments", {}))
        except (TypeError, ValueError):
            segment_index = len(pending_transcriptions.get(task_id, {}).get("segments", {}))

        logger.info("Received diarized segment %s for task %s", segment_index, task_id)

        if not task_id or not segment_path or not os.path.exists(segment_path):
            logger.error("Invalid segment payload: %s", payload)
            if task_id:
                update_task(task_id, status="failed", progress=0)
            continue

        if task_id not in pending_transcriptions:
            update_task(task_id, status="processing", progress=25, language=language)

        entry = pending_transcriptions.setdefault(
                task_id,
            {
                "segments": {},
                "processed": 0,
                "total": total_segments or 1,
                "language": language,
            },
        )
        entry["total"] = max(entry.get("total", 1), total_segments or 1)
        if language and language != "auto":
            entry["language"] = language

        def transcribe_one(path: str) -> str:
            kwargs = {}
            if language and language != "auto":
                kwargs["language"] = language
            text = asr_model.transcribe(path, **kwargs)
            if isinstance(text, dict) and "text" in text:
                text = text["text"]
            return (text or "").strip()

        try:
            transcription_text = transcribe_one(segment_path)
            if segment_index in entry["segments"]:
                logger.warning("Segment %s already processed for task %s", segment_index, task_id)
            else:
                entry["processed"] += 1
            entry["segments"][segment_index] = {
                "start_time": start_time,
                "end_time": end_time,
                "speaker_label": speaker_label or "Спикер 1",
                "text": transcription_text,
            }

            logger.info(
                "Task %s segment %s/%s transcribed", task_id, entry["processed"], entry["total"]
            )

            if entry["total"] and entry["processed"] >= entry["total"]:
                finalize_transcription(task_id, producer)

        except Exception as exc:
            logger.exception("Failed to transcribe segment for task %s", task_id)
            update_task(task_id, status="failed", error_message=str(exc))
            pending_transcriptions.pop(task_id, None)
        finally:
            try:
                os.remove(segment_path)
            except OSError:
                logger.warning("Failed to delete segment file %s", segment_path)
        time.sleep(0.1)


if __name__ == "__main__":
    main()
