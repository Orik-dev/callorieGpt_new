import uuid
import asyncio
import logging
from datetime import datetime
from yookassa import Configuration, Payment
import pytz

from app.config import settings
from app.db.queries.payment_queries import save_payment
from app.services.user import extend_subscription, block_autopay, get_user_by_id
from app.db.mysql import mysql

logger = logging.getLogger(__name__)

# Конфигурация YooKassa
Configuration.account_id = settings.yookassa_store_id
Configuration.secret_key = settings.yookassa_secret_key

RETURN_URL = "https://t.me/calories_by_photo_bot"


def _create_payment_payload(
    amount: float,
    description: str,
    user_id: int,
    days: int,
    *,
    return_url: str | None = None,
    method_id: str | None = None,
    force_method: str | None = None,
    customer_email: str | None = None,
) -> dict:
    """
    Формирует payload для YooKassa
    
    Args:
        amount: Сумма платежа
        description: Описание платежа
        user_id: ID пользователя
        days: Количество дней подписки
        return_url: URL возврата после оплаты
        method_id: ID сохраненного метода оплаты (для автосписания)
        force_method: Принудительный метод оплаты
        customer_email: Email для чека (если None - используется заглушка)
    """
    item_desc = (description or "Подписка").strip()[:128]
    email_for_receipt = (customer_email or f"user_{user_id}@example.com").strip()[:254]

    payload: dict = {
        "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
        "capture": True,
        "description": description,
        "metadata": {"user_id": str(user_id), "plan": f"{days}_days"},
        "receipt": {
            "customer": {"email": email_for_receipt},
            "items": [
                {
                    "description": item_desc,
                    "quantity": "1.00",
                    "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
                    "vat_code": 11,
                    "payment_subject": "service",
                    "payment_mode": "full_prepayment",
                    "measure": "piece",
                }
            ],
        },
    }

    # Принудительный метод оплаты
    if force_method in {"bank_card", "sbp", "yoo_money"}:
        payload["payment_method_data"] = {"type": force_method}

    # Рекуррентный платеж
    if method_id:
        payload["payment_method_id"] = method_id

    # Ручная оплата через redirect
    if return_url:
        payload["confirmation"] = {"type": "redirect", "return_url": return_url}
        payload["save_payment_method"] = True

    return payload


async def create_payment(
    user_id: int,
    amount: float,
    description: str,
    days: int,
    *,
    force_method: str | None = None,
    customer_email: str | None = None,
) -> str:
    """
    Создает платеж через YooKassa
    
    Returns:
        str: URL страницы оплаты
    """
    def _create():
        return Payment.create(
            _create_payment_payload(
                amount,
                description,
                user_id,
                days,
                return_url=RETURN_URL,
                force_method=force_method,
                customer_email=customer_email,
            ),
            str(uuid.uuid4()),
        )

    payment = await asyncio.to_thread(_create)

    # Получаем ID метода оплаты если есть
    pm = getattr(payment, "payment_method", None)
    pm_id = getattr(pm, "id", None) if pm else None
    method_id = pm_id if pm_id else None

    # Сохраняем платеж в БД
    await save_payment(
        user_id=user_id,
        status=payment.status,
        payment_id=payment.id,
        method_id=method_id,
        amount=amount,
        days=days,
    )

    logger.info(
        f"✅ Payment created: {payment.id} for user {user_id} "
        f"(amount={amount}, days={days}, method_id={'set' if method_id else 'none'})"
    )

    return payment.confirmation.confirmation_url


async def try_autopay(user: dict):
    """
    Пытается продлить подписку автоматически
    
    Условия:
    - Есть сохраненный payment_method_id
    - Подписка истекла
    - Не превышен лимит неудачных попыток
    """
    method_id = user.get("payment_method_id")
    user_id = int(user["tg_id"])

    if not method_id:
        logger.debug(f"[AutoPay] User {user_id}: no payment_method_id")
        return

    expiration_date = user.get("expiration_date")
    user_tz = user.get("timezone", "Europe/Moscow")
    try:
        tz = pytz.timezone(user_tz)
    except Exception:
        tz = pytz.timezone("Europe/Moscow")
    today = datetime.now(tz).date()

    if expiration_date is not None and expiration_date >= today:
        logger.debug(f"[AutoPay] User {user_id}: subscription still active")
        return

    days = user.get("last_subscription_days", settings.default_subscription_days)
    amount = user.get("last_subscription_amount", settings.default_subscription_amount)
    attempts = int(user.get("failed_autopay_attempts", 0))

    if attempts >= settings.max_failed_autopay_attempts:
        logger.warning(f"[AutoPay] User {user_id}: autopay blocked (max attempts)")
        return

    description = f"АВТОПЛАТЕЖ: {days} дн. / {amount}₽"
    customer_email = user.get("email")

    try:
        def _create():
            return Payment.create(
                _create_payment_payload(
                    amount,
                    description,
                    user_id,
                    days,
                    method_id=method_id,
                    customer_email=customer_email,
                ),
                str(uuid.uuid4()),
            )

        payment = await asyncio.to_thread(_create)

        if payment.status == "succeeded":
            logger.info(f"[AutoPay] ✅ User {user_id} payment succeeded: {payment.id}")
            await extend_subscription(user_id, days, method_id, amount)
            
            async with mysql.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "UPDATE users_tbl SET failed_autopay_attempts = 0 WHERE tg_id=%s",
                        (user_id,),
                    )
        else:
            raise RuntimeError(f"YooKassa status: {payment.status}")

    except Exception as e:
        logger.error(f"[AutoPay] ❌ User {user_id} error: {e}")

        # Задержка перед следующей попыткой (экспоненциальная)
        delay = min(5 * (2 ** attempts), 60)
        await asyncio.sleep(delay)

        async with mysql.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "UPDATE users_tbl SET failed_autopay_attempts = failed_autopay_attempts + 1 WHERE tg_id=%s",
                    (user_id,),
                )
        
        # Проверяем количество попыток
        fresh = await get_user_by_id(user_id)
        new_attempts = int(fresh.get("failed_autopay_attempts", 0))
        
        if new_attempts >= settings.max_failed_autopay_attempts:
            logger.warning(f"[AutoPay] User {user_id}: max attempts reached, blocking autopay")
            await block_autopay(user_id)
            
            # Уведомляем пользователя
            try:
                from app.bot.bot import bot
                await bot.send_message(
                    chat_id=user_id,
                    text=(
                        "❌ Автопродление подписки не удалось выполнить 3 раза подряд.\n\n"
                        "Возможные причины:\n"
                        "• Недостаточно средств на карте\n"
                        "• Карта заблокирована/просрочена\n"
                        "• Банк отклонил операцию\n\n"
                        "Автопродление отключено. Чтобы продолжить пользоваться ботом, "
                        "оформите подписку вручную: /subscribe"
                    ),
                )
            except Exception as notify_error:
                logger.warning(f"[AutoPay] Failed to notify user {user_id}: {notify_error}")


async def activate_subscription_after_payment(
    user_id: int,
    plan_key: str | None = None,
    days: int = 30,
    amount_rub: float | int = 0,
    source: str = "stars",
    external_id: str | None = None,
    amount_stars: int | None = None,
    **kwargs,
):
    """
    Активирует подписку после успешной оплаты (например, Telegram Stars)
    
    Для Stars method_id не сохраняется (None)
    """
    await extend_subscription(
        user_id=user_id,
        days=days,
        method_id=None,
        amount=float(amount_rub or 0),
    )
    
    logger.info(
        f"✅ Subscription activated: user={user_id}, days={days}, "
        f"source={source}, amount={amount_rub}"
    )
    
    return {
        "ok": True,
        "user_id": user_id,
        "days": days,
        "source": source
    }