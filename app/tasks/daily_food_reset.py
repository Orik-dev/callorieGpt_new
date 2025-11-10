import logging
from datetime import datetime, timedelta
from app.db.mysql import mysql

logger = logging.getLogger(__name__)


async def reset_daily_food(ctx):
    """
    Удаляет записи о еде старше 7 дней
    
    Запускается ежедневно в 03:00 МСК (00:00 UTC)
    
    Очищает:
    - meals_history - старше 7 дней
    - daily_totals - старше 7 дней
    
    Оставляет последние 7 дней для просмотра в /food
    """
    logger.info("[Task] Запуск ежедневной очистки старой еды...")
    
    try:
        # Вычисляем дату 7 дней назад
        cutoff_date = datetime.now().date() - timedelta(days=7)
        
        async with mysql.pool.acquire() as conn:
            async with conn.cursor() as cur:
                # Удаляем meals_history старше 7 дней
                await cur.execute(
                    "DELETE FROM meals_history WHERE meal_date < %s",
                    (cutoff_date,)
                )
                meals_deleted = cur.rowcount
                
                # Удаляем daily_totals старше 7 дней
                await cur.execute(
                    "DELETE FROM daily_totals WHERE date < %s",
                    (cutoff_date,)
                )
                totals_deleted = cur.rowcount
        
        logger.info(
            f"✅ [Task] Очистка завершена: удалено {meals_deleted} приемов пищи "
            f"и {totals_deleted} дневных итогов (старше {cutoff_date})"
        )
        
    except Exception as e:
        logger.exception(f"❌ [Task] Ошибка при очистке старой еды: {e}")