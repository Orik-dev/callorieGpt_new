# from aiogram.dispatcher.middlewares.base import BaseMiddleware
# from typing import Callable, Awaitable, Dict, Any
# from arq.connections import ArqRedis

# class RedisMiddleware(BaseMiddleware):
#     def __init__(self, arq_redis: ArqRedis):
#         self.arq_redis = arq_redis

#     async def __call__(
#         self,
#         handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
#         event: Any,
#         data: Dict[str, Any],
#     ) -> Any:
#         data["redis"] = self.arq_redis
#         return await handler(event, data)


from aiogram.dispatcher.middlewares.base import BaseMiddleware
from typing import Callable, Awaitable, Dict, Any
from app.db.redis_client import get_arq_redis

class RedisMiddleware(BaseMiddleware):
    """
    Middleware для добавления ArqRedis в контекст
    
    ИСПРАВЛЕНИЕ: Не принимает arq_redis при инициализации,
    а получает его динамически через get_arq_redis()
    
    Это решает проблему когда arq_redis еще не инициализирован
    при setup_middlewares()
    """
    
    def __init__(self):
        """Инициализация без параметров"""
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: Dict[str, Any],
    ) -> Any:
        """
        Добавляет ArqRedis в контекст для каждого события
        
        Получает arq_redis динамически, что гарантирует что он инициализирован
        """
        # ✅ ИСПРАВЛЕНИЕ: Получаем redis каждый раз
        data["redis"] = await get_arq_redis()
        return await handler(event, data)