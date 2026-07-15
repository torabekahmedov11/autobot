"""OAuth Callback Endpoint."""

import secrets
from datetime import datetime, timezone, timedelta

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from app.config import get_settings
from app.database import async_session
from app.models import Business
from app.utils.logger import logger

router = APIRouter(prefix="/auth", tags=["auth"])


def _safe_encrypt(token: str) -> str:
    """Token'ni shifrlaydi agar ENCRYPTION_KEY mavjud bo'lsa, aks holda oddiy saqlaydi."""
    settings = get_settings()
    key = settings.ENCRYPTION_KEY or settings.FERNET_KEY
    if key:
        try:
            from cryptography.fernet import Fernet
            cipher = Fernet(key.encode())
            return cipher.encrypt(token.encode()).decode()
        except Exception as e:
            logger.warning("Encrypt xatosi, token ochiq saqlanmoqda: %s", str(e))
    return token


async def _get_instagram_account_id(access_token: str) -> str | None:
    """Facebook Graph API orqali bog'langan Instagram akkaunt ID sini topish."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            url_pages = "https://graph.facebook.com/v21.0/me/accounts"
            params = {"access_token": access_token}
            resp_pages = await client.get(url_pages, params=params)

            if resp_pages.status_code != 200:
                logger.error("Pages fetching error: %s", resp_pages.text)
                return None

            pages = resp_pages.json().get("data", [])

            for page in pages:
                page_id = page.get("id")
                page_token = page.get("access_token")

                url_ig = f"https://graph.facebook.com/v21.0/{page_id}"
                params_ig = {
                    "fields": "instagram_business_account",
                    "access_token": page_token,
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
):
    """Facebook OAuth jarayonidan keyin foydalanuvchi qaytadigan manzil."""
    # Xatolarni tekshirish
    if error:
        logger.error("OAuth xatosi: %s - %s", error, error_description)
        return HTMLResponse(
            "<html><body style='font-family:sans-serif;text-align:center;margin-top:50px;'>"
            f"<h2 style='color:red;'>Xatolik: {error_description or error}</h2>"
            "<p>Telegram botga qaytib, qaytadan urinib ko'ring.</p>"
            "</body></html>",
            status_code=400,
        )

    if not code or not state:
        return HTMLResponse(
            "<html><body style='font-family:sans-serif;text-align:center;margin-top:50px;'>"
            "<h2 style='color:red;'>Noto'g'ri so'rov</h2>"
            "<p>code yoki state parametri yetishmayapti.</p>"
            "</body></html>",
            status_code=400,
        )

    try:
        telegram_id = int(state)
    except (ValueError, TypeError):
        return HTMLResponse(
            "<html><body style='font-family:sans-serif;text-align:center;margin-top:50px;'>"
            "<h2 style='color:red;'>Noto'g'ri identifikator</h2>"
            "</body></html>",
            status_code=400,
        )

    settings = get_settings()
    base_url = settings.RENDER_URL or "https://autobot-yqnm.onrender.com"
    redirect_uri = f"{base_url}/auth/callback"

    try:
        # 1. Code → short-lived access token
        async with httpx.AsyncClient(timeout=15) as client:
            token_url = "https://graph.facebook.com/v21.0/oauth/access_token"
            params = {
                "client_id": settings.IG_APP_ID,
                "redirect_uri": redirect_uri,
                "client_secret": settings.IG_APP_SECRET,
                "code": code,
            }
            resp = await client.get(token_url, params=params)

            if resp.status_code != 200:
                logger.error("Token olishda xato: status=%s body=%s", resp.status_code, resp.text)
                return HTMLResponse(
                    "<html><body style='font-family:sans-serif;text-align:center;margin-top:50px;'>"
                    "<h2 style='color:red;'>Facebook'dan token olishda xatolik</h2>"
                    f"<p>{resp.text[:200]}</p>"
                    "</body></html>",
                    status_code=502,
                )

            data = resp.json()
            short_token = data.get("access_token")

            if not short_token:
                logger.error("Access token olinmadi: %s", data)
                return HTMLResponse(
                    "<html><body style='font-family:sans-serif;text-align:center;margin-top:50px;'>"
                    "<h2 style='color:red;'>Access token olinmadi</h2>"
                    "</body></html>",
                    status_code=502,
                )

            # 2. Short-lived → long-lived token
            ll_url = "https://graph.facebook.com/v21.0/oauth/access_token"
            ll_params = {
                "grant_type": "fb_exchange_token",
                "client_id": settings.IG_APP_ID,
                "client_secret": settings.IG_APP_SECRET,
                "fb_exchange_token": short_token,
            }
            ll_resp = await client.get(ll_url, params=ll_params)

            token_to_save = short_token
            expires_in = 5184000  # 60 kun

            if ll_resp.status_code == 200:
                ll_data = ll_resp.json()
                token_to_save = ll_data.get("access_token", short_token)
                expires_in = ll_data.get("expires_in", 5184000)
            else:
                logger.warning("Long-lived token olinmadi, short token saqlanmoqda")

        # 3. Instagram Business Account ID
        ig_account_id = await _get_instagram_account_id(token_to_save)
        logger.info("Instagram Account ID: %s", ig_account_id)

        # 4. Bazaga yozish
        encrypted_token = _safe_encrypt(token_to_save)

        async with async_session() as db:
            stmt = select(Business).where(Business.owner_telegram_id == telegram_id)
            result = await db.execute(stmt)
            business = result.scalar_one_or_none()

            if business:
                business.ig_access_token = encrypted_token
                business.ig_token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
                business.is_active = True
                if ig_account_id:
                    business.ig_business_account_id = ig_account_id
            else:
                business = Business(
                    owner_telegram_id=telegram_id,
                    business_name=f"User {telegram_id}",
                    ig_business_account_id=ig_account_id or "",
                    ig_access_token=encrypted_token,
                    ig_token_expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
                    license_key=secrets.token_hex(32),
                    is_active=True,
                )
                db.add(business)

            await db.commit()

        logger.info("✅ OAuth muvaffaqiyatli — Telegram ID: %s, IG Account: %s", telegram_id, ig_account_id)

        return HTMLResponse(
            "<html><body style='font-family:sans-serif;text-align:center;margin-top:50px;"
            "background:#f0fdf4;'>"
            "<div style='max-width:500px;margin:auto;padding:40px;background:white;"
            "border-radius:16px;box-shadow:0 4px 20px rgba(0,0,0,0.1);'>"
            "<h1 style='color:#16a34a;font-size:48px;margin:0;'>✅</h1>"
            "<h2 style='color:#16a34a;'>Instagram muvaffaqiyatli ulandi!</h2>"
            "<p style='color:#666;'>Endi Telegram botga qaytib, <b>/start</b> buyrug'ini yuboring.</p>"
            "</div></body></html>"
        )

    except Exception as e:
        logger.exception("OAuth callback umumiy xato: %s", str(e))
        return HTMLResponse(
            "<html><body style='font-family:sans-serif;text-align:center;margin-top:50px;'>"
            "<h2 style='color:red;'>Serverda xatolik yuz berdi</h2>"
            f"<p>{str(e)[:200]}</p>"
            "</body></html>",
            status_code=500,
        )
