# # app/arq_worker.py
# ========================================
# ✅ CRITICAL: Отключить uvloop ДО ВСЕХ импортов!
# ========================================
import sys

if 'uvloop' in sys.modules:
    del sys.modules['uvloop']

sys.modules['uvloop'] = None

import asyncio
asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())

# ========================================
# Теперь безопасно импортировать остальное
# ========================================
import logging
from fastapi import FastAPI
from arq import run_worker, cron
from arq.connections import RedisSettings

from app.config import settings
from app.db.mysql import init_db, close_db
from app.tasks.subscriptions import try_all_autopays
from app.tasks.daily_reset import reset_tokens
from app.tasks.daily_food_reset import reset_daily_food
from app.tasks.broadcast import send_broadcast
from app.tasks.gpt_queue import process_universal_request  # ✅ НОВЫЙ ИМПОРТ
from app.db.redis_client import init_arq_redis
from app.utils.logger import setup_logger

setup_logger()
logger = logging.getLogger(__name__)

app = FastAPI()


async def startup(ctx):
    """Инициализация при запуске воркера"""
    logger.info("🚀 ARQ Worker: инициализация MySQL и Redis")
    await init_db(app)
    await init_arq_redis()
    ctx["app"] = app
    logger.info("✅ ARQ Worker: готов к работе")


async def shutdown(ctx):
    """Завершение работы воркера"""
    logger.info("🔻 ARQ Worker: закрытие соединений")
    await close_db(app)
    logger.info("👋 ARQ Worker: остановлен")


class WorkerSettings:
    """Настройки ARQ воркера"""
    
    functions = [
        try_all_autopays,
        send_broadcast,
        process_universal_request,  # ✅ ОДНА ФУНКЦИЯ ВМЕСТО 4-х
    ]
    
    cron_jobs = [
        cron(reset_daily_food, hour=0, minute=0),
        cron(reset_tokens, hour=3, minute=5),
        cron(try_all_autopays, hour=3, minute=10),
    ]
    
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    
    on_startup = startup
    on_shutdown = shutdown
    
    job_timeout = 120000
    keep_result = 3600
    max_jobs = 20
    
    max_tries = 3
    retry_jobs = True


if __name__ == "__main__":
    logger.info("👷 Запуск ARQ Worker")
    try:
        asyncio.run(run_worker(WorkerSettings))
    except KeyboardInterrupt:
        logger.info("⏹ ARQ Worker остановлен пользователем")
    except Exception as e:
        logger.exception(f"❌ Ошибка при запуске ARQ Worker: {e}")
        raise
