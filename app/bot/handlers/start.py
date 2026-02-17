# app/bot/handlers/start.py
from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, BotCommand
from aiogram.fsm.context import FSMContext
from app.services.user import get_or_create_user, get_user_by_id, set_user_timezone, FREE_TOKENS_COUNT
from app.utils.telegram_helpers import escape_html, safe_send_message
import logging

router = Router()
logger = logging.getLogger(__name__)

WELCOME_TEXT = """Привет, {name}!

Я считаю калории по фото или описанию. Просто пиши как удобно — я пойму.

<b>Добавить еду:</b>
- Отправь фото блюда
- Или напиши: «гречка с курицей», «съел яблоко»
- Или отправь голосовое

<b>Примеры:</b>
- «на обед борщ и хлеб»
- «перекусил бананом»
- «выпил латте»

<b>Удалить/отменить:</b>
- «убери последнее»
- «удали борщ»

<b>Только посчитать:</b>
- «сколько калорий в пицце?»

<b>Команды:</b>
/food — рацион за сегодня
/profile — профиль и настройки
/subscribe — подписка

У тебя <b>{tokens}</b> запросов на сегодня.
С подпиской — 25 в день → /subscribe

━━━━━━━━━━━━━━━━
⚠️ Данные о калориях приблизительные и не являются медицинской рекомендацией.

Используя бота, ты принимаешь <a href="https://docs.google.com/document/d/10JTUzBqa3_L4RWfF8TxXdHiyYeLelvw-3rwrybZA-q4/edit?tab=t.0#heading=h.arj7vefczzgi">пользовательское соглашение</a> и <a href="https://docs.google.com/document/d/11zwBLkxUQH0bRcXwTOeYqBmAS4nMAWMcy-e0Ab00vTw/edit?usp=drivesdk">политику конфиденциальности</a>.

💬 Поддержка: @guard_gpt"""


# Команды для меню бота (кнопка ☰ слева)
BOT_COMMANDS = [
    BotCommand(command="food", description="🍽 Рацион за сегодня"),
    BotCommand(command="profile", description="👤 Мой профиль"),
    BotCommand(command="subscribe", description="💎 Подписка"),
    BotCommand(command="help", description="❓ Помощь"),
    BotCommand(command="start", description="🔄 Перезапустить"),
]


async def setup_bot_commands():
    from app.bot.bot import bot
    try:
        await bot.set_my_commands(BOT_COMMANDS)
        logger.info("✅ Bot commands menu set")
    except Exception as e:
        logger.error(f"❌ Failed to set bot commands: {e}")


def get_timezone_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора часового пояса"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Москва UTC+3", callback_data="tz:Europe/Moscow"),
            InlineKeyboardButton(text="Минск UTC+3", callback_data="tz:Europe/Minsk"),
        ],
        [
            InlineKeyboardButton(text="Калининград UTC+2", callback_data="tz:Europe/Kaliningrad"),
            InlineKeyboardButton(text="Киев UTC+2", callback_data="tz:Europe/Kiev"),
        ],
        [
            InlineKeyboardButton(text="Самара UTC+4", callback_data="tz:Europe/Samara"),
            InlineKeyboardButton(text="Баку UTC+4", callback_data="tz:Asia/Baku"),
        ],
        [
            InlineKeyboardButton(text="Екатеринбург UTC+5", callback_data="tz:Asia/Yekaterinburg"),
            InlineKeyboardButton(text="Ташкент UTC+5", callback_data="tz:Asia/Tashkent"),
        ],
        [
            InlineKeyboardButton(text="Омск UTC+6", callback_data="tz:Asia/Omsk"),
            InlineKeyboardButton(text="Алматы UTC+6", callback_data="tz:Asia/Almaty"),
        ],
        [InlineKeyboardButton(text="Красноярск UTC+7", callback_data="tz:Asia/Krasnoyarsk")],
        [InlineKeyboardButton(text="Иркутск UTC+8", callback_data="tz:Asia/Irkutsk")],
        [InlineKeyboardButton(text="Якутск UTC+9", callback_data="tz:Asia/Yakutsk")],
        [InlineKeyboardButton(text="Владивосток UTC+10", callback_data="tz:Asia/Vladivostok")],
        [InlineKeyboardButton(text="Камчатка UTC+12", callback_data="tz:Asia/Kamchatka")],
        [InlineKeyboardButton(text="Пропустить", callback_data="tz:skip")],
    ])


@router.message(CommandStart())
async def handle_start(message: Message, state: FSMContext):
    """Обработка команды /start"""
    user_id = message.from_user.id
    user_name = escape_html(message.from_user.first_name or "друг")

    try:
        user = await get_or_create_user(user_id, message.from_user.first_name or "User")
        
        user_tz = user.get("timezone")
        needs_timezone_setup = not user_tz or user_tz == "UTC"
        
        if needs_timezone_setup:
            await message.answer(
                "<b>Настройка часового пояса</b>\n\nВыбери свой часовой пояс:",
                reply_markup=get_timezone_keyboard(),
                parse_mode="HTML"
            )
        else:
            tokens = user.get("free_tokens", FREE_TOKENS_COUNT)
            await message.answer(
                WELCOME_TEXT.format(name=user_name, tokens=tokens),
                parse_mode="HTML",
                disable_web_page_preview=True
            )
        
        await state.clear()
        logger.info(f"[Start] User {user_id} ({user_name}) started")

    except Exception as e:
        logger.exception(f"[Start] Error for user {user_id}: {e}")
        await message.answer(
            "Привет! Я бот для подсчёта калорий.\n\n"
            "Отправь фото еды или напиши что съел.\n"
            "Команды: /food /profile /subscribe"
        )


@router.callback_query(lambda c: c.data and c.data.startswith("tz:"))
async def handle_timezone_selection(callback: CallbackQuery):
    """Обработка выбора часового пояса"""
    user_id = callback.from_user.id
    user_name = escape_html(callback.from_user.first_name or "друг")
    
    try:
        action = callback.data.split(":", 1)[1]
        
        if action == "skip":
            await callback.answer("Пропущено")
            await set_user_timezone(user_id, "Europe/Moscow")
        else:
            await set_user_timezone(user_id, action)
            await callback.answer("Установлено")
        
        user = await get_user_by_id(user_id)
        tokens = user.get("free_tokens", FREE_TOKENS_COUNT)
        
        await callback.message.edit_text(
            WELCOME_TEXT.format(name=user_name, tokens=tokens),
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        
        logger.info(f"[Start] User {user_id} set timezone: {action}")
                
    except Exception as e:
        logger.exception(f"[Start] Timezone error for user {user_id}: {e}")
        await callback.answer("Ошибка. Попробуйте /start", show_alert=True)


