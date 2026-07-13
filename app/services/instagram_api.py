"""Instagram Graph API bilan ishlash servisi.

04_XATOLAR_VA_XAVFSIZLIK.md bo'yicha:
- Har bir API chaqiruvi try/except bilan o'ralgan
- 429 rate limit → exponential backoff (max 3 urinish)
- Barcha xatolar loglangan
"""

import asyncio

import httpx

from app.services.crypto import decrypt_token
from app.utils.logger import logger

GRAPH_API_BASE = "https://graph.facebook.com/v21.0"

# Rate limit retry sozlamalari
MAX_RETRIES = 3
INITIAL_BACKOFF = 2  # sekund


async def _api_request(
    method: str,
    url: str,
    payload: dict,
    retry_count: int = 0,
) -> dict | None:
    """
    Instagram API ga so'rov yuborish — retry va error handling bilan.

    - 429 (rate limit) → exponential backoff, max 3 marta
    - Boshqa xatolar → log qilib None qaytarish
    - Exception → log qilib None qaytarish
    """
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            if method == "POST":
                resp = await client.post(url, json=payload)
            else:
                resp = await client.get(url, params=payload)

            # 429 Rate Limit — exponential backoff
            if resp.status_code == 429 and retry_count < MAX_RETRIES:
                wait_time = INITIAL_BACKOFF * (2 ** retry_count)
                logger.warning(
                    "Instagram API 429 rate limit. %s-urinish, %s sek kutilmoqda...",
                    retry_count + 1,
                    wait_time,
                )
                await asyncio.sleep(wait_time)
                return await _api_request(method, url, payload, retry_count + 1)

            if resp.status_code != 200:
                logger.error(
                    "Instagram API xatosi: status=%s, body=%s, url=%s",
                    resp.status_code,
                    resp.text[:200],
                    url,
                )
                return None

            return resp.json()

    except httpx.TimeoutException:
        logger.error("Instagram API timeout: url=%s", url)
        return None
    except Exception as e:
        logger.exception("Instagram API kutilmagan xato: %s", str(e))
        return None


async def send_private_reply(
    ig_comment_id: str,
    message_text: str,
    access_token_encrypted: str,
) -> dict | None:
    """
    Instagram Private Reply API orqali izoh egasiga DM yuboradi.
    Bu — izohga javob emas, shaxsiy xabar (DM).
    """
    access_token = decrypt_token(access_token_encrypted)
    url = f"{GRAPH_API_BASE}/me/messages"
    payload = {
        "recipient": {"comment_id": ig_comment_id},
        "message": {"text": message_text},
        "access_token": access_token,
    }
    return await _api_request("POST", url, payload)


async def send_dm_text(
    ig_user_id: str,
    message_text: str,
    access_token_encrypted: str,
) -> dict | None:
    """Oddiy DM matn xabar yuborish."""
    access_token = decrypt_token(access_token_encrypted)
    url = f"{GRAPH_API_BASE}/me/messages"
    payload = {
        "recipient": {"id": ig_user_id},
        "message": {"text": message_text},
        "access_token": access_token,
    }
    return await _api_request("POST", url, payload)


async def send_dm_image(
    ig_user_id: str,
    image_url: str,
    access_token_encrypted: str,
) -> dict | None:
    """DM orqali rasm yuborish."""
    access_token = decrypt_token(access_token_encrypted)
    url = f"{GRAPH_API_BASE}/me/messages"
    payload = {
        "recipient": {"id": ig_user_id},
        "message": {
            "attachment": {
                "type": "image",
                "payload": {"url": image_url},
            }
        },
        "access_token": access_token,
    }
    return await _api_request("POST", url, payload)


async def send_dm_with_button(
    ig_comment_id: str,
    message_text: str,
    button_title: str,
    button_payload: str,
    access_token_encrypted: str,
) -> dict | None:
    """
    DM orqali xabar + tugma yuborish (Private Reply).
    send_subscribe_prompt uchun ishlatiladi — bu HAQIQIY obuna
    tekshiruvi EMAS, faqat foydalanuvchidan soft-check so'rash.
    """
    access_token = decrypt_token(access_token_encrypted)
    url = f"{GRAPH_API_BASE}/me/messages"
    payload = {
        "recipient": {"comment_id": ig_comment_id},
        "message": {
            "text": message_text,
            "quick_replies": [
                {
                    "content_type": "text",
                    "title": button_title,
                    "payload": button_payload,
                }
            ],
        },
        "access_token": access_token,
    }
    return await _api_request("POST", url, payload)
