FROM lintoai/linto-diarization-pyannote:1.1.1

WORKDIR /app

RUN apt-get update && apt-get install -y ffmpeg git git-lfs && rm -rf /var/lib/apt/lists/*

COPY workers/diarization/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY workers/diarization/worker.py /app/worker.py

ENTRYPOINT ["python", "worker.py"]
