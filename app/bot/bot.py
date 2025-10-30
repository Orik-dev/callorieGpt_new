# app/bot/bot.py
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.enums import ParseMode
from app.db.redis_client import redis, init_arq_redis
from app.config import settings
from app.bot.middleware.fastapi_app import FastAPIAppMiddleware # Middleware для FastAPI app
from app.bot.middleware.kick_on_private import KickNonPrivateMiddleware # Middleware для FastAPI app
from app.bot.handlers import start, profile, entry, subscribe, admin, system,help,bots
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
dp.include_router(system.router)     # Обработка системных событий (добавление/удаление бота из чатов)
dp.include_router(start.router)      # Команда /start
dp.include_router(bots.router)     # Команда /bots
dp.include_router(profile.router)    # Команда /profile и коллбэки профиля
dp.include_router(subscribe.router)  # Команда /subscribe и коллбэки подписки
dp.include_router(admin.router)  
dp.include_router(help.router)      # Обработка основных сообщений (текст, фото, голос) - ОБЫЧНО В КОНЦЕ
dp.include_router(entry.router)      # Обработка основных сообщений (текст, фото, голос) - ОБЫЧНО В КОНЦЕ



def setup_middlewares(app_instance):
    from app.db.redis_client import arq_redis  # получим после инициализации

    dp.message.middleware(KickNonPrivateMiddleware())
    dp.message.middleware(FastAPIAppMiddleware(app_instance))
    dp.message.middleware(RedisMiddleware(arq_redis))  # ← важно: ArqRedis
    dp.callback_query.middleware(FastAPIAppMiddleware(app_instance))
    dp.callback_query.middleware(RedisMiddleware(arq_redis))
