from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from app.services.user import get_user_by_id
from app.services.meals import get_today_summary, get_week_summary, get_nutrition_stats
from datetime import datetime
import pytz
import logging

router = Router()
logger = logging.getLogger(__name__)


@router.message(Command("today"))
async def show_today(message: Message):
    """Показывает детальную статистику за сегодня"""
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
        
        # Формируем ответ
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
        
        for idx, meal in enumerate(meals, 1):
            time = meal["meal_datetime"].strftime("%H:%M")
            text += f"{idx}. ⏰ <b>{time}</b> — {meal['food_name']}\n"
            text += (
                f"   {float(meal['calories']):.0f} ккал • "
                f"{float(meal['protein']):.1f}б • "
                f"{float(meal['fat']):.1f}ж • "
                f"{float(meal['carbs']):.1f}у\n\n"
            )
        
        await message.answer(text, parse_mode="HTML")
        logger.info(f"[Stats] User {user_id} viewed today stats")
        
    except Exception as e:
        logger.exception(f"[Stats] Error in /today for user {message.from_user.id}: {e}")
        await message.answer("⚠️ Ошибка при получении статистики.")


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
        
        # Названия дней недели на русском
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


@router.message(Command("stats"))
async def show_stats_menu(message: Message):
    """Показывает меню выбора периода статистики"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Сегодня", callback_data="stats:today")],
        [InlineKeyboardButton(text="📈 Неделя", callback_data="stats:week")],
        [InlineKeyboardButton(text="📊 Месяц", callback_data="stats:month")],
    ])
    
    await message.answer(
        "📊 <b>Статистика питания</b>\n\nВыберите период:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


@router.callback_query(lambda c: c.data and c.data.startswith("stats:"))
async def handle_stats_callback(callback: CallbackQuery):
    """Обработка выбора периода статистики"""
    try:
        user_id = callback.from_user.id
        period = callback.data.split(":", 1)[1]
        
        user = await get_user_by_id(user_id)
        if not user:
            await callback.answer("⚠️ Пользователь не найден", show_alert=True)
            return
        
        user_tz = user.get("timezone", "Europe/Moscow")
        
        if period == "today":
            # Перенаправляем на /today
            summary = await get_today_summary(user_id, user_tz)
            totals = summary["totals"]
            meals = summary["meals"]
            
            if not meals:
                await callback.message.edit_text(
                    "📭 <b>Сегодня вы еще ничего не добавили</b>",
                    parse_mode="HTML"
                )
                await callback.answer()
                return
            
            tz = pytz.timezone(user_tz)
            today = datetime.now(tz).strftime("%d.%m.%Y")
            
            text = f"📊 <b>Итоги за {today}</b>\n\n"
            text += f"🔥 {float(totals['total_calories']):.0f} ккал\n"
            text += f"🥩 {float(totals['total_protein']):.1f}г белка\n"
            text += f"🧈 {float(totals['total_fat']):.1f}г жиров\n"
            text += f"🍞 {float(totals['total_carbs']):.1f}г углеводов\n"
            text += f"🍽 {totals['meals_count']} приемов пищи"
            
        elif period == "week":
            stats = await get_nutrition_stats(user_id, days=7)
            if not stats or stats.get("days_tracked", 0) == 0:
                await callback.message.edit_text(
                    "📭 <b>За неделю нет данных</b>",
                    parse_mode="HTML"
                )
                await callback.answer()
                return
            
            text = "📈 <b>Статистика за неделю</b>\n\n"
            text += f"📊 Дней с данными: {stats['days_tracked']}/7\n\n"
            text += f"Среднее в день:\n"
            text += f"🔥 {stats['avg_calories']:.0f} ккал\n"
            text += f"🥩 {stats['avg_protein']:.1f}г белка\n"
            text += f"🧈 {stats['avg_fat']:.1f}г жиров\n"
            text += f"🍞 {stats['avg_carbs']:.1f}г углеводов\n\n"
            text += f"🍽 Всего приемов: {stats['total_meals']}"
            
        elif period == "month":
            stats = await get_nutrition_stats(user_id, days=30)
            if not stats or stats.get("days_tracked", 0) == 0:
                await callback.message.edit_text(
                    "📭 <b>За месяц нет данных</b>",
                    parse_mode="HTML"
                )
                await callback.answer()
                return
            
            text = "📊 <b>Статистика за месяц</b>\n\n"
            text += f"📊 Дней с данными: {stats['days_tracked']}/30\n\n"
            text += f"Среднее в день:\n"
            text += f"🔥 {stats['avg_calories']:.0f} ккал\n"
            text += f"🥩 {stats['avg_protein']:.1f}г белка\n"
            text += f"🧈 {stats['avg_fat']:.1f}г жиров\n"
            text += f"🍞 {stats['avg_carbs']:.1f}г углеводов\n\n"
            text += f"🍽 Всего приемов: {stats['total_meals']}"
        else:
            await callback.answer("⚠️ Неизвестный период", show_alert=True)
            return
        
        await callback.message.edit_text(text, parse_mode="HTML")
        await callback.answer()
        
    except Exception as e:
        logger.exception(f"[Stats] Error in callback for user {callback.from_user.id}: {e}")
        await callback.answer("⚠️ Ошибка", show_alert=True)