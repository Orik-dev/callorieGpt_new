from fastapi import APIRouter, Request, Header, HTTPException
from aiogram import Dispatcher, Bot
from app.bot.bot import dp, bot
from app.config import settings
import logging
import asyncio
import hmac

logger = logging.getLogger(__name__)
telegram_router = APIRouter()


@telegram_router.post("/telegram")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str = Header(None)
):
    """
    Обработчик Telegram webhook с проверкой секрета
    
    Security: Проверяет X-Telegram-Bot-Api-Secret-Token заголовок
    
    ИСПРАВЛЕНИЕ: Неблокирующая обработка - сразу отвечаем Telegram "OK",
    а обработку делаем в фоне, чтобы не было подвисаний
    """
    # Проверка секретного токена (constant-time comparison)
    expected = settings.webhook_secret or ""
    received = x_telegram_bot_api_secret_token or ""
    if not hmac.compare_digest(received, expected):
        logger.warning(f"❌ Invalid webhook secret from {request.client.host}")
        raise HTTPException(status_code=403, detail="Forbidden")
    
    # Получаем данные обновления
    try:
        update_data = await request.json()
        logger.debug(f"📨 Received update: {update_data.get('update_id')}")
    except Exception as e:
        logger.error(f"❌ Failed to parse update JSON: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON")
    
    # ✅ ИСПРАВЛЕНИЕ: Запускаем обработку в фоне (неблокирующая)
    # Сразу отвечаем Telegram "OK", чтобы не было подвисаний
    asyncio.create_task(_process_update(update_data))
    
    # Возвращаем успех сразу
    return {"ok": True}


async def _process_update(update_data: dict):
    """
    Фоновая обработка обновления от Telegram
    
    Вызывается асинхронно, не блокирует webhook endpoint
    """
    try:
        await dp.feed_raw_update(bot, update_data)
        logger.debug(f"✅ Update {update_data.get('update_id')} processed")
    except Exception as e:
        logger.exception(f"❌ Error processing Telegram update {update_data.get('update_id')}: {e}")
        # Не возвращаем 500, чтобы Telegram не ретраил


@telegram_router.get("/telegram/status")
async def telegram_status():
    """Проверка статуса Telegram бота"""
    try:
        me = await bot.get_me()
        return {
            "status": "ok",
            "bot_username": me.username,
            "bot_id": me.id,
            "bot_name": me.first_name
        }
    except Exception as e:
        logger.error(f"Failed to get bot info: {e}")
        return {
            "status": "error",
            "error": str(e)
        }