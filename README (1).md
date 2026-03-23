# Telegram ERP — Tikuvchilik Sexi

Python · aiogram 3.x · PostgreSQL · Redis · Railway

---

## GitHub + Railway orqali ishga tushirish

### 1. GitHub repo yaratish

```bash
git init
git add .
git commit -m "initial commit"
git branch -M main
git remote add origin https://github.com/USERNAME/telegram-erp.git
git push -u origin main
```

---

### 2. Railway loyiha yaratish

1. [railway.app](https://railway.app) → **New Project**
2. **Deploy from GitHub repo** → reponi tanlang
3. Railway `Dockerfile` ni o'zi topadi ✅

---

### 3. Railway pluginlari qo'shish

Dashboard → **+ Add Service**:

| Plugin | Nima uchun |
|--------|-----------|
| **PostgreSQL** | Asosiy baza |
| **Redis** | Bot FSM holatlari |

Pluginlar qo'shilgandan so'ng `DATABASE_URL` va `REDIS_URL` avtomatik ulanadi.

---

### 4. Environment variables

Railway → Bot servisi → **Variables**:

```
BOT_TOKEN   = 7123456789:AAHxxxx...    ← BotFather dan oling
ADMIN_IDS   = 123456789                ← Sizning Telegram ID
```

`DATABASE_URL` va `REDIS_URL` ni **yozmang** — Railway o'zi ulaydi.

---

### 5. Deploy

Har safar `main` ga push qilsangiz Railway avtomatik qayta deploy qiladi.

```bash
git add .
git commit -m "update"
git push
```

Deploy jarayoni:
1. 🐳 Docker image build
2. 🗄 `alembic upgrade head` — migratsiyalar
3. 🤖 `python main.py` — bot ishga tushadi

---

## Lokal ishlatish

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # BOT_TOKEN ni to'ldiring
docker-compose up -d db redis  # PostgreSQL + Redis
alembic upgrade head           # Jadvallar yaratish
python main.py                 # Botni ishga tushirish
```

---

## Admin buyruqlari

| Buyruq | Tavsif |
|--------|--------|
| `/start` | Botni boshlash |
| `/setrole <telegram_id>` | Xodimga rol berish |
| `/neworder` | Yangi zakaz ochish |
| `/report_daily` | Bugungi natijalar |
| `/report_orders` | Zakazlar holati |
| `/report_balances` | Xodimlar balanslari |
