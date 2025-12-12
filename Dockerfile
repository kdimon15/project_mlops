FROM python:3.11-slim

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Рабочая директория
WORKDIR /app

# Копирование зависимостей
COPY requirements.txt .

# Установка Python зависимостей
RUN pip install --no-cache-dir -r requirements.txt

# Копирование кода приложения
COPY api/ ./api/
COPY .env.example .env

# Создание директории для загрузок
RUN mkdir -p /tmp/uploads

# Переменные окружения
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Порт
EXPOSE 8000

# Запуск приложения из корня проекта
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
