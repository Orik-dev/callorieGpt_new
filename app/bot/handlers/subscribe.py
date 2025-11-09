from aiogram import Router, F
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    Message, CallbackQuery, LabeledPrice, PreCheckoutQuery
)
from app.services.payments_logic import create_payment
from app.services.user import get_or_create_user, get_user_by_id, set_user_email, EMAIL_RE
import logging
import uuid
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

router = Router()
logger = logging.getLogger(__name__)


class EmailState(StatesGroup):
    """Состояние для ввода email"""
    waiting_email = State()


# Тарифы (рубли)
SUBSCRIBES = {
    "key_1_month":  {"amount": 290,  "days": 30,  "desc": "1 месяц — 290₽"},
    "key_3_month":  {"amount": 770,  "days": 90,  "desc": "3 месяца — 770₽"},
    "key_12_month": {"amount": 2500, "days": 360, "desc": "12 месяцев — 2500₽"},
}

# Цены в звёздах (XTR)
STARS_PRICE = {
    "key_1_month":  249,
    "key_3_month":  690,
    "key_12_month": 2150,
}


def method_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора способа оплаты"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="💳 Картой (ЮKassa)",
            callback_data="sub_method_rub"
        )],
        [InlineKeyboardButton(
            text="⭐ Звёздами Telegram",
            callback_data="sub_method_stars"
        )],
    ])


def rub_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура тарифов для оплаты картой"""
    rows = []
    for key, data in SUBSCRIBES.items():
        rows.append([InlineKeyboardButton(
            text=data["desc"],
            callback_data=f"sub_rub_{key}"
        )])
    rows.append([InlineKeyboardButton(
        text="⬅️ Назад",
        callback_data="sub_back"
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def stars_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура тарифов для оплаты звёздами"""
    rows = []
    for key, data in SUBSCRIBES.items():
        period = data["desc"].split(" — ")[0]
        rows.append([InlineKeyboardButton(
            text=f"{period} — {STARS_PRICE[key]}⭐",
            callback_data=f"sub_stars_{key}"
        )])
    rows.append([InlineKeyboardButton(
        text="⬅️ Назад",
        callback_data="sub_back"
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(F.text == "/subscribe")
async def subscribe_menu(message: Message, state: FSMContext):
    """Главное меню подписки"""
    await state.clear()  # Очищаем любое предыдущее состояние
    
    await message.answer(
        "📦 <b>Подписка на бота</b>\n\n"
        "✨ С подпиской доступно:\n"
        "• 25 запросов в день (вместо 5)\n"
        "• Обновление токенов каждый день\n"
        "• Приоритетная поддержка\n\n"
        "Выберите способ оплаты:",
        reply_markup=method_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "sub_method_rub")
async def show_rub(callback: CallbackQuery):
    """Показывает тарифы для оплаты картой"""
    await callback.message.edit_text(
        "💳 <b>Оплата картой (ЮKassa)</b>\n\n"
        "Выберите тариф:",
        reply_markup=rub_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "sub_method_stars")
async def show_stars(callback: CallbackQuery):
    """Показывает тарифы для оплаты звёздами"""
    await callback.message.edit_text(
        "⭐ <b>Оплата звёздами Telegram</b>\n\n"
        "Выберите тариф:",
        reply_markup=stars_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "sub_back")
async def back_to_methods(callback: CallbackQuery):
    """Возврат к выбору способа оплаты"""
    await callback.message.edit_text(
        "📦 <b>Подписка на бота</b>\n\n"
        "✨ С подпиской доступно:\n"
        "• 25 запросов в день (вместо 5)\n"
        "• Обновление токенов каждый день\n"
        "• Приоритетная поддержка\n\n"
        "Выберите способ оплаты:",
        reply_markup=method_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("sub_rub_"))
async def handle_subscribe_rub(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора тарифа для оплаты картой"""
    user_id = callback.from_user.id
    key = callback.data.replace("sub_rub_", "")
    plan = SUBSCRIBES.get(key)
    
    if not plan:
        await callback.answer("⚠️ Неизвестный тариф", show_alert=True)
        return

    await get_or_create_user(user_id, callback.from_user.first_name)
    user = await get_user_by_id(user_id)
    user_email = user.get("email")

    # Если email не сохранён - спрашиваем
    if not user_email:
        await state.set_state(EmailState.waiting_email)
        await state.update_data(pending_plan_key=key)
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="☑️ Чек не нужен",
                callback_data="sub_skip_receipt"
            )],
            [InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data="sub_back"
            )],
        ])
        
        await callback.message.edit_text(
            "✉️ <b>Укажите e-mail для чека</b>\n\n"
            "E-mail будет использован для отправки чека об оплате.\n\n"
            "Если чек не нужен — нажмите «Чек не нужен».",
            reply_markup=kb,
            parse_mode="HTML",
        )
        await callback.answer()
        return

    # Email есть - создаём платёж
    try:
        payment_url = await create_payment(
            user_id,
            plan["amount"],
            plan["desc"],
            plan["days"],
            customer_email=user_email,
        )
    except Exception as e:
        logger.exception(f"[Subscribe] Error creating payment for user {user_id}: {e}")
        await callback.answer(
            "⚠️ Оплата картой временно недоступна. "
            "Попробуйте позже или выберите оплату звёздами.",
            show_alert=True
        )
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="💳 Перейти к оплате",
            url=payment_url
        )],
        [InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data="sub_back"
        )]
    ])
    
    await callback.message.edit_text(
        f"✅ <b>Тариф:</b> {plan['desc']}\n\n"
        f"Нажмите кнопку ниже для оплаты:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "sub_skip_receipt")
async def handle_skip_receipt(callback: CallbackQuery, state: FSMContext):
    """Оплата без чека"""
    data = await state.get_data()
    plan_key = data.get("pending_plan_key")
    plan = SUBSCRIBES.get(plan_key)

    if not plan:
        await callback.answer("⚠️ Неизвестный тариф", show_alert=True)
        return

    user_id = callback.from_user.id
    await state.clear()

    try:
        payment_url = await create_payment(
            user_id,
            plan["amount"],
            plan["desc"],
            plan["days"],
            customer_email=None,  # Без чека
        )
    except Exception as e:
        logger.exception(f"[Subscribe] Error creating payment (no receipt) for user {user_id}: {e}")
        await callback.answer(
            "⚠️ Оплата картой временно недоступна. "
            "Попробуйте позже или выберите оплату звёздами.",
            show_alert=True
        )
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="💳 Перейти к оплате",
            url=payment_url
        )],
        [InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data="sub_back"
        )]
    ])
    
    await callback.message.edit_text(
        f"✅ <b>Тариф:</b> {plan['desc']}\n\n"
        f"Нажмите кнопку ниже для оплаты:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(EmailState.waiting_email)
async def on_email_entered(message: Message, state: FSMContext):
    """Обработка введённого email"""
    email = (message.text or "").strip()
    
    if not EMAIL_RE.match(email):
        await message.answer(
            "⚠️ Похоже, это не e-mail.\n\n"
            "Отправьте адрес в формате <code>name@example.com</code>, "
            "нажмите «Чек не нужен» или /cancel.",
            parse_mode="HTML"
        )
        return

    try:
        await set_user_email(message.from_user.id, email)
    except Exception as e:
        logger.exception(f"[Subscribe] Error saving email for user {message.from_user.id}: {e}")
        await message.answer("⚠️ Не удалось сохранить e-mail. Попробуйте ещё раз.")
        return

    data = await state.get_data()
    plan_key = data.get("pending_plan_key")
    plan = SUBSCRIBES.get(plan_key) or SUBSCRIBES["key_1_month"]

    await state.clear()

    try:
        payment_url = await create_payment(
            message.from_user.id,
            plan["amount"],
            plan["desc"],
            plan["days"],
            customer_email=email,
        )
    except Exception as e:
        logger.exception(f"[Subscribe] Error creating payment after email for user {message.from_user.id}: {e}")
        await message.answer(
            "⚠️ Оплата картой временно недоступна. "
            "Попробуйте позже или выберите оплату звёздами: /subscribe"
        )
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="💳 Перейти к оплате",
            url=payment_url
        )],
        [InlineKeyboardButton(
            text="⬅️ Назад к подписке",
            callback_data="sub_back"
        )]
    ])
    
    await message.answer(
        f"✅ <b>E-mail сохранён:</b> {email}\n"
        f"<b>Тариф:</b> {plan['desc']}\n\n"
        f"Нажмите кнопку ниже для оплаты:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


# ==========================================
# TELEGRAM STARS (XTR)
# ==========================================

@router.callback_query(F.data.startswith("sub_stars_"))
async def handle_subscribe_stars(callback: CallbackQuery):
    """Обработка оплаты звёздами"""
    user_id = callback.from_user.id
    key = callback.data.replace("sub_stars_", "")
    plan = SUBSCRIBES.get(key)
    stars = STARS_PRICE.get(key)

    if not plan or not stars:
        await callback.answer("⚠️ Неизвестный тариф", show_alert=True)
        return

    await get_or_create_user(user_id, callback.from_user.first_name)

    payload = f"substars:{key}:{uuid.uuid4()}"
    
    try:
        await callback.bot.send_invoice(
            chat_id=user_id,
            title=plan["desc"].split(" — ")[0],
            description="Оплата подписки в Telegram Stars",
            currency="XTR",
            prices=[LabeledPrice(label=plan["desc"], amount=stars)],
            payload=payload,
            is_flexible=False,
            start_parameter=f"substars_{key}",
        )
        await callback.answer()
        logger.info(f"[Subscribe:Stars] Invoice sent to user {user_id}: {plan['desc']}")
    except Exception as e:
        logger.exception(f"[Subscribe:Stars] Error sending invoice to user {user_id}: {e}")
        await callback.answer(
            "⚠️ Ошибка при создании счёта. Попробуйте позже.",
            show_alert=True
        )


@router.pre_checkout_query()
async def on_pre_checkout(pcq: PreCheckoutQuery):
    """Проверка перед оплатой звёздами"""
    ok = False
    try:
        ok = pcq.invoice_payload.startswith("substars:")
    except Exception:
        ok = False
    
    await pcq.answer(
        ok=ok,
        error_message=None if ok else "⚠️ Неверные параметры заказа"
    )


@router.message(F.successful_payment)
async def on_successful_stars_payment(message: Message):
    """Обработка успешной оплаты звёздами"""
    sp = message.successful_payment
    
    if not sp or sp.currency != "XTR":
        return

    try:
        _, key, _ = sp.invoice_payload.split(":", 2)
    except Exception:
        key = "key_1_month"

    plan = SUBSCRIBES.get(key, {"days": 30, "amount": 0, "desc": "Подписка"})

    # Вызываем бизнес-логику активации подписки
    from app.services.payments_logic import activate_subscription_after_payment
    
    await activate_subscription_after_payment(
        user_id=message.from_user.id,
        plan_key=key,
        days=plan["days"],
        amount_rub=plan.get("amount", 0),
        source="stars",
        external_id=sp.telegram_payment_charge_id,
        amount_stars=sp.total_amount,
    )

    await message.answer(
        f"✅ <b>Оплата звёздами успешна!</b>\n\n"
        f"Тариф: <b>{plan['desc']}</b>\n"
        f"Подписка активирована на <b>{plan['days']} дней</b>\n\n"
        f"Теперь доступно 25 запросов в день!\n"
        f"Проверьте профиль: /profile",
        parse_mode="HTML"
    )
    
    logger.info(
        f"[Subscribe:Stars] Payment successful for user {message.from_user.id}: "
        f"{plan['desc']}"
    )


@router.callback_query(F.data == "cancel_sub")
async def cancel_sub(callback: CallbackQuery):
    """Закрытие меню подписки"""
    try:
        await callback.message.delete()
        await callback.answer("❌ Отменено")
    except Exception as e:
        logger.error(f"[Subscribe] Error closing menu for user {callback.from_user.id}: {e}")
        await callback.answer("⚠️ Ошибка при закрытии меню", show_alert=True)