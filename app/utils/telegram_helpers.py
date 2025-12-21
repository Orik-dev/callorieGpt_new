# app/utils/telegram_helpers.py
"""
Утилиты для работы с Telegram API с retry и обработкой ошибок
"""
import html
import asyncio
import logging
from typing import Optional
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError, TelegramRetryAfter

logger = logging.getLogger(__name__)

# Максимум попыток для retry
MAX_RETRIES = 3
RETRY_DELAY = 1.0


def escape_html(text: str) -> str:
    """Экранирует HTML-символы в тексте"""
    if not text:
        return ""
    return html.escape(str(text))


async def safe_send_message(
    bot: Bot,
    chat_id: int,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    parse_mode: str = "HTML"
) -> Optional[int]:
    """
    Безопасная отправка сообщения с retry
    
    Returns:
        message_id или None при ошибке
    """
    for attempt in range(MAX_RETRIES):
        try:
            msg = await bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
            return msg.message_id
            
        except TelegramRetryAfter as e:
            logger.warning(f"Rate limited, waiting {e.retry_after}s")
            await asyncio.sleep(e.retry_after)
            
        except TelegramNetworkError as e:
            logger.warning(f"Network error (attempt {attempt + 1}): {e}")
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY * (attempt + 1))
            else:
                logger.error(f"Failed to send message after {MAX_RETRIES} attempts")
                return None
                
        except TelegramBadRequest as e:
            error_msg = str(e).lower()
            
            # HTML parsing error - попробуем без форматирования
            if "can't parse entities" in error_msg:
                logger.warning(f"HTML parse error, retrying without formatting: {e}")
                try:
                    msg = await bot.send_message(
                        chat_id=chat_id,
                        text=text.replace("<b>", "").replace("</b>", "")
                                .replace("<i>", "").replace("</i>", "")
                                .replace("<code>", "").replace("</code>", ""),
                        reply_markup=reply_markup,
                        parse_mode=None
                    )
                    return msg.message_id
                except Exception as e2:
                    logger.error(f"Failed even without HTML: {e2}")
                    return None
            
            # Другие ошибки - не ретраим
            logger.error(f"Telegram Bad Request: {e}")
            return None
            
        except Exception as e:
            logger.exception(f"Unexpected error sending message: {e}")
            return None
    
    return None


async def safe_edit_message(
    bot: Bot,
    chat_id: int,
    message_id: int,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    parse_mode: str = "HTML"
) -> bool:
    """
    Безопасное редактирование сообщения с retry
    
    Returns:
        True если успешно, False при ошибке
    """
    for attempt in range(MAX_RETRIES):
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
            return True
            
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            
        except TelegramNetworkError as e:
            logger.warning(f"Network error editing (attempt {attempt + 1}): {e}")
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY * (attempt + 1))
            else:
                return False
                
        except TelegramBadRequest as e:
            error_msg = str(e).lower()
            
            if "message is not modified" in error_msg:
                return True  # Не ошибка
                
            if "message to edit not found" in error_msg:
                logger.warning("Message not found, sending new")
                await safe_send_message(bot, chat_id, text, reply_markup, parse_mode)
                return True
                
            if "can't parse entities" in error_msg:
                try:
                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=text.replace("<b>", "").replace("</b>", "")
                                .replace("<i>", "").replace("</i>", ""),
                        reply_markup=reply_markup,
                        parse_mode=None
                    )
                    return True
                except:
                    return False
            
            logger.error(f"Bad request editing: {e}")
            return False
            
        except Exception as e:
            logger.exception(f"Unexpected error editing: {e}")
            return False
    
    return False


async def safe_delete_message(bot: Bot, chat_id: int, message_id: int) -> bool:
    """Безопасное удаление сообщения"""
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
        return True
    except TelegramBadRequest as e:
        if "message to delete not found" in str(e).lower():
            return True  # Уже удалено
        logger.warning(f"Failed to delete message: {e}")
        return False
    except Exception as e:
        logger.warning(f"Error deleting message: {e}")
        return False