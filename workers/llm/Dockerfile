FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y git-lfs && rm -rf /var/lib/apt/lists/*

COPY workers/llm/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY workers/llm/worker.py /app/worker.py

ARG HF_TOKEN
ENV HF_TOKEN=${HF_TOKEN}
ENV HF_HOME=/root/.cache/huggingface

# Прекачиваем LLM-модель (gemma 2B) в образ, чтобы на старте не тянуть сетью
# Хранится в кэше HF; сам инференс продолжает идти через Ollama (LLM worker обращается к Ollama API)
ARG LLM_MODEL_ID=google/gemma-2b
ARG LLM_MODEL_REVISION=main
RUN python - <<'PY'
import os
import subprocess

model_id = os.getenv("LLM_MODEL_ID", "google/gemma-2b")
revision = os.getenv("LLM_MODEL_REVISION", "main")
token = os.getenv("HF_TOKEN", "")

if not token:
    raise SystemExit("HF_TOKEN обязателен для загрузки модели gemma-2b (доступ ограничен)")

cmd = [
    "huggingface-cli",
    "download",
    model_id,
    "--revision",
    revision,
    "--local-dir",
    f"/root/.cache/huggingface/hub/models--{model_id.replace('/', '--')}",
    "--resume-download",
]
if token:
    cmd.extend(["--token", token])

print("Downloading", model_id, "rev", revision)
subprocess.check_call(cmd)
PY

ENV KAFKA_BOOTSTRAP_SERVERS=kafka:9092
ENV KAFKA_TRANSCRIPTION_TOPIC=transcription-topic
ENV DATABASE_URL=postgresql://postgres:postgres@postgres:5432/callscribe

# Модель LLM тянется через Ollama в рантайме; здесь только код
CMD ["python", "worker.py"]
