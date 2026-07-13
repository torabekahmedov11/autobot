"""Admin handler — postlarni boshqarish (ro'yxat, tahrirlash, o'chirish)."""

from aiogram import Router, F
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models import Business, PostResponse, TrackedPost
from app.utils.logger import logger

router = Router(name="admin")


# ─── POSTLAR RO'YXATI ────────────────────────────────────────
@router.callback_query(F.data == "my_posts")
async def list_posts(callback: CallbackQuery):
    """📋 Postlarim — barcha kuzatilayotgan postlar ro'yxati."""
    async with async_session() as db:
        biz_stmt = select(Business).where(
            Business.owner_telegram_id == callback.from_user.id,
            Business.is_active == True,  # noqa: E712
        )
        result = await db.execute(biz_stmt)
        business = result.scalar_one_or_none()

        if not business:
            await callback.answer(
                "⛔ Xizmat vaqtincha to'xtatilgan.", show_alert=True
            )
            return

        posts_stmt = (
            select(TrackedPost)
            .where(TrackedPost.business_id == business.id)
            .order_by(TrackedPost.created_at.desc())
        )
        posts_result = await db.execute(posts_stmt)
        posts = posts_result.scalars().all()

    if not posts:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="➕ Post qo'shish", callback_data="add_post"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🏠 Asosiy menyu", callback_data="main_menu"
                    )
                ],
            ]
        )
        await callback.message.edit_text(
            "📋 Hozircha hech qanday post qo'shilmagan.", reply_markup=keyboard
        )
        await callback.answer()
        return

    # Postlar ro'yxati tugmalari
    buttons = []
    for post in posts:
        status = "🟢" if post.is_active else "🔴"
        label = f"{status} {post.keyword} — {(post.post_url or '')[:30]}..."
        buttons.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"view_post_{post.id}",
                )
            ]
        )

    buttons.append(
        [InlineKeyboardButton(text="🏠 Asosiy menyu", callback_data="main_menu")]
    )

    await callback.message.edit_text(
        f"📋 <b>Sizning postlaringiz</b> ({len(posts)} ta):\n\n"
        "Batafsil ko'rish uchun tanlang:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()


# ─── POST BATAFSIL ───────────────────────────────────────────
@router.callback_query(F.data.startswith("view_post_"))
async def view_post(callback: CallbackQuery):
    """Postni batafsil ko'rish + tahrirlash/o'chirish tugmalari."""
    post_id = int(callback.data.split("_")[-1])

    async with async_session() as db:
        post_stmt = select(TrackedPost).where(TrackedPost.id == post_id)
        result = await db.execute(post_stmt)
        post = result.scalar_one_or_none()

        if not post:
            await callback.answer("❌ Post topilmadi.", show_alert=True)
            return

        # Javob kontentlarini olish
        resp_stmt = (
            select(PostResponse)
            .where(PostResponse.tracked_post_id == post_id)
            .order_by(PostResponse.sort_order)
        )
        resp_result = await db.execute(resp_stmt)
        responses = resp_result.scalars().all()

    status = "🟢 Faol" if post.is_active else "🔴 To'xtatilgan"
    toggle_text = "⏸ To'xtatish" if post.is_active else "▶️ Faollashtirish"

    # Kontentlarni ko'rsatish
    content_lines = []
    for r in responses:
        if r.content_type == "text":
            content_lines.append(f"💬 Matn: {r.content_value[:80]}...")
        elif r.content_type == "image":
            content_lines.append("🖼 Rasm: [mavjud]")
        elif r.content_type == "link":
            content_lines.append(f"🔗 Link: {r.content_value[:60]}")
    content_text = "\n".join(content_lines) if content_lines else "Kontent yo'q"

    text = (
        f"📄 <b>Post tafsilotlari</b>\n\n"
        f"📎 URL: {post.post_url or 'N/A'}\n"
        f"🔑 Kalit so'z: <code>{post.keyword}</code>\n"
        f"📊 Holat: {status}\n"
        f"📅 Qo'shilgan: {post.created_at.strftime('%d.%m.%Y %H:%M') if post.created_at else 'N/A'}\n\n"
        f"<b>Javob kontenti:</b>\n{content_text}"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=toggle_text,
                    callback_data=f"toggle_post_{post.id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗑 O'chirish",
                    callback_data=f"delete_post_{post.id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="◀️ Orqaga", callback_data="my_posts"
                )
            ],
        ]
    )

    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


# ─── POST FAOLLASHTIRISH/TO'XTATISH ──────────────────────────
@router.callback_query(F.data.startswith("toggle_post_"))
async def toggle_post(callback: CallbackQuery):
    """Postni faollashtirish yoki to'xtatish."""
    post_id = int(callback.data.split("_")[-1])

    async with async_session() as db:
        stmt = select(TrackedPost).where(TrackedPost.id == post_id)
        result = await db.execute(stmt)
        post = result.scalar_one_or_none()

        if not post:
            await callback.answer("❌ Post topilmadi.", show_alert=True)
            return

        post.is_active = not post.is_active
        await db.commit()

        new_status = "faollashtirildi 🟢" if post.is_active else "to'xtatildi 🔴"
        logger.info("Post %s %s", post_id, new_status)

    await callback.answer(f"Post {new_status}", show_alert=True)

    # Qayta ko'rsatish
    await view_post(callback)


# ─── POST O'CHIRISH ──────────────────────────────────────────
@router.callback_query(F.data.startswith("delete_post_"))
async def confirm_delete_post(callback: CallbackQuery):
    """O'chirish tasdiqlash so'rash."""
    post_id = int(callback.data.split("_")[-1])

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Ha, o'chirish",
                    callback_data=f"confirm_delete_{post_id}",
                ),
                InlineKeyboardButton(
                    text="❌ Bekor qilish",
                    callback_data=f"view_post_{post_id}",
                ),
            ]
        ]
    )

    await callback.message.edit_text(
        "⚠️ <b>Rostdan ham bu postni o'chirmoqchimisiz?</b>\n\n"
        "Barcha javob kontentlari va loglar ham o'chadi!",
        reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_delete_"))
async def execute_delete_post(callback: CallbackQuery):
    """Postni bazadan o'chirish (CASCADE)."""
    post_id = int(callback.data.split("_")[-1])

    async with async_session() as db:
        stmt = delete(TrackedPost).where(TrackedPost.id == post_id)
        await db.execute(stmt)
        await db.commit()
        logger.info("Post o'chirildi: %s", post_id)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Postlarim", callback_data="my_posts")],
            [InlineKeyboardButton(text="🏠 Asosiy menyu", callback_data="main_menu")],
        ]
    )

    await callback.message.edit_text(
        "🗑 Post muvaffaqiyatli o'chirildi.", reply_markup=keyboard
    )
    await callback.answer()
