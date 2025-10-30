from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from app.services.user import get_user_by_id, block_autopay
from datetime import datetime,date
import logging

router = Router()
logger = logging.getLogger(__name__)


@router.message(Command("profile"))
async def handle_profile(message: types.Message):
    user_id = message.from_user.id
    try:
        user = await get_user_by_id(user_id)
        if not user:
            logger.warning(f"Профиль не найден для пользователя {user_id}. Предлагаем /start.")
            await message.answer("Профиль не найден. Пожалуйста, начните работу с ботом командой /start")
            return

        # Разбор даты подписки
        exp_date_raw = user.get("expiration_date")
        exp_date_str = "нет"

        if exp_date_raw:
            try:
                if isinstance(exp_date_raw, (datetime, date)):
                    exp_date_str = exp_date_raw.strftime("%d.%m.%Y")
                else:
                    logger.warning(f"[Profile] expiration_date странного типа: {type(exp_date_raw)}")
            except Exception as e:
                logger.warning(f"[Profile] Не удалось обработать дату подписки у {user_id}: {e}")

        # Состояние подписки
        # is_subscription_active = bool(exp_date_parsed and exp_date_parsed >= datetime.now().date())
        autopay_active = user.get("payment_method_id") is not None

        # Токены
        free_tokens = user.get("free_tokens", 0)
        tokens_display = f"{free_tokens}/25"

        # Финальное сообщение
        profile_text = (
            # f"👤 <b>Ваш профиль:</b> {user['name']}\n"
            f"📅 <b>Подписка до:</b> {exp_date_str}\n"
            f"🪙 <b>Осталось запросов на сегодня:</b> {tokens_display}\n"
            f"🔁 <b>Подписка:</b> {'включена ✅' if autopay_active else 'отключена ❌'}"
        )

        # Кнопка отключения автоплатежа
        keyboard = None
        if autopay_active:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отключить подписку", callback_data="cancel_autopay")]
            ])

        await message.answer(profile_text, reply_markup=keyboard, parse_mode="HTML")
        logger.info(f"Профиль показан для пользователя {user_id}.")

    except Exception as e:
        logger.exception(f"[Profile] Ошибка при загрузке профиля для пользователя {user_id}: {e}")
        await message.answer("Произошла ошибка при загрузке профиля. Пожалуйста, попробуйте позже.")


@router.callback_query(lambda c: c.data == "cancel_autopay")
async def handle_cancel_autopay(callback: CallbackQuery):
    user_id = callback.from_user.id
    try:
        await block_autopay(user_id)
        await callback.message.edit_text("✅ Автопродление отключено.")
        await callback.answer("Автопродление отключено")
        logger.info(f"Автопродление для пользователя {user_id} отключено через профиль.")
    except Exception as e:
        logger.exception(f"[Profile] Ошибка при отключении автоплатежа для пользователя {user_id}: {e}")
        await callback.answer("Ошибка при отключении автопродления. Попробуйте позже.", show_alert=True)
