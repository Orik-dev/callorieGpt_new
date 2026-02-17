import logging
from app.services.user import update_tokens_daily
from app.db.redis_client import redis

logger = logging.getLogger(__name__)

LOCK_TTL = 120  # 2 минуты


async def reset_tokens(ctx):
    lock_key = "lock:reset_tokens"
    acquired = await redis.set(lock_key, "1", ex=LOCK_TTL, nx=True)
    if not acquired:
        logger.info("[Task] Сброс токенов уже выполняется другим воркером, пропускаем")
        return

    try:
        logger.info("[Task] Запуск ежедневного сброса токенов.")
        await update_tokens_daily()
        logger.info("[Task] Ежедневный сброс токенов успешно завершен.")
    except Exception as e:
        logger.exception(f"[Task] Ошибка при ежедневном сбросе токенов: {e}")
    finally:
        await redis.delete(lock_key)
