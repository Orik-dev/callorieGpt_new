# app/bot/utils/messages.py

from app.bot.bot import bot  # единый экземпляр
from aiogram import exceptions

async def send_text(chat_id: int, text: str, reply_to_message_id: int = None):
    return await bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_to_message_id=reply_to_message_id
    )

async def edit_text(chat_id: int, message_id: int, text: str):
    try:
        return await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text
        )
    except exceptions.TelegramAPIError:
        return await send_text(chat_id, text, reply_to_message_id=message_id)

async def delete_message(chat_id: int, message_id: int):
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except exceptions.TelegramAPIError:
        pass
