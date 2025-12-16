import hashlib
import json
import logging
import os
import shutil
import tempfile
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import psycopg2
from kafka import KafkaConsumer, KafkaProducer
from pydub import AudioSegment
from pyannote.audio import Pipeline

try:
    from api.metrics import inc_task_status
except Exception:
    def inc_task_status(_: str) -> None:
        return None

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("diarization-worker")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@postgres:5432/callscribe")
KAFKA_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
AUDIO_TOPIC = os.getenv("KAFKA_AUDIO_TOPIC", "audio-topic")
DIARIZATION_TOPIC = os.getenv("KAFKA_DIARIZATION_TOPIC", "diarization-topic")
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/tmp/uploads")
DIARIZATION_MODEL = os.getenv("DIARIZATION_MODEL", "pyannote/speaker-diarization-3.1")
HF_TOKEN = os.getenv("HF_TOKEN", "")


def db_connect():
    parsed = urlparse(DATABASE_URL)
    return psycopg2.connect(
        dbname=parsed.path.lstrip("/"),
        user=parsed.username,
        password=parsed.password,
        host=parsed.hostname,
        port=parsed.port,
    )


def update_task(task_id: str, status: str = None, progress: int = None, error_message: str = None):
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


def load_diarization_pipeline():
    logger.info("Loading diarization model %s", DIARIZATION_MODEL)
    auth_token = HF_TOKEN or None
    return Pipeline.from_pretrained(
        DIARIZATION_MODEL,
        token=auth_token,
        # use_auth_token=auth_token,
    )


def normalize_audio(source_path: str, tmp_dir: str) -> tuple[str, AudioSegment]:
    audio = AudioSegment.from_file(source_path)
    audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)
    normalized_path = os.path.join(tmp_dir, "normalized.wav")
    audio.export(normalized_path, format="wav")
    return normalized_path, audio


def ensure_upload_dir(task_id: str) -> Path:
    target = Path(UPLOAD_DIR) / "diarization" / task_id
    target.mkdir(parents=True, exist_ok=True)
    return target


def speaker_label_map():
    speakers: dict[str, str] = {}

    def label(raw: str) -> str:
        if raw not in speakers:
            speakers[raw] = f"Спикер {len(speakers) + 1}"
        return speakers[raw]

    return label


def main():
    pipeline = load_diarization_pipeline()

    logger.info("Starting diarization worker. Subscribing to %s", AUDIO_TOPIC)
    consumer = KafkaConsumer(
        AUDIO_TOPIC,
        group_id="diarization-worker",
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

        logger.info("Received diarization task %s", task_id)
        if not task_id or not file_path or not os.path.exists(file_path):
            logger.error("Invalid payload for diarization: %s", payload)
            if task_id:
                update_task(task_id, status="failed", error_message="diarization payload missing fields")
            continue

        tmp_dir = tempfile.mkdtemp(prefix="diarization_")
        upload_dir = ensure_upload_dir(task_id)
        update_task(task_id, status="processing", progress=10)

        try:
            normalized_path, audio = normalize_audio(file_path, tmp_dir)
            output = pipeline(normalized_path)
            annotation = output.speaker_diarization
            annotation = annotation.support(collar=0.5)

            segments: list[tuple[float, float, str]] = []
            for segment, _, speaker in annotation.itertracks(yield_label=True):
                start = float(segment.start)
                end = float(segment.end)
                if end <= start:
                    continue
                segments.append((start, end, speaker))

            if not segments:
                duration = len(audio) / 1000.0
                segments = [(0.0, duration, "speaker_1")]

            segments.sort(key=lambda seg: seg[0])
            label_mapper = speaker_label_map()
            total = len(segments)

            for idx, (start, end, speaker_id) in enumerate(segments):
                segment_start_ms = int(start * 1000)
                segment_end_ms = int(end * 1000)
                chunk = audio[segment_start_ms:segment_end_ms]
                if len(chunk) == 0:
                    continue
                segment_path = upload_dir / f"segment_{idx:03d}.wav"
                chunk.export(segment_path, format="wav")
                checksum = hashlib.md5(chunk.raw_data).hexdigest()

                producer.send(
                    DIARIZATION_TOPIC,
                    {
                        "task_id": task_id,
                        "segment_id": f"{task_id}_{idx}",
                        "speaker_id": speaker_id,
                        "speaker_label": label_mapper(speaker_id),
                        "start_time": start,
                        "end_time": end,
                        "duration": end - start,
                        "file_path": str(segment_path),
                        "checksum": checksum,
                        "segment_index": idx,
                        "total_segments": total,
                        "language": language,
                    },
                )

            producer.flush()
            update_task(task_id, progress=35)
            logger.info("Diarization for task %s produced %d segments", task_id, total)
        except Exception as exc:
            logger.exception("Diarization failed for task %s", task_id)
            update_task(task_id, status="failed", error_message=str(exc))
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            try:
                os.remove(file_path)
            except OSError:
                pass
        time.sleep(0.1)


if __name__ == "__main__":
    main()
