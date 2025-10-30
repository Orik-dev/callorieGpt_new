from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from app.config import settings

router = Router()

@router.message(Command("help"))
async def handle_help(message: Message):
    text = """
🆘 *Калории по фото AI*  
Вопросы, проблемы, предложения — пишите.
"""

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Написать", url=f"https://t.me/@guard_gpt")]
    ])

    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
