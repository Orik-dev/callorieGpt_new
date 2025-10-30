# import logging
# from app.api.gpt import ai_request
# from app.services.user import deduct_token
# from app.bot.bot import send_markdown, send_text
# from app.utils.formatter import format_answer  # ← Вот тут импортируем
# # from app.config import settings — если нужно

# logger = logging.getLogger(__name__)

# async def process_gpt_request(
#     ctx,
#     user_id: int,
#     message_id: int,
#     chat_id: int,
#     text: str = None,
#     image_url: str = None
# ):
#     try:
#         # Отобразим статус "Генерируется..."
#         await send_markdown(chat_id, message_id, "Генерирую ответ..")

#         # Запрашиваем у OpenAI (или через свой API-прокси)
#         code, raw_response = await ai_request(user_id, text=text, image_link=image_url)

#         if code == 200:
#             # Преобразуем ответ в совместимый с Telegram формат
#             formatted_response = format_answer(raw_response)

#             # Отправляем пользователю
#             await send_text(chat_id, formatted_response, reply_to_message_id=message_id)

#             # Списываем токен
#             await deduct_token(user_id)
#         else:
#             await send_text(chat_id, "⚠️ Ошибка доступа к AI. Попробуйте позже.")

#     except Exception as e:
#         logger.exception(f"[TASK] Ошибка при обработке GPT-запроса: {e}")
#         await send_text(chat_id, "⚠️ Ошибка при обработке. Попробуйте позже.")

# app/tasks/gpt_queue.py

import logging
from app.api.gpt import ai_request
from app.services.user import deduct_token
from app.utils.messages import send_text, edit_text, delete_message
from app.utils.formatter import format_answer

logger = logging.getLogger(__name__)

async def process_gpt_request(
    ctx,
    user_id: int,
    message_id: int,
    chat_id: int,
    text: str = None,
    image_url: str = None
):
    try:

        code, raw_response = await ai_request(user_id, text=text, image_link=image_url)

        if code == 200:
            formatted_response = format_answer(raw_response)
            await edit_text(chat_id, message_id, formatted_response)
            await deduct_token(user_id)
        else:
            await edit_text(chat_id, message_id, "⚠️ Ошибка доступа к AI. Попробуйте позже.")

    except Exception as e:
        await delete_message(chat_id, message_id)
        await send_text(chat_id, "⚠️ Ошибка при обработке. Попробуйте позже.")
