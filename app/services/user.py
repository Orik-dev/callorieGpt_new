from app.db.mysql import mysql
from datetime import datetime, timedelta, date
from app.config import settings
import logging
import re
import pytz

logger = logging.getLogger(__name__)

# Количество токенов
FREE_TOKENS_COUNT = 5        # Для новых/неактивных пользователей
SUBSCRIBED_TOKENS_COUNT = 25  # Для подписчиков

# Улучшенная валидация email
EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')


async def get_user_by_id(user_id: int) -> dict:
    """
    Получить информацию о пользователе по Telegram ID
    
    Returns:
        dict с полями пользователя или None если не найден
    """
    try:
        return await mysql.fetchone(
            "SELECT * FROM users_tbl WHERE tg_id=%s",
            (user_id,)
        )
    except Exception as e:
        logger.error(f"Error fetching user {user_id}: {e}")
        raise


async def get_or_create_user(tg_id: int, tg_name: str) -> dict:
    """
    Получить пользователя или создать нового
    
    При создании выдается FREE_TOKENS_COUNT токенов
    Проверяет актуальность подписки и сбрасывает если истекла
    
    Returns:
        dict с данными пользователя
    """
    user = await get_user_by_id(tg_id)
    
    if not user:
        logger.info(f"Creating new user: TG ID={tg_id}, Name={tg_name}")
        try:
            await mysql.execute(
                """INSERT IGNORE INTO users_tbl (tg_id, tg_name, free_tokens, timezone)
                   VALUES (%s, %s, %s, %s)""",
                (tg_id, tg_name, FREE_TOKENS_COUNT, 'Europe/Moscow')
            )
            user = await get_user_by_id(tg_id)
            logger.info(f"✅ New user {tg_id} created with {FREE_TOKENS_COUNT} tokens")
        except Exception as e:
            logger.error(f"Error creating user {tg_id}: {e}")
            raise
        return user
    
    # Проверка актуальности подписки (только если дата точно устарела)
    exp_date = user.get("expiration_date")
    user_tz = user.get("timezone", "Europe/Moscow")
    try:
        tz = pytz.timezone(user_tz)
    except Exception:
        tz = pytz.timezone("Europe/Moscow")
    today = datetime.now(tz).date()

    if exp_date and exp_date < today:
        # Двойная проверка из БД перед сбросом (защита от race condition)
        fresh_user = await get_user_by_id(tg_id)
        if fresh_user["expiration_date"] and fresh_user["expiration_date"] < today:
            logger.info(f"[Subscription] User {tg_id} subscription expired, resetting")
            async with mysql.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """UPDATE users_tbl 
                           SET expiration_date = NULL, 
                               free_tokens = %s,
                               payment_method_id = NULL
                           WHERE tg_id = %s""",
                        (FREE_TOKENS_COUNT, tg_id)
                    )
            user["expiration_date"] = None
            user["free_tokens"] = FREE_TOKENS_COUNT
        else:
            # Обновилась параллельно - используем свежие данные
            user = fresh_user
    
    return user


async def extend_subscription(
    user_id: int,
    days: int,
    method_id: str | None,
    amount: float
):
    """
    Продлить/активировать подписку пользователя
    
    Args:
        user_id: Telegram ID пользователя
        days: Количество дней подписки
        method_id: ID метода оплаты (для автопродления)
        amount: Сумма платежа
    """
    user = await get_user_by_id(user_id)
    if not user:
        logger.error(f"Cannot extend subscription: user {user_id} not found")
        return
    
    current_expiration = user.get("expiration_date")
    user_tz = user.get("timezone", "Europe/Moscow")
    try:
        tz = pytz.timezone(user_tz)
    except Exception:
        tz = pytz.timezone("Europe/Moscow")
    today = datetime.now(tz).date()

    # Расчет новой даты окончания подписки
    if current_expiration and current_expiration >= today:
        new_exp_date = current_expiration + timedelta(days=days)
        logger.info(
            f"Extending subscription for user {user_id}: "
            f"{current_expiration} → {new_exp_date} (+{days} days)"
        )
    else:
        new_exp_date = today + timedelta(days=days)
        logger.info(
            f"Activating new subscription for user {user_id}: "
            f"expires {new_exp_date} ({days} days)"
        )

    try:
        async with mysql.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """UPDATE users_tbl
                       SET free_tokens=%s,
                           expiration_date=%s,
                           payment_method_id=%s,
                           last_subscription_days=%s,
                           last_subscription_amount=%s,
                           failed_autopay_attempts=0
                       WHERE tg_id=%s""",
                    (
                        SUBSCRIBED_TOKENS_COUNT,
                        new_exp_date,
                        method_id,
                        days,
                        amount,
                        user_id
                    )
                )
        
        logger.info(
            f"✅ Subscription updated for user {user_id}: "
            f"expires {new_exp_date}, tokens={SUBSCRIBED_TOKENS_COUNT}, "
            f"method_id={'set' if method_id else 'none'}"
        )
    except Exception as e:
        logger.error(f"Error extending subscription for user {user_id}: {e}")
        raise


async def block_autopay(user_id: int):
    """
    Блокировать автоплатежи для пользователя
    
    Сбрасывает payment_method_id и устанавливает максимальное
    количество неудачных попыток
    """
    try:
        async with mysql.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """UPDATE users_tbl
                       SET payment_method_id=NULL, 
                           failed_autopay_attempts=%s
                       WHERE tg_id=%s""",
                    (settings.max_failed_autopay_attempts, user_id)
                )
        logger.info(f"✅ Autopay blocked for user {user_id}")
    except Exception as e:
        logger.error(f"Error blocking autopay for user {user_id}: {e}")
        raise


async def update_tokens_daily():
    """
    Ежедневное обновление токенов для ВСЕХ пользователей
    
    НОВАЯ ЛОГИКА:
    - Активная подписка → 25 токенов
    - Без подписки → 5 токенов
    """
    logger.info("📅 Starting daily token reset...")

    try:
        # Используем московское время (основная аудитория)
        msk = pytz.timezone("Europe/Moscow")
        today = datetime.now(msk).date()

        async with mysql.pool.acquire() as conn:
            async with conn.cursor() as cur:
                # 1. Обновляем токены для подписчиков
                await cur.execute(
                    """UPDATE users_tbl 
                       SET free_tokens = %s 
                       WHERE expiration_date IS NOT NULL 
                       AND expiration_date >= %s""",
                    (SUBSCRIBED_TOKENS_COUNT, today)
                )
                subscribed_count = cur.rowcount
                
                # 2. Обновляем токены для бесплатных пользователей
                await cur.execute(
                    """UPDATE users_tbl 
                       SET free_tokens = %s 
                       WHERE expiration_date IS NULL 
                       OR expiration_date < %s""",
                    (FREE_TOKENS_COUNT, today)
                )
                free_count = cur.rowcount

        logger.info(
            f"✅ Daily token reset completed: "
            f"{subscribed_count} subscribed, {free_count} free users"
        )
        
    except Exception as e:
        logger.error(f"❌ Error in daily token reset: {e}", exc_info=True)
        raise

async def refund_token(user_id: int):
    """Возвращает токен при ошибке"""
    try:
        async with mysql.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "UPDATE users_tbl SET free_tokens = free_tokens + 1 WHERE tg_id = %s",
                    (user_id,)
                )
        logger.info(f"[User] Token refunded: user {user_id}")
    except Exception as e:
        logger.error(f"[User] Failed to refund token: {e}")


async def set_user_email(user_id: int, email: str) -> None:
    """
    Установить email пользователя
    
    Args:
        user_id: Telegram ID
        email: Email адрес
        
    Raises:
        ValueError: Если email невалидный
    """
    if not EMAIL_RE.match(email):
        raise ValueError("Invalid email format")
    
    try:
        async with mysql.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """UPDATE users_tbl 
                       SET email=%s, email_confirmed=1 
                       WHERE tg_id=%s""",
                    (email.strip().lower(), user_id)
                )
        logger.info(f"✅ Email set for user {user_id}: {email}")
    except Exception as e:
        logger.error(f"Error setting email for user {user_id}: {e}")
        raise


async def set_user_timezone(user_id: int, timezone: str) -> None:
    """
    Установить часовой пояс пользователя
    
    Args:
        user_id: Telegram ID
        timezone: Название timezone (например, 'Europe/Moscow')
    """
    try:
        # Проверка валидности timezone
        import pytz
        pytz.timezone(timezone)  # Выбросит исключение если невалидный
        
        async with mysql.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "UPDATE users_tbl SET timezone=%s WHERE tg_id=%s",
                    (timezone, user_id)
                )
        logger.info(f"✅ Timezone set for user {user_id}: {timezone}")
    except pytz.exceptions.UnknownTimeZoneError:
        logger.error(f"Invalid timezone: {timezone}")
        raise ValueError(f"Invalid timezone: {timezone}")
    except Exception as e:
        logger.error(f"Error setting timezone for user {user_id}: {e}")
        raise