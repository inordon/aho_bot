"""
Обработчики команд для менеджеров
Просмотр и обработка заявок
"""

import os
from typing import Optional

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler

from models.database import Database
from models.user import UserModel
from models.ticket import TicketModel, TICKET_TYPES, TICKET_STATUSES, TICKET_PRIORITIES
from utils.logger import get_logger
from utils.decorators import require_role, log_action, handle_errors

logger = get_logger(__name__)

# Состояние для ввода комментария
AWAITING_COMMENT = 100

# Конфигурация
AHO_GROUP_ID = int(os.getenv("AHO_GROUP_ID", "0"))


def create_ticket_buttons(ticket_id: int, current_status: str = "pending") -> InlineKeyboardMarkup:
    """Создать кнопки для заявки"""
    buttons = []
    
    if current_status == "pending":
        buttons.append([
            InlineKeyboardButton("▶️ В работу!", callback_data=f"take_{ticket_id}"),
        ])
    
    if current_status in ("pending", "in_progress"):
        buttons.append([
            InlineKeyboardButton("✅ Готово!", callback_data=f"done_{ticket_id}"),
            InlineKeyboardButton("❌ Отклоняю!", callback_data=f"reject_{ticket_id}"),
        ])
    
    buttons.append([
        InlineKeyboardButton("💬 Комментарий", callback_data=f"comment_{ticket_id}"),
    ])
    
    return InlineKeyboardMarkup(buttons)


@handle_errors
@require_role("manager_pass", "manager_purchase", "manager_repair", "manager_other", "lead", "admin")
async def tickets_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать заявки для менеджера"""
    db: Database = context.bot_data.get("db")
    if not db:
        await update.message.reply_text("❌ Ошибка сервера.")
        return
    
    ticket_model = TicketModel(db)
    user_model = UserModel(db)
    
    user_id = update.effective_user.id
    roles = await user_model.get_user_roles(user_id)
    
    # Определяем какие типы заявок показывать
    tickets = []
    
    if "admin" in roles or "lead" in roles:
        # Показываем все заявки
        tickets = await ticket_model.get_all_pending(limit=50)
    else:
        # Показываем заявки по ролям
        for role in roles:
            if role.startswith("manager_"):
                ticket_type = role.replace("manager_", "")
                type_tickets = await ticket_model.get_pending_by_type(ticket_type, limit=20)
                tickets.extend(type_tickets)
    
    if not tickets:
        await update.message.reply_text(
            "📭 Нет активных заявок для обработки.\n"
            "Новые заявки появятся здесь автоматически."
        )
        return
    
    # Группируем по типам
    grouped = {}
    for t in tickets:
        if t["type"] not in grouped:
            grouped[t["type"]] = []
        grouped[t["type"]].append(t)
    
    status_emoji = {
        "pending": "⏳",
        "in_progress": "🔄",
    }
    priority_emoji = {"urgent": "🔴", "normal": "🟡", "low": "🟢"}
    type_emoji = {"pass": "🪪", "purchase": "🛒", "repair": "🔧", "other": "❓"}
    type_name = {"pass": "Пропуска", "purchase": "Закупки", "repair": "Ремонты", "other": "Другое"}
    
    text = "📋 *Активные заявки:*\n\n"
    
    for ticket_type, type_tickets in grouped.items():
        text += f"*{type_emoji.get(ticket_type, '📋')} {type_name.get(ticket_type, ticket_type)}:*\n"
        
        for t in type_tickets[:10]:  # Максимум 10 на тип
            priority = t.get("priority", "normal")
            status = t.get("status", "pending")
            created = t["created_at"].strftime("%d.%m %H:%M") if t["created_at"] else "—"
            
            # Экранируем специальные символы для MarkdownV2
            username = t.get("username", "")
            if username:
                username = username.replace("_", "\\_").replace("*", "\\*")
            
            text += (
                f"  {priority_emoji.get(priority, '🟡')} "
                f"*\\#{t['id']}* {status_emoji.get(status, '❓')} "
                f"\\({created}\\)\n"
            )
        
        if len(type_tickets) > 10:
            text += f"  _\\.\\.\\. и еще {len(type_tickets) - 10}_\n"
        
        text += "\n"
    
    text += "_Нажмите на кнопки в заявках в группе для обработки_"
    
    await update.message.reply_text(text, parse_mode="MarkdownV2")


@handle_errors
async def handle_ticket_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    """Обработка нажатий на кнопки заявок"""
    query = update.callback_query
    await query.answer()
    
    db: Database = context.bot_data.get("db")
    if not db:
        await query.answer("❌ Ошибка сервера", show_alert=True)
        return None
    
    ticket_model = TicketModel(db)
    user_model = UserModel(db)
    
    # Парсим callback_data
    data = query.data
    action, ticket_id_str = data.rsplit("_", 1)
    
    try:
        ticket_id = int(ticket_id_str)
    except ValueError:
        await query.answer("❌ Неверный ID заявки", show_alert=True)
        return None
    
    # Получаем заявку
    ticket = await ticket_model.get_by_id(ticket_id)
    if not ticket:
        await query.answer("❌ Заявка не найдена", show_alert=True)
        return None
    
    # Проверяем права
    user_id = update.effective_user.id
    can_manage = await user_model.can_manage_ticket(user_id, ticket["type"])
    
    if not can_manage:
        await query.answer("⛔ У вас нет прав на эту заявку", show_alert=True)
        return None
    
    user = update.effective_user
    username = user.username or user.full_name
    
    if action == "take":
        # Взять в работу
        success = await ticket_model.update_status(
            ticket_id,
            "in_progress",
            user_id,
            username,
            "Взято в работу"
        )
        
        if success:
            # Уведомляем автора заявки
            try:
                await context.bot.send_message(
                    chat_id=ticket["telegram_user_id"],
                    text=f"🔄 Ваша заявка #{ticket_id} взята в работу!"
                )
            except Exception as e:
                logger.warning(f"Не удалось уведомить пользователя: {e}")
            
            # Обновляем кнопки
            await query.edit_message_reply_markup(
                reply_markup=create_ticket_buttons(ticket_id, "in_progress")
            )
            await query.answer("✅ Заявка взята в работу!")
        else:
            await query.answer("❌ Ошибка обновления статуса", show_alert=True)
    
    elif action == "done":
        # Завершить
        success = await ticket_model.update_status(
            ticket_id,
            "completed",
            user_id,
            username,
            "Заявка выполнена"
        )
        
        if success:
            # Уведомляем автора
            try:
                await context.bot.send_message(
                    chat_id=ticket["telegram_user_id"],
                    text=f"✅ Ваша заявка #{ticket_id} выполнена!"
                )
            except Exception as e:
                logger.warning(f"Не удалось уведомить пользователя: {e}")
            
            # Удаляем кнопки
            await query.edit_message_reply_markup(reply_markup=None)
            
            # Добавляем отметку о выполнении
            try:
                current_text = query.message.text or query.message.caption or ""
                new_text = current_text + f"\n\n✅ *Выполнено* \\(@{username}\\)"
                
                if query.message.text:
                    await query.edit_message_text(new_text, parse_mode="MarkdownV2")
                else:
                    await query.edit_message_caption(new_text, parse_mode="MarkdownV2")
            except Exception:
                pass
            
            await query.answer("✅ Заявка выполнена!")
        else:
            await query.answer("❌ Ошибка обновления статуса", show_alert=True)
    
    elif action == "reject":
        # Отклонить
        success = await ticket_model.update_status(
            ticket_id,
            "rejected",
            user_id,
            username,
            "Заявка отклонена"
        )
        
        if success:
            # Уведомляем автора
            try:
                await context.bot.send_message(
                    chat_id=ticket["telegram_user_id"],
                    text=f"❌ Ваша заявка #{ticket_id} отклонена.\n"
                         f"Свяжитесь со службой АХО для уточнения."
                )
            except Exception as e:
                logger.warning(f"Не удалось уведомить пользователя: {e}")
            
            await query.edit_message_reply_markup(reply_markup=None)
            
            try:
                current_text = query.message.text or query.message.caption or ""
                new_text = current_text + f"\n\n❌ *Отклонено* \\(@{username}\\)"
                
                if query.message.text:
                    await query.edit_message_text(new_text, parse_mode="MarkdownV2")
                else:
                    await query.edit_message_caption(new_text, parse_mode="MarkdownV2")
            except Exception:
                pass
            
            await query.answer("❌ Заявка отклонена!")
        else:
            await query.answer("❌ Ошибка обновления статуса", show_alert=True)
    
    elif action == "comment":
        # Запрашиваем комментарий
        context.user_data["comment_ticket_id"] = ticket_id
        context.user_data["comment_message"] = query.message
        
        await query.answer()
        await context.bot.send_message(
            chat_id=user_id,
            text=f"💬 Введите комментарий к заявке #{ticket_id}:\n"
                 f"(или /cancel для отмены)"
        )
        
        return AWAITING_COMMENT
    
    return None


@handle_errors
async def handle_comment_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка ввода комментария"""
    db: Database = context.bot_data.get("db")
    if not db:
        await update.message.reply_text("❌ Ошибка сервера.")
        return ConversationHandler.END
    
    ticket_model = TicketModel(db)
    
    ticket_id = context.user_data.get("comment_ticket_id")
    comment = update.message.text.strip()
    
    if not ticket_id:
        await update.message.reply_text("❌ Заявка не найдена.")
        return ConversationHandler.END
    
    if len(comment) < 2:
        await update.message.reply_text("❌ Комментарий слишком короткий.")
        return AWAITING_COMMENT
    
    if len(comment) > 500:
        await update.message.reply_text("❌ Комментарий слишком длинный (макс. 500 символов).")
        return AWAITING_COMMENT
    
    user = update.effective_user
    username = user.username or user.full_name
    
    # Сохраняем комментарий
    success = await ticket_model.add_comment(
        ticket_id,
        comment,
        user.id,
        username
    )
    
    if success:
        # Получаем заявку для уведомления автора
        ticket = await ticket_model.get_by_id(ticket_id)
        
        if ticket:
            try:
                await context.bot.send_message(
                    chat_id=ticket["telegram_user_id"],
                    text=f"💬 Комментарий к заявке #{ticket_id}:\n\n{comment}\n\n— {username}"
                )
            except Exception as e:
                logger.warning(f"Не удалось уведомить пользователя: {e}")
        
        await update.message.reply_text(f"✅ Комментарий добавлен к заявке #{ticket_id}!")
    else:
        await update.message.reply_text("❌ Ошибка добавления комментария.")
    
    # Очищаем данные
    context.user_data.pop("comment_ticket_id", None)
    context.user_data.pop("comment_message", None)
    
    return ConversationHandler.END
