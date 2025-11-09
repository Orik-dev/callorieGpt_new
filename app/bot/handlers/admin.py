import logging
from typing import Any

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiomysql import DictCursor

from app.bot.states.broadcast_state import BroadcastState
from app.db.redis_client import get_arq_redis, redis
from app.config import settings

REDIS_KEY_ADMIN = "broadcast:admin_id"

router = Router()
logger = logging.getLogger(__name__)


async def is_admin(message: Message) -> bool:
    """Проверка является ли пользователь администратором"""
    return message.from_user.id == int(settings.admin_id)


@router.message(Command("users"))
async def show_users_count(message: Message, **kwargs: Any):
    """Показывает количество пользователей в боте"""
    if not await is_admin(message):
        return await message.answer("⛔ Доступ запрещён.")

    try:
        app = kwargs["app"]
        pool = app.state.db_pool

        async with pool.acquire() as conn:
            async with conn.cursor(DictCursor) as cur:
                # Всего пользователей
                await cur.execute("SELECT COUNT(*) as count FROM users_tbl")
                total = await cur.fetchone()
                
                # С активной подпиской
                await cur.execute("""
                    SELECT COUNT(*) as count FROM users_tbl 
                    WHERE expiration_date IS NOT NULL 
                    AND expiration_date >= CURDATE()
                """)
                subscribed = await cur.fetchone()
                
                # Новых за последние 7 дней
                await cur.execute("""
                    SELECT COUNT(*) as count FROM users_tbl 
                    WHERE id > (SELECT MAX(id) FROM users_tbl) - 1000
                """)
                new_week = await cur.fetchone()

        text = (
            f"📊 <b>Статистика бота</b>\n\n"
            f"👥 Всего пользователей: <b>{total['count']}</b>\n"
            f"💎 С подпиской: <b>{subscribed['count']}</b>\n"
            f"🆕 Новых за неделю: <b>{new_week['count']}</b>"
        )
        
        await message.answer(text, parse_mode="HTML")
        
    except Exception as e:
        logger.exception(f"[Admin] Error in /users: {e}")
        await message.answer("⚠️ Ошибка при получении статистики.")


@router.message(Command("ping"))
async def handle_ping(message: Message):
    """Проверка работоспособности бота"""
    if not await is_admin(message):
        return
    
    try:
        await message.answer("🏓 Pong! Бот работает нормально.")
    except Exception as e:
        logger.exception(f"[Admin] Error in /ping: {e}")


@router.message(Command("send_all"))
async def start_broadcast(message: Message, state: FSMContext):
    """Начало рассылки"""
    if not await is_admin(message):
        return await message.answer("⛔ Доступ запрещён.")

    try:
        await state.set_state(BroadcastState.waiting_for_text)
        await redis.set(REDIS_KEY_ADMIN, message.from_user.id)
        
        await message.answer(
            "✉️ <b>Запуск рассылки</b>\n\n"
            "Отправьте сообщение для рассылки.\n"
            "Поддерживаются: текст, фото, видео, анимация.\n\n"
            "Для отмены: /cancel_send",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.exception(f"[Admin] Error starting broadcast: {e}")
        await message.answer("⚠️ Ошибка при запуске рассылки.")


@router.message(Command("cancel_send"))
async def cancel_broadcast(message: Message, state: FSMContext):
    """Отмена рассылки"""
    if not await is_admin(message):
        return await message.answer("⛔ Доступ запрещён.")

    try:
        await state.clear()
        await redis.delete(REDIS_KEY_ADMIN)
        await message.answer("❌ Рассылка отменена.")
    except Exception as e:
        logger.exception(f"[Admin] Error canceling broadcast: {e}")
        await message.answer("⚠️ Ошибка при отмене рассылки.")


@router.message(BroadcastState.waiting_for_text)
async def receive_broadcast_message(message: Message, state: FSMContext):
    """Получение сообщения для рассылки и запуск"""
    try:
        await message.answer(
            "📤 <b>Рассылка запущена...</b>\n\n"
            "Это может занять некоторое время.",
            parse_mode="HTML"
        )

        data = {
            "text": message.text or message.caption,
            "photo_id": message.photo[-1].file_id if message.photo else None,
            "animation_id": message.animation.file_id if message.animation else None,
            "video_id": message.video.file_id if message.video else None,
        }

        arq = await get_arq_redis()
        await arq.enqueue_job("send_broadcast", data)
        
        await state.clear()
        
        logger.info(f"[Admin] Broadcast started by user {message.from_user.id}")

    except Exception as e:
        logger.exception(f"[Admin] Error receiving broadcast message: {e}")
        await message.answer("⚠️ Не удалось запустить рассылку.")