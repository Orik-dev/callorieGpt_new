from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from app.services.user import get_user_by_id, block_autopay, FREE_TOKENS_COUNT, SUBSCRIBED_TOKENS_COUNT
from datetime import datetime, date
import logging

router = Router()
logger = logging.getLogger(__name__)


@router.message(Command("profile"))
async def handle_profile(message: types.Message):
    """Показывает профиль пользователя"""
    user_id = message.from_user.id
    
    try:
        user = await get_user_by_id(user_id)
        
        if not user:
            logger.warning(f"[Profile] User {user_id} not found")
            await message.answer(
                "⚠️ Профиль не найден. Пожалуйста, начните работу с ботом: /start"
            )
            return

        exp_date_raw = user.get("expiration_date")
        exp_date_str = "нет"
        is_active = False
        
        if exp_date_raw:
            try:
                if isinstance(exp_date_raw, (datetime, date)):
                    exp_date_obj = exp_date_raw if isinstance(exp_date_raw, date) else exp_date_raw.date()
                    exp_date_str = exp_date_obj.strftime("%d.%m.%Y")
                    is_active = exp_date_obj >= datetime.now().date()
            except Exception as e:
                logger.warning(f"[Profile] Failed to parse date for user {user_id}: {e}")

        autopay_active = user.get("payment_method_id") is not None

        # ИСПРАВЛЕНИЕ: Правильный формат - "осталось из максимума"
        free_tokens = user.get("free_tokens", 0)
        max_tokens = SUBSCRIBED_TOKENS_COUNT if is_active else FREE_TOKENS_COUNT
        tokens_display = f"{free_tokens} из {max_tokens}"  # ПРАВИЛЬНЫЙ ПОРЯДОК!

        profile_text = (
            f"👤 <b>Ваш профиль</b>\n\n"
            f"📅 <b>Подписка до:</b> {exp_date_str}\n"
            f"🪙 <b>Запросов осталось сегодня:</b> {tokens_display}\n"
            f"🔁 <b>Автопродление:</b> {'включено ✅' if autopay_active else 'отключено ❌'}\n"
        )
        
        if is_active:
            profile_text += f"\n✨ <b>Подписка активна</b>"
        else:
            profile_text += f"\n💎 Оформите подписку: /subscribe"

        keyboard = None
        if autopay_active:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="❌ Отключить автопродление",
                    callback_data="cancel_autopay"
                )]
            ])

        await message.answer(
            profile_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"[Profile] Shown for user {user_id}: {tokens_display}")

    except Exception as e:
        logger.exception(f"[Profile] Error for user {user_id}: {e}")
        await message.answer(
            "⚠️ Произошла ошибка при загрузке профиля. "
            "Пожалуйста, попробуйте позже."
        )


@router.callback_query(lambda c: c.data == "cancel_autopay")
async def handle_cancel_autopay(callback: CallbackQuery):
    """Отключает автопродление подписки"""
    user_id = callback.from_user.id
    
    try:
        await block_autopay(user_id)
        
        await callback.message.edit_text(
            "✅ <b>Автопродление отключено</b>\n\n"
            "Ваша текущая подписка будет действовать до окончания срока, "
            "после чего не будет продлена автоматически.\n\n"
            "Вы можете оформить новую подписку в любой момент: /subscribe",
            parse_mode="HTML"
        )
        
        await callback.answer("✅ Автопродление отключено")
        
        logger.info(f"[Profile] Autopay disabled for user {user_id}")
        
    except Exception as e:
        logger.exception(f"[Profile] Error disabling autopay for user {user_id}: {e}")
        await callback.answer(
            "⚠️ Ошибка при отключении автопродления. Попробуйте позже.",
            show_alert=True
        )