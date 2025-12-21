# import logging
# import json
# from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
# from aiogram.exceptions import TelegramBadRequest
# from app.api.gpt import ai_request
# from app.services.user import get_user_by_id
# from app.services.meals import (
#     parse_gpt_response,
#     save_meals,
#     get_today_summary,
#     get_last_meal,
#     update_meal,
#     delete_multiple_meals,
#     delete_meal,
#     MealParseError
# )
# from app.db.mysql import mysql
# from app.bot.bot import bot
# import pytz
# from datetime import datetime

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


# async def delete_message_safe(chat_id: int, message_id: int):
#     """
#     Безопасное удаление сообщения (не падает при ошибке)
#     """
#     try:
#         await bot.delete_message(chat_id=chat_id, message_id=message_id)
#         logger.debug(f"[GPT Queue] Deleted status message {message_id}")
#     except TelegramBadRequest as e:
#         if "message to delete not found" in str(e).lower():
#             logger.debug(f"[GPT Queue] Message {message_id} already deleted")
#         else:
#             logger.warning(f"[GPT Queue] Failed to delete message {message_id}: {e}")
#     except Exception as e:
#         logger.warning(f"[GPT Queue] Unexpected error deleting message {message_id}: {e}")


# async def process_gpt_request(ctx, user_id: int, chat_id: int, message_id: int, text: str, image_url: str = None):
#     """
#     Обработка запроса к GPT для расчета калорий
    
#     НОВАЯ ЛОГИКА: Сразу сохраняет в БД, показывает итоги + кнопку отмены
#     ✅ Удаляет статусное сообщение после обработки
#     """
#     logger.info(f"[GPT Queue] Processing request for user {user_id}")
    
#     try:
#         user = await get_user_by_id(user_id)
#         if not user:
#             logger.error(f"[GPT Queue] User {user_id} not found")
#             await delete_message_safe(chat_id, message_id)
#             return
        
#         user_tz = user.get('timezone', 'UTC')
        
#         logger.info(f"[GPT Queue] Sending request to GPT API for user {user_id}")
#         code, gpt_response = await ai_request(
#             user_id=user_id,
#             text=text,
#             image_link=image_url
#         )
        
#         if code != 200 or not gpt_response:
#             logger.error(f"[GPT Queue] Empty response from GPT for user {user_id}")
#             await delete_message_safe(chat_id, message_id)
#             await bot.send_message(
#                 chat_id=chat_id,
#                 text="❌ Не удалось обработать запрос. Попробуйте еще раз.",
#                 parse_mode="HTML"
#             )
#             await refund_token(user_id)
#             return
        
#         try:
#             parsed_data = await parse_gpt_response(gpt_response)
#             logger.info(f"[GPT Queue] Parsed {len(parsed_data.get('items', []))} meals for user {user_id}")
#         except MealParseError as e:
#             logger.error(f"[GPT Queue] Parse error for user {user_id}: {e}")
#             await delete_message_safe(chat_id, message_id)
#             await bot.send_message(
#                 chat_id=chat_id,
#                 text=f"❌ Ошибка обработки: {str(e)}\n\nПопробуйте переформулировать запрос.",
#                 parse_mode="HTML"
#             )
#             await refund_token(user_id)
#             return
        
#         items = parsed_data.get('items', [])
#         notes = parsed_data.get('notes', '')
        
#         # Проверка на "не еда"
#         if not items or parsed_data.get('is_not_food'):
#             logger.warning(f"[GPT Queue] Not food detected for user {user_id}")
#             await delete_message_safe(chat_id, message_id)
#             await bot.send_message(
#                 chat_id=chat_id,
#                 text=f"❌ {notes or 'Это не продукт питания. Отправьте фото еды или опишите блюдо.'}",
#                 parse_mode="HTML"
#             )
#             await refund_token(user_id)
#             return
        
#         # ✅ СРАЗУ СОХРАНЯЕМ В БД (без подтверждения)
#         result = await save_meals(user_id, parsed_data, user_tz, image_url)
#         added_meal_ids = result.get('added_meal_ids', [])
        
#         logger.info(f"[GPT Queue] Saved meals for user {user_id}, IDs: {added_meal_ids}")
        
#         # Получаем обновленные итоги за день
#         summary = await get_today_summary(user_id, user_tz)
#         totals = summary["totals"]
        
#         # Формируем сообщение
#         tz = pytz.timezone(user_tz)
#         today = datetime.now(tz).strftime("%d.%m.%Y")
        
#         message_text = "✅ <b>Добавлено в рацион:</b>\n\n"
        
#         for meal in items:
#             message_text += f"🍽 <b>{meal['name']}</b>\n"
#             message_text += f"   {meal['weight_grams']}г • "
#             message_text += f"{meal['calories']} ккал • "
#             message_text += f"{meal['protein']}б • {meal['fat']}ж • {meal['carbs']}у\n\n"
        
#         if notes:
#             message_text += f"💡 <b>{notes}</b>\n\n"
        
#         message_text += "━━━━━━━━━━━━━━━━\n"
#         message_text += f"📊 <b>Итоги за {today}:</b>\n\n"
#         message_text += f"🔥 Калории: <b>{float(totals['total_calories']):.0f}</b> ккал\n"
#         message_text += f"🥩 Белки: <b>{float(totals['total_protein']):.1f}</b> г\n"
#         message_text += f"🧈 Жиры: <b>{float(totals['total_fat']):.1f}</b> г\n"
#         message_text += f"🍞 Углеводы: <b>{float(totals['total_carbs']):.1f}</b> г\n"
#         message_text += f"🍽 Приемов: {totals['meals_count']}\n"
#         message_text += "━━━━━━━━━━━━━━━━\n\n"
#         message_text += "💡 <i>Команда /food для просмотра истории</i>"
        
#         # Кнопки
#         buttons = []
        
#         # Кнопка отмены (60 секунд)
#         if added_meal_ids:
#             meal_ids_str = ','.join(map(str, added_meal_ids))
#             buttons.append([
#                 InlineKeyboardButton(
#                     text="🗑 Отменить добавление",
#                     callback_data=f"undo_last:{meal_ids_str}"
#                 )
#             ])
        
#         # Кнопка показа всех приемов
#         buttons.append([
#             InlineKeyboardButton(
#                 text="📋 Все приемы за день",
#                 callback_data="show_today"
#             )
#         ])
        
#         keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
#         # ✅ УДАЛЯЕМ статусное сообщение и отправляем результат
#         await delete_message_safe(chat_id, message_id)
#         await bot.send_message(
#             chat_id=chat_id,
#             text=message_text,
#             reply_markup=keyboard,
#             parse_mode="HTML"
#         )
        
#         logger.info(f"[GPT Queue] Successfully processed and saved for user {user_id}")
        
#     except Exception as e:
#         logger.exception(f"[GPT Queue] Unexpected error for user {user_id}: {e}")
#         try:
#             await delete_message_safe(chat_id, message_id)
#             await bot.send_message(
#                 chat_id=chat_id,
#                 text="❌ Произошла ошибка при обработке. Попробуйте еще раз.",
#                 parse_mode="HTML"
#             )
#         except:
#             pass
#         await refund_token(user_id)


# async def process_meal_edit(ctx, user_id: int, chat_id: int, message_id: int, text: str):
#     """
#     Обработка текстового редактирования последнего приема пищи
    
#     Примеры команд:
#     - "исправь последнее - менее жирное"
#     - "сделай менее калорийным"
#     - "убери гречку"
    
#     ✅ Удаляет статусное сообщение после обработки
#     """
#     logger.info(f"[GPT Queue] Processing meal edit for user {user_id}: {text}")
    
#     try:
#         user = await get_user_by_id(user_id)
#         if not user:
#             await delete_message_safe(chat_id, message_id)
#             return
        
#         user_tz = user.get('timezone', 'UTC')
        
#         # Получаем последний прием пищи
#         last_meal = await get_last_meal(user_id, user_tz)
        
#         if not last_meal:
#             await delete_message_safe(chat_id, message_id)
#             await bot.send_message(
#                 chat_id=chat_id,
#                 text="❌ Нет приемов пищи для редактирования.\n\nСначала добавьте блюдо.",
#                 parse_mode="HTML"
#             )
#             await refund_token(user_id)
#             return
        
#         # Формируем промпт для GPT
#         edit_prompt = f"""Пользователь хочет отредактировать последний прием пищи.

# ТЕКУЩИЕ ДАННЫЕ:
# Название: {last_meal['food_name']}
# Вес: {last_meal['weight_grams']}г
# Калории: {last_meal['calories']} ккал
# Белки: {last_meal['protein']}г
# Жиры: {last_meal['fat']}г
# Углеводы: {last_meal['carbs']}г

# ЗАПРОС ПОЛЬЗОВАТЕЛЯ: {text}

# Верни обновленные данные в JSON формате:
# {{
#   "items": [
#     {{
#       "name": "обновленное название",
#       "weight_grams": вес,
#       "calories": калории,
#       "protein": белки,
#       "fat": жиры,
#       "carbs": углеводы,
#       "confidence": 0.9
#     }}
#   ],
#   "notes": "Что изменилось"
# }}

# ВАЖНО: 
# - Если пользователь просит "менее жирное" - уменьши жиры на 20-30% и пересчитай калории.
# - Если "менее калорийное" - уменьши порцию на 20-30%.
# - Если "больше" - увеличь на 20-30%.
# - Если указан конкретный вес - установи его.
# """
        
#         code, gpt_response = await ai_request(
#             user_id=user_id,
#             text=edit_prompt
#         )
        
#         if code != 200 or not gpt_response:
#             await delete_message_safe(chat_id, message_id)
#             await bot.send_message(
#                 chat_id=chat_id,
#                 text="❌ Не удалось обработать редактирование.",
#                 parse_mode="HTML"
#             )
#             await refund_token(user_id)
#             return
        
#         parsed_data = await parse_gpt_response(gpt_response)
#         items = parsed_data.get('items', [])
#         notes = parsed_data.get('notes', '')
        
#         if not items:
#             await delete_message_safe(chat_id, message_id)
#             await bot.send_message(
#                 chat_id=chat_id,
#                 text="❌ Не удалось обработать редактирование.",
#                 parse_mode="HTML"
#             )
#             await refund_token(user_id)
#             return
        
#         # Обновляем прием пищи в БД
#         new_data = items[0]
#         await update_meal(
#             meal_id=last_meal['id'],
#             user_id=user_id,
#             food_name=new_data['name'],
#             weight_grams=new_data['weight_grams'],
#             calories=new_data['calories'],
#             protein=new_data['protein'],
#             fat=new_data['fat'],
#             carbs=new_data['carbs']
#         )
        
#         # Получаем обновленные итоги
#         summary = await get_today_summary(user_id, user_tz)
#         totals = summary["totals"]
        
#         message_text = "✅ <b>Прием пищи обновлен:</b>\n\n"
#         message_text += f"🍽 <b>{new_data['name']}</b>\n"
#         message_text += f"   {new_data['weight_grams']}г • "
#         message_text += f"{new_data['calories']} ккал • "
#         message_text += f"{new_data['protein']}б • {new_data['fat']}ж • {new_data['carbs']}у\n\n"
        
#         if notes:
#             message_text += f"💡 {notes}\n\n"
        
#         message_text += "━━━━━━━━━━━━━━━━\n"
#         message_text += "📊 <b>Обновленные итоги:</b>\n\n"
#         message_text += f"🔥 {float(totals['total_calories']):.0f} ккал\n"
#         message_text += f"🥩 {float(totals['total_protein']):.1f}г\n"
#         message_text += f"🧈 {float(totals['total_fat']):.1f}г\n"
#         message_text += f"🍞 {float(totals['total_carbs']):.1f}г\n"
        
#         # ✅ УДАЛЯЕМ статусное сообщение и отправляем результат
#         await delete_message_safe(chat_id, message_id)
#         await bot.send_message(
#             chat_id=chat_id,
#             text=message_text,
#             parse_mode="HTML"
#         )
        
#         logger.info(f"[GPT Queue] Successfully edited meal for user {user_id}")
        
#     except Exception as e:
#         logger.exception(f"[GPT Queue] Error editing meal for user {user_id}: {e}")
#         await delete_message_safe(chat_id, message_id)
#         await bot.send_message(
#             chat_id=chat_id,
#             text="❌ Ошибка при редактировании.",
#             parse_mode="HTML"
#         )
#         await refund_token(user_id)


# async def process_calculation_only(ctx, user_id: int, chat_id: int, message_id: int, text: str):
#     """
#     Обработка запроса "только посчитать" - БЕЗ добавления в рацион
    
#     Примеры:
#     - "посчитай калории в гречке 200г"
#     - "сколько калорий в яблоке"
#     - "КБЖУ банана"
    
#     ✅ Удаляет статусное сообщение после обработки
#     """
#     logger.info(f"[GPT Queue] Processing calculation only for user {user_id}")
    
#     try:
#         user = await get_user_by_id(user_id)
#         if not user:
#             logger.error(f"[GPT Queue] User {user_id} not found")
#             await delete_message_safe(chat_id, message_id)
#             return
        
#         # Отправляем запрос к GPT
#         code, gpt_response = await ai_request(
#             user_id=user_id,
#             text=text
#         )
        
#         if code != 200 or not gpt_response:
#             await delete_message_safe(chat_id, message_id)
#             await bot.send_message(
#                 chat_id=chat_id,
#                 text="❌ Не удалось обработать запрос. Попробуйте еще раз.",
#                 parse_mode="HTML"
#             )
#             return
        
#         try:
#             parsed_data = await parse_gpt_response(gpt_response)
#         except MealParseError as e:
#             logger.error(f"[GPT Queue] Parse error for user {user_id}: {e}")
#             await delete_message_safe(chat_id, message_id)
#             await bot.send_message(
#                 chat_id=chat_id,
#                 text=f"❌ Ошибка обработки: {str(e)}",
#                 parse_mode="HTML"
#             )
#             return
        
#         items = parsed_data.get('items', [])
#         notes = parsed_data.get('notes', '')
        
#         if not items:
#             await delete_message_safe(chat_id, message_id)
#             await bot.send_message(
#                 chat_id=chat_id,
#                 text="❌ Не удалось распознать блюда.",
#                 parse_mode="HTML"
#             )
#             return
        
#         # Формируем сообщение с расчетами (БЕЗ добавления в БД)
#         total_calories = sum(m['calories'] for m in items)
#         total_protein = sum(m['protein'] for m in items)
#         total_fat = sum(m['fat'] for m in items)
#         total_carbs = sum(m['carbs'] for m in items)
        
#         message_text = "🔢 <b>Расчет калорийности:</b>\n\n"
        
#         for meal in items:
#             message_text += f"🍽 <b>{meal['name']}</b>\n"
#             message_text += f"   {meal['weight_grams']}г • "
#             message_text += f"{meal['calories']} ккал • "
#             message_text += f"{meal['protein']}б • {meal['fat']}ж • {meal['carbs']}у\n\n"
        
#         message_text += "━━━━━━━━━━━━━━━━\n"
#         message_text += "📊 <b>ИТОГО:</b>\n\n"
#         message_text += f"🔥 {total_calories} ккал\n"
#         message_text += f"🥩 Белки: {total_protein} г\n"
#         message_text += f"🧈 Жиры: {total_fat} г\n"
#         message_text += f"🍞 Углеводы: {total_carbs} г\n"
        
#         if notes:
#             message_text += f"\n💡 <b>{notes}</b>\n"
        
#         message_text += "\n━━━━━━━━━━━━━━━━\n"
#         message_text += "ℹ️ <i>Это только расчет, данные НЕ добавлены в рацион.</i>\n\n"
#         message_text += "💡 Чтобы добавить, отправьте описание без команд расчета."
        
#         # ✅ УДАЛЯЕМ статусное сообщение и отправляем результат
#         await delete_message_safe(chat_id, message_id)
#         await bot.send_message(
#             chat_id=chat_id,
#             text=message_text,
#             parse_mode="HTML"
#         )
        
#         logger.info(f"[GPT Queue] Calculation completed for user {user_id} (not saved)")
        
#     except Exception as e:
#         logger.exception(f"[GPT Queue] Unexpected error in calculation for user {user_id}: {e}")
#         await delete_message_safe(chat_id, message_id)
#         await bot.send_message(
#             chat_id=chat_id,
#             text="❌ Произошла ошибка при расчете.",
#             parse_mode="HTML"
#         )


# async def process_meal_delete(ctx, user_id: int, chat_id: int, message_id: int, text: str):
#     """
#     Обработка текстового удаления приема пищи
    
#     Примеры команд:
#     - "убери последнее"
#     - "удали гречку"
#     - "очисти рацион"
    
#     ✅ Удаляет статусное сообщение после обработки
#     """
#     logger.info(f"[GPT Queue] Processing meal delete for user {user_id}: {text}")
    
#     try:
#         user = await get_user_by_id(user_id)
#         if not user:
#             await delete_message_safe(chat_id, message_id)
#             return
        
#         user_tz = user.get('timezone', 'UTC')
#         text_lower = text.lower()
        
#         # Проверяем что именно удалять
#         if "всё" in text_lower or "все" in text_lower or "рацион" in text_lower:
#             # Удалить все приемы за сегодня
#             summary = await get_today_summary(user_id, user_tz)
#             meals = summary.get("meals", [])
            
#             if not meals:
#                 await delete_message_safe(chat_id, message_id)
#                 await bot.send_message(
#                     chat_id=chat_id,
#                     text="📭 Сегодня нет приемов пищи для удаления.",
#                     parse_mode="HTML"
#                 )
#                 await refund_token(user_id)
#                 return
            
#             meal_ids = [meal['id'] for meal in meals]
#             deleted_count = await delete_multiple_meals(meal_ids, user_id)
            
#             await delete_message_safe(chat_id, message_id)
#             await bot.send_message(
#                 chat_id=chat_id,
#                 text=f"✅ Удалено приемов пищи: <b>{deleted_count}</b>\n\nРацион за сегодня очищен.",
#                 parse_mode="HTML"
#             )
            
#             logger.info(f"[GPT Queue] Deleted all meals for user {user_id}")
#             return
        
#         # Удалить последнее
#         if "последн" in text_lower:
#             last_meal = await get_last_meal(user_id, user_tz)
            
#             if not last_meal:
#                 await delete_message_safe(chat_id, message_id)
#                 await bot.send_message(
#                     chat_id=chat_id,
#                     text="❌ Нет приемов пищи для удаления.",
#                     parse_mode="HTML"
#                 )
#                 await refund_token(user_id)
#                 return
            
#             success = await delete_meal(last_meal['id'], user_id)
            
#             if success:
#                 summary = await get_today_summary(user_id, user_tz)
#                 totals = summary["totals"]
                
#                 message_text = f"✅ <b>Удалено:</b> {last_meal['food_name']}\n\n"
#                 message_text += "━━━━━━━━━━━━━━━━\n"
#                 message_text += "📊 <b>Обновленные итоги:</b>\n\n"
#                 message_text += f"🔥 {float(totals['total_calories']):.0f} ккал\n"
#                 message_text += f"🥩 {float(totals['total_protein']):.1f}г\n"
#                 message_text += f"🧈 {float(totals['total_fat']):.1f}г\n"
#                 message_text += f"🍞 {float(totals['total_carbs']):.1f}г\n"
                
#                 await delete_message_safe(chat_id, message_id)
#                 await bot.send_message(
#                     chat_id=chat_id,
#                     text=message_text,
#                     parse_mode="HTML"
#                 )
                
#                 logger.info(f"[GPT Queue] Deleted last meal for user {user_id}")
#             else:
#                 await delete_message_safe(chat_id, message_id)
#                 await bot.send_message(
#                     chat_id=chat_id,
#                     text="❌ Не удалось удалить прием пищи.",
#                     parse_mode="HTML"
#                 )
            
#             return
        
#         # Удалить по названию блюда
#         summary = await get_today_summary(user_id, user_tz)
#         meals = summary.get("meals", [])
        
#         if not meals:
#             await delete_message_safe(chat_id, message_id)
#             await bot.send_message(
#                 chat_id=chat_id,
#                 text="📭 Сегодня нет приемов пищи.",
#                 parse_mode="HTML"
#             )
#             await refund_token(user_id)
#             return
        
#         # Ищем блюдо по частичному совпадению
#         meal_to_delete = None
#         for meal in reversed(meals):  # Ищем с конца (последние приемы)
#             meal_name_lower = meal['food_name'].lower()
#             # Убираем служебные слова
#             search_text = text_lower.replace('убери', '').replace('удали', '').replace('очисти', '').strip()
            
#             if search_text in meal_name_lower or meal_name_lower in search_text:
#                 meal_to_delete = meal
#                 break
        
#         if meal_to_delete:
#             success = await delete_meal(meal_to_delete['id'], user_id)
            
#             if success:
#                 summary = await get_today_summary(user_id, user_tz)
#                 totals = summary["totals"]
                
#                 message_text = f"✅ <b>Удалено:</b> {meal_to_delete['food_name']}\n\n"
#                 message_text += "━━━━━━━━━━━━━━━━\n"
#                 message_text += "📊 <b>Обновленные итоги:</b>\n\n"
#                 message_text += f"🔥 {float(totals['total_calories']):.0f} ккал\n"
#                 message_text += f"🥩 {float(totals['total_protein']):.1f}г\n"
#                 message_text += f"🧈 {float(totals['total_fat']):.1f}г\n"
#                 message_text += f"🍞 {float(totals['total_carbs']):.1f}г\n"
                
#                 await delete_message_safe(chat_id, message_id)
#                 await bot.send_message(
#                     chat_id=chat_id,
#                     text=message_text,
#                     parse_mode="HTML"
#                 )
                
#                 logger.info(f"[GPT Queue] Deleted meal by name for user {user_id}")
#             else:
#                 await delete_message_safe(chat_id, message_id)
#                 await bot.send_message(
#                     chat_id=chat_id,
#                     text="❌ Не удалось удалить прием пищи.",
#                     parse_mode="HTML"
#                 )
#         else:
#             # Не нашли блюдо - показываем список
#             text = "❓ <b>Блюдо не найдено</b>\n\n"
#             text += "Сегодня у вас:\n\n"
            
#             for idx, meal in enumerate(meals[-5:], 1):  # Последние 5
#                 time = meal["meal_datetime"].strftime("%H:%M")
#                 text += f"{idx}. {time} — {meal['food_name']}\n"
            
#             text += "\n💡 Попробуйте указать название точнее"
            
#             await delete_message_safe(chat_id, message_id)
#             await bot.send_message(
#                 chat_id=chat_id,
#                 text=text,
#                 parse_mode="HTML"
#             )
            
#             await refund_token(user_id)
        
#     except Exception as e:
#         logger.exception(f"[GPT Queue] Error deleting meal for user {user_id}: {e}")
#         await delete_message_safe(chat_id, message_id)
#         await bot.send_message(
#             chat_id=chat_id,
#             text="❌ Ошибка при удалении.",
#             parse_mode="HTML"
#         )
#         await refund_token(user_id)

import logging
import json
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest
from app.api.gpt import ai_request
from app.services.user import get_user_by_id
from app.services.meals import (
    parse_gpt_response,
    save_meals,
    get_today_summary,
    get_last_meal,
    update_meal,
    delete_multiple_meals,
    delete_meal,
    MealParseError
)
from app.db.mysql import mysql
from app.bot.bot import bot
import pytz
from datetime import datetime

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


async def delete_message_safe(chat_id: int, message_id: int):
    """
    Безопасное удаление сообщения (не падает при ошибке)
    """
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
        logger.debug(f"[GPT Queue] Deleted status message {message_id}")
    except TelegramBadRequest as e:
        if "message to delete not found" in str(e).lower():
            logger.debug(f"[GPT Queue] Message {message_id} already deleted")
        else:
            logger.warning(f"[GPT Queue] Failed to delete message {message_id}: {e}")
    except Exception as e:
        logger.warning(f"[GPT Queue] Unexpected error deleting message {message_id}: {e}")


async def process_gpt_request(ctx, user_id: int, chat_id: int, message_id: int, text: str, image_url: str = None):
    """
    Обработка запроса к GPT для расчета калорий
    
    НОВАЯ ЛОГИКА: Сразу сохраняет в БД, показывает итоги + кнопку отмены
    ✅ Удаляет статусное сообщение после обработки
    """
    logger.info(f"[GPT Queue] Processing request for user {user_id}")
    
    try:
        user = await get_user_by_id(user_id)
        if not user:
            logger.error(f"[GPT Queue] User {user_id} not found")
            await delete_message_safe(chat_id, message_id)
            return
        
        user_tz = user.get('timezone', 'UTC')
        
        logger.info(f"[GPT Queue] Sending request to GPT API for user {user_id}")
        code, gpt_response = await ai_request(
            user_id=user_id,
            text=text,
            image_link=image_url
        )
        
        if code != 200 or not gpt_response:
            logger.error(f"[GPT Queue] Empty response from GPT for user {user_id}")
            await delete_message_safe(chat_id, message_id)
            await bot.send_message(
                chat_id=chat_id,
                text="❌ Не удалось обработать запрос. Попробуйте еще раз.",
                parse_mode="HTML"
            )
            await refund_token(user_id)
            return
        
        try:
            parsed_data = await parse_gpt_response(gpt_response)
            logger.info(f"[GPT Queue] Parsed {len(parsed_data.get('items', []))} meals for user {user_id}")
        except MealParseError as e:
            logger.error(f"[GPT Queue] Parse error for user {user_id}: {e}")
            await delete_message_safe(chat_id, message_id)
            await bot.send_message(
                chat_id=chat_id,
                text=f"❌ Ошибка обработки: {str(e)}\n\nПопробуйте переформулировать запрос.",
                parse_mode="HTML"
            )
            await refund_token(user_id)
            return
        
        items = parsed_data.get('items', [])
        notes = parsed_data.get('notes', '')
        
        # Проверка на "не еда"
        if not items or parsed_data.get('is_not_food'):
            logger.warning(f"[GPT Queue] Not food detected for user {user_id}")
            await delete_message_safe(chat_id, message_id)
            await bot.send_message(
                chat_id=chat_id,
                text=f"❌ {notes or 'Это не продукт питания. Отправьте фото еды или опишите блюдо.'}",
                parse_mode="HTML"
            )
            await refund_token(user_id)
            return
        
        # ✅ СРАЗУ СОХРАНЯЕМ В БД (без подтверждения)
        result = await save_meals(user_id, parsed_data, user_tz, image_url)
        added_meal_ids = result.get('added_meal_ids', [])
        
        logger.info(f"[GPT Queue] Saved meals for user {user_id}, IDs: {added_meal_ids}")
        
        # Получаем обновленные итоги за день
        summary = await get_today_summary(user_id, user_tz)
        totals = summary["totals"]
        
        # Формируем сообщение
        tz = pytz.timezone(user_tz)
        today = datetime.now(tz).strftime("%d.%m.%Y")
        
        message_text = "✅ <b>Добавлено в рацион:</b>\n\n"
        
        for meal in items:
            message_text += f"🍽 <b>{meal['name']}</b>\n"
            message_text += f"   {meal['weight_grams']}г • "
            message_text += f"{meal['calories']} ккал • "
            message_text += f"{meal['protein']}б • {meal['fat']}ж • {meal['carbs']}у\n\n"
        
        if notes:
            message_text += f"💡 <b>{notes}</b>\n\n"
        
        message_text += "━━━━━━━━━━━━━━━━\n"
        message_text += f"📊 <b>Итоги за {today}:</b>\n\n"
        message_text += f"🔥 Калории: <b>{float(totals['total_calories']):.0f}</b> ккал\n"
        message_text += f"🥩 Белки: <b>{float(totals['total_protein']):.1f}</b> г\n"
        message_text += f"🧈 Жиры: <b>{float(totals['total_fat']):.1f}</b> г\n"
        message_text += f"🍞 Углеводы: <b>{float(totals['total_carbs']):.1f}</b> г\n"
        message_text += f"🍽 Приемов: {totals['meals_count']}\n"
        message_text += "━━━━━━━━━━━━━━━━\n\n"
        message_text += "💡 <i>Команда /food для просмотра истории</i>"
        
        # Кнопки
        buttons = []
        
        # Кнопка отмены (60 секунд)
        if added_meal_ids:
            meal_ids_str = ','.join(map(str, added_meal_ids))
            buttons.append([
                InlineKeyboardButton(
                    text="🗑 Отменить добавление",
                    callback_data=f"undo_last:{meal_ids_str}"
                )
            ])
        
        # Кнопка показа всех приемов
        buttons.append([
            InlineKeyboardButton(
                text="📋 Все приемы за день",
                callback_data="show_today"
            )
        ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        # ✅ УДАЛЯЕМ статусное сообщение и отправляем результат
        await delete_message_safe(chat_id, message_id)
        await bot.send_message(
            chat_id=chat_id,
            text=message_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"[GPT Queue] Successfully processed and saved for user {user_id}")
        
    except Exception as e:
        logger.exception(f"[GPT Queue] Unexpected error for user {user_id}: {e}")
        try:
            await delete_message_safe(chat_id, message_id)
            await bot.send_message(
                chat_id=chat_id,
                text="❌ Произошла ошибка при обработке. Попробуйте еще раз.",
                parse_mode="HTML"
            )
        except:
            pass
        await refund_token(user_id)


async def process_meal_edit(ctx, user_id: int, chat_id: int, message_id: int, text: str):
    """
    Обработка текстового редактирования последнего приема пищи
    
    ✅ УЛУЧШЕНО: Детальный промпт с примерами + fallback если GPT не понял
    
    Примеры команд:
    - "исправь последнее - менее жирное"
    - "сделай менее калорийным"
    - "убери гречку"
    
    ✅ Удаляет статусное сообщение после обработки
    """
    logger.info(f"[GPT Queue] Processing meal edit for user {user_id}: {text}")
    
    try:
        user = await get_user_by_id(user_id)
        if not user:
            await delete_message_safe(chat_id, message_id)
            return
        
        user_tz = user.get('timezone', 'UTC')
        
        # Получаем последний прием пищи
        last_meal = await get_last_meal(user_id, user_tz)
        
        if not last_meal:
            await delete_message_safe(chat_id, message_id)
            await bot.send_message(
                chat_id=chat_id,
                text="❌ Нет приемов пищи для редактирования.\n\nСначала добавьте блюдо.",
                parse_mode="HTML"
            )
            await refund_token(user_id)
            return
        
        # ✅ УЛУЧШЕННЫЙ ПРОМПТ с примерами и четкими инструкциями
        edit_prompt = f"""Ты редактируешь прием пищи. ОБЯЗАТЕЛЬНО верни items с ОДНИМ элементом.

ТЕКУЩИЕ ДАННЫЕ:
Название: {last_meal['food_name']}
Вес: {last_meal['weight_grams']}г
Калории: {last_meal['calories']} ккал
Белки: {last_meal['protein']}г
Жиры: {last_meal['fat']}г
Углеводы: {last_meal['carbs']}г

ЗАПРОС ПОЛЬЗОВАТЕЛЯ: "{text}"

ПРИМЕРЫ ОБРАБОТКИ ЗАПРОСОВ:

1. "менее жирное" / "без жира" / "нежирное"
   → Уменьши жиры на 30-40%, пересчитай калории

2. "менее калорийное" / "легче" / "диетическое"
   → Уменьши порцию на 30% (все КБЖУ пропорционально)

3. "больше" / "двойная порция" / "побольше"
   → Увеличь все на 50-100%

4. "200г" / "измени вес на 250г"
   → Установи новый вес, пересчитай КБЖУ пропорционально

5. "добавь сметану" / "с маслом"
   → Увеличь жиры на 10г, калории на 90

6. "без масла" / "без майонеза"
   → Уменьши жиры на 10-15г

7. "больше белка"
   → Увеличь белки на 20-30%

8. Непонятный запрос
   → Верни текущие данные БЕЗ изменений

ФОРМАТ ОТВЕТА (JSON):
{{
  "items": [
    {{
      "name": "{last_meal['food_name']}",
      "weight_grams": {last_meal['weight_grams']},
      "calories": {last_meal['calories']},
      "protein": {last_meal['protein']},
      "fat": {last_meal['fat']},
      "carbs": {last_meal['carbs']},
      "confidence": 0.9
    }}
  ],
  "notes": "Что изменил или 'Не понял запрос'"
}}

КРИТИЧЕСКИ ВАЖНО: 
- ВСЕГДА возвращай items с ОДНИМ элементом
- Если не понял - верни текущие данные БЕЗ ИЗМЕНЕНИЙ
- В notes напиши что сделал или что не понял"""
        
        code, gpt_response = await ai_request(
            user_id=user_id,
            text=edit_prompt
        )
        
        if code != 200 or not gpt_response:
            await delete_message_safe(chat_id, message_id)
            await bot.send_message(
                chat_id=chat_id,
                text="❌ Не удалось обработать редактирование.",
                parse_mode="HTML"
            )
            await refund_token(user_id)
            return
        
        # ✅ ОБРАБОТКА ОШИБОК ПАРСИНГА
        try:
            parsed_data = await parse_gpt_response(gpt_response)
            items = parsed_data.get('items', [])
            notes = parsed_data.get('notes', '')
        except MealParseError as e:
            logger.warning(f"[GPT Queue] Parse error in edit: {e}")
            # Fallback: предлагаем переформулировать
            await delete_message_safe(chat_id, message_id)
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    "🤔 Не совсем понял, что нужно изменить.\n\n"
                    "<b>Попробуйте так:</b>\n"
                    "• \"сделай менее жирным\"\n"
                    "• \"уменьши порцию вдвое\"\n"
                    "• \"измени вес на 200г\"\n"
                    "• \"добавь сметану\"\n"
                    "• \"больше белка\"\n\n"
                    "Или опишите блюдо заново."
                ),
                parse_mode="HTML"
            )
            await refund_token(user_id)
            return
        
        # ✅ ПРОВЕРКА НА ПУСТОЙ items
        if not items:
            logger.warning(f"[GPT Queue] Empty items in edit response")
            await delete_message_safe(chat_id, message_id)
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    "🤔 Не понял, что нужно изменить.\n\n"
                    "<b>Примеры команд:</b>\n"
                    "• \"сделай менее жирным\"\n"
                    "• \"уменьши порцию\"\n"
                    "• \"200г вместо 150г\"\n"
                    "• \"добавь масло\"\n\n"
                    "💡 Или просто опишите блюдо заново"
                ),
                parse_mode="HTML"
            )
            await refund_token(user_id)
            return
        
        # Обновляем прием пищи в БД
        new_data = items[0]
        await update_meal(
            meal_id=last_meal['id'],
            user_id=user_id,
            food_name=new_data['name'],
            weight_grams=new_data['weight_grams'],
            calories=new_data['calories'],
            protein=new_data['protein'],
            fat=new_data['fat'],
            carbs=new_data['carbs']
        )
        
        # Получаем обновленные итоги
        summary = await get_today_summary(user_id, user_tz)
        totals = summary["totals"]
        
        message_text = "✅ <b>Прием пищи обновлен:</b>\n\n"
        message_text += f"🍽 <b>{new_data['name']}</b>\n"
        message_text += f"   {new_data['weight_grams']}г • "
        message_text += f"{new_data['calories']} ккал • "
        message_text += f"{new_data['protein']}б • {new_data['fat']}ж • {new_data['carbs']}у\n\n"
        
        if notes:
            message_text += f"💡 {notes}\n\n"
        
        message_text += "━━━━━━━━━━━━━━━━\n"
        message_text += "📊 <b>Обновленные итоги:</b>\n\n"
        message_text += f"🔥 {float(totals['total_calories']):.0f} ккал\n"
        message_text += f"🥩 {float(totals['total_protein']):.1f}г\n"
        message_text += f"🧈 {float(totals['total_fat']):.1f}г\n"
        message_text += f"🍞 {float(totals['total_carbs']):.1f}г\n"
        
        # ✅ УДАЛЯЕМ статусное сообщение и отправляем результат
        await delete_message_safe(chat_id, message_id)
        await bot.send_message(
            chat_id=chat_id,
            text=message_text,
            parse_mode="HTML"
        )
        
        logger.info(f"[GPT Queue] Successfully edited meal for user {user_id}")
        
    except Exception as e:
        logger.exception(f"[GPT Queue] Error editing meal for user {user_id}: {e}")
        await delete_message_safe(chat_id, message_id)
        await bot.send_message(
            chat_id=chat_id,
            text="❌ Ошибка при редактировании.",
            parse_mode="HTML"
        )
        await refund_token(user_id)


async def process_calculation_only(ctx, user_id: int, chat_id: int, message_id: int, text: str):
    """
    Обработка запроса "только посчитать" - БЕЗ добавления в рацион
    
    Примеры:
    - "посчитай калории в гречке 200г"
    - "сколько калорий в яблоке"
    - "КБЖУ банана"
    
    ✅ Удаляет статусное сообщение после обработки
    """
    logger.info(f"[GPT Queue] Processing calculation only for user {user_id}")
    
    try:
        user = await get_user_by_id(user_id)
        if not user:
            logger.error(f"[GPT Queue] User {user_id} not found")
            await delete_message_safe(chat_id, message_id)
            return
        
        # Отправляем запрос к GPT
        code, gpt_response = await ai_request(
            user_id=user_id,
            text=text
        )
        
        if code != 200 or not gpt_response:
            await delete_message_safe(chat_id, message_id)
            await bot.send_message(
                chat_id=chat_id,
                text="❌ Не удалось обработать запрос. Попробуйте еще раз.",
                parse_mode="HTML"
            )
            return
        
        try:
            parsed_data = await parse_gpt_response(gpt_response)
        except MealParseError as e:
            logger.error(f"[GPT Queue] Parse error for user {user_id}: {e}")
            await delete_message_safe(chat_id, message_id)
            await bot.send_message(
                chat_id=chat_id,
                text=f"❌ Ошибка обработки: {str(e)}",
                parse_mode="HTML"
            )
            return
        
        items = parsed_data.get('items', [])
        notes = parsed_data.get('notes', '')
        
        if not items:
            await delete_message_safe(chat_id, message_id)
            await bot.send_message(
                chat_id=chat_id,
                text="❌ Не удалось распознать блюда.",
                parse_mode="HTML"
            )
            return
        
        # Формируем сообщение с расчетами (БЕЗ добавления в БД)
        total_calories = sum(m['calories'] for m in items)
        total_protein = sum(m['protein'] for m in items)
        total_fat = sum(m['fat'] for m in items)
        total_carbs = sum(m['carbs'] for m in items)
        
        message_text = "🔢 <b>Расчет калорийности:</b>\n\n"
        
        for meal in items:
            message_text += f"🍽 <b>{meal['name']}</b>\n"
            message_text += f"   {meal['weight_grams']}г • "
            message_text += f"{meal['calories']} ккал • "
            message_text += f"{meal['protein']}б • {meal['fat']}ж • {meal['carbs']}у\n\n"
        
        message_text += "━━━━━━━━━━━━━━━━\n"
        message_text += "📊 <b>ИТОГО:</b>\n\n"
        message_text += f"🔥 {total_calories} ккал\n"
        message_text += f"🥩 Белки: {total_protein} г\n"
        message_text += f"🧈 Жиры: {total_fat} г\n"
        message_text += f"🍞 Углеводы: {total_carbs} г\n"
        
        if notes:
            message_text += f"\n💡 <b>{notes}</b>\n"
        
        message_text += "\n━━━━━━━━━━━━━━━━\n"
        message_text += "ℹ️ <i>Это только расчет, данные НЕ добавлены в рацион.</i>\n\n"
        message_text += "💡 Чтобы добавить, отправьте описание без команд расчета."
        
        # ✅ УДАЛЯЕМ статусное сообщение и отправляем результат
        await delete_message_safe(chat_id, message_id)
        await bot.send_message(
            chat_id=chat_id,
            text=message_text,
            parse_mode="HTML"
        )
        
        logger.info(f"[GPT Queue] Calculation completed for user {user_id} (not saved)")
        
    except Exception as e:
        logger.exception(f"[GPT Queue] Unexpected error in calculation for user {user_id}: {e}")
        await delete_message_safe(chat_id, message_id)
        await bot.send_message(
            chat_id=chat_id,
            text="❌ Произошла ошибка при расчете.",
            parse_mode="HTML"
        )


async def process_meal_delete(ctx, user_id: int, chat_id: int, message_id: int, text: str):
    """
    Обработка текстового удаления приема пищи
    
    Примеры команд:
    - "убери последнее"
    - "удали гречку"
    - "очисти рацион"
    
    ✅ Удаляет статусное сообщение после обработки
    """
    logger.info(f"[GPT Queue] Processing meal delete for user {user_id}: {text}")
    
    try:
        user = await get_user_by_id(user_id)
        if not user:
            await delete_message_safe(chat_id, message_id)
            return
        
        user_tz = user.get('timezone', 'UTC')
        text_lower = text.lower()
        
        # Проверяем что именно удалять
        if "всё" in text_lower or "все" in text_lower or "рацион" in text_lower:
            # Удалить все приемы за сегодня
            summary = await get_today_summary(user_id, user_tz)
            meals = summary.get("meals", [])
            
            if not meals:
                await delete_message_safe(chat_id, message_id)
                await bot.send_message(
                    chat_id=chat_id,
                    text="📭 Сегодня нет приемов пищи для удаления.",
                    parse_mode="HTML"
                )
                await refund_token(user_id)
                return
            
            meal_ids = [meal['id'] for meal in meals]
            deleted_count = await delete_multiple_meals(meal_ids, user_id)
            
            await delete_message_safe(chat_id, message_id)
            await bot.send_message(
                chat_id=chat_id,
                text=f"✅ Удалено приемов пищи: <b>{deleted_count}</b>\n\nРацион за сегодня очищен.",
                parse_mode="HTML"
            )
            
            logger.info(f"[GPT Queue] Deleted all meals for user {user_id}")
            return
        
        # Удалить последнее
        if "последн" in text_lower:
            last_meal = await get_last_meal(user_id, user_tz)
            
            if not last_meal:
                await delete_message_safe(chat_id, message_id)
                await bot.send_message(
                    chat_id=chat_id,
                    text="❌ Нет приемов пищи для удаления.",
                    parse_mode="HTML"
                )
                await refund_token(user_id)
                return
            
            success = await delete_meal(last_meal['id'], user_id)
            
            if success:
                summary = await get_today_summary(user_id, user_tz)
                totals = summary["totals"]
                
                message_text = f"✅ <b>Удалено:</b> {last_meal['food_name']}\n\n"
                message_text += "━━━━━━━━━━━━━━━━\n"
                message_text += "📊 <b>Обновленные итоги:</b>\n\n"
                message_text += f"🔥 {float(totals['total_calories']):.0f} ккал\n"
                message_text += f"🥩 {float(totals['total_protein']):.1f}г\n"
                message_text += f"🧈 {float(totals['total_fat']):.1f}г\n"
                message_text += f"🍞 {float(totals['total_carbs']):.1f}г\n"
                
                await delete_message_safe(chat_id, message_id)
                await bot.send_message(
                    chat_id=chat_id,
                    text=message_text,
                    parse_mode="HTML"
                )
                
                logger.info(f"[GPT Queue] Deleted last meal for user {user_id}")
            else:
                await delete_message_safe(chat_id, message_id)
                await bot.send_message(
                    chat_id=chat_id,
                    text="❌ Не удалось удалить прием пищи.",
                    parse_mode="HTML"
                )
            
            return
        
        # Удалить по названию блюда
        summary = await get_today_summary(user_id, user_tz)
        meals = summary.get("meals", [])
        
        if not meals:
            await delete_message_safe(chat_id, message_id)
            await bot.send_message(
                chat_id=chat_id,
                text="📭 Сегодня нет приемов пищи.",
                parse_mode="HTML"
            )
            await refund_token(user_id)
            return
        
        # Ищем блюдо по частичному совпадению
        meal_to_delete = None
        for meal in reversed(meals):  # Ищем с конца (последние приемы)
            meal_name_lower = meal['food_name'].lower()
            # Убираем служебные слова
            search_text = text_lower.replace('убери', '').replace('удали', '').replace('очисти', '').strip()
            
            if search_text in meal_name_lower or meal_name_lower in search_text:
                meal_to_delete = meal
                break
        
        if meal_to_delete:
            success = await delete_meal(meal_to_delete['id'], user_id)
            
            if success:
                summary = await get_today_summary(user_id, user_tz)
                totals = summary["totals"]
                
                message_text = f"✅ <b>Удалено:</b> {meal_to_delete['food_name']}\n\n"
                message_text += "━━━━━━━━━━━━━━━━\n"
                message_text += "📊 <b>Обновленные итоги:</b>\n\n"
                message_text += f"🔥 {float(totals['total_calories']):.0f} ккал\n"
                message_text += f"🥩 {float(totals['total_protein']):.1f}г\n"
                message_text += f"🧈 {float(totals['total_fat']):.1f}г\n"
                message_text += f"🍞 {float(totals['total_carbs']):.1f}г\n"
                
                await delete_message_safe(chat_id, message_id)
                await bot.send_message(
                    chat_id=chat_id,
                    text=message_text,
                    parse_mode="HTML"
                )
                
                logger.info(f"[GPT Queue] Deleted meal by name for user {user_id}")
            else:
                await delete_message_safe(chat_id, message_id)
                await bot.send_message(
                    chat_id=chat_id,
                    text="❌ Не удалось удалить прием пищи.",
                    parse_mode="HTML"
                )
        else:
            # Не нашли блюдо - показываем список
            text = "❓ <b>Блюдо не найдено</b>\n\n"
            text += "Сегодня у вас:\n\n"
            
            for idx, meal in enumerate(meals[-5:], 1):  # Последние 5
                time = meal["meal_datetime"].strftime("%H:%M")
                text += f"{idx}. {time} — {meal['food_name']}\n"
            
            text += "\n💡 Попробуйте указать название точнее"
            
            await delete_message_safe(chat_id, message_id)
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="HTML"
            )
            
            await refund_token(user_id)
        
    except Exception as e:
        logger.exception(f"[GPT Queue] Error deleting meal for user {user_id}: {e}")
        await delete_message_safe(chat_id, message_id)
        await bot.send_message(
            chat_id=chat_id,
            text="❌ Ошибка при удалении.",
            parse_mode="HTML"
        )
        await refund_token(user_id)