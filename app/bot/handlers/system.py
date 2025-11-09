from aiogram import Router, types
from aiogram.enums import ChatMemberStatus
import logging

router = Router()
logger = logging.getLogger(__name__)


@router.my_chat_member()
async def leave_if_added_to_group(event: types.ChatMemberUpdated):
    """
    Обрабатывает изменения статуса бота в чате.
    Если бота добавляют в группу, он автоматически покидает её.
    """
    from app.bot.bot import bot

    chat_type = event.chat.type
    bot_id = (await bot.me()).id

    if chat_type != "private" and event.new_chat_member.user.id == bot_id:
        if event.new_chat_member.status == ChatMemberStatus.MEMBER:
            logger.warning(
                f"[System] 🚫 Бот добавлен в {chat_type} ({event.chat.id}). "
                f"Покидаю чат..."
            )
            try:
                await bot.leave_chat(event.chat.id)
                logger.info(f"[System] ✅ Бот покинул чат {event.chat.id}")
            except Exception as e:
                logger.exception(
                    f"[System] ❌ Ошибка при покидании чата {event.chat.id}: {e}"
                )
        elif event.new_chat_member.status == ChatMemberStatus.LEFT:
            logger.info(f"[System] Бот был удалён из {chat_type} ({event.chat.id})")
            
    elif chat_type == "private" and event.new_chat_member.user.id == bot_id:
        if event.new_chat_member.status == ChatMemberStatus.MEMBER:
            logger.info(f"[System] Бот начал чат с пользователем {event.chat.id}")
        elif event.new_chat_member.status == ChatMemberStatus.LEFT:
            logger.info(f"[System] Пользователь {event.chat.id} заблокировал бота")