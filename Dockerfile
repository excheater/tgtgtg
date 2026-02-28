# Используем легкий образ Python
FROM python:3.11-slim

# Устанавливаем системные зависимости: ffmpeg для нарезки видео
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем файл зависимостей
COPY requirements.txt .

# Устанавливаем библиотеки
RUN pip install --no-cache-dir -r requirements.txt

# Копируем все файлы проекта (включая bot.py и cookies.txt)
COPY . .

# Создаем папку для загрузок, чтобы не было ошибок доступа
RUN mkdir -p /app/downloads && chmod 777 /app/downloads

# Команда запуска бота
CMD ["python", "bot.py"]
