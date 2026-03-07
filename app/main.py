import logging
from fastapi import FastAPI
from contextlib import asynccontextmanager

from app.api.yookassa import yookassa_router
from app.api.telegram import telegram_router
from app.bot.bot import dp, setup_middlewares, bot
from app.db.mysql import init_db, close_db
from app.db.redis_client import redis, init_arq_redis
from app.config import settings
from app.utils.logger import setup_logger
from app.bot.handlers.start import setup_bot_commands 

logger = logging.getLogger(__name__)
setup_logger()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    logger.info("🚀 Приложение стартует: Инициализация ресурсов...")
    
    # Инициализация БД и Redis
    await init_db(app)
    await init_arq_redis()
    
    # Настройка middleware для Aiogram
    setup_middlewares(app)
    
    await setup_bot_commands()

    logger.info("✅ Ресурсы инициализированы. Приложение готово принимать запросы.")
    
    yield  # Приложение работает
    
    logger.info("🔻 Приложение завершает работу: Закрытие ресурсов...")

    # Закрытие соединений — каждое в try/except чтобы не блокировать остальные
    try:
        await close_db(app)
    except Exception as e:
        logger.error(f"Ошибка при закрытии БД: {e}")

    try:
        await bot.session.close()
    except Exception as e:
        logger.error(f"Ошибка при закрытии bot session: {e}")

    try:
        from app.api.gpt import close_client
        await close_client()
    except Exception as e:
        logger.error(f"Ошибка при закрытии httpx client: {e}")

    try:
        from app.db.redis_client import arq_redis
        if arq_redis:
            await arq_redis.close()
    except Exception as e:
        logger.error(f"Ошибка при закрытии arq_redis: {e}")

    try:
        await redis.close()
    except Exception as e:
        logger.error(f"Ошибка при закрытии Redis: {e}")

    logger.info("👋 Ресурсы закрыты. Приложение остановлено.")


# Создание FastAPI приложения
app = FastAPI(
    title="Calories Bot API",
    version="2.0.0",
    lifespan=lifespan
)

# Подключение роутеров
app.include_router(telegram_router, prefix="/webhook")
app.include_router(yookassa_router, prefix="/webhook")


@app.get("/")
async def root():
    """Главная страница"""
    return {
        "service": "Calories Bot API",
        "version": "2.0.0",
        "status": "running"
    }


@app.get("/ping")
async def ping():
    """Health check эндпоинт"""
    logger.info("Получен запрос /ping")
    return {
        "status": "ok", 
        "message": "Service is running and healthy!"
    }


@app.get("/health")
async def health():
    """Детальная проверка здоровья сервиса"""
    try:
        # Проверка MySQL
        from app.db.mysql import mysql
        await mysql.fetchone("SELECT 1")
        db_status = "ok"
    except Exception as e:
        logger.error(f"DB health check failed: {e}")
        db_status = "error"
    
    try:
        # Проверка Redis
        await redis.ping()
        redis_status = "ok"
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        redis_status = "error"
    
    return {
        "status": "ok" if db_status == "ok" and redis_status == "ok" else "degraded",
        "database": db_status,
        "redis": redis_status
    }