# import logging
# from datetime import datetime
# from aiogram import Router, F
# from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
# from aiogram.filters import Command
# from aiogram.exceptions import TelegramBadRequest
# from app.services.meals import (
#     get_food_history,
#     get_day_meals,
#     get_today_summary,
#     delete_meal,
#     delete_multiple_meals,
#     get_week_stats
# )
# from app.db.redis_client import get_arq_redis
# from app.services.user import get_user_by_id
# import pytz

# logger = logging.getLogger(__name__)
# router = Router()


# async def safe_callback_answer(callback: CallbackQuery, text: str = None, show_alert: bool = False):
#     """
#     Безопасный ответ на callback query с обработкой устаревших запросов
#     """
#     try:
#         await callback.answer(text, show_alert=show_alert)
#     except TelegramBadRequest as e:
#         if "query is too old" in str(e) or "query ID is invalid" in str(e):
#             logger.warning(f"[Food] Callback query too old: {e}")
#         else:
#             raise


# @router.message(Command("food"))
# async def cmd_food(message: Message):
#     """Команда /food - показывает историю питания за 7 дней"""
#     user_id = message.from_user.id
#     logger.info(f"[Food Handler] /food command from user {user_id}")
    
#     try:
#         user = await get_user_by_id(user_id)
#         if not user:
#             await message.answer("❌ Пользователь не найден")
#             return
        
#         user_tz = user.get('timezone', 'Europe/Moscow')
#         history = await get_food_history(user_id, user_tz, days=7)
        
#         if not history or len(history) == 0:
#             await message.answer(
#                 "📭 <b>У вас пока нет записей о еде</b>\n\n"
#                 "Отправьте фото блюда или опишите что съели!",
#                 parse_mode="HTML"
#             )
#             return
        
#         today = history[0]
        
#         text = "📊 <b>Моя еда</b>\n\n"
#         text += "━━━━━━━━━━━━━━━━\n"
#         text += f"📅 <b>{today['date_formatted']}</b>\n"
#         text += f"🔥 {float(today['total_calories']):.0f} ккал | "
#         text += f"🥩 {float(today['total_protein']):.1f}г | "
#         text += f"🧈 {float(today['total_fat']):.1f}г | "
#         text += f"🍞 {float(today['total_carbs']):.1f}г\n\n"
        
#         if today['meals']:
#             for idx, meal in enumerate(today['meals'], 1):
#                 time = meal["meal_datetime"].strftime("%H:%M")
#                 text += (
#                     f"{idx}. ⏰ <b>{time}</b> — {meal['food_name']}\n"
#                     f"   {float(meal['calories']):.0f} ккал • "
#                     f"{float(meal['protein']):.1f}б • "
#                     f"{float(meal['fat']):.1f}ж • "
#                     f"{float(meal['carbs']):.1f}у\n\n"
#                 )
#         else:
#             text += "<i>Пока нет приемов пищи</i>\n\n"
        
#         if len(history) > 1:
#             text += "━━━━━━━━━━━━━━━━\n"
#             text += "📅 <b>Предыдущие дни:</b>\n\n"
            
#             for day in history[1:]:
#                 text += f"<b>{day['date_formatted']}</b>\n"
#                 text += f"🔥 {float(day['total_calories']):.0f} ккал | "
#                 text += f"🍽 {day['meals_count']} приемов\n\n"
            
#             text += "👇 <i>Нажмите на день чтобы увидеть приемы пищи</i>"
        
#         buttons = []
        
#         if today['meals']:
#             for meal in today['meals'][-10:]:
#                 meal_time = meal["meal_datetime"].strftime("%H:%M")
#                 buttons.append([
#                     InlineKeyboardButton(
#                         text=f"🗑 {meal_time} - {meal['food_name'][:25]}",
#                         callback_data=f"del_meal:{meal['id']}"
#                     )
#                 ])
        
#         if len(history) > 1:
#             for day in history[1:]:
#                 date_str = day["date"].isoformat()
#                 buttons.append([
#                     InlineKeyboardButton(
#                         text=f"📋 {day['date_formatted']}: {float(day['total_calories']):.0f} ккал",
#                         callback_data=f"show_day:{date_str}"
#                     )
#                 ])
        
#         keyboard = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
#         await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        
#     except Exception as e:
#         logger.exception(f"[Food Handler] Error in /food for user {user_id}: {e}")
#         await message.answer("❌ Произошла ошибка. Попробуйте позже.")


# @router.callback_query(F.data == "show_today")
# async def callback_show_today(callback: CallbackQuery):
#     """Callback для показа приемов пищи за сегодня"""
#     await safe_callback_answer(callback)
    
#     user_id = callback.from_user.id
#     logger.info(f"[Food Handler] show_today callback from user {user_id}")
    
#     try:
#         user = await get_user_by_id(user_id)
#         if not user:
#             await callback.message.edit_text("❌ Пользователь не найден")
#             return
        
#         user_tz = user.get('timezone', 'Europe/Moscow')
#         history = await get_food_history(user_id, user_tz, days=7)
        
#         if not history or len(history) == 0:
#             await callback.message.answer(
#                 "📭 Сегодня вы ещё ничего не добавили.\n\n"
#                 "Отправьте фото еды или опишите блюдо текстом!"
#             )
#             return
        
#         today = history[0]
        
#         text = "📊 <b>Моя еда</b>\n\n"
#         text += "━━━━━━━━━━━━━━━━\n"
#         text += f"📅 <b>{today['date_formatted']}</b>\n"
#         text += f"🔥 {float(today['total_calories']):.0f} ккал | "
#         text += f"🥩 {float(today['total_protein']):.1f}г | "
#         text += f"🧈 {float(today['total_fat']):.1f}г | "
#         text += f"🍞 {float(today['total_carbs']):.1f}г\n\n"
        
#         if today['meals']:
#             for idx, meal in enumerate(today['meals'], 1):
#                 time = meal["meal_datetime"].strftime("%H:%M")
#                 text += (
#                     f"{idx}. ⏰ <b>{time}</b> — {meal['food_name']}\n"
#                     f"   {float(meal['calories']):.0f} ккал • "
#                     f"{float(meal['protein']):.1f}б • "
#                     f"{float(meal['fat']):.1f}ж • "
#                     f"{float(meal['carbs']):.1f}у\n\n"
#                 )
#         else:
#             text += "<i>Пока нет приемов пищи</i>\n\n"
        
#         buttons = []
#         if today['meals']:
#             for meal in today['meals'][-10:]:
#                 meal_time = meal["meal_datetime"].strftime("%H:%M")
#                 buttons.append([
#                     InlineKeyboardButton(
#                         text=f"🗑 {meal_time} - {meal['food_name'][:25]}",
#                         callback_data=f"del_meal:{meal['id']}"
#                     )
#                 ])
        
#         keyboard = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
#         await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        
#     except Exception as e:
#         logger.exception(f"[Food Handler] Error in show_today for user {user_id}: {e}")
#         await callback.message.answer("❌ Произошла ошибка. Попробуйте позже.")


# @router.callback_query(F.data.startswith("show_day:"))
# async def handle_show_day(callback: CallbackQuery):
#     """Показывает приемы пищи для конкретного дня"""
#     try:
#         await safe_callback_answer(callback)
        
#         user_id = callback.from_user.id
#         date_str = callback.data.split(":", 1)[1]
        
#         user = await get_user_by_id(user_id)
#         if not user:
#             await callback.message.edit_text("⚠️ Пользователь не найден")
#             return
        
#         user_tz = user.get("timezone", "Europe/Moscow")
#         day_data = await get_day_meals(user_id, date_str, user_tz)
        
#         if not day_data:
#             await callback.message.edit_text("⚠️ Данные не найдены")
#             return
        
#         text = f"📅 <b>{day_data['date_formatted']}</b>\n"
#         text += "━━━━━━━━━━━━━━━━\n"
#         text += f"🔥 {float(day_data['total_calories']):.0f} ккал | "
#         text += f"🥩 {float(day_data['total_protein']):.1f}г | "
#         text += f"🧈 {float(day_data['total_fat']):.1f}г | "
#         text += f"🍞 {float(day_data['total_carbs']):.1f}г\n\n"
        
#         if day_data['meals']:
#             for idx, meal in enumerate(day_data['meals'], 1):
#                 time = meal["meal_datetime"].strftime("%H:%M")
#                 text += (
#                     f"{idx}. ⏰ <b>{time}</b> — {meal['food_name']}\n"
#                     f"   {float(meal['calories']):.0f} ккал • "
#                     f"{float(meal['protein']):.1f}б • "
#                     f"{float(meal['fat']):.1f}ж • "
#                     f"{float(meal['carbs']):.1f}у\n\n"
#                 )
#         else:
#             text += "<i>Нет приемов пищи</i>"
        
#         await callback.message.answer(text, parse_mode="HTML")
        
#     except TelegramBadRequest as e:
#         if "query is too old" not in str(e):
#             raise
#         logger.warning(f"[Food] Callback too old in show_day")
#     except Exception as e:
#         logger.exception(f"[Food] Error showing day: {e}")


# @router.callback_query(F.data.startswith("del_meal:"))
# async def handle_delete_meal(callback: CallbackQuery):
#     """Удаляет прием пищи"""
#     try:
#         user_id = callback.from_user.id
#         meal_id = int(callback.data.split(":", 1)[1])
        
#         success = await delete_meal(meal_id, user_id)
        
#         if not success:
#             await safe_callback_answer(callback, "⚠️ Не удалось удалить", show_alert=True)
#             return
        
#         user = await get_user_by_id(user_id)
#         user_tz = user.get("timezone", "Europe/Moscow")
#         history = await get_food_history(user_id, user_tz, days=7)
        
#         if not history or len(history) == 0:
#             await callback.message.edit_text(
#                 "📭 <b>Все приемы пищи удалены</b>\n\n"
#                 "Отправьте фото блюда или опишите что съели!",
#                 parse_mode="HTML"
#             )
#             await safe_callback_answer(callback, "✅ Прием пищи удален")
#             return
        
#         today = history[0]
        
#         text = "📊 <b>Моя еда</b>\n\n"
#         text += "━━━━━━━━━━━━━━━━\n"
#         text += f"📅 <b>{today['date_formatted']}</b>\n"
#         text += f"🔥 {float(today['total_calories']):.0f} ккал | "
#         text += f"🥩 {float(today['total_protein']):.1f}г | "
#         text += f"🧈 {float(today['total_fat']):.1f}г | "
#         text += f"🍞 {float(today['total_carbs']):.1f}г\n\n"
        
#         if today['meals']:
#             for idx, meal in enumerate(today['meals'], 1):
#                 time = meal["meal_datetime"].strftime("%H:%M")
#                 text += (
#                     f"{idx}. ⏰ <b>{time}</b> — {meal['food_name']}\n"
#                     f"   {float(meal['calories']):.0f} ккал • "
#                     f"{float(meal['protein']):.1f}б • "
#                     f"{float(meal['fat']):.1f}ж • "
#                     f"{float(meal['carbs']):.1f}у\n\n"
#                 )
#         else:
#             text += "<i>Пока нет приемов пищи</i>\n\n"
        
#         buttons = []
#         if today['meals']:
#             for meal in today['meals'][-10:]:
#                 meal_time = meal["meal_datetime"].strftime("%H:%M")
#                 buttons.append([
#                     InlineKeyboardButton(
#                         text=f"🗑 {meal_time} - {meal['food_name'][:25]}",
#                         callback_data=f"del_meal:{meal['id']}"
#                     )
#                 ])
        
#         if len(history) > 1:
#             for day in history[1:]:
#                 date_str = day["date"].isoformat()
#                 buttons.append([
#                     InlineKeyboardButton(
#                         text=f"📋 {day['date_formatted']}: {float(day['total_calories']):.0f} ккал",
#                         callback_data=f"show_day:{date_str}"
#                     )
#                 ])
        
#         keyboard = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
        
#         await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
#         await safe_callback_answer(callback, "✅ Прием пищи удален")
        
#     except TelegramBadRequest as e:
#         if "query is too old" not in str(e):
#             raise
#         logger.warning(f"[Food] Callback too old in delete_meal")
#     except Exception as e:
#         logger.exception(f"[Food] Error deleting meal: {e}")


# @router.callback_query(F.data.startswith("undo_last:"))
# async def handle_undo_last(callback: CallbackQuery):
#     """Отменяет последнее добавление (удаляет приемы пищи)"""
#     try:
#         user_id = callback.from_user.id
#         meal_ids_str = callback.data.split(":", 1)[1]
#         meal_ids = [int(x) for x in meal_ids_str.split(",") if x]
        
#         if not meal_ids:
#             await safe_callback_answer(callback, "⚠️ Ошибка: нет данных", show_alert=True)
#             return
        
#         deleted_count = await delete_multiple_meals(meal_ids, user_id)
        
#         if deleted_count == 0:
#             await safe_callback_answer(callback, "⚠️ Не удалось удалить", show_alert=True)
#             return
        
#         user = await get_user_by_id(user_id)
#         user_tz = user.get("timezone", "Europe/Moscow")
#         summary = await get_today_summary(user_id, user_tz)
        
#         totals = summary["totals"]
#         meals = summary["meals"]
        
#         if not meals:
#             await callback.message.edit_text(
#                 "✅ <b>Добавление отменено</b>\n\n"
#                 "📭 Сегодня пока нет приемов пищи.\n\n"
#                 "Отправьте фото блюда или опишите что съели!",
#                 parse_mode="HTML"
#             )
#             await safe_callback_answer(callback, f"✅ Удалено: {deleted_count}")
#             return
        
#         tz = pytz.timezone(user_tz)
#         today = datetime.now(tz).strftime("%d.%m.%Y")
        
#         text = f"✅ <b>Добавление отменено</b>\n\n"
#         text += f"📊 <b>Актуальные итоги за {today}:</b>\n\n"
#         text += "━━━━━━━━━━━━━━━━\n"
#         text += f"🔥 Калории: <b>{float(totals['total_calories']):.0f}</b> ккал\n"
#         text += f"🥩 Белки: <b>{float(totals['total_protein']):.1f}</b> г\n"
#         text += f"🧈 Жиры: <b>{float(totals['total_fat']):.1f}</b> г\n"
#         text += f"🍞 Углеводы: <b>{float(totals['total_carbs']):.1f}</b> г\n"
#         text += f"🍽 Приемов пищи: {totals['meals_count']}\n"
#         text += "━━━━━━━━━━━━━━━━\n\n"
#         text += "💡 Команда /food для просмотра истории"
        
#         await callback.message.edit_text(text, parse_mode="HTML")
#         await safe_callback_answer(callback, f"✅ Удалено: {deleted_count}")
        
#     except TelegramBadRequest as e:
#         if "query is too old" not in str(e):
#             raise
#         logger.warning(f"[Food] Callback too old in undo_last")
#     except Exception as e:
#         logger.exception(f"[Food] Error undoing: {e}")


# @router.callback_query(F.data.startswith("confirm_meal:"))
# async def callback_confirm_meal(callback: CallbackQuery):
#     """Подтверждение добавления блюда в рацион"""
#     user_id = callback.from_user.id
#     meal_key = callback.data.split(":")[1]
#     message_id = callback.message.message_id
    
#     logger.info(f"[Food Handler] Confirming meal for user {user_id}, key={meal_key}")
    
#     try:
#         # ✅ ЗАЩИТА 1: Убираем кнопки сразу
#         await callback.message.edit_reply_markup(reply_markup=None)
#         await safe_callback_answer(callback, "⏳ Обрабатываем...")
        
#         # Ставим задачу в очередь
#         arq = await get_arq_redis()
#         await arq.enqueue_job(
#             'confirm_meal_addition',
#             user_id,
#             meal_key,
#             message_id
#         )
        
#         await callback.message.edit_text("⏳ Добавляю в рацион...")
        
#     except TelegramBadRequest as e:
#         if "query is too old" not in str(e):
#             raise
#         logger.warning(f"[Food] Callback too old in confirm_meal")
#     except Exception as e:
#         logger.exception(f"[Food Handler] Error confirming meal: {e}")
#         try:
#             await callback.message.edit_text("❌ Ошибка. Попробуйте еще раз.")
#         except:
#             pass


# @router.callback_query(F.data.startswith("cancel_meal:"))
# async def callback_cancel_meal(callback: CallbackQuery):
#     """Отмена добавления блюда"""
#     user_id = callback.from_user.id
#     meal_key = callback.data.split(":")[1]
#     message_id = callback.message.message_id
    
#     logger.info(f"[Food Handler] Canceling meal for user {user_id}, key={meal_key}")
    
#     try:
#         # ✅ ЗАЩИТА 1: Убираем кнопки сразу
#         await callback.message.edit_reply_markup(reply_markup=None)
#         await safe_callback_answer(callback, "⏳ Обрабатываем...")
        
#         # Ставим задачу в очередь
#         arq = await get_arq_redis()
#         await arq.enqueue_job(
#             'cancel_meal_addition',
#             user_id,
#             meal_key,
#             message_id
#         )
        
#         await callback.message.edit_text("⏳ Отменяю...")
        
#     except TelegramBadRequest as e:
#         if "query is too old" not in str(e):
#             raise
#         logger.warning(f"[Food] Callback too old in cancel_meal")
#     except Exception as e:
#         logger.exception(f"[Food Handler] Error canceling meal: {e}")
#         try:
#             await callback.message.edit_text("❌ Ошибка. Попробуйте еще раз.")
#         except:
#             pass

import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest
from app.services.meals import (
    get_food_history,
    get_day_meals,
    get_today_summary,
    delete_meal,
    delete_multiple_meals,
    get_week_stats
)
from app.db.redis_client import get_arq_redis
from app.services.user import get_user_by_id
import pytz

logger = logging.getLogger(__name__)
router = Router()


async def safe_edit_message(callback: CallbackQuery, text: str, reply_markup=None):
    """
    Безопасное редактирование сообщения с обработкой ошибок
    """
    try:
        await callback.message.edit_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            logger.debug(f"[Food] Message not modified, skipping edit")
        elif "message to edit not found" in str(e).lower():
            logger.warning(f"[Food] Message not found, sending new")
            await callback.message.answer(text, reply_markup=reply_markup, parse_mode="HTML")
        else:
            raise


async def safe_edit_reply_markup(message, reply_markup):
    """
    Безопасное удаление кнопок с обработкой ошибок
    """
    try:
        await message.edit_reply_markup(reply_markup=reply_markup)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            logger.debug(f"[Food] Markup not modified, skipping")
        elif "message to edit not found" in str(e).lower():
            logger.warning(f"[Food] Message not found for markup edit")
        else:
            logger.error(f"[Food] Error editing markup: {e}")


async def safe_callback_answer(callback: CallbackQuery, text: str = None, show_alert: bool = False):
    """
    Безопасный ответ на callback query
    """
    try:
        await callback.answer(text, show_alert=show_alert)
    except TelegramBadRequest as e:
        if "query is too old" in str(e) or "query ID is invalid" in str(e):
            logger.debug(f"[Food] Callback query too old, skipping answer")
        else:
            logger.error(f"[Food] Error answering callback: {e}")


@router.message(Command("food"))
async def cmd_food(message: Message):
    """Команда /food - показывает историю питания за 7 дней"""
    user_id = message.from_user.id
    logger.info(f"[Food Handler] /food command from user {user_id}")
    
    try:
        user = await get_user_by_id(user_id)
        if not user:
            await message.answer("❌ Пользователь не найден")
            return
        
        user_tz = user.get('timezone', 'Europe/Moscow')
        history = await get_food_history(user_id, user_tz, days=7)
        
        if not history or len(history) == 0:
            await message.answer(
                "📭 <b>У вас пока нет записей о еде</b>\n\n"
                "Отправьте фото блюда или опишите что съели!",
                parse_mode="HTML"
            )
            return
        
        today = history[0]
        
        text = "📊 <b>Моя еда</b>\n\n"
        text += "━━━━━━━━━━━━━━━━\n"
        text += f"📅 <b>{today['date_formatted']}</b>\n"
        text += f"🔥 {float(today['total_calories']):.0f} ккал | "
        text += f"🥩 {float(today['total_protein']):.1f}г | "
        text += f"🧈 {float(today['total_fat']):.1f}г | "
        text += f"🍞 {float(today['total_carbs']):.1f}г\n\n"
        
        if today['meals']:
            # ✅ ПОКАЗЫВАЕМ ВСЕ ПРИЕМЫ (убрали лимит)
            for idx, meal in enumerate(today['meals'], 1):
                time = meal["meal_datetime"].strftime("%H:%M")
                text += (
                    f"{idx}. ⏰ <b>{time}</b> — {meal['food_name']}\n"
                    f"   {float(meal['calories']):.0f} ккал • "
                    f"{float(meal['protein']):.1f}б • "
                    f"{float(meal['fat']):.1f}ж • "
                    f"{float(meal['carbs']):.1f}у\n\n"
                )
        else:
            text += "<i>Пока нет приемов пищи</i>\n\n"
        
        if len(history) > 1:
            text += "━━━━━━━━━━━━━━━━\n"
            text += "📅 <b>Предыдущие дни:</b>\n\n"
            
            for day in history[1:]:
                text += f"<b>{day['date_formatted']}</b>\n"
                text += f"🔥 {float(day['total_calories']):.0f} ккал | "
                text += f"🍽 {day['meals_count']} приемов\n\n"
            
            text += "👇 <i>Нажмите на день чтобы увидеть приемы пищи</i>"
        
        buttons = []
        
        # Кнопки удаления/редактирования для каждого приема
        if today['meals']:
            for meal in today['meals']:
                meal_time = meal["meal_datetime"].strftime("%H:%M")
                meal_name = meal['food_name'][:20]
                buttons.append([
                    InlineKeyboardButton(
                        text=f"✏️ {meal_time} - {meal_name}",
                        callback_data=f"edit_meal:{meal['id']}"
                    ),
                    InlineKeyboardButton(
                        text="🗑",
                        callback_data=f"del_meal:{meal['id']}"
                    )
                ])
        
        # Кнопки для предыдущих дней
        if len(history) > 1:
            for day in history[1:]:
                date_str = day["date"].isoformat()
                buttons.append([
                    InlineKeyboardButton(
                        text=f"📋 {day['date_formatted']}: {float(day['total_calories']):.0f} ккал",
                        callback_data=f"show_day:{date_str}"
                    )
                ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        
    except Exception as e:
        logger.exception(f"[Food Handler] Error in /food for user {user_id}: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте позже.")


@router.callback_query(F.data == "show_today")
async def callback_show_today(callback: CallbackQuery):
    """Callback для показа приемов пищи за сегодня"""
    await safe_callback_answer(callback)
    
    user_id = callback.from_user.id
    logger.info(f"[Food Handler] show_today callback from user {user_id}")
    
    try:
        user = await get_user_by_id(user_id)
        if not user:
            await safe_edit_message(callback, "❌ Пользователь не найден")
            return
        
        user_tz = user.get('timezone', 'Europe/Moscow')
        history = await get_food_history(user_id, user_tz, days=7)
        
        if not history or len(history) == 0:
            await callback.message.answer(
                "📭 Сегодня вы ещё ничего не добавили.\n\n"
                "Отправьте фото еды или опишите блюдо текстом!"
            )
            return
        
        today = history[0]
        
        text = "📊 <b>Моя еда</b>\n\n"
        text += "━━━━━━━━━━━━━━━━\n"
        text += f"📅 <b>{today['date_formatted']}</b>\n"
        text += f"🔥 {float(today['total_calories']):.0f} ккал | "
        text += f"🥩 {float(today['total_protein']):.1f}г | "
        text += f"🧈 {float(today['total_fat']):.1f}г | "
        text += f"🍞 {float(today['total_carbs']):.1f}г\n\n"
        
        if today['meals']:
            for idx, meal in enumerate(today['meals'], 1):
                time = meal["meal_datetime"].strftime("%H:%M")
                text += (
                    f"{idx}. ⏰ <b>{time}</b> — {meal['food_name']}\n"
                    f"   {float(meal['calories']):.0f} ккал • "
                    f"{float(meal['protein']):.1f}б • "
                    f"{float(meal['fat']):.1f}ж • "
                    f"{float(meal['carbs']):.1f}у\n\n"
                )
        else:
            text += "<i>Пока нет приемов пищи</i>\n\n"
        
        buttons = []
        if today['meals']:
            for meal in today['meals']:
                meal_time = meal["meal_datetime"].strftime("%H:%M")
                meal_name = meal['food_name'][:20]
                buttons.append([
                    InlineKeyboardButton(
                        text=f"✏️ {meal_time} - {meal_name}",
                        callback_data=f"edit_meal:{meal['id']}"
                    ),
                    InlineKeyboardButton(
                        text="🗑",
                        callback_data=f"del_meal:{meal['id']}"
                    )
                ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
        await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        
    except Exception as e:
        logger.exception(f"[Food Handler] Error in show_today for user {user_id}: {e}")
        await callback.message.answer("❌ Произошла ошибка. Попробуйте позже.")


@router.callback_query(F.data.startswith("show_day:"))
async def handle_show_day(callback: CallbackQuery):
    """Показывает приемы пищи для конкретного дня"""
    try:
        await safe_callback_answer(callback)
        
        user_id = callback.from_user.id
        date_str = callback.data.split(":", 1)[1]
        
        user = await get_user_by_id(user_id)
        if not user:
            await safe_edit_message(callback, "⚠️ Пользователь не найден")
            return
        
        user_tz = user.get("timezone", "Europe/Moscow")
        day_data = await get_day_meals(user_id, date_str, user_tz)
        
        if not day_data:
            await safe_edit_message(callback, "⚠️ Данные не найдены")
            return
        
        text = f"📅 <b>{day_data['date_formatted']}</b>\n"
        text += "━━━━━━━━━━━━━━━━\n"
        text += f"🔥 {float(day_data['total_calories']):.0f} ккал | "
        text += f"🥩 {float(day_data['total_protein']):.1f}г | "
        text += f"🧈 {float(day_data['total_fat']):.1f}г | "
        text += f"🍞 {float(day_data['total_carbs']):.1f}г\n\n"
        
        if day_data['meals']:
            for idx, meal in enumerate(day_data['meals'], 1):
                time = meal["meal_datetime"].strftime("%H:%M")
                text += (
                    f"{idx}. ⏰ <b>{time}</b> — {meal['food_name']}\n"
                    f"   {float(meal['calories']):.0f} ккал • "
                    f"{float(meal['protein']):.1f}б • "
                    f"{float(meal['fat']):.1f}ж • "
                    f"{float(meal['carbs']):.1f}у\n\n"
                )
        else:
            text += "<i>Нет приемов пищи</i>"
        
        await callback.message.answer(text, parse_mode="HTML")
        
    except Exception as e:
        logger.exception(f"[Food] Error showing day: {e}")


@router.callback_query(F.data.startswith("edit_meal:"))
async def handle_edit_meal(callback: CallbackQuery):
    """
    ✏️ НОВОЕ: Редактирование приема пищи
    """
    try:
        await safe_callback_answer(callback)
        
        user_id = callback.from_user.id
        meal_id = int(callback.data.split(":", 1)[1])
        
        await callback.message.answer(
            "✏️ <b>Редактирование приема пищи</b>\n\n"
            "Напишите как изменить блюдо:\n\n"
            "Примеры:\n"
            "• \"сделай менее жирным\"\n"
            "• \"уменьши порцию вдвое\"\n"
            "• \"измени вес на 200г\"\n\n"
            "💡 Или просто опишите блюдо заново",
            parse_mode="HTML"
        )
        
    except Exception as e:
        logger.exception(f"[Food] Error in edit_meal: {e}")


@router.callback_query(F.data.startswith("del_meal:"))
async def handle_delete_meal(callback: CallbackQuery):
    """Удаляет прием пищи"""
    try:
        user_id = callback.from_user.id
        meal_id = int(callback.data.split(":", 1)[1])
        
        success = await delete_meal(meal_id, user_id)
        
        if not success:
            await safe_callback_answer(callback, "⚠️ Не удалось удалить", show_alert=True)
            return
        
        user = await get_user_by_id(user_id)
        user_tz = user.get("timezone", "Europe/Moscow")
        history = await get_food_history(user_id, user_tz, days=7)
        
        if not history or len(history) == 0:
            await safe_edit_message(
                callback,
                "📭 <b>Все приемы пищи удалены</b>\n\n"
                "Отправьте фото блюда или опишите что съели!"
            )
            await safe_callback_answer(callback, "✅ Прием пищи удален")
            return
        
        today = history[0]
        
        text = "📊 <b>Моя еда</b>\n\n"
        text += "━━━━━━━━━━━━━━━━\n"
        text += f"📅 <b>{today['date_formatted']}</b>\n"
        text += f"🔥 {float(today['total_calories']):.0f} ккал | "
        text += f"🥩 {float(today['total_protein']):.1f}г | "
        text += f"🧈 {float(today['total_fat']):.1f}г | "
        text += f"🍞 {float(today['total_carbs']):.1f}г\n\n"
        
        if today['meals']:
            for idx, meal in enumerate(today['meals'], 1):
                time = meal["meal_datetime"].strftime("%H:%M")
                text += (
                    f"{idx}. ⏰ <b>{time}</b> — {meal['food_name']}\n"
                    f"   {float(meal['calories']):.0f} ккал • "
                    f"{float(meal['protein']):.1f}б • "
                    f"{float(meal['fat']):.1f}ж • "
                    f"{float(meal['carbs']):.1f}у\n\n"
                )
        else:
            text += "<i>Пока нет приемов пищи</i>\n\n"
        
        buttons = []
        if today['meals']:
            for meal in today['meals']:
                meal_time = meal["meal_datetime"].strftime("%H:%M")
                meal_name = meal['food_name'][:20]
                buttons.append([
                    InlineKeyboardButton(
                        text=f"✏️ {meal_time} - {meal_name}",
                        callback_data=f"edit_meal:{meal['id']}"
                    ),
                    InlineKeyboardButton(
                        text="🗑",
                        callback_data=f"del_meal:{meal['id']}"
                    )
                ])
        
        if len(history) > 1:
            for day in history[1:]:
                date_str = day["date"].isoformat()
                buttons.append([
                    InlineKeyboardButton(
                        text=f"📋 {day['date_formatted']}: {float(day['total_calories']):.0f} ккал",
                        callback_data=f"show_day:{date_str}"
                    )
                ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
        
        await safe_edit_message(callback, text, keyboard)
        await safe_callback_answer(callback, "✅ Прием пищи удален")
        
    except Exception as e:
        logger.exception(f"[Food] Error deleting meal: {e}")


@router.callback_query(F.data.startswith("undo_last:"))
async def handle_undo_last(callback: CallbackQuery):
    """Отменяет последнее добавление (удаляет приемы пищи)"""
    try:
        user_id = callback.from_user.id
        meal_ids_str = callback.data.split(":", 1)[1]
        meal_ids = [int(x) for x in meal_ids_str.split(",") if x]
        
        if not meal_ids:
            await safe_callback_answer(callback, "⚠️ Ошибка: нет данных", show_alert=True)
            return
        
        # ✅ Убираем кнопки сразу
        await safe_edit_reply_markup(callback.message, None)
        
        deleted_count = await delete_multiple_meals(meal_ids, user_id)
        
        if deleted_count == 0:
            await safe_callback_answer(callback, "⚠️ Не удалось удалить", show_alert=True)
            return
        
        user = await get_user_by_id(user_id)
        user_tz = user.get("timezone", "Europe/Moscow")
        summary = await get_today_summary(user_id, user_tz)
        
        totals = summary["totals"]
        meals = summary["meals"]
        
        if not meals:
            await safe_edit_message(
                callback,
                "✅ <b>Добавление отменено</b>\n\n"
                "📭 Сегодня пока нет приемов пищи.\n\n"
                "Отправьте фото блюда или опишите что съели!"
            )
            await safe_callback_answer(callback, f"✅ Удалено: {deleted_count}")
            return
        
        tz = pytz.timezone(user_tz)
        today = datetime.now(tz).strftime("%d.%m.%Y")
        
        text = f"✅ <b>Добавление отменено</b>\n\n"
        text += f"📊 <b>Актуальные итоги за {today}:</b>\n\n"
        text += "━━━━━━━━━━━━━━━━\n"
        text += f"🔥 Калории: <b>{float(totals['total_calories']):.0f}</b> ккал\n"
        text += f"🥩 Белки: <b>{float(totals['total_protein']):.1f}</b> г\n"
        text += f"🧈 Жиры: <b>{float(totals['total_fat']):.1f}</b> г\n"
        text += f"🍞 Углеводы: <b>{float(totals['total_carbs']):.1f}</b> г\n"
        text += f"🍽 Приемов пищи: {totals['meals_count']}\n"
        text += "━━━━━━━━━━━━━━━━\n\n"
        text += "💡 Команда /food для просмотра истории"
        
        await safe_edit_message(callback, text)
        await safe_callback_answer(callback, f"✅ Удалено: {deleted_count}")
        
    except Exception as e:
        logger.exception(f"[Food] Error undoing: {e}")