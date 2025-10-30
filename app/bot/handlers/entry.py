
# from aiogram import Router, F
# from aiogram.types import Message
# from app.services.user import get_or_create_user
# from app.utils.audio import ogg_to_text
# import logging

# router = Router()
# logger = logging.getLogger(__name__)

# TEXT_LIMIT_EXCEEDED = "🥲 Бесплатные запросы закончились. Используйте /subscribe"
# TEXT_GENERATE = "⏳ Генерирую ответ..."
# TEXT_ERROR = "⚠️ Ошибка. Попробуйте позже."


# @router.message(F.text)
# async def on_text(message: Message, **data):
#     user = await get_or_create_user(message.from_user.id, message.from_user.first_name)
#     if user["free_tokens"] == 0:
#         return await message.answer(TEXT_LIMIT_EXCEEDED)

#     msg = await message.answer(TEXT_GENERATE)

#     redis = data["redis"]
#     await redis.enqueue_job(
#         "process_gpt_request",
#         user_id=user["tg_id"],
#         message_id=msg.message_id,
#         chat_id=message.chat.id,
#         text=message.text
#     )


# @router.message(F.voice)
# async def on_voice(message: Message, **data):
#     user = await get_or_create_user(message.from_user.id, message.from_user.first_name)
#     if user["free_tokens"] == 0:
#         return await message.answer(TEXT_LIMIT_EXCEEDED)

#     try:
#         file = await message.bot.get_file(message.voice.file_id)
#         file_path = f"/shared-voice/{file.file_path.split('/')[-1]}"
#         await message.bot.download_file(file.file_path, destination=file_path)

#         text = ogg_to_text(file_path)
#         if not text:
#             return await message.answer("Ошибка при распознавании речи")

#         await message.answer(f"🗣️ Расшифровка: {text}")
#         msg = await message.answer(TEXT_GENERATE)

#         redis = data["redis"]
#         await redis.enqueue_job(
#             "process_gpt_request",
#             user_id=user["tg_id"],
#             message_id=msg.message_id,
#             chat_id=message.chat.id,
#             text=text
#         )

#     except Exception as e:
#         logger.exception(f"[Voice] Ошибка: {e}")
#         await message.answer("⚠️ Ошибка при обработке голосового сообщения.")


# @router.message(F.photo)
# async def on_photo(message: Message,  **data):
#     user = await get_or_create_user(message.from_user.id, message.from_user.first_name)
#     if user["free_tokens"] == 0:
#         return await message.answer(TEXT_LIMIT_EXCEEDED)

#     try:
#         photo = message.photo[-1]
#         file = await message.bot.get_file(photo.file_id)
#         url = f"https://api.telegram.org/file/bot{message.bot.token}/{file.file_path}"

#         caption = message.caption or "Фото еды"
#         msg = await message.answer(TEXT_GENERATE)

#         redis = data["redis"]
#         await redis.enqueue_job(
#             "process_gpt_request",
#             user_id=user["tg_id"],
#             message_id=msg.message_id,
#             chat_id=message.chat.id,
#             text=caption,
#             image_url=url
#         )

#     except Exception as e:
#         logger.exception(f"[Photo] Ошибка: {e}")
#         await message.answer("⚠️ Ошибка при обработке фото.")

from aiogram import Router, F
from aiogram.types import Message
from app.services.user import get_or_create_user
from app.utils.audio import ogg_to_text
import logging
import asyncio
router = Router()
logger = logging.getLogger(__name__)

TEXT_LIMIT_EXCEEDED = "🥲 Бесплатные запросы закончились. Используйте /subscribe"
TEXT_GENERATE = "⏳ Генерирую ответ..."

# 🧠 ТЕКСТОВЫЕ СООБЩЕНИЯ
@router.message(F.text)
async def on_text(message: Message, **data):
    user = await get_or_create_user(message.from_user.id, message.from_user.first_name)
    if user["free_tokens"] == 0:
        return await message.answer(TEXT_LIMIT_EXCEEDED)

    redis = data["redis"]
    # Отправляем "⏳"
    msg = await message.answer(TEXT_GENERATE)

    # Отправляем задачу в очередь
    await redis.enqueue_job(
        "process_gpt_request",
        user_id=user["tg_id"],
        message_id=msg.message_id,  # ← будем удалять его потом
        chat_id=message.chat.id,
        text=message.text
    )


# 🧠 ГОЛОСОВЫЕ СООБЩЕНИЯ
@router.message(F.voice)
async def on_voice(message: Message, **data):
    user = await get_or_create_user(message.from_user.id, message.from_user.first_name)
    if user["free_tokens"] == 0:
        return await message.answer(TEXT_LIMIT_EXCEEDED)

    try:
        file = await message.bot.get_file(message.voice.file_id)
        file_path = f"/shared-voice/{file.file_path.split('/')[-1]}"
        await message.bot.download_file(file.file_path, destination=file_path)

        text = ogg_to_text(file_path)
        if not text:
            return await message.answer("Ошибка при распознавании речи")

        await message.answer(f"🗣️ Расшифровка: {text}")

        redis = data["redis"]
        msg = await message.answer(TEXT_GENERATE)

        await redis.enqueue_job(
            "process_gpt_request",
            user_id=user["tg_id"],
            message_id=msg.message_id,
            chat_id=message.chat.id,
            text=text
        )

    except Exception as e:
        logger.exception(f"[Voice] Ошибка: {e}")
        await message.answer("⚠️ Ошибка при обработке голосового сообщения.")


# 🧠 ФОТО
@router.message(F.photo)
async def on_photo(message: Message, **data):
    user = await get_or_create_user(message.from_user.id, message.from_user.first_name)
    if user["free_tokens"] == 0:
        return await message.answer(TEXT_LIMIT_EXCEEDED)

    try:
        photo = message.photo[-1]
        file = await message.bot.get_file(photo.file_id)
        await asyncio.sleep(1)
        url = f"https://api.telegram.org/file/bot{message.bot.token}/{file.file_path}"

        caption = message.caption or "Фото еды"
        redis = data["redis"]
        msg = await message.answer(TEXT_GENERATE)

        await redis.enqueue_job(
            "process_gpt_request",
            user_id=user["tg_id"],
            message_id=msg.message_id,
            chat_id=message.chat.id,
            text=caption,
            image_url=url
        )

    except Exception as e:
        logger.exception(f"[Photo] Ошибка: {e}")
        await message.answer("⚠️ Ошибка при обработке фото.")
