FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y git-lfs && rm -rf /var/lib/apt/lists/*

COPY workers/llm/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY workers/llm/worker.py /app/worker.py

ARG HF_TOKEN
ENV HF_TOKEN=${HF_TOKEN}
ENV HF_HOME=/root/.cache/huggingface

ENV KAFKA_BOOTSTRAP_SERVERS=kafka:9092
ENV KAFKA_TRANSCRIPTION_TOPIC=transcription-topic
ENV DATABASE_URL=postgresql://postgres:postgres@postgres:5432/callscribe

# Модель LLM тянется через Ollama в рантайме; здесь только код
CMD ["python", "worker.py"]
