"""Loyiha sozlamalari — barcha env o'zgaruvchilar shu yerda."""

from typing import Optional
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
    IG_VERIFY_TOKEN: Optional[str] = None
    WEBHOOK_VERIFY_TOKEN: Optional[str] = None
    IG_BUSINESS_ACCOUNT_ID: Optional[str] = None
    IG_ACCESS_TOKEN: Optional[str] = None

    # Encryption
    ENCRYPTION_KEY: Optional[str] = None
    FERNET_KEY: Optional[str] = None

    # License
    LICENSE_MASTER_KEY: str = "your_master_key_here"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
