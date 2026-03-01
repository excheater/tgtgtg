=== БОТА-НАРЕЗЧИК ВИДЕО ===

1. Переименуй .env.example в .env и заполни:
   BOT_TOKEN = токен от @BotFather (нового бота!)
   API_ID    = число с my.telegram.org
   API_HASH  = хеш с my.telegram.org

2. Запуск локально:
   docker-compose up --build

3. Railway:
   - Загрузи все файлы на GitHub (приватный репо!)
   - New Project -> Deploy from GitHub
   - Variables: BOT_TOKEN, API_ID, API_HASH

=== КАК ПОЛЬЗОВАТЬСЯ ===
1. /start — выбери режим (15 или 30 сек)
2. Кинь видео или перешли из канала
3. Бот скачает и нарежет на части
