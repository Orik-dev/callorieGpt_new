from app.bot.bot import bot
from aiogram import exceptions
import logging

logger = logging.getLogger(__name__)


async def send_text(chat_id: int, text: str, reply_to_message_id: int = None):
    """Отправляет текстовое сообщение"""
    try:
        return await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_to_message_id=reply_to_message_id,
            parse_mode="HTML"
        )
    except exceptions.TelegramAPIError as e:
        logger.error(f"[Messages] Error sending message to {chat_id}: {e}")
        raise


async def edit_text(chat_id: int, message_id: int, text: str):
    """Редактирует текст сообщения"""
    try:
        return await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            parse_mode="HTML"
        )
    except exceptions.TelegramBadRequest as e:
        # Сообщение не изменилось или уже удалено
        logger.warning(f"[Messages] Cannot edit message {message_id}: {e}")
        return await send_text(chat_id, text)
    except exceptions.TelegramAPIError as e:
        logger.error(f"[Messages] Error editing message {message_id}: {e}")
        raise


async def delete_message(chat_id: int, message_id: int):
    """Удаляет сообщение"""
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except exceptions.TelegramAPIError as e:
        logger.warning(f"[Messages] Cannot delete message {message_id}: {e}")
        pass