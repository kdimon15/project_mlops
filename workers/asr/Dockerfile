FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

COPY workers/asr/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY workers/asr/worker.py /app/worker.py

ENV HF_TOKEN=""
ENV KAFKA_BOOTSTRAP_SERVERS=kafka:9092
ENV KAFKA_AUDIO_TOPIC=audio-topic
ENV KAFKA_TRANSCRIPTION_TOPIC=transcription-topic
ENV DATABASE_URL=postgresql://postgres:postgres@postgres:5432/callscribe

CMD ["python", "worker.py"]

