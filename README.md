# Instagram Auto-DM Bot 🤖

Instagram'da post/video'ga izoh qoldirgan foydalanuvchilarga, izohda kalit so'z bo'lsa, avtomatik DM (shaxsiy xabar) yuboradigan tizim. Boshqaruv Telegram bot orqali.

## Texnologiyalar

- **Python 3.11+**
- **FastAPI** — webhook server
- **PostgreSQL** — ma'lumotlar bazasi
- **SQLAlchemy 2.0 (async)** — ORM
- **Aiogram 3.x** — Telegram bot
- **Instagram Graph API** — DM yuborish
- **Alembic** — migratsiyalar

## Tez boshlash (Local)

### 1. Reponi klonlash
```bash
git clone https://github.com/username/instagram-autobot.git
cd instagram-autobot
```

### 2. Virtual environment
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

### 3. Kutubxonalar o'rnatish
```bash
pip install -r requirements.txt
```

### 4. Environment sozlamalari
```bash
cp .env.example .env
# .env faylni to'ldiring
```

### 5. Bazani yaratish
```bash
alembic upgrade head
```

### 6. Serverni ishga tushirish
```bash
uvicorn app.main:app --reload
```

## Deploy (Render.com)

### 1. Render.com da yangi Web Service yarating
- Repo ulang
- `render.yaml` orqali avtomatik sozlanadi

### 2. Environment Variables sozlang
Render Dashboard → Environment tab:
- `TELEGRAM_BOT_TOKEN` — @BotFather dan olingan token
- `IG_APP_ID` — Meta Developer App ID
- `IG_APP_SECRET` — Meta Developer App Secret
- `IG_VERIFY_TOKEN` — o'zingiz belgilagan webhook verify token
- `ENCRYPTION_KEY` — Fernet kalit (generatsiya: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`)
- `LICENSE_MASTER_KEY` — litsenziya uchun master kalit

### 3. PostgreSQL baza
Render avtomatik bepul PostgreSQL yaratadi (`render.yaml` da ko'rsatilgan).

## Instagram Webhook Sozlash

### 1. Meta Developer Console
1. https://developers.facebook.com ga kiring
2. Yangi App yarating (yoki mavjudini oching)
3. **App Review** → kerakli ruxsatlarni so'rang:
   - `instagram_basic`
   - `instagram_manage_comments`
   - `instagram_manage_messages`
   - `pages_manage_metadata`
   - `pages_show_list`

### 2. Webhook qo'shish
1. App Dashboard → Webhooks bo'limiga o'ting
2. **Instagram** ni tanlang
3. **Callback URL**: `https://your-app.onrender.com/webhook/instagram`
4. **Verify Token**: `.env` dagi `IG_VERIFY_TOKEN` bilan bir xil
5. **Subscribe** tugmasini bosing
6. `comments` va `messages` field'larini tanlang

### 3. Instagram Business Account ulash
1. Telegram botga `/start` buyrug'ini yuboring
2. "Instagram ulash" tugmasini bosing
3. Facebook/Instagram akkauntingiz bilan kiring
4. Ruxsatlarni bering

## Server "Uxlab Qolishi" Muammosi ⚠️

Render.com bepul tierda server 15 daqiqa faoliyatsiz bo'lsa "uxlab qoladi". Webhook'lar shu paytda kelmaydi.

### Yechim: UptimeRobot
1. https://uptimerobot.com ga ro'yxatdan o'ting (bepul)
2. Yangi monitor qo'shing:
   - **Monitor Type**: HTTP(s)
   - **URL**: `https://your-app.onrender.com/health`
   - **Monitoring Interval**: 5 minutes
3. Bu serverni har 5 daqiqada "ping" qilib, uxlab qolishiga yo'l qo'ymaydi

## Loyiha Tuzilishi

```
instagram-autobot/
├── app/
│   ├── main.py              # FastAPI asosiy fayl
│   ├── config.py             # Sozlamalar (.env)
│   ├── database.py           # Async SQLAlchemy engine
│   ├── models.py             # 5 ta jadval modellari
│   ├── webhooks/
│   │   └── instagram_webhook.py  # Webhook handler
│   ├── services/
│   │   ├── instagram_api.py  # Instagram DM yuborish
│   │   └── crypto.py         # Token shifrlash
│   ├── telegram_bot/
│   │   ├── bot.py            # Bot va Dispatcher
│   │   └── handlers/
│   │       ├── setup.py      # /start, OAuth
│   │       ├── posts.py      # Post qo'shish (FSM)
│   │       └── admin.py      # Postlarni boshqarish
│   └── utils/
│       └── logger.py         # Markaziy logger
├── alembic/                  # Migratsiyalar
├── .env.example              # Env namuna
├── .gitignore
├── requirements.txt
├── render.yaml               # Render.com deploy
└── README.md
```

## Litsenziya

MIT
