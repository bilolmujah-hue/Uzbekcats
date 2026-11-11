# ==============================================================================
# LOYIHA: UzbekCats Bot & Web App
# FAYL: api.py
# TAVSIF: FastAPI Backend — to'liq mukammal, yangilangan (URL rasmlar, cats_data)
# ==============================================================================

import hashlib
import hmac
import json
import logging
import os
import urllib.parse
import uuid
from datetime import datetime, timedelta
from typing import List, Optional

import uvicorn
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from aiogram import Bot as AiogramBot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, FSInputFile
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.sessions import StringSession

from config import (
    BotConfig,
    DataLists,
    Prices,
    Settings,
    Texts,
    UserbotConfig,
    WebAppConfig,
)
from db import db

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


# ==============================================================================
# FASTAPI SOZLAMALARI
# ==============================================================================

app = FastAPI(
    title="UzbekCats API",
    description="Telegram Web App va Bot uchun Backend API",
    version="3.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = os.path.abspath("uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# Kanalga post yuborish uchun yengil bot instansiyasi
try:
    api_bot = AiogramBot(
        token=BotConfig.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
except Exception as e:
    logger.critical(f"❌ api_bot yaratilmadi: {e}")
    api_bot = None


# ==============================================================================
# PYDANTIC MODELLARI
# ==============================================================================

class TelegramAuthRequest(BaseModel):
    init_data: str
    user: dict


class TopUpRequest(BaseModel):
    amount: int = Field(..., ge=Settings.MIN_TOPUP_AMOUNT, le=100_000_000)


class AddCardRequest(BaseModel):
    number: str = Field(..., min_length=16, max_length=19)
    holder: str = Field(..., min_length=2, max_length=100)

    @field_validator("number")
    @classmethod
    def validate_card(cls, v: str) -> str:
        digits = "".join(ch for ch in v if ch.isdigit())
        if len(digits) != 16:
            raise ValueError("Karta raqami 16 xonali bo'lishi kerak")
        return digits


class UserbotRequestCode(BaseModel):
    phone: str = Field(..., min_length=9, max_length=20)


class UserbotVerifyCode(BaseModel):
    phone: str
    code: str = Field(..., min_length=4, max_length=10)
    password: Optional[str] = None


class AdminActionRequest(BaseModel):
    telegram_id: int
    amount: Optional[int] = None
    reason: Optional[str] = None


class AdminAddScoreRequest(BaseModel):
    phone: str = Field(..., min_length=9, max_length=20)
    score: int = Field(..., ge=-10000, le=10000)


class AdminPaymentAction(BaseModel):
    reason: Optional[str] = None


# ==============================================================================
# AUTENTIFIKATSIYA
# ==============================================================================

MAX_INIT_DATA_AGE = 86400  # 24 soat

def verify_telegram_webapp_data(init_data: str) -> dict:
    """Telegram WebApp initData ni HMAC-SHA256 bilan tekshiradi."""
    if not init_data:
        raise HTTPException(401, "initData bo'sh")

    try:
        parsed = dict(urllib.parse.parse_qsl(init_data, strict_parsing=False))
    except Exception as e:
        raise HTTPException(401, f"initData parse xato: {e}")

    if "hash" not in parsed:
        raise HTTPException(401, "initData: hash yo'q")

    received_hash = parsed.pop("hash")
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))

    secret_key = hmac.new(
        b"WebAppData",
        BotConfig.BOT_TOKEN.encode(),
        hashlib.sha256,
    ).digest()

    calculated_hash = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(calculated_hash, received_hash):
        raise HTTPException(401, "initData hash noto'g'ri")

    # Muddatni tekshirish
    try:
        auth_date = int(parsed.get("auth_date", 0))
    except (ValueError, TypeError):
        auth_date = 0

    if auth_date and (datetime.utcnow().timestamp() - auth_date) > MAX_INIT_DATA_AGE:
        logger.warning(f"initData muddati o'tgan (auth_date={auth_date})")
        raise HTTPException(401, "initData muddati o'tgan. WebApp'ni qayta oching.")

    user_json = parsed.get("user")
    if not user_json:
        raise HTTPException(401, "initData da user yo'q")

    try:
        user_data = json.loads(user_json)
    except json.JSONDecodeError:
        raise HTTPException(401, "user JSON xato")

    if not isinstance(user_data, dict) or not user_data.get("id"):
        raise HTTPException(401, "user.id yo'q")

    return user_data


async def get_current_user(x_telegram_init_data: str = Header(None)) -> dict:
    """Header orqali foydalanuvchini aniqlaydi."""
    if not x_telegram_init_data:
        raise HTTPException(401, "Telegram initData yuborilmagan")

    user_data = verify_telegram_webapp_data(x_telegram_init_data)
    user_id = user_data["id"]

    user = await db.get_user(user_id)
    if not user:
        raise HTTPException(404, "Foydalanuvchi topilmadi. Botga /start bosing.")
    if user.get("is_banned"):
        raise HTTPException(403, Texts.USER_BANNED)

    # Telegramdan kelgan rasm URLini foydalanuvchi ma'lumotlariga qo'shamiz (Frontend uchun)
    user["photo_url"] = user_data.get("photo_url")
    
    return user


async def check_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """Faqat adminlarga ruxsat."""
    if current_user["id"] not in BotConfig.ADMIN_IDS and not current_user.get("is_admin"):
        raise HTTPException(403, Texts.NOT_ADMIN)
    return current_user


# ==============================================================================
# YORDAMCHI FUNKSIYALAR
# ==============================================================================

def _parse_photos(photos) -> list:
    if isinstance(photos, str):
        try:
            photos = json.loads(photos)
        except json.JSONDecodeError:
            photos = []
    return photos if isinstance(photos, list) else []


async def _post_ad_to_channel(ad_data: dict) -> dict:
    """API orqali kanalga post yuborish (mahalliy fayllar bilan)."""
    if api_bot is None:
        raise HTTPException(500, "Bot instansiyasi mavjud emas")

    ad_type = ad_data.get("ad_type")
    cats_data = ad_data.get("cats_data") or []
    address = ad_data.get("address") or "—"
    phone = ad_data.get("phone") or "—"
    price = ad_data.get("price") or "0"
    currency = ad_data.get("currency") or "so'm"

    # Mushuklar ma'lumotlarini chiroyli formatga keltirish
    cats_text = ""
    if cats_data:
        for i, cat in enumerate(cats_data):
            cats_text += f"🐱 <b>{i+1}-mushuk:</b> {cat.get('breed', '—')} | {cat.get('age', '—')} | {cat.get('gender', '—')} | {cat.get('health', '—')}\n"
    else:
        # Agar eski uslubda bitta mushuk bo'lsa
        breed = ad_data.get("breed") or "—"
        age = ad_data.get("age") or "—"
        cats_text = f"🐱 {breed} | {age}\n"

    footer = (
        '👤 <a href="https://t.me/zayd_catlover">Admin</a>\n'
        '📢 <a href="https://t.me/Uzbek_cat_bot?start=reklama">Reklama berish</a>\n\n'
        '<a href="https://youtu.be/vdwgSB7_amw">YouTube</a> | '
        '<a href="https://www.instagram.com/p/C-cZkgstVGK/">Instagram</a> | '
        '<a href="https://t.me/uzbek_cats">Telegram</a>'
    )

    if ad_type == "sotish":
        caption = (
            f"#SOTILADI 💰\n\n"
            f"{cats_text}\n"
            f"📍 Manzil: {address}\n💵 Narxi: {price} {currency}\n📞 Tel: {phone}\n\n{footer}"
        )
        target = BotConfig.CHANNEL_SOTISH_ID
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎁 Hadiya kanal", url=BotConfig.CHANNEL_HADIYA_LINK)],
            [InlineKeyboardButton(text="📢 Reklama berish", url=BotConfig.BOT_LINK)],
        ])
    elif ad_type == "hadiya":
        caption = (
            f"#HADIYA 🎁\n\n"
            f"{cats_text}\n"
            f"📍 Manzil: {address}\n📞 Tel: {phone}\n\n{footer}"
        )
        target = BotConfig.CHANNEL_HADIYA_ID
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💰 Sotiladi kanal", url=BotConfig.CHANNEL_SOTISH_LINK)],
            [InlineKeyboardButton(text="📢 Reklama berish", url=BotConfig.BOT_LINK)],
        ])
    else:
        raise HTTPException(400, f"Noma'lum ad_type: {ad_type}")

    photos = _parse_photos(ad_data.get("photos"))
    
    # Birinchi rasmni fayl sifatida yuklaymiz
    photo_file = None
    if photos:
        file_path = os.path.join(UPLOAD_DIR, photos[0].split("/")[-1])
        if os.path.exists(file_path):
            photo_file = FSInputFile(file_path)

    try:
        if photo_file:
            sent = await api_bot.send_photo(chat_id=target, photo=photo_file, caption=caption, reply_markup=kb)
        else:
            sent = await api_bot.send_message(chat_id=target, text=caption, reply_markup=kb)
        
        logger.info(f"✅ Kanalga yuborildi: chat={target} msg_id={sent.message_id}")
        return {"message_id": sent.message_id, "chat_id": sent.chat.id}
    except Exception as e:
        logger.error(f"❌ Kanalga yuborish xatosi (chat={target}): {e}")
        raise HTTPException(500, f"Kanalga yuborilmadi: {str(e)[:200]}")


async def _refund_ad(user_id: int, amount: int):
    """Reklama rad etilganda pulni qaytarish."""
    if amount <= 0:
        return
    try:
        await db.update_user_balance(user_id, amount, operation="add")
        logger.info(f"💸 Refund: user={user_id} amount={amount}")
    except Exception as e:
        logger.error(f"❌ Refund xatosi: {e}")


# ==============================================================================
# 1. HEALTH & CONFIG
# ==============================================================================

@app.get("/api/health")
async def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}


@app.get("/api/config")
async def get_frontend_config():
    """Frontend uchun umumiy konfiguratsiya."""
    return {
        "bot_username": BotConfig.BOT_USERNAME,
        "bot_link": BotConfig.BOT_LINK,
        "web_app_url": BotConfig.WEB_APP_URL,
        "tariffs": WebAppConfig.TARIFFS,
        "min_topup": Settings.MIN_TOPUP_AMOUNT,
        "topup_timer_minutes": Settings.TOPUP_TIMER_MINUTES,
        "web_ad_days": Settings.WEB_AD_DAYS,
        "viloyatlar": DataLists.VILOYATLAR,
        "ages": DataLists.AGES,
        "breeds": DataLists.BREEDS,
    }


# ==============================================================================
# 2. AUTENTIFIKATSIYA VA FOYDALANUVCHI
# ==============================================================================

@app.post("/api/auth/telegram")
async def auth_telegram(req: TelegramAuthRequest):
    user_data = verify_telegram_webapp_data(req.init_data)
    user = await db.get_user(user_data["id"])
    if not user:
        raise HTTPException(404, "Foydalanuvchi topilmadi. Botga /start bosing.")
    
    return {
        "access_token": req.init_data,
        "user": {
            "telegram_id": user["id"],
            "user_number": user["user_number"],
            "full_name": user["full_name"],
            "username": user.get("username"),
            "photo_url": user_data.get("photo_url"), # Telegram rasmi
            "balance": user["balance"],
            "score": user["score"],
            "is_admin": user["id"] in BotConfig.ADMIN_IDS or bool(user.get("is_admin")),
        },
    }


@app.get("/api/user/me")
async def get_me(user: dict = Depends(get_current_user)):
    return {
        "id": user["id"],
        "user_number": user["user_number"],
        "full_name": user["full_name"],
        "username": user.get("username"),
        "photo_url": user.get("photo_url"), # get_current_user dan olinadi
        "balance": user["balance"],
        "score": user["score"],
        "spent": user.get("spent", 0),
        "ad_count": user.get("ad_count", 0),
        "is_admin": user["id"] in BotConfig.ADMIN_IDS or bool(user.get("is_admin")),
    }


@app.get("/api/user/ads")
async def get_my_ads(user: dict = Depends(get_current_user)):
    return await db.get_user_ads(user["id"])


# ==============================================================================
# 3. REKLAMALAR
# ==============================================================================

@app.get("/api/ads")
async def get_active_ads():
    try:
        await db.cleanup_expired_ads()
    except Exception as e:
        logger.warning(f"cleanup_expired_ads xatosi: {e}")
    return await db.get_active_web_ads()


@app.post("/api/ads")
async def create_ad(
    tariff: str = Form(...),
    cat_count: int = Form(...),
    cats_data: str = Form(...), # JSON string ko'rinishida keladi
    address: str = Form(...),
    phone: str = Form(...),
    price: str = Form(default="0"),
    currency: str = Form(default="so'm"),
    photos: List[UploadFile] = File(...),
    user: dict = Depends(get_current_user)
):
    """Web App orqali yangi reklama yaratish (rasmlar URL orqali yuklanadi)."""
    
    # 1. Tarifni tekshirish va narxni aniqlash
    tariff_info = WebAppConfig.TARIFFS.get(tariff)
    if not tariff_info:
        raise HTTPException(400, "Noto'g'ri tarif tanlandi")

    ad_price = tariff_info["prices"].get(cat_count)
    if ad_price is None:
        raise HTTPException(400, "Bu mushuk soni uchun narx belgilanmagan")

    if user["balance"] < ad_price:
        raise HTTPException(
            402,
            Texts.ERROR_INSUFFICIENT_BALANCE.format(price=ad_price, balance=user["balance"]),
        )

    # 2. cats_data ni JSON dan o'girish
    try:
        cats_list = json.loads(cats_data)
    except json.JSONDecodeError:
        raise HTTPException(400, "Mushuklar ma'lumotlari xato formatda")

    # 3. Rasmlarni saqlash (maks 3 ta)
    if len(photos) > 3:
        raise HTTPException(400, "Maksimal 3 ta rasm yuklash mumkin")
    
    saved_urls = []
    for file in photos:
        if not file.content_type.startswith("image/"):
            raise HTTPException(400, "Faqat rasm yuklang")
        
        ext = file.filename.split(".")[-1] if "." in file.filename else "jpg"
        safe_name = f"ad_{uuid.uuid4().hex[:10]}.{ext}"
        safe_path = os.path.join(UPLOAD_DIR, safe_name)
        
        with open(safe_path, "wb") as f:
            f.write(await file.read())
        
        saved_urls.append(f"/uploads/{safe_name}")

    # 4. Balansdan yechish
    try:
        await db.update_user_balance(user["id"], ad_price, operation="subtract")
    except ValueError:
        raise HTTPException(402, Texts.ERROR_BALANCE_SUBTRACT)

    # 5. Reklama yaratish
    try:
        new_ad = await db.create_ad(
            user_id=user["id"],
            ad_type="sotish",
            tariff=tariff,
            photos=saved_urls,
            cats_data=cats_list,
            address=address,
            phone=phone,
            price=price,
            currency=currency,
            ad_number=(user.get("ad_count") or 0) + 1,
            cat_count=cat_count,
            price_paid=ad_price,
        )
    except Exception as e:
        await _refund_ad(user["id"], ad_price) # Xato bo'lsa pulni qaytarish
        logger.exception("create_ad xatosi")
        raise HTTPException(500, f"Reklama yaratilmadi: {str(e)[:200]}")

    # 6. Adminga yuborish
    if api_bot and new_ad:
        try:
            admin_caption = f"🆕 <b>YANGI WEB APP REKLAMA!</b>\n\n👤 #{user['user_number']} ({user['full_name']})\n💰 Tarif: {tariff}\n🐱 Soni: {cat_count} ta\n💵 To'landi: {ad_price:,} so'm\n📍 Manzil: {address}"
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"adm_ok_{new_ad['id']}")],
                [InlineKeyboardButton(text="❌ Rad etish", callback_data=f"adm_no_{new_ad['id']}")]
            ])
            file_path = os.path.join(UPLOAD_DIR, saved_urls[0].split("/")[-1])
            await api_bot.send_photo(
                chat_id=BotConfig.TECH_ADMIN_ID,
                photo=FSInputFile(file_path),
                caption=admin_caption,
                reply_markup=kb
            )
        except Exception as e:
            logger.error(f"Adminga xabar yuborishda xato: {e}")

    return {
        "status": "success",
        "message": "Reklama muvaffaqiyatli yaratildi va adminga yuborildi",
        "ad_id": new_ad["id"],
        "charged": ad_price,
    }


@app.delete("/api/ads/{ad_id}")
async def delete_my_ad(ad_id: int, user: dict = Depends(get_current_user)):
    """Faqat o'z reklamasini o'chirish."""
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM ads WHERE id = $1 AND user_id = $2", ad_id, user["id"])
        if not row:
            raise HTTPException(404, "Reklama topilmadi")
        if row["status"] not in ("pending", "approved"):
            raise HTTPException(400, "Bu reklamani o'chirib bo'lmaydi")

        await conn.execute(
            "UPDATE ads SET status = 'rejected', reject_reason = 'Foydalanuvchi o''chirdi' WHERE id = $1", ad_id
        )

    # Sotildi deb belgilash (Faqat ruxsat berilgan holatlarda pul qaytarilmaydi)
    return {"status": "success", "message": "Reklama o'chirildi"}


@app.get("/api/rating")
async def get_rating():
    """Top 50 foydalanuvchilar."""
    top_users = await db.get_top_users(limit=50)
    result = []
    for u in top_users:
        name = u.get("full_name") or "Foydalanuvchi"
        result.append({
            "id": u["id"],
            "name": name,
            "score": u["score"],
            "user_number": u.get("user_number"),
            "avatar": f"https://ui-avatars.com/api/?name={urllib.parse.quote(name)}&background=3B82F6&color=fff",
        })
    return result


# ==============================================================================
# 4. HISOB TO'LDIRISH (TOPUP)
# ==============================================================================

@app.post("/api/topup")
async def create_topup(req: TopUpRequest, user: dict = Depends(get_current_user)):
    card = await db.get_active_card()
    if not card:
        raise HTTPException(404, Texts.TOPUP_NO_CARD)

    card_last4 = str(card["number"])[-4:]
    payment_id = await db.create_payment_request(user["id"], req.amount, card["id"], card_last4)

    return {
        "payment_id": payment_id,
        "card_number": card["number"],
        "card_holder": card["holder"],
        "amount": req.amount,
        "timer_seconds": Settings.TOPUP_TIMER_MINUTES * 60,
    }


@app.post("/api/topup/receipt")
async def upload_receipt(
    payment_id: int = Form(...),
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    async with db.pool.acquire() as conn:
        payment = await conn.fetchrow("SELECT * FROM payments WHERE id = $1 AND user_id = $2", payment_id, user["id"])
    
    if not payment or payment["status"] != "pending":
        raise HTTPException(400, "To'lov topilmadi yoki yopilgan")

    ext = file.filename.split(".")[-1].lower()
    safe_name = f"receipt_{payment_id}_{uuid.uuid4().hex[:8]}.{ext}"
    safe_path = os.path.join(UPLOAD_DIR, safe_name)
    
    with open(safe_path, "wb") as f:
        f.write(await file.read())

    await db.attach_receipt(payment_id, safe_name)

    # Adminga yuborish
    if api_bot:
        try:
            await api_bot.send_photo(
                BotConfig.TECH_ADMIN_ID,
                photo=FSInputFile(safe_path),
                caption=f"🧾 <b>Yangi chek!</b>\n\n👤 Foydalanuvchi: #{user['user_number']}\n💰 Summa: {payment['amount']:,} so'm\n🆔 To'lov ID: <code>{payment_id}</code>",
            )
        except: pass

    return {"status": "success", "message": "Chek yuklandi. Admin tasdiqlashini kuting."}


# ==============================================================================
# 5. ADMIN — API ENDPOINTLARI (Panellar uchun)
# ==============================================================================

@app.get("/api/admin/stats")
async def admin_stats(admin: dict = Depends(check_admin)):
    """Barcha statistikalar (Bugun, Kecha, 7 kun, 30 kun, 1 yil, Jami)."""
    return await db.get_statistics()


@app.get("/api/admin/ads")
async def get_all_ads(admin: dict = Depends(check_admin)):
    return await db.get_all_ads()


@app.get("/api/admin/users")
async def get_all_users(admin: dict = Depends(check_admin)):
    return await db.get_all_users()


@app.get("/api/admin/cards")
async def get_all_cards(admin: dict = Depends(check_admin)):
    return await db.get_all_cards()


@app.post("/api/admin/card")
async def add_card(req: AddCardRequest, admin: dict = Depends(check_admin)):
    card_id = await db.add_card(req.number, req.holder)
    return {"status": "success", "card_id": card_id, "message": "Karta yangilandi"}


@app.delete("/api/admin/card/{card_id}")
async def delete_card(card_id: int, admin: dict = Depends(check_admin)):
    ok = await db.delete_card(card_id)
    if not ok: raise HTTPException(404, "Karta topilmadi")
    return {"status": "success", "message": "Karta o'chirildi"}


@app.post("/api/admin/ads/approve/{ad_id}")
async def approve_ad(ad_id: int, admin: dict = Depends(check_admin)):
    ad = await db.get_ad(ad_id)
    if not ad: raise HTTPException(404, "E'lon topilmadi")
    if ad["status"] != "pending": raise HTTPException(400, "E'lon allaqachon ko'rilgan")

    msg_info = None
    if ad.get("tariff") in ("channel_only", "web_and_channel", "bot"):
        msg_info = await _post_ad_to_channel(ad)

    await db.update_ad_status(ad_id, "approved", channel_message_id=msg_info["message_id"] if msg_info else None)
    
    if api_bot:
        try:
            await api_bot.send_message(ad["user_id"], "✅ <b>E'loningiz tasdiqlandi va kanalga joylandi!</b>")
        except: pass
        
    return {"status": "success"}


@app.post("/api/admin/ads/reject/{ad_id}")
async def reject_ad(ad_id: int, req: AdminPaymentAction, admin: dict = Depends(check_admin)):
    ad = await db.get_ad(ad_id)
    if not ad: raise HTTPException(404, "E'lon topilmadi")
    
    await db.update_ad_status(ad_id, "rejected", reason=req.reason)
    
    # Pulni qaytarish
    if ad.get("price_paid", 0) > 0:
        await _refund_ad(ad["user_id"], ad["price_paid"])
        
    if api_bot:
        try:
            await api_bot.send_message(ad["user_id"], f"❌ <b>E'loningiz rad etildi.</b>\nSabab: {req.reason}\nPul qaytarildi.")
        except: pass
        
    return {"status": "success"}


# ==============================================================================
# STARTUP / SHUTDOWN
# ==============================================================================

@app.on_event("startup")
async def startup():
    await db.connect()
    logger.info("✅ API va Database ishga tushdi")

@app.on_event("shutdown")
async def shutdown():
    if api_bot is not None:
        try: await api_bot.session.close()
        except: pass
    await db.disconnect()
    logger.info("🔌 API to'xtatildi")


if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=False)
