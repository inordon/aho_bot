"""
Модуль работы с пользователями и ролями
CRUD операции, управление ролями
"""

import os
from typing import Optional, List, Dict, Any
from datetime import datetime

from models.database import Database
from utils.logger import get_logger

logger = get_logger(__name__)

# Маппинг ролей на типы заявок
ROLE_TO_TICKET_TYPE = {
    "manager_pass": "pass",
    "manager_purchase": "purchase",
    "manager_repair": "repair",
    "manager_other": "other",
    "lead": None,  # Все типы
    "admin": None,  # Все типы
}

# Все доступные роли
ALL_ROLES = [
    "user",
    "manager_pass",
    "manager_purchase",
    "manager_repair",
    "manager_other",
    "lead",
    "admin",
]


class UserModel:
    """Модель для работы с пользователями"""
    
    def __init__(self, db: Database):
        self.db = db
    
    async def get_or_create(
        self,
        telegram_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Получить или создать пользователя"""
        
        # Проверяем существование
        user = await self.db.fetchrow(
            "SELECT * FROM users WHERE telegram_id = $1",
            telegram_id
        )
        
        if user:
            # Обновляем данные если изменились
            if (user["username"] != username or 
                user["first_name"] != first_name or 
                user["last_name"] != last_name):
                await self.db.execute(
                    """
                    UPDATE users 
                    SET username = $2, first_name = $3, last_name = $4
                    WHERE telegram_id = $1
                    """,
                    telegram_id, username, first_name, last_name
                )
            return dict(user)
        
        # Создаем нового
        user = await self.db.fetchrow(
            """
            INSERT INTO users (telegram_id, username, first_name, last_name)
            VALUES ($1, $2, $3, $4)
            RETURNING *
            """,
            telegram_id, username, first_name, last_name
        )
        
        # Добавляем роль user по умолчанию
        await self.add_role(telegram_id, "user")
        
        logger.info(f"Создан новый пользователь: {telegram_id} ({username})")
        return dict(user)
    
    async def get_by_telegram_id(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        """Получить пользователя по telegram_id"""
        user = await self.db.fetchrow(
            "SELECT * FROM users WHERE telegram_id = $1",
            telegram_id
        )
        return dict(user) if user else None
    
    async def get_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получить пользователя по внутреннему ID"""
        user = await self.db.fetchrow(
            "SELECT * FROM users WHERE id = $1",
            user_id
        )
        return dict(user) if user else None
    
    async def get_user_roles(self, telegram_id: int) -> List[str]:
        """Получить все роли пользователя"""
        roles = await self.db.fetch(
            """
            SELECT r.name FROM roles r
            JOIN user_roles ur ON r.id = ur.role_id
            JOIN users u ON u.id = ur.user_id
            WHERE u.telegram_id = $1
            """,
            telegram_id
        )
        return [r["name"] for r in roles]
    
    async def has_role(self, telegram_id: int, role: str) -> bool:
        """Проверить наличие роли у пользователя"""
        roles = await self.get_user_roles(telegram_id)
        return role in roles
    
    async def has_any_role(self, telegram_id: int, roles: List[str]) -> bool:
        """Проверить наличие любой из ролей"""
        user_roles = await self.get_user_roles(telegram_id)
        return bool(set(user_roles) & set(roles))
    
    async def add_role(
        self,
        telegram_id: int,
        role: str,
        assigned_by: Optional[int] = None
    ) -> bool:
        """Добавить роль пользователю"""
        if role not in ALL_ROLES:
            logger.warning(f"Попытка добавить несуществующую роль: {role}")
            return False
        
        try:
            # Получаем user_id и role_id
            user = await self.get_by_telegram_id(telegram_id)
            if not user:
                logger.warning(f"Пользователь не найден: {telegram_id}")
                return False
            
            role_record = await self.db.fetchrow(
                "SELECT id FROM roles WHERE name = $1",
                role
            )
            if not role_record:
                logger.warning(f"Роль не найдена в БД: {role}")
                return False
            
            # Добавляем связь
            await self.db.execute(
                """
                INSERT INTO user_roles (user_id, role_id, assigned_by)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id, role_id) DO NOTHING
                """,
                user["id"], role_record["id"], assigned_by
            )
            
            logger.info(f"Роль {role} добавлена пользователю {telegram_id}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка добавления роли: {e}")
            return False
    
    async def remove_role(self, telegram_id: int, role: str) -> bool:
        """Удалить роль у пользователя"""
        try:
            user = await self.get_by_telegram_id(telegram_id)
            if not user:
                return False
            
            role_record = await self.db.fetchrow(
                "SELECT id FROM roles WHERE name = $1",
                role
            )
            if not role_record:
                return False
            
            result = await self.db.execute(
                """
                DELETE FROM user_roles 
                WHERE user_id = $1 AND role_id = $2
                """,
                user["id"], role_record["id"]
            )
            
            logger.info(f"Роль {role} удалена у пользователя {telegram_id}")
            return "DELETE 1" in result
            
        except Exception as e:
            logger.error(f"Ошибка удаления роли: {e}")
            return False
    
    async def get_managers_for_type(self, ticket_type: str) -> List[Dict[str, Any]]:
        """Получить менеджеров для типа заявки"""
        role_name = f"manager_{ticket_type}"
        
        managers = await self.db.fetch(
            """
            SELECT u.* FROM users u
            JOIN user_roles ur ON u.id = ur.user_id
            JOIN roles r ON r.id = ur.role_id
            WHERE r.name IN ($1, 'lead', 'admin')
            AND u.is_active = TRUE
            """,
            role_name
        )
        
        return [dict(m) for m in managers]
    
    async def get_all_managers(self) -> List[Dict[str, Any]]:
        """Получить всех менеджеров с их ролями"""
        managers = await self.db.fetch(
            """
            SELECT 
                u.telegram_id,
                u.username,
                u.first_name,
                u.last_name,
                ARRAY_AGG(r.name) as roles
            FROM users u
            JOIN user_roles ur ON u.id = ur.user_id
            JOIN roles r ON r.id = ur.role_id
            WHERE r.name != 'user'
            GROUP BY u.id, u.telegram_id, u.username, u.first_name, u.last_name
            ORDER BY u.first_name
            """
        )
        return [dict(m) for m in managers]
    
    async def is_admin(self, telegram_id: int) -> bool:
        """Проверить, является ли пользователь администратором"""
        # Проверяем роль в БД
        has_admin_role = await self.has_role(telegram_id, "admin")
        
        # Также проверяем переменную окружения
        admin_id = os.getenv("ADMIN_ID")
        is_env_admin = admin_id and int(admin_id) == telegram_id
        
        return has_admin_role or is_env_admin
    
    async def can_manage_ticket(self, telegram_id: int, ticket_type: str) -> bool:
        """Проверить, может ли пользователь управлять заявкой данного типа"""
        roles = await self.get_user_roles(telegram_id)
        
        # Администраторы и руководители могут всё
        if "admin" in roles or "lead" in roles:
            return True
        
        # Проверяем соответствующую роль менеджера
        required_role = f"manager_{ticket_type}"
        return required_role in roles


async def get_user_model(db: Database) -> UserModel:
    """Фабрика для получения модели пользователей"""
    return UserModel(db)
