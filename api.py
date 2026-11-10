# ==============================================================================
# LOYIHA: UzbekCats Bot & Web App
# FAYL: api.py
# TAVSIF: FastAPI Backend (Web App uchun to'liq mukammal API)
# ==============================================================================

import hmac
import hashlib
import json
import os
import urllib.parse
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Depends, Header, UploadFile, File, Form, status, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import uvicorn
import logging

# Telethon (Userbot qo'shish uchun)
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError

# O'zimizning fayllar
from config import BotConfig, Settings, Prices, DataLists, WebAppConfig
from db import db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==============================================================================
# FASTAPI SOZLAMALARI
# ==============================================================================

app = FastAPI(
    title="UzbekCats API",
    description="Telegram Web App va Bot uchun Backend API",
    version="1.0.0"
)

# CORS (Frontend GitHub Pages'da bo'lgani uchun barcha domenlarga ruxsat beramiz)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Yuklangan rasmlar (cheklar) saqlanadigan papka
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


# ==============================================================================
# PYDANTIC MODELLARI (Ma'lumotlarni tekshirish uchun)
# ==============================================================================

class TelegramAuthRequest(BaseModel):
    init_data: str
    user: dict


class AdCreateRequest(BaseModel):
    tariff: str
    cat_count: int
    photos: List[str]
    breed: str
    age: str
    gender: str
    health: str
    sterilization: str
    address: str
    phone: str
    price: str
    currency: str
    title: str
    description: Optional[str] = None


class TopUpRequest(BaseModel):
    amount: int


class AddCardRequest(BaseModel):
    number: str
    holder: str


class UserbotRequestCode(BaseModel):
    phone: str


class UserbotVerifyCode(BaseModel):
    phone: str
    code: str
    password: Optional[str] = None


class AdminActionRequest(BaseModel):
    telegram_id: int
    amount: Optional[int] = None
    reason: Optional[str] = None


class AdminAddScoreRequest(BaseModel):
    phone: str
    score: int


# ==============================================================================
# XAVFSIZLIK VA AUTENTIFIKATSIYA
# ==============================================================================

def verify_telegram_webapp_data(init_data: str) -> dict:
    """Telegram Web App'dan kelgan ma'lumotlarni HMAC-SHA256 orqali tekshiradi."""
    try:
        parsed_data = dict(urllib.parse.parse_qsl(init_data))
        if "hash" not in parsed_data:
            raise HTTPException(status_code=401, detail="Invalid initData: hash missing")

        received_hash = parsed_data.pop("hash")
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed_data.items()))

        secret_key = hmac.new(
            b"WebAppData",
            BotConfig.BOT_TOKEN.encode(),
            hashlib.sha256
        ).digest()

        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256
        ).hexdigest()

        if calculated_hash != received_hash:
            raise HTTPException(status_code=401, detail="Invalid initData: hash mismatch")

        user_data = json.loads(parsed_data.get("user", "{}"))
        return user_data
    except Exception as e:
        logger.error(f"Auth xatosi: {e}")
        raise HTTPException(status_code=401, detail="Avtorizatsiyadan o'tilmadi")


async def get_current_user(x_telegram_init_data: str = Header(None)):
    """Header orqali kelgan foydalanuvchini aniqlaydi va bazadan qidiradi."""
    if not x_telegram_init_data:
        raise HTTPException(status_code=401, detail="Telegram ma'lumotlari topilmadi")

    user_data = verify_telegram_webapp_data(x_telegram_init_data)
    user_id = user_data.get("id")

    if not user_id:
        raise HTTPException(status_code=401, detail="Foydalanuvchi ID topilmadi")

    user = await db.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Foydalanuvchi bazadan topilmadi. Iltimos botga /start bosing.")
    return user


async def check_admin(current_user: dict = Depends(get_current_user)):
    """Faqat adminlarga ruxsat berish."""
    if current_user['id'] not in BotConfig.ADMIN_IDS and not current_user.get('is_admin'):
        raise HTTPException(status_code=403, detail="Siz admin emassiz!")
    return current_user


# ==============================================================================
# 1. AUTENTIFIKATSIYA VA FOYDALANUVCHI
# ==============================================================================

@app.post("/api/auth/telegram")
async def auth_telegram(req: TelegramAuthRequest):
    """Frontend ochilganda foydalanuvchini tekshirish va bazaga ulash."""
    user = await db.get_user(req.user['id'])
    if not user:
        raise HTTPException(404, "Foydalanuvchi topilmadi. Botga kirib /start bosing.")

    return {
        "access_token": req.init_data,
        "user": {
            "telegram_id": user["id"],
            "user_number": user["user_number"],
            "first_name": user["full_name"].split()[0] if user["full_name"] else "",
            "last_name": " ".join(user["full_name"].split()[1:]) if user["full_name"] and len(
                user["full_name"].split()) > 1 else "",
            "username": user["username"].replace("@", "") if user["username"] else None,
            "phone": user["phone"],
            "balance": user["balance"],
            "score": user["score"],
            "is_admin": user["id"] in BotConfig.ADMIN_IDS or user.get("is_admin", False)
        }
    }


@app.get("/api/user/me")
async def get_me(user: dict = Depends(get_current_user)):
    """Profil sahifasi uchun joriy foydalanuvchi ma'lumotlari."""
    return {
        "id": user["id"],
        "user_number": user["user_number"],
        "full_name": user["full_name"],
        "username": user["username"],
        "phone": user["phone"],
        "balance": user["balance"],
        "score": user["score"],
        "is_admin": user["id"] in BotConfig.ADMIN_IDS or user.get("is_admin", False)
    }


@app.get("/api/user/ads")
async def get_my_ads(user: dict = Depends(get_current_user)):
    """Foydalanuvchining o'z reklamalari ro'yxati."""
    return await db.get_user_ads(user["id"])


# ==============================================================================
# 2. REKLAMALAR VA KONKURS
# ==============================================================================

@app.get("/api/ads")
async def get_active_ads():
    """Asosiy sahifa uchun faol (Web) reklamalar."""
    await db.cleanup_expired_ads()  # Muddati o'tganlarni tozalash
    return await db.get_active_web_ads()


@app.post("/api/ads")
async def create_ad(req: AdCreateRequest, user: dict = Depends(get_current_user)):
    """Web App orqali yangi reklama joylash va balansdan pul yechish."""
    # Narxni hisoblash
    count_idx = min(req.cat_count, 5)
    price = 0
    if req.tariff == "web_only":
        price = Prices.TARIFF_WEB[count_idx]
    elif req.tariff == "channel_only":
        price = Prices.TARIFF_CHANNEL[count_idx]
    elif req.tariff == "web_and_channel":
        price = Prices.TARIFF_BOTH[count_idx]
    else:
        raise HTTPException(400, "Noto'g'ri tarif")

    # Balansni tekshirish va yechish
    if user["balance"] < price:
        raise HTTPException(status_code=402, detail="Balansda mablag' yetarli emas!")

    try:
        await db.update_user_balance(user["id"], price, operation='subtract')
    except ValueError:
        raise HTTPException(status_code=402, detail="Mablag' yechishda xatolik (balans yetarli emas).")

    # Bazaga saqlash
    new_ad = await db.create_ad(
        user_id=user["id"], ad_type="sotish", tariff=req.tariff, photos=req.photos,
        breed=req.breed, age=req.age, gender=req.gender, health=req.health,
        sterilization=req.sterilization, address=req.address, phone=req.phone,
        price=req.price, currency=req.currency, ad_number=user["ad_count"] + 1
    )
    return {"status": "success", "message": "Reklama yaratildi", "ad": new_ad}


@app.get("/api/rating")
async def get_rating():
    """Frontend'dagi Podium (Top 10) uchun reyting."""
    top_users = await db.get_top_10_users()
    # Frontendga moslab formatlaymiz
    formatted = []
    for u in top_users:
        formatted.append({
            "id": u["id"],
            "name": u["full_name"] or "Foydalanuvchi",
            "score": u["score"],
            "avatar": f"https://ui-avatars.com/api/?name={u['full_name'] or 'U'}&background=3B82F6&color=fff"
        })
    return formatted


# ==============================================================================
# 3. HISOB TO'LDIRISH (TOPUP) VA TO'LOVLAR
# ==============================================================================

@app.post("/api/topup")
async def create_topup(req: TopUpRequest, user: dict = Depends(get_current_user)):
    """Karta ma'lumotlarini olish va to'lov so'rovini yaratish."""
    if req.amount < 1000:
        raise HTTPException(400, "Minimal to'lov 1000 so'm")

    card = await db.get_active_card()
    if not card:
        raise HTTPException(404, "To'lov kartasi mavjud emas. Admin bilan bog'laning.")

    card_last4 = card['number'][-4:]
    payment_id = await db.create_payment_request(user["id"], req.amount, card["id"], card_last4)

    return {
        "payment_id": payment_id,
        "card_number": card["number"],
        "card_holder": card["holder"],
        "amount": req.amount,
        "timer_seconds": Settings.TOPUP_TIMER_MINUTES * 60
    }


@app.post("/api/topup/receipt")
async def upload_receipt(
        payment_id: int = Form(...),
        file: UploadFile = File(...),
        user: dict = Depends(get_current_user)
):
    """To'lov chekini (rasmini) serverga yuklash."""
    file_ext = file.filename.split('.')[-1] if file.filename else "jpg"
    file_name = f"receipt_{payment_id}_{user['id']}.{file_ext}"
    file_path = os.path.join(UPLOAD_DIR, file_name)

    with open(file_path, "wb") as f:
        f.write(await file.read())

    await db.attach_receipt(payment_id, file_name)
    return {"status": "success", "message": "Chek yuklandi. Admin tasdiqlashini kuting."}


# ==============================================================================
# 4. ADMIN PANEL (STATISTIKA VA BOSHQARUV)
# ==============================================================================

@app.get("/api/admin/stats")
async def admin_stats(admin: dict = Depends(check_admin)):
    """Admin uchun umumiy va batafsil statistika."""
    return await db.get_statistics()


@app.post("/api/admin/card")
async def add_card(req: AddCardRequest, admin: dict = Depends(check_admin)):
    """Yangi to'lov kartasini qo'shish."""
    if len(req.number) != 16 or not req.number.isdigit():
        raise HTTPException(400, "Karta 16 xonali raqam bo'lishi kerak")
    await db.add_card(req.number, req.holder)
    return {"status": "success", "message": "Karta o'zgartirildi"}


@app.get("/api/admin/pending_ads")
async def get_pending_ads(admin: dict = Depends(check_admin)):
    """Kanalga chiqishi kutilayotgan (Tasdiqlanmagan) reklamalar."""
    return await db.get_pending_ads()


@app.post("/api/admin/ads/approve/{ad_id}")
async def approve_ad(ad_id: int, admin: dict = Depends(check_admin)):
    """Reklamani tasdiqlash."""
    await db.update_ad_status(ad_id, "approved")
    return {"status": "success"}


@app.post("/api/admin/ads/reject/{ad_id}")
async def reject_ad(ad_id: int, admin: dict = Depends(check_admin)):
    """Reklamani rad etish."""
    await db.update_ad_status(ad_id, "rejected")
    return {"status": "success"}


@app.post("/api/admin/bot/toggle")
async def toggle_bot(admin: dict = Depends(check_admin)):
    """Botni yoqish yoki o'chirish."""
    current = await db.get_setting("bot_enabled", "1")
    new_val = "0" if current == "1" else "1"
    await db.set_setting("bot_enabled", new_val)
    return {"status": "success", "bot_enabled": new_val == "1"}


# ==============================================================================
# 5. ADMIN - FOYDALANUVCHILARNI BOSHQARISH
# ==============================================================================

@app.get("/api/admin/users")
async def get_users(admin: dict = Depends(check_admin)):
    """Barcha foydalanuvchilar ro'yxati."""
    async with db.pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM users ORDER BY registered_at DESC")
        return [dict(r) for r in rows]


@app.get("/api/admin/user/{telegram_id}")
async def get_user_detail(telegram_id: int, admin: dict = Depends(check_admin)):
    """Bitta foydalanuvchi haqida to'liq ma'lumot (Detal statistika)."""
    user = await db.get_detailed_user_stats(telegram_id)
    if not user:
        raise HTTPException(404, "Foydalanuvchi topilmadi")
    return user


@app.post("/api/admin/user/block")
async def block_user(req: AdminActionRequest, admin: dict = Depends(check_admin)):
    """Foydalanuvchini bloklash."""
    await db.block_user(req.telegram_id)
    return {"status": "success"}


@app.post("/api/admin/user/unblock")
async def unblock_user(req: AdminActionRequest, admin: dict = Depends(check_admin)):
    """Foydalanuvchini blokdan chiqarish."""
    await db.unblock_user(req.telegram_id)
    return {"status": "success"}


@app.post("/api/admin/user/balance")
async def add_balance(req: AdminActionRequest, admin: dict = Depends(check_admin)):
    """Admin tomonidan qo'lda balans qo'shish yoki ayirish."""
    if not req.amount:
        raise HTTPException(400, "Summani kiriting")
    op = 'add' if req.amount > 0 else 'subtract'
    try:
        new_bal = await db.update_user_balance(req.telegram_id, abs(req.amount), op)
        return {"status": "success", "new_balance": new_bal}
    except ValueError:
        raise HTTPException(400, "Balans yetarli emas yoki xatolik.")


@app.post("/api/admin/user/add-score")
async def add_score(req: AdminAddScoreRequest, admin: dict = Depends(check_admin)):
    """Telefon raqam orqali foydalanuvchiga ball qo'shish."""
    success = await db.add_score_by_phone_batch(req.phone, req.score)
    if success:
        return {"status": "success", "message": "Ball qo'shildi"}
    raise HTTPException(404, "Bunday telefon raqamli foydalanuvchi topilmadi.")


# ==============================================================================
# 6. ADMIN - KONKURS VA REFERRAL QIDIRUVI
# ==============================================================================

@app.get("/api/admin/participants")
async def get_participants(admin: dict = Depends(check_admin)):
    """Konkurs ishtirokchilari (15+ ball)."""
    return await db.get_top_participants(min_score=15)


@app.get("/api/admin/referrals/{telegram_id}")
async def get_referrals(telegram_id: int, admin: dict = Depends(check_admin)):
    """Foydalanuvchi kimlarni taklif qilgani (yoki kim taklif qilgani)."""
    refs = await db.get_referrals_by_user(telegram_id)
    referrer = await db.get_referrer_of_user(telegram_id)
    return {"referrals": refs, "referrer": referrer}


# ==============================================================================
# 7. USERBOT BOSHQARUVI (Faqat Web App orqali)
# ==============================================================================

userbot_temp_sessions = {}


@app.post("/api/admin/userbot/send_code")
async def userbot_send_code(req: UserbotRequestCode, admin: dict = Depends(check_admin)):
    """Userbot qo'shish uchun Telegram raqamga kod yuborish."""
    try:
        client = TelegramClient(StringSession(), api_id=6, api_hash="eb06d4abfb49dc3eeb1aeb98ae0f581e")
        await client.connect()
        sent_code = await client.send_code_request(req.phone)

        userbot_temp_sessions[req.phone] = {
            "client": client,
            "phone_code_hash": sent_code.phone_code_hash
        }
        return {"status": "success", "message": "Kod yuborildi"}
    except Exception as e:
        raise HTTPException(400, f"Xatolik: {str(e)}")


@app.post("/api/admin/userbot/verify_code")
async def userbot_verify_code(req: UserbotVerifyCode, admin: dict = Depends(check_admin)):
    """Kodni tasdiqlash va sessiyani saqlash."""
    if req.phone not in userbot_temp_sessions:
        raise HTTPException(400, "Avval kod so'rang")

    session_data = userbot_temp_sessions[req.phone]
    client = session_data["client"]
    phone_code_hash = session_data["phone_code_hash"]

    try:
        await client.sign_in(req.phone, req.code, phone_code_hash=phone_code_hash)
    except SessionPasswordNeededError:
        if not req.password:
            raise HTTPException(401, "Ikkinchi bosqich paroli (2FA) kerak")
        await client.sign_in(password=req.password)
    except Exception as e:
        raise HTTPException(400, f"Kod xato: {str(e)}")

    session_string = client.session.save()

    async with db.pool.acquire() as conn:
        await conn.execute("UPDATE userbot_sessions SET is_active = FALSE")
        await conn.execute(
            "INSERT INTO userbot_sessions (phone, session_string, is_active) VALUES ($1, $2, TRUE)",
            req.phone, session_string
        )

    await client.disconnect()
    del userbot_temp_sessions[req.phone]
    return {"status": "success", "message": "Userbot muvaffaqiyatli qo'shildi"}


# ==============================================================================
# ISHGA TUSHIRISH (STARTUP & SHUTDOWN)
# ==============================================================================

@app.on_event("startup")
async def startup():
    await db.connect()
    logger.info("✅ API va Database ishga tushdi")


@app.on_event("shutdown")
async def shutdown():
    await db.disconnect()
    logger.info("🔌 API to'xtatildi")


if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)