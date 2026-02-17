# app/tasks/gpt_queue.py
"""
Универсальная обработка запросов к GPT.
Чистый дизайн + обработка всех edge cases.
"""
import logging
import json
import hashlib
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from app.api.gpt import ai_request
from app.services.user import get_user_by_id, refund_token
from app.services.meals import (
    save_meals,
    get_today_summary,
    get_last_meal,
    get_today_meals,
    update_meal,
    delete_meal,
    delete_multiple_meals,
    user_today,
)
from app.db.redis_client import redis
from app.bot.bot import bot
from app.utils.telegram_helpers import safe_send_message, safe_delete_message, escape_html
from app.config import settings
import pytz
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)

# ============================================
# КОНСТАНТЫ
# ============================================
UNDO_KEY_TTL = 1800       # 30 минут на отмену
CALC_DATA_TTL = 600       # 10 минут для данных расчёта
MAX_FOOD_NAME_LEN = 100   # Макс длина названия
MAX_WEIGHT_GRAMS = 3000   # Макс вес порции
MIN_WEIGHT_GRAMS = 1      # Мин вес
MAX_CALORIES = 5000       # Макс калорий на блюдо
MIN_CALORIES_PER_100G = 20  # Минимум калорий на 100г (даже огурец ~15)


# ============================================
# ФОРМАТИРОВАНИЕ (чистый дизайн)
# ============================================

def format_meal_line(meal: dict, show_macros: bool = True) -> str:
    """Форматирует одно блюдо"""
    name = escape_html(meal.get('name', 'Блюдо')[:MAX_FOOD_NAME_LEN])
    weight = meal.get('weight_grams', 0)
    cal = meal.get('calories', 0)
    
    if show_macros:
        p = meal.get('protein', 0)
        f = meal.get('fat', 0)
        c = meal.get('carbs', 0)
        return f"<b>{name}</b>\n{weight}г · {cal:.1f} ккал\nБелки {p:.1f}г · Жиры {f:.1f}г · Углеводы {c:.1f}г"
    else:
        return f"<b>{name}</b> — {weight}г, {cal:.1f} ккал"


def format_totals(totals: dict, date_str: str = None) -> str:
    """Форматирует итоги"""
    cal = float(totals.get('total_calories', 0))
    p = float(totals.get('total_protein', 0))
    f = float(totals.get('total_fat', 0))
    c = float(totals.get('total_carbs', 0))
    count = totals.get('meals_count', 0)
    
    header = f"Итого за {date_str}" if date_str else "Итого"
    
    return (
        f"<b>{header}:</b>\n"
        f"{cal:.1f} ккал · {count} приёмов\n"
        f"Белки {p:.1f}г\n"
        f"Жиры {f:.1f}г\n"
        f"Углеводы {c:.1f}г"
    )


def format_add_success(items: list, totals: dict, date_str: str) -> str:
    """Успешное добавление"""
    lines = ["<b>✓ Добавлено</b>\n"]
    
    for meal in items:
        lines.append(format_meal_line(meal, show_macros=True))
        lines.append("")
    
    lines.append("─" * 20)
    lines.append(format_totals(totals, date_str))
    
    return "\n".join(lines)


def format_calculate_result(items: list) -> str:
    """Результат расчёта"""
    lines = ["<b>Расчёт калорийности</b>\n"]
    
    total_cal = 0
    total_p = 0
    total_f = 0
    total_c = 0
    
    for meal in items:
        lines.append(format_meal_line(meal, show_macros=True))
        lines.append("")
        total_cal += meal.get('calories', 0)
        total_p += meal.get('protein', 0)
        total_f += meal.get('fat', 0)
        total_c += meal.get('carbs', 0)
    
    lines.append("─" * 20)
    lines.append(f"<b>Всего:</b> {total_cal:.1f} ккал")
    lines.append(f"Белки {total_p:.1f}г\nЖиры {total_f:.1f}г\nУглеводы {total_c:.1f}г")
    lines.append("")
    lines.append("<i>Не добавлено в рацион</i>")
    
    return "\n".join(lines)


def format_delete_success(food_name: str, remaining_cal: float) -> str:
    """Успешное удаление"""
    name = escape_html(food_name[:MAX_FOOD_NAME_LEN])
    return f"<b>✓ Удалено:</b> {name}\n\nИтого за день: {remaining_cal:.1f} ккал"


def format_edit_success(meal: dict, totals: dict) -> str:
    """Успешное редактирование"""
    lines = ["<b>✓ Обновлено</b>\n"]
    lines.append(format_meal_line(meal, show_macros=True))
    lines.append("")
    lines.append("─" * 20)
    lines.append(f"Итого: {float(totals.get('total_calories', 0)):.1f} ккал")
    return "\n".join(lines)


def format_today_meals(meals: list) -> str:
    """Список за сегодня"""
    if not meals:
        return "Сегодня пока ничего не добавлено."
    
    lines = ["<b>Сегодня:</b>\n"]
    
    for meal in meals[-7:]:
        time = meal["meal_datetime"].strftime("%H:%M")
        name = escape_html(meal['food_name'][:30])
        cal = float(meal.get('calories', 0))
        lines.append(f"{time}  {name} — {cal:.1f} ккал")
    
    if len(meals) > 7:
        lines.append(f"\n<i>...и ещё {len(meals) - 7}</i>")
    
    return "\n".join(lines)


# ============================================
# ВАЛИДАЦИЯ
# ============================================

def validate_and_fix_item(item: dict) -> dict:
    """Валидирует и исправляет данные блюда"""
    weight = item.get('weight_grams', 100)
    weight = max(MIN_WEIGHT_GRAMS, min(weight, MAX_WEIGHT_GRAMS))
    
    calories = float(item.get('calories', 0))
    calories = max(0, min(calories, MAX_CALORIES))
    
    protein = max(0, float(item.get('protein', 0)))
    fat = max(0, float(item.get('fat', 0)))
    carbs = max(0, float(item.get('carbs', 0)))
    
    name = item.get('name', 'Блюдо')[:MAX_FOOD_NAME_LEN]
    if not name.strip():
        name = 'Блюдо'
    
    # ✅ ИСПРАВЛЕНИЕ: Если калории = 0, но есть БЖУ — пересчитать
    if calories == 0 and (protein > 0 or fat > 0 or carbs > 0):
        calories = (protein * 4) + (fat * 9) + (carbs * 4)
        logger.warning(f"[Validate] Recalculated calories from macros: {calories}")
    
    # ✅ ИСПРАВЛЕНИЕ: Если всё нули — установить минимальные значения
    if calories == 0 and protein == 0 and fat == 0 and carbs == 0:
        # Грубая оценка: ~150 ккал на 100г (средняя еда)
        estimated_cal = (weight / 100) * 150
        calories = estimated_cal
        protein = weight * 0.05  # ~5г белка на 100г
        fat = weight * 0.05     # ~5г жира на 100г
        carbs = weight * 0.15   # ~15г углеводов на 100г
        logger.warning(f"[Validate] All zeros for '{name}', estimated: {calories:.0f} ккал")
    
    # ✅ ИСПРАВЛЕНИЕ: Проверка минимальной калорийности
    min_expected = (weight / 100) * MIN_CALORIES_PER_100G
    if calories < min_expected and weight > 0:
        logger.warning(f"[Validate] Suspiciously low calories for '{name}': {calories} < {min_expected}")
        # Не меняем, но логируем
    
    return {
        'name': name,
        'weight_grams': int(weight),
        'calories': round(calories, 1),
        'protein': round(protein, 1),
        'fat': round(fat, 1),
        'carbs': round(carbs, 1),
    }


def validate_items(items: list) -> list:
    """Валидирует список блюд"""
    if not items:
        return []
    return [validate_and_fix_item(item) for item in items]


def check_all_zeros(items: list) -> bool:
    """Проверяет, все ли значения нулевые"""
    for item in items:
        if (item.get('calories', 0) > 0 or 
            item.get('protein', 0) > 0 or 
            item.get('fat', 0) > 0 or 
            item.get('carbs', 0) > 0):
            return False
    return True


# ============================================
# HELPERS
# ============================================

async def get_meals_context(user_id: int, user_tz: str) -> str:
    """Контекст для GPT"""
    try:
        meals = await get_today_meals(user_id, user_tz, limit=5)
        if not meals:
            return ""
        
        lines = ["Сегодня добавлено:"]
        for meal in meals:
            time = meal["meal_datetime"].strftime("%H:%M")
            cal = float(meal.get('calories', 0))
            lines.append(f"- {time}: {meal['food_name']} ({cal:.1f} ккал)")
        return "\n".join(lines)
    except Exception:
        return ""


async def save_undo_data(meal_ids: list, user_id: int) -> str:
    """Сохраняет для отмены"""
    key = f"undo:{user_id}:{uuid.uuid4().hex[:8]}"
    await redis.setex(key, UNDO_KEY_TTL, json.dumps(meal_ids))
    return key


async def save_calc_data(items: list, user_id: int) -> str:
    """Сохраняет расчёт с уникальным ключом"""
    calc_id = uuid.uuid4().hex[:8]
    key = f"calc:{user_id}:{calc_id}"
    await redis.setex(key, CALC_DATA_TTL, json.dumps(items))
    # Сохраняем ссылку на последний расчёт (для add_previous через текст)
    await redis.setex(f"calc_last:{user_id}", CALC_DATA_TTL, key)
    return key


async def get_calc_data(user_id: int, calc_key: str = None) -> list:
    """Получает расчёт по ключу или последний"""
    if calc_key:
        data = await redis.get(calc_key)
    else:
        # Берём последний расчёт (для add_previous через текст)
        last_key = await redis.get(f"calc_last:{user_id}")
        if not last_key:
            return []
        data = await redis.get(last_key)
    return json.loads(data) if data else []


async def is_duplicate_request(user_id: int, text_hash: str) -> bool:
    """Антидубликат"""
    key = f"req:{user_id}:{text_hash}"
    if await redis.exists(key):
        return True
    await redis.setex(key, 15, "1")
    return False


# ============================================
# ИСТОРИЯ ДИАЛОГА (контекст разговора)
# ============================================
CHAT_HISTORY_TTL = 600          # 10 минут
CHAT_HISTORY_MAX_ENTRIES = 6    # 3 обмена (user+assistant)
CHAT_HISTORY_MAX_CHARS = 1500   # лимит символов


async def get_chat_history(user_id: int) -> list[dict]:
    """Получает историю диалога из Redis"""
    key = f"chat_history:{user_id}"
    try:
        data = await redis.get(key)
        if not data:
            return []
        history = json.loads(data)
        return history if isinstance(history, list) else []
    except Exception as e:
        logger.warning(f"[ChatHistory] Error reading for {user_id}: {e}")
        return []


async def save_chat_exchange(
    user_id: int,
    user_summary: str,
    assistant_summary: str,
) -> None:
    """Сохраняет обмен user+assistant в историю"""
    key = f"chat_history:{user_id}"
    try:
        history = await get_chat_history(user_id)

        history.append({"role": "user", "content": user_summary})
        history.append({"role": "assistant", "content": assistant_summary})

        # Обрезаем до макс. записей
        if len(history) > CHAT_HISTORY_MAX_ENTRIES:
            history = history[-CHAT_HISTORY_MAX_ENTRIES:]

        # Обрезаем по символам (удаляем старые пары)
        while history and sum(len(m["content"]) for m in history) > CHAT_HISTORY_MAX_CHARS:
            if len(history) >= 2:
                history = history[2:]
            else:
                history = []
                break

        await redis.setex(
            key,
            CHAT_HISTORY_TTL,
            json.dumps(history, ensure_ascii=False),
        )
    except Exception as e:
        logger.warning(f"[ChatHistory] Error saving for {user_id}: {e}")


def build_user_summary(text: str, has_image: bool) -> str:
    """Краткое описание сообщения пользователя (без base64)"""
    if has_image:
        caption = text.replace("[ФОТО ЕДЫ]", "").strip()
        if caption:
            return f"Пользователь отправил фото еды с подписью: {caption[:100]}"
        return "Пользователь отправил фото еды"
    return text[:200] if text and text.strip() else "Сообщение пользователя"


def build_assistant_summary(intent: str, items: list, notes: str) -> str:
    """Краткое описание ответа GPT"""
    if intent == "add" and items:
        parts = [
            f"{it.get('name', 'Блюдо')[:30]} {it.get('weight_grams', 0)}г ({it.get('calories', 0):.0f} ккал)"
            for it in items[:5]
        ]
        return "Добавлено: " + ", ".join(parts)

    if intent == "calculate" and items:
        parts = [
            f"{it.get('name', 'Блюдо')[:30]} ({it.get('calories', 0):.0f} ккал)"
            for it in items[:5]
        ]
        return "Расчёт: " + ", ".join(parts)

    if intent == "delete":
        return "Удалено из рациона"

    if intent == "edit":
        return "Отредактировано"

    return notes[:100] if notes else "Ответ бота"


# ============================================
# ГЛАВНАЯ ФУНКЦИЯ
# ============================================

async def process_universal_request(
    ctx,
    user_id: int,
    chat_id: int,
    message_id: int,
    text: str,
    image_url: str = None
):
    """Универсальная обработка"""
    logger.info(f"[GPT] User {user_id}: {text[:50]}...")
    
    try:
        # Антидубликат (15 сек окно — защита от двойного нажатия)
        text_hash = hashlib.md5((text + str(image_url)).encode()).hexdigest()[:8]
        if await is_duplicate_request(user_id, text_hash):
            logger.info(f"[GPT] Duplicate from {user_id}")
            await safe_delete_message(bot, chat_id, message_id)
            await safe_send_message(bot, chat_id, "⏳ Это сообщение уже обрабатывается.")
            await refund_token(user_id)
            return

        user = await get_user_by_id(user_id)
        if not user:
            await safe_delete_message(bot, chat_id, message_id)
            await safe_send_message(bot, chat_id, "Пользователь не найден. Нажмите /start")
            await refund_token(user_id)
            return
        
        user_tz = user.get('timezone', 'Europe/Moscow')
        context = await get_meals_context(user_id, user_tz)

        # Получаем историю диалога для контекста
        chat_history = await get_chat_history(user_id)

        if image_url:
            text = f"[ФОТО ЕДЫ] {text}" if text else "[ФОТО ЕДЫ]"

        code, gpt_response = await ai_request(
            user_id=user_id,
            text=text,
            image_link=image_url,
            context=context,
            history=chat_history,
        )
        logger.info(f"[GPT] Raw response for {user_id}: {gpt_response[:500] if gpt_response else 'None'}...")
        
        if code == 429 and gpt_response == "QUOTA_EXCEEDED":
            await safe_delete_message(bot, chat_id, message_id)
            await safe_send_message(bot, chat_id, "Сервис временно недоступен. Попробуйте позже.")
            await refund_token(user_id)
            return
        
        if code != 200 or not gpt_response:
            await safe_delete_message(bot, chat_id, message_id)
            await safe_send_message(bot, chat_id, "Не удалось обработать. Попробуйте ещё раз.")
            await refund_token(user_id)
            return
        
        try:
            data = json.loads(gpt_response)
        except json.JSONDecodeError:
            await safe_delete_message(bot, chat_id, message_id)
            await safe_send_message(bot, chat_id, "Ошибка распознавания. Переформулируйте.")
            await refund_token(user_id)
            return
        
        intent = data.get("intent", "add")
        raw_items = data.get("items", [])
        items = validate_items(raw_items)
        notes = data.get("notes", "")
        meal_time = data.get("meal_time")  # "HH:MM" или None

        logger.info(f"[GPT] User {user_id}: intent={intent}, items={len(items)}, meal_time={meal_time}")

        # ✅ ИСПРАВЛЕНИЕ: Проверка на нулевые значения ДО валидации
        if raw_items and check_all_zeros(raw_items):
            logger.warning(f"[GPT] All zeros in response for user {user_id}, GPT failed to calculate")

        # Сохраняем обмен в историю диалога
        try:
            user_summary = build_user_summary(text, image_url is not None)
            assistant_summary = build_assistant_summary(intent, items, notes)
            await save_chat_exchange(user_id, user_summary, assistant_summary)
        except Exception as e:
            logger.warning(f"[GPT] Error saving chat history for {user_id}: {e}")

        # Роутинг
        if intent == "unknown":
            await handle_unknown(user_id, chat_id, message_id, notes)
        elif intent == "calculate":
            await handle_calculate(user_id, chat_id, message_id, items)
        elif intent == "add_previous":
            await handle_add_previous(user_id, chat_id, message_id, user_tz, user)
        elif intent == "delete":
            await handle_delete(user_id, chat_id, message_id, data, user_tz)
        elif intent == "edit":
            await handle_edit(user_id, chat_id, message_id, data, user_tz)
        else:
            if not items:
                await safe_delete_message(bot, chat_id, message_id)
                await safe_send_message(bot, chat_id, notes or "Не распознал еду. Опишите подробнее.")
                await refund_token(user_id)
                return
            await handle_add(user_id, chat_id, message_id, items, user_tz, image_url, meal_time, user)
        
    except Exception as e:
        logger.exception(f"[GPT] Error: {e}")
        try:
            await safe_delete_message(bot, chat_id, message_id)
            await safe_send_message(bot, chat_id, "Ошибка. Попробуйте ещё раз.")
        except Exception:
            pass
        await refund_token(user_id)


# ============================================
# ОБРАБОТЧИКИ
# ============================================

async def handle_unknown(user_id: int, chat_id: int, message_id: int, notes: str):
    """Непонятный запрос"""
    await safe_delete_message(bot, chat_id, message_id)
    await safe_send_message(bot, chat_id, notes or "Не понял. Отправьте фото еды или напишите что съели.")
    await refund_token(user_id)


async def handle_add(user_id: int, chat_id: int, message_id: int, items: list, user_tz: str, image_url: str = None, meal_time: str = None, user_data: dict = None):
    """Добавление"""
    try:
        user_data = user_data or {}
        goal = user_data.get("calorie_goal") or settings.default_calorie_goal

        result = await save_meals(user_id, {"items": items, "notes": ""}, user_tz, image_url, meal_time=meal_time)
        added_ids = result.get('added_meal_ids', [])

        summary = await get_today_summary(user_id, user_tz)
        date_str = user_today(user_tz).strftime("%d.%m")

        text = format_add_success(items, summary["totals"], date_str)

        # Прогресс калорий за день
        totals = summary["totals"]
        cal = float(totals.get('total_calories', 0))
        pct = min(cal / goal * 100, 100) if goal > 0 else 0
        filled = int(pct / 10)
        bar = "▓" * filled + "░" * (10 - filled)
        text += f"\n\n{bar} {pct:.0f}% от ~{goal} ккал"

        # Прогресс БЖУ (если есть цели)
        p_goal = user_data.get("protein_goal")
        f_goal = user_data.get("fat_goal")
        c_goal = user_data.get("carbs_goal")
        if p_goal and f_goal and c_goal:
            p_now = float(totals.get('total_protein', 0))
            f_now = float(totals.get('total_fat', 0))
            c_now = float(totals.get('total_carbs', 0))
            text += (
                f"\nБелки: {p_now:.0f}/{p_goal}г"
                f"\nЖиры: {f_now:.0f}/{f_goal}г"
                f"\nУглеводы: {c_now:.0f}/{c_goal}г"
            )

        # Показываем остаток запросов
        user = await get_user_by_id(user_id)
        remaining = user.get('free_tokens', 0) if user else 0
        text += f"\n\nОсталось запросов: {remaining}"

        buttons = []
        if added_ids:
            undo_key = await save_undo_data(added_ids, user_id)
            buttons.append([InlineKeyboardButton(text="Отменить", callback_data=undo_key)])

        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None

        await safe_delete_message(bot, chat_id, message_id)
        await safe_send_message(bot, chat_id, text, keyboard)
        
    except Exception as e:
        logger.exception(f"[GPT] Add error: {e}")
        await safe_delete_message(bot, chat_id, message_id)
        await safe_send_message(bot, chat_id, "Ошибка сохранения.")
        await refund_token(user_id)


async def handle_calculate(user_id: int, chat_id: int, message_id: int, items: list):
    """Только расчёт"""
    if not items:
        await safe_delete_message(bot, chat_id, message_id)
        await safe_send_message(bot, chat_id, "Не удалось определить блюдо.")
        await refund_token(user_id)
        return

    calc_key = await save_calc_data(items, user_id)
    text = format_calculate_result(items)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Добавить в рацион", callback_data=f"addcalc:{calc_key}")]
    ])
    
    await safe_delete_message(bot, chat_id, message_id)
    await safe_send_message(bot, chat_id, text, keyboard)


async def handle_add_previous(user_id: int, chat_id: int, message_id: int, user_tz: str, user_data: dict = None):
    """Добавить расчёт"""
    items = await get_calc_data(user_id)

    if not items:
        await safe_delete_message(bot, chat_id, message_id)
        await safe_send_message(bot, chat_id, "Нет сохранённого расчёта. Сначала отправьте еду.")
        await refund_token(user_id)
        return

    # Удаляем ссылку на последний расчёт
    last_key = await redis.get(f"calc_last:{user_id}")
    if last_key:
        await redis.delete(last_key)
    await redis.delete(f"calc_last:{user_id}")
    await handle_add(user_id, chat_id, message_id, items, user_tz, None, None, user_data)


async def handle_delete(user_id: int, chat_id: int, message_id: int, data: dict, user_tz: str):
    """Удаление"""
    try:
        target = data.get("delete_target", "last")
        
        if target == "all":
            summary = await get_today_summary(user_id, user_tz)
            meals = summary.get("meals", [])

            if not meals:
                await safe_delete_message(bot, chat_id, message_id)
                await safe_send_message(bot, chat_id, "Сегодня нечего удалять.")
                await refund_token(user_id)
                return

            # Подтверждение перед удалением всего
            meal_ids = [m['id'] for m in meals]
            confirm_key = f"delall:{user_id}:{uuid.uuid4().hex[:8]}"
            await redis.setex(confirm_key, 300, json.dumps(meal_ids))

            cal = float(summary["totals"]["total_calories"])
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Да, удалить всё", callback_data=confirm_key)],
                [InlineKeyboardButton(text="Отмена", callback_data="canceldelall")],
            ])

            await safe_delete_message(bot, chat_id, message_id)
            await safe_send_message(
                bot, chat_id,
                f"⚠️ <b>Удалить все записи за сегодня?</b>\n\n"
                f"Записей: {len(meals)}, всего: {cal:.1f} ккал",
                keyboard
            )
            return
        
        if target == "last":
            last = await get_last_meal(user_id, user_tz)
            
            if not last:
                await safe_delete_message(bot, chat_id, message_id)
                await safe_send_message(bot, chat_id, "Нечего удалять.")
                await refund_token(user_id)
                return
            
            if await delete_meal(last['id'], user_id):
                summary = await get_today_summary(user_id, user_tz)
                text = format_delete_success(last['food_name'], float(summary["totals"]['total_calories']))
                await safe_delete_message(bot, chat_id, message_id)
                await safe_send_message(bot, chat_id, text)
            else:
                await safe_delete_message(bot, chat_id, message_id)
                await safe_send_message(bot, chat_id, "Не удалось удалить.")
            return
        
        # По названию
        summary = await get_today_summary(user_id, user_tz)
        meals = summary.get("meals", [])
        
        if not meals:
            await safe_delete_message(bot, chat_id, message_id)
            await safe_send_message(bot, chat_id, "Сегодня нет записей.")
            await refund_token(user_id)
            return
        
        found = None
        for meal in reversed(meals):
            if target.lower() in meal['food_name'].lower():
                found = meal
                break
        
        if found:
            if await delete_meal(found['id'], user_id):
                summary = await get_today_summary(user_id, user_tz)
                text = format_delete_success(found['food_name'], float(summary["totals"]['total_calories']))
                await safe_delete_message(bot, chat_id, message_id)
                await safe_send_message(bot, chat_id, text)
            else:
                await safe_delete_message(bot, chat_id, message_id)
                await safe_send_message(bot, chat_id, "Не удалось удалить.")
        else:
            await safe_delete_message(bot, chat_id, message_id)
            text = f"Не нашёл «{escape_html(target)}».\n\n" + format_today_meals(meals)
            await safe_send_message(bot, chat_id, text)
            await refund_token(user_id)
            
    except Exception as e:
        logger.exception(f"[GPT] Delete error: {e}")
        await safe_delete_message(bot, chat_id, message_id)
        await safe_send_message(bot, chat_id, "Ошибка удаления.")
        await refund_token(user_id)


async def handle_edit(user_id: int, chat_id: int, message_id: int, data: dict, user_tz: str):
    """Редактирование (по имени или последнее)"""
    try:
        edit_target = data.get("edit_target", "last")
        meal = None

        if edit_target and edit_target != "last":
            # Поиск по названию
            summary = await get_today_summary(user_id, user_tz)
            meals = summary.get("meals", [])
            for m in reversed(meals):
                if edit_target.lower() in m['food_name'].lower():
                    meal = m
                    break

        if not meal:
            meal = await get_last_meal(user_id, user_tz)

        if not meal:
            await safe_delete_message(bot, chat_id, message_id)
            await safe_send_message(bot, chat_id, "Нет записей для редактирования.")
            await refund_token(user_id)
            return

        items = validate_items(data.get("items", []))

        if items:
            new = items[0]
            await update_meal(
                meal_id=meal['id'],
                user_id=user_id,
                food_name=new.get('name', meal['food_name']),
                weight_grams=new.get('weight_grams', meal['weight_grams']),
                calories=new.get('calories', meal['calories']),
                protein=new.get('protein', meal['protein']),
                fat=new.get('fat', meal['fat']),
                carbs=new.get('carbs', meal['carbs'])
            )

            summary = await get_today_summary(user_id, user_tz)
            text = format_edit_success(new, summary["totals"])
            await safe_delete_message(bot, chat_id, message_id)
            await safe_send_message(bot, chat_id, text)
        else:
            await safe_delete_message(bot, chat_id, message_id)
            await safe_send_message(
                bot, chat_id,
                "Не понял что изменить.\n\nПримеры:\n• «там было 150г»\n• «исправь гречку — было 200г»"
            )
            await refund_token(user_id)

    except Exception as e:
        logger.exception(f"[GPT] Edit error: {e}")
        await safe_delete_message(bot, chat_id, message_id)
        await safe_send_message(bot, chat_id, "Ошибка редактирования.")
        await refund_token(user_id)