from fastapi import APIRouter, Request
from aiogram import Dispatcher, Bot
from app.bot.bot import dp, bot

telegram_router = APIRouter()

@telegram_router.post("/telegram")
async def telegram_webhook(request: Request):
    update_data = await request.json()
    try:
        await dp.feed_raw_update(bot, update_data)
    except Exception as e:
        import logging
        logging.exception("Ошибка при обработке Telegram update")
    return {"ok": True}
