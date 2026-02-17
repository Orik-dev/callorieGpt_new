import logging
from app.db.mysql import mysql
from app.db.redis_client import redis
from app.services.payments_logic import try_autopay

logger = logging.getLogger(__name__)

LOCK_TTL = 300  # 5 минут — максимальное время выполнения


async def try_all_autopays(ctx):
    """
    Проверяет всех пользователей с автоплатежами и пытается продлить подписку

    Вызывается по крону каждый день в 03:10 UTC.
    Distributed lock предотвращает двойное выполнение при нескольких воркерах.
    """
    lock_key = "lock:try_all_autopays"
    acquired = await redis.set(lock_key, "1", ex=LOCK_TTL, nx=True)
    if not acquired:
        logger.info("[Task] Автоплатежи уже выполняются другим воркером, пропускаем")
        return

    logger.info("[Task] Запуск задачи автоплатежей...")
    
    try:
        users = await mysql.fetchall(
            """SELECT tg_id, expiration_date, payment_method_id, email,
                      last_subscription_days, last_subscription_amount,
                      failed_autopay_attempts, timezone
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
    finally:
        await redis.delete(lock_key)