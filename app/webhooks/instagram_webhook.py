"""Instagram Webhook endpoint — 02_WEBHOOK_OQIMI.md bo'yicha."""

import hashlib
import hmac
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models import (
    Business,
    ErrorLog,
    PostResponse,
    ReplyLog,
    TrackedPost,
)
from app.services.instagram_api import (
    send_dm_image,
    send_dm_text,
    send_private_reply,
)
from app.utils.logger import logger

router = APIRouter(prefix="/webhook", tags=["webhook"])


# ─── IMZO TEKSHIRUVI ────────────────────────────────────────
def _verify_signature(payload: bytes, signature: str, app_secret: str) -> bool:
    """X-Hub-Signature-256 ni tekshiradi."""
    expected = "sha256=" + hmac.new(
        app_secret.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


# ─── WEBHOOK VERIFICATION (GET) ─────────────────────────────
@router.get("/instagram")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    """Facebook/Instagram webhook subscription verification."""
    settings = get_settings()
    if hub_mode == "subscribe" and hub_verify_token == settings.IG_VERIFY_TOKEN:
        logger.info("Webhook verification muvaffaqiyatli.")
        return Response(content=hub_challenge, media_type="text/plain")
    logger.warning("Webhook verification rad etildi.")
    return Response(content="Forbidden", status_code=403)


# ─── WEBHOOK HANDLER (POST) ──────────────────────────────────
@router.post("/instagram")
async def handle_instagram_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_hub_signature_256: str | None = Header(None),
):
    """
    Instagram webhook — izoh kelganda ishlov beradi.

    Qadamlar (02_WEBHOOK_OQIMI.md bo'yicha):
    1. Imzoni tekshir
    2. ig_media_id bo'yicha tracked_post top
    3. Business faolligini tekshir
    4. Kalit so'zni tekshir (case-insensitive substring)
    5. reply_log da dublikat borligini tekshir
    6. "Obuna bo'ldim" tugmali DM yubor
    7. Tugma bosilganda — javob kontentlarini yuborish
    """
    settings = get_settings()
    body = await request.body()

    # 1-QADAM: Imzo tekshiruvi
    if not x_hub_signature_256 or not _verify_signature(
        body, x_hub_signature_256, settings.IG_APP_SECRET
    ):
        logger.warning("Webhook: imzo tekshiruvi muvaffaqiyatsiz.")
        return Response(content="Forbidden", status_code=403)

    data = json.loads(body)
    logger.info("Webhook qabul qilindi: %s", data.get("object", "unknown"))

    # Webhook turini aniqlash
    for entry in data.get("entry", []):
        # ── IZOH (comments) webhook ──
        if "changes" in entry:
            for change in entry["changes"]:
                if change.get("field") == "comments":
                    await _handle_comment(change["value"], db, settings)

        # ── MESSAGING webhook (matn yozilganda) ──
        if "messaging" in entry:
            for msg_event in entry["messaging"]:
                if "message" in msg_event and not msg_event["message"].get("is_echo"):
                    await _handle_incoming_message(msg_event, db)

    return Response(content="OK", status_code=200)


# ─── IZOH ISHLOV BERISH ──────────────────────────────────────
async def _handle_comment(
    value: dict, db: AsyncSession, settings
) -> None:
    """Yangi izohni qayta ishlash — 2-6 qadamlar."""
    ig_media_id = value.get("media", {}).get("id", "")
    if not ig_media_id:
        ig_media_id = value.get("media_id", "")
    comment_id = value.get("id", "")
    comment_text = value.get("text", "")
    commenter_id = value.get("from", {}).get("id", "")

    if not all([ig_media_id, comment_id, comment_text, commenter_id]):
        logger.warning("Webhook: izoh ma'lumotlari to'liq emas.")
        return

    # 2-QADAM: tracked_posts dan topish
    stmt = (
        select(TrackedPost)
        .where(
            TrackedPost.ig_media_id == ig_media_id,
            TrackedPost.is_active == True,  # noqa: E712
        )
    )
    result = await db.execute(stmt)
    tracked_post = result.scalar_one_or_none()

    if not tracked_post:
        return  # Bu post kuzatilmayapti — hech narsa qilmaymiz

    # 3-QADAM: Business faolligini tekshirish
    biz_stmt = select(Business).where(
        Business.id == tracked_post.business_id,
        Business.is_active == True,  # noqa: E712
    )
    biz_result = await db.execute(biz_stmt)
    business = biz_result.scalar_one_or_none()

    if not business:
        return  # Business aktiv emas

    # 4-QADAM: Kalit so'z tekshiruvi (case-insensitive substring)
    if tracked_post.keyword.lower() not in comment_text.lower():
        return  # Kalit so'z topilmadi — hech narsa qilmaymiz (xato emas)

    # 5-QADAM: Dublikat tekshiruvi — har bir foydalanuvchi 1 marta javob oladi
    existing_stmt = select(ReplyLog).where(
        ReplyLog.tracked_post_id == tracked_post.id,
        ReplyLog.ig_commenter_id == commenter_id,
    )
    existing = await db.execute(existing_stmt)
    if existing.scalar_one_or_none():
        return  # Avval javob olgan — takroriy yubormaymiz

    # 6-QADAM: Obuna matnli shaxsiy xabar yuborish (Private Reply)
    subscribe_message = (
        "Qiziqarli materialni (javobni) ko'rish uchun avval sahifamizga obuna bo'ling! ✅\n\n"
        "Obuna bo'lganingizdan so'ng, ushbu xabarga «Obuna bo'ldim» yoki «+» deb yozib javob qaytaring. Shundan so'ng sizga materiallar avtomatik yuboriladi."
    )

    try:
        result = await send_private_reply(
            ig_comment_id=comment_id,
            message_text=subscribe_message,
            access_token_encrypted=business.ig_access_token,
        )

        if result:
            # reply_log ga yozish — ON CONFLICT DO NOTHING
            insert_stmt = (
                pg_insert(ReplyLog)
                .values(
                    tracked_post_id=tracked_post.id,
                    ig_commenter_id=commenter_id,
                    subscribe_prompt_sent_at=datetime.now(timezone.utc),
                )
                .on_conflict_do_nothing(
                    constraint="uq_post_commenter"
                )
            )
            await db.execute(insert_stmt)
            await db.commit()
            logger.info(
                "Obuna prompt yuborildi: post=%s, user=%s",
                tracked_post.id,
                commenter_id,
            )
        else:
            await _log_error(
                db,
                business.id,
                "dm_send_failed",
                "Obuna prompt DM yuborishda xatolik",
                {"comment_id": comment_id, "commenter_id": commenter_id},
            )
    except Exception as e:
        logger.exception("DM yuborishda kutilmagan xato: %s", str(e))
        await _log_error(
            db,
            business.id,
            "dm_exception",
            str(e),
            {"comment_id": comment_id, "commenter_id": commenter_id},
        )


# ─── XABAR KELGANDA (INCOMING MESSAGE) ───────────────────────
async def _handle_incoming_message(msg_event: dict, db: AsyncSession) -> None:
    """
    7-QADAM: Foydalanuvchi Private Reply ga javob yozdi (tasdiqladi).
    - confirmed_at yangilanadi
    - post_responses kontentlari DM orqali yuboriladi
    - final_reply_sent_at yangilanadi
    """
    sender_id = msg_event.get("sender", {}).get("id", "")
    message_text = msg_event.get("message", {}).get("text", "")

    if not sender_id or not message_text:
        return

    # Kutilayotgan (javob yuborilmagan) reply_log larni topish
    log_stmt = (
        select(ReplyLog)
        .where(
            ReplyLog.ig_commenter_id == sender_id,
            ReplyLog.final_reply_sent_at.is_(None)
        )
        .order_by(ReplyLog.id.desc())
    )
    result = await db.execute(log_stmt)
    pending_logs = result.scalars().all()

    if not pending_logs:
        return

    for reply_log in pending_logs:
        # confirmed_at ni yangilash
        reply_log.confirmed_at = datetime.now(timezone.utc)
        tracked_post_id = reply_log.tracked_post_id

    # tracked_post va business ma'lumotlarini olish
    post_stmt = (
        select(TrackedPost)
        .where(TrackedPost.id == tracked_post_id)
    )
    post_result = await db.execute(post_stmt)
    tracked_post = post_result.scalar_one_or_none()

    if not tracked_post:
        return

    biz_stmt = select(Business).where(Business.id == tracked_post.business_id)
    biz_result = await db.execute(biz_stmt)
    business = biz_result.scalar_one_or_none()

    if not business or not business.ig_access_token:
        return

    # post_responses ni sort_order bo'yicha olish
    resp_stmt = (
        select(PostResponse)
        .where(PostResponse.tracked_post_id == tracked_post_id)
        .order_by(PostResponse.sort_order)
    )
    resp_result = await db.execute(resp_stmt)
    responses = resp_result.scalars().all()

    # Kontentlarni ketma-ket DM orqali yuborish
    all_sent = True
    for resp in responses:
        send_result = None
        if resp.content_type == "text":
            send_result = await send_dm_text(
                ig_user_id=sender_id,
                message_text=resp.content_value,
                access_token_encrypted=business.ig_access_token,
            )
        elif resp.content_type == "image":
            send_result = await send_dm_image(
                ig_user_id=sender_id,
                image_url=resp.content_value,
                access_token_encrypted=business.ig_access_token,
            )
        elif resp.content_type == "link":
            send_result = await send_dm_text(
                ig_user_id=sender_id,
                message_text=resp.content_value,
                access_token_encrypted=business.ig_access_token,
            )

        if not send_result:
            all_sent = False
            logger.error(
                "Javob yuborilmadi: post=%s, type=%s",
                tracked_post_id,
                resp.content_type,
            )

    for reply_log in pending_logs:
        reply_log.final_reply_sent_at = datetime.now(timezone.utc)
        logger.info(
            "Barcha javoblar yuborildi: user=%s",
            sender_id,
        )

    await db.commit()


# ─── XATO LOGLASH ────────────────────────────────────────────
async def _log_error(
    db: AsyncSession,
    business_id: int,
    error_type: str,
    error_message: str,
    context: dict | None = None,
) -> None:
    """error_log jadvaliga xato yozish."""
    try:
        error = ErrorLog(
            business_id=business_id,
            error_type=error_type,
            error_message=error_message,
            context=context,
        )
        db.add(error)
        await db.commit()
    except Exception:
        logger.exception("error_log ga yozishda xato")
