# import logging
# from app.api.gpt import ai_request
# from app.services.user import get_user_by_id
# from app.services.meals import (
#     parse_gpt_response,
#     save_meals,
#     get_today_summary,
#     MealParseError
# )
# from app.utils.messages import send_text, edit_text, delete_message
# from app.db.mysql import mysql

# logger = logging.getLogger(__name__)


# async def refund_token(user_id: int):
#     """Возвращает токен при ошибке"""
#     async with mysql.pool.acquire() as conn:
#         async with conn.cursor() as cur:
#             await cur.execute(
#                 "UPDATE users_tbl SET free_tokens = free_tokens + 1 WHERE tg_id = %s",
#                 (user_id,)
#             )
#     logger.info(f"[GPT Queue] Token refunded for user {user_id}")


# async def process_gpt_request(
#     ctx,
#     user_id: int,
#     message_id: int,
#     chat_id: int,
#     text: str = None,
#     image_url: str = None
# ):
#     """
#     Обрабатывает запрос к GPT и сохраняет результат
    
#     КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ:
#     - НЕ передаем историю дня в запрос к GPT
#     - GPT анализирует только ТЕКУЩЕЕ сообщение пользователя
#     - Историю показываем только в финальном ответе
#     """
#     try:
#         user = await get_user_by_id(user_id)
#         if not user:
#             await edit_text(
#                 chat_id,
#                 message_id,
#                 "⚠️ Пользователь не найден. Используйте /start"
#             )
#             return
        
#         user_tz = user.get("timezone", "Europe/Moscow")
        
#         # ИСПРАВЛЕНИЕ: Убрали добавление контекста к запросу!
#         # GPT должен анализировать ТОЛЬКО текущее сообщение
#         request_text = text or "Определи блюдо на фото и рассчитай КБЖУ"
        
#         logger.info(f"[GPT Queue] User {user_id}: requesting GPT")
#         code, raw_response = await ai_request(
#             user_id=user_id,
#             text=request_text,  # Только текущий запрос!
#             image_link=image_url
#         )
        
#         if code != 200:
#             await edit_text(
#                 chat_id,
#                 message_id,
#                 "⚠️ Не удалось получить ответ от AI. Попробуйте позже."
#             )
#             await refund_token(user_id)
#             return
        
#         # Парсим ответ
#         try:
#             parsed_data = await parse_gpt_response(raw_response)
            
#             # ПРОВЕРКА: Это не еда?
#             if parsed_data.get("is_not_food"):
#                 notes = parsed_data.get("notes", "Это не продукт питания")
#                 await edit_text(
#                     chat_id,
#                     message_id,
#                     f"🤔 {notes}\n\n"
#                     "Пожалуйста, отправьте:\n"
#                     "📸 Фото еды\n"
#                     "📝 Описание блюда\n"
#                     "🎤 Голосовое сообщение о еде"
#                 )
#                 await refund_token(user_id)
#                 logger.info(f"[GPT Queue] User {user_id}: not food, token refunded")
#                 return
            
#             logger.info(
#                 f"[GPT Queue] User {user_id}: parsed {len(parsed_data['items'])} items"
#             )
#         except MealParseError as e:
#             logger.error(f"[GPT Queue] User {user_id}: parse error: {e}")
#             await edit_text(
#                 chat_id,
#                 message_id,
#                 "⚠️ Не удалось распознать блюдо.\n\n"
#                 "Попробуйте:\n"
#                 "• Сфотографировать четче при хорошем освещении\n"
#                 "• Описать текстом с весом (например: 'гречка 200г с курицей 150г')\n"
#                 "• Указать точное количество продуктов"
#             )
#             await refund_token(user_id)
#             return
        
#         # Сохраняем в БД
#         try:
#             await save_meals(user_id, parsed_data, user_tz, image_file_id=None)
#             logger.info(f"[GPT Queue] User {user_id}: saved to DB")
#         except Exception as e:
#             logger.exception(f"[GPT Queue] User {user_id}: DB save error: {e}")
#             await edit_text(
#                 chat_id,
#                 message_id,
#                 "⚠️ Ошибка сохранения данных. Попробуйте еще раз."
#             )
#             await refund_token(user_id)
#             return
        
#         # ПОСЛЕ СОХРАНЕНИЯ получаем ОБНОВЛЕННЫЕ итоги
#         summary = await get_today_summary(user_id, user_tz)
#         totals = summary["totals"]
        
#         # Формируем ответ - показываем что ДОБАВИЛИ СЕЙЧАС
#         response = "✅ <b>Добавлено:</b>\n\n"
        
#         for item in parsed_data["items"]:
#             response += (
#                 f"🍽 <b>{item['name']}</b>\n"
#                 f"   Вес: {int(item['weight_grams'])}г\n"
#                 f"   Калории: {item['calories']:.1f} ккал\n"
#                 f"   БЖУ: {item['protein']:.1f}г • "
#                 f"{item['fat']:.1f}г • {item['carbs']:.1f}г\n"
#             )
            
#             confidence = item.get("confidence", 1.0)
#             if confidence < 0.7:
#                 response += f"   ⚠️ Примерная оценка (уверенность: {confidence:.0%})\n"
            
#             response += "\n"
        
#         # Рекомендации от GPT
#         if parsed_data.get("notes"):
#             response += f"💡 <b>Совет:</b>\n<i>{parsed_data['notes']}</i>\n\n"
        
#         # ОБНОВЛЕННЫЕ итоги дня (после добавления)
#         response += "━━━━━━━━━━━━━━━━\n"
#         response += f"📊 <b>Итого за день:</b>\n"
#         response += f"🔥 Калории: <b>{float(totals['total_calories']):.0f}</b> ккал\n"
#         response += f"🥩 Белки: {float(totals['total_protein']):.1f}г\n"
#         response += f"🧈 Жиры: {float(totals['total_fat']):.1f}г\n"
#         response += f"🍞 Углеводы: {float(totals['total_carbs']):.1f}г\n"
#         response += f"🍽 Приемов пищи: {totals['meals_count']}\n\n"
#         response += "📋 Команда /today для детального просмотра"
        
#         await edit_text(chat_id, message_id, response)
        
#         logger.info(f"[GPT Queue] User {user_id}: success")
        
#     except Exception as e:
#         logger.exception(f"[GPT Queue] User {user_id}: critical error: {e}")
#         try:
#             await delete_message(chat_id, message_id)
#             await send_text(
#                 chat_id,
#                 "⚠️ Произошла ошибка при обработке. "
#                 "Попробуйте еще раз или обратитесь в поддержку."
#             )
#             await refund_token(user_id)
#         except Exception:
#             pass

import logging
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from app.api.gpt import ai_request
from app.services.user import get_user_by_id
from app.services.meals import (
    parse_gpt_response,
    save_meals,
    get_today_summary,
    MealParseError
)
from app.utils.messages import send_text, edit_text, delete_message
from app.db.mysql import mysql
from app.bot.bot import bot

logger = logging.getLogger(__name__)


async def refund_token(user_id: int):
    """Возвращает токен при ошибке"""
    async with mysql.pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE users_tbl SET free_tokens = free_tokens + 1 WHERE tg_id = %s",
                (user_id,)
            )
    logger.info(f"[GPT Queue] Token refunded for user {user_id}")


async def get_last_meal_ids(user_id: int, count: int = 1) -> list:
    """Получает ID последних приемов пищи"""
    try:
        meals = await mysql.fetchall(
            """SELECT id FROM meals_history 
               WHERE tg_id = %s 
               ORDER BY meal_datetime DESC 
               LIMIT %s""",
            (user_id, count)
        )
        return [meal['id'] for meal in meals] if meals else []
    except Exception as e:
        logger.error(f"Error getting last meal IDs: {e}")
        return []


async def process_gpt_request(
    ctx,
    user_id: int,
    message_id: int,
    chat_id: int,
    text: str = None,
    image_url: str = None
):
    """
    Обрабатывает запрос к GPT и сохраняет результат
    
    НОВОЕ: Добавлена кнопка "Отменить добавление"
    """
    try:
        user = await get_user_by_id(user_id)
        if not user:
            await edit_text(
                chat_id,
                message_id,
                "⚠️ Пользователь не найден. Используйте /start"
            )
            return
        
        user_tz = user.get("timezone", "Europe/Moscow")
        request_text = text or "Определи блюдо на фото и рассчитай КБЖУ"
        
        logger.info(f"[GPT Queue] User {user_id}: requesting GPT")
        code, raw_response = await ai_request(
            user_id=user_id,
            text=request_text,
            image_link=image_url
        )
        
        if code != 200:
            await edit_text(
                chat_id,
                message_id,
                "⚠️ Не удалось получить ответ от AI. Попробуйте позже."
            )
            await refund_token(user_id)
            return
        
        # Парсим ответ
        try:
            parsed_data = await parse_gpt_response(raw_response)
            
            # ПРОВЕРКА: Это не еда?
            if parsed_data.get("is_not_food"):
                notes = parsed_data.get("notes", "Это не продукт питания")
                await edit_text(
                    chat_id,
                    message_id,
                    f"🤔 {notes}\n\n"
                    "Пожалуйста, отправьте:\n"
                    "📸 Фото еды\n"
                    "📝 Описание блюда\n"
                    "🎤 Голосовое сообщение о еде"
                )
                await refund_token(user_id)
                logger.info(f"[GPT Queue] User {user_id}: not food, token refunded")
                return
            
            logger.info(
                f"[GPT Queue] User {user_id}: parsed {len(parsed_data['items'])} items"
            )
        except MealParseError as e:
            logger.error(f"[GPT Queue] User {user_id}: parse error: {e}")
            await edit_text(
                chat_id,
                message_id,
                "⚠️ Не удалось распознать блюдо.\n\n"
                "Попробуйте:\n"
                "• Сфотографировать четче при хорошем освещении\n"
                "• Описать текстом с весом (например: 'гречка 200г с курицей 150г')\n"
                "• Указать точное количество продуктов"
            )
            await refund_token(user_id)
            return
        
        # СОХРАНЯЕМ количество добавленных блюд для кнопки отмены
        items_count = len(parsed_data["items"])
        
        # Сохраняем в БД
        try:
            await save_meals(user_id, parsed_data, user_tz, image_file_id=None)
            logger.info(f"[GPT Queue] User {user_id}: saved to DB")
        except Exception as e:
            logger.exception(f"[GPT Queue] User {user_id}: DB save error: {e}")
            await edit_text(
                chat_id,
                message_id,
                "⚠️ Ошибка сохранения данных. Попробуйте еще раз."
            )
            await refund_token(user_id)
            return
        
        # ПОЛУЧАЕМ ID последних добавленных блюд
        last_meal_ids = await get_last_meal_ids(user_id, items_count)
        
        # ПОСЛЕ СОХРАНЕНИЯ получаем ОБНОВЛЕННЫЕ итоги
        summary = await get_today_summary(user_id, user_tz)
        totals = summary["totals"]
        
        # Формируем ответ
        response = "✅ <b>Добавлено в рацион:</b>\n\n"
        
        for item in parsed_data["items"]:
            response += (
                f"🍽 <b>{item['name']}</b>\n"
                f"   Вес: {int(item['weight_grams'])}г\n"
                f"   Калории: {item['calories']:.1f} ккал\n"
                f"   БЖУ: {item['protein']:.1f}г • "
                f"{item['fat']:.1f}г • {item['carbs']:.1f}г\n"
            )
            
            confidence = item.get("confidence", 1.0)
            if confidence < 0.7:
                response += f"   ⚠️ Примерная оценка (уверенность: {confidence:.0%})\n"
            
            response += "\n"
        
        # Рекомендации от GPT
        if parsed_data.get("notes"):
            response += f"💡 <b>Совет:</b>\n<i>{parsed_data['notes']}</i>\n\n"
        
        # ОБНОВЛЕННЫЕ итоги дня
        response += "━━━━━━━━━━━━━━━━\n"
        response += f"📊 <b>Итого за день:</b>\n"
        response += f"🔥 Калории: <b>{float(totals['total_calories']):.0f}</b> ккал\n"
        response += f"🥩 Белки: {float(totals['total_protein']):.1f}г\n"
        response += f"🧈 Жиры: {float(totals['total_fat']):.1f}г\n"
        response += f"🍞 Углеводы: {float(totals['total_carbs']):.1f}г\n"
        response += f"🍽 Приемов пищи: {totals['meals_count']}"
        
        # СОЗДАЕМ КЛАВИАТУРУ С КНОПКОЙ ОТМЕНЫ
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="🗑 Отменить добавление",
                callback_data=f"undo_last:{','.join(map(str, last_meal_ids))}"
            )],
            [InlineKeyboardButton(
                text="📋 Все приемы за день",
                callback_data="show_today"
            )]
        ])
        
        # Отправляем сообщение с кнопками
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=response,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"[GPT Queue] Error editing message: {e}")
            # Если не удалось отредактировать - удаляем и отправляем новое
            await delete_message(chat_id, message_id)
            await bot.send_message(
                chat_id=chat_id,
                text=response,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        
        logger.info(f"[GPT Queue] User {user_id}: success")
        
    except Exception as e:
        logger.exception(f"[GPT Queue] User {user_id}: critical error: {e}")
        try:
            await delete_message(chat_id, message_id)
            await send_text(
                chat_id,
                "⚠️ Произошла ошибка при обработке. "
                "Попробуйте еще раз или обратитесь в поддержку."
            )
            await refund_token(user_id)
        except Exception:
            pass