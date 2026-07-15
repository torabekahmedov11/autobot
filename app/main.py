"""FastAPI — asosiy dastur fayli. main.py"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from sqlalchemy import text

from app.config import get_settings
from app.database import engine, async_session
from app.telegram_bot.bot import bot, dp
from app.webhooks.instagram_webhook import router as webhook_router
from app.utils.logger import logger


# ─── TOKEN YANGILASH TASK ─────────────────────────────────────
async def _token_refresh_loop():
    """
    Kunlik token yangilash task — Instagram token muddati
    tugashiga 5 kun qolganda avtomatik yangilaydi.
    """
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import select, update
    from app.models import Business
    import httpx

    settings = get_settings()

    while True:
        try:
            async with async_session() as db:
                # Token muddati 5 kundan kam qolgan bizneslarni topish
                threshold = datetime.now(timezone.utc) + timedelta(days=5)
                stmt = select(Business).where(
                    Business.ig_token_expires_at.isnot(None),
                    Business.ig_token_expires_at < threshold,
                    Business.is_active == True,  # noqa: E712
                )
                result = await db.execute(stmt)
                businesses = result.scalars().all()

                for biz in businesses:
                    try:
                        from app.services.crypto import decrypt_token, encrypt_token

                        old_token = decrypt_token(biz.ig_access_token)
                        url = (
                            f"https://graph.facebook.com/v21.0/oauth/access_token"
                            f"?grant_type=fb_exchange_token"
                            f"&client_id={settings.IG_APP_ID}"
                            f"&client_secret={settings.IG_APP_SECRET}"
                            f"&fb_exchange_token={old_token}"
                        )
                        async with httpx.AsyncClient(timeout=15) as client:
                            resp = await client.get(url)
                            if resp.status_code == 200:
                                data = resp.json()
                                new_token = data["access_token"]
                                expires_in = data.get("expires_in", 5184000)  # ~60 kun

                                biz.ig_access_token = encrypt_token(new_token)
                                biz.ig_token_expires_at = datetime.now(
                                    timezone.utc
                                ) + timedelta(seconds=expires_in)
                                await db.commit()
                                logger.info(
                                    "Token yangilandi: business=%s", biz.id
                                )
                            else:
                                logger.error(
                                    "Token yangilash xatosi: business=%s, status=%s",
                                    biz.id,
                                    resp.status_code,
                                )
                    except Exception as e:
                        logger.exception(
                            "Token yangilashda xato: business=%s, error=%s",
                            biz.id,
                            str(e),
                        )
        except Exception as e:
            logger.exception("Token refresh loop xatosi: %s", str(e))

        # 24 soatdan keyin qayta tekshirish
        await asyncio.sleep(86400)


# ─── LIFESPAN ─────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Dastur ishga tushganda va to'xtalganda."""
    settings = get_settings()

    # Faqat eng muhim o'zgaruvchilarni tekshirish
    required_vars = {
        "DATABASE_URL": settings.DATABASE_URL,
        "TELEGRAM_BOT_TOKEN": settings.TELEGRAM_BOT_TOKEN,
        "IG_APP_ID": settings.IG_APP_ID,
        "IG_APP_SECRET": settings.IG_APP_SECRET,
    }
    for var_name, var_value in required_vars.items():
        if not var_value:
            raise RuntimeError(
                f"❌ MUHIM: {var_name} environment o'zgaruvchisi topilmadi! "
                f".env faylingizni tekshiring."
            )
    # Ixtiyoriy o'zgaruvchilar tekshiruvi (xato chiqarmaydi)
    if not settings.IG_VERIFY_TOKEN:
        logger.warning("⚠️  IG_VERIFY_TOKEN belgilanmagan — webhook verify ishlamaydi.")
    if not settings.ENCRYPTION_KEY:
        logger.warning("⚠️  ENCRYPTION_KEY belgilanmagan — token shifrlash ishlamaydi.")

    logger.info("🚀 Instagram Auto-DM Bot ishga tushmoqda...")

    # Telegram bot polling (alohida task)
    polling_task = asyncio.create_task(dp.start_polling(bot))

    # Token yangilash task
    refresh_task = asyncio.create_task(_token_refresh_loop())

    logger.info("✅ Bot ishga tushdi!")
    yield

    # Dastur to'xtashi
    logger.info("Bot to'xtayapti...")
    polling_task.cancel()
    refresh_task.cancel()
    await bot.session.close()
    await engine.dispose()


# ─── FASTAPI APP ──────────────────────────────────────────────
app = FastAPI(
    title="Instagram Auto-DM Bot",
    description="Instagram izohlariga kalit so'z bo'yicha avtomatik DM yuborish tizimi",
    version="1.0.0",
    lifespan=lifespan,
)

# Router'larni ulash
app.include_router(webhook_router)


# ─── HEALTH CHECK ─────────────────────────────────────────────
@app.get("/health")
async def health_check():
    """Server + baza ulanish holatini tekshirish."""
    db_ok = False
    try:
        async with async_session() as db:
            await db.execute(text("SELECT 1"))
            db_ok = True
    except Exception as e:
        logger.error("Health check baza xatosi: %s", str(e))

    status = "healthy" if db_ok else "unhealthy"
    status_code = 200 if db_ok else 503

    return Response(
        content=f'{{"status": "{status}", "database": {str(db_ok).lower()}}}',
        media_type="application/json",
        status_code=status_code,
    )
