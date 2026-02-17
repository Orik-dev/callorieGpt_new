FROM python:3.11-slim

# Установим системные зависимости
RUN apt-get update && apt-get install -y ffmpeg git default-mysql-client && apt-get clean

WORKDIR /app

# Копируем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код
COPY ./app /app/app
COPY ./app/arq_worker.py /app/arq_worker.py
COPY ./app/init_webhook.py /app/init_webhook.py

ENV PYTHONPATH=/app

# По умолчанию запускаем сервер FastAPI через gunicorn
CMD ["gunicorn", "app.main:app", "--workers=2", "--worker-class=uvicorn.workers.UvicornWorker", "--bind=0.0.0.0:8000"]
