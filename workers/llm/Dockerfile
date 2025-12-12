FROM python:3.11-slim

WORKDIR /app

COPY workers/llm/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY workers/llm/worker.py /app/worker.py

ENV HF_TOKEN=""
ENV KAFKA_BOOTSTRAP_SERVERS=kafka:9092
ENV KAFKA_TRANSCRIPTION_TOPIC=transcription-topic
ENV DATABASE_URL=postgresql://postgres:postgres@postgres:5432/callscribe

CMD ["python", "worker.py"]

