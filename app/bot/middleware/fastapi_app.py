# app/bot/middleware/fastapi_app.py
from typing import Callable, Dict, Any
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from fastapi import FastAPI
import logging

logger = logging.getLogger(__name__)

class FastAPIAppMiddleware(BaseMiddleware):
    def __init__(self, app: FastAPI):
        super().__init__()
        self._app = app
        logger.debug("FastAPIAppMiddleware инициализирован.")

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Any],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        """
        Вызывается для каждого обновления. Добавляет 'app' в 'data'.
        """
        data["app"] = self._app
        logger.debug(f"FastAPIAppMiddleware: 'app' добавлен в контекст для события {type(event).__name__}.")
        return await handler(event, data)