from datetime import datetime, date
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
        Dict с обновленными итогами дня
    """
    try:
        # Получаем текущее время в timezone пользователя
        tz = pytz.timezone(user_tz)
        now = datetime.now(tz)
        today = now.date()
        
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
                        f"on {today}"
                    )
                    
                    # Получаем обновленные итоги
                    return await get_today_summary(user_id, user_tz)
                    
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
        
        from datetime import timedelta
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


async def delete_meal(meal_id: int, user_id: int) -> bool:
    """
    Удаляет прием пищи и пересчитывает итоги дня
    
    Returns:
        bool - успешно ли удалено
    """
    try:
        async with mysql.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await conn.begin()
                
                try:
                    # Получаем дату удаляемого приема
                    meal = await mysql.fetchone(
                        "SELECT meal_date FROM meals_history WHERE id = %s AND tg_id = %s",
                        (meal_id, user_id)
                    )
                    
                    if not meal:
                        return False
                    
                    meal_date = meal["meal_date"]
                    
                    # Удаляем прием пищи
                    await cur.execute(
                        "DELETE FROM meals_history WHERE id = %s AND tg_id = %s",
                        (meal_id, user_id)
                    )
                    
                    if cur.rowcount == 0:
                        await conn.rollback()
                        return False
                    
                    # Пересчитываем итоги дня
                    await cur.execute(
                        """INSERT INTO daily_totals 
                            (tg_id, date, total_calories, total_protein, 
                             total_fat, total_carbs, meals_count)
                        SELECT 
                            tg_id, 
                            meal_date,
                            COALESCE(SUM(calories), 0), 
                            COALESCE(SUM(protein), 0), 
                            COALESCE(SUM(fat), 0), 
                            COALESCE(SUM(carbs), 0), 
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
                    logger.info(f"✅ Deleted meal {meal_id} for user {user_id}")
                    return True
                    
                except Exception as e:
                    await conn.rollback()
                    logger.exception(f"Error deleting meal: {e}")
                    raise
                    
    except Exception as e:
        logger.exception(f"Critical error in delete_meal: {e}")
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
        from datetime import timedelta
        import pytz
        
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
    
    
async def parse_gpt_response(response: str) -> Dict:
    """
    Парсит JSON-ответ от GPT и валидирует данные
    
    ИСПРАВЛЕНИЕ: Если items пустой - это специальный случай (не еда)
    """
    try:
        response = response.strip()
        
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
        
        data = json.loads(response)
        
        if "items" not in data:
            raise MealParseError("Отсутствует поле 'items' в ответе")
        
        if not isinstance(data["items"], list):
            raise MealParseError("Поле 'items' должно быть массивом")
        
        # ИСПРАВЛЕНИЕ: Пустой массив = не еда
        if len(data["items"]) == 0:
            # Проверяем notes - возможно это намеренно (не еда)
            notes = data.get("notes", "")
            if "не продукт" in notes.lower() or "не еда" in notes.lower():
                # Это валидный ответ "не еда" - возвращаем с флагом
                data["is_not_food"] = True
                return data
            else:
                raise MealParseError("Массив 'items' пуст - не удалось определить продукт")
        
        # Остальная валидация как раньше...
        for idx, item in enumerate(data["items"]):
            required_fields = ["name", "weight_grams", "calories", "protein", "fat", "carbs"]
            
            for field in required_fields:
                if field not in item:
                    raise MealParseError(f"Отсутствует поле '{field}' в элементе {idx}")
            
            try:
                weight = float(item["weight_grams"])
                calories = float(item["calories"])
                protein = float(item["protein"])
                fat = float(item["fat"])
                carbs = float(item["carbs"])
                
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
                
                calculated_cal = (protein * 4) + (fat * 9) + (carbs * 4)
                if abs(calories - calculated_cal) > calculated_cal * 0.3:
                    logger.warning(
                        f"Suspicious calories for {item['name']}: "
                        f"stated={calories}, calculated={calculated_cal:.1f}"
                    )
                
                item["weight_grams"] = weight
                item["calories"] = calories
                item["protein"] = protein
                item["fat"] = fat
                item["carbs"] = carbs
                
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

async def delete_multiple_meals(meal_ids: list[int], user_id: int) -> int:
    """
    Удаляет несколько приемов пищи и пересчитывает итоги
    
    Returns:
        int - количество удаленных приемов
    """
    if not meal_ids:
        return 0
    
    try:
        async with mysql.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await conn.begin()
                
                try:
                    # Получаем даты всех удаляемых приемов
                    placeholders = ','.join(['%s'] * len(meal_ids))
                    query = f"""SELECT DISTINCT meal_date FROM meals_history 
                               WHERE id IN ({placeholders}) AND tg_id = %s"""
                    
                    await cur.execute(query, (*meal_ids, user_id))
                    dates = await cur.fetchall()
                    
                    if not dates:
                        await conn.rollback()
                        return 0
                    
                    # Удаляем приемы пищи
                    delete_query = f"""DELETE FROM meals_history 
                                      WHERE id IN ({placeholders}) AND tg_id = %s"""
                    await cur.execute(delete_query, (*meal_ids, user_id))
                    deleted_count = cur.rowcount
                    
                    if deleted_count == 0:
                        await conn.rollback()
                        return 0
                    
                    # Пересчитываем итоги для всех затронутых дат
                    for date_row in dates:
                        meal_date = date_row["meal_date"]
                        
                        await cur.execute(
                            """INSERT INTO daily_totals 
                                (tg_id, date, total_calories, total_protein, 
                                 total_fat, total_carbs, meals_count)
                            SELECT 
                                tg_id, 
                                meal_date,
                                COALESCE(SUM(calories), 0), 
                                COALESCE(SUM(protein), 0), 
                                COALESCE(SUM(fat), 0), 
                                COALESCE(SUM(carbs), 0), 
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
                    logger.info(f"✅ Deleted {deleted_count} meals for user {user_id}")
                    return deleted_count
                    
                except Exception as e:
                    await conn.rollback()
                    logger.exception(f"Error deleting multiple meals: {e}")
                    raise
                    
    except Exception as e:
        logger.exception(f"Critical error in delete_multiple_meals: {e}")
        return 0    