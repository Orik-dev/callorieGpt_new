from aiogram import Router, F
from aiogram.types import Message
from app.services.user import get_or_create_user
from app.utils.audio import ogg_to_text
from app.db.mysql import mysql
import logging
import asyncio
import re

router = Router()
logger = logging.getLogger(__name__)

TEXT_LIMIT_EXCEEDED = (
    "🥲 Бесплатные запросы на сегодня закончились.\n\n"
    "💎 Оформите подписку: /subscribe\n"
    "С подпиской доступно 25 запросов в день!"
)
TEXT_GENERATE = "⏳ Анализирую блюдо..."
TEXT_VOICE_PROCESSING = "🎤 Распознаю речь..."
TEXT_CALCULATING = "🔢 Считаю калорийность..."
TEXT_EDITING = "⏳ Редактирую последний прием пищи..."
TEXT_DELETING = "⏳ Удаляю из рациона..."


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


def is_calculation_only(text: str) -> bool:
    """
    Проверяет, хочет ли пользователь только посчитать калории (без добавления в рацион)
    
    Паттерны:
    - "посчитай калории в гречке"
    - "сколько калорий в яблоке"
    - "КБЖУ банана"
    - "калорийность пиццы"
    """
    calc_patterns = [
        r'посчитай',
        r'сколько.*калор',
        r'сколько.*ккал',
        r'калорийность',
        r'кбжу',
        r'бжу(?:\s|$)',
        r'узнать.*калор',
        r'проверь.*калор',
        r'рассчитай',
    ]
    
    text_lower = text.lower()
    
    for pattern in calc_patterns:
        if re.search(pattern, text_lower):
            return True
    
    return False


def is_delete_command(text: str) -> bool:
    """
    Проверяет, является ли текст командой удаления
    
    Паттерны:
    - "убери последнее"
    - "удали гречку"
    - "очисти рацион"
    """
    delete_patterns = [
        r'убери',
        r'удали',
        r'очисти',
        r'стер',
        r'сотри',
        r'выкинь',
        r'убрать',
        r'удалить',
        r'очистить',
    ]
    
    text_lower = text.lower()
    
    for pattern in delete_patterns:
        if re.search(pattern, text_lower):
            return True
    
    return False


def is_edit_command(text: str) -> bool:
    """
    Проверяет, является ли текст командой редактирования
    
    Паттерны:
    - "исправь последнее"
    - "измени последнее"
    - "поправь жиры"
    - "сделай менее жирным/калорийным"
    """
    edit_patterns = [
        r'исправ',
        r'измен',
        r'поправ',
        r'сделай.*(?:мен[ье]е|больше)',
        r'(?:мен[ье]е|больше).*(?:жир|калорий|белк|углевод)',
        r'уменьш',
        r'увелич',
        r'скорректир',
        r'редактир',
    ]
    
    text_lower = text.lower()
    
    for pattern in edit_patterns:
        if re.search(pattern, text_lower):
            return True
    
    return False


@router.message(F.text)
async def on_text(message: Message, **data):
    """Обработка текстовых сообщений"""
    user_id = message.from_user.id
    text = message.text.strip()
    
    # Проверка на команды
    if text.startswith('/'):
        return
    
    # ✅ ПРОВЕРКА: Только посчитать (БЕЗ добавления в рацион, БЕЗ списания токена)
    if is_calculation_only(text):
        logger.info(f"[Entry:Text] User {user_id}: calculation only (no save)")
        
        redis = data["redis"]
        msg = await message.answer(TEXT_CALCULATING)
        
        try:
            await redis.enqueue_job(
                "process_calculation_only",
                user_id=user_id,
                message_id=msg.message_id,
                chat_id=message.chat.id,
                text=text
            )
        except Exception as e:
            logger.error(f"[Entry:Text] Failed to enqueue calculation for user {user_id}: {e}")
            await msg.edit_text("⚠️ Ошибка. Попробуйте позже.")
        
        return
    
    # ✅ ПРОВЕРКА: Команды удаления
    if is_delete_command(text):
        logger.info(f"[Entry:Text] User {user_id}: delete command detected")
        
        if not await deduct_token_atomic(user_id):
            await message.answer(TEXT_LIMIT_EXCEEDED)
            return
        
        redis = data["redis"]
        msg = await message.answer(TEXT_DELETING)
        
        try:
            await redis.enqueue_job(
                "process_meal_delete",
                user_id=user_id,
                message_id=msg.message_id,
                chat_id=message.chat.id,
                text=text
            )
        except Exception as e:
            logger.error(f"[Entry:Text] Failed to enqueue delete for user {user_id}: {e}")
            await msg.edit_text("⚠️ Ошибка. Попробуйте позже.")
            await refund_token(user_id)
        
        return
    
    # ✅ ПРОВЕРКА: Команды редактирования
    if is_edit_command(text):
        logger.info(f"[Entry:Text] User {user_id}: edit command detected")
        
        if not await deduct_token_atomic(user_id):
            await message.answer(TEXT_LIMIT_EXCEEDED)
            return
        
        redis = data["redis"]
        msg = await message.answer(TEXT_EDITING)
        
        try:
            await redis.enqueue_job(
                "process_meal_edit",
                user_id=user_id,
                message_id=msg.message_id,
                chat_id=message.chat.id,
                text=text
            )
        except Exception as e:
            logger.error(f"[Entry:Text] Failed to enqueue edit for user {user_id}: {e}")
            await msg.edit_text("⚠️ Ошибка. Попробуйте позже.")
            await refund_token(user_id)
        
        return
    
    # ✅ ОБЫЧНОЕ ДОБАВЛЕНИЕ БЛЮДА
    if not await deduct_token_atomic(user_id):
        await message.answer(TEXT_LIMIT_EXCEEDED)
        return
    
    logger.info(f"[Entry:Text] User {user_id}: processing text ({len(text)} chars)")
    
    redis = data["redis"]
    msg = await message.answer(TEXT_GENERATE)
    
    try:
        await redis.enqueue_job(
            "process_gpt_request",
            user_id=user_id,
            message_id=msg.message_id,
            chat_id=message.chat.id,
            text=text
        )
    except Exception as e:
        logger.error(f"[Entry:Text] Failed to enqueue for user {user_id}: {e}")
        await msg.edit_text("⚠️ Ошибка постановки в очередь. Попробуйте позже.")
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
        logger.debug(f"[Entry:Voice] Downloaded to {file_path}")
        
        text = await asyncio.to_thread(ogg_to_text, file_path)
        
        if not text:
            await status_msg.edit_text(
                "⚠️ Не удалось распознать речь. "
                "Попробуйте еще раз или напишите текстом."
            )
            await refund_token(user_id)
            return
        
        logger.info(f"[Entry:Voice] User {user_id}: recognized text: {text[:100]}")
        
        await message.answer(f"🗣 Распознано: <i>{text}</i>", parse_mode="HTML")
        await status_msg.edit_text(TEXT_GENERATE)
        
        redis = data["redis"]
        
        await redis.enqueue_job(
            "process_gpt_request",
            user_id=user_id,
            message_id=status_msg.message_id,
            chat_id=message.chat.id,
            text=text
        )
        
    except Exception as e:
        logger.exception(f"[Entry:Voice] Error for user {user_id}: {e}")
        try:
            await status_msg.edit_text(
                "⚠️ Ошибка при обработке голосового сообщения. "
                "Попробуйте еще раз."
            )
        except:
            await message.answer("⚠️ Ошибка при обработке голосового сообщения.")
        
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
            await message.answer(
                "⚠️ Фото слишком большое (максимум 10 МБ).\n"
                "Попробуйте сжать фото или использовать другое."
            )
            await refund_token(user_id)
            return
        
        logger.debug(
            f"[Entry:Photo] Photo size: {file_size_mb:.2f}MB, "
            f"dimensions: {photo.width}x{photo.height}"
        )
        
        file = await message.bot.get_file(photo.file_id)
        await asyncio.sleep(0.3)
        
        url = f"https://api.telegram.org/file/bot{message.bot.token}/{file.file_path}"
        caption = message.caption or "Определи все блюда на фото и рассчитай КБЖУ"
        
        redis = data["redis"]
        msg = await message.answer(TEXT_GENERATE)
        
        await redis.enqueue_job(
            "process_gpt_request",
            user_id=user_id,
            message_id=msg.message_id,
            chat_id=message.chat.id,
            text=caption,
            image_url=url
        )
        
    except Exception as e:
        logger.exception(f"[Entry:Photo] Error for user {user_id}: {e}")
        await message.answer(
            "⚠️ Ошибка при обработке фото. Попробуйте еще раз."
        )
        await refund_token(user_id)


@router.message(F.video | F.document | F.sticker | F.animation)
async def on_unsupported_media(message: Message):
    """Обработка неподдерживаемых типов медиа"""
    await message.answer(
        "⚠️ Этот тип сообщения не поддерживается.\n\n"
        "Пожалуйста, отправьте:\n"
        "📸 Фото блюда\n"
        "📝 Текстовое описание\n"
        "🎤 Голосовое сообщение\n\n"
        "💡 Или используйте команды:\n"
        "🔢 \"посчитай калории в яблоке\"\n"
        "✏️ \"исправь последнее - менее жирное\"\n"
        "🗑 \"убери последнее\""
    )