import logging
from app.db.mysql import mysql
from app.services.payments_logic import try_autopay

logger = logging.getLogger(__name__)


async def try_all_autopays(ctx):
    """
    Проверяет всех пользователей с автоплатежами и пытается продлить подписку
    
    Вызывается:
    - При старте приложения (с блокировкой)
    - По крону каждый день в 03:10 UTC
    """
    logger.info("[Task] Запуск задачи автоплатежей...")
    
    try:
        users = await mysql.fetchall(
            """SELECT tg_id, expiration_date, payment_method_id, email,
                      last_subscription_days, last_subscription_amount, 
                      failed_autopay_attempts
               FROM users_tbl
               WHERE payment_method_id IS NOT NULL"""
        )

        if not users:
            logger.info("[Task] Нет пользователей с активными автоплатежами")
            return

        logger.info(f"[Task] Найдено {len(users)} пользователей для проверки")
        
        success_count = 0
        for user in users:
            try:
                await try_autopay(user)
                success_count += 1
            except Exception as e:
                logger.error(
                    f"[AutoPay Task] Ошибка при автосписании "
                    f"TG ID={user['tg_id']}: {e}",
                    exc_info=True
                )

        logger.info(
            f"[Task] Задача автоплатежей завершена: "
            f"проверено {len(users)}, обработано {success_count}"
        )
        
    except Exception as e:
        logger.exception(f"[AutoPay Task] Критическая ошибка: {e}")