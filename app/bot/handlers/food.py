# from aiogram import Router
# from aiogram.filters import Command
# from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
# from app.services.user import get_user_by_id
# from app.services.meals import get_food_history, delete_meal, get_today_summary, get_day_meals
# from datetime import datetime
# import pytz
# import logging

# router = Router()
# logger = logging.getLogger(__name__)


# def get_meal_delete_keyboard(meals: list) -> InlineKeyboardMarkup:
#     """Создает кнопки удаления ТОЛЬКО для сегодняшних приемов"""
#     if not meals:
#         return None
    
#     buttons = []
    
#     # Показываем последние 10 приемов
#     for meal in meals[-10:]:
#         meal_id = meal["id"]
#         meal_name = meal["food_name"][:25]
#         meal_time = meal["meal_datetime"].strftime("%H:%M")
        
#         buttons.append([
#             InlineKeyboardButton(
#                 text=f"🗑 {meal_time} - {meal_name}",
#                 callback_data=f"del_meal:{meal_id}"
#             )
#         ])
    
#     return InlineKeyboardMarkup(inline_keyboard=buttons)


# def get_history_keyboard(days_data: list) -> InlineKeyboardMarkup:
#     """Создает кнопки 'Показать приемы' для предыдущих дней"""
#     if len(days_data) <= 1:  # Если только сегодня
#         return None
    
#     buttons = []
    
#     # Пропускаем сегодня (индекс 0), для остальных создаем кнопки
#     for day in days_data[1:]:
#         date_str = day["date"].isoformat()  # Передаем дату в формате YYYY-MM-DD
#         label = day["date_formatted"]
#         calories = float(day["total_calories"])
#         meals_count = day["meals_count"]
        
#         buttons.append([
#             InlineKeyboardButton(
#                 text=f"📋 {label}: {calories:.0f} ккал • {meals_count} приемов",
#                 callback_data=f"show_day:{date_str}"
#             )
#         ])
    
#     return InlineKeyboardMarkup(inline_keyboard=buttons)


# @router.message(Command("food"))
# async def show_food_history(message: Message):
#     """
#     Показывает историю питания
    
#     - Сегодня: детально с кнопками удаления
#     - Предыдущие дни: краткая сводка + кнопки "Показать приемы"
#     """
#     try:
#         user_id = message.from_user.id
#         user = await get_user_by_id(user_id)
        
#         if not user:
#             await message.answer("⚠️ Пользователь не найден. Используйте /start")
#             return
        
#         user_tz = user.get("timezone", "Europe/Moscow")
        
#         # Получаем историю за 7 дней
#         history = await get_food_history(user_id, user_tz, days=7)
        
#         if not history or len(history) == 0:
#             await message.answer(
#                 "📭 <b>У вас пока нет записей о еде</b>\n\n"
#                 "Отправьте фото блюда или опишите что съели!",
#                 parse_mode="HTML"
#             )
#             return
        
#         # ========== СЕГОДНЯ (детально) ==========
#         today = history[0]
        
#         text = "📊 <b>Моя еда</b>\n\n"
#         text += "━━━━━━━━━━━━━━━━\n"
#         text += f"📅 <b>{today['date_formatted']}</b>\n"
#         text += f"🔥 {float(today['total_calories']):.0f} ккал | "
#         text += f"🥩 {float(today['total_protein']):.1f}г | "
#         text += f"🧈 {float(today['total_fat']):.1f}г | "
#         text += f"🍞 {float(today['total_carbs']):.1f}г\n\n"
        
#         # Приемы пищи сегодня
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
        
#         # ========== ПРЕДЫДУЩИЕ ДНИ (кратко) ==========
#         if len(history) > 1:
#             text += "━━━━━━━━━━━━━━━━\n"
#             text += "📅 <b>Предыдущие дни:</b>\n\n"
            
#             for day in history[1:]:
#                 text += f"<b>{day['date_formatted']}</b>\n"
#                 text += f"🔥 {float(day['total_calories']):.0f} ккал | "
#                 text += f"🍽 {day['meals_count']} приемов\n\n"
            
#             text += "👇 <i>Нажмите на день чтобы увидеть приемы пищи</i>"
        
#         # Создаем клавиатуры
#         today_keyboard = get_meal_delete_keyboard(today['meals'])
#         history_keyboard = get_history_keyboard(history)
        
#         # Объединяем клавиатуры
#         if today_keyboard and history_keyboard:
#             combined_buttons = today_keyboard.inline_keyboard + history_keyboard.inline_keyboard
#             keyboard = InlineKeyboardMarkup(inline_keyboard=combined_buttons)
#         elif today_keyboard:
#             keyboard = today_keyboard
#         elif history_keyboard:
#             keyboard = history_keyboard
#         else:
#             keyboard = None
        
#         await message.answer(
#             text,
#             reply_markup=keyboard,
#             parse_mode="HTML"
#         )
        
#         logger.info(f"[Food] User {user_id} viewed food history")
        
#     except Exception as e:
#         logger.exception(f"[Food] Error in /food for user {message.from_user.id}: {e}")
#         await message.answer("⚠️ Ошибка при получении истории питания.")


# @router.callback_query(lambda c: c.data and c.data.startswith("show_day:"))
# async def handle_show_day(callback: CallbackQuery):
#     """Показывает приемы пищи для конкретного дня"""
#     try:
#         user_id = callback.from_user.id
        
#         # Извлекаем дату из callback_data (формат: "show_day:2025-11-08")
#         date_str = callback.data.split(":", 1)[1]
        
#         user = await get_user_by_id(user_id)
#         if not user:
#             await callback.answer("⚠️ Пользователь не найден", show_alert=True)
#             return
        
#         user_tz = user.get("timezone", "Europe/Moscow")
        
#         # Получаем приемы пищи для этого дня
#         day_data = await get_day_meals(user_id, date_str, user_tz)
        
#         if not day_data:
#             await callback.answer("⚠️ Данные не найдены", show_alert=True)
#             return
        
#         # Формируем сообщение с деталями
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
        
#         # Просто отправляем новое сообщение (без кнопок)
#         await callback.message.answer(
#             text,
#             parse_mode="HTML"
#         )
        
#         await callback.answer()
#         logger.info(f"[Food] User {user_id} viewed day {date_str}")
        
#     except Exception as e:
#         logger.exception(f"[Food] Error showing day: {e}")
#         await callback.answer("⚠️ Ошибка при загрузке данных", show_alert=True)

# @router.callback_query(lambda c: c.data == "show_today")
# async def handle_show_today_from_button(callback: CallbackQuery):
#     """Показывает все приемы за сегодня (вызывается из кнопки после добавления)"""
#     try:
#         user_id = callback.from_user.id
#         user = await get_user_by_id(user_id)
        
#         if not user:
#             await callback.answer("⚠️ Пользователь не найден", show_alert=True)
#             return
        
#         user_tz = user.get("timezone", "Europe/Moscow")
        
#         # Получаем историю
#         history = await get_food_history(user_id, user_tz, days=7)
        
#         if not history or len(history) == 0:
#             await callback.answer("📭 Нет данных", show_alert=True)
#             return
        
#         # Берем сегодняшний день (первый элемент)
#         today = history[0]
        
#         # Формируем сообщение
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
        
#         # Предыдущие дни
#         if len(history) > 1:
#             text += "━━━━━━━━━━━━━━━━\n"
#             text += "📅 <b>Предыдущие дни:</b>\n\n"
            
#             for day in history[1:]:
#                 text += f"<b>{day['date_formatted']}</b>\n"
#                 text += f"🔥 {float(day['total_calories']):.0f} ккал | "
#                 text += f"🍽 {day['meals_count']} приемов\n\n"
            
#             text += "👇 <i>Нажмите на день чтобы увидеть приемы пищи</i>"
        
#         # Клавиатуры
#         today_keyboard = get_meal_delete_keyboard(today['meals'])
#         history_keyboard = get_history_keyboard(history)
        
#         if today_keyboard and history_keyboard:
#             combined_buttons = today_keyboard.inline_keyboard + history_keyboard.inline_keyboard
#             keyboard = InlineKeyboardMarkup(inline_keyboard=combined_buttons)
#         elif today_keyboard:
#             keyboard = today_keyboard
#         elif history_keyboard:
#             keyboard = history_keyboard
#         else:
#             keyboard = None
        
#         # Отправляем новое сообщение (не редактируем старое)
#         await callback.message.answer(
#             text,
#             reply_markup=keyboard,
#             parse_mode="HTML"
#         )
        
#         await callback.answer()
#         logger.info(f"[Food] User {user_id} viewed today from button")
        
#     except Exception as e:
#         logger.exception(f"[Food] Error showing today from button: {e}")
#         await callback.answer("⚠️ Ошибка", show_alert=True)

# @router.callback_query(lambda c: c.data and c.data.startswith("del_meal:"))
# async def handle_delete_meal(callback: CallbackQuery):
#     """Удаляет прием пищи из сегодняшнего дня"""
#     try:
#         user_id = callback.from_user.id
#         meal_id = int(callback.data.split(":", 1)[1])
        
#         # Удаляем прием пищи
#         success = await delete_meal(meal_id, user_id)
        
#         if not success:
#             await callback.answer(
#                 "⚠️ Не удалось удалить. Возможно, прием уже удален.",
#                 show_alert=True
#             )
#             return
        
#         # Получаем обновленные данные
#         user = await get_user_by_id(user_id)
#         user_tz = user.get("timezone", "Europe/Moscow")
#         history = await get_food_history(user_id, user_tz, days=7)
        
#         if not history or len(history) == 0:
#             await callback.message.edit_text(
#                 "📭 <b>Все приемы пищи удалены</b>\n\n"
#                 "Отправьте фото блюда или опишите что съели!",
#                 parse_mode="HTML"
#             )
#             await callback.answer("✅ Прием пищи удален")
#             return
        
#         # Формируем обновленное сообщение
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
        
#         today_keyboard = get_meal_delete_keyboard(today['meals'])
#         history_keyboard = get_history_keyboard(history)
        
#         if today_keyboard and history_keyboard:
#             combined_buttons = today_keyboard.inline_keyboard + history_keyboard.inline_keyboard
#             keyboard = InlineKeyboardMarkup(inline_keyboard=combined_buttons)
#         elif today_keyboard:
#             keyboard = today_keyboard
#         elif history_keyboard:
#             keyboard = history_keyboard
#         else:
#             keyboard = None
        
#         await callback.message.edit_text(
#             text,
#             reply_markup=keyboard,
#             parse_mode="HTML"
#         )
        
#         await callback.answer("✅ Прием пищи удален")
#         logger.info(f"[Food] User {user_id} deleted meal {meal_id}")
        
#     except Exception as e:
#         logger.exception(f"[Food] Error deleting meal: {e}")
#         await callback.answer("⚠️ Ошибка при удалении", show_alert=True)


# @router.callback_query(lambda c: c.data and c.data.startswith("undo_last:"))
# async def handle_undo_last(callback: CallbackQuery):
#     """Отменяет последнее добавление (удаляет приемы пищи)"""
#     try:
#         user_id = callback.from_user.id
        
#         # Извлекаем ID приемов пищи
#         meal_ids_str = callback.data.split(":", 1)[1]
#         meal_ids = [int(x) for x in meal_ids_str.split(",")]
        
#         if not meal_ids:
#             await callback.answer("⚠️ Ошибка: нет данных", show_alert=True)
#             return
        
#         # Удаляем все приемы
#         deleted_count = 0
#         for meal_id in meal_ids:
#             success = await delete_meal(meal_id, user_id)
#             if success:
#                 deleted_count += 1
        
#         if deleted_count == 0:
#             await callback.answer("⚠️ Не удалось удалить", show_alert=True)
#             return
        
#         # Получаем обновленные итоги
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
#             await callback.answer(f"✅ Удалено: {deleted_count}")
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
#         await callback.answer(f"✅ Удалено: {deleted_count}")
#         logger.info(f"[Food] User {user_id} undid last addition ({deleted_count} meals)")
        
#     except Exception as e:
#         logger.exception(f"[Food] Error undoing: {e}")
#         await callback.answer("⚠️ Ошибка при отмене", show_alert=True)
import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from app.services.meals import (
    get_food_history,
    get_day_meals,
    get_today_summary,
    delete_meal,
    delete_multiple_meals,
    get_week_stats
)
from app.db.redis_client import redis_arq
from app.services.user import get_user_by_id
import pytz

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("food"))
async def cmd_food(message: Message):
    """
    Команда /food - показывает историю питания за 7 дней
    """
    user_id = message.from_user.id
    logger.info(f"[Food Handler] /food command from user {user_id}")
    
    try:
        # Получаем данные пользователя
        user = await get_user_by_id(user_id)
        if not user:
            await message.answer("❌ Пользователь не найден")
            return
        
        user_tz = user.get('timezone', 'Europe/Moscow')
        
        # Получаем историю за 7 дней
        history = await get_food_history(user_id, user_tz, days=7)
        
        if not history or len(history) == 0:
            await message.answer(
                "📭 <b>У вас пока нет записей о еде</b>\n\n"
                "Отправьте фото блюда или опишите что съели!",
                parse_mode="HTML"
            )
            return
        
        # Формируем сообщение
        today = history[0]
        
        text = "📊 <b>Моя еда</b>\n\n"
        text += "━━━━━━━━━━━━━━━━\n"
        text += f"📅 <b>{today['date_formatted']}</b>\n"
        text += f"🔥 {float(today['total_calories']):.0f} ккал | "
        text += f"🥩 {float(today['total_protein']):.1f}г | "
        text += f"🧈 {float(today['total_fat']):.1f}г | "
        text += f"🍞 {float(today['total_carbs']):.1f}г\n\n"
        
        # Приемы пищи сегодня
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
        
        # Предыдущие дни
        if len(history) > 1:
            text += "━━━━━━━━━━━━━━━━\n"
            text += "📅 <b>Предыдущие дни:</b>\n\n"
            
            for day in history[1:]:
                text += f"<b>{day['date_formatted']}</b>\n"
                text += f"🔥 {float(day['total_calories']):.0f} ккал | "
                text += f"🍽 {day['meals_count']} приемов\n\n"
            
            text += "👇 <i>Нажмите на день чтобы увидеть приемы пищи</i>"
        
        # Создаем кнопки для удаления и просмотра дней
        buttons = []
        
        # Кнопки удаления для сегодняшних приемов
        if today['meals']:
            for meal in today['meals'][-10:]:  # Последние 10
                meal_time = meal["meal_datetime"].strftime("%H:%M")
                buttons.append([
                    InlineKeyboardButton(
                        text=f"🗑 {meal_time} - {meal['food_name'][:25]}",
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
    """
    Callback для показа приемов пищи за сегодня
    """
    await callback.answer()
    
    user_id = callback.from_user.id
    logger.info(f"[Food Handler] show_today callback from user {user_id}")
    
    try:
        # Получаем пользователя
        user = await get_user_by_id(user_id)
        if not user:
            await callback.message.edit_text("❌ Пользователь не найден")
            return
        
        user_tz = user.get('timezone', 'Europe/Moscow')
        
        # Получаем историю за 7 дней
        history = await get_food_history(user_id, user_tz, days=7)
        
        if not history or len(history) == 0:
            await callback.message.answer(
                "📭 Сегодня вы ещё ничего не добавили.\n\n"
                "Отправьте фото еды или опишите блюдо текстом!"
            )
            return
        
        # Формируем сообщение для сегодня
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
        
        # Кнопки
        buttons = []
        if today['meals']:
            for meal in today['meals'][-10:]:
                meal_time = meal["meal_datetime"].strftime("%H:%M")
                buttons.append([
                    InlineKeyboardButton(
                        text=f"🗑 {meal_time} - {meal['food_name'][:25]}",
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
        user_id = callback.from_user.id
        date_str = callback.data.split(":", 1)[1]
        
        user = await get_user_by_id(user_id)
        if not user:
            await callback.answer("⚠️ Пользователь не найден", show_alert=True)
            return
        
        user_tz = user.get("timezone", "Europe/Moscow")
        
        # Получаем приемы пищи для этого дня
        day_data = await get_day_meals(user_id, date_str, user_tz)
        
        if not day_data:
            await callback.answer("⚠️ Данные не найдены", show_alert=True)
            return
        
        # Формируем сообщение
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
        await callback.answer()
        
    except Exception as e:
        logger.exception(f"[Food] Error showing day: {e}")
        await callback.answer("⚠️ Ошибка при загрузке данных", show_alert=True)


@router.callback_query(F.data.startswith("del_meal:"))
async def handle_delete_meal(callback: CallbackQuery):
    """Удаляет прием пищи"""
    try:
        user_id = callback.from_user.id
        meal_id = int(callback.data.split(":", 1)[1])
        
        # Удаляем прием пищи
        success = await delete_meal(meal_id, user_id)
        
        if not success:
            await callback.answer(
                "⚠️ Не удалось удалить. Возможно, прием уже удален.",
                show_alert=True
            )
            return
        
        # Получаем обновленные данные
        user = await get_user_by_id(user_id)
        user_tz = user.get("timezone", "Europe/Moscow")
        history = await get_food_history(user_id, user_tz, days=7)
        
        if not history or len(history) == 0:
            await callback.message.edit_text(
                "📭 <b>Все приемы пищи удалены</b>\n\n"
                "Отправьте фото блюда или опишите что съели!",
                parse_mode="HTML"
            )
            await callback.answer("✅ Прием пищи удален")
            return
        
        # Формируем обновленное сообщение
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
        
        # Кнопки
        buttons = []
        if today['meals']:
            for meal in today['meals'][-10:]:
                meal_time = meal["meal_datetime"].strftime("%H:%M")
                buttons.append([
                    InlineKeyboardButton(
                        text=f"🗑 {meal_time} - {meal['food_name'][:25]}",
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
        
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        await callback.answer("✅ Прием пищи удален")
        
    except Exception as e:
        logger.exception(f"[Food] Error deleting meal: {e}")
        await callback.answer("⚠️ Ошибка при удалении", show_alert=True)


@router.callback_query(F.data.startswith("undo_last:"))
async def handle_undo_last(callback: CallbackQuery):
    """Отменяет последнее добавление (удаляет приемы пищи)"""
    try:
        user_id = callback.from_user.id
        
        # Извлекаем ID приемов пищи
        meal_ids_str = callback.data.split(":", 1)[1]
        meal_ids = [int(x) for x in meal_ids_str.split(",")]
        
        if not meal_ids:
            await callback.answer("⚠️ Ошибка: нет данных", show_alert=True)
            return
        
        # Удаляем все приемы
        deleted_count = await delete_multiple_meals(meal_ids, user_id)
        
        if deleted_count == 0:
            await callback.answer("⚠️ Не удалось удалить", show_alert=True)
            return
        
        # Получаем обновленные итоги
        user = await get_user_by_id(user_id)
        user_tz = user.get("timezone", "Europe/Moscow")
        summary = await get_today_summary(user_id, user_tz)
        
        totals = summary["totals"]
        meals = summary["meals"]
        
        if not meals:
            await callback.message.edit_text(
                "✅ <b>Добавление отменено</b>\n\n"
                "📭 Сегодня пока нет приемов пищи.\n\n"
                "Отправьте фото блюда или опишите что съели!",
                parse_mode="HTML"
            )
            await callback.answer(f"✅ Удалено: {deleted_count}")
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
        
        await callback.message.edit_text(text, parse_mode="HTML")
        await callback.answer(f"✅ Удалено: {deleted_count}")
        
    except Exception as e:
        logger.exception(f"[Food] Error undoing: {e}")
        await callback.answer("⚠️ Ошибка при отмене", show_alert=True)



@router.message(Command("food"))
async def cmd_food(message: Message):
    """
    Команда /food - показывает все приемы пищи за сегодня
    """
    user_id = message.from_user.id
    logger.info(f"[Food Handler] /food command from user {user_id}")
    
    try:
        # Получаем timezone пользователя
        user = await get_user_by_id(user_id)
        if not user:
            await message.answer("❌ Пользователь не найден")
            return
        
        user_tz = user.get('timezone', 'UTC')
        
        # Получаем приемы пищи за сегодня
        meals = await get_today_meals(user_id, user_tz)
        
        if not meals:
            await message.answer(
                "📋 Сегодня вы ещё ничего не добавили.\n\n"
                "Отправьте фото еды или опишите блюдо текстом, "
                "и я посчитаю калории!"
            )
            return
        
        # Получаем итоги за день
        summary = await get_today_summary(user_id, user_tz)
        
        # Формируем сообщение
        message_text = "📋 **Ваши приемы пищи за сегодня:**\n\n"
        
        for meal in meals:
            meal_time = format_meal_time(meal['created_at'], user_tz)
            message_text += f"🕐 **{meal_time}**\n"
            message_text += f"🍽 {meal['name']}\n"
            message_text += f"   Вес: {meal['weight']}г\n"
            message_text += f"   {meal['calories']} ккал • "
            message_text += f"{meal['protein']}б • {meal['fat']}ж • {meal['carbs']}у\n\n"
        
        message_text += "━━━━━━━━━━━━━━━━\n"
        message_text += "📊 **ИТОГО ЗА ДЕНЬ:**\n\n"
        message_text += f"🔥 {summary['total_calories']} ккал\n"
        message_text += f"🥩 Белки: {summary['total_protein']} г\n"
        message_text += f"🧈 Жиры: {summary['total_fat']} г\n"
        message_text += f"🍞 Углеводы: {summary['total_carbs']} г\n"
        message_text += f"🍽 Приемов пищи: {summary['meal_count']}\n"
        message_text += "━━━━━━━━━━━━━━━━"
        
        # Кнопки для удаления приемов пищи
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🗑 Удалить прием пищи",
                    callback_data="delete_meal_menu"
                )
            ]
        ])
        
        await message.answer(message_text, reply_markup=keyboard)
        
    except Exception as e:
        logger.exception(f"[Food Handler] Error in /food for user {user_id}: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте позже.")


@router.callback_query(F.data == "show_today")
async def callback_show_today(callback: CallbackQuery):
    """
    Callback для показа приемов пищи за сегодня
    """
    await callback.answer()
    
    user_id = callback.from_user.id
    logger.info(f"[Food Handler] show_today callback from user {user_id}")
    
    try:
        # Получаем timezone пользователя
        user = await get_user_by_id(user_id)
        if not user:
            await callback.message.edit_text("❌ Пользователь не найден")
            return
        
        user_tz = user.get('timezone', 'UTC')
        
        # Получаем приемы пищи за сегодня
        meals = await get_today_meals(user_id, user_tz)
        
        if not meals:
            await callback.message.edit_text(
                "📋 Сегодня вы ещё ничего не добавили.\n\n"
                "Отправьте фото еды или опишите блюдо текстом!"
            )
            return
        
        # Получаем итоги за день
        summary = await get_today_summary(user_id, user_tz)
        
        # Формируем сообщение
        message_text = "📋 **Ваши приемы пищи за сегодня:**\n\n"
        
        for meal in meals:
            meal_time = format_meal_time(meal['created_at'], user_tz)
            message_text += f"🕐 **{meal_time}**\n"
            message_text += f"🍽 {meal['name']}\n"
            message_text += f"   Вес: {meal['weight']}г\n"
            message_text += f"   {meal['calories']} ккал • "
            message_text += f"{meal['protein']}б • {meal['fat']}ж • {meal['carbs']}у\n\n"
        
        message_text += "━━━━━━━━━━━━━━━━\n"
        message_text += "📊 **ИТОГО ЗА ДЕНЬ:**\n\n"
        message_text += f"🔥 {summary['total_calories']} ккал\n"
        message_text += f"🥩 Белки: {summary['total_protein']} г\n"
        message_text += f"🧈 Жиры: {summary['total_fat']} г\n"
        message_text += f"🍞 Углеводы: {summary['total_carbs']} г\n"
        message_text += f"🍽 Приемов пищи: {summary['meal_count']}\n"
        message_text += "━━━━━━━━━━━━━━━━"
        
        # Кнопки для удаления приемов пищи
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🗑 Удалить прием пищи",
                    callback_data="delete_meal_menu"
                )
            ]
        ])
        
        await callback.message.edit_text(message_text, reply_markup=keyboard)
        
    except Exception as e:
        logger.exception(f"[Food Handler] Error in show_today for user {user_id}: {e}")
        await callback.message.edit_text("❌ Произошла ошибка. Попробуйте позже.")


@router.callback_query(F.data == "delete_meal_menu")
async def callback_delete_meal_menu(callback: CallbackQuery):
    """
    Показывает меню для выбора приема пищи для удаления
    """
    await callback.answer()
    
    user_id = callback.from_user.id
    logger.info(f"[Food Handler] delete_meal_menu from user {user_id}")
    
    try:
        # Получаем timezone пользователя
        user = await get_user_by_id(user_id)
        if not user:
            await callback.message.edit_text("❌ Пользователь не найден")
            return
        
        user_tz = user.get('timezone', 'UTC')
        
        # Получаем приемы пищи за сегодня
        meals = await get_today_meals(user_id, user_tz)
        
        if not meals:
            await callback.message.edit_text(
                "📋 Нет приемов пищи для удаления."
            )
            return
        
        # Формируем сообщение и кнопки
        message_text = "🗑 **Выберите прием пищи для удаления:**\n\n"
        
        buttons = []
        for i, meal in enumerate(meals, 1):
            meal_time = format_meal_time(meal['created_at'], user_tz)
            message_text += f"{i}. **{meal_time}** - {meal['name']} ({meal['calories']} ккал)\n"
            
            buttons.append([
                InlineKeyboardButton(
                    text=f"{i}. {meal['name']} - {meal['calories']} ккал",
                    callback_data=f"delete_meal:{meal['id']}"
                )
            ])
        
        # Добавляем кнопку "Назад"
        buttons.append([
            InlineKeyboardButton(
                text="◀️ Назад",
                callback_data="show_today"
            )
        ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        await callback.message.edit_text(message_text, reply_markup=keyboard)
        
    except Exception as e:
        logger.exception(f"[Food Handler] Error in delete_meal_menu for user {user_id}: {e}")
        await callback.message.edit_text("❌ Произошла ошибка. Попробуйте позже.")


@router.callback_query(F.data.startswith("delete_meal:"))
async def callback_delete_meal(callback: CallbackQuery):
    """
    Удаляет выбранный прием пищи
    """
    await callback.answer()
    
    user_id = callback.from_user.id
    meal_id = int(callback.data.split(":")[1])
    
    logger.info(f"[Food Handler] Deleting meal {meal_id} for user {user_id}")
    
    try:
        # Удаляем прием пищи
        deleted = await delete_meal(user_id, meal_id)
        
        if not deleted:
            await callback.message.edit_text(
                "❌ Прием пищи не найден или уже удален."
            )
            return
        
        # Получаем обновленные данные
        user = await get_user_by_id(user_id)
        user_tz = user.get('timezone', 'UTC')
        
        meals = await get_today_meals(user_id, user_tz)
        summary = await get_today_summary(user_id, user_tz)
        
        if not meals:
            await callback.message.edit_text(
                "✅ Прием пищи удален!\n\n"
                "📋 Сегодня больше нет добавленных приемов пищи."
            )
            return
        
        # Формируем обновленное сообщение
        message_text = "✅ **Прием пищи удален!**\n\n"
        message_text += "📋 **Оставшиеся приемы пищи:**\n\n"
        
        for meal in meals:
            meal_time = format_meal_time(meal['created_at'], user_tz)
            message_text += f"🕐 **{meal_time}**\n"
            message_text += f"🍽 {meal['name']}\n"
            message_text += f"   Вес: {meal['weight']}г\n"
            message_text += f"   {meal['calories']} ккал • "
            message_text += f"{meal['protein']}б • {meal['fat']}ж • {meal['carbs']}у\n\n"
        
        message_text += "━━━━━━━━━━━━━━━━\n"
        message_text += "📊 **ИТОГО ЗА ДЕНЬ:**\n\n"
        message_text += f"🔥 {summary['total_calories']} ккал\n"
        message_text += f"🥩 Белки: {summary['total_protein']} г\n"
        message_text += f"🧈 Жиры: {summary['total_fat']} г\n"
        message_text += f"🍞 Углеводы: {summary['total_carbs']} г\n"
        message_text += f"🍽 Приемов пищи: {summary['meal_count']}\n"
        message_text += "━━━━━━━━━━━━━━━━"
        
        # Кнопки
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🗑 Удалить еще",
                    callback_data="delete_meal_menu"
                )
            ]
        ])
        
        await callback.message.edit_text(message_text, reply_markup=keyboard)
        
    except Exception as e:
        logger.exception(f"[Food Handler] Error deleting meal {meal_id} for user {user_id}: {e}")
        await callback.message.edit_text("❌ Ошибка при удалении. Попробуйте позже.")


@router.callback_query(F.data.startswith("confirm_meal:"))
async def callback_confirm_meal(callback: CallbackQuery):
    """
    Подтверждение добавления блюда в рацион
    """
    await callback.answer()
    
    user_id = callback.from_user.id
    meal_key = callback.data.split(":")[1]
    message_id = callback.message.message_id
    
    logger.info(f"[Food Handler] Confirming meal for user {user_id}, key={meal_key}")
    
    # Ставим задачу в очередь
    await redis_arq.enqueue_job(
        'confirm_meal_addition',
        user_id,
        meal_key,
        message_id
    )
    
    # Показываем, что обрабатываем
    await callback.message.edit_text(
        "⏳ Добавляю в рацион..."
    )


@router.callback_query(F.data.startswith("cancel_meal:"))
async def callback_cancel_meal(callback: CallbackQuery):
    """
    Отмена добавления блюда
    """
    await callback.answer()
    
    user_id = callback.from_user.id
    meal_key = callback.data.split(":")[1]
    message_id = callback.message.message_id
    
    logger.info(f"[Food Handler] Canceling meal for user {user_id}, key={meal_key}")
    
    # Ставим задачу в очередь
    await redis_arq.enqueue_job(
        'cancel_meal_addition',
        user_id,
        meal_key,
        message_id
    )
    
    # Показываем, что обрабатываем
    await callback.message.edit_text(
        "⏳ Отменяю..."
    )


@router.callback_query(F.data.startswith("undo_meal:"))
async def callback_undo_meal(callback: CallbackQuery):
    """
    Отмена последнего добавления (удаление только что добавленных блюд)
    """
    await callback.answer()
    
    user_id = callback.from_user.id
    meal_key = callback.data.split(":")[1]
    
    logger.info(f"[Food Handler] Undoing meal for user {user_id}, key={meal_key}")
    
    try:
        # Получаем timezone пользователя
        user = await get_user_by_id(user_id)
        if not user:
            await callback.message.edit_text("❌ Пользователь не найден")
            return
        
        user_tz = user.get('timezone', 'UTC')
        
        # Получаем последние приемы пищи (они должны быть добавлены только что)
        meals = await get_today_meals(user_id, user_tz, limit=10)
        
        if not meals:
            await callback.message.edit_text(
                "❌ Нет приемов пищи для отмены."
            )
            return
        
        # Удаляем последние добавленные приемы
        # (предполагаем, что они были добавлены в последнюю минуту)
        now = datetime.now()
        deleted_count = 0
        
        for meal in meals:
            meal_time = meal['created_at']
            time_diff = (now - meal_time).total_seconds()
            
            # Если прием был добавлен меньше минуты назад
            if time_diff < 60:
                await delete_meal(user_id, meal['id'])
                deleted_count += 1
        
        if deleted_count == 0:
            await callback.message.edit_text(
                "❌ Не найдено недавно добавленных приемов пищи.\n\n"
                "Используйте /food для просмотра и удаления конкретных приемов."
            )
            return
        
        # Получаем обновленные данные
        meals = await get_today_meals(user_id, user_tz)
        summary = await get_today_summary(user_id, user_tz)
        
        if not meals:
            await callback.message.edit_text(
                f"✅ Удалено приемов пищи: {deleted_count}\n\n"
                "📋 Сегодня больше нет добавленных приемов пищи."
            )
            return
        
        # Формируем обновленное сообщение
        message_text = f"✅ **Удалено приемов пищи: {deleted_count}**\n\n"
        message_text += "📋 **Оставшиеся приемы пищи:**\n\n"
        
        for meal in meals[:5]:  # Показываем только последние 5
            meal_time = format_meal_time(meal['created_at'], user_tz)
            message_text += f"🕐 **{meal_time}**\n"
            message_text += f"🍽 {meal['name']} ({meal['calories']} ккал)\n\n"
        
        if len(meals) > 5:
            message_text += f"... и еще {len(meals) - 5} приемов\n\n"
        
        message_text += "━━━━━━━━━━━━━━━━\n"
        message_text += "📊 **ИТОГО ЗА ДЕНЬ:**\n\n"
        message_text += f"🔥 {summary['total_calories']} ккал\n"
        message_text += f"🥩 Белки: {summary['total_protein']} г\n"
        message_text += f"🧈 Жиры: {summary['total_fat']} г\n"
        message_text += f"🍞 Углеводы: {summary['total_carbs']} г\n"
        message_text += f"🍽 Приемов пищи: {summary['meal_count']}\n"
        message_text += "━━━━━━━━━━━━━━━━"
        
        await callback.message.edit_text(message_text)
        
    except Exception as e:
        logger.exception(f"[Food Handler] Error undoing meal for user {user_id}: {e}")
        await callback.message.edit_text("❌ Ошибка при отмене. Попробуйте позже.")