"""
Модели данных АХО Бота
"""

from models.database import Database, get_db
from models.user import UserModel, get_user_model, ALL_ROLES, ROLE_TO_TICKET_TYPE
from models.ticket import TicketModel, get_ticket_model, TICKET_STATUSES, TICKET_TYPES, TICKET_PRIORITIES
from models.analytics import AnalyticsModel, get_analytics_model

__all__ = [
    "Database",
    "get_db",
    "UserModel",
    "get_user_model",
    "TicketModel",
    "get_ticket_model",
    "AnalyticsModel",
    "get_analytics_model",
    "ALL_ROLES",
    "ROLE_TO_TICKET_TYPE",
    "TICKET_STATUSES",
    "TICKET_TYPES",
    "TICKET_PRIORITIES",
]
