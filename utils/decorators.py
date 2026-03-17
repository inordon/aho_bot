"""
Декораторы для обработчиков
Rate limiting, проверка ролей, логирование
"""

import os
import functools
from datetime import datetime, timedelta
from typing import List, Callable, Optional, Any

from telegram import Update
from telegram.ext import ContextTypes

from utils.logger import get_logger, get_action_logger

logger = get_logger(__name__)

# Конфигурация rate limiting
RATE_LIMIT_TICKETS = int(os.getenv("RATE_LIMIT_TICKETS", "5"))  # Заявок в час
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "3600"))  # Окно в секундах


def require_role(*required_roles: str):
    """
    Декоратор для проверки ролей пользователя
    
    Использование:
        @require_role("admin")
        @require_role("manager_pass", "lead", "admin")
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            from models.user import UserModel
            
            user_id = update.effective_user.id
            db = context.bot_data.get("db")
            
            if not db:
                logger.error("База данных не инициализирована")
                await update.effective_message.reply_text(
                    "❌ Ошибка сервера. Попробуйте позже."
                )
                return None
            
            user_model = UserModel(db)
            
            # Проверяем наличие хотя бы одной из требуемых ролей
            has_access = await user_model.has_any_role(user_id, list(required_roles))
            
            if not has_access:
                logger.warning(
                    f"Отказ в доступе для {user_id}. "
                    f"Требуются роли: {required_roles}"
                )
                await update.effective_message.reply_text(
                    "⛔ У вас нет прав для выполнения этой команды.\n"
                    "Обратитесь к администратору."
                )
                return None
            
            return await func(update, context, *args, **kwargs)
        
        return wrapper
    return decorator


def require_admin(func: Callable):
    """Декоратор для проверки прав администратора"""
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        from models.user import UserModel
        
        user_id = update.effective_user.id
        db = context.bot_data.get("db")
        
        if not db:
            await update.effective_message.reply_text("❌ Ошибка сервера.")
            return None
        
        user_model = UserModel(db)
        
        # Проверяем роль admin или переменную ADMIN_ID
        is_admin = await user_model.is_admin(user_id)
        
        if not is_admin:
            logger.warning(f"Попытка доступа к админ-команде от {user_id}")
            await update.effective_message.reply_text(
                "⛔ Эта команда доступна только администраторам."
            )
            return None
        
        return await func(update, context, *args, **kwargs)
    
    return wrapper


def rate_limit(action_type: str = "ticket", limit: int = None, window: int = None):
    """
    Декоратор для rate limiting
    
    Использование:
        @rate_limit("ticket", limit=5, window=3600)  # 5 заявок в час
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            user_id = update.effective_user.id
            db = context.bot_data.get("db")
            
            actual_limit = limit or RATE_LIMIT_TICKETS
            actual_window = window or RATE_LIMIT_WINDOW
            
            if not db:
                return await func(update, context, *args, **kwargs)
            
            try:
                # Проверяем текущий счетчик
                window_start = datetime.now() - timedelta(seconds=actual_window)
                
                record = await db.fetchrow(
                    """
                    SELECT action_count, window_start 
                    FROM rate_limits
                    WHERE telegram_user_id = $1 AND action_type = $2
                    """,
                    user_id, action_type
                )
                
                if record:
                    if record["window_start"] > window_start:
                        # Окно еще активно
                        if record["action_count"] >= actual_limit:
                            remaining = (record["window_start"] + timedelta(seconds=actual_window) - datetime.now())
                            minutes = int(remaining.total_seconds() / 60)
                            
                            logger.warning(f"Rate limit превышен для {user_id}: {action_type}")
                            await update.effective_message.reply_text(
                                f"⚠️ Превышен лимит запросов.\n"
                                f"Вы можете создать максимум {actual_limit} заявок в час.\n"
                                f"Попробуйте через {minutes} минут."
                            )
                            return None
                        
                        # Увеличиваем счетчик
                        await db.execute(
                            """
                            UPDATE rate_limits 
                            SET action_count = action_count + 1
                            WHERE telegram_user_id = $1 AND action_type = $2
                            """,
                            user_id, action_type
                        )
                    else:
                        # Окно истекло, сбрасываем
                        await db.execute(
                            """
                            UPDATE rate_limits 
                            SET action_count = 1, window_start = NOW()
                            WHERE telegram_user_id = $1 AND action_type = $2
                            """,
                            user_id, action_type
                        )
                else:
                    # Создаем новую запись
                    await db.execute(
                        """
                        INSERT INTO rate_limits (telegram_user_id, action_type, action_count, window_start)
                        VALUES ($1, $2, 1, NOW())
                        ON CONFLICT (telegram_user_id, action_type) 
                        DO UPDATE SET action_count = 1, window_start = NOW()
                        """,
                        user_id, action_type
                    )
                
            except Exception as e:
                logger.error(f"Ошибка rate limiting: {e}")
                # Продолжаем выполнение при ошибке
            
            return await func(update, context, *args, **kwargs)
        
        return wrapper
    return decorator


def log_action(action_name: str):
    """
    Декоратор для логирования действий
    
    Использование:
        @log_action("create_ticket")
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            user_id = update.effective_user.id
            username = update.effective_user.username
            db = context.bot_data.get("db")
            
            action_logger = get_action_logger(db)
            
            # Логируем начало действия
            await action_logger.log(
                user_id,
                f"{action_name}_started",
                {
                    "username": username,
                    "chat_id": update.effective_chat.id if update.effective_chat else None,
                }
            )
            
            try:
                result = await func(update, context, *args, **kwargs)
                
                # Логируем успешное завершение
                await action_logger.log(
                    user_id,
                    f"{action_name}_completed",
                    {"username": username}
                )
                
                return result
                
            except Exception as e:
                # Логируем ошибку
                await action_logger.log(
                    user_id,
                    f"{action_name}_error",
                    {
                        "username": username,
                        "error": str(e),
                    }
                )
                raise
        
        return wrapper
    return decorator


def ensure_user_exists(func: Callable):
    """Декоратор для создания/обновления пользователя в БД"""
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        from models.user import UserModel
        
        db = context.bot_data.get("db")
        if not db:
            return await func(update, context, *args, **kwargs)
        
        user = update.effective_user
        user_model = UserModel(db)
        
        # Создаем или обновляем пользователя
        await user_model.get_or_create(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
        )
        
        return await func(update, context, *args, **kwargs)
    
    return wrapper


def handle_errors(func: Callable):
    """Декоратор для обработки ошибок в хендлерах"""
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        try:
            return await func(update, context, *args, **kwargs)
        except Exception as e:
            logger.exception(f"Ошибка в обработчике {func.__name__}: {e}")
            
            if update.effective_message:
                await update.effective_message.reply_text(
                    "❌ Произошла ошибка. Попробуйте позже или обратитесь к администратору."
                )
            
            return None
    
    return wrapper
