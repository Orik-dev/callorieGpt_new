import logging
from app.db.redis_client import redis

logger = logging.getLogger(__name__)

async def reset_all_user_contexts(ctx=None):
    logger.info("[GPT] Очистка GPT-контекстов...")
    BATCH_SIZE = 1000
    keys = await redis.keys("gpt:ctx:*")
    for i in range(0, len(keys), BATCH_SIZE):
        await redis.delete(*keys[i:i+BATCH_SIZE])
        logger.info(f"[GPT] Удалено {len(keys)} контекстов.")
    else:
        logger.info("[GPT] Контексты не найдены.")
