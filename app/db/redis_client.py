from redis.asyncio import Redis
from arq import create_pool
from arq.connections import RedisSettings, ArqRedis
from app.config import settings
import logging

logger = logging.getLogger(__name__)

# Стандартный Redis клиент (aiogram FSM, context storage и пр.)
redis = Redis.from_url(
    settings.redis_url,
    decode_responses=False
)

# ArqRedis (для очередей задач)
arq_redis: ArqRedis | None = None


async def init_arq_redis() -> ArqRedis:
    global arq_redis
    arq_redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    return arq_redis

async def get_arq_redis() -> ArqRedis:
    global arq_redis
    if arq_redis is None:
        logger.warning("⚠️ arq_redis не был инициализирован — создаём заново.")
        arq_redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    return arq_redis
