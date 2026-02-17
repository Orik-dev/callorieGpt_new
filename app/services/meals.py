import aiomysql
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import json
import pytz
from decimal import Decimal
from app.db.mysql import mysql
import logging
import re

logger = logging.getLogger(__name__)


class MealParseError(Exception):
    """Ошибка парсинга ответа GPT"""
    pass


async def parse_gpt_response(response: str) -> Dict:
    """
    Парсит JSON-ответ от GPT и валидирует данные
    
    Args:
        response: Сырой ответ от GPT
        
    Returns:
        Dict с полями items[], notes
        
    Raises:
        MealParseError: Если ответ невалидный
    """
    try:
        # Убираем markdown блоки если есть
        response = response.strip()
        
        # Удаляем возможные ```json ... ```
        if '```' in response:
            match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response, re.DOTALL)
            if match:
                response = match.group(1)
            else:
                parts = response.split('```')
                if len(parts) >= 2:
                    response = parts[1]
                    if response.startswith('json'):
                        response = response[4:]
        
        # Парсим JSON
        data = json.loads(response)
        
        # Валидация структуры
        if "items" not in data:
            raise MealParseError("Отсутствует поле 'items' в ответе")
        
        if not isinstance(data["items"], list):
            raise MealParseError("Поле 'items' должно быть массивом")
        
        if len(data["items"]) == 0:
            raise MealParseError("Массив 'items' пуст")
        
        # Валидация каждого элемента
        for idx, item in enumerate(data["items"]):
            required_fields = ["name", "weight_grams", "calories", "protein", "fat", "carbs"]
            
            for field in required_fields:
                if field not in item:
                    raise MealParseError(f"Отсутствует поле '{field}' в элементе {idx}")
            
            # Проверка типов и разумности значений
            try:
                weight = float(item["weight_grams"])
                calories = float(item["calories"])
                protein = float(item["protein"])
                fat = float(item["fat"])
                carbs = float(item["carbs"])
                
                # Проверка диапазонов
                if not (1 <= weight <= 5000):
                    raise ValueError(f"Вес {weight}г вне диапазона 1-5000")
                
                if not (0 <= calories <= 5000):
                    raise ValueError(f"Калории {calories} вне диапазона 0-5000")
                
                if not (0 <= protein <= 500):
                    raise ValueError(f"Белки {protein}г вне диапазона 0-500")
                
                if not (0 <= fat <= 500):
                    raise ValueError(f"Жиры {fat}г вне диапазона 0-500")
                
                if not (0 <= carbs <= 1000):
                    raise ValueError(f"Углеводы {carbs}г вне диапазона 0-1000")
                
                # Проверка калорийности по формуле (допуск ±20%)
                calculated_cal = (protein * 4) + (fat * 9) + (carbs * 4)
                if abs(calories - calculated_cal) > calculated_cal * 0.3:
                    logger.warning(
                        f"Suspicious calories for {item['name']}: "
                        f"stated={calories}, calculated={calculated_cal:.1f}"
                    )
                
                # Обновляем значения как float
                item["weight_grams"] = weight
                item["calories"] = calories
                item["protein"] = protein
                item["fat"] = fat
                item["carbs"] = carbs
                
                # Проверяем confidence
                if "confidence" in item:
                    conf = float(item["confidence"])
                    if not (0 <= conf <= 1):
                        item["confidence"] = 0.8
                else:
                    item["confidence"] = 0.8
                    
            except (ValueError, TypeError) as e:
                raise MealParseError(f"Ошибка валидации элемента {idx}: {e}")
        
        return data
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error: {e}\nResponse: {response[:500]}")
        raise MealParseError(f"Некорректный JSON: {e}")
    except MealParseError:
        raise
    except Exception as e:
        logger.error(f"Unexpected parse error: {e}")
        raise MealParseError(f"Ошибка парсинга: {e}")


async def save_meals(
    user_id: int,
    parsed_data: Dict,
    user_tz: str = "Europe/Moscow",
    image_file_id: Optional[str] = None
) -> Dict:
    """
    Сохраняет прием пищи в БД и обновляет дневные итоги
    
    Args:
        user_id: Telegram ID пользователя
        parsed_data: Распарсенные данные от GPT
        user_tz: Часовой пояс пользователя
        image_file_id: ID фото в Telegram (если было)
        
    Returns:
        Dict с обновленными итогами дня и ID добавленных блюд
    """
    try:
        tz = pytz.timezone(user_tz)
        now = datetime.now(tz)
        today = now.date()
        
        added_meal_ids = []  # ✅ Список ID добавленных блюд
        
        async with mysql.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await conn.begin()
                
                try:
                    # Сохраняем каждое блюдо
                    for item in parsed_data["items"]:
                        await cur.execute(
                            """INSERT INTO meals_history 
                            (tg_id, meal_date, meal_datetime, food_name, weight_grams,
                             calories, protein, fat, carbs, confidence_score, 
                             gpt_raw_response, image_file_id)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                            (
                                user_id,
                                today,
                                now,
                                item["name"][:255],
                                int(item["weight_grams"]),
                                Decimal(str(item["calories"])),
                                Decimal(str(item["protein"])),
                                Decimal(str(item["fat"])),
                                Decimal(str(item["carbs"])),
                                Decimal(str(item.get("confidence", 0.8))),
                                json.dumps(parsed_data, ensure_ascii=False),
                                image_file_id
                            )
                        )
                        
                        # ✅ Получаем ID добавленного блюда
                        added_meal_ids.append(cur.lastrowid)
                    
                    # Пересчитываем итоги дня (атомарно)
                    await cur.execute(
                        """INSERT INTO daily_totals 
                            (tg_id, date, total_calories, total_protein, 
                             total_fat, total_carbs, meals_count)
                        SELECT 
                            tg_id, 
                            meal_date,
                            SUM(calories), 
                            SUM(protein), 
                            SUM(fat), 
                            SUM(carbs), 
                            COUNT(*)
                        FROM meals_history
                        WHERE tg_id = %s AND meal_date = %s
                        GROUP BY tg_id, meal_date
                        ON DUPLICATE KEY UPDATE
                            total_calories = VALUES(total_calories),
                            total_protein = VALUES(total_protein),
                            total_fat = VALUES(total_fat),
                            total_carbs = VALUES(total_carbs),
                            meals_count = VALUES(meals_count)""",
                        (user_id, today)
                    )
                    
                    await conn.commit()
                    
                    logger.info(
                        f"✅ Saved {len(parsed_data['items'])} meals for user {user_id} "
                        f"on {today}, IDs: {added_meal_ids}"
                    )
                    
                    # Получаем обновленные итоги
                    summary = await get_today_summary(user_id, user_tz)
                    summary['added_meal_ids'] = added_meal_ids  # ✅ Добавляем ID
                    
                    return summary
                    
                except Exception as e:
                    await conn.rollback()
                    logger.exception(f"Error saving meals for user {user_id}: {e}")
                    raise
                    
    except Exception as e:
        logger.exception(f"Critical error in save_meals: {e}")
        raise

async def get_today_summary(user_id: int, user_tz: str = "Europe/Moscow") -> Dict:
    """
    Получает итоги за сегодняшний день
    
    Args:
        user_id: Telegram ID пользователя
        user_tz: Часовой пояс пользователя
        
    Returns:
        Dict с ключами totals и meals
    """
    try:
        tz = pytz.timezone(user_tz)
        today = datetime.now(tz).date()
        
        # Получаем итоги
        totals = await mysql.fetchone(
            "SELECT * FROM daily_totals WHERE tg_id = %s AND date = %s",
            (user_id, today)
        )
        
        # Получаем список приемов пищи
        meals = await mysql.fetchall(
            """SELECT * FROM meals_history
            WHERE tg_id = %s AND meal_date = %s
            ORDER BY meal_datetime""",
            (user_id, today)
        )
        
        # Формируем ответ с дефолтными значениями
        if not totals:
            totals = {
                "total_calories": Decimal("0"),
                "total_protein": Decimal("0"),
                "total_fat": Decimal("0"),
                "total_carbs": Decimal("0"),
                "meals_count": 0
            }
        
        return {
            "totals": totals,
            "meals": meals or []
        }
        
    except Exception as e:
        logger.exception(f"Error getting today summary for user {user_id}: {e}")
        return {
            "totals": {
                "total_calories": Decimal("0"),
                "total_protein": Decimal("0"),
                "total_fat": Decimal("0"),
                "total_carbs": Decimal("0"),
                "meals_count": 0
            },
            "meals": []
        }


async def get_week_summary(user_id: int, user_tz: str = "Europe/Moscow") -> List[Dict]:
    """
    Получает итоги за последние 7 дней
    
    Returns:
        List[Dict] - данные по дням
    """
    try:
        tz = pytz.timezone(user_tz)
        today = datetime.now(tz).date()
        
        week_ago = today - timedelta(days=6)
        
        results = await mysql.fetchall(
            """SELECT * FROM daily_totals
            WHERE tg_id = %s 
            AND date BETWEEN %s AND %s
            ORDER BY date""",
            (user_id, week_ago, today)
        )
        
        return results or []
        
    except Exception as e:
        logger.exception(f"Error getting week summary: {e}")
        return []


async def _recalculate_daily_totals(cur, user_id: int, meal_date) -> None:
    """Пересчитывает daily_totals после удаления"""
    # Проверяем остались ли записи за этот день
    await cur.execute(
        "SELECT COUNT(*) as cnt FROM meals_history WHERE tg_id = %s AND meal_date = %s",
        (user_id, meal_date)
    )
    row = await cur.fetchone()
    count = row["cnt"] if row else 0

    if count == 0:
        # Нет записей — удаляем строку из daily_totals
        await cur.execute(
            "DELETE FROM daily_totals WHERE tg_id = %s AND date = %s",
            (user_id, meal_date)
        )
    else:
        # Пересчитываем итоги
        await cur.execute(
            """INSERT INTO daily_totals
                (tg_id, date, total_calories, total_protein,
                 total_fat, total_carbs, meals_count)
            SELECT
                tg_id, meal_date,
                SUM(calories), SUM(protein), SUM(fat), SUM(carbs), COUNT(*)
            FROM meals_history
            WHERE tg_id = %s AND meal_date = %s
            GROUP BY tg_id, meal_date
            ON DUPLICATE KEY UPDATE
                total_calories = VALUES(total_calories),
                total_protein = VALUES(total_protein),
                total_fat = VALUES(total_fat),
                total_carbs = VALUES(total_carbs),
                meals_count = VALUES(meals_count)""",
            (user_id, meal_date)
        )


async def delete_meal(meal_id: int, user_id: int) -> bool:
    """Удаляет прием пищи и пересчитывает daily_totals (в транзакции)"""
    try:
        async with mysql.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await conn.begin()
                try:
                    # Получаем дату для пересчёта
                    await cur.execute(
                        "SELECT meal_date FROM meals_history WHERE id = %s AND tg_id = %s",
                        (meal_id, user_id)
                    )

                    result = await cur.fetchone()
                    if not result:
                        await conn.rollback()
                        logger.warning(f"[Meals] Meal {meal_id} not found for user {user_id}")
                        return False

                    meal_date = result["meal_date"]

                    # Удаляем
                    await cur.execute(
                        "DELETE FROM meals_history WHERE id = %s AND tg_id = %s",
                        (meal_id, user_id)
                    )

                    if cur.rowcount > 0:
                        # Пересчитываем daily_totals
                        await _recalculate_daily_totals(cur, user_id, meal_date)
                        await conn.commit()

                        # Инвалидируем кэш
                        from app.db.redis_client import redis
                        cache_key = f"meals:summary:{user_id}:{meal_date}"
                        await redis.delete(cache_key)
                        logger.info(f"[Meals] Deleted meal {meal_id}, recalculated totals for {meal_date}")
                        return True

                    await conn.rollback()
                    return False

                except Exception as e:
                    await conn.rollback()
                    raise

    except Exception as e:
        logger.exception(f"Error deleting meal {meal_id}: {e}")
        return False


async def get_nutrition_stats(user_id: int, days: int = 7) -> Dict:
    """
    Получает статистику по питанию за период
    
    Args:
        user_id: Telegram ID
        days: Количество дней назад
        
    Returns:
        Dict со статистикой
    """
    try:
        from app.services.user import get_user_by_id
        user = await get_user_by_id(user_id)
        tz = pytz.timezone(user.get("timezone", "Europe/Moscow"))
        
        today = datetime.now(tz).date()
        start_date = today - timedelta(days=days - 1)
        
        # Получаем данные за период
        daily_stats = await mysql.fetchall(
            """SELECT 
                date,
                total_calories,
                total_protein,
                total_fat,
                total_carbs,
                meals_count
            FROM daily_totals
            WHERE tg_id = %s 
            AND date BETWEEN %s AND %s
            ORDER BY date""",
            (user_id, start_date, today)
        )
        
        if not daily_stats:
            return {
                "period_days": days,
                "days_tracked": 0,
                "avg_calories": 0,
                "avg_protein": 0,
                "avg_fat": 0,
                "avg_carbs": 0,
                "total_meals": 0
            }
        
        # Считаем средние значения
        total_cal = sum(float(d["total_calories"]) for d in daily_stats)
        total_protein = sum(float(d["total_protein"]) for d in daily_stats)
        total_fat = sum(float(d["total_fat"]) for d in daily_stats)
        total_carbs = sum(float(d["total_carbs"]) for d in daily_stats)
        total_meals = sum(d["meals_count"] for d in daily_stats)
        
        days_count = len(daily_stats)
        
        return {
            "period_days": days,
            "days_tracked": days_count,
            "avg_calories": round(total_cal / days_count, 1),
            "avg_protein": round(total_protein / days_count, 1),
            "avg_fat": round(total_fat / days_count, 1),
            "avg_carbs": round(total_carbs / days_count, 1),
            "total_meals": total_meals,
            "daily_stats": daily_stats
        }
        
    except Exception as e:
        logger.exception(f"Error getting nutrition stats: {e}")
        return {}



async def delete_multiple_meals(meal_ids: list, user_id: int) -> int:
    """Удаляет несколько приемов пищи и пересчитывает daily_totals"""
    if not meal_ids:
        logger.warning("delete_multiple_meals called with empty meal_ids")
        return 0

    try:
        async with mysql.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await conn.begin()
                try:
                    placeholders = ', '.join(['%s'] * len(meal_ids))

                    # Получаем даты для пересчёта
                    await cur.execute(
                        f"""SELECT DISTINCT meal_date
                        FROM meals_history
                        WHERE id IN ({placeholders}) AND tg_id = %s""",
                        (*meal_ids, user_id)
                    )
                    dates_to_recalculate = await cur.fetchall()

                    # Удаляем приемы пищи
                    await cur.execute(
                        f"""DELETE FROM meals_history
                        WHERE id IN ({placeholders}) AND tg_id = %s""",
                        (*meal_ids, user_id)
                    )
                    deleted_count = cur.rowcount

                    # Пересчитываем daily_totals
                    if deleted_count > 0:
                        for date_row in dates_to_recalculate:
                            await _recalculate_daily_totals(cur, user_id, date_row["meal_date"])

                    await conn.commit()

                    # Инвалидируем кэш после коммита
                    if deleted_count > 0:
                        from app.db.redis_client import redis
                        for date_row in dates_to_recalculate:
                            cache_key = f"meals:summary:{user_id}:{date_row['meal_date']}"
                            await redis.delete(cache_key)

                    logger.info(f"[Meals] Deleted {deleted_count} meals for user {user_id}")
                    return deleted_count

                except Exception as e:
                    await conn.rollback()
                    raise

    except Exception as e:
        logger.exception(f"Error deleting multiple meals: {e}")
        return 0




async def get_food_history(user_id: int, user_tz: str = "Europe/Moscow", days: int = 7) -> List[Dict]:
    """
    Получает историю питания за N дней
    
    Args:
        user_id: Telegram ID пользователя
        user_tz: Часовой пояс пользователя
        days: Количество дней (по умолчанию 7)
        
    Returns:
        List[Dict] с данными по каждому дню:
        - date: дата (date object)
        - date_formatted: форматированная дата "Сегодня", "Вчера", "8 ноября, ЧТ"
        - total_calories, total_protein, total_fat, total_carbs: итоги
        - meals_count: количество приемов
        - meals: список приемов пищи (только для сегодня)
    """
    try:
        tz = pytz.timezone(user_tz)
        today = datetime.now(tz).date()
        start_date = today - timedelta(days=days - 1)
        
        # Получаем дневные итоги
        daily_data = await mysql.fetchall(
            """SELECT 
                date,
                total_calories,
                total_protein,
                total_fat,
                total_carbs,
                meals_count
            FROM daily_totals
            WHERE tg_id = %s 
            AND date BETWEEN %s AND %s
            ORDER BY date DESC""",
            (user_id, start_date, today)
        )
        
        if not daily_data:
            return []
        
        result = []
        weekdays = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"]
        
        for idx, day in enumerate(daily_data):
            date_obj = day["date"]
            
            # Форматирование даты
            if date_obj == today:
                date_formatted = f"Сегодня, {date_obj.strftime('%d %B')}"
            elif date_obj == today - timedelta(days=1):
                date_formatted = f"Вчера, {date_obj.strftime('%d %B')}"
            else:
                weekday = weekdays[date_obj.weekday()]
                date_formatted = f"{date_obj.strftime('%d %B')}, {weekday}"
            
            day_dict = {
                "date": date_obj,
                "date_formatted": date_formatted,
                "total_calories": day["total_calories"],
                "total_protein": day["total_protein"],
                "total_fat": day["total_fat"],
                "total_carbs": day["total_carbs"],
                "meals_count": day["meals_count"],
                "meals": []
            }
            
            # Для сегодня получаем список приемов
            if idx == 0:  # Сегодняшний день
                meals = await mysql.fetchall(
                    """SELECT * FROM meals_history
                    WHERE tg_id = %s AND meal_date = %s
                    ORDER BY meal_datetime""",
                    (user_id, date_obj)
                )
                day_dict["meals"] = meals or []
            
            result.append(day_dict)
        
        return result
        
    except Exception as e:
        logger.exception(f"Error getting food history for user {user_id}: {e}")
        return []


async def get_day_details(user_id: int, user_tz: str, day_index: int) -> Dict:
    """
    Получает детали конкретного дня
    
    Args:
        user_id: Telegram ID пользователя
        user_tz: Часовой пояс
        day_index: Индекс дня (1 = вчера, 2 = позавчера, ...)
        
    Returns:
        Dict с данными дня и списком приемов пищи
    """
    try:
        tz = pytz.timezone(user_tz)
        today = datetime.now(tz).date()
        target_date = today - timedelta(days=day_index)
        
        # Получаем итоги дня
        totals = await mysql.fetchone(
            "SELECT * FROM daily_totals WHERE tg_id = %s AND date = %s",
            (user_id, target_date)
        )
        
        if not totals:
            return None
        
        # Получаем приемы пищи
        meals = await mysql.fetchall(
            """SELECT * FROM meals_history
            WHERE tg_id = %s AND meal_date = %s
            ORDER BY meal_datetime""",
            (user_id, target_date)
        )
        
        # Форматируем дату
        weekdays = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"]
        
        if target_date == today - timedelta(days=1):
            date_formatted = f"Вчера, {target_date.strftime('%d %B')}"
        else:
            weekday = weekdays[target_date.weekday()]
            date_formatted = f"{target_date.strftime('%d %B')}, {weekday}"
        
        return {
            "date": target_date,
            "date_formatted": date_formatted,
            "total_calories": totals["total_calories"],
            "total_protein": totals["total_protein"],
            "total_fat": totals["total_fat"],
            "total_carbs": totals["total_carbs"],
            "meals_count": totals["meals_count"],
            "meals": meals or []
        }
        
    except Exception as e:
        logger.exception(f"Error getting day details: {e}")
        return None


async def get_week_stats(user_id: int, user_tz: str = "Europe/Moscow") -> Dict:
    """
    Получает статистику за неделю для профиля
    
    Args:
        user_id: Telegram ID пользователя
        user_tz: Часовой пояс
        
    Returns:
        Dict со статистикой:
        - days_tracked: количество дней с записями
        - avg_calories: средние калории в день
        - total_meals: общее количество приемов
    """
    try:
        tz = pytz.timezone(user_tz)
        today = datetime.now(tz).date()
        start_date = today - timedelta(days=6)
        
        # Получаем данные за неделю
        daily_stats = await mysql.fetchall(
            """SELECT 
                total_calories,
                meals_count
            FROM daily_totals
            WHERE tg_id = %s 
            AND date BETWEEN %s AND %s
            ORDER BY date""",
            (user_id, start_date, today)
        )
        
        if not daily_stats:
            return {
                "days_tracked": 0,
                "avg_calories": 0,
                "total_meals": 0
            }
        
        # Считаем средние значения
        total_cal = sum(float(d["total_calories"]) for d in daily_stats)
        total_meals = sum(d["meals_count"] for d in daily_stats)
        days_count = len(daily_stats)
        
        return {
            "days_tracked": days_count,
            "avg_calories": round(total_cal / days_count, 1) if days_count > 0 else 0,
            "total_meals": total_meals
        }
        
    except Exception as e:
        logger.exception(f"Error getting week stats: {e}")
        return {
            "days_tracked": 0,
            "avg_calories": 0,
            "total_meals": 0
        }
        
async def get_day_meals(user_id: int, date_str: str, user_tz: str = "Europe/Moscow") -> Dict:
    """
    Получает приемы пищи для конкретного дня
    
    Args:
        user_id: Telegram ID пользователя
        date_str: Дата в формате "YYYY-MM-DD"
        user_tz: Часовой пояс
        
    Returns:
        Dict с данными дня и списком приемов пищи
    """
    try:
        # Парсим дату из строки
        target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        
        # Получаем итоги дня
        totals = await mysql.fetchone(
            "SELECT * FROM daily_totals WHERE tg_id = %s AND date = %s",
            (user_id, target_date)
        )
        
        if not totals:
            return None
        
        # Получаем приемы пищи
        meals = await mysql.fetchall(
            """SELECT * FROM meals_history
            WHERE tg_id = %s AND meal_date = %s
            ORDER BY meal_datetime""",
            (user_id, target_date)
        )
        
        # Форматируем дату
        tz = pytz.timezone(user_tz)
        today = datetime.now(tz).date()
        weekdays = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"]
        
        if target_date == today:
            date_formatted = f"Сегодня, {target_date.strftime('%d %B')}"
        elif target_date == today - timedelta(days=1):
            date_formatted = f"Вчера, {target_date.strftime('%d %B')}"
        else:
            weekday = weekdays[target_date.weekday()]
            date_formatted = f"{target_date.strftime('%d %B')}, {weekday}"
        
        return {
            "date": target_date,
            "date_formatted": date_formatted,
            "total_calories": totals["total_calories"],
            "total_protein": totals["total_protein"],
            "total_fat": totals["total_fat"],
            "total_carbs": totals["total_carbs"],
            "meals_count": totals["meals_count"],
            "meals": meals or []
        }
        
    except Exception as e:
        logger.exception(f"Error getting day meals: {e}")
        return None        


async def get_today_meals(user_id: int, user_tz: str = "Europe/Moscow", limit: int = None) -> list:
    """
    Получает приемы пищи за сегодняшний день
    
    Args:
        user_id: Telegram ID пользователя
        user_tz: Часовой пояс
        limit: Ограничение количества (опционально)
        
    Returns:
        List[Dict] с приемами пищи
    """
    try:
        tz = pytz.timezone(user_tz)
        today = datetime.now(tz).date()
        
        if limit:
            query = """SELECT * FROM meals_history
                      WHERE tg_id = %s AND meal_date = %s
                      ORDER BY meal_datetime DESC
                      LIMIT %s"""
            meals = await mysql.fetchall(query, (user_id, today, limit))
        else:
            query = """SELECT * FROM meals_history
                      WHERE tg_id = %s AND meal_date = %s
                      ORDER BY meal_datetime"""
            meals = await mysql.fetchall(query, (user_id, today))
        
        return meals or []
        
    except Exception as e:
        logger.exception(f"Error getting today meals for user {user_id}: {e}")
        return []


def format_meal_time(meal_datetime: datetime, user_tz: str = "Europe/Moscow") -> str:
    """
    Форматирует время приема пищи
    
    Args:
        meal_datetime: Datetime объект
        user_tz: Часовой пояс
        
    Returns:
        Строка формата "14:30"
    """
    try:
        if isinstance(meal_datetime, datetime):
            tz = pytz.timezone(user_tz)
            localized = meal_datetime.astimezone(tz)
            return localized.strftime("%H:%M")
        return "00:00"
    except Exception as e:
        logger.error(f"Error formatting meal time: {e}")
        return "00:00"

async def get_last_meal(user_id: int, user_tz: str = "Europe/Moscow"):
    """
    Получает последний прием пищи за сегодня
    
    Returns:
        Dict с данными приема или None
    """
    try:
        tz = pytz.timezone(user_tz)
        today = datetime.now(tz).date()
        
        meal = await mysql.fetchone(
            """SELECT * FROM meals_history
            WHERE tg_id = %s AND meal_date = %s
            ORDER BY meal_datetime DESC
            LIMIT 1""",
            (user_id, today)
        )
        
        return meal
        
    except Exception as e:
        logger.exception(f"Error getting last meal for user {user_id}: {e}")
        return None


async def update_meal(
    meal_id: int,
    user_id: int,
    food_name: str = None,
    weight_grams: int = None,
    calories: float = None,
    protein: float = None,
    fat: float = None,
    carbs: float = None
):
    """
    Обновляет прием пищи в БД
    
    Args:
        meal_id: ID приема пищи
        user_id: ID пользователя (для проверки прав)
        food_name, weight_grams, calories, protein, fat, carbs: Новые значения
    """
    try:
        from decimal import Decimal
        
        async with mysql.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await conn.begin()
                
                try:
                    # Проверяем принадлежность приема пользователю
                    await cur.execute(
                        "SELECT meal_date FROM meals_history WHERE id = %s AND tg_id = %s FOR UPDATE",
                        (meal_id, user_id)
                    )
                    
                    result = await cur.fetchone()
                    if not result:
                        logger.warning(f"[Meals] Meal {meal_id} not found or access denied for user {user_id}")
                        return False
                    
                    meal_date = result["meal_date"]
                    
                    # Обновляем прием пищи
                    update_fields = []
                    values = []
                    
                    if food_name is not None:
                        update_fields.append("food_name = %s")
                        values.append(food_name[:255])
                    
                    if weight_grams is not None:
                        update_fields.append("weight_grams = %s")
                        values.append(int(weight_grams))
                    
                    if calories is not None:
                        update_fields.append("calories = %s")
                        values.append(Decimal(str(calories)))
                    
                    if protein is not None:
                        update_fields.append("protein = %s")
                        values.append(Decimal(str(protein)))
                    
                    if fat is not None:
                        update_fields.append("fat = %s")
                        values.append(Decimal(str(fat)))
                    
                    if carbs is not None:
                        update_fields.append("carbs = %s")
                        values.append(Decimal(str(carbs)))
                    
                    if not update_fields:
                        logger.warning(f"[Meals] No fields to update for meal {meal_id}")
                        return False
                    
                    values.extend([meal_id, user_id])
                    
                    await cur.execute(
                        f"""UPDATE meals_history 
                        SET {', '.join(update_fields)}
                        WHERE id = %s AND tg_id = %s""",
                        values
                    )
                    
                    # Пересчитываем итоги дня
                    await cur.execute(
                        """INSERT INTO daily_totals 
                            (tg_id, date, total_calories, total_protein, 
                             total_fat, total_carbs, meals_count)
                        SELECT 
                            tg_id, 
                            meal_date,
                            SUM(calories), 
                            SUM(protein), 
                            SUM(fat), 
                            SUM(carbs), 
                            COUNT(*)
                        FROM meals_history
                        WHERE tg_id = %s AND meal_date = %s
                        GROUP BY tg_id, meal_date
                        ON DUPLICATE KEY UPDATE
                            total_calories = VALUES(total_calories),
                            total_protein = VALUES(total_protein),
                            total_fat = VALUES(total_fat),
                            total_carbs = VALUES(total_carbs),
                            meals_count = VALUES(meals_count)""",
                        (user_id, meal_date)
                    )
                    
                    await conn.commit()
                    
                    logger.info(f"✅ Updated meal {meal_id} for user {user_id}")
                    
                    # Инвалидируем кэш
                    from app.db.redis_client import redis
                    cache_key = f"meals:summary:{user_id}:{meal_date}"
                    await redis.delete(cache_key)
                    
                    return True
                    
                except Exception as e:
                    await conn.rollback()
                    logger.exception(f"Error updating meal {meal_id}: {e}")
                    raise
                    
    except Exception as e:
        logger.exception(f"Critical error in update_meal: {e}")
        return False    