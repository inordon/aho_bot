"""
Модуль логирования
JSON формат, ротация по дням
"""

import os
import sys
import json
import logging
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from typing import Optional, Dict, Any


class JSONFormatter(logging.Formatter):
    """Форматтер для JSON логов"""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Добавляем extra данные
        if hasattr(record, "user_id"):
            log_data["user_id"] = record.user_id
        if hasattr(record, "action"):
            log_data["action"] = record.action
        if hasattr(record, "details"):
            log_data["details"] = record.details
        if hasattr(record, "ticket_id"):
            log_data["ticket_id"] = record.ticket_id
        
        # Добавляем исключение если есть
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_data, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    """Форматтер для консольных логов с цветами"""
    
    COLORS = {
        "DEBUG": "\033[36m",     # Cyan
        "INFO": "\033[32m",      # Green
        "WARNING": "\033[33m",   # Yellow
        "ERROR": "\033[31m",     # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"
    
    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, self.RESET)
        
        # Базовый формат
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message = f"{color}[{timestamp}] [{record.levelname}] {record.name}: {record.getMessage()}{self.RESET}"
        
        # Добавляем исключение если есть
        if record.exc_info:
            message += f"\n{self.formatException(record.exc_info)}"
        
        return message


def setup_logging(level: str = "INFO") -> None:
    """Настройка системы логирования"""
    
    # Определяем уровень
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    # Создаем директорию для логов
    log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    # Корневой логгер
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Очищаем существующие обработчики
    root_logger.handlers = []
    
    # Консольный обработчик
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(ConsoleFormatter())
    root_logger.addHandler(console_handler)
    
    # Файловый обработчик с JSON и ротацией по дням
    log_file = os.path.join(log_dir, "aho_bot.json")
    file_handler = TimedRotatingFileHandler(
        filename=log_file,
        when="midnight",
        interval=1,
        backupCount=30,  # Хранить логи 30 дней
        encoding="utf-8",
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(JSONFormatter())
    file_handler.suffix = "%Y-%m-%d.json"
    root_logger.addHandler(file_handler)
    
    # Отключаем лишние логгеры
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    
    logging.info("Система логирования инициализирована")


def get_logger(name: str) -> logging.Logger:
    """Получить логгер по имени"""
    return logging.getLogger(name)


class ActionLogger:
    """Логгер для действий пользователей с сохранением в БД"""
    
    def __init__(self, db=None):
        self.db = db
        self.logger = get_logger("actions")
    
    async def log(
        self,
        user_id: Optional[int],
        action: str,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """Записать действие в лог и БД"""
        
        # Логируем в файл
        self.logger.info(
            f"Action: {action}",
            extra={
                "user_id": user_id,
                "action": action,
                "details": details or {},
            }
        )
        
        # Записываем в БД если доступна
        if self.db:
            try:
                await self.db.execute(
                    """
                    INSERT INTO operation_logs (telegram_user_id, action, details)
                    VALUES ($1, $2, $3)
                    """,
                    user_id,
                    action,
                    json.dumps(details or {}, ensure_ascii=False),
                )
            except Exception as e:
                self.logger.error(f"Ошибка записи в БД: {e}")
    
    async def log_ticket_action(
        self,
        user_id: int,
        ticket_id: int,
        action: str,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """Логировать действие с заявкой"""
        await self.log(
            user_id,
            action,
            {
                "ticket_id": ticket_id,
                **(details or {}),
            }
        )


def get_action_logger(db=None) -> ActionLogger:
    """Получить логгер действий"""
    return ActionLogger(db)
