import logging
from app.db.mysql import mysql
from app.services.payments_logic import try_autopay

logger = logging.getLogger(__name__)

async def try_all_autopays(ctx):  # добавили ctx
    logger.info("[Task] Запуск задачи автоплатежей...")
    try:
        users = await mysql.fetchall("""
            SELECT tg_id, expiration_date, payment_method_id,
                   last_subscription_days, last_subscription_amount, failed_autopay_attempts
            FROM users_tbl
            WHERE payment_method_id IS NOT NULL
        """)

        if not users:
            logger.info("[Task] Нет пользователей с активными автоплатежами. Пропускаем.")
            return

        logger.info(f"[Task] Найдено {len(users)} пользователей для автосписания.")
        for user in users:
            try:
                await try_autopay(user)
            except Exception as e:
                logger.error(f"[AutoPay Task] Ошибка при автосписании TG ID={user['tg_id']}: {e}", exc_info=True)

        logger.info("[Task] Задача автоплатежей завершена.")
    except Exception as e:
        logger.exception(f"[AutoPay Task] Критическая ошибка: {e}")
