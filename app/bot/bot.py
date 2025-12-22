# app/bot/bot.py
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.enums import ParseMode
from app.db.redis_client import redis, init_arq_redis
from app.config import settings
from app.bot.middleware.fastapi_app import FastAPIAppMiddleware
from app.bot.middleware.kick_on_private import KickNonPrivateMiddleware
from app.bot.handlers import start, profile, entry, subscribe, admin, system, help, bots, food  # ✅ food вместо stats
from app.bot.middleware.redis_middleware import RedisMiddleware

# Инициализация хранилища состояний для FSM
storage = RedisStorage(redis=redis)

bot = Bot(
    token=settings.bot_token,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

# Инициализация диспетчера
dp = Dispatcher(storage=storage)

# Включение роутеров в диспетчер
# Порядок включения может иметь значение для обработки команд
dp.include_router(system.router)     # Обработка системных событий
dp.include_router(start.router)      # Команда /start
dp.include_router(bots.router)       # Команда /bots
dp.include_router(profile.router)    # Команда /profile
dp.include_router(subscribe.router)  # Команда /subscribe
dp.include_router(admin.router)      # Админ команды
dp.include_router(help.router)       # Команда /help
dp.include_router(food.router)       # ✅ Команда /food (было stats.router)
dp.include_router(entry.router)      # Обработка сообщений (текст, фото, голос) - ВСЕГДА В КОНЦЕ


def setup_middlewares(app_instance):
    """
    Настройка middleware для диспетчера
    
    ИСПРАВЛЕНИЕ: RedisMiddleware теперь не требует параметр при инициализации
    """
    from app.db.redis_client import get_arq_redis

    dp.message.middleware(KickNonPrivateMiddleware())
    dp.message.middleware(FastAPIAppMiddleware(app_instance))
    dp.message.middleware(RedisMiddleware())  # ✅ ИСПРАВЛЕНИЕ: без параметра
    
    dp.callback_query.middleware(FastAPIAppMiddleware(app_instance))
    dp.callback_query.middleware(RedisMiddleware())  # ✅ ИСПРАВЛЕНИЕ: без параметра