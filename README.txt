=== CEREBRAS AI BOT ===

1. Получи API ключ: https://cloud.cerebras.ai
2. Создай бота у @BotFather

=== Railway ===
1. Загрузи файлы на GitHub
2. New Project -> Deploy from GitHub
3. Variables:
   BOT_TOKEN = токен
   CEREBRAS_API_KEY = ключ с cerebras.ai
   SYSTEM_PROMPT = (опционально) системный промпт

=== Docker локально ===
cp .env.example .env
nano .env
docker build -t cerebras-bot .
docker run --env-file .env cerebras-bot

=== Возможности ===
- Диалог с памятью (хранит последние 20 сообщений)
- /clear — очистить историю
- /history — посмотреть длину истории
- Модель: gpt-oss-120b (самая мощная у Cerebras)
- Скорость: Cerebras очень быстрый (~1000 tokens/sec)
