FROM python:3.11-slim

# Метаданные
LABEL maintainer="AHO Bot" \
      version="1.0" \
      description="Telegram бот для управления заявками АХО"

# Переменные окружения
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Рабочая директория
WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Копирование и установка зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование исходного кода
COPY bot.py .
COPY handlers/ handlers/
COPY models/ models/
COPY validators/ validators/
COPY utils/ utils/
COPY schemas/ schemas/

# Создание директорий для данных
RUN mkdir -p logs data

# Создание непривилегированного пользователя
RUN useradd -m -u 1000 botuser && \
    chown -R botuser:botuser /app

USER botuser

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import asyncio; asyncio.run(__import__('asyncpg').connect())" || exit 1

# Запуск бота
CMD ["python", "-u", "bot.py"]
