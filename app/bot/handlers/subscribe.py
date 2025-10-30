# app/bot/handlers/subscribe.py
from aiogram import Router, F
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    Message, CallbackQuery, LabeledPrice, PreCheckoutQuery
)
from app.services.payments_logic import create_payment  # ЮKassa
from app.services.user import get_or_create_user, get_user_by_id
import logging
import uuid
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from typing import Any
from app.services.user import set_user_email  # <— новая функция
from app.services.user import EMAIL_RE      

router = Router()
logger = logging.getLogger(__name__)

class EmailState(StatesGroup):
    waiting_email = State()

# 💳 Тарифы (рубли)
SUBSCRIBES = {
    "key_1_month":  {"amount": 290,  "days": 30,  "desc": "1 месяц — 290₽"},
    "key_3_month":  {"amount": 770,  "days": 90,  "desc": "3 месяца — 770₽"},
    "key_12_month": {"amount": 2500, "days": 360, "desc": "12 месяцев — 2500₽"},
}

# ⭐ Цены в звёздах (XTR)
STARS_PRICE = {
    "key_1_month":  249,
    "key_3_month":  690,
    "key_12_month": 2150,
}

# ---------------- UI ----------------

def method_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="💳 Картой (ЮKassa)", callback_data="sub_method_rub"),
        InlineKeyboardButton(text="⭐ Звёздами",         callback_data="sub_method_stars"),
    ]])

def rub_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for key, data in SUBSCRIBES.items():
        rows.append([InlineKeyboardButton(text=data["desc"], callback_data=f"sub_rub_{key}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="sub_back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def stars_keyboard() -> InlineKeyboardMarkup:
    # «в столбик»
    rows = []
    for key, data in SUBSCRIBES.items():
        period = data["desc"].split(" — ")[0]  # "1 месяц", "3 месяца", ...
        rows.append([InlineKeyboardButton(
            text=f"{period} — {STARS_PRICE[key]}⭐",
            callback_data=f"sub_stars_{key}"
        )])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="sub_back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

# ---------------- /subscribe ----------------

@router.message(F.text == "/subscribe")
async def subscribe_menu(message: Message):
    await message.answer(
        "📦 <b>Подписка</b>\nВыберите способ оплаты:",
        reply_markup=method_keyboard(),
        parse_mode="HTML",
    )

@router.callback_query(F.data == "sub_method_rub")
async def show_rub(callback: CallbackQuery):
    await callback.message.edit_text(
        "💳 <b>Оплата картой (ЮKassa)</b>\nВыберите тариф:",
        reply_markup=rub_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()

@router.callback_query(F.data == "sub_method_stars")
async def show_stars(callback: CallbackQuery):
    await callback.message.edit_text(
        "⭐ <b>Оплата звёздами</b>\nВыберите тариф:",
        reply_markup=stars_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()

@router.callback_query(F.data == "sub_back")
async def back_to_methods(callback: CallbackQuery):
    await callback.message.edit_text(
        "📦 <b>Подписка</b>\nВыберите способ оплаты:",
        reply_markup=method_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()

# ---------------- ЮKassa (как было) ----------------

# @router.callback_query(F.data.startswith("sub_rub_"))
# async def handle_subscribe_rub(callback: CallbackQuery, state: FSMContext):
#     user_id = callback.from_user.id
#     key = callback.data.replace("sub_rub_", "")
#     plan = SUBSCRIBES.get(key)
#     if not plan:
#         await callback.answer("Неизвестный тариф.", show_alert=True)
#         return

#     await get_or_create_user(user_id, callback.from_user.first_name)
#     user = await get_user_by_id(user_id)
#     user_email = user.get("email")

#     # Если e-mail не сохранён — спросим 1 раз и вернёмся сюда
#     if not user_email:
#         await state.set_state(EmailState.waiting_email)
#         await state.update_data(pending_plan_key=key)
#         await callback.message.edit_text(
#             "✉️ Укажите e-mail для чека. Его спросим один раз и запомним.\n\n"
#             "Пример: <code>name@example.com</code>\n\n"
#             "Можно отменить — нажмите «Назад».",
#             reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="sub_back")]]),
#             parse_mode="HTML",
#         )
#         await callback.answer()
#         return

#     # e-mail есть — создаём платёж как раньше, но передаём его в чек
#     try:
#         payment_url = await create_payment(
#             user_id, plan["amount"], plan["desc"], plan["days"],
#             customer_email=user_email,  # <—
#         )
#     except Exception as e:
#         logger.exception(f"[Subscribe:RUB] Ошибка create_payment: {e}")
#         await callback.answer("Оплата картой временно недоступна. Попробуйте позже или выберите ⭐.", show_alert=True)
#         return

#     keyboard = InlineKeyboardMarkup(inline_keyboard=[
#         [InlineKeyboardButton(text="💳 Перейти к оплате", url=payment_url)],
#         [InlineKeyboardButton(text="⬅️ Назад", callback_data="sub_back")]
#     ])
#     await callback.message.edit_text(
#         f"✅ Тариф: <b>{plan['desc']}</b>\n\nНажмите кнопку ниже для оплаты:",
#         reply_markup=keyboard,
#         parse_mode="HTML",
#     )
#     await callback.answer()


@router.callback_query(F.data.startswith("sub_rub_"))
async def handle_subscribe_rub(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    key = callback.data.replace("sub_rub_", "")
    plan = SUBSCRIBES.get(key)
    if not plan:
        await callback.answer("Неизвестный тариф.", show_alert=True)
        return

    await get_or_create_user(user_id, callback.from_user.first_name)
    user = await get_user_by_id(user_id)
    user_email = user.get("email")

    # Если e-mail не сохранён — спросим 1 раз
    if not user_email:
        await state.set_state(EmailState.waiting_email)
        await state.update_data(pending_plan_key=key)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="☑️ Чек не нужен", callback_data="sub_skip_receipt")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="sub_back")],
        ])
        await callback.message.edit_text(
            "✉️ Укажите e-mail для чека.\n\n"
            "Если чек не нужен — нажмите  «Чек не нужен».",
            reply_markup=kb,
            parse_mode="HTML",
        )
        await callback.answer()
        return

    # e-mail есть — создаём платёж как раньше
    try:
        payment_url = await create_payment(
            user_id, plan["amount"], plan["desc"], plan["days"],
            customer_email=user_email,  # есть адрес — передаём
        )
    except Exception as e:
        logger.exception(f"[Subscribe:RUB] Ошибка create_payment: {e}")
        await callback.answer("Оплата картой временно недоступна. Попробуйте позже или выберите ⭐.", show_alert=True)
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Перейти к оплате", url=payment_url)],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="sub_back")]
    ])
    await callback.message.edit_text(
        f"✅ Тариф: <b>{plan['desc']}</b>\n\nНажмите кнопку ниже для оплаты:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()

# 👉 Новый хендлер: оплата без чека
@router.callback_query(F.data == "sub_skip_receipt")
async def handle_skip_receipt(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    plan_key = data.get("pending_plan_key")
    plan = SUBSCRIBES.get(plan_key)

    if not plan:
        await callback.answer("Неизвестный тариф.", show_alert=True)
        return

    user_id = callback.from_user.id

    # Сбрасываем состояние, чтобы не висело
    await state.clear()

    try:
        # Передаём None (или пустую строку) — в create_payment не добавляйте receipt.customer
        payment_url = await create_payment(
            user_id,
            plan["amount"],
            plan["desc"],
            plan["days"],
            customer_email=None,  # <- чек не нужен
        )
    except Exception as e:
        logger.exception(f"[Subscribe:RUB] Ошибка create_payment (skip receipt): {e}")
        await callback.answer("Оплата картой временно недоступна. Попробуйте позже или выберите ⭐.", show_alert=True)
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Перейти к оплате", url=payment_url)],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="sub_back")]
    ])
    await callback.message.edit_text(
        f"✅ Тариф: <b>{plan['desc']}</b>\n\nНажмите кнопку ниже для оплаты:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()

    

# ---------------- Stars (XTR) ----------------

@router.callback_query(F.data.startswith("sub_stars_"))
async def handle_subscribe_stars(callback: CallbackQuery):
    user_id = callback.from_user.id
    key = callback.data.replace("sub_stars_", "")
    plan = SUBSCRIBES.get(key)
    stars = STARS_PRICE.get(key)

    if not plan or not stars:
        await callback.answer("Неизвестный тариф.", show_alert=True)
        return

    await get_or_create_user(user_id, callback.from_user.first_name)

    payload = f"substars:{key}:{uuid.uuid4()}"
    # ВАЖНО: currency="XTR", provider_token НЕ указывать
    await callback.bot.send_invoice(
        chat_id=user_id,
        title=plan["desc"].split(" — ")[0],
        description="Оплата подписки в Telegram Stars",
        currency="XTR",
        prices=[LabeledPrice(label=plan["desc"], amount=stars)],  # amount — целое число ⭐
        payload=payload,
        is_flexible=False,
        start_parameter=f"substars_{key}",
    )
    await callback.answer()

@router.pre_checkout_query()
async def on_pre_checkout(pcq: PreCheckoutQuery):
    ok = False
    try:
        ok = pcq.invoice_payload.startswith("substars:")
    except Exception:
        ok = False
    await pcq.answer(ok=ok, error_message=None if ok else "Неверные параметры заказа")

# ---- общий вызов «послеплатёжного» обработчика как у ЮKassa ----

async def apply_after_payment_wrapper(**kwargs: Any):
    """
    Вызывает ТО ЖЕ действие, что и после успешной оплаты в ЮKassa.
    Пытаемся найти функцию в app.services.payments_logic под разными именами.
    """
    func = None
    try:
        from app.services.payments_logic import activate_subscription_after_payment as f  # типовое имя
        func = f
    except Exception:
        try:
            from app.services.payments_logic import apply_after_payment as f
            func = f
        except Exception:
            try:
                from app.services.payments_logic import mark_sub_paid as f
                func = f
            except Exception:
                func = None

    if not func:
        logger.warning("[Subscribe:STARS] Не найдена функция пост-обработки платежа в payments_logic")
        return

    # Пробуем вызвать с максимально полными kwargs; при несовпадении сигнатуры — урезаем
    try:
        return await func(**kwargs)
    except TypeError:
        # Самые частые сигнатуры:
        minimal = {k: kwargs[k] for k in ("user_id", "plan_key") if k in kwargs}
        try:
            return await func(**minimal)
        except Exception as e:
            logger.exception(f"[Subscribe:STARS] Ошибка вызова пост-обработчика: {e}")

@router.message(F.successful_payment)
async def on_successful_stars_payment(message: Message):
    sp = message.successful_payment
    if not sp or sp.currency != "XTR":
        return

    try:
        _, key, _ = sp.invoice_payload.split(":", 2)
    except Exception:
        key = "key_1_month"

    plan = SUBSCRIBES.get(key, {"days": 30, "amount": 0, "desc": "Подписка"})

    # ⚡️ ВАЖНО: вызываем ту же бизнес-логику, что и у ЮKassa
    await apply_after_payment_wrapper(
        user_id=message.from_user.id,
        plan_key=key,
        days=plan["days"],
        amount_rub=plan.get("amount", 0),
        source="stars",
        external_id=sp.telegram_payment_charge_id,
        amount_stars=sp.total_amount,
    )

    await message.answer(
        f"✅ Оплата звёздами успешна!\n"
        f"Тариф: <b>{plan['desc']}</b>\n"
        f"Подписка активирована/продлена на <b>{plan['days']} дн.</b>"
    )

# --- совместимость со старой «/cancel_sub» (если где-то используется) ---

@router.callback_query(F.data == "cancel_sub")
async def cancel_sub(callback: CallbackQuery):
    try:
        await callback.message.delete()
        await callback.answer("Отменено.")
    except Exception as e:
        logger.error(f"Ошибка при закрытии меню подписки для пользователя {callback.from_user.id}: {e}")
        await callback.answer("Ошибка при закрытии меню.", show_alert=True)

# @router.message(EmailState.waiting_email)
# async def on_email_entered(message: Message, state: FSMContext):
#     email = (message.text or "").strip()
#     if not EMAIL_RE.match(email):
#         await message.answer("Похоже, это не e-mail. Отправьте адрес в формате <code>name@example.com</code> или нажмите /cancel.", parse_mode="HTML")
#         return

#     try:
#         await set_user_email(message.from_user.id, email)
#     except Exception as e:
#         logger.exception(f"[Subscribe:RUB] set_user_email: {e}")
#         await message.answer("Не удалось сохранить e-mail. Попробуйте ещё раз.")
#         return

#     data = await state.get_data()
#     plan_key = data.get("pending_plan_key")
#     plan = SUBSCRIBES.get(plan_key) or SUBSCRIBES["key_1_month"]

#     # Сброс состояния, чтобы не висело
#     await state.clear()

#     # Сразу запускаем оплату с только что сохранённым e-mail
#     try:
#         payment_url = await create_payment(
#             message.from_user.id,
#             plan["amount"],
#             plan["desc"],
#             plan["days"],
#             customer_email=email,  # <—
#         )
#     except Exception as e:
#         logger.exception(f"[Subscribe:RUB] Ошибка create_payment после ввода e-mail: {e}")
#         await message.answer("Оплата картой временно недоступна. Попробуйте позже или выберите ⭐.")
#         return

#     keyboard = InlineKeyboardMarkup(inline_keyboard=[
#         [InlineKeyboardButton(text="💳 Перейти к оплате", url=payment_url)],
#         [InlineKeyboardButton(text="⬅️ Назад", callback_data="sub_back")]
#     ])
#     await message.answer(
#         f"Спасибо! E-mail сохранён: <b>{email}</b>\n"
#         f"Тариф: <b>{plan['desc']}</b>\n\nНажмите кнопку ниже для оплаты:",
#         reply_markup=keyboard,
#         parse_mode="HTML",
#     )


@router.message(EmailState.waiting_email)
async def on_email_entered(message: Message, state: FSMContext):
    email = (message.text or "").strip()
    if not EMAIL_RE.match(email):
        await message.answer(
            "Похоже, это не e-mail. Отправьте адрес в формате <code>name@example.com</code>, "
            "нажмите «Чек не нужен» или /cancel.",
            parse_mode="HTML"
        )
        return

    try:
        await set_user_email(message.from_user.id, email)
    except Exception as e:
        logger.exception(f"[Subscribe:RUB] set_user_email: {e}")
        await message.answer("Не удалось сохранить e-mail. Попробуйте ещё раз.")
        return

    data = await state.get_data()
    plan_key = data.get("pending_plan_key")
    plan = SUBSCRIBES.get(plan_key) or SUBSCRIBES["key_1_month"]

    # Сброс состояния
    await state.clear()

    try:
        payment_url = await create_payment(
            message.from_user.id,
            plan["amount"],
            plan["desc"],
            plan["days"],
            customer_email=email,  # чек нужен — передаём e-mail
        )
    except Exception as e:
        logger.exception(f"[Subscribe:RUB] Ошибка create_payment после ввода e-mail: {e}")
        await message.answer("Оплата картой временно недоступна. Попробуйте позже или выберите ⭐.")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Перейти к оплате", url=payment_url)],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="sub_back")]
    ])
    await message.answer(
        f"Спасибо! E-mail сохранён: <b>{email}</b>\n"
        f"Тариф: <b>{plan['desc']}</b>\n\nНажмите кнопку ниже для оплаты:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )