"""
Модуль работы с базой данных PostgreSQL
Пул соединений, миграции, базовые операции
"""

import os
import asyncio
from typing import Optional, List, Dict, Any

import asyncpg
from asyncpg.pool import Pool

from utils.logger import get_logger

logger = get_logger(__name__)


class Database:
    """Класс для работы с PostgreSQL"""
    
    _instance: Optional['Database'] = None
    _pool: Optional[Pool] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        self.host = os.getenv("DB_HOST", "postgres")
        self.port = int(os.getenv("DB_PORT", "5432"))
        self.user = os.getenv("DB_USER", "aho_user")
        self.password = os.getenv("DB_PASSWORD", "aho_password")
        self.database = os.getenv("DB_NAME", "aho_bot")
        self.min_pool_size = int(os.getenv("DB_POOL_MIN", "5"))
        self.max_pool_size = int(os.getenv("DB_POOL_MAX", "20"))
    
    async def init(self) -> None:
        """Инициализация пула соединений и миграций"""
        if self._pool is not None:
            return
        
        try:
            logger.info(f"Подключение к PostgreSQL: {self.host}:{self.port}/{self.database}")
            
            # Создание пула соединений
            self._pool = await asyncpg.create_pool(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
                min_size=self.min_pool_size,
                max_size=self.max_pool_size,
                command_timeout=60,
            )
            
            logger.info("Пул соединений создан")
            
            # Запуск миграций
            await self._run_migrations()
            
            logger.info("База данных инициализирована")
            
        except Exception as e:
            logger.error(f"Ошибка подключения к БД: {e}")
            raise
    
    async def _run_migrations(self) -> None:
        """Выполнение миграций из SQL файла"""
        schema_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "schemas",
            "database_schema.sql"
        )
        
        if not os.path.exists(schema_path):
            logger.warning(f"Файл схемы не найден: {schema_path}")
            return
        
        try:
            with open(schema_path, "r", encoding="utf-8") as f:
                schema_sql = f.read()
            
            async with self._pool.acquire() as conn:
                await conn.execute(schema_sql)
            
            logger.info("Миграции выполнены успешно")
            
        except Exception as e:
            logger.error(f"Ошибка выполнения миграций: {e}")
            raise
    
    async def close(self) -> None:
        """Закрытие пула соединений"""
        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info("Пул соединений закрыт")
    
    @property
    def pool(self) -> Pool:
        """Получение пула соединений"""
        if self._pool is None:
            raise RuntimeError("База данных не инициализирована")
        return self._pool
    
    async def fetch(self, query: str, *args) -> List[asyncpg.Record]:
        """Выполнение SELECT запроса"""
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)
    
    async def fetchrow(self, query: str, *args) -> Optional[asyncpg.Record]:
        """Выполнение SELECT запроса с одной записью"""
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)
    
    async def fetchval(self, query: str, *args) -> Any:
        """Выполнение SELECT запроса с одним значением"""
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, *args)
    
    async def execute(self, query: str, *args) -> str:
        """Выполнение INSERT/UPDATE/DELETE запроса"""
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)
    
    async def executemany(self, query: str, args: List[tuple]) -> None:
        """Выполнение множественных INSERT запросов"""
        async with self.pool.acquire() as conn:
            await conn.executemany(query, args)
    
    async def transaction(self):
        """Контекстный менеджер для транзакций"""
        conn = await self.pool.acquire()
        try:
            async with conn.transaction():
                yield conn
        finally:
            await self.pool.release(conn)


# Синглтон инстанс базы данных
db = Database()


async def get_db() -> Database:
    """Получение инстанса базы данных"""
    if db._pool is None:
        await db.init()
    return db
