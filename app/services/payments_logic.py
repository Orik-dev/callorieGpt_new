# import uuid
# import asyncio
# import logging
# from datetime import datetime
# from app.config import settings
# from yookassa import Configuration, Payment
# from app.db.queries.payment_queries import save_payment
# from app.services.user import extend_subscription, block_autopay, get_user_by_id
# from app.db.mysql import mysql

# # 🔐 Настройка API
# Configuration.account_id = settings.yookassa_store_id
# Configuration.secret_key = settings.yookassa_secret_key

# RETURN_URL = "https://t.me/calories_by_photo_bot"
# # RETURN_URL = "https://t.me/callorie_v2_bot"


# def _create_payment_payload(
#     amount,
#     description,
#     user_id,
#     days,
#     return_url=None,
#     method_id=None,
#     force_method: str | None = None,
#     customer_email: str | None = None,   # <— e-mail для чека (если None — подставится заглушка)
# ):
#     """
#     Формирует payload для YooKassa.

#     По умолчанию НЕ задаём payment_method_data, чтобы на странице YooKassa был выбор способа
#     (карта / СБП / ЮMoney и т.д.). Если нужно принудительно открыть конкретный способ,
#     передайте force_method: "bank_card" | "sbp" | "yoo_money".

#     Для рекуррентных платежей (автосписание) передаём method_id (payment_method_id) и НЕ указываем return_url.
#     """
#     item_desc = (description or "Подписка").strip()[:128]
#     email_for_receipt = (customer_email or f"user_{user_id}@example.com").strip()[:254]

#     payload = {
#         "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
#         "capture": True,
#         "description": description,
#         "metadata": {"user_id": str(user_id), "plan": f"{days}_days"},
#         # 🔽 ЧЕК ДЛЯ ИП (54-ФЗ)
#         "receipt": {
#             "customer": {"email": email_for_receipt},
#             "items": [
#                 {
#                     "description": item_desc,
#                     "quantity": "1.00",
#                     "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
#                     "vat_code": 1,                        # без НДС (УСН) — подставь свой при необходимости
#                     "payment_subject": "service",         # услуга (подписка)
#                     "payment_mode": "full_prepayment",    # полная предоплата
#                     "measure": "piece",                   # шт
#                 }
#             ],
#         },
#     }

#     # Экран выбора способа
#     if force_method in {"bank_card", "sbp", "yoo_money"}:
#         payload["payment_method_data"] = {"type": force_method}

#     # Рекуррент через сохранённый метод
#     if method_id:
#         payload["payment_method_id"] = method_id

#     # Подтверждение через редирект — только для «ручной» оплаты
#     if return_url:
#         payload["confirmation"] = {"type": "redirect", "return_url": return_url}
#         payload["save_payment_method"] = True

#     return payload


# def _method_supports_recurring(pm_type: str | None) -> bool:
#     """Возвращает True, если метод можно сохранить для автосписаний."""
#     return pm_type in {"bank_card", "yoo_money"}


# # ✅ Создание платежа (экран YooKassa с ВЫБОРОМ способа)
# #    Если нужно принудительно открыть конкретный способ, передай force_method="bank_card"/"sbp"/"yoo_money"
# async def create_payment(
#     user_id,
#     amount,
#     description,
#     days,
#     *,
#     force_method: str | None = None,
#     customer_email: str | None = None
# ):
#     def _create():
#         return Payment.create(
#             _create_payment_payload(
#                 amount,
#                 description,
#                 user_id,
#                 days,
#                 return_url=RETURN_URL,           # экран YooKassa
#                 force_method=force_method,
#                 customer_email=customer_email,   # <— e-mail попадёт в чек
#             ),
#             str(uuid.uuid4()),  # идемпотентный ключ
#         )

#     payment = await asyncio.to_thread(_create)

#     # Определяем, можно ли сохранить метод оплаты для рекуррента
#     pm = getattr(payment, "payment_method", None)
#     pm_type = getattr(pm, "type", None)
#     pm_id = getattr(pm, "id", None)

#     # сохраняем токен только для поддерживаемых методов
#     method_id = pm_id if (_method_supports_recurring(pm_type) and pm_id) else None

#     await save_payment(
#         user_id=user_id,
#         status=payment.status,
#         payment_id=payment.id,
#         method_id=method_id,
#         amount=amount,
#         days=days,
#     )

#     # вернём ссылку на страницу оплаты/продолжения
#     return payment.confirmation.confirmation_url


# # 🔁 Автосписание (включено)
# async def try_autopay(user: dict):
#     """
#     Пытается продлить подписку, если:
#     - есть сохранённый payment_method_id (карта/ЮMoney),
#     - подписка просрочена,
#     - не превышен лимит неудачных попыток.
#     В чек добавляем e-mail пользователя, если он сохранён.
#     """
#     method_id = user.get("payment_method_id")
#     user_id = user["tg_id"]

#     if not method_id:
#         logging.info(f"[AutoPay] USER={user_id}: нет payment_method_id")
#         return

#     expiration_date = user.get("expiration_date")
#     if expiration_date is not None and expiration_date >= datetime.now().date():
#         logging.info(f"[AutoPay] USER={user_id}: подписка ещё активна")
#         return

#     days = user.get("last_subscription_days", settings.default_subscription_days)
#     amount = user.get("last_subscription_amount", settings.default_subscription_amount)
#     attempts = user.get("failed_autopay_attempts", 0)

#     if attempts >= settings.max_failed_autopay_attempts:
#         logging.warning(f"[AutoPay] USER={user_id}: автоплатёж заблокирован")
#         return

#     description = f"АВТОПЛАТЕЖ: {days} дн. / {amount}₽"

#     # e-mail пользователя (если есть) — пойдёт в receipt.customer.email
#     customer_email = user.get("email")

#     try:
#         def _create():
#             return Payment.create(
#                 _create_payment_payload(
#                     amount,
#                     description,
#                     user_id,
#                     days,
#                     # при автоплатеже НЕ нужен return_url и НЕ нужен экран выбора способа
#                     method_id=method_id,
#                     customer_email=customer_email,  # <— добавлено
#                 ),
#                 str(uuid.uuid4()),
#             )

#         payment = await asyncio.to_thread(_create)

#         if payment.status == "succeeded":
#             logging.info(f"[AutoPay] ✅ USER={user_id} списание прошло: {payment.id}")
#             await extend_subscription(user_id, days, method_id, amount)
#             await mysql.execute(
#                 "UPDATE users_tbl SET failed_autopay_attempts = 0 WHERE tg_id=%s",
#                 (user_id,),
#             )
#         else:
#             raise Exception(f"YooKassa status: {payment.status}")

#     except Exception as e:
#         logging.error(f"[AutoPay] ❌ USER={user_id} ошибка: {e}")
#         await mysql.execute(
#             "UPDATE users_tbl SET failed_autopay_attempts = failed_autopay_attempts + 1 WHERE tg_id=%s",
#             (user_id,),
#         )
#         user = await get_user_by_id(user_id)
#         if user.get("failed_autopay_attempts", 0) >= 3:
#             await block_autopay(user_id)
#             try:
#                 from app.bot.bot import bot
#                 await bot.send_message(
#                     chat_id=user_id,
#                     text=(
#                         "❌ Автоплатёж не прошёл 3 раза. Подписка не продлена. "
#                         "Оплатите вручную командой /subscribe. "
#                         "Для автопродления выберите оплату картой и сохраните её."
#                     ),
#                 )
#             except Exception as e2:
#                 logging.warning(f"[Bot] Уведомление не доставлено: {e2}")


# # ✅ Активация подписки после успешной оплаты (например, Telegram Stars)
# async def activate_subscription_after_payment(
#     user_id: int,
#     plan_key: str | None = None,
#     days: int = 30,
#     amount_rub: float | int = 0,
#     source: str = "stars",
#     external_id: str | None = None,
#     amount_stars: int | None = None,
#     **kwargs,
# ):
#     """
#     Пост-обработчик: просто активирует/продлевает подписку.
#     Для Stars метод оплаты не сохраняем (None), чтобы не мешать автосписаниям по карте.
#     """
#     await extend_subscription(
#         user_id=user_id,
#         days=days,
#         method_id=None,  # у Stars не формируется сохраняемый метод
#         amount=float(amount_rub or 0),
#     )
#     return {"ok": True, "user_id": user_id, "days": days, "source": source}


import uuid
import asyncio
import logging
from datetime import datetime
from yookassa import Configuration, Payment

from app.config import settings
from app.db.queries.payment_queries import save_payment
from app.services.user import extend_subscription, block_autopay, get_user_by_id
from app.db.mysql import mysql

logger = logging.getLogger(__name__)

# 🔐 YooKassa конфигурация
Configuration.account_id = settings.yookassa_store_id
Configuration.secret_key = settings.yookassa_secret_key

RETURN_URL = "https://t.me/calories_by_photo_bot"  # экран ЮKassa после ручной оплаты


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
    Формирует payload для YooKassa.
    ⚠️ Чек оставляем как у тебя: ВСЕГДА добавляем receipt с e-mail (если не дали — подставляем заглушку).
    """
    item_desc = (description or "Подписка").strip()[:128]
    email_for_receipt = (customer_email or f"user_{user_id}@example.com").strip()[:254]

    payload: dict = {
        "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
        "capture": True,
        "description": description,
        "metadata": {"user_id": str(user_id), "plan": f"{days}_days"},
        # 54-ФЗ чек
        "receipt": {
            "customer": {"email": email_for_receipt},
            "items": [
                {
                    "description": item_desc,
                    "quantity": "1.00",
                    "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
                    "vat_code": 1,                        # без НДС
                    "payment_subject": "service",         # услуга
                    "payment_mode": "full_prepayment",    # полная предоплата
                    "measure": "piece",
                }
            ],
        },
    }

    # Принудительно открыть конкретный способ (по желанию)
    if force_method in {"bank_card", "sbp", "yoo_money"}:
        payload["payment_method_data"] = {"type": force_method}

    # Рекуррент: используем сохранённый метод
    if method_id:
        payload["payment_method_id"] = method_id

    # Ручная оплата через редирект на страницу ЮKassa
    if return_url:
        payload["confirmation"] = {"type": "redirect", "return_url": return_url}
        payload["save_payment_method"] = True  # предложить сохранить метод

    return payload


# ✅ Создание платежа (страница ЮKassa)
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
    Возвращает confirmation_url.
    Сохраняем в БД ЛЮБОЙ payment_method.id, если ЮKassa его вернула (без фильтра по type).
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
            str(uuid.uuid4()),  # идемпотентный ключ
        )

    payment = await asyncio.to_thread(_create)

    pm = getattr(payment, "payment_method", None)
    pm_id = getattr(pm, "id", None)  # берем как есть
    method_id = pm_id if pm_id else None

    # сохраняем сам платёж
    await save_payment(
        user_id=user_id,
        status=payment.status,
        payment_id=payment.id,
        method_id=method_id,          # может быть None — ок, потом обновим из вебхука
        amount=amount,
        days=days,
    )

    # ссылка на страницу оплаты
    return payment.confirmation.confirmation_url


# 🔁 Автосписание по сохранённому способу
async def try_autopay(user: dict):
    """
    Пытается продлить подписку, если:
      • есть payment_method_id,
      • подписка просрочена,
      • не превышен лимит неудачных попыток.
    В чек добавляем e-mail пользователя (или заглушку, как в _create_payment_payload).
    """
    method_id = user.get("payment_method_id")
    user_id = int(user["tg_id"])

    if not method_id:
        logger.info(f"[AutoPay] USER={user_id}: нет payment_method_id")
        return

    expiration_date = user.get("expiration_date")
    if expiration_date is not None and expiration_date >= datetime.now().date():
        logger.info(f"[AutoPay] USER={user_id}: подписка ещё активна")
        return

    days = user.get("last_subscription_days", settings.default_subscription_days)
    amount = user.get("last_subscription_amount", settings.default_subscription_amount)
    attempts = int(user.get("failed_autopay_attempts", 0))

    if attempts >= settings.max_failed_autopay_attempts:
        logger.warning(f"[AutoPay] USER={user_id}: автоплатёж заблокирован лимитом")
        return

    description = f"АВТОПЛАТЕЖ: {days} дн. / {amount}₽"
    customer_email = user.get("email")  # может быть None — ок

    try:
        def _create():
            return Payment.create(
                _create_payment_payload(
                    amount,
                    description,
                    user_id,
                    days,
                    method_id=method_id,        # рекуррент — без return_url
                    customer_email=customer_email,
                ),
                str(uuid.uuid4()),
            )

        payment = await asyncio.to_thread(_create)

        if payment.status == "succeeded":
            logger.info(f"[AutoPay] ✅ USER={user_id} списание прошло: {payment.id}")
            await extend_subscription(user_id, days, method_id, amount)
            await mysql.execute(
                "UPDATE users_tbl SET failed_autopay_attempts = 0 WHERE tg_id=%s",
                (user_id,),
            )
        else:
            raise RuntimeError(f"YooKassa status: {payment.status}")

    except Exception as e:
        logger.error(f"[AutoPay] ❌ USER={user_id} ошибка: {e}")
        await mysql.execute(
            "UPDATE users_tbl SET failed_autopay_attempts = failed_autopay_attempts + 1 WHERE tg_id=%s",
            (user_id,),
        )
        fresh = await get_user_by_id(user_id)
        if int(fresh.get("failed_autopay_attempts", 0)) >= settings.max_failed_autopay_attempts:
            await block_autopay(user_id)


# ✅ Унифицированный пост-обработчик (для Stars и т.п.)
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
    await extend_subscription(
        user_id=user_id,
        days=days,
        method_id=None,  # у Stars не формируем сохраняемый метод
        amount=float(amount_rub or 0),
    )
    return {"ok": True, "user_id": user_id, "days": days, "source": source}
