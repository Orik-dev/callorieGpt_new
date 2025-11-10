# from aiogram import Router
# from aiogram.filters import Command
# from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
# from app.config import settings

# router = Router()


# @router.message(Command("help"))
# async def handle_help(message: Message):
#     """Показывает помощь и контакты поддержки"""
#     text = """🆘 <b>Помощь и поддержка</b>

# <b>Как пользоваться ботом:</b>
# 1️⃣ Отправьте фото блюда
# 2️⃣ Или опишите текстом (например: "гречка 200г")
# 3️⃣ Получите точный подсчет КБЖУ

# <b>Полезные команды:</b>
# /start — Начать работу
# /today — Итоги за сегодня
# /week — Статистика за неделю
# /profile — Ваш профиль
# /subscribe — Оформить подписку
# /bots — Наши другие проекты

# <b>Возникли вопросы или проблемы?</b>
# Напишите в поддержку — мы поможем!"""

#     keyboard = InlineKeyboardMarkup(inline_keyboard=[
#         [InlineKeyboardButton(
#             text="💬 Написать в поддержку",
#             url="https://t.me/guard_gpt"
#         )]
#     ])

#     await message.answer(
#         text,
#         reply_markup=keyboard,
#         parse_mode="HTML"
#     )

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from app.config import settings

router = Router()


@router.message(Command("help"))
async def handle_help(message: Message):
    """Показывает помощь и контакты поддержки"""
    text = """🆘 <b>Помощь и поддержка</b>

<b>Как пользоваться ботом:</b>
1️⃣ Отправьте фото блюда
2️⃣ Или опишите текстом (например: "гречка 200г")
3️⃣ Получите точный подсчет КБЖУ

<b>Полезные команды:</b>
/start — Начать работу
/food — История питания (7 дней)
/profile — Профиль и статистика
/subscribe — Оформить подписку
/bots — Наши другие проекты

<b>Возникли вопросы или проблемы?</b>
Напишите в поддержку — мы поможем!"""

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="💬 Написать в поддержку",
            url="https://t.me/guard_gpt"
        )]
    ])

    await message.answer(
        text,
        reply_markup=keyboard,
        parse_mode="HTML"
    )