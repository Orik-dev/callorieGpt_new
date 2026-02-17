from aiogram.dispatcher.middlewares.base import BaseMiddleware
from typing import Callable, Awaitable, Dict, Any
from app.db.redis_client import get_arq_redis

class RedisMiddleware(BaseMiddleware):
    """
    Middleware для добавления ArqRedis в контекст.
    Кэширует ссылку на пул после первого получения.
    """

    def __init__(self):
        super().__init__()
        self._arq_redis = None

    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: Dict[str, Any],
    ) -> Any:
        if self._arq_redis is None:
            self._arq_redis = await get_arq_redis()
        data["redis"] = self._arq_redis
        return await handler(event, data)