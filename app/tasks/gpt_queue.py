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
    
    meal_key = str(uuid.uuid4())[:12]
    redis_key = f"pending_meal:{user_id}:{meal_key}"
    
    data_to_save = {
        "parsed_data": parsed_data,
        "user_tz": user_tz
    }
    
    await redis.set(redis_key, json.dumps(data_to_save, ensure_ascii=False), ex=3600)
    
    logger.info(f"[GPT Queue] Saved pending meal for user {user_id}, key={meal_key}")
    return meal_key


async def process_gpt_request(ctx, user_id: int, chat_id: int, message_id: int, text: str, image_url: str = None):
    """
    Обработка запроса к GPT для расчета калорий
    Теперь НЕ сохраняет сразу в БД, а показывает preview с кнопками
    """
    logger.info(f"[GPT Queue] Processing request for user {user_id}")
    
    try:
        user = await get_user_by_id(user_id)
        if not user:
            logger.error(f"[GPT Queue] User {user_id} not found")
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
            await bot.send_message(
                chat_id=chat_id,
                text=f"❌ Ошибка обработки: {str(e)}\n\nПопробуйте переформулировать запрос.",
                parse_mode="HTML"
            )
            await refund_token(user_id)
            return
        
        meal_key = await save_pending_meal(user_id, parsed_data, user_tz)
        
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
    
    ✅ ЗАЩИТА ОТ ДУБЛИРОВАНИЯ:
    - Atomic lock в Redis
    - getdel для атомарного получения и удаления
    """
    logger.info(f"[GPT Queue] Confirming meal for user {user_id}, key={meal_key}")
    
    from app.db.redis_client import redis
    
    # ✅ ЗАЩИТА 2: Блокировка в Redis
    lock_key = f"lock:meal:{user_id}:{meal_key}"
    locked = await redis.set(lock_key, "1", ex=30, nx=True)
    
    if not locked:
        logger.warning(f"[GPT Queue] Meal {meal_key} already being processed by another task")
        return  # Другая задача уже обрабатывает
    
    try:
        # ✅ ЗАЩИТА 3: Атомарное получение и удаление (getdel)
        redis_key = f"pending_meal:{user_id}:{meal_key}"
        
        # Redis >= 6.2.0 поддерживает GETDEL
        data = await redis.getdel(redis_key)
        
        if not data:
            logger.warning(f"[GPT Queue] Pending meal {meal_key} not found (already processed)")
            await bot.edit_message_text(
                chat_id=user_id,
                message_id=message_id,
                text="❌ Данные устарели или уже были обработаны.",
                parse_mode="HTML"
            )
            return
        
        pending_data = json.loads(data)
        parsed_data = pending_data['parsed_data']
        user_tz = pending_data['user_tz']
        
        # Сохраняем в БД
        await save_meals(user_id, parsed_data, user_tz)
        logger.info(f"[GPT Queue] Saved meals for user {user_id}")
        
        # Получаем итоги за день
        summary = await get_today_summary(user_id, user_tz)
        totals = summary["totals"]
        
        items = parsed_data.get('items', [])
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
        message_text += f"🔥 {float(totals['total_calories']):.0f} ккал\n"
        message_text += f"🥩 Белки: {float(totals['total_protein']):.1f} г\n"
        message_text += f"🧈 Жиры: {float(totals['total_fat']):.1f} г\n"
        message_text += f"🍞 Углеводы: {float(totals['total_carbs']):.1f} г\n"
        message_text += f"🍽 Приемов пищи: {totals['meals_count']}\n"
        message_text += "━━━━━━━━━━━━━━━━"
        
        # Получаем ID добавленных блюд для кнопки отмены
        meal_ids = [str(meal.get('id', '')) for meal in summary.get('meals', [])[-len(items):] if meal.get('id')]
        meal_ids_str = ','.join(meal_ids) if meal_ids else ''
        
        # Кнопки
        buttons = []
        if meal_ids_str:
            buttons.append([
                InlineKeyboardButton(
                    text="🗑 Отменить добавление",
                    callback_data=f"undo_last:{meal_ids_str}"
                )
            ])
        buttons.append([
            InlineKeyboardButton(
                text="📋 Все приемы за день",
                callback_data="show_today"
            )
        ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        await bot.edit_message_text(
            chat_id=user_id,
            message_id=message_id,
            text=message_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"[GPT Queue] Successfully confirmed meal for user {user_id}")
        
    except Exception as e:
        logger.exception(f"[GPT Queue] Error confirming meal for user {user_id}: {e}")
        try:
            await bot.edit_message_text(
                chat_id=user_id,
                message_id=message_id,
                text="❌ Ошибка при добавлении. Попробуйте еще раз.",
                parse_mode="HTML"
            )
        except:
            pass
    finally:
        # ✅ Всегда освобождаем блокировку
        try:
            await redis.delete(lock_key)
        except:
            pass


async def cancel_meal_addition(ctx, user_id: int, meal_key: str, message_id: int):
    """
    Отмена добавления блюда
    
    ✅ ЗАЩИТА ОТ ДУБЛИРОВАНИЯ: Атомарное удаление через getdel
    """
    logger.info(f"[GPT Queue] Canceling meal for user {user_id}, key={meal_key}")
    
    from app.db.redis_client import redis
    
    try:
        # ✅ Атомарное удаление
        redis_key = f"pending_meal:{user_id}:{meal_key}"
        data = await redis.getdel(redis_key)
        
        if not data:
            logger.warning(f"[GPT Queue] Meal {meal_key} already processed or cancelled")
            await bot.edit_message_text(
                chat_id=user_id,
                message_id=message_id,
                text="❌ Данные уже были обработаны или отменены.",
                parse_mode="HTML"
            )
            return
        
        # Возвращаем токен
        await refund_token(user_id)
        
        await bot.edit_message_text(
            chat_id=user_id,
            message_id=message_id,
            text="❌ Добавление отменено.\n\nОтправьте новое фото или опишите блюдо текстом.",
            parse_mode="HTML"
        )
        
        logger.info(f"[GPT Queue] Successfully cancelled meal for user {user_id}")
        
    except Exception as e:
        logger.exception(f"[GPT Queue] Error canceling meal for user {user_id}: {e}")
        try:
            await bot.edit_message_text(
                chat_id=user_id,
                message_id=message_id,
                text="❌ Ошибка при отмене. Попробуйте еще раз.",
                parse_mode="HTML"
            )
        except:
            pass