# app/logger.py
import logging
import sys
from logging.handlers import RotatingFileHandler
from app.config import settings

def setup_logger():
    """
    Настраивает логирование для приложения.
    Логи выводятся в консоль и в файл app.log (с ротацией).
    """
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S"
    )

    # Основной stdout лог
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)

    # Файл-лог (с ротацией: 5МБ на файл, 5 резервных копий)
    # Создайте папку 'logs' в корне проекта, если её нет.
    try:
        os.makedirs("logs", exist_ok=True)
    except OSError as e:
        print(f"Ошибка при создании папки logs: {e}")

    file_handler = RotatingFileHandler("logs/app.log", maxBytes=5_000_000, backupCount=5)
    file_handler.setFormatter(formatter)

    # Устанавливаем базовую конфигурацию логирования
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        handlers=[stream_handler, file_handler],
    )

    # Уменьшаем уровень логирования для некоторых библиотек, чтобы не зашумлять логи
    logging.getLogger("aiogram").setLevel(logging.WARNING)
    logging.getLogger("yookassa").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING) # Логи HTTP-клиента
    logging.getLogger("aiomysql").setLevel(logging.WARNING) # Логи MySQL драйвера
    logging.getLogger("arq").setLevel(logging.WARNING) # Логи ARQ

# Вызываем настройку логгера при импорте модуля
import os
setup_logger()