FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y git-lfs && rm -rf /var/lib/apt/lists/*

COPY workers/llm/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY workers/llm/worker.py /app/worker.py

ARG HF_TOKEN
ENV HF_TOKEN=${HF_TOKEN}
ENV HF_HOME=/root/.cache/huggingface

# Прекачиваем LLM-модель (gemma 1B) в образ, чтобы на старте не тянуть сетью
# Хранится в кэше HF; сам инференс продолжает идти через Ollama (LLM worker обращается к Ollama API)
ARG LLM_MODEL_ID=gemma3:1b-it
ARG LLM_MODEL_REVISION=main
RUN python - <<'PY'
import os
from huggingface_hub import snapshot_download

model_id = os.getenv("LLM_MODEL_ID", "gemma3:1b-it")
revision = os.getenv("LLM_MODEL_REVISION", "main")
token = os.getenv("HF_TOKEN", "")

if ":" in model_id:
    print("Skipping HF preload for Ollama-style model id:", model_id)
    raise SystemExit(0)

if not token:
    raise SystemExit("HF_TOKEN обязателен для загрузки модели gemma3:1b (доступ ограничен)")

print("Downloading", model_id, "rev", revision)
snapshot_download(
    repo_id=model_id,
    revision=revision,
    local_dir=f"/root/.cache/huggingface/hub/models--{model_id.replace('/', '--')}",
    resume_download=True,
    token=token,
    allow_patterns=["*"],
    ignore_patterns=["*.gguf"],
)
PY

ENV KAFKA_BOOTSTRAP_SERVERS=kafka:9092
ENV KAFKA_TRANSCRIPTION_TOPIC=transcription-topic
ENV DATABASE_URL=postgresql://postgres:postgres@postgres:5432/callscribe

# Модель LLM тянется через Ollama в рантайме; здесь только код
CMD ["python", "worker.py"]
