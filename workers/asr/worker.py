import json
import logging
import os
import shutil
import subprocess
import time
import tempfile
from glob import glob
from datetime import datetime
from urllib.parse import urlparse

import psycopg2
import torch
from huggingface_hub import login
from kafka import KafkaConsumer, KafkaProducer
from transformers import AutoModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("asr-worker")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@postgres:5432/callscribe")
KAFKA_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
AUDIO_TOPIC = os.getenv("KAFKA_AUDIO_TOPIC", "audio-topic")
TRANSCRIPTION_TOPIC = os.getenv("KAFKA_TRANSCRIPTION_TOPIC", "transcription-topic")
HF_TOKEN = os.getenv("HF_TOKEN")
ASR_MODEL_ID = os.getenv("ASR_MODEL_ID", "ai-sage/GigaAM-v3")
ASR_MODEL_REVISION = os.getenv("ASR_MODEL_REVISION", "e2e_rnnt")

# GigaAM-v3 написан с кастомным .transcribe через trust_remote_code
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
DTYPE = torch.float16 if torch.cuda.is_available() else torch.float32
SEGMENT_SECONDS = int(os.getenv("ASR_SEGMENT_SECONDS", "24"))


def db_connect():
    parsed = urlparse(DATABASE_URL)
    return psycopg2.connect(
        dbname=parsed.path.lstrip("/"),
        user=parsed.username,
        password=parsed.password,
        host=parsed.hostname,
        port=parsed.port,
    )


def update_task(task_id: str, status: str = None, progress: int = None, transcription: str = None, language: str = None):
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
                if transcription is not None:
                    fields.append("transcription = %(transcription)s")
                    params["transcription"] = transcription
                if language is not None:
                    fields.append("language = %(language)s")
                    params["language"] = language
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
        torch_dtype=DTYPE,
        device_map="auto" if torch.cuda.is_available() else None,
    )
    model.to(DEVICE)
    return model


def get_duration(path: str) -> float:
    try:
        out = subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                path,
            ]
        )
        return float(out.strip())
    except Exception:
        return 0.0


def split_audio(path: str, segment_seconds: int) -> list[str]:
    tmp_dir = tempfile.mkdtemp(prefix="asr_segments_")
    out_tpl = os.path.join(tmp_dir, "seg_%03d.wav")
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        path,
        "-ac",
        "1",
        "-ar",
        "16000",
        "-f",
        "segment",
        "-segment_time",
        str(segment_seconds),
        "-c:a",
        "pcm_s16le",
        out_tpl,
    ]
    subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    segments = sorted(glob(os.path.join(tmp_dir, "seg_*.wav")))
    return segments, tmp_dir


def main():
    asr_model = load_asr_pipeline()

    logger.info("Starting ASR worker. Subscribing to %s", AUDIO_TOPIC)
    consumer = KafkaConsumer(
        AUDIO_TOPIC,
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
        file_path = payload.get("file_path")
        language = payload.get("language", "auto")
        logger.info("Received audio task %s (lang=%s, file=%s)", task_id, language, file_path)

        if not task_id or not file_path or not os.path.exists(file_path):
            logger.error("Invalid payload: %s", payload)
            if task_id:
                update_task(task_id, status="failed", progress=0)
            continue

        try:
            update_task(task_id, status="processing", progress=25, language=language)

            transcribe_kwargs = {}
            if language and language != "auto":
                transcribe_kwargs["language"] = language

            duration = get_duration(file_path)

            def transcribe_one(path: str) -> str:
                text = asr_model.transcribe(path, **transcribe_kwargs)
                if isinstance(text, dict) and "text" in text:
                    text = text["text"]
                return text or ""

            if duration > SEGMENT_SECONDS:
                logger.info(
                    "Splitting long audio (%.1fs) for task %s into %ds chunks",
                    duration,
                    task_id,
                    SEGMENT_SECONDS,
                )
                segments, tmp_dir = split_audio(file_path, SEGMENT_SECONDS)
                parts = []
                try:
                    for idx, seg in enumerate(segments, start=1):
                        part_text = transcribe_one(seg)
                        logger.info("Task %s chunk %d/%d done", task_id, idx, len(segments))
                        parts.append(part_text)
                    transcription = "\n".join(parts).strip()
                finally:
                    shutil.rmtree(tmp_dir, ignore_errors=True)
            else:
                transcription = transcribe_one(file_path)

            update_task(task_id, status="processing", progress=70, transcription=transcription, language=language)

            producer.send(
                TRANSCRIPTION_TOPIC,
                {
                    "task_id": task_id,
                    "transcription": transcription,
                    "language": language,
                },
            )
            update_task(task_id, status="processing", progress=85)
            logger.info("Task %s sent to transcription-topic", task_id)
        except Exception as e:
            logger.exception("Failed to process task %s: %s", task_id, e)
            update_task(task_id, status="failed")
        time.sleep(0.1)


if __name__ == "__main__":
    main()

