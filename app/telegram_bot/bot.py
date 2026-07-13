"""Telegram bot — Aiogram 3.x bilan asosiy sozlash."""

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import get_settings
from app.telegram_bot.handlers import setup, posts, admin

settings = get_settings()

bot = Bot(
    token=settings.TELEGRAM_BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)

dp = Dispatcher(storage=MemoryStorage())

# Handler'larni ro'yxatdan o'tkazish
dp.include_router(setup.router)
dp.include_router(posts.router)
dp.include_router(admin.router)
