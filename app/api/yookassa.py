import aiomysql
import asyncio
import ipaddress
import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, Request, Response
from yookassa import Payment
import pytz

from app.db.mysql import mysql
from app.bot.bot import bot
from app.services.user import SUBSCRIBED_TOKENS_COUNT, get_user_by_id

logger = logging.getLogger(__name__)
yookassa_router = APIRouter()

SUPPORTED_EVENTS = {"payment.succeeded", "payment.canceled", "payment.refunded"}

# Доверенные IP-адреса YooKassa (из документации)
YOOKASSA_TRUSTED_NETS = [
    ipaddress.ip_network("185.71.76.0/27"),
    ipaddress.ip_network("185.71.77.0/27"),
    ipaddress.ip_network("77.75.153.0/25"),
    ipaddress.ip_network("77.75.156.11/32"),
    ipaddress.ip_network("77.75.156.35/32"),
    ipaddress.ip_network("77.75.154.128/25"),
]


def _is_trusted_ip(ip_str: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip_str)
        return any(addr in net for net in YOOKASSA_TRUSTED_NETS)
    except ValueError:
        return False


@yookassa_router.post("/yookassa")
async def yookassa_webhook(request: Request):
    """
    Атомарная обработка вебхука YooKassa.
    Верификация: проверка IP + подтверждение статуса через API.
    """
    # Проверка IP отправителя
    client_ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if not client_ip:
        client_ip = request.client.host
    if not _is_trusted_ip(client_ip):
        logger.warning(f"[Webhook] untrusted IP: {client_ip}")
        return Response(status_code=403)

    try:
        data = await request.json()
    except Exception:
        logger.warning("[Webhook] bad json")
        return Response(status_code=400)

    event = data.get("event")
    if event not in SUPPORTED_EVENTS:
        logger.warning(f"[Webhook] unknown event: {event}")
        return Response(status_code=400)

    payment = data.get("object") or {}
    payment_id = payment.get("id")
    if not payment_id:
        logger.warning("[Webhook] missing id")
        return Response(status_code=400)

    # Верификация: получаем актуальный статус платежа из API YooKassa
    try:
        real_payment = await asyncio.to_thread(Payment.find_one, payment_id)
        status_event = real_payment.status
    except Exception as e:
        logger.error(f"[Webhook] Payment.find_one failed for {payment_id}: {e}")
        return Response(status_code=500)

    # Быстрая идемпотентность/валидация существования
    async with mysql.pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT tg_id, status FROM payment_tbl WHERE payment_id=%s",
                (payment_id,),
            )
            payrow = await cur.fetchone()

    if not payrow:
        # наш side-effect уже мог удалиться/не создаться — не падаем
        logger.warning(f"[Webhook] payment {payment_id} not found")
        return Response(status_code=200)

    if payrow["status"] == status_event:
        logger.info(f"[Webhook] payment {payment_id} already {status_event}")
        return Response(status_code=200)

    user_id = int(payrow["tg_id"])

    # ---- success ----
    if event == "payment.succeeded":
        event_pm = payment.get("payment_method") or {}
        event_method_id = event_pm.get("id")  # берём ЛЮБОЙ id, если прислали
        new_exp = None
        saved_method_id = None

        async with mysql.pool.acquire() as conn:
            try:
                await conn.begin()
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    # 1) фиксируем статус платежа
                    await cur.execute(
                        "UPDATE payment_tbl SET status=%s WHERE payment_id=%s",
                        (status_event, payment_id),
                    )

                    # 2) читаем amount/days/method_id под блокировкой
                    await cur.execute(
                        "SELECT amount, days, method_id FROM payment_tbl "
                        "WHERE payment_id=%s FOR UPDATE",
                        (payment_id,),
                    )
                    p = await cur.fetchone()
                    if not p:
                        raise RuntimeError("payment row disappeared")

                    amount = float(p["amount"])
                    days = int(p["days"])

                    # 3) если в событии есть method_id — записываем в payment_tbl
                    if event_method_id and event_method_id != p["method_id"]:
                        await cur.execute(
                            "UPDATE payment_tbl SET method_id=%s WHERE payment_id=%s",
                            (event_method_id, payment_id),
                        )

                    # финальный метод: из события, иначе из нашей записи
                    saved_method_id = event_method_id or p["method_id"]

                    # 4) под блокировкой считаем новую дату подписки
                    await cur.execute(
                        "SELECT expiration_date FROM users_tbl WHERE tg_id=%s FOR UPDATE",
                        (user_id,),
                    )
                    u = await cur.fetchone()
                    # Получаем таймзону пользователя
                    user_data = await get_user_by_id(user_id)
                    user_tz = user_data.get("timezone", "Europe/Moscow") if user_data else "Europe/Moscow"
                    try:
                        tz = pytz.timezone(user_tz)
                    except Exception:
                        tz = pytz.timezone("Europe/Moscow")
                    today = datetime.now(tz).date()
                    current_exp = u["expiration_date"] if u else None
                    if current_exp and current_exp >= today:
                        new_exp = current_exp + timedelta(days=days)
                    else:
                        new_exp = today + timedelta(days=days)

                    # 5) обновляем профиль пользователя
                    await cur.execute(
                        """
                        UPDATE users_tbl
                        SET free_tokens=%s,
                            expiration_date=%s,
                            payment_method_id=%s,
                            last_subscription_days=%s,
                            last_subscription_amount=%s,
                            failed_autopay_attempts=0
                        WHERE tg_id=%s
                        """,
                        (
                            SUBSCRIBED_TOKENS_COUNT,
                            new_exp,
                            saved_method_id,   # может быть None — тогда автопродления не будет
                            days,
                            amount,
                            user_id,
                        ),
                    )

                await conn.commit()
            except Exception as e:
                await conn.rollback()
                logger.exception(f"[Webhook] TX error for {payment_id}: {e}")
                return Response(status_code=500)

        # уведомляем ПОСЛЕ коммита
        try:
            if saved_method_id:
                msg = (
                    "✅ Платёж получен.\n"
                    f"Подписка продлена до {new_exp}.\n"
                    # "🔁 Автопродление включено."
                )
            else:
                msg = (
                    "✅ Платёж получен.\n"
                    f"Подписка продлена до {new_exp}.\n"
                    # "ℹ️ Оплата прошла без сохранения способа — автопродления не будет."
                )
            await bot.send_message(chat_id=user_id, text=msg)
        except Exception as e:
            logger.warning(f"[Webhook] notify fail: {e}")

        return Response(status_code=200)

    # ---- canceled / refunded ----
    else:
        async with mysql.pool.acquire() as conn:
            try:
                await conn.begin()
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute(
                        "UPDATE payment_tbl SET status=%s WHERE payment_id=%s",
                        (status_event, payment_id),
                    )
                await conn.commit()
            except Exception:
                await conn.rollback()
                return Response(status_code=500)

        try:
            await bot.send_message(user_id, "❌ Ваш платёж был отменён или возвращён.")
        except Exception:
            pass

        return Response(status_code=200)
