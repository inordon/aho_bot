-- ============================================
-- АХО Бот - Схема базы данных PostgreSQL
-- ============================================

-- Создание расширений
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================
-- ТАБЛИЦА: users - Пользователи системы
-- ============================================
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    username VARCHAR(255),
    first_name VARCHAR(255),
    last_name VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- ТАБЛИЦА: roles - Роли пользователей
-- ============================================
CREATE TABLE IF NOT EXISTS roles (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    description VARCHAR(255)
);

-- Вставка предустановленных ролей
INSERT INTO roles (name, description) VALUES
    ('user', 'Обычный пользователь'),
    ('manager_pass', 'Менеджер по пропускам'),
    ('manager_purchase', 'Менеджер по закупкам'),
    ('manager_repair', 'Менеджер по ремонтам'),
    ('manager_other', 'Менеджер по прочим заявкам'),
    ('lead', 'Руководитель (все заявки)'),
    ('admin', 'Администратор системы')
ON CONFLICT (name) DO NOTHING;

-- ============================================
-- ТАБЛИЦА: user_roles - Связь пользователей и ролей
-- ============================================
CREATE TABLE IF NOT EXISTS user_roles (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    role_id INTEGER REFERENCES roles(id) ON DELETE CASCADE,
    assigned_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    assigned_by BIGINT,
    UNIQUE(user_id, role_id)
);

-- ============================================
-- ТАБЛИЦА: tickets - Заявки
-- ============================================
CREATE TABLE IF NOT EXISTS tickets (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    telegram_user_id BIGINT NOT NULL,
    type VARCHAR(20) NOT NULL CHECK (type IN ('pass', 'purchase', 'repair', 'other')),
    status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'in_progress', 'completed', 'rejected')),
    priority VARCHAR(10) NOT NULL DEFAULT 'normal' CHECK (priority IN ('urgent', 'normal', 'low')),
    data JSONB NOT NULL DEFAULT '{}',
    message_id BIGINT,
    topic_id BIGINT,
    assigned_to INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- ТАБЛИЦА: ticket_status_history - История статусов
-- ============================================
CREATE TABLE IF NOT EXISTS ticket_status_history (
    id SERIAL PRIMARY KEY,
    ticket_id INTEGER REFERENCES tickets(id) ON DELETE CASCADE,
    old_status VARCHAR(20),
    new_status VARCHAR(20) NOT NULL,
    changed_by BIGINT,
    changed_by_username VARCHAR(255),
    comment TEXT,
    changed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- ТАБЛИЦА: operation_logs - Логи операций
-- ============================================
CREATE TABLE IF NOT EXISTS operation_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    telegram_user_id BIGINT,
    action VARCHAR(100) NOT NULL,
    details JSONB DEFAULT '{}',
    ip_address VARCHAR(45),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- ТАБЛИЦА: rate_limits - Rate limiting
-- ============================================
CREATE TABLE IF NOT EXISTS rate_limits (
    id SERIAL PRIMARY KEY,
    telegram_user_id BIGINT NOT NULL,
    action_type VARCHAR(50) NOT NULL,
    action_count INTEGER DEFAULT 1,
    window_start TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(telegram_user_id, action_type)
);

-- ============================================
-- ИНДЕКСЫ для оптимизации
-- ============================================

-- Индекс для быстрого поиска пользователя по telegram_id
CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);

-- Индекс для поиска заявок по пользователю
CREATE INDEX IF NOT EXISTS idx_tickets_user_id ON tickets(user_id);
CREATE INDEX IF NOT EXISTS idx_tickets_telegram_user_id ON tickets(telegram_user_id);

-- Индекс для поиска заявок по статусу
CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);

-- Индекс для поиска заявок по типу
CREATE INDEX IF NOT EXISTS idx_tickets_type ON tickets(type);

-- Индекс для поиска заявок по приоритету
CREATE INDEX IF NOT EXISTS idx_tickets_priority ON tickets(priority);

-- Составной индекс для поиска заявок по типу и статусу
CREATE INDEX IF NOT EXISTS idx_tickets_type_status ON tickets(type, status);

-- Индекс для истории статусов
CREATE INDEX IF NOT EXISTS idx_ticket_history_ticket_id ON ticket_status_history(ticket_id);

-- Индекс для логов операций
CREATE INDEX IF NOT EXISTS idx_operation_logs_user_id ON operation_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_operation_logs_created_at ON operation_logs(created_at);

-- Индекс для rate limits
CREATE INDEX IF NOT EXISTS idx_rate_limits_user_action ON rate_limits(telegram_user_id, action_type);

-- ============================================
-- ФУНКЦИЯ: Автообновление updated_at
-- ============================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Триггеры для автообновления
DROP TRIGGER IF EXISTS update_users_updated_at ON users;
CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_tickets_updated_at ON tickets;
CREATE TRIGGER update_tickets_updated_at
    BEFORE UPDATE ON tickets
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- ПРЕДСТАВЛЕНИЯ для статистики
-- ============================================
CREATE OR REPLACE VIEW ticket_stats AS
SELECT 
    type,
    status,
    priority,
    COUNT(*) as count,
    DATE(created_at) as date
FROM tickets
GROUP BY type, status, priority, DATE(created_at);

CREATE OR REPLACE VIEW user_ticket_stats AS
SELECT 
    u.telegram_id,
    u.username,
    u.first_name,
    COUNT(t.id) as total_tickets,
    COUNT(CASE WHEN t.status = 'pending' THEN 1 END) as pending,
    COUNT(CASE WHEN t.status = 'in_progress' THEN 1 END) as in_progress,
    COUNT(CASE WHEN t.status = 'completed' THEN 1 END) as completed,
    COUNT(CASE WHEN t.status = 'rejected' THEN 1 END) as rejected
FROM users u
LEFT JOIN tickets t ON u.id = t.user_id
GROUP BY u.id, u.telegram_id, u.username, u.first_name;

-- ============================================
-- КОММЕНТАРИИ К ТАБЛИЦАМ
-- ============================================
COMMENT ON TABLE users IS 'Пользователи системы';
COMMENT ON TABLE roles IS 'Роли пользователей (manager_pass, manager_purchase, etc.)';
COMMENT ON TABLE user_roles IS 'Связь пользователей и ролей (многие-ко-многим)';
COMMENT ON TABLE tickets IS 'Заявки АХО';
COMMENT ON TABLE ticket_status_history IS 'История изменений статусов заявок';
COMMENT ON TABLE operation_logs IS 'Логи всех операций в системе';
COMMENT ON TABLE rate_limits IS 'Таблица для rate limiting';
