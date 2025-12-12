FROM python:3.11-slim

WORKDIR /app

# Зависимости UI
COPY ui/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Код UI
COPY ui/ .

# Тесты UI
ENV PYTHONPATH=/app
RUN pytest -q tests

ENV API_BASE_URL=http://api:8000
EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]

