# from fastapi import APIRouter, Request, Response, status
# from app.db.queries.payment_queries import update_payment_status, get_payment_data, get_payment_by_id
# from app.services.user import extend_subscription,get_user_by_id
# from app.bot.bot import bot  # импорт Telegram бота
# import logging

# logger = logging.getLogger(__name__)
# yookassa_router = APIRouter()

# SUPPORTED_EVENTS = {"payment.succeeded", "payment.canceled", "payment.refunded"}


# @yookassa_router.post("/yookassa")
# async def yookassa_webhook(request: Request):
#     try:
#         data = await request.json()
#         event = data.get("event")

#         if event not in SUPPORTED_EVENTS:
#             logger.warning(f"[Webhook] Неизвестное событие: {event}")
#             return Response(status_code=400)

#         payment = data.get("object", {})
#         payment_id = payment.get("id")
#         status_event = payment.get("status")
#         metadata = payment.get("metadata", {})

#         if not payment_id or not status_event:
#             logger.warning(f"[Webhook] Некорректное тело запроса: {data}")
#             return Response(status_code=400)

#         # Проверка: платёж уже обработан с этим статусом?
#         existing_payment = await get_payment_by_id(payment_id)
#         if not existing_payment:
#             logger.warning(f"[Webhook] Платёж {payment_id} не найден в БД.")
#             return Response(status_code=200)

#         if existing_payment["status"] == status_event:
#             logger.info(f"[Webhook] Платёж {payment_id} уже обработан со статусом {status_event}")
#             return Response(status_code=200)

#         await update_payment_status(payment_id, status_event)

#         user_id = existing_payment["tg_id"]

#         if event == "payment.succeeded":
#             saved_payment = await get_payment_data(payment_id)
#             await extend_subscription(
#                 int(user_id),
#                 saved_payment["days"],
#                 payment.get("payment_method", {}).get("id"),
#                 saved_payment["amount"]
#             )

#             user = await get_user_by_id(user_id)
#             expiration_date = user.get("expiration_date", "N/A")

#             # Уведомляем пользователя
#             try:
#                 text = (
#                     "✅ *Платёж успешно получен!*\n"
#                     f"Подписка активирована до {expiration_date}.\n"
#                     f"Спасибо за покупку!"
#                 )
#                 await bot.send_message(chat_id=user_id, text=text, parse_mode="Markdown")
#             except Exception as e:
#                 logger.warning(f"[Webhook] Не удалось отправить Telegram уведомление: {e}")

#             logger.info(f"[Webhook] Подписка активирована для пользователя {user_id} по платежу {payment_id}")

#         elif event in ("payment.canceled", "payment.refunded"):
#             try:
#                 await bot.send_message(chat_id=user_id, text="❌ Ваш платёж был отменён или возвращён.")
#             except Exception as e:
#                 logger.warning(f"[Webhook] Telegram уведомление отмены не доставлено: {e}")

#             logger.info(f"[Webhook] Платёж {payment_id} отменён или возвращён")

#         return Response(status_code=200)

#     except Exception as e:
#         logger.exception(f"[Webhook Error] Ошибка при обработке вебхука YooKassa: {e}")
#         return Response(status_code=500)


import aiomysql
import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, Request, Response

from app.db.mysql import mysql
from app.bot.bot import bot
from app.services.user import SUBSCRIBED_TOKENS_COUNT

logger = logging.getLogger(__name__)
yookassa_router = APIRouter()

SUPPORTED_EVENTS = {"payment.succeeded", "payment.canceled", "payment.refunded"}


@yookassa_router.post("/yookassa")
async def yookassa_webhook(request: Request):
    """
    Атомарная обработка вебхука YooKassa.
    Все апдейты происходят в одной транзакции:
      1) фиксируем новый статус платежа,
      2) при success — дочитываем amount/days/method_id под блокировкой,
         переустанавливаем method_id из события (если прислали),
      3) под FOR UPDATE считаем новую дату подписки и обновляем users_tbl.
    После коммита отправляем уведомление пользователю.
    """
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
    status_event = payment.get("status")
    if not payment_id or not status_event:
        logger.warning("[Webhook] missing id/status")
        return Response(status_code=400)

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
                    today = datetime.now().date()
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
