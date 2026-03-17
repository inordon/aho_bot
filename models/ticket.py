"""
Модуль работы с заявками (tickets)
CRUD операции, история статусов
"""

import os
import json
from typing import Optional, List, Dict, Any
from datetime import datetime

from models.database import Database
from utils.logger import get_logger

logger = get_logger(__name__)

# Статусы заявок
TICKET_STATUSES = {
    "pending": "⏳ Ожидает",
    "in_progress": "🔄 В работе",
    "completed": "✅ Выполнено",
    "rejected": "❌ Отклонено",
}

# Типы заявок
TICKET_TYPES = {
    "pass": "🪪 Пропуск",
    "purchase": "🛒 Закупка",
    "repair": "🔧 Ремонт",
    "other": "❓ Другое",
}

# Приоритеты
TICKET_PRIORITIES = {
    "urgent": "🔴 Срочно",
    "normal": "🟡 Обычно",
    "low": "🟢 Планово",
}

# Маппинг типа на topic_id
def get_topic_id(ticket_type: str) -> Optional[int]:
    """Получить ID темы для типа заявки"""
    topic_ids = {
        "pass": os.getenv("PASS_TOPIC_ID"),
        "purchase": os.getenv("PURCHASE_TOPIC_ID"),
        "repair": os.getenv("REPAIR_TOPIC_ID"),
        "other": os.getenv("OTHER_TOPIC_ID"),
    }
    topic_id = topic_ids.get(ticket_type)
    return int(topic_id) if topic_id else None


class TicketModel:
    """Модель для работы с заявками"""
    
    def __init__(self, db: Database):
        self.db = db
    
    async def create(
        self,
        telegram_user_id: int,
        ticket_type: str,
        data: Dict[str, Any],
        priority: str = "normal",
        message_id: Optional[int] = None,
        topic_id: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """Создать новую заявку"""
        try:
            # Получаем user_id
            user = await self.db.fetchrow(
                "SELECT id FROM users WHERE telegram_id = $1",
                telegram_user_id
            )
            user_id = user["id"] if user else None
            
            # Создаем заявку
            ticket = await self.db.fetchrow(
                """
                INSERT INTO tickets 
                    (user_id, telegram_user_id, type, priority, data, message_id, topic_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING *
                """,
                user_id, telegram_user_id, ticket_type, priority,
                json.dumps(data, ensure_ascii=False), message_id, topic_id
            )
            
            # Записываем в историю
            await self._add_history(
                ticket["id"],
                None,
                "pending",
                telegram_user_id,
                None,
                "Заявка создана"
            )
            
            logger.info(f"Создана заявка #{ticket['id']} типа {ticket_type}")
            return dict(ticket)
            
        except Exception as e:
            logger.error(f"Ошибка создания заявки: {e}")
            return None
    
    async def get_by_id(self, ticket_id: int) -> Optional[Dict[str, Any]]:
        """Получить заявку по ID"""
        ticket = await self.db.fetchrow(
            "SELECT * FROM tickets WHERE id = $1",
            ticket_id
        )
        return dict(ticket) if ticket else None
    
    async def get_by_message_id(self, message_id: int) -> Optional[Dict[str, Any]]:
        """Получить заявку по ID сообщения"""
        ticket = await self.db.fetchrow(
            "SELECT * FROM tickets WHERE message_id = $1",
            message_id
        )
        return dict(ticket) if ticket else None
    
    async def update_message_id(self, ticket_id: int, message_id: int) -> bool:
        """Обновить ID сообщения заявки"""
        try:
            await self.db.execute(
                "UPDATE tickets SET message_id = $2 WHERE id = $1",
                ticket_id, message_id
            )
            return True
        except Exception as e:
            logger.error(f"Ошибка обновления message_id: {e}")
            return False
    
    async def update_status(
        self,
        ticket_id: int,
        new_status: str,
        changed_by: int,
        changed_by_username: Optional[str] = None,
        comment: Optional[str] = None
    ) -> bool:
        """Обновить статус заявки"""
        try:
            # Получаем текущий статус
            ticket = await self.get_by_id(ticket_id)
            if not ticket:
                return False
            
            old_status = ticket["status"]
            
            # Обновляем статус
            await self.db.execute(
                "UPDATE tickets SET status = $2 WHERE id = $1",
                ticket_id, new_status
            )
            
            # Записываем в историю
            await self._add_history(
                ticket_id,
                old_status,
                new_status,
                changed_by,
                changed_by_username,
                comment
            )
            
            logger.info(f"Заявка #{ticket_id}: {old_status} -> {new_status}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка обновления статуса: {e}")
            return False
    
    async def assign_to(self, ticket_id: int, assigned_to_user_id: int) -> bool:
        """Назначить заявку на пользователя"""
        try:
            await self.db.execute(
                "UPDATE tickets SET assigned_to = $2 WHERE id = $1",
                ticket_id, assigned_to_user_id
            )
            return True
        except Exception as e:
            logger.error(f"Ошибка назначения заявки: {e}")
            return False
    
    async def get_user_tickets(
        self,
        telegram_user_id: int,
        status: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Получить заявки пользователя"""
        if status:
            tickets = await self.db.fetch(
                """
                SELECT * FROM tickets 
                WHERE telegram_user_id = $1 AND status = $2
                ORDER BY created_at DESC
                LIMIT $3
                """,
                telegram_user_id, status, limit
            )
        else:
            tickets = await self.db.fetch(
                """
                SELECT * FROM tickets 
                WHERE telegram_user_id = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                telegram_user_id, limit
            )
        
        return [dict(t) for t in tickets]
    
    async def get_pending_by_type(
        self,
        ticket_type: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Получить ожидающие заявки по типу"""
        tickets = await self.db.fetch(
            """
            SELECT t.*, u.username, u.first_name, u.last_name
            FROM tickets t
            LEFT JOIN users u ON t.user_id = u.id
            WHERE t.type = $1 AND t.status IN ('pending', 'in_progress')
            ORDER BY 
                CASE t.priority 
                    WHEN 'urgent' THEN 1 
                    WHEN 'normal' THEN 2 
                    WHEN 'low' THEN 3 
                END,
                t.created_at ASC
            LIMIT $2
            """,
            ticket_type, limit
        )
        return [dict(t) for t in tickets]
    
    async def get_all_pending(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Получить все ожидающие заявки"""
        tickets = await self.db.fetch(
            """
            SELECT t.*, u.username, u.first_name, u.last_name
            FROM tickets t
            LEFT JOIN users u ON t.user_id = u.id
            WHERE t.status IN ('pending', 'in_progress')
            ORDER BY 
                CASE t.priority 
                    WHEN 'urgent' THEN 1 
                    WHEN 'normal' THEN 2 
                    WHEN 'low' THEN 3 
                END,
                t.created_at ASC
            LIMIT $1
            """,
            limit
        )
        return [dict(t) for t in tickets]
    
    async def get_history(self, ticket_id: int) -> List[Dict[str, Any]]:
        """Получить историю статусов заявки"""
        history = await self.db.fetch(
            """
            SELECT * FROM ticket_status_history
            WHERE ticket_id = $1
            ORDER BY changed_at ASC
            """,
            ticket_id
        )
        return [dict(h) for h in history]
    
    async def _add_history(
        self,
        ticket_id: int,
        old_status: Optional[str],
        new_status: str,
        changed_by: int,
        changed_by_username: Optional[str],
        comment: Optional[str]
    ) -> None:
        """Добавить запись в историю статусов"""
        await self.db.execute(
            """
            INSERT INTO ticket_status_history 
                (ticket_id, old_status, new_status, changed_by, changed_by_username, comment)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            ticket_id, old_status, new_status, changed_by, changed_by_username, comment
        )
    
    async def add_comment(
        self,
        ticket_id: int,
        comment: str,
        user_id: int,
        username: Optional[str] = None
    ) -> bool:
        """Добавить комментарий к заявке"""
        try:
            ticket = await self.get_by_id(ticket_id)
            if not ticket:
                return False
            
            await self._add_history(
                ticket_id,
                ticket["status"],
                ticket["status"],
                user_id,
                username,
                comment
            )
            
            logger.info(f"Добавлен комментарий к заявке #{ticket_id}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка добавления комментария: {e}")
            return False


async def get_ticket_model(db: Database) -> TicketModel:
    """Фабрика для получения модели заявок"""
    return TicketModel(db)
