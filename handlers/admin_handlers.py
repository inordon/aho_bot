"""
Обработчики команд для администраторов
Управление ролями, статистика
"""

from telegram import Update
from telegram.ext import ContextTypes

from models.database import Database
from models.user import UserModel, ALL_ROLES
from models.analytics import AnalyticsModel
from models.ticket import TICKET_TYPES, TICKET_STATUSES
from utils.logger import get_logger
from utils.decorators import require_admin, log_action, handle_errors

logger = get_logger(__name__)


@handle_errors
@require_admin
@log_action("add_manager")
async def add_manager(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Добавить менеджера с ролью: /add_manager <id> <role>"""
    db: Database = context.bot_data.get("db")
    if not db:
        await update.message.reply_text("❌ Ошибка сервера.")
        return
    
    user_model = UserModel(db)
    
    # Парсим аргументы
    args = context.args
    if len(args) < 2:
        roles_list = "\n".join([f"• `{r}`" for r in ALL_ROLES if r != "user"])
        await update.message.reply_text(
            "❌ Использование: `/add_manager <telegram_id> <role>`\n\n"
            f"Доступные роли:\n{roles_list}",
            parse_mode="Markdown"
        )
        return
    
    try:
        target_id = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ ID должен быть числом.")
        return
    
    role = args[1].lower()
    
    if role not in ALL_ROLES:
        roles_list = ", ".join([f"`{r}`" for r in ALL_ROLES if r != "user"])
        await update.message.reply_text(
            f"❌ Неизвестная роль: `{role}`\n\n"
            f"Доступные: {roles_list}",
            parse_mode="Markdown"
        )
        return
    
    # Проверяем/создаем пользователя
    user = await user_model.get_by_telegram_id(target_id)
    if not user:
        # Создаем пользователя без данных
        user = await user_model.get_or_create(telegram_id=target_id)
    
    # Добавляем роль
    admin_id = update.effective_user.id
    success = await user_model.add_role(target_id, role, assigned_by=admin_id)
    
    if success:
        await update.message.reply_text(
            f"✅ Роль `{role}` добавлена пользователю `{target_id}`",
            parse_mode="Markdown"
        )
        logger.info(f"Admin {admin_id} добавил роль {role} пользователю {target_id}")
    else:
        await update.message.reply_text(
            f"⚠️ Не удалось добавить роль. Возможно, она уже есть."
        )


@handle_errors
@require_admin
@log_action("remove_manager")
async def remove_manager(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Удалить роль у менеджера: /remove_manager <id> <role>"""
    db: Database = context.bot_data.get("db")
    if not db:
        await update.message.reply_text("❌ Ошибка сервера.")
        return
    
    user_model = UserModel(db)
    
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "❌ Использование: `/remove_manager <telegram_id> <role>`",
            parse_mode="Markdown"
        )
        return
    
    try:
        target_id = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ ID должен быть числом.")
        return
    
    role = args[1].lower()
    
    success = await user_model.remove_role(target_id, role)
    
    if success:
        await update.message.reply_text(
            f"✅ Роль `{role}` удалена у пользователя `{target_id}`",
            parse_mode="Markdown"
        )
        logger.info(f"Admin {update.effective_user.id} удалил роль {role} у {target_id}")
    else:
        await update.message.reply_text(
            f"⚠️ Не удалось удалить роль. Возможно, её нет у пользователя."
        )


@handle_errors
@require_admin
async def list_managers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Список всех менеджеров и их ролей"""
    db: Database = context.bot_data.get("db")
    if not db:
        await update.message.reply_text("❌ Ошибка сервера.")
        return
    
    user_model = UserModel(db)
    managers = await user_model.get_all_managers()
    
    if not managers:
        await update.message.reply_text(
            "📭 Менеджеры не назначены.\n"
            "Используйте `/add_manager <id> <role>` для добавления.",
            parse_mode="Markdown"
        )
        return
    
    text = "👥 *Список менеджеров:*\n\n"
    
    role_emoji = {
        "manager_pass": "🪪",
        "manager_purchase": "🛒",
        "manager_repair": "🔧",
        "manager_other": "❓",
        "lead": "👔",
        "admin": "👑",
    }
    
    for m in managers:
        name = m.get("first_name") or m.get("username") or str(m["telegram_id"])
        # Экранируем для MarkdownV2
        name = name.replace("_", "\\_").replace("*", "\\*").replace("[", "\\[").replace("]", "\\]")
        
        roles = m.get("roles", [])
        roles_str = " ".join([role_emoji.get(r, "•") for r in roles if r != "user"])
        
        text += f"• `{m['telegram_id']}` \\- {name}\n"
        text += f"  Роли: {roles_str or 'нет'}\n\n"
    
    await update.message.reply_text(text, parse_mode="MarkdownV2")


@handle_errors
@require_admin
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать полную статистику"""
    db: Database = context.bot_data.get("db")
    if not db:
        await update.message.reply_text("❌ Ошибка сервера.")
        return
    
    analytics = AnalyticsModel(db)
    report = await analytics.get_full_report()
    
    overall = report.get("overall", {})
    today = report.get("today", {})
    by_type = report.get("by_type", [])
    managers = report.get("managers", [])
    
    type_emoji = {"pass": "🪪", "purchase": "🛒", "repair": "🔧", "other": "❓"}
    type_name = {"pass": "Пропуска", "purchase": "Закупки", "repair": "Ремонты", "other": "Другое"}
    
    text = "📊 *СТАТИСТИКА АХО БОТА*\n\n"
    
    # Общая статистика
    text += "*📈 Общая статистика:*\n"
    text += f"  Всего заявок: {overall.get('total_tickets', 0)}\n"
    text += f"  ⏳ Ожидают: {overall.get('pending', 0)}\n"
    text += f"  🔄 В работе: {overall.get('in_progress', 0)}\n"
    text += f"  ✅ Выполнено: {overall.get('completed', 0)}\n"
    text += f"  ❌ Отклонено: {overall.get('rejected', 0)}\n\n"
    
    # По приоритетам
    text += "*📊 По приоритетам:*\n"
    text += f"  🔴 Срочные: {overall.get('urgent', 0)}\n"
    text += f"  🟡 Обычные: {overall.get('normal', 0)}\n"
    text += f"  🟢 Плановые: {overall.get('low_priority', 0)}\n\n"
    
    # За сегодня
    text += "*📅 Сегодня:*\n"
    text += f"  Создано: {today.get('created_today', 0)}\n"
    text += f"  Выполнено: {today.get('completed_today', 0)}\n"
    text += f"  В ожидании: {today.get('pending_today', 0)}\n\n"
    
    # По типам
    if by_type:
        text += "*📋 По типам заявок:*\n"
        for t in by_type:
            emoji = type_emoji.get(t["type"], "📋")
            name = type_name.get(t["type"], t["type"])
            text += f"  {emoji} {name}: {t['total']} "
            text += f"\\(✅{t['completed']} ⏳{t['pending']}\\)\n"
        text += "\n"
    
    # Активность менеджеров
    if managers:
        text += "*👥 Активность менеджеров:*\n"
        for m in managers[:5]:  # Топ 5
            username = m.get("username") or str(m.get("telegram_id", "?"))
            username = username.replace("_", "\\_")
            text += f"  @{username}: {m['tickets_processed']} заявок\n"
        text += "\n"
    
    # Среднее время обработки
    avg_time = report.get("avg_resolution_hours")
    if avg_time:
        text += f"*⏱ Среднее время обработки:* {avg_time:.1f} ч\n\n"
    
    # Количество пользователей
    text += f"*👤 Пользователей:* {report.get('user_count', 0)}\n"
    text += f"*👔 Менеджеров:* {report.get('manager_count', 0)}\n"
    
    await update.message.reply_text(text, parse_mode="MarkdownV2")


@handle_errors
@require_admin
@log_action("set_lead")
async def set_lead(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Назначить руководителя: /set_lead <id>"""
    db: Database = context.bot_data.get("db")
    if not db:
        await update.message.reply_text("❌ Ошибка сервера.")
        return
    
    user_model = UserModel(db)
    
    args = context.args
    if len(args) < 1:
        await update.message.reply_text(
            "❌ Использование: `/set_lead <telegram_id>`\n\n"
            "Руководитель получает доступ ко всем типам заявок.",
            parse_mode="Markdown"
        )
        return
    
    try:
        target_id = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ ID должен быть числом.")
        return
    
    # Создаем пользователя если нужно
    user = await user_model.get_by_telegram_id(target_id)
    if not user:
        user = await user_model.get_or_create(telegram_id=target_id)
    
    # Добавляем роль lead
    admin_id = update.effective_user.id
    success = await user_model.add_role(target_id, "lead", assigned_by=admin_id)
    
    if success:
        await update.message.reply_text(
            f"✅ Пользователь `{target_id}` назначен руководителем.\n"
            f"Теперь он имеет доступ ко всем типам заявок.",
            parse_mode="Markdown"
        )
        logger.info(f"Admin {admin_id} назначил руководителя {target_id}")
    else:
        await update.message.reply_text(
            f"⚠️ Не удалось назначить. Возможно, роль уже есть."
        )
