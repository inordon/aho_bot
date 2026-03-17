"""
Обработчики команд для пользователей
Создание заявок, просмотр статуса
"""

import os
import json
from datetime import datetime
from typing import Optional

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import ContextTypes, ConversationHandler

from models.database import Database
from models.user import UserModel
from models.ticket import TicketModel, TICKET_TYPES, TICKET_PRIORITIES, get_topic_id
from validators.input_validators import InputValidators
from utils.logger import get_logger
from utils.decorators import ensure_user_exists, rate_limit, log_action, handle_errors

logger = get_logger(__name__)

# Состояния ConversationHandler
(
    MAIN_MENU,
    PRIORITY_SELECT,
    PASS_FIO,
    PASS_DATE,
    PASS_PURPOSE,
    PASS_CONFIRM,
    PURCHASE_LINK,
    PURCHASE_QUANTITY,
    PURCHASE_REASON,
    PURCHASE_CONFIRM,
    PROBLEM_TYPE,
    PROBLEM_DESCRIPTION,
    PROBLEM_PHOTO,
    PROBLEM_CONFIRM,
    OTHER_DESCRIPTION,
    OTHER_CONFIRM,
) = range(16)

# Категории проблем
PROBLEM_CATEGORIES = [
    "Вентиляция",
    "Санузел",
    "Электрика",
    "Мебель",
    "Оборудование",
    "Другое",
]

# Конфигурация
AHO_GROUP_ID = int(os.getenv("AHO_GROUP_ID", "0"))


def create_main_menu() -> ReplyKeyboardMarkup:
    """Создает клавиатуру главного меню"""
    keyboard = [
        ["🪪 Заказать пропуск"],
        ["🛒 Заявка на закупку"],
        ["🔧 Что-то сломалось"],
        ["❓ Другое"],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def create_priority_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура выбора приоритета"""
    keyboard = [
        ["🔴 Срочно"],
        ["🟡 Обычно"],
        ["🟢 Планово"],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)


def create_confirm_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура подтверждения"""
    keyboard = [["✅ Да, отправить"], ["❌ Нет, отменить"]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)


def create_ticket_buttons(ticket_id: int) -> InlineKeyboardMarkup:
    """Создать кнопки для управления заявкой"""
    buttons = [
        [
            InlineKeyboardButton("▶️ В работу!", callback_data=f"take_{ticket_id}"),
            InlineKeyboardButton("✅ Готово!", callback_data=f"done_{ticket_id}"),
        ],
        [
            InlineKeyboardButton("❌ Отклоняю!", callback_data=f"reject_{ticket_id}"),
            InlineKeyboardButton("💬 Комментарий", callback_data=f"comment_{ticket_id}"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


@handle_errors
@ensure_user_exists
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Приветственное сообщение с главным меню"""
    context.user_data.clear()
    
    welcome_text = (
        "🏢 *Добро пожаловать в бот службы АХО\\!*\n\n"
        "Я ваш цифровой помощник для решения офисных задач\\. "
        "Через меня вы можете:\n\n"
        "• 🪪 _Заказать гостевой пропуск_\n"
        "• 🛒 _Оформить заявку на закупку_\n"
        "• 🔧 _Сообщить о поломке_\n"
        "• ❓ _Задать любой вопрос службе АХО_\n\n"
        "Выберите нужную опцию в меню ниже 👇\n\n"
        "_⏱ Среднее время обработки \\- 1 рабочий день_"
    )
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=create_main_menu(),
        parse_mode="MarkdownV2",
    )
    return MAIN_MENU


@handle_errors
async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора в главном меню"""
    choice = update.message.text
    
    if choice == "🪪 Заказать пропуск":
        context.user_data.clear()
        context.user_data["type"] = "pass"
        await update.message.reply_text(
            "📊 Выберите приоритет заявки:",
            reply_markup=create_priority_keyboard(),
        )
        return PRIORITY_SELECT
    
    elif choice == "🛒 Заявка на закупку":
        context.user_data.clear()
        context.user_data["type"] = "purchase"
        await update.message.reply_text(
            "📊 Выберите приоритет заявки:",
            reply_markup=create_priority_keyboard(),
        )
        return PRIORITY_SELECT
    
    elif choice == "🔧 Что-то сломалось":
        context.user_data.clear()
        context.user_data["type"] = "repair"
        await update.message.reply_text(
            "📊 Выберите приоритет заявки:",
            reply_markup=create_priority_keyboard(),
        )
        return PRIORITY_SELECT
    
    elif choice == "❓ Другое":
        context.user_data.clear()
        context.user_data["type"] = "other"
        await update.message.reply_text(
            "📊 Выберите приоритет заявки:",
            reply_markup=create_priority_keyboard(),
        )
        return PRIORITY_SELECT
    
    # Обработка выбора приоритета
    priority_result = InputValidators.validate_priority(choice)
    if priority_result.is_valid:
        context.user_data["priority"] = priority_result.value
        ticket_type = context.user_data.get("type")
        
        if ticket_type == "pass":
            await update.message.reply_text(
                "👤 Введите ФИО гостя (или несколько через запятую):\n"
                "Пример: Иванов Иван Иванович, Петрова Анна Сергеевна",
                reply_markup=ReplyKeyboardRemove(),
            )
            return PASS_FIO
        
        elif ticket_type == "purchase":
            await update.message.reply_text(
                "🛒 Введите ссылку на товар для закупки:\n"
                "Пример: https://www.example.com/product",
                reply_markup=ReplyKeyboardRemove(),
            )
            return PURCHASE_LINK
        
        elif ticket_type == "repair":
            keyboard = [[cat] for cat in PROBLEM_CATEGORIES]
            await update.message.reply_text(
                "🔧 Выберите категорию проблемы:",
                reply_markup=ReplyKeyboardMarkup(
                    keyboard, one_time_keyboard=True, resize_keyboard=True
                ),
            )
            return PROBLEM_TYPE
        
        elif ticket_type == "other":
            await update.message.reply_text(
                "📝 Опишите вашу просьбу или проблему (10-500 символов):",
                reply_markup=ReplyKeyboardRemove(),
            )
            return OTHER_DESCRIPTION
    
    await update.message.reply_text(
        "Пожалуйста, выберите опцию из меню.",
        reply_markup=create_main_menu(),
    )
    return MAIN_MENU


# ====== ПРОПУСКА ======

@handle_errors
async def process_pass_fio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка ФИО для пропуска"""
    result = InputValidators.validate_fio_list(update.message.text)
    
    if not result.is_valid:
        await update.message.reply_text(f"❌ {result.error_message}\n\nВведите ФИО еще раз:")
        return PASS_FIO
    
    context.user_data["fio_list"] = result.value
    await update.message.reply_text(
        "📅 Введите дату посещения в формате ДД.ММ.ГГГГ:\n"
        "Пример: 15.08.2025"
    )
    return PASS_DATE


@handle_errors
async def process_pass_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка даты для пропуска"""
    result = InputValidators.validate_future_date(update.message.text)
    
    if not result.is_valid:
        await update.message.reply_text(f"❌ {result.error_message}\n\nВведите дату еще раз:")
        return PASS_DATE
    
    context.user_data["date"] = result.value.strftime("%d.%m.%Y")
    await update.message.reply_text("🎯 Введите цель посещения (5-200 символов):")
    return PASS_PURPOSE


@handle_errors
async def process_pass_purpose(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка цели для пропуска"""
    result = InputValidators.validate_text(
        update.message.text, min_length=5, max_length=200, field_name="Цель"
    )
    
    if not result.is_valid:
        await update.message.reply_text(f"❌ {result.error_message}\n\nВведите цель еще раз:")
        return PASS_PURPOSE
    
    context.user_data["purpose"] = result.value
    
    priority_emoji = {"urgent": "🔴", "normal": "🟡", "low": "🟢"}
    priority = context.user_data.get("priority", "normal")
    
    confirmation_text = "✅ Проверьте данные заявки на пропуск:\n\n"
    for i, fio in enumerate(context.user_data["fio_list"], 1):
        confirmation_text += f"Гость #{i}: {fio}\n"
    
    confirmation_text += (
        f"\n📅 Дата: {context.user_data['date']}\n"
        f"🎯 Цель: {context.user_data['purpose']}\n"
        f"📊 Приоритет: {priority_emoji.get(priority, '🟡')} {TICKET_PRIORITIES.get(priority, 'Обычно')}\n\n"
        "Всё верно? Отправляем заявку?"
    )
    
    await update.message.reply_text(confirmation_text, reply_markup=create_confirm_keyboard())
    return PASS_CONFIRM


# ====== ЗАКУПКИ ======

@handle_errors
async def process_purchase_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка ссылки на товар"""
    result = InputValidators.validate_url(update.message.text)
    
    if not result.is_valid:
        await update.message.reply_text(f"❌ {result.error_message}\n\nВведите ссылку еще раз:")
        return PURCHASE_LINK
    
    context.user_data["link"] = result.value
    await update.message.reply_text(
        "🔢 Укажите количество:\n"
        "Пример: 5 шт, 1 комплект, 10 упаковок"
    )
    return PURCHASE_QUANTITY


@handle_errors
async def process_purchase_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка количества товара"""
    result = InputValidators.validate_quantity(update.message.text)
    
    if not result.is_valid:
        await update.message.reply_text(f"❌ {result.error_message}\n\nВведите количество еще раз:")
        return PURCHASE_QUANTITY
    
    context.user_data["quantity"] = result.value
    await update.message.reply_text("📝 Напишите обоснование закупки (5-500 символов):")
    return PURCHASE_REASON


@handle_errors
async def process_purchase_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка обоснования закупки"""
    result = InputValidators.validate_text(
        update.message.text, min_length=5, max_length=500, field_name="Обоснование"
    )
    
    if not result.is_valid:
        await update.message.reply_text(f"❌ {result.error_message}\n\nВведите обоснование еще раз:")
        return PURCHASE_REASON
    
    context.user_data["reason"] = result.value
    
    priority_emoji = {"urgent": "🔴", "normal": "🟡", "low": "🟢"}
    priority = context.user_data.get("priority", "normal")
    
    confirmation_text = (
        "✅ Проверьте данные заявки на закупку:\n\n"
        f"🔗 Ссылка: {context.user_data['link']}\n"
        f"🔢 Количество: {context.user_data['quantity']}\n"
        f"📝 Обоснование: {context.user_data['reason']}\n"
        f"📊 Приоритет: {priority_emoji.get(priority, '🟡')} {TICKET_PRIORITIES.get(priority, 'Обычно')}\n\n"
        "Всё верно? Отправляем заявку?"
    )
    
    await update.message.reply_text(confirmation_text, reply_markup=create_confirm_keyboard())
    return PURCHASE_CONFIRM


# ====== РЕМОНТЫ ======

@handle_errors
async def process_problem_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка типа проблемы"""
    problem_type = update.message.text
    
    if problem_type not in PROBLEM_CATEGORIES:
        keyboard = [[cat] for cat in PROBLEM_CATEGORIES]
        await update.message.reply_text(
            "❌ Выберите категорию из списка:",
            reply_markup=ReplyKeyboardMarkup(
                keyboard, one_time_keyboard=True, resize_keyboard=True
            ),
        )
        return PROBLEM_TYPE
    
    context.user_data["problem_type"] = problem_type
    await update.message.reply_text(
        "🔧 Опишите проблему подробно (10-1000 символов):\n"
        "Укажите кабинет, что сломалось, как проявляется",
        reply_markup=ReplyKeyboardRemove(),
    )
    return PROBLEM_DESCRIPTION


@handle_errors
async def process_problem_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка описания проблемы"""
    result = InputValidators.validate_text(
        update.message.text, min_length=10, max_length=1000, field_name="Описание"
    )
    
    if not result.is_valid:
        await update.message.reply_text(f"❌ {result.error_message}\n\nВведите описание еще раз:")
        return PROBLEM_DESCRIPTION
    
    context.user_data["description"] = result.value
    await update.message.reply_text(
        "📸 Прикрепите фото проблемы или отправьте /skip если фото нет:"
    )
    return PROBLEM_PHOTO


@handle_errors
async def process_problem_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка фото проблемы"""
    if update.message.photo:
        photo = update.message.photo[-1]
        context.user_data["photo_id"] = photo.file_id
    else:
        context.user_data["photo_id"] = None
    
    return await show_problem_confirmation(update, context)


@handle_errors
async def skip_problem_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Пропуск фото"""
    context.user_data["photo_id"] = None
    return await show_problem_confirmation(update, context)


async def show_problem_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать подтверждение заявки на ремонт"""
    priority_emoji = {"urgent": "🔴", "normal": "🟡", "low": "🟢"}
    priority = context.user_data.get("priority", "normal")
    
    confirmation_text = (
        "✅ Проверьте данные заявки на ремонт:\n\n"
        f"🔧 Категория: {context.user_data['problem_type']}\n"
        f"📝 Описание: {context.user_data['description']}\n"
        f"📸 Фото: {'приложено' if context.user_data.get('photo_id') else 'нет'}\n"
        f"📊 Приоритет: {priority_emoji.get(priority, '🟡')} {TICKET_PRIORITIES.get(priority, 'Обычно')}\n\n"
        "Всё верно? Отправляем заявку?"
    )
    
    await update.message.reply_text(confirmation_text, reply_markup=create_confirm_keyboard())
    return PROBLEM_CONFIRM


# ====== ДРУГОЕ ======

@handle_errors
async def process_other_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка описания для 'Другое'"""
    result = InputValidators.validate_text(
        update.message.text, min_length=10, max_length=500, field_name="Описание"
    )
    
    if not result.is_valid:
        await update.message.reply_text(f"❌ {result.error_message}\n\nВведите описание еще раз:")
        return OTHER_DESCRIPTION
    
    context.user_data["description"] = result.value
    
    priority_emoji = {"urgent": "🔴", "normal": "🟡", "low": "🟢"}
    priority = context.user_data.get("priority", "normal")
    
    confirmation_text = (
        "✅ Проверьте вашу заявку:\n\n"
        f"📝 Описание: {context.user_data['description']}\n"
        f"📊 Приоритет: {priority_emoji.get(priority, '🟡')} {TICKET_PRIORITIES.get(priority, 'Обычно')}\n\n"
        "Всё верно? Отправляем заявку?"
    )
    
    await update.message.reply_text(confirmation_text, reply_markup=create_confirm_keyboard())
    return OTHER_CONFIRM


# ====== ОТПРАВКА ЗАЯВКИ ======

@handle_errors
@rate_limit("ticket", limit=5, window=3600)
@log_action("create_ticket")
async def confirm_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Подтверждение и отправка заявки"""
    db: Database = context.bot_data.get("db")
    if not db:
        await update.message.reply_text("❌ Ошибка сервера. Попробуйте позже.")
        return MAIN_MENU
    
    ticket_model = TicketModel(db)
    user_model = UserModel(db)
    
    user = update.effective_user
    ticket_type = context.user_data.get("type")
    priority = context.user_data.get("priority", "normal")
    
    # Подготавливаем данные заявки
    ticket_data = dict(context.user_data)
    
    # Создаем заявку в БД
    ticket = await ticket_model.create(
        telegram_user_id=user.id,
        ticket_type=ticket_type,
        data=ticket_data,
        priority=priority,
    )
    
    if not ticket:
        await update.message.reply_text("❌ Ошибка создания заявки. Попробуйте позже.")
        return MAIN_MENU
    
    # Формируем текст для группы
    priority_emoji = {"urgent": "🔴", "normal": "🟡", "low": "🟢"}
    type_emoji = {"pass": "🪪", "purchase": "🛒", "repair": "🔧", "other": "❓"}
    type_name = {"pass": "ПРОПУСК", "purchase": "ЗАКУПКА", "repair": "РЕМОНТ", "other": "ДРУГОЕ"}
    
    request_text = (
        f"{type_emoji.get(ticket_type, '📋')} НОВАЯ ЗАЯВКА #{ticket['id']}: {type_name.get(ticket_type, 'ЗАЯВКА')}\n"
        f"{priority_emoji.get(priority, '🟡')} Приоритет: {TICKET_PRIORITIES.get(priority, 'Обычно')}\n\n"
    )
    
    if ticket_type == "pass":
        fio_list = context.user_data.get("fio_list", [])
        request_text += f"👤 Гости: {', '.join(fio_list)}\n"
        request_text += f"📅 Дата: {context.user_data.get('date')}\n"
        request_text += f"🎯 Цель: {context.user_data.get('purpose')}\n"
    
    elif ticket_type == "purchase":
        request_text += f"🔗 Ссылка: {context.user_data.get('link')}\n"
        request_text += f"🔢 Количество: {context.user_data.get('quantity')}\n"
        request_text += f"📝 Обоснование: {context.user_data.get('reason')}\n"
    
    elif ticket_type == "repair":
        request_text += f"🔧 Категория: {context.user_data.get('problem_type')}\n"
        request_text += f"📝 Описание: {context.user_data.get('description')}\n"
    
    else:
        request_text += f"📝 Описание: {context.user_data.get('description')}\n"
    
    username = f"@{user.username}" if user.username else f"ID: {user.id}"
    request_text += f"\n👤 От: {user.full_name} ({username})"
    
    # Отправляем в группу
    topic_id = get_topic_id(ticket_type)
    
    try:
        if ticket_type == "repair" and context.user_data.get("photo_id"):
            sent_message = await context.bot.send_photo(
                chat_id=AHO_GROUP_ID,
                photo=context.user_data["photo_id"],
                caption=request_text,
                message_thread_id=topic_id,
                reply_markup=create_ticket_buttons(ticket["id"]),
            )
        else:
            sent_message = await context.bot.send_message(
                chat_id=AHO_GROUP_ID,
                text=request_text,
                message_thread_id=topic_id,
                reply_markup=create_ticket_buttons(ticket["id"]),
            )
        
        # Обновляем message_id
        await ticket_model.update_message_id(ticket["id"], sent_message.message_id)
        
    except Exception as e:
        logger.error(f"Ошибка отправки в группу: {e}")
    
    # Уведомляем пользователя
    success_text = f"✅ Заявка #{ticket['id']} успешно создана!\n\n"
    
    if ticket_type == "pass":
        success_text += "Когда пропуск будет готов, мы вас уведомим."
    elif ticket_type == "purchase":
        success_text += "Мы рассмотрим заявку и сообщим о результате."
    elif ticket_type == "repair":
        success_text += "Специалисты уже работают над решением."
    else:
        success_text += "Ваша заявка принята в работу."
    
    await update.message.reply_text(success_text, reply_markup=create_main_menu())
    context.user_data.clear()
    
    return MAIN_MENU


@handle_errors
async def cancel_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена заявки"""
    context.user_data.clear()
    await update.message.reply_text("❌ Заявка отменена.", reply_markup=create_main_menu())
    return MAIN_MENU


@handle_errors
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Команда отмены"""
    context.user_data.clear()
    await update.message.reply_text(
        "Действие отменено. Выберите опцию в меню.",
        reply_markup=create_main_menu(),
    )
    return ConversationHandler.END


# ====== ПРОСМОТР СТАТУСА ======

@handle_errors
@ensure_user_exists
async def mystatus(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать мои заявки"""
    db: Database = context.bot_data.get("db")
    if not db:
        await update.message.reply_text("❌ Ошибка сервера.")
        return
    
    ticket_model = TicketModel(db)
    user_id = update.effective_user.id
    
    tickets = await ticket_model.get_user_tickets(user_id, limit=10)
    
    if not tickets:
        await update.message.reply_text(
            "📋 У вас пока нет заявок.\n"
            "Создайте заявку через главное меню.",
            reply_markup=create_main_menu(),
        )
        return
    
    status_emoji = {
        "pending": "⏳",
        "in_progress": "🔄",
        "completed": "✅",
        "rejected": "❌",
    }
    status_name = {
        "pending": "Ожидает",
        "in_progress": "В работе",
        "completed": "Выполнено",
        "rejected": "Отклонено",
    }
    type_emoji = {"pass": "🪪", "purchase": "🛒", "repair": "🔧", "other": "❓"}
    
    text = "📋 *Ваши последние заявки:*\n\n"
    
    for t in tickets:
        created = t["created_at"].strftime("%d.%m.%Y %H:%M") if t["created_at"] else "—"
        text += (
            f"{type_emoji.get(t['type'], '📋')} *#{t['id']}* \\- "
            f"{status_emoji.get(t['status'], '❓')} {status_name.get(t['status'], t['status'])}\n"
            f"   _Создана: {created}_\n\n"
        )
    
    await update.message.reply_text(
        text,
        parse_mode="MarkdownV2",
        reply_markup=create_main_menu(),
    )
