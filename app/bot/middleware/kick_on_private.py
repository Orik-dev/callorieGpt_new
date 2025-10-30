from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message
from typing import Callable, Dict, Any
import logging

logger = logging.getLogger(__name__)

class KickNonPrivateMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Any],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        if isinstance(event, Message):
            chat = event.chat
            if chat.type != "private":
                bot = data["bot"]
                try:
                    await bot.leave_chat(chat.id)
                    logger.warning(f"[KICK] Бот кикнул сам себя из {chat.type} ({chat.id})")
                except Exception as e:
                    logger.exception(f"[KICK] Ошибка при попытке выйти из чата {chat.id}: {e}")
                return  # Не продолжаем обработку

        return await handler(event, data)
