from aiogram.dispatcher.middlewares.base import BaseMiddleware
from typing import Callable, Awaitable, Dict, Any
from arq.connections import ArqRedis

class RedisMiddleware(BaseMiddleware):
    def __init__(self, arq_redis: ArqRedis):
        self.arq_redis = arq_redis

    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: Dict[str, Any],
    ) -> Any:
        data["redis"] = self.arq_redis
        return await handler(event, data)
