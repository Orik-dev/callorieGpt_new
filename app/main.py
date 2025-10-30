# app/main.py
import logging
from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.api.yookassa import yookassa_router
from app.api.telegram import telegram_router # Импорт роутера Telegram
from app.bot.bot import dp, setup_middlewares, bot # Импорт диспетчера и бота Aiogram
from app.db.mysql import init_db, close_db # Функции инициализации и закрытия MySQL
from app.db.redis_client import redis # Клиент Redis
from app.utils.logger import setup_logger 
# from app.tasks.context_cleanup import reset_all_user_contexts
from app.db.redis_client import redis, init_arq_redis
from fastapi import HTTPException, Query
from app.db.redis_client import get_arq_redis
from app.config import settings
from app.tasks.subscriptions import try_all_autopays


logger = logging.getLogger(__name__)

# Инициализация логгера при запуске модуля
setup_logger()

# async def clear_all_contexts():
#     from app.tasks.context_cleanup import reset_all_user_contexts
#     logger.info("✅ Контекст очищен новый день начался и новая история")

#     await reset_all_user_contexts()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Приложение стартует: Инициализация ресурсов...")
    # Инициализация базы данных MySQL
    await init_db(app)
    await init_arq_redis()
    # Настройка middleware для Aiogram (передаём текущий экземпляр FastAPI)
    setup_middlewares(app)
    # app/main.py
import logging
from fastapi import FastAPI
from contextlib import asynccontextmanager

from app.api.yookassa import yookassa_router
from app.api.telegram import telegram_router  # Импорт роутера Telegram
from app.bot.bot import dp, setup_middlewares, bot  # Импорт диспетчера и бота Aiogram
from app.db.mysql import init_db, close_db  # Функции инициализации и закрытия MySQL
from app.db.redis_client import redis  # Клиент Redis
from app.utils.logger import setup_logger
# from app.tasks.context_cleanup import reset_all_user_contexts
from app.db.redis_client import redis, init_arq_redis
from fastapi import HTTPException, Query
from app.db.redis_client import get_arq_redis
from app.config import settings
from app.tasks.subscriptions import try_all_autopays

logger = logging.getLogger(__name__)

# Инициализация логгера при запуске модуля
setup_logger()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Приложение стартует: Инициализация ресурсов...")
    # Инициализация базы данных MySQL
    await init_db(app)
    await init_arq_redis()
    # Настройка middleware для Aiogram (передаём текущий экземпляр FastAPI)
    setup_middlewares(app)

    # ---- ВАЖНО: защищаем разовый запуск автоплатежей редис-локом ----
    try:
        # атомарный лок (SET key value EX 600 NX)
        lock_key = "locks:autopays:startup"
        locked = await redis.set(lock_key, "1", ex=600, nx=True)
        if locked:
            await try_all_autopays(None)   # внутри ctx не используется
            logger.info("✅ Разовый прогон автосписаний выполнен (под локом)")
        else:
            logger.info("⏭️ Пропускаю автосписания: другой воркер уже схватил лок.")
    except Exception:
        logger.exception("❌ Ошибка при разовом прогоне автосписаний")
    # await clear_all_contexts()

    logger.info("✅ Ресурсы инициализированы. Приложение готово принимать запросы.")
    yield # Приложение активно и обрабатывает запросы
    logger.info("🔻 Приложение завершает работу: Закрытие ресурсов...")
    # Закрытие соединения с MySQL
    await close_db(app)
    # Закрытие сессии бота
    await bot.session.close()
    # Закрытие соединения с Redis (можно добавить redis.close() если используете не через aiogram storage)
    await redis.close()
    logger.info("👋 Ресурсы закрыты. Приложение остановлено.")


# Создание экземпляра FastAPI приложения
app = FastAPI(lifespan=lifespan)

# Подключение роутеров для обработки вебхуков
app.include_router(telegram_router, prefix="/webhook") # Вебхуки от Telegram
app.include_router(yookassa_router, prefix="/webhook")

@app.get("/ping")
async def ping():
    """
    Простой эндпоинт для проверки работоспособности сервиса.
    """
    logger.info("Получен запрос /ping.")
    return {"status": "ok", "message": "Service is running and healthy!"}


# @app.post("/internal/run-autopays")
# async def run_autopays(token: str = Query(..., min_length=8)):
#     if not settings.admin_http_token or token != settings.admin_http_token:
#         raise HTTPException(status_code=403, detail="forbidden")
#     arq = await get_arq_redis()
#     await arq.enqueue_job("try_all_autopays")
#     return {"queued": True} 
# #     return {"queued": True}
