"""Setup handler — /start, Instagram OAuth, akkaunt ulash."""

import secrets

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    CallbackQuery,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import async_session
from app.models import Business
from app.services.crypto import encrypt_token
from app.utils.logger import logger

router = Router(name="setup")


def _main_menu_keyboard() -> InlineKeyboardMarkup:
    """Asosiy menyu tugmalari."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Yangi post qo'shish", callback_data="add_post")],
            [InlineKeyboardButton(text="📋 Postlarim", callback_data="my_posts")],
        ]
    )


async def _get_business(telegram_id: int, db: AsyncSession) -> Business | None:
    """Telegram ID bo'yicha biznes topish."""
    stmt = select(Business).where(Business.owner_telegram_id == telegram_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _check_active(message: Message, db: AsyncSession) -> Business | None:
    """
    Ruxsat tekshiruvi: owner_telegram_id == from_user.id
    va businesses.is_active == TRUE.
    """
    business = await _get_business(message.from_user.id, db)
    if not business:
        return None
    if not business.is_active:
        await message.answer("⛔ Xizmat vaqtincha to'xtatilgan.")
        return None
    return business


@router.message(CommandStart())
async def cmd_start(message: Message):
    """
    /start — Salom xabari + Instagram ulash tugmasi.
    Agar allaqachon ulangan bo'lsa — asosiy menyuni ko'rsatadi.
    """
    async with async_session() as db:
        business = await _get_business(message.from_user.id, db)

    if business and business.ig_access_token:
        await message.answer(
            f"👋 Qaytib kelganingizdan xursandmiz, <b>{business.business_name or 'foydalanuvchi'}</b>!\n\n"
            "Quyidagi menyudan foydalaning:",
            reply_markup=_main_menu_keyboard(),
        )
        return

    settings = get_settings()
    base_url = getattr(settings, "RENDER_URL", "https://autobot-yqnm.onrender.com")
    callback_url = f"{base_url}/auth/callback"
    # Facebook OAuth link — bu brauzer orqali ochiladi
    oauth_url = (
        f"https://www.facebook.com/v21.0/dialog/oauth?"
        f"client_id={settings.IG_APP_ID}"
        f"&redirect_uri={callback_url}"
        f"&scope=instagram_basic,instagram_manage_comments,"
        f"instagram_manage_messages,pages_manage_metadata,"
        f"pages_show_list"
        f"&state={message.from_user.id}"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Instagram ulash", url=oauth_url)],
        ]
    )

    await message.answer(
        "👋 Salom! Instagram Auto-DM botiga xush kelibsiz!\n\n"
        "Bu bot izohda kalit so'z yozgan foydalanuvchilarga "
        "avtomatik DM yuboradi.\n\n"
        "Boshlash uchun Instagram akkauntingizni ulang:",
        reply_markup=keyboard,
    )


@router.callback_query(F.data == "main_menu")
async def show_main_menu(callback: CallbackQuery):
    """Asosiy menyuga qaytish."""
    await callback.message.edit_text(
        "📌 Asosiy menyu — quyidagi amallardan birini tanlang:",
        reply_markup=_main_menu_keyboard(),
    )
    await callback.answer()
