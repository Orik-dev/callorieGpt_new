# import logging
# from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
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
# from app.bot.bot import bot

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


# async def get_last_meal_ids(user_id: int, count: int = 1) -> list:
#     """Получает ID последних приемов пищи"""
#     try:
#         meals = await mysql.fetchall(
#             """SELECT id FROM meals_history 
#                WHERE tg_id = %s 
#                ORDER BY meal_datetime DESC 
#                LIMIT %s""",
#             (user_id, count)
#         )
#         return [meal['id'] for meal in meals] if meals else []
#     except Exception as e:
#         logger.error(f"Error getting last meal IDs: {e}")
#         return []


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
    
#     НОВОЕ: Добавлена кнопка "Отменить добавление"
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
#         request_text = text or "Определи блюдо на фото и рассчитай КБЖУ"
        
#         logger.info(f"[GPT Queue] User {user_id}: requesting GPT")
#         code, raw_response = await ai_request(
#             user_id=user_id,
#             text=request_text,
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
        
#         # СОХРАНЯЕМ количество добавленных блюд для кнопки отмены
#         items_count = len(parsed_data["items"])
        
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
        
#         # ПОЛУЧАЕМ ID последних добавленных блюд
#         last_meal_ids = await get_last_meal_ids(user_id, items_count)
        
#         # ПОСЛЕ СОХРАНЕНИЯ получаем ОБНОВЛЕННЫЕ итоги
#         summary = await get_today_summary(user_id, user_tz)
#         totals = summary["totals"]
        
#         # Формируем ответ
#         response = "✅ <b>Добавлено в рацион:</b>\n\n"
        
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
        
#         # ОБНОВЛЕННЫЕ итоги дня
#         response += "━━━━━━━━━━━━━━━━\n"
#         response += f"📊 <b>Итого за день:</b>\n"
#         response += f"🔥 Калории: <b>{float(totals['total_calories']):.0f}</b> ккал\n"
#         response += f"🥩 Белки: {float(totals['total_protein']):.1f}г\n"
#         response += f"🧈 Жиры: {float(totals['total_fat']):.1f}г\n"
#         response += f"🍞 Углеводы: {float(totals['total_carbs']):.1f}г\n"
#         response += f"🍽 Приемов пищи: {totals['meals_count']}"
        
#         # СОЗДАЕМ КЛАВИАТУРУ С КНОПКОЙ ОТМЕНЫ
#         keyboard = InlineKeyboardMarkup(inline_keyboard=[
#             [InlineKeyboardButton(
#                 text="🗑 Отменить добавление",
#                 callback_data=f"undo_last:{','.join(map(str, last_meal_ids))}"
#             )],
#             [InlineKeyboardButton(
#                 text="📋 Все приемы за день",
#                 callback_data="show_today"
#             )]
#         ])
        
#         # Отправляем сообщение с кнопками
#         try:
#             await bot.edit_message_text(
#                 chat_id=chat_id,
#                 message_id=message_id,
#                 text=response,
#                 reply_markup=keyboard,
#                 parse_mode="HTML"
#             )
#         except Exception as e:
#             logger.error(f"[GPT Queue] Error editing message: {e}")
#             # Если не удалось отредактировать - удаляем и отправляем новое
#             await delete_message(chat_id, message_id)
#             await bot.send_message(
#                 chat_id=chat_id,
#                 text=response,
#                 reply_markup=keyboard,
#                 parse_mode="HTML"
#             )
        
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
import json
import uuid
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from app.api.gpt import ai_request
from app.services.user import get_user_by_id
from app.services.meals import (
    parse_gpt_response,
    save_meals,
    get_today_summary,
    MealParseError
)
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


async def save_pending_meal(user_id: int, parsed_data: dict, user_tz: str) -> str:
    """
    Сохраняет временные данные о блюде в Redis
    
    Returns:
        str: Уникальный ключ для callback
    """
    from app.db.redis_client import redis
    
    meal_key = str(uuid.uuid4())[:12]  # Короткий уникальный ID
    redis_key = f"pending_meal:{user_id}:{meal_key}"
    
    data_to_save = {
        "parsed_data": parsed_data,
        "user_tz": user_tz
    }
    
    # Сохраняем на 1 час
    await redis.set(redis_key, json.dumps(data_to_save, ensure_ascii=False), ex=3600)
    
    logger.info(f"[GPT Queue] Saved pending meal for user {user_id}, key={meal_key}")
    return meal_key


async def get_pending_meal(user_id: int, meal_key: str) -> dict:
    """Получает временные данные о блюде из Redis"""
    from app.db.redis_client import redis
    
    redis_key = f"pending_meal:{user_id}:{meal_key}"
    
    data = await redis.get(redis_key)
    if not data:
        return None
    
    return json.loads(data)


async def delete_pending_meal(user_id: int, meal_key: str):
    """Удаляет временные данные о блюде из Redis"""
    from app.db.redis_client import redis
    
    redis_key = f"pending_meal:{user_id}:{meal_key}"
    await redis.delete(redis_key)
    logger.info(f"[GPT Queue] Deleted pending meal for user {user_id}, key={meal_key}")


async def process_gpt_request(ctx, user_id: int, chat_id: int, message_id: int, text: str, image_url: str = None):
    """
    Обработка запроса к GPT для расчета калорий
    Теперь НЕ сохраняет сразу в БД, а показывает preview с кнопками
    """
    logger.info(f"[GPT Queue] Processing request for user {user_id}")
    
    try:
        # Получаем данные пользователя
        user = await get_user_by_id(user_id)
        if not user:
            logger.error(f"[GPT Queue] User {user_id} not found")
            return
        
        user_tz = user.get('timezone', 'UTC')
        
        # Отправляем запрос в GPT
        logger.info(f"[GPT Queue] Sending request to GPT API for user {user_id}")
        code, gpt_response = await ai_request(
            user_id=user_id,
            text=text,
            image_link=image_url
        )
        
        if code != 200 or not gpt_response:
            logger.error(f"[GPT Queue] Empty response from GPT for user {user_id}")
            await bot.send_message(
                chat_id=chat_id,
                text="❌ Не удалось обработать запрос. Попробуйте еще раз.",
                parse_mode="HTML"
            )
            await refund_token(user_id)
            return
        
        # Парсим ответ GPT
        try:
            parsed_data = await parse_gpt_response(gpt_response)
            logger.info(f"[GPT Queue] Parsed {len(parsed_data.get('items', []))} meals for user {user_id}")
        except MealParseError as e:
            logger.error(f"[GPT Queue] Parse error for user {user_id}: {e}")
            await bot.send_message(
                chat_id=chat_id,
                text=f"❌ Ошибка обработки: {str(e)}\n\nПопробуйте переформулировать запрос.",
                parse_mode="HTML"
            )
            await refund_token(user_id)
            return
        
        # Сохраняем временные данные в Redis
        meal_key = await save_pending_meal(user_id, parsed_data, user_tz)
        
        # Формируем сообщение с предпросмотром
        items = parsed_data.get('items', [])
        notes = parsed_data.get('notes', '')
        
        if not items:
            logger.warning(f"[GPT Queue] No items parsed for user {user_id}")
            await bot.send_message(
                chat_id=chat_id,
                text="❌ Не удалось распознать блюда. Попробуйте описать подробнее.",
                parse_mode="HTML"
            )
            await refund_token(user_id)
            return
        
        # Подсчитываем общие калории для предпросмотра
        total_calories = sum(m['calories'] for m in items)
        total_protein = sum(m['protein'] for m in items)
        total_fat = sum(m['fat'] for m in items)
        total_carbs = sum(m['carbs'] for m in items)
        
        message_text = "📋 <b>Что будет добавлено:</b>\n\n"
        
        for meal in items:
            message_text += f"🍽 <b>{meal['name']}</b>\n"
            message_text += f"   Вес: {meal['weight_grams']}г\n"
            message_text += f"   {meal['calories']} ккал • "
            message_text += f"{meal['protein']}б • {meal['fat']}ж • {meal['carbs']}у\n\n"
        
        if notes:
            message_text += f"💡 <b>Совет:</b>\n{notes}\n\n"
        
        message_text += "━━━━━━━━━━━━━━━━\n"
        message_text += "📊 <b>ИТОГО:</b>\n\n"
        message_text += f"🔥 {total_calories} ккал\n"
        message_text += f"🥩 Белки: {total_protein} г\n"
        message_text += f"🧈 Жиры: {total_fat} г\n"
        message_text += f"🍞 Углеводы: {total_carbs} г\n"
        message_text += f"🍽 Блюд: {len(items)}\n"
        message_text += "━━━━━━━━━━━━━━━━\n\n"
        message_text += "Добавить в рацион?"
        
        # Кнопки подтверждения
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Да, добавить",
                    callback_data=f"confirm_meal:{meal_key}"
                ),
                InlineKeyboardButton(
                    text="❌ Отменить",
                    callback_data=f"cancel_meal:{meal_key}"
                )
            ]
        ])
        
        await bot.send_message(
            chat_id=chat_id,
            text=message_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        logger.info(f"[GPT Queue] Sent preview to user {user_id}, meal_key={meal_key}")
        
    except Exception as e:
        logger.exception(f"[GPT Queue] Unexpected error for user {user_id}: {e}")
        await bot.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при обработке. Попробуйте еще раз.",
            parse_mode="HTML"
        )
        await refund_token(user_id)


async def confirm_meal_addition(ctx, user_id: int, meal_key: str, message_id: int):
    """
    Подтверждение добавления блюда в рацион
    """
    logger.info(f"[GPT Queue] Confirming meal for user {user_id}, key={meal_key}")
    
    try:
        # Получаем данные из Redis
        pending_data = await get_pending_meal(user_id, meal_key)
        
        if not pending_data:
            await bot.edit_message_text(
                chat_id=user_id,
                message_id=message_id,
                text="❌ Данные устарели. Попробуйте еще раз.",
                parse_mode="HTML"
            )
            return
        
        parsed_data = pending_data['parsed_data']
        user_tz = pending_data['user_tz']
        
        # Сохраняем в БД
        items = parsed_data.get('items', [])
        saved_count = await save_meals(user_id, items, user_tz)
        logger.info(f"[GPT Queue] Saved {saved_count} meals for user {user_id}")
        
        # Получаем итоги за день
        summary = await get_today_summary(user_id, user_tz)
        
        # Формируем сообщение с результатом
        notes = parsed_data.get('notes', '')
        
        message_text = "✅ <b>Добавлено:</b>\n\n"
        
        for meal in items:
            message_text += f"🍽 <b>{meal['name']}</b>\n"
            message_text += f"   Вес: {meal['weight_grams']}г\n"
            message_text += f"   {meal['calories']} ккал • "
            message_text += f"{meal['protein']}б • {meal['fat']}ж • {meal['carbs']}у\n\n"
        
        if notes:
            message_text += f"💡 <b>Совет:</b>\n{notes}\n\n"
        
        message_text += "━━━━━━━━━━━━━━━━\n"
        message_text += "📊 <b>ИТОГО ЗА ДЕНЬ:</b>\n\n"
        message_text += f"🔥 {summary['total_calories']} ккал\n"
        message_text += f"🥩 Белки: {summary['total_protein']} г\n"
        message_text += f"🧈 Жиры: {summary['total_fat']} г\n"
        message_text += f"🍞 Углеводы: {summary['total_carbs']} г\n"
        message_text += f"🍽 Приемов пищи: {summary['meal_count']}\n"
        message_text += "━━━━━━━━━━━━━━━━"
        
        # Кнопки для дальнейших действий
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🗑 Отменить добавление",
                    callback_data=f"undo_meal:{meal_key}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📋 Все приемы за день",
                    callback_data="show_today"
                )
            ]
        ])
        
        await bot.edit_message_text(
            chat_id=user_id,
            message_id=message_id,
            text=message_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        # Удаляем из Redis
        await delete_pending_meal(user_id, meal_key)
        
    except Exception as e:
        logger.exception(f"[GPT Queue] Error confirming meal for user {user_id}: {e}")
        await bot.edit_message_text(
            chat_id=user_id,
            message_id=message_id,
            text="❌ Ошибка при добавлении. Попробуйте еще раз.",
            parse_mode="HTML"
        )


async def cancel_meal_addition(ctx, user_id: int, meal_key: str, message_id: int):
    """
    Отмена добавления блюда
    """
    logger.info(f"[GPT Queue] Canceling meal for user {user_id}, key={meal_key}")
    
    try:
        # Удаляем из Redis
        await delete_pending_meal(user_id, meal_key)
        
        # Возвращаем токен
        await refund_token(user_id)
        
        await bot.edit_message_text(
            chat_id=user_id,
            message_id=message_id,
            text="❌ Добавление отменено.\n\nОтправьте новое фото или опишите блюдо текстом.",
            parse_mode="HTML"
        )
        
    except Exception as e:
        logger.exception(f"[GPT Queue] Error canceling meal for user {user_id}: {e}")
        await bot.edit_message_text(
            chat_id=user_id,
            message_id=message_id,
            text="❌ Ошибка при отмене. Попробуйте еще раз.",
            parse_mode="HTML"
        )