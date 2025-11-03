from aiogram import Router, F
from aiogram.types import Message
from app.services.user import get_or_create_user
from app.utils.audio import ogg_to_text
from app.db.mysql import mysql
import logging
import asyncio

router = Router()
logger = logging.getLogger(__name__)

TEXT_LIMIT_EXCEEDED = (
    "🥲 Бесплатные запросы на сегодня закончились.\n\n"
    "💎 Оформите подписку: /subscribe\n"
    "С подпиской доступно 25 запросов в день!"
)
TEXT_GENERATE = "⏳ Анализирую блюдо..."
TEXT_VOICE_PROCESSING = "🎤 Распознаю речь..."


async def deduct_token_atomic(user_id: int) -> bool:
    """
    Атомарно списывает токен (защита от race condition)
    
    Returns:
        True если токен списан, False если токенов нет
    """
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


# =====================================
# ТЕКСТОВЫЕ СООБЩЕНИЯ
# =====================================
@router.message(F.text)
async def on_text(message: Message, **data):
    """
    Обработка текстовых описаний еды
    
    Примеры:
    - "гречка 200г с курицей 150г"
    - "два яблока и банан"
    - "пицца маргарита целая"
    """
    user_id = message.from_user.id
    
    # Проверка на команды (не обрабатываем как еду)
    if message.text.startswith('/'):
        return
    
    # Атомарное списание токена
    if not await deduct_token_atomic(user_id):
        await message.answer(TEXT_LIMIT_EXCEEDED)
        return
    
    logger.info(
        f"[Entry:Text] User {user_id}: processing text ({len(message.text)} chars)"
    )
    
    # Отправляем в очередь
    redis = data["redis"]
    msg = await message.answer(TEXT_GENERATE)
    
    try:
        await redis.enqueue_job(
            "process_gpt_request",
            user_id=user_id,
            message_id=msg.message_id,
            chat_id=message.chat.id,
            text=message.text
        )
    except Exception as e:
        logger.error(f"[Entry:Text] Failed to enqueue for user {user_id}: {e}")
        await msg.edit_text("⚠️ Ошибка постановки в очередь. Попробуйте позже.")
        await refund_token(user_id)


# =====================================
# ГОЛОСОВЫЕ СООБЩЕНИЯ
# =====================================
@router.message(F.voice)
async def on_voice(message: Message, **data):
    """
    Обработка голосовых сообщений
    
    Процесс:
    1. Скачивание OGG файла
    2. Распознавание речи через Google Speech Recognition
    3. Отправка текста в GPT
    """
    user_id = message.from_user.id
    
    # Атомарное списание токена
    if not await deduct_token_atomic(user_id):
        await message.answer(TEXT_LIMIT_EXCEEDED)
        return
    
    status_msg = await message.answer(TEXT_VOICE_PROCESSING)
    
    try:
        logger.info(f"[Entry:Voice] User {user_id}: processing voice")
        
        # Скачиваем голосовое сообщение
        file = await message.bot.get_file(message.voice.file_id)
        file_name = file.file_path.split('/')[-1]
        file_path = f"/shared-voice/{file_name}"
        
        await message.bot.download_file(file.file_path, destination=file_path)
        logger.debug(f"[Entry:Voice] Downloaded to {file_path}")
        
        # Распознаем речь
        text = await asyncio.to_thread(ogg_to_text, file_path)
        
        if not text:
            await status_msg.edit_text(
                "⚠️ Не удалось распознать речь. "
                "Попробуйте еще раз или напишите текстом."
            )
            await refund_token(user_id)
            return
        
        logger.info(f"[Entry:Voice] User {user_id}: recognized text: {text[:100]}")
        
        # Показываем распознанный текст
        await message.answer(f"🗣 Распознано: <i>{text}</i>", parse_mode="HTML")
        
        # Обновляем статус
        await status_msg.edit_text(TEXT_GENERATE)
        
        # Отправляем в очередь
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


# =====================================
# ФОТО
# =====================================
@router.message(F.photo)
async def on_photo(message: Message, **data):
    """
    Обработка фотографий еды
    
    Процесс:
    1. Получение самого большого размера фото
    2. Формирование URL для доступа
    3. Отправка в GPT с vision
    """
    user_id = message.from_user.id
    
    # Атомарное списание токена
    if not await deduct_token_atomic(user_id):
        await message.answer(TEXT_LIMIT_EXCEEDED)
        return
    
    try:
        logger.info(f"[Entry:Photo] User {user_id}: processing photo")
        
        # Получаем самое большое фото
        photo = message.photo[-1]
        file_size_mb = photo.file_size / (1024 * 1024) if photo.file_size else 0
        
        # Проверка размера (защита от слишком больших файлов)
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
        
        # Получаем файл
        file = await message.bot.get_file(photo.file_id)
        
        # Небольшая задержка для гарантии доступности файла
        await asyncio.sleep(0.3)
        
        # Формируем URL для доступа к фото
        url = f"https://api.telegram.org/file/bot{message.bot.token}/{file.file_path}"
        
        # Текстовое описание (если есть)
        caption = message.caption or "Определи все блюда на фото и рассчитай КБЖУ"
        
        # Отправляем в очередь
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


# =====================================
# ДРУГИЕ ТИПЫ МЕДИА (отклоняем)
# =====================================
@router.message(F.video | F.document | F.sticker | F.animation)
async def on_unsupported_media(message: Message):
    """Обработка неподдерживаемых типов медиа"""
    await message.answer(
        "⚠️ Этот тип сообщения не поддерживается.\n\n"
        "Пожалуйста, отправьте:\n"
        "📸 Фото блюда\n"
        "📝 Текстовое описание\n"
        "🎤 Голосовое сообщение"
    )