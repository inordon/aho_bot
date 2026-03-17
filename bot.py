#!/usr/bin/env python3
"""
АХО Бот - Production-ready Telegram бот для управления заявками АХО
Точка входа и координатор приложения
"""

import asyncio
import logging
import signal
import sys
from datetime import datetime

from dotenv import load_dotenv
from telegram import Update, BotCommand
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
)

# Загрузка конфигурации
load_dotenv("config.env")

# Импорт модулей приложения
from utils.logger import setup_logging, get_logger
from models.database import Database
from handlers.user_handlers import (
    start, main_menu, cancel,
    process_pass_fio, process_pass_date, process_pass_purpose,
    process_purchase_link, process_purchase_quantity, process_purchase_reason,
    process_problem_type, process_problem_description, process_problem_photo, skip_problem_photo,
    process_other_description,
    confirm_ticket, cancel_request,
    mystatus,
    MAIN_MENU, PASS_FIO, PASS_DATE, PASS_PURPOSE, PASS_CONFIRM,
    PURCHASE_LINK, PURCHASE_QUANTITY, PURCHASE_REASON, PURCHASE_CONFIRM,
    PROBLEM_TYPE, PROBLEM_DESCRIPTION, PROBLEM_PHOTO, PROBLEM_CONFIRM,
    OTHER_DESCRIPTION, OTHER_CONFIRM, PRIORITY_SELECT
)
from handlers.manager_handlers import (
    tickets_command, handle_ticket_callback, handle_comment_input,
    AWAITING_COMMENT
)
from handlers.admin_handlers import (
    add_manager, remove_manager, list_managers, stats, set_lead
)

import os

# Конфигурация
BOT_TOKEN = os.getenv("BOT_TOKEN")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Инициализация логирования
setup_logging(LOG_LEVEL)
logger = get_logger(__name__)


async def set_bot_commands(application):
    """Установка команд бота для меню"""
    commands = [
        BotCommand("start", "🏠 Главное меню"),
        BotCommand("new_ticket", "📝 Новая заявка"),
        BotCommand("mystatus", "📋 Мои заявки"),
        BotCommand("tickets", "📥 Заявки для обработки (менеджеры)"),
        BotCommand("stats", "📊 Статистика (админы)"),
        BotCommand("cancel", "❌ Отменить текущее действие"),
    ]
    await application.bot.set_my_commands(commands)


async def post_init(application):
    """Действия после инициализации бота"""
    logger.info("Инициализация бота...")
    
    # Инициализация базы данных
    db = Database()
    await db.init()
    application.bot_data["db"] = db
    
    # Установка команд
    await set_bot_commands(application)
    
    logger.info("Бот успешно инициализирован")


async def post_shutdown(application):
    """Действия при остановке бота"""
    logger.info("Остановка бота...")
    
    db = application.bot_data.get("db")
    if db:
        await db.close()
    
    logger.info("Бот остановлен")


def main():
    """Главная функция запуска бота"""
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не задан в config.env")
        sys.exit(1)
    
    logger.info("=" * 50)
    logger.info("Запуск АХО Бота")
    logger.info(f"Время запуска: {datetime.now().isoformat()}")
    logger.info("=" * 50)
    
    # Создание приложения
    application = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    
    # Основной ConversationHandler для пользователей
    user_conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("new_ticket", start),
        ],
        states={
            MAIN_MENU: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, main_menu)
            ],
            
            # Приоритет
            PRIORITY_SELECT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, main_menu)
            ],
            
            # Пропуска
            PASS_FIO: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_pass_fio)
            ],
            PASS_DATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_pass_date)
            ],
            PASS_PURPOSE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_pass_purpose)
            ],
            PASS_CONFIRM: [
                MessageHandler(filters.Regex(r'^✅ Да, отправить$'), confirm_ticket),
                MessageHandler(filters.Regex(r'^❌ Нет, отменить$'), cancel_request),
            ],
            
            # Закупки
            PURCHASE_LINK: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_purchase_link)
            ],
            PURCHASE_QUANTITY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_purchase_quantity)
            ],
            PURCHASE_REASON: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_purchase_reason)
            ],
            PURCHASE_CONFIRM: [
                MessageHandler(filters.Regex(r'^✅ Да, отправить$'), confirm_ticket),
                MessageHandler(filters.Regex(r'^❌ Нет, отменить$'), cancel_request),
            ],
            
            # Ремонты
            PROBLEM_TYPE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_problem_type)
            ],
            PROBLEM_DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_problem_description)
            ],
            PROBLEM_PHOTO: [
                MessageHandler(filters.PHOTO, process_problem_photo),
                CommandHandler("skip", skip_problem_photo),
                MessageHandler(filters.TEXT & ~filters.COMMAND, skip_problem_photo),
            ],
            PROBLEM_CONFIRM: [
                MessageHandler(filters.Regex(r'^✅ Да, отправить$'), confirm_ticket),
                MessageHandler(filters.Regex(r'^❌ Нет, отменить$'), cancel_request),
            ],
            
            # Другое
            OTHER_DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_other_description)
            ],
            OTHER_CONFIRM: [
                MessageHandler(filters.Regex(r'^✅ Да, отправить$'), confirm_ticket),
                MessageHandler(filters.Regex(r'^❌ Нет, отменить$'), cancel_request),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start),
        ],
        allow_reentry=True,
        name="user_conversation",
    )
    
    # ConversationHandler для комментариев менеджеров
    manager_comment_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(handle_ticket_callback, pattern=r"^(take|done|reject|comment)_\d+$")
        ],
        states={
            AWAITING_COMMENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_comment_input)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
        ],
        allow_reentry=True,
        name="manager_comment",
        per_message=False,
    )
    
    # Регистрация обработчиков
    application.add_handler(user_conv_handler)
    application.add_handler(manager_comment_handler)
    
    # Команды для пользователей
    application.add_handler(CommandHandler("mystatus", mystatus))
    
    # Команды для менеджеров
    application.add_handler(CommandHandler("tickets", tickets_command))
    
    # Команды для администраторов
    application.add_handler(CommandHandler("add_manager", add_manager))
    application.add_handler(CommandHandler("remove_manager", remove_manager))
    application.add_handler(CommandHandler("list_managers", list_managers))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("set_lead", set_lead))
    
    # Обработка callback-запросов для кнопок заявок
    application.add_handler(
        CallbackQueryHandler(handle_ticket_callback, pattern=r"^(take|done|reject|comment)_\d+$")
    )
    
    logger.info("Бот запущен и готов к работе")
    
    # Запуск polling
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
