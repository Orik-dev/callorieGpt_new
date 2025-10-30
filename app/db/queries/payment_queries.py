# app/db/queries/payment_queries.py
from app.db.mysql import mysql
import logging

logger = logging.getLogger(__name__)

# 📦 Сохранить платёж в БД
async def save_payment(user_id: int, status: str, payment_id: str, method_id: str | None, amount: float, days: int):
    """Сохраняет информацию о платеже в payment_tbl."""
    try:
        await mysql.execute("""
            INSERT INTO payment_tbl (tg_id, status, payment_id, method_id, amount, days)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (user_id, status, payment_id, method_id, amount, days))
        logger.info(f"Платёж {payment_id} для пользователя {user_id} сохранён со статусом '{status}'.")
    except Exception as e:
        logger.error(f"Ошибка при сохранении платежа {payment_id} для пользователя {user_id}: {e}")
        raise

# 📥 Получить платёж по ID
async def get_payment_by_id(payment_id: str):
    """Получает информацию о платеже по его ID."""
    try:
        return await mysql.fetchone("SELECT * FROM payment_tbl WHERE payment_id=%s", (payment_id,))
    except Exception as e:
        logger.error(f"Ошибка при получении платежа по ID {payment_id}: {e}")
        raise

# ❌ Удалить платёж
async def delete_payment(payment_id: str):
    """Удаляет платёж из payment_tbl."""
    try:
        await mysql.execute("DELETE FROM payment_tbl WHERE payment_id=%s", (payment_id,))
        logger.info(f"Платёж {payment_id} удалён из БД.")
    except Exception as e:
        logger.error(f"Ошибка при удалении платежа {payment_id}: {e}")
        raise

# Обновить статус платежа
async def update_payment_status(payment_id: str, status: str):
    """Обновляет статус существующего платежа."""
    try:
        await mysql.execute(
            "UPDATE payment_tbl SET status=%s WHERE payment_id=%s",
            (status, payment_id)
        )
        logger.info(f"Статус платежа {payment_id} обновлён до '{status}'.")
    except Exception as e:
        logger.error(f"Ошибка при обновлении статуса платежа {payment_id} до '{status}': {e}")
        raise
# Получить данные по платежу (дней, сумма, метод)
# app/db/queries/payment_queries.py

# Получить данные по платежу (кол-во дней, сумма, метод оплаты)
async def get_payment_data(payment_id: str):
    try:
        return await mysql.fetchone(
            "SELECT amount, days, method_id FROM payment_tbl WHERE payment_id=%s",
            (payment_id,)
        )
    except Exception as e:
        logger.error(f"Ошибка при получении данных о платеже {payment_id}: {e}")
        raise
