# app/bot/handlers/entry.py
"""
Единый обработчик входящих сообщений.
Все намерения (add/calculate/edit/delete) определяет GPT.
"""
from aiogram import Router, F
from aiogram.types import Message
from app.services.user import get_or_create_user
from app.utils.audio import ogg_to_text
from app.utils.telegram_helpers import escape_html
from app.db.mysql import mysql
import logging
import asyncio

router = Router()
logger = logging.getLogger(__name__)

TEXT_LIMIT_EXCEEDED = (
    "🥲 Запросы на сегодня закончились.\n\n"
    "💎 Оформите подписку: /subscribe\n"
    "С подпиской доступно 25 запросов в день!"
)
TEXT_PROCESSING = "⏳ Обрабатываю..."
TEXT_VOICE_PROCESSING = "🎤 Распознаю речь..."


async def deduct_token_atomic(user_id: int) -> bool:
    """Атомарно списывает токен"""
    async with mysql.pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """UPDATE users_tbl 
                   SET free_tokens = free_tokens - 1 
                   WHERE tg_id = %s AND free_tokens > 0""",
                (user_id,)
            )
            return cur.rowcount > 0


async def refund_token(user_id: int):
    """Возвращает токен при ошибке"""
    async with mysql.pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """UPDATE users_tbl 
                   SET free_tokens = free_tokens + 1 
                   WHERE tg_id = %s""",
                (user_id,)
            )
            logger.info(f"Token refunded for user {user_id}")


@router.message(F.text)
async def on_text(message: Message, **data):
    """
    Обработка текстовых сообщений.
    GPT сам определит intent (add/calculate/edit/delete).
    """
    user_id = message.from_user.id
    text = message.text.strip()
    
    # Игнорируем команды
    if text.startswith('/'):
        return
    
    # Списываем токен
    if not await deduct_token_atomic(user_id):
        await message.answer(TEXT_LIMIT_EXCEEDED)
        return
    
    logger.info(f"[Entry:Text] User {user_id}: {text[:50]}...")
    
    redis = data["redis"]
    msg = await message.answer(TEXT_PROCESSING)
    
    try:
        await redis.enqueue_job(
            "process_universal_request",
            user_id=user_id,
            message_id=msg.message_id,
            chat_id=message.chat.id,
            text=text,
            image_url=None
        )
    except Exception as e:
        logger.error(f"[Entry:Text] Queue error for user {user_id}: {e}")
        await msg.edit_text("⚠️ Ошибка. Попробуйте позже.")
        await refund_token(user_id)


@router.message(F.voice)
async def on_voice(message: Message, **data):
    """Обработка голосовых сообщений"""
    user_id = message.from_user.id
    
    if not await deduct_token_atomic(user_id):
        await message.answer(TEXT_LIMIT_EXCEEDED)
        return
    
    status_msg = await message.answer(TEXT_VOICE_PROCESSING)
    
    try:
        logger.info(f"[Entry:Voice] User {user_id}: processing voice")
        
        file = await message.bot.get_file(message.voice.file_id)
        file_name = file.file_path.split('/')[-1]
        file_path = f"/shared-voice/{file_name}"
        
        await message.bot.download_file(file.file_path, destination=file_path)
        
        text = await asyncio.to_thread(ogg_to_text, file_path)
        
        if not text:
            await status_msg.edit_text(
                "⚠️ Не удалось распознать речь.\n"
                "Попробуйте еще раз или напишите текстом."
            )
            await refund_token(user_id)
            return
        
        logger.info(f"[Entry:Voice] User {user_id}: recognized: {text[:50]}")
        
        await message.answer(f"🗣 Распознано: <i>{escape_html(text)}</i>", parse_mode="HTML")
        await status_msg.edit_text(TEXT_PROCESSING)
        
        redis = data["redis"]
        
        await redis.enqueue_job(
            "process_universal_request",
            user_id=user_id,
            message_id=status_msg.message_id,
            chat_id=message.chat.id,
            text=text,
            image_url=None
        )
        
    except Exception as e:
        logger.exception(f"[Entry:Voice] Error for user {user_id}: {e}")
        try:
            await status_msg.edit_text("⚠️ Ошибка при обработке голосового.")
        except Exception:
            pass
        await refund_token(user_id)


@router.message(F.photo)
async def on_photo(message: Message, **data):
    """Обработка фотографий еды"""
    user_id = message.from_user.id
    
    if not await deduct_token_atomic(user_id):
        await message.answer(TEXT_LIMIT_EXCEEDED)
        return
    
    try:
        logger.info(f"[Entry:Photo] User {user_id}: processing photo")
        
        photo = message.photo[-1]
        file_size_mb = photo.file_size / (1024 * 1024) if photo.file_size else 0
        
        if file_size_mb > 10:
            await message.answer("⚠️ Фото слишком большое (максимум 10 МБ).")
            await refund_token(user_id)
            return
        
        file = await message.bot.get_file(photo.file_id)
        await asyncio.sleep(0.3)
        
        url = f"https://api.telegram.org/file/bot{message.bot.token}/{file.file_path}"
        caption = message.caption.strip() if message.caption else ""
        
        redis = data["redis"]
        msg = await message.answer(TEXT_PROCESSING)
        
        await redis.enqueue_job(
            "process_universal_request",
            user_id=user_id,
            message_id=msg.message_id,
            chat_id=message.chat.id,
            text=caption,
            image_url=url
        )
        
    except Exception as e:
        logger.exception(f"[Entry:Photo] Error for user {user_id}: {e}")
        await message.answer("⚠️ Ошибка при обработке фото.")
        await refund_token(user_id)


@router.message(F.video | F.document | F.sticker | F.animation)
async def on_unsupported_media(message: Message):
    """Обработка неподдерживаемых типов"""
    await message.answer(
        "⚠️ Этот тип сообщения не поддерживается.\n\n"
        "Отправьте:\n"
        "📸 Фото блюда\n"
        "📝 Текст (что съели)\n"
        "🎤 Голосовое сообщение"
    )