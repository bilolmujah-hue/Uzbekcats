# ==============================================================================
# LOYIHA: UzbekCats Bot & Web App
# FAYL: api.py
# TAVSIF: FastAPI Backend (Web App bilan ishlash uchun barcha API yo'llari)
# ==============================================================================

import hmac
import hashlib
import json
import os
import urllib.parse
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Depends, Header, UploadFile, File, Form, status
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

class TelegramAuthData(BaseModel):
    initData: str


class AdCreateRequest(BaseModel):
    tariff: str  # web_only, channel_only, web_and_channel
    cat_count: int
    photos: List[str]  # Rasm URL yoki file_id lari (Hozircha Base64 yoki URL deb qabul qilamiz)
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


# ==============================================================================
# XAVFSIZLIK VA AUTENTIFIKATSIYA (Telegram WebApp ni tekshirish)
# ==============================================================================

def verify_telegram_webapp_data(init_data: str) -> dict:
    """
    Telegram Web App'dan kelgan ma'lumotlarni tekshiradi (HMAC-SHA256).
    Bu foydalanuvchi haqiqatan ham Telegram'dan kelayotganini tasdiqlaydi.
    """
    try:
        parsed_data = dict(urllib.parse.parse_qsl(init_data))
        if "hash" not in parsed_data:
            raise HTTPException(status_code=401, detail="Invalid initData: hash missing")

        received_hash = parsed_data.pop("hash")

        # Ma'lumotlarni tartiblab, stringga aylantiramiz
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed_data.items()))

        # Bot tokenidan foydalanib maxfiy kalit yasaymiz
        secret_key = hmac.new(
            b"WebAppData",
            BotConfig.BOT_TOKEN.encode(),
            hashlib.sha256
        ).digest()

        # Tekshiramiz
        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256
        ).hexdigest()

        if calculated_hash != received_hash:
            raise HTTPException(status_code=401, detail="Invalid initData: hash mismatch")

        # Foydalanuvchi ma'lumotlarini qaytaramiz
        user_data = json.loads(parsed_data.get("user", "{}"))
        return user_data
    except Exception as e:
        logger.error(f"Auth xatosi: {e}")
        raise HTTPException(status_code=401, detail="Avtorizatsiyadan o'tilmadi")


async def get_current_user(x_telegram_init_data: str = Header(None)):
    """Header orqali kelgan foydalanuvchini aniqlaydi."""
    if not x_telegram_init_data:
        raise HTTPException(status_code=401, detail="Telegram ma'lumotlari topilmadi")

    user_data = verify_telegram_webapp_data(x_telegram_init_data)
    user_id = user_data.get("id")

    if not user_id:
        raise HTTPException(status_code=401, detail="Foydalanuvchi ID topilmadi")

    user = await db.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Foydalanuvchi bazadan topilmadi")

    return user


async def check_admin(current_user: dict = Depends(get_current_user)):
    """Faqat adminlarga ruxsat berish."""
    if current_user['id'] not in BotConfig.ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Siz admin emassiz!")
    return current_user


# ==============================================================================
# 1. FOYDALANUVCHI MA'LUMOTLARI
# ==============================================================================

@app.get("/api/user/me")
async def get_me(user: dict = Depends(get_current_user)):
    """Profil sahifasi uchun foydalanuvchi ma'lumotlari."""
    return {
        "id": user["id"],
        "user_number": user["user_number"],
        "full_name": user["full_name"],
        "username": user["username"],
        "phone": user["phone"],
        "balance": user["balance"],
        "score": user["score"],
        "is_admin": user["id"] in BotConfig.ADMIN_IDS
    }


@app.get("/api/tariffs")
async def get_tariffs():
    """Frontend uchun narxlar ro'yxati."""
    return WebAppConfig.TARIFFS


# ==============================================================================
# 2. REKLAMALAR (ADS) BILAN ISHLASH
# ==============================================================================

@app.get("/api/ads")
async def get_active_ads():
    """Asosiy sahifa uchun barcha faol (Web) reklamalar."""
    # Eski, muddati o'tgan reklamlarni tozalash
    await db.cleanup_expired_web_ads()
    ads = await db.get_active_web_ads()
    return ads


@app.get("/api/user/ads")
async def get_my_ads(user: dict = Depends(get_current_user)):
    """Foydalanuvchining o'z reklamalari."""
    ads = await db.get_user_ads(user["id"])
    return ads


@app.post("/api/ads")
async def create_ad(req: AdCreateRequest, user: dict = Depends(get_current_user)):
    """Yangi reklama yaratish va balansdan pul yechish."""

    # 1. Narxni hisoblash
    count_idx = min(req.cat_count, 5)
    price = 0
    if req.tariff == "web_only":
        price = Prices.TARIFF_WEB[count_idx]
    elif req.tariff == "channel_only":
        price = Prices.TARIFF_CHANNEL[count_idx]
    elif req.tariff == "web_and_channel":
        price = Prices.TARIFF_BOTH[count_idx]
    else:
        raise HTTPException(400, "Noto'g'ri tarif tanlandi")

    # 2. Balansni tekshirish
    if user["balance"] < price:
        raise HTTPException(status_code=402, detail="Balansda mablag' yetarli emas! Iltimos, hisobni to'ldiring.")

    # 3. Balansdan pul yechish (Atomic)
    try:
        await db.update_user_balance(user["id"], price, operation='subtract')
    except ValueError:
        raise HTTPException(status_code=402, detail="Mablag' yechishda xatolik yuz berdi (balans yetarli emas).")

    # 4. Bazaga saqlash
    new_ad = await db.create_ad(
        user_id=user["id"],
        ad_type="sotish",
        tariff=req.tariff,
        photos=req.photos,
        breed=req.breed,
        age=req.age,
        gender=req.gender,
        health=req.health,
        sterilization=req.sterilization,
        address=req.address,
        phone=req.phone,
        price=req.price,
        currency=req.currency,
        ad_number=user["ad_count"] + 1
    )

    # 5. Agar 2 yoki 3-tarif bo'lsa Texnik Adminga yuborish (kanalga chiqishi uchun)
    if req.tariff in ["channel_only", "web_and_channel"]:
        # Bu yerda botga xabar yuborish funksiyasini chaqirish mumkin.
        # Hozircha DB da status 'pending' bo'lib turadi va Admin paneldan tasdiqlanadi.
        pass

    return {"status": "success", "message": "Reklama yaratildi", "ad": new_ad}


# ==============================================================================
# 3. HISOB TO'LDIRISH (TOP UP)
# ==============================================================================

@app.post("/api/topup")
async def create_topup(req: TopUpRequest, user: dict = Depends(get_current_user)):
    """Hisob to'ldirish uchun karta va taymer ma'lumotlarini berish."""
    if req.amount < 1000:
        raise HTTPException(400, "Minimal to'lov 1000 so'm")

    card = await db.get_active_card()
    if not card:
        raise HTTPException(404, "Hozircha to'lov kartasi mavjud emas. Admin bilan bog'laning.")

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
    """To'lov chekini yuklash."""
    # Faylni saqlash
    file_ext = file.filename.split('.')[-1]
    file_name = f"receipt_{payment_id}_{user['id']}.{file_ext}"
    file_path = os.path.join(UPLOAD_DIR, file_name)

    with open(file_path, "wb") as f:
        f.write(await file.read())

    # Bazaga yozish
    await db.attach_receipt(payment_id, file_name)

    # Adminni xabardor qilish (Bot.py dagi funksiyaga murojaat qilsa ham bo'ladi)
    # Hozircha API qaytaradi, bot polling qilib olsa ham bo'ladi.

    return {"status": "success", "message": "Chek yuklandi. Admin tasdiqlashini kuting."}


# ==============================================================================
# 4. ADMIN PANEL (Faqat Adminlar uchun)
# ==============================================================================

@app.get("/api/admin/stats")
async def admin_stats(admin: dict = Depends(check_admin)):
    """Admin uchun statistika (Tushum, Texnik admin ulushi va h.k.)."""
    stats = await db.get_statistics()
    return stats


@app.post("/api/admin/card")
async def add_card(req: AddCardRequest, admin: dict = Depends(check_admin)):
    """Yangi to'lov kartasini qo'shish."""
    if len(req.number) != 16 or not req.number.isdigit():
        raise HTTPException(400, "Karta 16 xonali raqam bo'lishi kerak")
    await db.add_card(req.number, req.holder)
    return {"status": "success", "message": "Karta o'zgartirildi"}


@app.get("/api/admin/pending_ads")
async def get_pending_ads(admin: dict = Depends(check_admin)):
    """Kanaldagi tasdiqlanishi kutilayotgan reklamalar."""
    ads = await db.get_pending_ads_for_tech_admin()
    return ads


@app.post("/api/admin/approve_ad/{ad_id}")
async def approve_ad(ad_id: int, admin: dict = Depends(check_admin)):
    """Reklamani tasdiqlash (Bot orqali kanalga post qilinadi)."""
    await db.update_ad_status(ad_id, "approved")
    return {"status": "success"}


# ==============================================================================
# 5. USERBOT BOSHQARUVI (Faqat Web App orqali)
# ==============================================================================

# Userbot login jarayonida vaqtinchalik kodni saqlash uchun lug'at
userbot_temp_sessions = {}


@app.post("/api/admin/userbot/send_code")
async def userbot_send_code(req: UserbotRequestCode, admin: dict = Depends(check_admin)):
    """Userbot qo'shish uchun Telegram raqamga kod yuborish."""
    try:
        client = TelegramClient(StringSession(), api_id=6, api_hash="eb06d4abfb49dc3eeb1aeb98ae0f581e")
        await client.connect()

        sent_code = await client.send_code_request(req.phone)

        # Sessiyani vaqtincha saqlaymiz
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
        # Agar 2FA parol bo'lsa
        if not req.password:
            raise HTTPException(401, "Ikkinchi bosqich paroli (2FA) kerak")
        await client.sign_in(password=req.password)
    except Exception as e:
        raise HTTPException(400, f"Kod xato: {str(e)}")

    # Sessiyani saqlash
    session_string = client.session.save()

    # Bazaga yozish
    async with db.pool.acquire() as conn:
        await conn.execute("UPDATE userbot_sessions SET is_active = FALSE")  # Eskilarni o'chirish
        await conn.execute(
            "INSERT INTO userbot_sessions (phone, session_string, is_active) VALUES ($1, $2, TRUE)",
            req.phone, session_string
        )

    await client.disconnect()
    del userbot_temp_sessions[req.phone]

    return {"status": "success", "message": "Userbot muvaffaqiyatli qo'shildi"}


# ==============================================================================
# ISHGA TUSHIRISH
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