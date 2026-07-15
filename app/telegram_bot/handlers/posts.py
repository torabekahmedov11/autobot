"""Posts handler — post qo'shish, kalit so'z, javob kontenti (FSM)."""

import re

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models import Business, PostResponse, TrackedPost
from app.utils.logger import logger

router = Router(name="posts")


# ─── FSM STATES ──────────────────────────────────────────────
class AddPostStates(StatesGroup):
    waiting_for_post_url = State()
    waiting_for_keyword = State()
    waiting_for_text = State()
    waiting_for_image = State()
    waiting_for_link = State()


# ─── YORDAMCHILAR ────────────────────────────────────────────
async def _get_active_business(
    telegram_id: int, db: AsyncSession
) -> Business | None:
    stmt = select(Business).where(
        Business.owner_telegram_id == telegram_id,
        Business.is_active == True,  # noqa: E712
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


def _extract_shortcode_from_url(url: str) -> str | None:
    """Post URL dan shortcode olish."""
    match = re.search(r"instagram\.com\/(?:p|reel|tv)\/([A-Za-z0-9_\-]+)", url)
    if match:
        return match.group(1)
    return url.strip()


async def _resolve_media_id(shortcode: str, access_token: str) -> str | None:
    """
    Shortcode'ni haqiqiy raqamli ig_media_id ga aylantirish.
    Instagram Graph API: GET /{ig-user-id}/media?fields=id,shortcode
    yoki oEmbed endpoint orqali.
    """
    import httpx
    try:
        # oEmbed orqali media_id olish
        url = f"https://graph.facebook.com/v21.0/instagram_oembed"
        params = {
            "url": f"https://www.instagram.com/p/{shortcode}/",
            "access_token": access_token,
            "fields": "media_id",
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params=params)
            if resp.status_code == 200:
                data = resp.json()
                media_id = data.get("media_id")
                if media_id:
                    logger.info("Shortcode %s -> media_id %s", shortcode, media_id)
                    return media_id
    except Exception as e:
        logger.warning("oEmbed media_id olishda xato: %s", str(e))

    # Fallback: shortcode ni qaytarish
    logger.warning("Media ID olishda fallback: shortcode=%s saqlanmoqda", shortcode)
    return shortcode


# ─── POST QO'SHISH BOSHLASH ──────────────────────────────────
@router.callback_query(F.data == "add_post")
async def start_add_post(callback: CallbackQuery, state: FSMContext):
    """Post qo'shish jarayonini boshlash."""
    async with async_session() as db:
        business = await _get_active_business(callback.from_user.id, db)

    if not business:
        await callback.answer("⛔ Avval Instagram akkauntingizni ulang!", show_alert=True)
        return

    await state.update_data(
        business_id=business.id,
        access_token=business.ig_access_token,
    )
    await state.set_state(AddPostStates.waiting_for_post_url)

    await callback.message.edit_text(
        "📎 <b>Post URL yuboring</b>\n\n"
        "Instagram postning havolasini yuboring.\n"
        "Masalan: https://www.instagram.com/p/ABC123/\n\n"
        "⚠️ Eski postlar uchun ham ishlaydi.",
    )
    await callback.answer()


# ─── POST URL QABUL QILISH ───────────────────────────────────
@router.message(AddPostStates.waiting_for_post_url)
async def receive_post_url(message: Message, state: FSMContext):
    """Post URL qabul qilindi — kalit so'z so'rash."""
    url = message.text.strip()

    if "instagram.com" not in url and not url.startswith("http"):
        await message.answer(
            "❌ Noto'g'ri format. Instagram post havolasini yuboring.\n"
            "Masalan: https://www.instagram.com/p/ABC123/"
        )
        return

    await message.answer("⏳ Post tekshirilmoqda...")

    shortcode = _extract_shortcode_from_url(url)

    # Access token bilan media_id ni olishga urinish
    data = await state.get_data()
    access_token = data.get("access_token", "")

    if access_token:
        try:
            from app.services.crypto import decrypt_token
            token = decrypt_token(access_token)
            media_id = await _resolve_media_id(shortcode, token)
        except Exception:
            media_id = shortcode
    else:
        media_id = shortcode

    await state.update_data(post_url=url, ig_media_id=media_id)
    await state.set_state(AddPostStates.waiting_for_keyword)

    await message.answer(
        "🔑 <b>Kalit so'zni kiriting</b>\n\n"
        "Izohda qaysi so'z bo'lsa javob yuborilsin?\n"
        "Masalan: <code>menga</code>, <code>link</code>, <code>kerak</code>"
    )


# ─── KALIT SO'Z QABUL QILISH ─────────────────────────────────
@router.message(AddPostStates.waiting_for_keyword)
async def receive_keyword(message: Message, state: FSMContext):
    """Kalit so'z qabul qilindi — javob matni so'rash."""
    keyword = message.text.strip()

    if len(keyword) < 2:
        await message.answer("❌ Kalit so'z kamida 2 ta belgidan iborat bo'lishi kerak.")
        return

    await state.update_data(keyword=keyword)
    await state.set_state(AddPostStates.waiting_for_text)

    await message.answer(
        "💬 <b>Javob matnini yuboring</b>\n\n"
        "Foydalanuvchiga DM'da yuboriladigan matnni kiriting:"
    )


# ─── JAVOB MATNI QABUL QILISH ────────────────────────────────
@router.message(AddPostStates.waiting_for_text)
async def receive_text_response(message: Message, state: FSMContext):
    """Javob matni qabul qilindi — rasm so'rash."""
    text = message.text.strip()

    if not text:
        await message.answer("❌ Matn bo'sh bo'lmasligi kerak.")
        return

    await state.update_data(response_text=text)
    await state.set_state(AddPostStates.waiting_for_image)

    await message.answer(
        "🖼 <b>Rasm yuboring</b> (yoki <code>yo'q</code>)\n\n"
        "DM'da matn bilan birga rasm ham yuborilsinmi?\n"
        "Rasm yuboring yoki <code>yo'q</code> deb yozing."
    )


# ─── RASM QABUL QILISH ───────────────────────────────────────
@router.message(AddPostStates.waiting_for_image)
async def receive_image_response(message: Message, state: FSMContext):
    """Rasm qabul qilindi yoki 'yo'q' — link so'rash."""
    if message.photo:
        # Eng katta o'lchamdagi rasmni olish
        photo = message.photo[-1]
        await state.update_data(response_image_file_id=photo.file_id)
    elif message.text and message.text.strip().lower() in ("yo'q", "yoq", "нет", "no"):
        await state.update_data(response_image_file_id=None)
    else:
        await message.answer(
            "❌ Rasm yuboring yoki <code>yo'q</code> deb yozing."
        )
        return

    await state.set_state(AddPostStates.waiting_for_link)

    await message.answer(
        "🔗 <b>Link yuboring</b> (yoki <code>yo'q</code>)\n\n"
        "DM'da qo'shimcha link ham yuborilsinmi?\n"
        "Link yuboring yoki <code>yo'q</code> deb yozing."
    )


# ─── LINK QABUL QILISH VA SAQLASH ────────────────────────────
@router.message(AddPostStates.waiting_for_link)
async def receive_link_response(message: Message, state: FSMContext):
    """Link qabul qilindi — hammasi bazaga saqlanadi."""
    link = None
    if message.text:
        text = message.text.strip()
        if text.lower() not in ("yo'q", "yoq", "нет", "no"):
            link = text

    data = await state.get_data()
    await state.clear()

    # Bazaga yozish
    async with async_session() as db:
        # TrackedPost yaratish
        tracked_post = TrackedPost(
            business_id=data["business_id"],
            ig_media_id=data["ig_media_id"],
            post_url=data["post_url"],
            keyword=data["keyword"],
            is_active=True,
        )
        db.add(tracked_post)
        await db.flush()  # ID olish uchun

        # PostResponse — matn (sort_order=1)
        sort_order = 1
        db.add(
            PostResponse(
                tracked_post_id=tracked_post.id,
                content_type="text",
                content_value=data["response_text"],
                sort_order=sort_order,
            )
        )

        # PostResponse — rasm (sort_order=2)
        if data.get("response_image_file_id"):
            sort_order += 1
            file = await message.bot.get_file(data["response_image_file_id"])
            image_url = f"https://api.telegram.org/file/bot{message.bot.token}/{file.file_path}"
            
            db.add(
                PostResponse(
                    tracked_post_id=tracked_post.id,
                    content_type="image",
                    content_value=image_url,
                    sort_order=sort_order,
                )
            )

        # PostResponse — link (sort_order=3)
        if link:
            sort_order += 1
            db.add(
                PostResponse(
                    tracked_post_id=tracked_post.id,
                    content_type="link",
                    content_value=link,
                    sort_order=sort_order,
                )
            )

        await db.commit()
        logger.info(
            "Yangi post qo'shildi: business=%s, post=%s, keyword=%s",
            data["business_id"],
            tracked_post.id,
            data["keyword"],
        )

    # Muvaffaqiyat xabari
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Yana post qo'shish", callback_data="add_post")],
            [InlineKeyboardButton(text="📋 Postlarim", callback_data="my_posts")],
            [InlineKeyboardButton(text="🏠 Asosiy menyu", callback_data="main_menu")],
        ]
    )

    has_image = "Ha" if data.get("response_image_file_id") else "Yo'q"
    link_text = link or "Yo'q"

    summary = (
        f"✅ <b>Tayyor!</b>\n\n"
        f"📎 Post: {data['post_url']}\n"
        f"🔑 Kalit so'z: <code>{data['keyword']}</code>\n"
        f"💬 Matn: {data['response_text'][:50]}...\n"
        f"🖼 Rasm: {has_image}\n"
        f"🔗 Link: {link_text}"
    )

    await message.answer(summary, reply_markup=keyboard)
