# app/services/user.py
from app.db.mysql import mysql
from datetime import datetime, timedelta
from app.config import settings
import logging
import re
logger = logging.getLogger(__name__)


# Количество бесплатных токенов для новых пользователей и неверифицированных
FREE_TOKENS_COUNT = 5
# Количество токенов для подписчиков
SUBSCRIBED_TOKENS_COUNT = 25

async def get_user_by_id(user_id: int):
    """Получить информацию о пользователе по его Telegram ID."""
    try:
        return await mysql.fetchone("SELECT * FROM users_tbl WHERE tg_id=%s", (user_id,))
    except Exception as e:
        logger.error(f"Ошибка при получении пользователя {user_id}: {e}")
        raise


async def get_or_create_user(tg_id: int, tg_name: str):
    user = await get_user_by_id(tg_id)
    
    if not user:
        logger.info(f"Создаем нового пользователя: TG ID={tg_id}, Name={tg_name}")
        try:
            await mysql.execute(
                "INSERT INTO users_tbl (tg_id, tg_name, free_tokens) VALUES (%s, %s, %s)",
                (tg_id, tg_name, FREE_TOKENS_COUNT)
            )
            user = await get_user_by_id(tg_id)
            logger.info(f"Новый пользователь {tg_id} успешно создан с {FREE_TOKENS_COUNT} токенами.")
        except Exception as e:
            logger.error(f"Ошибка при создании нового пользователя {tg_id}: {e}")
            raise

    # Защитная проверка с UPDATE только если дата точно устарела
    if user.get("expiration_date") and user["expiration_date"] < datetime.now().date():
        # Перепроверим из базы перед сбросом
        fresh_user = await get_user_by_id(tg_id)
        if fresh_user["expiration_date"] and fresh_user["expiration_date"] < datetime.now().date():
            logger.info(f"[Подписка] У {tg_id} истек срок. Обнуляем expiration_date.")
            await mysql.execute("UPDATE users_tbl SET expiration_date = NULL WHERE tg_id = %s", (tg_id,))
            user["expiration_date"] = None
        else:
            # Обновилась в это время – используем свежую
            user["expiration_date"] = fresh_user["expiration_date"]

    return user

async def deduct_token(user_id: int) -> bool:
    """
    Списать 1 токен у пользователя.
    Возвращает True, если токен был списан, False в противном случае (если токенов нет).
    """
    user = await get_user_by_id(user_id)
    if not user:
        logger.warning(f"Попытка списать токен у несуществующего пользователя: {user_id}")
        return False

    current_tokens = user.get("free_tokens", 0)
    if current_tokens > 0:
        try:
            await mysql.execute(
                "UPDATE users_tbl SET free_tokens = free_tokens - 1 WHERE tg_id=%s",
                (user_id,)
            )
            logger.info(f"Токен списан у пользователя {user_id}. Осталось: {current_tokens - 1}")
            return True
        except Exception as e:
            logger.error(f"Ошибка при списании токена у пользователя {user_id}: {e}")
            raise
    else:
        logger.info(f"Недостаточно токенов у пользователя {user_id}. Текущие токены: {current_tokens}.")
        return False

async def extend_subscription(user_id: int, days: int, method_id: str | None, amount: float):
    user = await get_user_by_id(user_id)
    if not user:
        logger.error(f"Попытка продлить подписку несуществующему пользователю: {user_id}")
        return
    current_expiration = user.get("expiration_date")
    today = datetime.now().date()

    if current_expiration and current_expiration >= today:
        new_exp_date = current_expiration + timedelta(days=days)
        logger.info(f"Продление существующей подписки для {user_id}. Старая дата: {current_expiration}, Новая дата: {new_exp_date}")
    else:
        new_exp_date = today + timedelta(days=days)
        logger.info(f"Активация новой подписки для {user_id}. Дата истечения: {new_exp_date}")

    try:
        await mysql.execute("""
            UPDATE users_tbl
            SET free_tokens=%s,
                expiration_date=%s,
                payment_method_id=%s,
                last_subscription_days=%s,
                last_subscription_amount=%s,
                failed_autopay_attempts=0
            WHERE tg_id=%s
        """, (SUBSCRIBED_TOKENS_COUNT, new_exp_date, method_id, days, amount, user_id))
        logger.info(f"Подписка для пользователя {user_id} успешно обновлена до {new_exp_date}. Токены установлены в {SUBSCRIBED_TOKENS_COUNT}.")
    except Exception as e:
        logger.error(f"Ошибка при продлении/активации подписки для пользователя {user_id}: {e}")
        raise

async def block_autopay(user_id: int):
    """
    Блокирует автоплатёж для пользователя, устанавливая payment_method_id в NULL
    и сбрасывая счётчик неудачных попыток до максимального значения, чтобы предотвратить дальнейшие попытки.
    """
    try:
        await mysql.execute("""
            UPDATE users_tbl
            SET payment_method_id=NULL, failed_autopay_attempts=%s
            WHERE tg_id=%s
        """, (settings.max_failed_autopay_attempts, user_id,))
        logger.info(f"Автоплатёж для пользователя {user_id} заблокирован.")
    except Exception as e:
        logger.error(f"Ошибка при блокировке автоплатежа для пользователя {user_id}: {e}")
        raise
    
async def update_tokens_daily():
    logger.info("Запуск ежедневного обновления токенов...")
    try:
        today = datetime.now().date()

        # Обновляем токены только для пользователей с активной подпиской
        await mysql.execute(
            """
            UPDATE users_tbl 
            SET free_tokens = %s 
            WHERE expiration_date IS NOT NULL 
            AND expiration_date >= %s
            """,
            (SUBSCRIBED_TOKENS_COUNT, today)
        )

        result = await mysql.fetchall("SELECT ROW_COUNT() as rows")
        updated_rows = result[0]["rows"]

        logger.info(f"Ежедневное обновление токенов завершено. Обновлено {updated_rows} записей.")
    except Exception as e:
        logger.error(f"Ошибка при выполнении ежедневного обновления токенов: {e}", exc_info=True)
        raise

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

async def set_user_email(user_id: int, email: str) -> None:
    if not EMAIL_RE.match(email):
        raise ValueError("Некорректный e-mail")
    await mysql.execute(
        "UPDATE users_tbl SET email=%s, email_confirmed=1 WHERE tg_id=%s",
        (email.strip(), user_id),
    )