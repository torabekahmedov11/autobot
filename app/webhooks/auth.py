"""OAuth Callback Endpoint."""

import secrets
from datetime import datetime, timezone, timedelta

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models import Business
from app.services.crypto import encrypt_token
from app.utils.logger import logger

router = APIRouter(prefix="/auth", tags=["auth"])


async def _get_instagram_account_id(access_token: str) -> str | None:
    """Facebook Graph API orqali bog'langan Instagram akkaunt ID sini topish."""
    try:
        async with httpx.AsyncClient() as client:
            # 1. Barcha sahifalarni (pages) olish
            url_pages = "https://graph.facebook.com/v21.0/me/accounts"
            params = {"access_token": access_token}
            resp_pages = await client.get(url_pages, params=params)
            
            if resp_pages.status_code != 200:
                logger.error("Pages fetching error: %s", resp_pages.text)
                return None
                
            pages = resp_pages.json().get("data", [])
            
            # 2. Xar bir sahifa uchun instagram_business_account mavjudligini tekshirish
            for page in pages:
                page_id = page.get("id")
                page_token = page.get("access_token")
                
                url_ig = f"https://graph.facebook.com/v21.0/{page_id}"
                params_ig = {
                    "fields": "instagram_business_account",
                    "access_token": page_token
                }
                resp_ig = await client.get(url_ig, params=params_ig)
                if resp_ig.status_code == 200:
                    data_ig = resp_ig.json()
                    ig_account = data_ig.get("instagram_business_account")
                    if ig_account and "id" in ig_account:
                        return ig_account["id"]
                        
    except Exception as e:
        logger.exception("Instagram account qidirishda xato: %s", str(e))
        
    return None


@router.get("/callback")
async def oauth_callback(
    request: Request,
    code: str = None,
    state: str = None,
    error: str = None,
    error_reason: str = None,
    error_description: str = None,
    db: AsyncSession = Depends(get_db)
):
    """Facebook OAuth jarayonidan keyin foydalanuvchi qaytadigan manzil."""
    if error:
        logger.error("OAuth xatosi: %s - %s", error, error_description)
        return HTMLResponse(f"<h3>Xatolik yuz berdi: {error_description}</h3>")
    
    if not code or not state:
        return HTMLResponse("<h3>Noto'g'ri so'rov (code yoki state yetishmayapti).</h3>")

    try:
        telegram_id = int(state)
    except ValueError:
        return HTMLResponse("<h3>Noto'g'ri identifikator (state formati xato).</h3>")

    settings = get_settings()
    base_url = getattr(settings, "RENDER_URL", "https://autobot-yqnm.onrender.com")
    redirect_uri = f"{base_url}/auth/callback"

    # 1. Code'ni short-lived token'ga almashtirish
    async with httpx.AsyncClient() as client:
        token_url = "https://graph.facebook.com/v21.0/oauth/access_token"
        params = {
            "client_id": settings.IG_APP_ID,
            "redirect_uri": redirect_uri,
            "client_secret": settings.IG_APP_SECRET,
            "code": code
        }
        resp = await client.get(token_url, params=params)
        
        if resp.status_code != 200:
            logger.error("Token olishda xato: %s", resp.text)
            return HTMLResponse("<h3>Facebook'dan tokenni olishda xatolik yuz berdi.</h3>")
        
        data = resp.json()
        short_token = data.get("access_token")

        if not short_token:
            return HTMLResponse("<h3>Access token olinmadi.</h3>")

        # 2. Short-lived tokenni long-lived token'ga aylantirish
        ll_url = "https://graph.facebook.com/v21.0/oauth/access_token"
        ll_params = {
            "grant_type": "fb_exchange_token",
            "client_id": settings.IG_APP_ID,
            "client_secret": settings.IG_APP_SECRET,
            "fb_exchange_token": short_token
        }
        ll_resp = await client.get(ll_url, params=ll_params)
        
        token_to_save = short_token
        expires_in = 5184000  # Default 60 kun
        
        if ll_resp.status_code == 200:
            ll_data = ll_resp.json()
            token_to_save = ll_data.get("access_token", short_token)
            expires_in = ll_data.get("expires_in", 5184000)

    # 3. Instagram Business Account ID'ni avtomatik olishga urinish
    ig_account_id = await _get_instagram_account_id(token_to_save)

    # 4. Bazaga yozish (yangi Business yaratiladi yoki bor bo'lsa yangilanadi)
    stmt = select(Business).where(Business.owner_telegram_id == telegram_id)
    result = await db.execute(stmt)
    business = result.scalar_one_or_none()
    
    if business:
        # Yangilash
        business.ig_access_token = encrypt_token(token_to_save)
        business.ig_token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        business.is_active = True
        if ig_account_id:
            business.ig_business_account_id = ig_account_id
    else:
        # Yangi foydalanuvchini yaratish
        business = Business(
            owner_telegram_id=telegram_id,
            business_name=f"User {telegram_id}",
            ig_business_account_id=ig_account_id or settings.IG_BUSINESS_ACCOUNT_ID,
            ig_access_token=encrypt_token(token_to_save),
            ig_token_expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
            license_key=secrets.token_hex(32),
            is_active=True
        )
        db.add(business)
        
    await db.commit()
    logger.info("OAuth muvaffaqiyatli yakunlandi - Telegram ID: %s", telegram_id)
    
    return HTMLResponse(
        "<html><body style='font-family: sans-serif; text-align: center; margin-top: 50px;'>"
        "<h2 style='color: green;'>Instagram akkaunt muvaffaqiyatli ulandi! ✅</h2>"
        "<p>Endi Telegram botga qaytib, oyna orqali boshqarishda davom etishingiz mumkin.</p>"
        "</body></html>"
    )
