from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from app.services.user import get_or_create_user, get_user_by_id, set_user_timezone, FREE_TOKENS_COUNT
import logging

router = Router()
logger = logging.getLogger(__name__)

WELCOME_TEXT = """👋 Привет, {name}!

Я помогу тебе считать калории по фото или описанию блюд.

<b>Как пользоваться:</b>
📸 Сфотографируй блюдо
📝 Или опиши текстом (например: "гречка 200г с курицей")
🎤 Или надиктуй голосовым сообщением

Я точно определю вес продуктов и рассчитаю:
- Калории
- Белки, жиры, углеводы
- Итоги за день

<b>Полезные команды:</b>
/today — итоги за сегодня
/week — статистика за неделю
/subscribe — подписка (больше запросов)
/bots — наши другие проекты

У тебя есть <b>{tokens} бесплатных запросов</b> на сегодня. Они обновляются ежедневно.

Пользуясь ботом, ты принимаешь <a href="https://docs.google.com/document/d/10JTUzBqa3_L4RWfF8TxXdHiyYeLelvw-3rwrybZA-q4/edit?tab=t.0#heading=h.arj7vefczzgi">пользовательское соглашение</a> и <a href="https://telegram.org/privacy-tpa">политику конфиденциальности</a>."""


TIMEZONE_TEXT = """🌍 <b>Настройка часового пояса</b>

Выбери свой часовой пояс для точного подсчета калорий за день:"""


def get_timezone_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора часового пояса"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🇷🇺 Москва (МСК, UTC+3)",
            callback_data="tz:Europe/Moscow"
        )],
        [InlineKeyboardButton(
            text="🇷🇺 Калининград (UTC+2)",
            callback_data="tz:Europe/Kaliningrad"
        )],
        [InlineKeyboardButton(
            text="🇷🇺 Екатеринбург (UTC+5)",
            callback_data="tz:Asia/Yekaterinburg"
        )],
        [InlineKeyboardButton(
            text="🇷🇺 Новосибирск (UTC+7)",
            callback_data="tz:Asia/Novosibirsk"
        )],
        [InlineKeyboardButton(
            text="🇷🇺 Владивосток (UTC+10)",
            callback_data="tz:Asia/Vladivostok"
        )],
        [InlineKeyboardButton(
            text="🌏 Другой часовой пояс",
            callback_data="tz:custom"
        )],
        [InlineKeyboardButton(
            text="⏭️ Пропустить",
            callback_data="tz:skip"
        )]
    ])


@router.message(CommandStart())
async def handle_start(message: Message, state: FSMContext):
    """
    Обработка команды /start
    
    Создает пользователя если новый, предлагает настроить timezone
    """
    user_id = message.from_user.id
    user_name = message.from_user.first_name or "друг"

    try:
        # Создаем/получаем пользователя
        user = await get_or_create_user(user_id, user_name)
        
        # Проверяем, настроен ли timezone
        user_tz = user.get("timezone")
        needs_timezone_setup = (
            not user_tz or 
            user_tz == "UTC" or
            user.get("id") == user_id  # Новый пользователь (ID совпадает с tg_id)
        )
        
        if needs_timezone_setup:
            # Предлагаем настроить timezone
            await message.answer(
                TIMEZONE_TEXT,
                reply_markup=get_timezone_keyboard(),
                parse_mode="HTML"
            )
        else:
            # Показываем приветствие
            tokens = user.get("free_tokens", FREE_TOKENS_COUNT)
            await message.answer(
                WELCOME_TEXT.format(name=user_name, tokens=tokens),
                parse_mode="HTML",
                disable_web_page_preview=True
            )
        
        # Очищаем состояние FSM
        await state.clear()
        
        logger.info(f"[Start] User {user_id} ({user_name}) processed /start")

    except Exception as e:
        logger.exception(f"[Start] Error for user {user_id}: {e}")
        await message.answer(
            "⚠️ Произошла ошибка при запуске бота. "
            "Пожалуйста, попробуйте позже или обратитесь в поддержку."
        )


@router.callback_query(lambda c: c.data and c.data.startswith("tz:"))
async def handle_timezone_selection(callback: CallbackQuery):
    """Обработка выбора часового пояса"""
    user_id = callback.from_user.id
    user_name = callback.from_user.first_name or "друг"
    
    try:
        action = callback.data.split(":", 1)[1]
        
        if action == "skip":
            # Пропускаем настройку timezone
            await callback.answer("⏭️ Настройка пропущена")
            user = await get_user_by_id(user_id)
            tokens = user.get("free_tokens", FREE_TOKENS_COUNT)
            
            await callback.message.edit_text(
                WELCOME_TEXT.format(name=user_name, tokens=tokens),
                parse_mode="HTML",
                disable_web_page_preview=True
            )
            
        elif action == "custom":
            # Запрос кастомного timezone
            await callback.answer()
            await callback.message.edit_text(
                "🌍 <b>Выбор часового пояса</b>\n\n"
                "Отправьте название вашего города или часового пояса.\n\n"
                "Примеры:\n"
                "• Минск\n"
                "• Киев\n"
                "• Алматы\n"
                "• Europe/London\n"
                "• Asia/Tokyo\n\n"
                "Или используйте /start для возврата к началу.",
                parse_mode="HTML"
            )
            
        else:
            # Устанавливаем выбранный timezone
            timezone = action
            
            try:
                await set_user_timezone(user_id, timezone)
                await callback.answer(f"✅ Установлен: {timezone}")
                
                user = await get_user_by_id(user_id)
                tokens = user.get("free_tokens", FREE_TOKENS_COUNT)
                
                await callback.message.edit_text(
                    WELCOME_TEXT.format(name=user_name, tokens=tokens),
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
                
                logger.info(f"[Start] User {user_id} set timezone: {timezone}")
                
            except ValueError as e:
                await callback.answer(f"⚠️ Ошибка: {e}", show_alert=True)
                
    except Exception as e:
        logger.exception(f"[Start] Timezone selection error for user {user_id}: {e}")
        await callback.answer("⚠️ Ошибка. Попробуйте еще раз.", show_alert=True)