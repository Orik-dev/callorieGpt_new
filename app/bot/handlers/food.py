# app/bot/handlers/food.py
import logging
import uuid
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
)
from app.services.user import get_user_by_id
from app.db.redis_client import redis
from app.utils.telegram_helpers import escape_html
import pytz
import json


logger = logging.getLogger(__name__)
router = Router()

UNDO_KEY_TTL = 1800  # 30 минут


async def safe_callback_answer(callback: CallbackQuery, text: str = None, show_alert: bool = False):
    """Безопасный ответ на callback"""
    try:
        await callback.answer(text, show_alert=show_alert)
    except TelegramBadRequest as e:
        if "query is too old" not in str(e).lower():
            logger.error(f"[Food] Callback error: {e}")


def format_date_ru(date_obj) -> str:
    """Форматирует дату по-русски"""
    months = {
        1: "января", 2: "февраля", 3: "марта", 4: "апреля",
        5: "мая", 6: "июня", 7: "июля", 8: "августа",
        9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"
    }
    if isinstance(date_obj, str):
        date_obj = datetime.fromisoformat(date_obj)
    return f"{date_obj.day} {months[date_obj.month]}"


@router.message(Command("food"))
async def cmd_food(message: Message):
    """Команда /food - рацион за сегодня"""
    user_id = message.from_user.id
    logger.info(f"[Food] /food from user {user_id}")
    
    try:
        user = await get_user_by_id(user_id)
        if not user:
            await message.answer("Пользователь не найден. /start")
            return
        
        user_tz = user.get('timezone', 'Europe/Moscow')
        history = await get_food_history(user_id, user_tz, days=7)
        
        if not history:
            await message.answer(
                "Пока нет записей.\n\n"
                "Отправь фото еды или напиши что съел.",
                parse_mode="HTML"
            )
            return
        
        today = history[0]
        tz = pytz.timezone(user_tz)
        now = datetime.now(tz)
        
        # Заголовок
        if today['date'] == now.date():
            text = f"<b>Сегодня, {format_date_ru(now)}</b>\n\n"
        else:
            text = f"<b>{format_date_ru(today['date'])}</b>\n\n"
        
        # Приёмы пищи
        if today['meals']:
            for meal in today['meals']:
                time = meal["meal_datetime"].strftime("%H:%M")
                name = escape_html(meal['food_name'][:35])
                cal = float(meal['calories'])
                p = float(meal['protein'])
                f = float(meal['fat'])
                c = float(meal['carbs'])
                
                text += f"<b>{time}</b>  {name}\n"
                text += f"        {cal:.1f} ккал · Б{p:.1f} Ж{f:.1f} У{c:.1f}\n\n"
        else:
            text += "<i>Нет приёмов пищи</i>\n\n"
        
        # Итого
        text += "─" * 24 + "\n"
        text += f"<b>Итого:</b> {float(today['total_calories']):.1f} ккал\n"
        text += f"Б {float(today['total_protein']):.1f}г · "
        text += f"Ж {float(today['total_fat']):.1f}г · "
        text += f"У {float(today['total_carbs']):.1f}г"

        # Кнопки
        buttons = []

        # Кнопки удаления для КАЖДОГО приёма (макс 10)
        if today['meals']:
            for meal in today['meals'][-10:]:
                time = meal["meal_datetime"].strftime("%H:%M")
                name = meal['food_name'][:20]
                buttons.append([
                    InlineKeyboardButton(
                        text=f"✕ {time} {name}",
                        callback_data=f"del:{meal['id']}"
                    )
                ])
        
        # Предыдущие дни
        if len(history) > 1:
            for day in history[1:4]:
                short_date = day["date"].strftime("%Y%m%d")
                date_text = format_date_ru(day["date"])
                cal = float(day['total_calories'])
                buttons.append([
                    InlineKeyboardButton(
                        text=f"{date_text} — {cal:.1f} ккал",
                        callback_data=f"day:{short_date}"
                    )
                ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        
    except Exception as e:
        logger.exception(f"[Food] Error: {e}")
        await message.answer("Ошибка. Попробуйте позже.")


@router.callback_query(F.data == "show_today")
async def callback_show_today(callback: CallbackQuery):
    """Показать приёмы за сегодня"""
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
        now = datetime.now(tz)
        
        text = f"<b>Сегодня, {format_date_ru(now)}</b>\n\n"
        
        if meals:
            for meal in meals:
                time = meal["meal_datetime"].strftime("%H:%M")
                name = escape_html(meal['food_name'][:35])
                cal = float(meal['calories'])
                text += f"{time}  {name} — {cal:.1f} ккал\n"
        else:
            text += "<i>Нет приёмов пищи</i>\n"

        text += "\n" + "─" * 24 + "\n"
        text += f"<b>Итого:</b> {float(totals['total_calories']):.1f} ккал"
        
        await callback.message.answer(text, parse_mode="HTML")
        
    except Exception as e:
        logger.exception(f"[Food] Error show_today: {e}")


@router.callback_query(F.data.startswith("day:"))
async def handle_show_day(callback: CallbackQuery):
    """Показать приёмы за конкретный день"""
    try:
        await safe_callback_answer(callback)
        
        user_id = callback.from_user.id
        short_date = callback.data.split(":")[1]
        
        if len(short_date) == 8:
            year = int(short_date[:4])
            month = int(short_date[4:6])
            day = int(short_date[6:])
        else:
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
            await callback.message.answer("Данные не найдены")
            return
        
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        text = f"<b>{format_date_ru(date_obj)}</b>\n\n"
        
        if day_data['meals']:
            for meal in day_data['meals']:
                time = meal["meal_datetime"].strftime("%H:%M")
                name = escape_html(meal['food_name'][:35])
                cal = float(meal['calories'])
                text += f"{time}  {name} — {cal:.1f} ккал\n"
        else:
            text += "<i>Нет приёмов пищи</i>\n"

        text += "\n" + "─" * 24 + "\n"
        text += f"<b>Итого:</b> {float(day_data['total_calories']):.1f} ккал\n"
        text += f"Б {float(day_data['total_protein']):.1f}г · "
        text += f"Ж {float(day_data['total_fat']):.1f}г · "
        text += f"У {float(day_data['total_carbs']):.1f}г"
        
        await callback.message.answer(text, parse_mode="HTML")
        
    except Exception as e:
        logger.exception(f"[Food] Error showing day: {e}")


@router.callback_query(F.data.startswith("del:"))
async def handle_delete_meal(callback: CallbackQuery):
    """Удаление приёма пищи"""
    try:
        user_id = callback.from_user.id
        meal_id = int(callback.data.split(":")[1])
        
        success = await delete_meal(meal_id, user_id)
        
        if not success:
            await safe_callback_answer(callback, "Не удалось удалить", show_alert=True)
            return
        
        await safe_callback_answer(callback, "Удалено")
        
        user = await get_user_by_id(user_id)
        user_tz = user.get("timezone", "Europe/Moscow")
        summary = await get_today_summary(user_id, user_tz)
        
        totals = summary["totals"]
        
        if totals["meals_count"] == 0:
            text = "Все записи удалены.\n\nОтправь фото или напиши что съел."
        else:
            text = f"<b>✓ Удалено</b>\n\nИтого за день: {float(totals['total_calories']):.1f} ккал"
        
        try:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=None)
        except TelegramBadRequest:
            pass

    except Exception as e:
        logger.exception(f"[Food] Error deleting: {e}")
        await safe_callback_answer(callback, "Ошибка", show_alert=True)


@router.callback_query(F.data.startswith("undo:"))
async def handle_undo(callback: CallbackQuery):
    """Отмена добавления"""
    try:
        user_id = callback.from_user.id
        undo_key = callback.data
        
        if f":{user_id}:" not in undo_key:
            await safe_callback_answer(callback, "Не ваша кнопка", show_alert=True)
            return
        
        data = await redis.get(undo_key)
        
        if not data:
            await safe_callback_answer(callback, "Время отмены истекло", show_alert=True)
            try:
                await callback.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
            return
        
        meal_ids = json.loads(data)
        await redis.delete(undo_key)
        
        deleted = await delete_multiple_meals(meal_ids, user_id)
        
        if deleted > 0:
            user = await get_user_by_id(user_id)
            user_tz = user.get("timezone", "Europe/Moscow")
            summary = await get_today_summary(user_id, user_tz)
            
            text = f"<b>✓ Отменено</b>\n\nИтого за день: {float(summary['totals']['total_calories']):.1f} ккал"
            try:
                await callback.message.edit_text(text, reply_markup=None, parse_mode="HTML")
            except TelegramBadRequest:
                pass
            await safe_callback_answer(callback, "Отменено")
        else:
            await safe_callback_answer(callback, "Не удалось отменить", show_alert=True)
        
    except Exception as e:
        logger.exception(f"[Food] Undo error: {e}")
        await safe_callback_answer(callback, "Ошибка", show_alert=True)


@router.callback_query(F.data.startswith("addcalc:"))
async def handle_add_calculated(callback: CallbackQuery):
    """Добавить рассчитанное в рацион"""
    try:
        user_id = callback.from_user.id
        # Ключ приходит в callback_data: "addcalc:calc:USER_ID:UUID"
        calc_key = callback.data.split(":", 1)[1]  # "calc:USER_ID:UUID"
        data = await redis.get(calc_key)

        if not data:
            await safe_callback_answer(callback, "Время истекло. Отправьте заново.", show_alert=True)
            try:
                await callback.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
            return

        items = json.loads(data)
        await redis.delete(calc_key)
        
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except:
            pass
        
        await safe_callback_answer(callback, "Добавляю...")
        
        user = await get_user_by_id(user_id)
        user_tz = user.get("timezone", "Europe/Moscow")
        
        from app.services.meals import save_meals
        
        result = await save_meals(user_id, {"items": items, "notes": ""}, user_tz, None)
        added_ids = result.get('added_meal_ids', [])
        
        summary = await get_today_summary(user_id, user_tz)
        totals = summary["totals"]
        
        tz = pytz.timezone(user_tz)
        date_str = format_date_ru(datetime.now(tz))
        
        lines = ["<b>✓ Добавлено</b>\n"]
        for meal in items:
            name = escape_html(meal.get('name', 'Блюдо'))
            weight = meal.get('weight_grams', 0)
            cal = float(meal.get('calories', 0))
            p = float(meal.get('protein', 0))
            f = float(meal.get('fat', 0))
            c = float(meal.get('carbs', 0))
            lines.append(f"<b>{name}</b>\n{weight}г · {cal:.1f} ккал · Б{p:.1f} Ж{f:.1f} У{c:.1f}")
        
        lines.append("")
        lines.append("─" * 20)
        lines.append(f"<b>Итого за {date_str}:</b> {float(totals['total_calories']):.1f} ккал")
        lines.append(f"Б {float(totals['total_protein']):.1f}г · Ж {float(totals['total_fat']):.1f}г · У {float(totals['total_carbs']):.1f}г")
        
        buttons = []
        if added_ids:
            undo_key = f"undo:{user_id}:{uuid.uuid4().hex[:8]}"
            await redis.setex(undo_key, UNDO_KEY_TTL, json.dumps(added_ids))
            buttons.append([InlineKeyboardButton(text="Отменить", callback_data=undo_key)])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
        try:
            await callback.message.edit_text("\n".join(lines), reply_markup=keyboard, parse_mode="HTML")
        except TelegramBadRequest:
            pass

    except Exception as e:
        logger.exception(f"[Food] Add calculated error: {e}")
        await safe_callback_answer(callback, "Ошибка", show_alert=True)


@router.callback_query(F.data.startswith("delall:"))
async def handle_confirm_delete_all(callback: CallbackQuery):
    """Подтверждение удаления всех записей за день"""
    try:
        user_id = callback.from_user.id
        confirm_key = callback.data

        if f":{user_id}:" not in confirm_key:
            await safe_callback_answer(callback, "Не ваша кнопка", show_alert=True)
            return

        data = await redis.get(confirm_key)

        if not data:
            await safe_callback_answer(callback, "Время истекло", show_alert=True)
            try:
                await callback.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
            return

        meal_ids = json.loads(data)
        await redis.delete(confirm_key)

        deleted = await delete_multiple_meals(meal_ids, user_id)

        text = f"<b>✓ Удалено записей: {deleted}</b>\nРацион за сегодня очищен."
        try:
            await callback.message.edit_text(text, reply_markup=None, parse_mode="HTML")
        except TelegramBadRequest:
            pass
        await safe_callback_answer(callback, "Удалено")

    except Exception as e:
        logger.exception(f"[Food] Delete all error: {e}")
        await safe_callback_answer(callback, "Ошибка", show_alert=True)


@router.callback_query(F.data == "canceldelall")
async def handle_cancel_delete_all(callback: CallbackQuery):
    """Отмена удаления всех записей"""
    try:
        await callback.message.edit_text(
            "<b>Отменено</b>\nЗаписи не удалены.",
            reply_markup=None,
            parse_mode="HTML"
        )
        await safe_callback_answer(callback, "Отменено")
    except Exception as e:
        logger.exception(f"[Food] Cancel delete all error: {e}")
        await safe_callback_answer(callback, "Ошибка", show_alert=True)