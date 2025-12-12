FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y ffmpeg git-lfs && rm -rf /var/lib/apt/lists/*

COPY workers/asr/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

ARG HF_TOKEN
ENV HF_TOKEN=${HF_TOKEN}
ENV HF_HOME=/root/.cache/huggingface

# Прекачиваем модель GigaAM-v3 (e2e_rnnt) в образ, чтобы на старте не грузить из сети
RUN python - <<'PY'
import os
import subprocess

model_id = "ai-sage/GigaAM-v3"
revision = os.getenv("ASR_MODEL_REVISION", "e2e_rnnt")
token = os.getenv("HF_TOKEN", "")

cmd = [
    "huggingface-cli",
    "download",
    model_id,
    "--revision",
    revision,
    "--local-dir",
    "/root/.cache/huggingface/hub/models--ai-sage--GigaAM-v3",
    "--resume-download",
]
if token:
    cmd.extend(["--token", token])

print("Downloading", model_id, "rev", revision)
subprocess.check_call(cmd)
PY

COPY workers/asr/worker.py /app/worker.py

ENV KAFKA_BOOTSTRAP_SERVERS=kafka:9092
ENV KAFKA_AUDIO_TOPIC=audio-topic
ENV KAFKA_TRANSCRIPTION_TOPIC=transcription-topic
ENV DATABASE_URL=postgresql://postgres:postgres@postgres:5432/callscribe

CMD ["python", "worker.py"]
