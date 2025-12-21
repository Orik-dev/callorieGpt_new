# app/tasks/gpt_queue.py
"""
Универсальная обработка запросов к GPT.
GPT сам определяет intent и возвращает структурированный ответ.
"""
import logging
import json
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from app.api.gpt import ai_request
from app.services.user import get_user_by_id
from app.services.meals import (
    parse_gpt_response,
    save_meals,
    get_today_summary,
    get_last_meal,
    get_today_meals,
    update_meal,
    delete_meal,
    delete_multiple_meals,
    MealParseError
)
from app.db.mysql import mysql
from app.db.redis_client import redis
from app.bot.bot import bot
from app.utils.telegram_helpers import safe_send_message, safe_delete_message, escape_html
import pytz
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)

# TTL для ключа отмены
UNDO_KEY_TTL = 60


async def refund_token(user_id: int):
    """Возвращает токен при ошибке"""
    async with mysql.pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE users_tbl SET free_tokens = free_tokens + 1 WHERE tg_id = %s",
                (user_id,)
            )
    logger.info(f"[GPT Queue] Token refunded for user {user_id}")


async def get_meals_context(user_id: int, user_tz: str) -> str:
    """Получает контекст последних приемов пищи для GPT"""
    try:
        meals = await get_today_meals(user_id, user_tz, limit=5)
        if not meals:
            return ""
        
        context_lines = []
        for meal in meals:
            time = meal["meal_datetime"].strftime("%H:%M")
            context_lines.append(
                f"- {time}: {meal['food_name']} "
                f"({meal['calories']} ккал, {meal['weight_grams']}г)"
            )
        
        return "\n".join(context_lines)
    except:
        return ""


async def save_undo_data(meal_ids: list, user_id: int) -> str:
    """Сохраняет meal_ids в Redis для кнопки отмены"""
    key = f"undo:{user_id}:{uuid.uuid4().hex[:8]}"
    await redis.setex(key, UNDO_KEY_TTL, json.dumps(meal_ids))
    return key


async def process_universal_request(
    ctx,
    user_id: int,
    chat_id: int,
    message_id: int,
    text: str,
    image_url: str = None
):
    """
    Универсальная обработка запроса.
    GPT определяет intent и возвращает данные.
    """
    logger.info(f"[GPT Queue] Processing for user {user_id}: {text[:50]}...")
    
    try:
        user = await get_user_by_id(user_id)
        if not user:
            logger.error(f"[GPT Queue] User {user_id} not found")
            await safe_delete_message(bot, chat_id, message_id)
            return
        
        user_tz = user.get('timezone', 'Europe/Moscow')
        
        # Получаем контекст последних приемов
        context = await get_meals_context(user_id, user_tz)
        
        # Запрос к GPT
        code, gpt_response = await ai_request(
            user_id=user_id,
            text=text,
            image_link=image_url,
            context=context
        )
        
        # Обработка ошибок API
        if code == 429 and gpt_response == "QUOTA_EXCEEDED":
            await safe_delete_message(bot, chat_id, message_id)
            await safe_send_message(
                bot, chat_id,
                "⚠️ Сервис временно недоступен.\n"
                "Попробуйте через несколько минут."
            )
            await refund_token(user_id)
            return
        
        if code != 200 or not gpt_response:
            logger.error(f"[GPT Queue] Empty response for user {user_id}, code={code}")
            await safe_delete_message(bot, chat_id, message_id)
            await safe_send_message(
                bot, chat_id,
                "❌ Не удалось обработать запрос. Попробуйте еще раз."
            )
            await refund_token(user_id)
            return
        
        # Парсим ответ
        try:
            data = json.loads(gpt_response)
        except json.JSONDecodeError as e:
            logger.error(f"[GPT Queue] JSON parse error: {e}")
            await safe_delete_message(bot, chat_id, message_id)
            await safe_send_message(
                bot, chat_id,
                "❌ Ошибка обработки. Попробуйте переформулировать."
            )
            await refund_token(user_id)
            return
        
        intent = data.get("intent", "add")
        items = data.get("items", [])
        notes = data.get("notes", "")
        
        logger.info(f"[GPT Queue] User {user_id}: intent={intent}, items={len(items)}")
        
        # Обработка по intent
        if intent == "unknown":
            await safe_delete_message(bot, chat_id, message_id)
            msg = notes or "Я не понял запрос. Отправьте фото еды или опишите блюдо."
            await safe_send_message(bot, chat_id, f"🤔 {msg}")
            await refund_token(user_id)
            return
        
        if intent == "calculate":
            await handle_calculate(chat_id, message_id, items, notes)
            return
        
        if intent == "delete":
            await handle_delete(user_id, chat_id, message_id, data, user_tz)
            return
        
        if intent == "edit":
            await handle_edit(user_id, chat_id, message_id, data, user_tz)
            return
        
        # intent == "add" (по умолчанию)
        if not items:
            await safe_delete_message(bot, chat_id, message_id)
            await safe_send_message(
                bot, chat_id,
                f"❌ {notes or 'Не удалось распознать блюдо. Попробуйте описать подробнее.'}"
            )
            await refund_token(user_id)
            return
        
        await handle_add(user_id, chat_id, message_id, items, notes, user_tz, image_url)
        
    except Exception as e:
        logger.exception(f"[GPT Queue] Unexpected error for user {user_id}: {e}")
        try:
            await safe_delete_message(bot, chat_id, message_id)
            await safe_send_message(
                bot, chat_id,
                "❌ Произошла ошибка. Попробуйте еще раз."
            )
        except:
            pass
        await refund_token(user_id)


async def handle_add(
    user_id: int,
    chat_id: int,
    message_id: int,
    items: list,
    notes: str,
    user_tz: str,
    image_url: str = None
):
    """Добавление блюд в рацион"""
    try:
        parsed_data = {"items": items, "notes": notes}
        result = await save_meals(user_id, parsed_data, user_tz, image_url)
        added_meal_ids = result.get('added_meal_ids', [])
        
        logger.info(f"[GPT Queue] Saved meals for user {user_id}, IDs: {added_meal_ids}")
        
        summary = await get_today_summary(user_id, user_tz)
        totals = summary["totals"]
        
        tz = pytz.timezone(user_tz)
        today = datetime.now(tz).strftime("%d.%m.%Y")
        
        text = "✅ <b>Добавлено:</b>\n\n"
        
        for meal in items:
            name = escape_html(meal.get('name', 'Блюдо'))
            text += f"🍽 <b>{name}</b>\n"
            text += f"   {meal.get('weight_grams', 0)}г • "
            text += f"{meal.get('calories', 0)} ккал • "
            text += f"{meal.get('protein', 0)}б • "
            text += f"{meal.get('fat', 0)}ж • "
            text += f"{meal.get('carbs', 0)}у\n\n"
        
        if notes:
            text += f"💡 {escape_html(notes)}\n\n"
        
        text += "━━━━━━━━━━━━━━━━\n"
        text += f"📊 <b>Итого за {today}:</b>\n"
        text += f"🔥 {float(totals['total_calories']):.0f} ккал • "
        text += f"🍽 {totals['meals_count']} приемов\n"
        text += "━━━━━━━━━━━━━━━━"
        
        buttons = []
        
        # Кнопка отмены (сохраняем в Redis)
        if added_meal_ids:
            undo_key = await save_undo_data(added_meal_ids, user_id)
            buttons.append([
                InlineKeyboardButton(
                    text="🗑 Отменить",
                    callback_data=undo_key  # Короткий ключ!
                )
            ])
        
        buttons.append([
            InlineKeyboardButton(
                text="📋 Все приемы",
                callback_data="show_today"
            )
        ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        await safe_delete_message(bot, chat_id, message_id)
        await safe_send_message(bot, chat_id, text, keyboard)
        
    except Exception as e:
        logger.exception(f"[GPT Queue] Error in handle_add: {e}")
        await safe_delete_message(bot, chat_id, message_id)
        await safe_send_message(bot, chat_id, "❌ Ошибка сохранения.")
        await refund_token(user_id)


async def handle_calculate(
    chat_id: int,
    message_id: int,
    items: list,
    notes: str
):
    """Только расчет калорий (без добавления)"""
    if not items:
        await safe_delete_message(bot, chat_id, message_id)
        await safe_send_message(bot, chat_id, "❌ Не удалось определить блюдо.")
        return
    
    total_cal = sum(m.get('calories', 0) for m in items)
    total_protein = sum(m.get('protein', 0) for m in items)
    total_fat = sum(m.get('fat', 0) for m in items)
    total_carbs = sum(m.get('carbs', 0) for m in items)
    
    text = "🔢 <b>Расчет калорийности:</b>\n\n"
    
    for meal in items:
        name = escape_html(meal.get('name', 'Блюдо'))
        text += f"🍽 <b>{name}</b>\n"
        text += f"   {meal.get('weight_grams', 0)}г • "
        text += f"{meal.get('calories', 0)} ккал • "
        text += f"{meal.get('protein', 0)}б • "
        text += f"{meal.get('fat', 0)}ж • "
        text += f"{meal.get('carbs', 0)}у\n\n"
    
    text += "━━━━━━━━━━━━━━━━\n"
    text += f"📊 <b>ИТОГО:</b> {total_cal} ккал\n"
    text += f"🥩 {total_protein}г • 🧈 {total_fat}г • 🍞 {total_carbs}г\n"
    text += "━━━━━━━━━━━━━━━━\n\n"
    
    if notes:
        text += f"💡 {escape_html(notes)}\n\n"
    
    text += "<i>ℹ️ Это расчет. Данные НЕ добавлены в рацион.</i>\n"
    text += "Чтобы добавить — просто скажите что съели."
    
    await safe_delete_message(bot, chat_id, message_id)
    await safe_send_message(bot, chat_id, text)


async def handle_delete(
    user_id: int,
    chat_id: int,
    message_id: int,
    data: dict,
    user_tz: str
):
    """Удаление приемов пищи"""
    try:
        delete_target = data.get("delete_target", "last")
        
        if delete_target == "all":
            summary = await get_today_summary(user_id, user_tz)
            meals = summary.get("meals", [])
            
            if not meals:
                await safe_delete_message(bot, chat_id, message_id)
                await safe_send_message(bot, chat_id, "📭 Нечего удалять — сегодня нет приемов.")
                await refund_token(user_id)
                return
            
            meal_ids = [m['id'] for m in meals]
            deleted = await delete_multiple_meals(meal_ids, user_id)
            
            await safe_delete_message(bot, chat_id, message_id)
            await safe_send_message(
                bot, chat_id,
                f"✅ Удалено приемов: <b>{deleted}</b>\n\nРацион очищен."
            )
            return
        
        if delete_target == "last":
            last_meal = await get_last_meal(user_id, user_tz)
            
            if not last_meal:
                await safe_delete_message(bot, chat_id, message_id)
                await safe_send_message(bot, chat_id, "📭 Нечего удалять.")
                await refund_token(user_id)
                return
            
            success = await delete_meal(last_meal['id'], user_id)
            
            if success:
                summary = await get_today_summary(user_id, user_tz)
                totals = summary["totals"]
                
                text = f"✅ <b>Удалено:</b> {escape_html(last_meal['food_name'])}\n\n"
                text += f"🔥 Осталось: {float(totals['total_calories']):.0f} ккал"
                
                await safe_delete_message(bot, chat_id, message_id)
                await safe_send_message(bot, chat_id, text)
            else:
                await safe_delete_message(bot, chat_id, message_id)
                await safe_send_message(bot, chat_id, "❌ Не удалось удалить.")
            return
        
        # Удаление по названию
        summary = await get_today_summary(user_id, user_tz)
        meals = summary.get("meals", [])
        
        if not meals:
            await safe_delete_message(bot, chat_id, message_id)
            await safe_send_message(bot, chat_id, "📭 Сегодня нет приемов пищи.")
            await refund_token(user_id)
            return
        
        target_lower = delete_target.lower()
        meal_to_delete = None
        
        for meal in reversed(meals):
            if target_lower in meal['food_name'].lower():
                meal_to_delete = meal
                break
        
        if meal_to_delete:
            success = await delete_meal(meal_to_delete['id'], user_id)
            if success:
                summary = await get_today_summary(user_id, user_tz)
                totals = summary["totals"]
                
                text = f"✅ <b>Удалено:</b> {escape_html(meal_to_delete['food_name'])}\n\n"
                text += f"🔥 Осталось: {float(totals['total_calories']):.0f} ккал"
                
                await safe_delete_message(bot, chat_id, message_id)
                await safe_send_message(bot, chat_id, text)
            else:
                await safe_delete_message(bot, chat_id, message_id)
                await safe_send_message(bot, chat_id, "❌ Не удалось удалить.")
        else:
            text = "❓ <b>Не нашел такое блюдо</b>\n\nСегодня:\n"
            for meal in meals[-5:]:
                time = meal["meal_datetime"].strftime("%H:%M")
                text += f"• {time} — {escape_html(meal['food_name'])}\n"
            
            await safe_delete_message(bot, chat_id, message_id)
            await safe_send_message(bot, chat_id, text)
            await refund_token(user_id)
            
    except Exception as e:
        logger.exception(f"[GPT Queue] Error in handle_delete: {e}")
        await safe_delete_message(bot, chat_id, message_id)
        await safe_send_message(bot, chat_id, "❌ Ошибка удаления.")
        await refund_token(user_id)


async def handle_edit(
    user_id: int,
    chat_id: int,
    message_id: int,
    data: dict,
    user_tz: str
):
    """Редактирование последнего приема пищи"""
    try:
        last_meal = await get_last_meal(user_id, user_tz)
        
        if not last_meal:
            await safe_delete_message(bot, chat_id, message_id)
            await safe_send_message(
                bot, chat_id,
                "❌ Нет приемов для редактирования.\nСначала добавьте блюдо."
            )
            await refund_token(user_id)
            return
        
        items = data.get("items", [])
        edit_instruction = data.get("edit_instruction", "")
        
        # Если GPT вернул готовые данные
        if items and len(items) > 0:
            new_data = items[0]
            await update_meal(
                meal_id=last_meal['id'],
                user_id=user_id,
                food_name=new_data.get('name', last_meal['food_name']),
                weight_grams=new_data.get('weight_grams', last_meal['weight_grams']),
                calories=new_data.get('calories', last_meal['calories']),
                protein=new_data.get('protein', last_meal['protein']),
                fat=new_data.get('fat', last_meal['fat']),
                carbs=new_data.get('carbs', last_meal['carbs'])
            )
            
            summary = await get_today_summary(user_id, user_tz)
            totals = summary["totals"]
            
            name = escape_html(new_data.get('name', last_meal['food_name']))
            text = f"✅ <b>Обновлено:</b> {name}\n\n"
            text += f"🍽 {new_data.get('weight_grams', 0)}г • "
            text += f"{new_data.get('calories', 0)} ккал • "
            text += f"{new_data.get('protein', 0)}б • "
            text += f"{new_data.get('fat', 0)}ж • "
            text += f"{new_data.get('carbs', 0)}у\n\n"
            text += "━━━━━━━━━━━━━━━━\n"
            text += f"🔥 Итого: {float(totals['total_calories']):.0f} ккал"
            
            await safe_delete_message(bot, chat_id, message_id)
            await safe_send_message(bot, chat_id, text)
        else:
            # GPT не смог обработать — просим уточнить
            await safe_delete_message(bot, chat_id, message_id)
            await safe_send_message(
                bot, chat_id,
                "🤔 Не понял, что изменить.\n\n"
                "<b>Примеры:</b>\n"
                "• \"там было 150г, не 200\"\n"
                "• \"сделай менее жирным\"\n"
                "• \"добавь масло\"\n\n"
                "Или опишите блюдо заново."
            )
            await refund_token(user_id)
            
    except Exception as e:
        logger.exception(f"[GPT Queue] Error in handle_edit: {e}")
        await safe_delete_message(bot, chat_id, message_id)
        await safe_send_message(bot, chat_id, "❌ Ошибка редактирования.")
        await refund_token(user_id)