# app/bot/handlers/start.py
from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from app.services.user import get_or_create_user, FREE_TOKENS_COUNT
import logging

router = Router()
logger = logging.getLogger(__name__)

@router.message(CommandStart())
async def handle_start(message: Message):

    user_id = message.from_user.id
    user_name = message.from_user.first_name

    try:
        # Получаем или создаём пользователя. При создании выдаётся FREE_TOKENS_COUNT
        await get_or_create_user(user_id, user_name)

        text = (
            f"Здравствуйте, {user_name}!\n"
            f"Пришлите фото, голосовое или описание блюда, и я рассчитаю калории, белки, жиры и углеводы.\n"
            f"/bots — Наши другие проекты.\n\n"
             'Пользуясь Ботом, Вы принимаете наше <a href="https://docs.google.com/document/d/10JTUzBqa3_L4RWfF8TxXdHiyYeLelvw-3rwrybZA-q4/edit?tab=t.0#heading=h.arj7vefczzgi">пользовательское соглашение</a> и <a href="https://telegram.org/privacy-tpa">политику конфиденциальности</a>.'
            # f"У вас есть {FREE_TOKENS_COUNT} бесплатных запросов на сегодня. "
            # f"Они обновляются ежедневно. Хотите больше? Оформите подписку: /subscribe"
        )
        await message.answer(text,parse_mode="HTML",disable_web_page_preview=True)
        logger.info(f"Команда /start обработана для пользователя {user_id}.")

    except Exception as e:
        logger.exception(f"Ошибка при обработке команды /start для пользователя {user_id}: {e}")
        await message.answer("Произошла ошибка при запуске бота. Пожалуйста, попробуйте позже.")