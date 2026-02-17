# app/config.py
import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    def __init__(self):
        # Telegram Bot API
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.telegram_bot_url = os.getenv("TELEGRAM_BOT_URL")
        self.admin_http_token = os.getenv("ADMIN_HTTP_TOKEN")

        # OpenAI API
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.openai_api_url = os.getenv("OPENAI_API_URL", "https://api.openai.com/v1/chat/completions")
        self.openai_default_model = os.getenv("OPENAI_DEFAULT_MODEL", "gpt-5.2")
        self.openai_timeout = int(os.getenv("OPENAI_TIMEOUT_SECONDS", 25))
        self.openai_max_tokens = int(os.getenv("OPENAI_MAX_TOKENS", 2048))
        self.openai_temperature = float(os.getenv("OPENAI_TEMPERATURE", 0.5))

        # YooKassa API
        self.yookassa_store_id = os.getenv("YOKASSA_STORE_ID")
        self.yookassa_secret_key = os.getenv("YOKASSA_SECRET_KEY")
        self.yookassa_webhook_secret = os.getenv("YOKASSA_WEBHOOK_SECRET")

        # Database (MySQL)
        self.db_host = os.getenv("DB_HOST")
        self.db_port = int(os.getenv("DB_PORT", 3306))
        self.db_user = os.getenv("DB_USER")
        self.db_password = os.getenv("DB_PASSWORD")
        self.db_name = os.getenv("DB_NAME")

        # Cache (Redis)
        self.redis_host = os.getenv("REDIS_HOST", "redis")
        self.redis_port = int(os.getenv("REDIS_PORT", 6379))
        self.redis_password = os.getenv("REDIS_PASSWORD")
        self.redis_url = os.getenv("REDIS_URL")


        # Webhook
        self.webhook_url = os.getenv("WEBHOOK_URL")
        self.webhook_secret = os.getenv("WEBHOOK_SECRET")

        # Admin Settings
        self.admin_id = int(os.getenv("ADMIN_ID", 0))

        # Business Logic Settings
        self.max_failed_autopay_attempts = int(os.getenv("MAX_FAILED_AUTOPAY_ATTEMPTS", 3))
        self.default_subscription_days = int(os.getenv("DEFAULT_SUBSCRIPTION_DAYS", 30))
        self.default_subscription_amount = float(os.getenv("DEFAULT_SUBSCRIPTION_AMOUNT", 1090.0))

        # Logging
        self.log_level = os.getenv("LOG_LEVEL", "INFO").upper()

settings = Settings()