# ========================================
# ✅ CRITICAL: Отключить uvloop ДО ВСЕХ импортов!
# ========================================
import sys

# Удалить uvloop из sys.modules если он там есть
if 'uvloop' in sys.modules:
    del sys.modules['uvloop']

# Блокировать импорт uvloop
sys.modules['uvloop'] = None

# Принудительно установить стандартный asyncio policy
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
from app.tasks.broadcast import send_broadcast
from app.tasks.gpt_queue import process_gpt_request
from app.db.redis_client import init_arq_redis
from app.utils.logger import setup_logger

# Настройка логов
setup_logger()
logger = logging.getLogger(__name__)

# FastAPI-приложение (для доступа к db_pool)
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
    
    # Обрабатываемые функции
    functions = [
        try_all_autopays,
        send_broadcast,
        process_gpt_request,
    ]
    
    # Крон-задачи (выполняются по расписанию)
    cron_jobs = [
        cron(reset_tokens, hour=3, minute=5),       # Сброс токенов в 03:05 UTC
        cron(try_all_autopays, hour=3, minute=10),  # Автоплатежи в 03:10 UTC
    ]
    
    # Настройки Redis
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    
    # Lifecycle хуки
    on_startup = startup
    on_shutdown = shutdown
    
    # Таймауты и лимиты
    job_timeout = 600        # 10 минут на задачу
    keep_result = 3600       # Хранить результаты 1 час
    max_jobs = 10            # Максимум 10 задач одновременно
    
    # Настройки повторов
    max_tries = 3            # Максимум 3 попытки
    retry_jobs = True        # Включить повторы


if __name__ == "__main__":
    logger.info("👷 Запуск ARQ Worker")
    try:
        asyncio.run(run_worker(WorkerSettings))
    except KeyboardInterrupt:
        logger.info("⏹ ARQ Worker остановлен пользователем")
    except Exception as e:
        logger.exception(f"❌ Ошибка при запуске ARQ Worker: {e}")
        raise