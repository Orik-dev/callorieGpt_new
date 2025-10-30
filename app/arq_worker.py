# import logging
# import asyncio
# from fastapi import FastAPI
# from arq import run_worker, cron
# from arq.connections import RedisSettings
# from app.config import settings
# from app.db.mysql import init_db, close_db
# from app.tasks.subscriptions import try_all_autopays
# from app.tasks.daily_reset import reset_tokens
# from app.tasks.broadcast import send_broadcast
# from app.tasks.gpt_queue import process_gpt_request
# from app.tasks.context_cleanup import reset_all_user_contexts
# from app.db.redis_client import init_arq_redis

# # Настройка логов
# logging.basicConfig(level=settings.log_level, format="%(asctime)s [%(levelname)s] %(message)s")
# logger = logging.getLogger(__name__)

# # FastAPI-приложение (используется для доступа к state.db_pool)
# app = FastAPI()

# # Инициализация при запуске
# async def startup(ctx):
#     logger.info("🚀 ARQ Worker: инициализация MySQL")
#     await init_db(app)
#     await init_arq_redis()

#     ctx["app"] = app

# # Завершение работы
# async def shutdown(ctx):
#     logger.info("🔻 ARQ Worker: закрытие MySQL")
#     await close_db(app)

# # Настройки воркера
# class WorkerSettings:
#     functions = [
#         try_all_autopays,
#         send_broadcast,
#         process_gpt_request, 
#         ]

#     cron_jobs = [
#         cron(reset_tokens, hour=3, minute=5),           # 🕛 Обновление токенов каждый день
#         cron(try_all_autopays, hour=3, minute=10),       # 🔁 Попытка автосписания утром
#         cron(reset_all_user_contexts, hour=3, minute=15),       # 🔁 Попытка автосписания утром
#     ]

#     redis_settings = RedisSettings.from_dsn(settings.redis_url)

#     on_startup = startup
#     on_shutdown = shutdown

#     job_timeout = 386400          # 12 часов (достаточно для 1M при 25 RPS)
#     keep_result = 86400 

# # Запуск вручную (если надо)
# if __name__ == "__main__":
#     logger.info("👷 Запуск ARQ Worker вручную")
#     try:
#         asyncio.run(run_worker(WorkerSettings))
#     except Exception as e:
#         logger.exception("❌ Ошибка при запуске worker")
#         raise


# app/workers/arq_worker.py
# ========================================
# ✅ CRITICAL: Отключить uvloop ДО ВСЕХ импортов!
# ========================================
import sys
import os

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
from app.tasks.context_cleanup import reset_all_user_contexts
from app.db.redis_client import init_arq_redis

# Настройка логов
logging.basicConfig(level=settings.log_level, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# FastAPI-приложение (используется для доступа к state.db_pool)
app = FastAPI()

# Инициализация при запуске
async def startup(ctx):
    logger.info("🚀 ARQ Worker: инициализация MySQL")
    await init_db(app)
    await init_arq_redis()
    ctx["app"] = app

# Завершение работы
async def shutdown(ctx):
    logger.info("🔻 ARQ Worker: закрытие MySQL")
    await close_db(app)

# Настройки воркера
class WorkerSettings:
    functions = [
        try_all_autopays,
        send_broadcast,
        process_gpt_request, 
    ]

    cron_jobs = [
        cron(reset_tokens, hour=3, minute=5),
        cron(try_all_autopays, hour=3, minute=10),
        cron(reset_all_user_contexts, hour=3, minute=15),
    ]

    redis_settings = RedisSettings.from_dsn(settings.redis_url)

    on_startup = startup
    on_shutdown = shutdown

    job_timeout = 386400
    keep_result = 86400 

# Запуск вручную (если надо)
if __name__ == "__main__":
    logger.info("👷 Запуск ARQ Worker вручную")
    try:
        asyncio.run(run_worker(WorkerSettings))
    except Exception as e:
        logger.exception("❌ Ошибка при запуске worker")
        raise