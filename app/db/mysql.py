# app/db/mysql.py
import aiomysql
from fastapi import FastAPI
from app.config import settings
import logging

logger = logging.getLogger(__name__)

class MySQLClient:
    def __init__(self):
        self.pool = None

    async def init(self, app: FastAPI):
        """Инициализирует пул соединений с MySQL."""
        logger.info("Попытка инициализации MySQL пула соединений...")
        try:
            self.pool = await aiomysql.create_pool(
                host=settings.db_host,
                port=settings.db_port,
                user=settings.db_user,
                password=settings.db_password,
                db=settings.db_name,
                minsize=5, # Минимальное количество соединений в пуле
                maxsize=20, # Максимальное количество соединений в пуле
                autocommit=True # Автоматический коммит транзакций
            )
            app.state.db_pool = self.pool # Сохраняем пул в состоянии FastAPI приложения
            logger.info("MySQL пул соединений успешно инициализирован.")
        except Exception as e:
            logger.critical(f"Критическая ошибка при инициализации MySQL пула: {e}")
            raise # Перевыбрасываем исключение, так как без БД приложение неработоспособно

    async def close(self):
        """Закрывает пул соединений с MySQL."""
        if self.pool:
            logger.info("Закрытие MySQL пула соединений...")
            self.pool.close()
            await self.pool.wait_closed()
            logger.info("MySQL пул соединений закрыт.")

    async def fetchone(self, query: str, params: tuple = ()):
        """Выполняет SELECT запрос и возвращает одну запись (словарь)."""
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur: # DictCursor для получения результатов как словарей
                await cur.execute(query, params)
                return await cur.fetchone()

    async def fetchall(self, query: str, params: tuple = ()):
        """Выполняет SELECT запрос и возвращает все записи (список словарей)."""
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(query, params)
                return await cur.fetchall()

    async def execute(self, query: str, params: tuple = ()):
        """Выполняет DML (INSERT, UPDATE, DELETE) запрос."""
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, params)
                # Autocommit=True в create_pool, поэтому COMMIT не требуется явно

mysql = MySQLClient() # Создаем экземпляр клиента MySQL

async def init_db(app: FastAPI):
    """Функция инициализации БД для FastAPI lifespan."""
    await mysql.init(app)

async def close_db(app: FastAPI):
    """Функция закрытия БД для FastAPI lifespan."""
    await mysql.close()