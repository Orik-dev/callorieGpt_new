# app/bot/handlers/food.py
import logging
import uuid
from datetime import datetime, timedelta
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
)
from app.services.user import get_user_by_id
from app.db.redis_client import redis
from app.utils.telegram_helpers import safe_send_message, safe_edit_message, safe_delete_message
import pytz
import json

logger = logging.getLogger(__name__)
router = Router()

# Время жизни ключа отмены в Redis (60 секунд)
UNDO_KEY_TTL = 60


async def save_undo_data(meal_ids: list, user_id: int) -> str:
    """
    Сохраняет meal_ids в Redis и возвращает короткий ключ.
    Решает проблему callback_data > 64 байт.
    """
    key = f"undo:{user_id}:{uuid.uuid4().hex[:8]}"
    await redis.setex(key, UNDO_KEY_TTL, json.dumps(meal_ids))
    return key


async def get_undo_data(key: str) -> list:
    """Получает meal_ids из Redis по ключу"""
    data = await redis.get(key)
    if data:
        await redis.delete(key)
        return json.loads(data)
    return []


async def safe_callback_answer(callback: CallbackQuery, text: str = None, show_alert: bool = False):
    """Безопасный ответ на callback"""
    try:
        await callback.answer(text, show_alert=show_alert)
    except TelegramBadRequest as e:
        if "query is too old" not in str(e).lower():
            logger.error(f"[Food] Callback answer error: {e}")


@router.message(Command("food"))
async def cmd_food(message: Message):
    """Команда /food - история питания за 7 дней"""
    user_id = message.from_user.id
    logger.info(f"[Food] /food from user {user_id}")
    
    try:
        user = await get_user_by_id(user_id)
        if not user:
            await message.answer("❌ Пользователь не найден. /start")
            return
        
        user_tz = user.get('timezone', 'Europe/Moscow')
        history = await get_food_history(user_id, user_tz, days=7)
        
        if not history:
            await message.answer(
                "📭 <b>Пока нет записей о еде</b>\n\n"
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
        
        # Кнопки удаления для каждого приема (только сегодня)
        if today['meals']:
            for meal in today['meals'][-8:]:  # Макс 8 кнопок
                meal_time = meal["meal_datetime"].strftime("%H:%M")
                meal_name = meal['food_name'][:18]
                # ✅ ИСПРАВЛЕНИЕ: Короткий callback_data
                buttons.append([
                    InlineKeyboardButton(
                        text=f"🗑 {meal_time} {meal_name}",
                        callback_data=f"del:{meal['id']}"
                    )
                ])
        
        # Кнопки для предыдущих дней
        if len(history) > 1:
            text += "━━━━━━━━━━━━━━━━\n📅 <b>Предыдущие дни:</b>\n"
            for day in history[1:4]:  # Макс 3 дня
                date_str = day["date"].isoformat()
                # ✅ Короткий формат даты в callback
                short_date = day["date"].strftime("%m%d")
                buttons.append([
                    InlineKeyboardButton(
                        text=f"📋 {day['date_formatted']}: {float(day['total_calories']):.0f} ккал",
                        callback_data=f"day:{short_date}"
                    )
                ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        
    except Exception as e:
        logger.exception(f"[Food] Error in /food for user {user_id}: {e}")
        await message.answer("❌ Ошибка. Попробуйте позже.")


@router.callback_query(F.data == "show_today")
async def callback_show_today(callback: CallbackQuery):
    """Показать приемы за сегодня"""
    await safe_callback_answer(callback)
    
    user_id = callback.from_user.id
    
    try:
        user = await get_user_by_id(user_id)
        if not user:
            return
        
        user_tz = user.get('timezone', 'Europe/Moscow')
        summary = await get_today_summary(user_id, user_tz)
        
        totals = summary["totals"]
        meals = summary["meals"]
        
        tz = pytz.timezone(user_tz)
        today = datetime.now(tz).strftime("%d.%m.%Y")
        
        text = f"📊 <b>Сегодня, {today}</b>\n\n"
        text += "━━━━━━━━━━━━━━━━\n"
        text += f"🔥 {float(totals['total_calories']):.0f} ккал\n"
        text += f"🥩 {float(totals['total_protein']):.1f}г • "
        text += f"🧈 {float(totals['total_fat']):.1f}г • "
        text += f"🍞 {float(totals['total_carbs']):.1f}г\n\n"
        
        if meals:
            for idx, meal in enumerate(meals, 1):
                time = meal["meal_datetime"].strftime("%H:%M")
                text += f"{idx}. {time} — {meal['food_name']}\n"
        else:
            text += "<i>Пока нет приемов пищи</i>\n"
        
        text += "\n💡 /food для полной истории"
        
        await callback.message.answer(text, parse_mode="HTML")
        
    except Exception as e:
        logger.exception(f"[Food] Error show_today: {e}")


@router.callback_query(F.data.startswith("day:"))
async def handle_show_day(callback: CallbackQuery):
    """Показать приемы за конкретный день"""
    try:
        await safe_callback_answer(callback)
        
        user_id = callback.from_user.id
        short_date = callback.data.split(":")[1]  # MMDD
        
        # Восстанавливаем полную дату
        year = datetime.now().year
        month = int(short_date[:2])
        day = int(short_date[2:])
        date_str = f"{year}-{month:02d}-{day:02d}"
        
        user = await get_user_by_id(user_id)
        if not user:
            return
        
        user_tz = user.get("timezone", "Europe/Moscow")
        day_data = await get_day_meals(user_id, date_str, user_tz)
        
        if not day_data:
            await callback.message.answer("⚠️ Данные не найдены")
            return
        
        text = f"📅 <b>{day_data['date_formatted']}</b>\n"
        text += "━━━━━━━━━━━━━━━━\n"
        text += f"🔥 {float(day_data['total_calories']):.0f} ккал\n"
        text += f"🥩 {float(day_data['total_protein']):.1f}г • "
        text += f"🧈 {float(day_data['total_fat']):.1f}г • "
        text += f"🍞 {float(day_data['total_carbs']):.1f}г\n\n"
        
        if day_data['meals']:
            for idx, meal in enumerate(day_data['meals'], 1):
                time = meal["meal_datetime"].strftime("%H:%M")
                text += f"{idx}. {time} — {meal['food_name']}\n"
        else:
            text += "<i>Нет приемов пищи</i>"
        
        await callback.message.answer(text, parse_mode="HTML")
        
    except Exception as e:
        logger.exception(f"[Food] Error showing day: {e}")


@router.callback_query(F.data.startswith("del:"))
async def handle_delete_meal(callback: CallbackQuery):
    """Удаление одного приема пищи"""
    try:
        user_id = callback.from_user.id
        meal_id = int(callback.data.split(":")[1])
        
        success = await delete_meal(meal_id, user_id)
        
        if not success:
            await safe_callback_answer(callback, "⚠️ Не удалось удалить", show_alert=True)
            return
        
        await safe_callback_answer(callback, "✅ Удалено")
        
        # Обновляем сообщение
        user = await get_user_by_id(user_id)
        user_tz = user.get("timezone", "Europe/Moscow")
        summary = await get_today_summary(user_id, user_tz)
        
        totals = summary["totals"]
        
        if totals["meals_count"] == 0:
            await callback.message.edit_text(
                "📭 <b>Все приемы удалены</b>\n\n"
                "Отправьте фото блюда или опишите что съели!",
                parse_mode="HTML"
            )
        else:
            text = f"✅ <b>Удалено</b>\n\n"
            text += f"🔥 Осталось: {float(totals['total_calories']):.0f} ккал\n"
            text += f"🍽 Приемов: {totals['meals_count']}\n\n"
            text += "💡 /food для полной истории"
            
            await callback.message.edit_text(text, parse_mode="HTML")
        
    except Exception as e:
        logger.exception(f"[Food] Error deleting meal: {e}")
        await safe_callback_answer(callback, "⚠️ Ошибка", show_alert=True)


@router.callback_query(F.data.startswith("undo:"))
async def handle_undo_last(callback: CallbackQuery):
    """Отмена последнего добавления"""
    try:
        user_id = callback.from_user.id
        undo_key = callback.data  # Полный ключ: undo:user_id:hash
        
        meal_ids = await get_undo_data(undo_key)
        
        if not meal_ids:
            await safe_callback_answer(callback, "⏰ Время отмены истекло", show_alert=True)
            # Убираем кнопку
            try:
                await callback.message.edit_reply_markup(reply_markup=None)
            except:
                pass
            return
        
        deleted_count = await delete_multiple_meals(meal_ids, user_id)
        
        if deleted_count == 0:
            await safe_callback_answer(callback, "⚠️ Не удалось отменить", show_alert=True)
            return
        
        await safe_callback_answer(callback, f"✅ Отменено: {deleted_count}")
        
        # Обновляем сообщение
        user = await get_user_by_id(user_id)
        user_tz = user.get("timezone", "Europe/Moscow")
        summary = await get_today_summary(user_id, user_tz)
        
        totals = summary["totals"]
        
        text = f"✅ <b>Добавление отменено</b>\n\n"
        text += f"🔥 Итого за сегодня: {float(totals['total_calories']):.0f} ккал\n"
        text += f"🍽 Приемов: {totals['meals_count']}\n\n"
        text += "💡 /food для просмотра истории"
        
        await callback.message.edit_text(text, parse_mode="HTML")
        
    except Exception as e:
        logger.exception(f"[Food] Error undoing: {e}")
        await safe_callback_answer(callback, "⚠️ Ошибка", show_alert=True)