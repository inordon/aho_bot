# 🏢 АХО Бот

Production-ready Telegram бот для управления заявками административно-хозяйственного отдела.

## 📋 Возможности

- **4 типа заявок**: пропуска, закупки, ремонты, прочее
- **3 уровня приоритета**: 🔴 Срочно, 🟡 Обычно, 🟢 Планово
- **Система ролей**: множественные роли на пользователя
- **История статусов**: полное отслеживание изменений
- **Rate limiting**: защита от спама (5 заявок/час)
- **JSON логирование**: с ротацией по дням
- **PostgreSQL**: надежное хранение данных

## 🚀 Быстрый старт

### 1. Клонирование и настройка

```bash
git clone <repository>
cd aho-bot

# Создаем конфигурацию
cp .env.example config.env
```

### 2. Настройка config.env

Отредактируйте `config.env`:

```env
# Обязательные параметры
BOT_TOKEN=your_bot_token_here
AHO_GROUP_ID=-1001234567890
ADMIN_ID=123456789

# ID тем в группе
PASS_TOPIC_ID=2
PURCHASE_TOPIC_ID=4
REPAIR_TOPIC_ID=6
OTHER_TOPIC_ID=10
```

### 3. Запуск

```bash
docker-compose up -d
```

## 📱 Команды

### Для пользователей
- `/start` - Главное меню
- `/new_ticket` - Новая заявка
- `/mystatus` - Мои заявки

### Для менеджеров
- `/tickets` - Заявки для обработки

### Для администраторов
- `/add_manager <id> <role>` - Добавить роль
- `/remove_manager <id> <role>` - Удалить роль
- `/list_managers` - Список менеджеров
- `/stats` - Статистика
- `/set_lead <id>` - Назначить руководителя

## 👥 Роли

| Роль | Описание |
|------|----------|
| `manager_pass` | Менеджер по пропускам |
| `manager_purchase` | Менеджер по закупкам |
| `manager_repair` | Менеджер по ремонтам |
| `manager_other` | Менеджер по прочим заявкам |
| `lead` | Руководитель (все заявки) |
| `admin` | Администратор системы |

## 🗃️ Структура проекта

```
aho-bot/
├── bot.py                 # Точка входа
├── docker-compose.yml     # Оркестрация
├── Dockerfile            # Образ
├── requirements.txt      # Зависимости
├── config.env            # Конфигурация (создать)
├── .env.example          # Шаблон конфигурации
├── handlers/
│   ├── user_handlers.py     # Обработчики пользователей
│   ├── manager_handlers.py  # Обработчики менеджеров
│   └── admin_handlers.py    # Обработчики админов
├── models/
│   ├── database.py       # Пул соединений, миграции
│   ├── user.py           # Модель пользователей
│   ├── ticket.py         # Модель заявок
│   └── analytics.py      # Аналитика
├── validators/
│   └── input_validators.py  # Валидация данных
├── utils/
│   ├── logger.py         # JSON логирование
│   ├── decorators.py     # Декораторы
│   └── email_service.py  # Email уведомления
├── schemas/
│   └── database_schema.sql  # SQL схема
├── logs/                 # Логи (создается автоматически)
└── data/                 # Данные
```

## 🔧 Настройка группы Telegram

1. Создайте группу с темами (Topics)
2. Добавьте бота в группу с правами администратора
3. Создайте темы: Пропуска, Закупки, Ремонты, Другое
4. Получите ID тем (отправьте сообщение и посмотрите в логах)

## 📊 Мониторинг

### Логи
```bash
# Просмотр логов бота
docker-compose logs -f bot

# Просмотр логов БД
docker-compose logs -f postgres
```

### Подключение к БД
```bash
psql -h localhost -p 5434 -U aho_user -d aho_bot
```

## 🔒 Безопасность

- Храните `config.env` в безопасности
- Не коммитьте секреты в репозиторий
- Используйте сильные пароли для БД
- Регулярно обновляйте зависимости

## 📧 Email уведомления (опционально)

Для включения email уведомлений:

```env
SMTP_ENABLED=true
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_app_password
SMTP_FROM=your_email@gmail.com
```

## 🛠️ Разработка

```bash
# Создание виртуального окружения
python -m venv venv
source venv/bin/activate

# Установка зависимостей
pip install -r requirements.txt

# Запуск без Docker (требуется локальный PostgreSQL)
python bot.py
```

## 📝 Лицензия

MIT License
