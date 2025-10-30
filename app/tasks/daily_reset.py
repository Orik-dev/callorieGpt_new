import logging
from app.services.user import update_tokens_daily

logger = logging.getLogger(__name__)

async def reset_tokens(ctx):  # добавили ctx
    try:
        logger.info("[Task] Запуск ежедневного сброса токенов.")
        await update_tokens_daily()
        logger.info("[Task] Ежедневный сброс токенов успешно завершен.")
    except Exception as e:
        logger.exception(f"[Task] Ошибка при ежедневном сбросе токенов: {e}")
