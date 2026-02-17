import logging
import sys
import os
import asyncio
import time
from logging.handlers import RotatingFileHandler
from app.config import settings


class TelegramErrorHandler(logging.Handler):
    """
    Отправляет ERROR/CRITICAL логи админу в Telegram.
    Дедупликация: одинаковые ошибки не чаще раза в 5 минут.
    """

    COOLDOWN = 300  # 5 минут между одинаковыми ошибками

    def __init__(self):
        super().__init__(level=logging.ERROR)
        self._last_sent = {}  # {message_hash: timestamp}

    def emit(self, record):
        if not settings.admin_id:
            return

        msg = self.format(record)
        msg_key = f"{record.name}:{record.lineno}:{record.getMessage()[:100]}"

        now = time.time()
        if now - self._last_sent.get(msg_key, 0) < self.COOLDOWN:
            return
        self._last_sent[msg_key] = now

        # Обрезаем для Telegram (макс 4096 символов)
        text = f"🚨 <b>ERROR</b>\n<pre>{msg[:3900]}</pre>"

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._send(text))
        except RuntimeError:
            pass  # Нет event loop — пропускаем

    @staticmethod
    async def _send(text: str):
        try:
            from app.bot.bot import bot
            await bot.send_message(
                chat_id=settings.admin_id,
                text=text,
                parse_mode="HTML",
            )
        except Exception:
            pass  # Не падаем если не удалось отправить


def setup_logger():
    """
    Настраивает логирование для приложения.
    Логи выводятся в консоль, в файл app.log и критические — админу в Telegram.
    """
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
        "%Y-%m-%d %H:%M:%S"
    )

    # Основной stdout лог
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)

    # Файл-лог (с ротацией: 5МБ на файл, 5 резервных копий)
    try:
        os.makedirs("logs", exist_ok=True)
    except OSError as e:
        print(f"⚠️ Ошибка при создании папки logs: {e}")

    file_handler = RotatingFileHandler(
        "logs/app.log",
        maxBytes=5_000_000,
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)

    # Telegram handler для ошибок
    tg_handler = TelegramErrorHandler()
    tg_handler.setFormatter(formatter)

    # Устанавливаем базовую конфигурацию логирования
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        handlers=[stream_handler, file_handler, tg_handler],
    )

    # Уменьшаем уровень логирования для библиотек
    logging.getLogger("aiogram").setLevel(logging.WARNING)
    logging.getLogger("yookassa").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("aiomysql").setLevel(logging.WARNING)
    logging.getLogger("arq").setLevel(logging.WARNING)

    logger = logging.getLogger(__name__)
    logger.info("✅ Логирование настроено")
