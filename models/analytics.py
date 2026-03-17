"""
Модуль аналитики и статистики
Метрики, отчеты, дашборды
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from models.database import Database
from utils.logger import get_logger

logger = get_logger(__name__)


class AnalyticsModel:
    """Модель для аналитики и статистики"""
    
    def __init__(self, db: Database):
        self.db = db
    
    async def get_overall_stats(self) -> Dict[str, Any]:
        """Получить общую статистику"""
        stats = await self.db.fetchrow(
            """
            SELECT
                COUNT(*) as total_tickets,
                COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending,
                COUNT(CASE WHEN status = 'in_progress' THEN 1 END) as in_progress,
                COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed,
                COUNT(CASE WHEN status = 'rejected' THEN 1 END) as rejected,
                COUNT(CASE WHEN priority = 'urgent' THEN 1 END) as urgent,
                COUNT(CASE WHEN priority = 'normal' THEN 1 END) as normal,
                COUNT(CASE WHEN priority = 'low' THEN 1 END) as low_priority
            FROM tickets
            """
        )
        return dict(stats) if stats else {}
    
    async def get_stats_by_type(self) -> List[Dict[str, Any]]:
        """Получить статистику по типам заявок"""
        stats = await self.db.fetch(
            """
            SELECT
                type,
                COUNT(*) as total,
                COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending,
                COUNT(CASE WHEN status = 'in_progress' THEN 1 END) as in_progress,
                COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed,
                COUNT(CASE WHEN status = 'rejected' THEN 1 END) as rejected
            FROM tickets
            GROUP BY type
            ORDER BY total DESC
            """
        )
        return [dict(s) for s in stats]
    
    async def get_stats_by_period(
        self,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """Получить статистику за период"""
        since = datetime.now() - timedelta(days=days)
        
        stats = await self.db.fetch(
            """
            SELECT
                DATE(created_at) as date,
                COUNT(*) as created,
                COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed
            FROM tickets
            WHERE created_at >= $1
            GROUP BY DATE(created_at)
            ORDER BY date DESC
            """,
            since
        )
        return [dict(s) for s in stats]
    
    async def get_today_stats(self) -> Dict[str, Any]:
        """Получить статистику за сегодня"""
        today = datetime.now().date()
        
        stats = await self.db.fetchrow(
            """
            SELECT
                COUNT(*) as created_today,
                COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_today,
                COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending_today
            FROM tickets
            WHERE DATE(created_at) = $1
            """,
            today
        )
        return dict(stats) if stats else {}
    
    async def get_manager_stats(self) -> List[Dict[str, Any]]:
        """Получить статистику по менеджерам"""
        stats = await self.db.fetch(
            """
            SELECT
                h.changed_by as telegram_id,
                h.changed_by_username as username,
                COUNT(DISTINCT h.ticket_id) as tickets_processed,
                COUNT(CASE WHEN h.new_status = 'completed' THEN 1 END) as completed,
                COUNT(CASE WHEN h.new_status = 'rejected' THEN 1 END) as rejected
            FROM ticket_status_history h
            WHERE h.changed_by IS NOT NULL
                AND h.new_status IN ('in_progress', 'completed', 'rejected')
            GROUP BY h.changed_by, h.changed_by_username
            ORDER BY tickets_processed DESC
            """
        )
        return [dict(s) for s in stats]
    
    async def get_avg_resolution_time(self) -> Optional[float]:
        """Получить среднее время обработки заявки (в часах)"""
        result = await self.db.fetchval(
            """
            SELECT AVG(
                EXTRACT(EPOCH FROM (
                    SELECT MIN(changed_at) 
                    FROM ticket_status_history h2 
                    WHERE h2.ticket_id = t.id 
                    AND h2.new_status = 'completed'
                ) - t.created_at) / 3600
            )
            FROM tickets t
            WHERE t.status = 'completed'
            """
        )
        return float(result) if result else None
    
    async def get_user_count(self) -> int:
        """Получить количество пользователей"""
        count = await self.db.fetchval("SELECT COUNT(*) FROM users")
        return count or 0
    
    async def get_active_managers_count(self) -> int:
        """Получить количество активных менеджеров"""
        count = await self.db.fetchval(
            """
            SELECT COUNT(DISTINCT u.id)
            FROM users u
            JOIN user_roles ur ON u.id = ur.user_id
            JOIN roles r ON r.id = ur.role_id
            WHERE r.name LIKE 'manager_%' OR r.name IN ('lead', 'admin')
            AND u.is_active = TRUE
            """
        )
        return count or 0
    
    async def get_top_requesters(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Получить топ пользователей по количеству заявок"""
        users = await self.db.fetch(
            """
            SELECT
                u.telegram_id,
                u.username,
                u.first_name,
                COUNT(t.id) as ticket_count
            FROM users u
            LEFT JOIN tickets t ON u.id = t.user_id
            GROUP BY u.id, u.telegram_id, u.username, u.first_name
            ORDER BY ticket_count DESC
            LIMIT $1
            """,
            limit
        )
        return [dict(u) for u in users]
    
    async def get_full_report(self) -> Dict[str, Any]:
        """Получить полный отчет"""
        overall = await self.get_overall_stats()
        by_type = await self.get_stats_by_type()
        today = await self.get_today_stats()
        managers = await self.get_manager_stats()
        avg_time = await self.get_avg_resolution_time()
        user_count = await self.get_user_count()
        manager_count = await self.get_active_managers_count()
        
        return {
            "overall": overall,
            "by_type": by_type,
            "today": today,
            "managers": managers,
            "avg_resolution_hours": avg_time,
            "user_count": user_count,
            "manager_count": manager_count,
            "generated_at": datetime.now().isoformat(),
        }


async def get_analytics_model(db: Database) -> AnalyticsModel:
    """Фабрика для получения модели аналитики"""
    return AnalyticsModel(db)
