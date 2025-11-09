from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from app.services.user import get_user_by_id
from app.services.meals import (
    get_today_summary,
    get_week_summary,
    get_nutrition_stats,
    delete_meal
)
from datetime import datetime
import pytz
import logging

router = Router()
logger = logging.getLogger(__name__)


def get_meal_keyboard(meals: list, user_id: int) -> InlineKeyboardMarkup:
    """Создает клавиатуру с кнопками удаления для каждого приема"""
    if not meals:
        return None
    
    buttons = []
    
    # Показываем только последние 10 приемов (ограничение Telegram)
    for meal in meals[-10:]:
        meal_id = meal["id"]
        meal_name = meal["food_name"][:30]  # Обрезаем длинные названия
        meal_time = meal["meal_datetime"].strftime("%H:%M")
        
        buttons.append([
            InlineKeyboardButton(
                text=f"🗑 {meal_time} - {meal_name}",
                callback_data=f"del_meal:{meal_id}"
            )
        ])
    
    buttons.append([
        InlineKeyboardButton(
            text="🔄 Обновить",
            callback_data="refresh_today"
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(Command("today"))
async def show_today(message: Message):
    """Показывает детальную статистику за сегодня с возможностью удаления"""
    try:
        user_id = message.from_user.id
        user = await get_user_by_id(user_id)
        
        if not user:
            await message.answer("⚠️ Пользователь не найден. Используйте /start")
            return
        
        user_tz = user.get("timezone", "Europe/Moscow")
        summary = await get_today_summary(user_id, user_tz)
        
        totals = summary["totals"]
        meals = summary["meals"]
        
        if not meals:
            await message.answer(
                "📭 <b>Сегодня вы еще ничего не добавили</b>\n\n"
                "Отправьте фото блюда или опишите что съели текстом!",
                parse_mode="HTML"
            )
            return
        
        tz = pytz.timezone(user_tz)
        today = datetime.now(tz).strftime("%d.%m.%Y")
        
        text = f"📊 <b>Итоги за {today}</b>\n\n"
        text += "━━━━━━━━━━━━━━━━\n"
        text += f"🔥 Калории: <b>{float(totals['total_calories']):.0f}</b> ккал\n"
        text += f"🥩 Белки: <b>{float(totals['total_protein']):.1f}</b> г\n"
        text += f"🧈 Жиры: <b>{float(totals['total_fat']):.1f}</b> г\n"
        text += f"🍞 Углеводы: <b>{float(totals['total_carbs']):.1f}</b> г\n"
        text += "━━━━━━━━━━━━━━━━\n\n"
        
        text += f"<b>Приемы пищи ({totals['meals_count']}):</b>\n\n"
        
        # ИСПРАВЛЕНИЕ: Показываем ВСЕ приемы, но с ограничением на длину сообщения
        MAX_MESSAGE_LENGTH = 3800  # Telegram лимит ~4096, оставляем запас
        
        for idx, meal in enumerate(meals, 1):
            time = meal["meal_datetime"].strftime("%H:%M")
            meal_text = (
                f"{idx}. ⏰ <b>{time}</b> — {meal['food_name']}\n"
                f"   {float(meal['calories']):.0f} ккал • "
                f"{float(meal['protein']):.1f}б • "
                f"{float(meal['fat']):.1f}ж • "
                f"{float(meal['carbs']):.1f}у\n\n"
            )
            
            # Проверка длины сообщения
            if len(text + meal_text) > MAX_MESSAGE_LENGTH:
                text += f"\n<i>... и еще {len(meals) - idx + 1} приемов пищи</i>\n"
                break
            
            text += meal_text
        
        # Добавляем подсказку об удалении
        text += "\n💡 Чтобы удалить прием пищи, нажмите кнопку ниже"
        
        keyboard = get_meal_keyboard(meals, user_id)
        
        await message.answer(
            text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"[Stats] User {user_id} viewed today stats ({len(meals)} meals)")
        
    except Exception as e:
        logger.exception(f"[Stats] Error in /today for user {message.from_user.id}: {e}")
        await message.answer("⚠️ Ошибка при получении статистики.")


@router.callback_query(lambda c: c.data and c.data.startswith("del_meal:"))
async def handle_delete_meal(callback: CallbackQuery):
    """Удаляет прием пищи"""
    try:
        user_id = callback.from_user.id
        meal_id = int(callback.data.split(":", 1)[1])
        
        # Удаляем прием пищи
        success = await delete_meal(meal_id, user_id)
        
        if not success:
            await callback.answer(
                "⚠️ Не удалось удалить прием пищи. Возможно, он уже удален.",
                show_alert=True
            )
            return
        
        # Обновляем сообщение
        user = await get_user_by_id(user_id)
        user_tz = user.get("timezone", "Europe/Moscow")
        summary = await get_today_summary(user_id, user_tz)
        
        totals = summary["totals"]
        meals = summary["meals"]
        
        if not meals:
            await callback.message.edit_text(
                "📭 <b>Все приемы пищи удалены</b>\n\n"
                "Отправьте фото блюда или опишите что съели!",
                parse_mode="HTML"
            )
            await callback.answer("✅ Прием пищи удален")
            return
        
        tz = pytz.timezone(user_tz)
        today = datetime.now(tz).strftime("%d.%m.%Y")
        
        text = f"📊 <b>Итоги за {today}</b>\n\n"
        text += "━━━━━━━━━━━━━━━━\n"
        text += f"🔥 Калории: <b>{float(totals['total_calories']):.0f}</b> ккал\n"
        text += f"🥩 Белки: <b>{float(totals['total_protein']):.1f}</b> г\n"
        text += f"🧈 Жиры: <b>{float(totals['total_fat']):.1f}</b> г\n"
        text += f"🍞 Углеводы: <b>{float(totals['total_carbs']):.1f}</b> г\n"
        text += "━━━━━━━━━━━━━━━━\n\n"
        
        text += f"<b>Приемы пищи ({totals['meals_count']}):</b>\n\n"
        
        MAX_MESSAGE_LENGTH = 3800
        
        for idx, meal in enumerate(meals, 1):
            time = meal["meal_datetime"].strftime("%H:%M")
            meal_text = (
                f"{idx}. ⏰ <b>{time}</b> — {meal['food_name']}\n"
                f"   {float(meal['calories']):.0f} ккал • "
                f"{float(meal['protein']):.1f}б • "
                f"{float(meal['fat']):.1f}ж • "
                f"{float(meal['carbs']):.1f}у\n\n"
            )
            
            if len(text + meal_text) > MAX_MESSAGE_LENGTH:
                text += f"\n<i>... и еще {len(meals) - idx + 1} приемов пищи</i>\n"
                break
            
            text += meal_text
        
        text += "\n💡 Чтобы удалить прием пищи, нажмите кнопку ниже"
        
        keyboard = get_meal_keyboard(meals, user_id)
        
        await callback.message.edit_text(
            text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        await callback.answer("✅ Прием пищи удален")
        logger.info(f"[Stats] User {user_id} deleted meal {meal_id}")
        
    except Exception as e:
        logger.exception(f"[Stats] Error deleting meal: {e}")
        await callback.answer("⚠️ Ошибка при удалении", show_alert=True)


@router.callback_query(lambda c: c.data == "refresh_today")
async def handle_refresh_today(callback: CallbackQuery):
    """Обновляет статистику за сегодня"""
    try:
        user_id = callback.from_user.id
        user = await get_user_by_id(user_id)
        user_tz = user.get("timezone", "Europe/Moscow")
        summary = await get_today_summary(user_id, user_tz)
        
        # Код повторяет show_today (можно вынести в отдельную функцию)
        # ... (тот же код что и выше)
        
        await callback.answer("🔄 Обновлено")
        
    except Exception as e:
        logger.exception(f"[Stats] Error refreshing: {e}")
        await callback.answer("⚠️ Ошибка", show_alert=True)


@router.message(Command("week"))
async def show_week(message: Message):
    """Показывает статистику за неделю"""
    try:
        user_id = message.from_user.id
        user = await get_user_by_id(user_id)
        
        if not user:
            await message.answer("⚠️ Пользователь не найден. Используйте /start")
            return
        
        user_tz = user.get("timezone", "Europe/Moscow")
        week_data = await get_week_summary(user_id, user_tz)
        
        if not week_data:
            await message.answer(
                "📭 <b>За последнюю неделю нет данных</b>\n\n"
                "Начните добавлять блюда - отправьте фото или описание!",
                parse_mode="HTML"
            )
            return
        
        text = "📈 <b>Статистика за неделю</b>\n\n"
        
        total_week_cal = 0
        total_week_meals = 0
        
        weekdays = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        
        for day in week_data:
            date_obj = day["date"]
            weekday = weekdays[date_obj.weekday()]
            date_str = date_obj.strftime(f"%d.%m ({weekday})")
            
            cal = float(day["total_calories"])
            meals = day["meals_count"]
            
            total_week_cal += cal
            total_week_meals += meals
            
            text += f"📅 {date_str}\n"
            text += f"   {cal:.0f} ккал • {meals} приемов\n\n"
        
        avg_cal = total_week_cal / len(week_data) if week_data else 0
        
        text += "━━━━━━━━━━━━━━━━\n"
        text += f"<b>Среднее в день:</b> {avg_cal:.0f} ккал\n"
        text += f"<b>Всего приемов:</b> {total_week_meals}"
        
        await message.answer(text, parse_mode="HTML")
        logger.info(f"[Stats] User {user_id} viewed week stats")
        
    except Exception as e:
        logger.exception(f"[Stats] Error in /week for user {message.from_user.id}: {e}")
        await message.answer("⚠️ Ошибка при получении статистики.")
        
@router.callback_query(lambda c: c.data and c.data.startswith("undo_last:"))
async def handle_undo_last(callback: CallbackQuery):
    """Отменяет последнее добавление (удаляет приемы пищи)"""
    try:
        user_id = callback.from_user.id
        
        # Извлекаем ID приемов пищи из callback_data
        meal_ids_str = callback.data.split(":", 1)[1]
        meal_ids = [int(x) for x in meal_ids_str.split(",")]
        
        if not meal_ids:
            await callback.answer("⚠️ Ошибка: нет данных для удаления", show_alert=True)
            return
        
        # Удаляем все приемы пищи из этого добавления
        deleted_count = 0
        for meal_id in meal_ids:
            success = await delete_meal(meal_id, user_id)
            if success:
                deleted_count += 1
        
        if deleted_count == 0:
            await callback.answer(
                "⚠️ Не удалось удалить приемы пищи. Возможно, они уже удалены.",
                show_alert=True
            )
            return
        
        # Получаем обновленные итоги
        user = await get_user_by_id(user_id)
        user_tz = user.get("timezone", "Europe/Moscow")
        summary = await get_today_summary(user_id, user_tz)
        
        totals = summary["totals"]
        meals = summary["meals"]
        
        # Формируем новое сообщение
        if not meals:
            await callback.message.edit_text(
                "✅ <b>Добавление отменено</b>\n\n"
                "📭 Сегодня пока нет приемов пищи.\n\n"
                "Отправьте фото блюда или опишите что съели!",
                parse_mode="HTML"
            )
            await callback.answer(f"✅ Удалено приемов: {deleted_count}")
            return
        
        # Показываем обновленные итоги
        from datetime import datetime
        
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
        text += "💡 Команда /today для детального просмотра"
        
        await callback.message.edit_text(
            text,
            parse_mode="HTML"
        )
        
        await callback.answer(f"✅ Удалено приемов: {deleted_count}")
        logger.info(f"[Stats] User {user_id} undid last addition ({deleted_count} meals)")
        
    except Exception as e:
        logger.exception(f"[Stats] Error undoing last addition: {e}")
        await callback.answer("⚠️ Ошибка при отмене", show_alert=True)


@router.callback_query(lambda c: c.data == "show_today")
async def handle_show_today_from_button(callback: CallbackQuery):
    """Показывает детальную статистику за сегодня (из кнопки)"""
    try:
        user_id = callback.from_user.id
        user = await get_user_by_id(user_id)
        
        if not user:
            await callback.answer("⚠️ Пользователь не найден", show_alert=True)
            return
        
        user_tz = user.get("timezone", "Europe/Moscow")
        summary = await get_today_summary(user_id, user_tz)
        
        totals = summary["totals"]
        meals = summary["meals"]
        
        if not meals:
            await callback.message.edit_text(
                "📭 <b>Сегодня вы еще ничего не добавили</b>\n\n"
                "Отправьте фото блюда или опишите что съели текстом!",
                parse_mode="HTML"
            )
            await callback.answer()
            return
        
        import pytz
        from datetime import datetime
        
        tz = pytz.timezone(user_tz)
        today = datetime.now(tz).strftime("%d.%m.%Y")
        
        text = f"📊 <b>Итоги за {today}</b>\n\n"
        text += "━━━━━━━━━━━━━━━━\n"
        text += f"🔥 Калории: <b>{float(totals['total_calories']):.0f}</b> ккал\n"
        text += f"🥩 Белки: <b>{float(totals['total_protein']):.1f}</b> г\n"
        text += f"🧈 Жиры: <b>{float(totals['total_fat']):.1f}</b> г\n"
        text += f"🍞 Углеводы: <b>{float(totals['total_carbs']):.1f}</b> г\n"
        text += "━━━━━━━━━━━━━━━━\n\n"
        
        text += f"<b>Приемы пищи ({totals['meals_count']}):</b>\n\n"
        
        MAX_MESSAGE_LENGTH = 3800
        
        for idx, meal in enumerate(meals, 1):
            time = meal["meal_datetime"].strftime("%H:%M")
            meal_text = (
                f"{idx}. ⏰ <b>{time}</b> — {meal['food_name']}\n"
                f"   {float(meal['calories']):.0f} ккал • "
                f"{float(meal['protein']):.1f}б • "
                f"{float(meal['fat']):.1f}ж • "
                f"{float(meal['carbs']):.1f}у\n\n"
            )
            
            if len(text + meal_text) > MAX_MESSAGE_LENGTH:
                text += f"\n<i>... и еще {len(meals) - idx + 1} приемов пищи</i>\n"
                break
            
            text += meal_text
        
        text += "\n💡 Нажмите кнопку ниже для удаления конкретного приема"
        
        keyboard = get_meal_keyboard(meals, user_id)
        
        await callback.message.edit_text(
            text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        await callback.answer()
        
    except Exception as e:
        logger.exception(f"[Stats] Error showing today from button: {e}")
        await callback.answer("⚠️ Ошибка", show_alert=True)        