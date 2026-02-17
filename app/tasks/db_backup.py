import logging
import asyncio
import os
from datetime import datetime
from app.config import settings
from app.db.redis_client import redis

logger = logging.getLogger(__name__)

LOCK_TTL = 600  # 10 минут
BACKUP_DIR = "/tmp/db_backups"


async def backup_database(ctx):
    """
    Создаёт дамп MySQL и отправляет админу в Telegram.
    Запускается каждые 6 часов. Distributed lock предотвращает двойное выполнение.
    """
    lock_key = "lock:db_backup"
    acquired = await redis.set(lock_key, "1", ex=LOCK_TTL, nx=True)
    if not acquired:
        logger.info("[Backup] Уже выполняется другим воркером")
        return

    logger.info("[Backup] Запуск бэкапа базы данных...")

    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"backup_{settings.db_name}_{timestamp}.sql"
        filepath = os.path.join(BACKUP_DIR, filename)

        cmd = (
            f"mysqldump -h {settings.db_host} -P {settings.db_port} "
            f"-u {settings.db_user} -p'{settings.db_password}' "
            f"{settings.db_name} > {filepath}"
        )

        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            error = stderr.decode().strip()
            logger.error(f"[Backup] mysqldump failed: {error}")
            return

        file_size = os.path.getsize(filepath)
        logger.info(f"[Backup] Дамп создан: {filename} ({file_size} bytes)")

        # Отправляем админу
        if settings.admin_id:
            try:
                from aiogram.types import FSInputFile
                from app.bot.bot import bot

                doc = FSInputFile(filepath, filename=filename)
                await bot.send_document(
                    chat_id=settings.admin_id,
                    document=doc,
                    caption=f"💾 Бэкап БД: {settings.db_name}\n{timestamp}",
                )
                logger.info("[Backup] Бэкап отправлен админу")
            except Exception as e:
                logger.error(f"[Backup] Не удалось отправить бэкап: {e}")

        # Удаляем файл после отправки
        try:
            os.remove(filepath)
        except OSError:
            pass

    except Exception as e:
        logger.exception(f"[Backup] Ошибка: {e}")
    finally:
        await redis.delete(lock_key)
