app/
├── api/                  # Модули интеграций (GPT, Yookassa)
│   ├── gpt.py
│   ├── yookassa.py
│   └── telegram_api.py
├── bot/                  # Telegram-бот на Aiogram
│   ├── bot.py
│   ├── utils.py
│   └── handlers/
│       ├── start.py
│       ├── subscribe.py
│       ├── profile.py
│       ├── broadcast.py
│       ├── entry.py        # сообщения (текст, фото, голос)
│       └── admin.py
├── db/                   # Работа с БД
│   ├── mysql.py
│   └── redis_client.py
├── services/             # Бизнес-логика
│   ├── user.py
    ├── context.py
│   ├── payments_logic.py
├── tasks/                # ARQ задачи
│   ├── subscriptions.py
│   └── daily_reset.py
├── utils/                # Утилиты
│   ├── audio.py
│   ├── formatter.py
│   ├── logger.py
├── main.py               # FastAPI точка входа
├── arq_worker.py 
├── config.py 
├── init_webhook.py
.env                      # Окружение
docker-compose.yml
Dockerfile
requirements.txt
