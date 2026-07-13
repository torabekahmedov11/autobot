"""Loyiha sozlamalari — barcha env o'zgaruvchilar shu yerda."""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # PostgreSQL
    DATABASE_URL: str

    # Telegram
    TELEGRAM_BOT_TOKEN: str

    # Instagram
    IG_APP_ID: str
    IG_APP_SECRET: str
    WEBHOOK_VERIFY_TOKEN: str
    IG_BUSINESS_ACCOUNT_ID: str
    IG_ACCESS_TOKEN: str

    # Encryption
    FERNET_KEY: str

    # License
    LICENSE_MASTER_KEY: str = "your_master_key_here"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
