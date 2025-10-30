import logging
from typing import Any

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiomysql import DictCursor

from app.bot.states.broadcast_state import BroadcastState
from app.db.redis_client import get_arq_redis
from app.db.redis_client import redis
from app.config import settings

REDIS_KEY_ADMIN = "broadcast:admin_id"

router = Router()
logger = logging.getLogger(__name__)


async def is_admin(message: Message) -> bool:
    return message.from_user.id == int(settings.admin_id)


@router.message(Command("users"))
async def show_users_count(message: Message, **kwargs: Any):
    if not await is_admin(message):
        return await message.answer("⛔ Доступ запрещён.")

    try:
        app = kwargs["app"]
        pool = app.state.db_pool

        async with pool.acquire() as conn:
            async with conn.cursor(DictCursor) as cur:
                await cur.execute("SELECT COUNT(*) as count FROM users_tbl")
                row = await cur.fetchone()

        await message.answer(f"👥 Пользователей в боте: {row['count']}")
    except Exception as e:
        logger.exception("Ошибка при выполнении команды /users")
        await message.answer("⚠️ Ошибка при получении количества пользователей.")


@router.message(Command("ping"))
async def handle_ping(message: Message):
    if not await is_admin(message):
        return
    try:
        await message.answer("🏓 Pong")
    except Exception as e:
        logger.exception("Ошибка при выполнении команды /ping")
        await message.answer("⚠️ Ошибка при ответе.")


@router.message(Command("send_all"))
async def start_broadcast(message: Message, state: FSMContext):
    if not await is_admin(message):
        return await message.answer("⛔ Доступ запрещён.")

    try:
        await state.set_state(BroadcastState.waiting_for_text)
        await redis.set(REDIS_KEY_ADMIN, message.from_user.id)
        await message.answer("✉️ Введите сообщение для рассылки (или /cancel_send):")
    except Exception as e:
        logger.exception("Ошибка при запуске рассылки")
        await message.answer("⚠️ Ошибка при запуске рассылки.")


@router.message(Command("cancel_send"))
async def cancel_broadcast(message: Message, state: FSMContext):
    if not await is_admin(message):
        return await message.answer("⛔ Доступ запрещён.")

    try:
        await state.clear()
        await redis.delete(REDIS_KEY_ADMIN)
        await message.answer("❌ Рассылка отменена.")
    except Exception as e:
        logger.exception("Ошибка при отмене рассылки")
        await message.answer("⚠️ Ошибка при отмене рассылки.")


@router.message(BroadcastState.waiting_for_text)
async def receive_broadcast_message(message: Message, state: FSMContext):
    try:
        await message.answer("📤 Рассылка запущена...")

        data = {
            "text": message.text or message.caption,
            "photo_id": message.photo[-1].file_id if message.photo else None,
            "animation_id": message.animation.file_id if message.animation else None,
            "video_id": message.video.file_id if message.video else None,
        }

        arq = await get_arq_redis()
        await arq.enqueue_job("send_broadcast", data)
        await state.clear()

    except Exception as e:
        logger.exception("Ошибка при отправке рассылки")
        await message.answer("⚠️ Не удалось запустить рассылку.")

