import os
import logging
import re
from datetime import datetime
from dotenv import load_dotenv
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove
)
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    CallbackContext
)

# Загрузка конфигурации
load_dotenv("config.env")
BOT_TOKEN = os.getenv("BOT_TOKEN")
AHO_GROUP_ID = int(os.getenv("AHO_GROUP_ID"))  # ID основной группы

# ID тем в группе
PASS_TOPIC_ID = int(os.getenv("PASS_TOPIC_ID"))
PURCHASE_TOPIC_ID = int(os.getenv("PURCHASE_TOPIC_ID"))
REPAIR_TOPIC_ID = int(os.getenv("REPAIR_TOPIC_ID"))
OTHER_TOPIC_ID = int(os.getenv("OTHER_TOPIC_ID"))

# Ролевая модель
MANAGER_IDS = [int(x) for x in os.getenv("MANAGER_IDS", "").split(",") if x.strip()]
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))  # ID администратора бота

# Настройка логгирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния диалога для разных заявок
MAIN_MENU, = range(1)
PASS_FIO, PASS_DATE, PASS_PURPOSE, PASS_CONFIRM = range(10, 14)
PURCHASE_LINK, PURCHASE_QUANTITY, PURCHASE_REASON, PURCHASE_CONFIRM = range(20, 24)
PROBLEM_TYPE, PROBLEM_DESCRIPTION, PROBLEM_PHOTO, PROBLEM_CONFIRM = range(30, 34)
OTHER_DESCRIPTION, OTHER_CONFIRM = range(40, 42)

# База данных для хранения заявок
ticket_db = {}

# Категории для "Что-то сломалось"
PROBLEM_CATEGORIES = [
    "Вентиляция",
    "Санузел",
    "Электрика",
    "Мебель",
    "Оборудование",
    "Другое"
]

def create_main_menu():
    """Создает клавиатуру главного меню"""
    keyboard = [
        ["🪪 Заказать пропуск"],
        ["🛒 Заявка на закупку"],
        ["🔧 Что-то сломалось"],
        ["❓ Другое"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветственное сообщение с главным меню"""
    welcome_text = (
        "🏢 *Добро пожаловать в бот службы АХО\!*\n\n"
        "Я ваш цифровой помощник для решения офисных задач\. "
        "Через меня вы можете:\n\n"
        "• 🪪 _Заказать гостевой пропуск_\n"
        "• 🛒 _Оформить заявку на закупку канцтоваров или оборудования_\n"
        "• 🔧 _Сообщить о поломке или необходимости ремонта_\n"
        "• ❓ _Задать любой вопрос службе АХО_\n\n"
        "Выберите нужную опцию в меню ниже 👇\n\n"
        "_⏱ Среднее время обработки заявки \- 1 рабочий день_\n"
        "_💡 Чтобы начать новую заявку в любой момент, просто нажмите кнопку внизу экрана_"
    )
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=create_main_menu(),
        parse_mode="MarkdownV2"
    )
    return MAIN_MENU

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора в главном меню"""
    choice = update.message.text
    
    if choice == "🪪 Заказать пропуск":
        context.user_data.clear()
        context.user_data["type"] = "pass"
        await update.message.reply_text(
            "👤 Введите ФИО гостя (или несколько через запятую):\n"
            "Пример: Иванов Иван Иванович, Петрова Анна Сергеевна",
            reply_markup=ReplyKeyboardRemove()
        )
        return PASS_FIO
    
    elif choice == "🛒 Заявка на закупку":
        context.user_data.clear()
        context.user_data["type"] = "purchase"
        await update.message.reply_text(
            "🛒 Введите ссылку на товар для закупки:\n"
            "Пример: https://www.канцелярия.ru/товар123",
            reply_markup=ReplyKeyboardRemove()
        )
        return PURCHASE_LINK
    
    elif choice == "🔧 Что-то сломалось":
        context.user_data.clear()
        context.user_data["type"] = "repair"
        # Создаем клавиатуру с категориями
        keyboard = [[cat] for cat in PROBLEM_CATEGORIES]
        await update.message.reply_text(
            "🔧 Выберите категорию проблемы:",
            reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        )
        return PROBLEM_TYPE
    
    elif choice == "❓ Другое":
        context.user_data.clear()
        context.user_data["type"] = "other"
        await update.message.reply_text(
            "📝 Опишите вашу просьбу или проблему:\n"
            "Укажите все необходимые детали (10-500 символов)",
            reply_markup=ReplyKeyboardRemove()
        )
        return OTHER_DESCRIPTION
    
    await update.message.reply_text("Пожалуйста, выберите опцию из меню.")
    return MAIN_MENU

# ====== БЛОК: ЗАКАЗ ПРОПУСКА ======
async def process_pass_fio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ФИО для пропуска"""
    fio_list = [fio.strip() for fio in update.message.text.split(",") if fio.strip()]
    
    if not fio_list:
        await update.message.reply_text("❌ ФИО не может быть пустым. Введи еще раз:")
        return PASS_FIO
    
    invalid_fios = []
    for fio in fio_list:
        if not re.match(r"^[а-яА-ЯёЁ\s-]{5,50}$", fio):
            invalid_fios.append(fio)
    
    if invalid_fios:
        await update.message.reply_text(
            f"❌ Ошибка в ФИО: {', '.join(invalid_fios)}\n"
            "✅ Используй только русские буквы, пробелы и дефисы (5-50 символов)\n"
            "Попробуй еще раз:"
        )
        return PASS_FIO
    
    context.user_data["fio_list"] = fio_list
    await update.message.reply_text(
        "📅 Введите дату посещения в формате ДД.ММ.ГГГГ:\n"
        "Пример: 15.08.2023"
    )
    return PASS_DATE

async def process_pass_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка даты для пропуска"""
    date_str = update.message.text.strip()
    
    try:
        visit_date = datetime.strptime(date_str, "%d.%m.%Y").date()
    except:
        await update.message.reply_text("❌ Неправильный формат даты. Используй ДД.ММ.ГГГГ:")
        return PASS_DATE
    
    if visit_date < datetime.now().date():
        await update.message.reply_text("❌ Дата не может быть прошлой. Введи будущую дату:")
        return PASS_DATE
    
    context.user_data["date"] = visit_date.strftime("%d.%m.%Y")
    await update.message.reply_text("🎯 Введите цель посещения (5-200 символов):")
    return PASS_PURPOSE

async def process_pass_purpose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка цели для пропуска"""
    purpose = update.message.text.strip()
    
    if len(purpose) < 5 or len(purpose) > 200:
        await update.message.reply_text("❌ Слишком коротко или длинно. Введи 5-200 символов:")
        return PASS_PURPOSE
    
    context.user_data["purpose"] = purpose
    
    # Формируем текст подтверждения
    confirmation_text = "✅ Проверьте данные заявки на пропуск:\n\n"
    for i, fio in enumerate(context.user_data["fio_list"], 1):
        confirmation_text += f"Гость #{i}: {fio}\n"
    
    confirmation_text += (
        f"\n📅 Дата: {context.user_data['date']}\n"
        f"🎯 Цель: {context.user_data['purpose']}\n\n"
        "Все верно? Отправляем заявку?"
    )
    
    # Создаем кнопки
    keyboard = [["✅ Да, отправить"], ["❌ Нет, отменить"]]
    await update.message.reply_text(
        confirmation_text,
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return PASS_CONFIRM

# ====== БЛОК: ЗАЯВКА НА ЗАКУПКУ ======
async def process_purchase_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ссылки на товар"""
    link = update.message.text.strip()
    
    # Простая валидация URL
    if not re.match(r"^https?://\S+", link):
        await update.message.reply_text(
            "❌ Неверный формат ссылки. Введите корректный URL:\n"
            "Пример: https://www.example.com/product123"
        )
        return PURCHASE_LINK
    
    context.user_data["link"] = link
    await update.message.reply_text(
        "🔢 Укажите количество:\n"
        "Пример: 5 шт, 1 комплект, 10 упаковок"
    )
    return PURCHASE_QUANTITY

async def process_purchase_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка количества товара"""
    quantity = update.message.text.strip()
    
    if len(quantity) < 1 or len(quantity) > 50:
        await update.message.reply_text("❌ Некорректное количество. Введите снова:")
        return PURCHASE_QUANTITY
    
    context.user_data["quantity"] = quantity
    await update.message.reply_text(
        "📝 Напишите обоснование закупки:\n"
        "Зачем нужен этот товар? (5-500 символов)"
    )
    return PURCHASE_REASON

async def process_purchase_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка обоснования закупки"""
    reason = update.message.text.strip()
    
    if len(reason) < 5 or len(reason) > 500:
        await update.message.reply_text("❌ Слишком короткое или длинное обоснование. Введите 5-500 символов:")
        return PURCHASE_REASON
    
    context.user_data["reason"] = reason
    
    # Формируем текст подтверждения
    confirmation_text = (
        "✅ Проверьте данные заявки на закупку:\n\n"
        f"🔗 Ссылка: {context.user_data['link']}\n"
        f"🔢 Количество: {context.user_data['quantity']}\n"
        f"📝 Обоснование: {reason}\n\n"
        "Все верно? Отправляем заявку?"
    )
    
    # Создаем кнопки
    keyboard = [["✅ Да, отправить"], ["❌ Нет, отменить"]]
    await update.message.reply_text(
        confirmation_text,
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return PURCHASE_CONFIRM

# ====== БЛОК: ЧТО-ТО СЛОМАЛОСЬ ======
async def process_problem_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка типа проблемы"""
    problem_type = update.message.text
    context.user_data["problem_type"] = problem_type
    await update.message.reply_text(
        "🔧 Опишите проблему подробно:\n"
        "Укажите кабинет, что именно сломалось, как проявляется проблема (10-1000 символов)",
        reply_markup=ReplyKeyboardRemove()
    )
    return PROBLEM_DESCRIPTION

async def process_problem_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка описания проблемы"""
    description = update.message.text.strip()
    
    if len(description) < 10 or len(description) > 1000:
        await update.message.reply_text("❌ Описание слишком короткое или длинное. Введите 10-1000 символов:")
        return PROBLEM_DESCRIPTION
    
    context.user_data["description"] = description
    await update.message.reply_text(
        "📸 При желании прикрепите фото проблемы (или нажмите /skip если фото не нужно):"
    )
    return PROBLEM_PHOTO

async def process_problem_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка фото проблемы"""
    if update.message.photo:
        # Сохраняем самое большое фото
        photo = update.message.photo[-1]
        context.user_data["photo_id"] = photo.file_id
    else:
        context.user_data["photo_id"] = None
    
    # Формируем текст подтверждения
    confirmation_text = (
        "✅ Проверьте данные заявки на ремонт:\n\n"
        f"🔧 Тип проблемы: {context.user_data['problem_type']}\n"
        f"📝 Описание: {context.user_data['description']}\n"
        f"📸 Фото: {'приложено' if context.user_data.get('photo_id') else 'нет'}\n\n"
        "Все верно? Отправляем заявку?"
    )
    
    # Создаем кнопки
    keyboard = [["✅ Да, отправить"], ["❌ Нет, отменить"]]
    await update.message.reply_text(
        confirmation_text,
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return PROBLEM_CONFIRM

async def skip_problem_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пропуск добавления фото"""
    context.user_data["photo_id"] = None
    return await process_problem_photo(update, context)

# ====== БЛОК: ДРУГОЕ ======
async def process_other_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка описания для 'Другое'"""
    description = update.message.text.strip()
    
    if len(description) < 10 or len(description) > 500:
        await update.message.reply_text("❌ Описание слишком короткое или длинное. Введите 10-500 символов:")
        return OTHER_DESCRIPTION
    
    context.user_data["description"] = description
    
    # Формируем текст подтверждения
    confirmation_text = (
        "✅ Проверьте вашу заявку:\n\n"
        f"📝 Описание: {description}\n\n"
        "Все верно? Отправляем заявку?"
    )
    
    # Создаем кнопки
    keyboard = [["✅ Да, отправить"], ["❌ Нет, отменить"]]
    await update.message.reply_text(
        confirmation_text,
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return OTHER_CONFIRM

# ====== ОБЩИЕ ФУНКЦИИ ДЛЯ ВСЕХ ЗАЯВОК ======
async def send_ticket_to_topic(update: Update, context: ContextTypes.DEFAULT_TYPE, ticket_type: str):
    """Отправляет заявку в соответствующую тему группы"""
    user_id = update.effective_user.id
    username = update.effective_user.username or "Без username"
    full_name = update.effective_user.full_name
    
    # Выбираем тему для заявки
    topic_ids = {
        "pass": PASS_TOPIC_ID,
        "purchase": PURCHASE_TOPIC_ID,
        "repair": REPAIR_TOPIC_ID,
        "other": OTHER_TOPIC_ID
    }
    topic_id = topic_ids.get(ticket_type, None)
    
    if not topic_id:
        logger.error(f"Неизвестный тип заявки: {ticket_type}")
        return None
    
    # Формируем текст заявки
    if ticket_type == "pass":
        request_text = (
            "🚀 НОВАЯ ЗАЯВКА: ПРОПУСК\n\n"
            f"👤 Гости: {', '.join(context.user_data['fio_list'])}\n"
            f"📅 Дата: {context.user_data['date']}\n"
            f"🎯 Цель: {context.user_data['purpose']}\n\n"
            f"👤 От: {full_name} (@{username})"
        )
    elif ticket_type == "purchase":
        request_text = (
            "🛒 НОВАЯ ЗАЯВКА: ЗАКУПКА\n\n"
            f"🔗 Ссылка: {context.user_data['link']}\n"
            f"🔢 Количество: {context.user_data['quantity']}\n"
            f"📝 Обоснование: {context.user_data['reason']}\n\n"
            f"👤 От: {full_name} (@{username})"
        )
    elif ticket_type == "repair":
        request_text = (
            "🔧 НОВАЯ ЗАЯВКА: РЕМОНТ\n\n"
            f"🔧 Тип проблемы: {context.user_data['problem_type']}\n"
            f"📝 Описание: {context.user_data['description']}\n\n"
            f"👤 От: {full_name} (@{username})"
        )
    else:  # other
        request_text = (
            "❓ НОВАЯ ЗАЯВКА: ДРУГОЕ\n\n"
            f"📝 Описание: {context.user_data['description']}\n\n"
            f"👤 От: {full_name} (@{username})"
        )
    
    # Добавляем инструкцию
    request_text += (
        "\n\n--------------------------------\n"
        "✅ Чтобы отметить как выполненное, напишите 'Готово'"
    )
    
    try:
        # Отправляем сообщение в тему
        if ticket_type == "repair" and context.user_data.get("photo_id"):
            # Отправляем с фото
            sent_message = await context.bot.send_photo(
                chat_id=AHO_GROUP_ID,
                photo=context.user_data["photo_id"],
                caption=request_text,
                message_thread_id=topic_id
            )
        else:
            # Отправляем текстовое сообщение
            sent_message = await context.bot.send_message(
                chat_id=AHO_GROUP_ID,
                text=request_text,
                message_thread_id=topic_id
            )
        
        ticket_id = sent_message.message_id
        
        # Сохраняем в базу данных
        ticket_db[ticket_id] = {
            "user_id": user_id,
            "type": ticket_type,
            "topic_id": topic_id,
            "data": dict(context.user_data),
            "status": "pending"
        }
        
        return ticket_id
        
    except Exception as e:
        logger.error(f"Ошибка отправки заявки: {e}")
        return None

async def confirm_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение и отправка заявки"""
    ticket_type = context.user_data["type"]
    ticket_id = await send_ticket_to_topic(update, context, ticket_type)
    
    if not ticket_id:
        await update.message.reply_text(
            "❌ Произошла ошибка при отправке заявки. Попробуйте позже.",
            reply_markup=create_main_menu()
        )
        return MAIN_MENU
    
    # Формируем сообщение об успехе
    success_text = "✅ Заявка успешно отправлена!\n\n"
    
    if ticket_type == "pass":
        success_text += "Когда пропуск будет готов, мы вас уведомим."
    elif ticket_type == "purchase":
        success_text += "Мы рассмотрим вашу заявку на закупку и сообщим о результате."
    elif ticket_type == "repair":
        success_text += "Специалисты уже работают над решением проблемы."
    else:
        success_text += "Ваша заявка принята в работу."
    
    success_text += "\n\nВы можете отслеживать статус в этом чате."
    
    await update.message.reply_text(
        success_text,
        reply_markup=create_main_menu()
    )
    return MAIN_MENU

async def cancel_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена заявки и возврат в главное меню"""
    await update.message.reply_text(
        "❌ Заявка отменена.",
        reply_markup=create_main_menu()
    )
    return MAIN_MENU

# ====== ОБРАБОТКА ОТВЕТОВ ОТ ОФИС-МЕНЕДЖЕРОВ ======
async def handle_manager_reply(update: Update, context: CallbackContext):
    """Обработка ответов от офис-менеджеров в темах"""
    # Проверяем, что это ответ на сообщение
    if not update.message.reply_to_message:
        return
    
    # Проверяем, что ответ в нужной группе
    if update.effective_chat.id != AHO_GROUP_ID:
        return
    
    # Проверяем права пользователя
    user_id = update.effective_user.id
    
    # Разрешаем ответы только от:
    # 1. Назначенных менеджеров
    # 2. Анонимных администраторов групп (если включено)
    # 3. Самого бота (на всякий случай)
    is_allowed = (
        user_id in MANAGER_IDS or
        user_id == 1087968824 or  # GroupAnonymousBot
        user_id == context.bot.id
    )
    
    if not is_allowed:
        try:
            # Уведомляем пользователя об отсутствии прав
            await update.message.reply_text(
                "⛔ У вас недостаточно прав для обработки заявок.\n"
                "Обратитесь к администратору для получения доступа.",
                reply_to_message_id=update.message.message_id
            )
        except Exception as e:
            logger.warning(f"Не удалось уведомить пользователя: {e}")
        return
    
    # Получаем ID исходного сообщения (заявки)
    ticket_id = update.message.reply_to_message.message_id
    
    # Проверяем, что это заявка из нашей базы
    if ticket_id not in ticket_db:
        return
    
    # Получаем данные о заявке
    ticket = ticket_db[ticket_id]
    user_id = ticket["user_id"]
    manager_text = update.message.text
    
    # Проверяем, является ли сообщение отметкой о выполнении
    if "готов" in manager_text.lower():
        # Формируем уведомление о выполнении
        notification = "✅ Ваша заявка выполнена!\n\n"
        
        if ticket["type"] == "pass":
            notification += "Пропуск готов. Вы можете получить его у охраны."
        elif ticket["type"] == "purchase":
            notification += "Закупка выполнена. Товар будет доставлен в офис."
        elif ticket["type"] == "repair":
            notification += "Проблема устранена. Если что-то не работает, создайте новую заявку."
        else:
            notification += "Ваша просьба выполнена."
        
        # Обновляем статус заявки
        ticket_db[ticket_id]["status"] = "completed"
    else:
        # Формируем уведомление с комментарием
        notification = (
            "📬 Вам сообщение от службы АХО:\n\n"
            f"{manager_text}"
        )
    
    try:
        # Отправляем уведомление сотруднику
        await context.bot.send_message(
            chat_id=user_id,
            text=notification
        )
        
        # Подтверждаем менеджеру
        await update.message.reply_text(
            "✅ Уведомление отправлено сотруднику!",
            reply_to_message_id=update.message.message_id
        )
        
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления: {e}")
        await update.message.reply_text(
            "❌ Не удалось отправить уведомление сотруднику.",
            reply_to_message_id=update.message.message_id
        )

# ====== КОМАНДЫ ДЛЯ УПРАВЛЕНИЯ МЕНЕДЖЕРАМИ ======
async def get_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для получения ID пользователя"""
    user_id = update.effective_user.id
    await update.message.reply_text(
        f"🆔 Ваш ID: `{user_id}`\n\n"
        "Сообщите этот ID администратору для добавления в менеджеры.",
        parse_mode="Markdown"
    )

async def list_managers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать список менеджеров"""
    if not MANAGER_IDS:
        await update.message.reply_text("Список менеджеров пуст.")
        return
    
    manager_list = "\n".join([f"• `{mid}`" for mid in MANAGER_IDS])
    await update.message.reply_text(
        f"👨‍💼 Список менеджеров:\n{manager_list}",
        parse_mode="Markdown"
    )

async def add_manager(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавить менеджера (только для админа)"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ У вас нет прав для выполнения этой команды.")
        return
    
    try:
        # Пытаемся получить ID из аргументов команды
        new_id = int(context.args[0])
        
        # Проверяем, не добавлен ли уже
        if new_id in MANAGER_IDS:
            await update.message.reply_text(f"⚠️ Пользователь `{new_id}` уже в списке менеджеров.", parse_mode="Markdown")
            return
        
        # Добавляем в список
        MANAGER_IDS.append(new_id)
        
        # Обновляем файл .env
        with open('config.env', 'a') as f:
            f.write(f"\nMANAGER_IDS={','.join(map(str, MANAGER_IDS))}")
        
        await update.message.reply_text(
            f"✅ Пользователь `{new_id}` добавлен в менеджеры!",
            parse_mode="Markdown"
        )
        
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Неверный формат команды. Используйте: /add_manager <ID>")
    except Exception as e:
        logger.error(f"Ошибка добавления менеджера: {e}")
        await update.message.reply_text("❌ Произошла ошибка при добавлении менеджера.")

def main():
    # Проверка наличия менеджеров
    if not MANAGER_IDS:
        logger.warning("Список MANAGER_IDS пуст! Никто не сможет обрабатывать заявки.")
    
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Главный обработчик
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MAIN_MENU: [MessageHandler(filters.TEXT, main_menu)],
            
            # Заказ пропуска
            PASS_FIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_pass_fio)],
            PASS_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_pass_date)],
            PASS_PURPOSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_pass_purpose)],
            PASS_CONFIRM: [
                MessageHandler(filters.Regex(r'^✅ Да, отправить$'), confirm_ticket),
                MessageHandler(filters.Regex(r'^❌ Нет, отменить$'), cancel_request)
            ],
            
            # Заявка на закупку
            PURCHASE_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_purchase_link)],
            PURCHASE_QUANTITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_purchase_quantity)],
            PURCHASE_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_purchase_reason)],
            PURCHASE_CONFIRM: [
                MessageHandler(filters.Regex(r'^✅ Да, отправить$'), confirm_ticket),
                MessageHandler(filters.Regex(r'^❌ Нет, отменить$'), cancel_request)
            ],
            
            # Что-то сломалось
            PROBLEM_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_problem_type)],
            PROBLEM_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_problem_description)],
            PROBLEM_PHOTO: [
                MessageHandler(filters.PHOTO, process_problem_photo),
                CommandHandler("skip", skip_problem_photo)
            ],
            PROBLEM_CONFIRM: [
                MessageHandler(filters.Regex(r'^✅ Да, отправить$'), confirm_ticket),
                MessageHandler(filters.Regex(r'^❌ Нет, отменить$'), cancel_request)
            ],
            
            # Другое
            OTHER_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_other_description)],
            OTHER_CONFIRM: [
                MessageHandler(filters.Regex(r'^✅ Да, отправить$'), confirm_ticket),
                MessageHandler(filters.Regex(r'^❌ Нет, отменить$'), cancel_request)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_request)],
        allow_reentry=True
    )
    
    # Обработчик ответов от менеджеров
    application.add_handler(MessageHandler(
        filters.TEXT & filters.REPLY & filters.ChatType.GROUPS,
        handle_manager_reply
    ))
    
    # Регистрируем команды управления
    application.add_handler(CommandHandler("id", get_user_id))
    application.add_handler(CommandHandler("managers", list_managers))
    application.add_handler(CommandHandler("add_manager", add_manager))
    
    application.add_handler(conv_handler)
    
    print("Бот службы АХО запущен! Закройте это окно для остановки.")
    application.run_polling()

if __name__ == "__main__":
    main()
