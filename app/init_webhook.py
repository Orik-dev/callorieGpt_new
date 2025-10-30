# # init_webhook.py
# import asyncio
# import logging
# from app.config import settings
# from app.bot.bot import bot # Импортируем объект bot
# from app.utils.logger import setup_logger 

# # Инициализация логгера при запуске модуля
# setup_logger()
# logger = logging.getLogger(__name__)

# async def main():
#     try:
#         logger.info("Попытка установки/проверки Telegram вебхука...")
#         info = await bot.get_webhook_info()
#         if info.url != settings.webhook_url:
#             logger.info(f"Текущий вебхук: {info.url}. Устанавливаем новый: {settings.webhook_url}")
#             await bot.set_webhook(
#                 url=settings.webhook_url,
#                 secret_token=settings.webhook_secret,
#                 drop_pending_updates=True # Удаляет все ожидающие обновления
#             )
#             logger.info(f"✅ Telegram вебхук успешно установлен: {settings.webhook_url}")
#         else:
#             logger.info(f"🔄 Telegram вебхук уже актуален: {info.url}")
#     except Exception as e:
#         logger.error(f"❌ Ошибка при установке Telegram вебхука: {e}", exc_info=True)
#     finally:
#         if bot.session:
#             await bot.session.close()
#             logger.debug("Сессия бота закрыта.")

# if __name__ == "__main__":
#     asyncio.run(main())

# init_webhook.py
import asyncio
import logging
from app.config import settings
from app.bot.bot import bot  # Импортируем объект bot
from app.utils.logger import setup_logger

# Инициализация логгера при запуске модуля
setup_logger()
logger = logging.getLogger(__name__)

async def main():
    try:
        logger.info("Попытка установки/проверки Telegram вебхука...")
        info = await bot.get_webhook_info()
        
        # ✅ Явно указываем все необходимые типы обновлений
        allowed_updates = [
            "message",
            "callback_query",
            "my_chat_member",
            "pre_checkout_query",    # ✅ КРИТИЧНО для платежей
            "successful_payment",    # ✅ КРИТИЧНО для платежей
        ]
        
        # Проверяем URL и allowed_updates
        needs_update = (
            info.url != settings.webhook_url or 
            set(info.allowed_updates or []) != set(allowed_updates)
        )
        
        if needs_update:
            logger.info(f"Текущий вебхук: {info.url}")
            logger.info(f"Текущие allowed_updates: {info.allowed_updates}")
            logger.info(f"Устанавливаем новый: {settings.webhook_url}")
            logger.info(f"С allowed_updates: {allowed_updates}")
            
            await bot.set_webhook(
                url=settings.webhook_url,
                secret_token=settings.webhook_secret,
                allowed_updates=allowed_updates,
                drop_pending_updates=True  # Удаляет все ожидающие обновления
            )
            
            logger.info(f"✅ Telegram вебхук успешно установлен: {settings.webhook_url}")
            logger.info(f"✅ Allowed updates: {', '.join(allowed_updates)}")
        else:
            logger.info(f"🔄 Telegram вебхук уже актуален: {info.url}")
            logger.info(f"✅ Allowed updates: {info.allowed_updates}")
            
    except Exception as e:
        logger.error(f"❌ Ошибка при установке Telegram вебхука: {e}", exc_info=True)
    finally:
        if bot.session:
            await bot.session.close()
            logger.debug("Сессия бота закрыта.")

if __name__ == "__main__":
    asyncio.run(main())