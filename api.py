# ==============================================================================
# LOYIHA: UzbekCats Bot & Web App
# FAYL: api.py
# TAVSIF: FastAPI Backend — Frontend bilan to'liq moslashtirilgan, rasm/video
#         xatolari bartaraf etilgan, Admin panel (Userbot, Sozlamalar, Tahrirlash) 
#         uchun to'liq kengaytirilgan versiya.
# ==============================================================================

import hashlib
import hmac
import json
import logging
import os
import urllib.parse
import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

import uvicorn
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from aiogram import Bot as AiogramBot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, InputMediaVideo
from aiogram.exceptions import TelegramBadRequest
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
    version="2.3.0",
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


class AdEditRequest(BaseModel):
    address: Optional[str] = None
    phone: Optional[str] = None
    price: Optional[str] = None
    currency: Optional[str] = None


class SettingsUpdateRequest(BaseModel):
    ad_duration_days: Optional[int] = None


# ==============================================================================
# AUTENTIFIKATSIYA
# ==============================================================================

MAX_INIT_DATA_AGE = 86400  # 24 soat


def verify_telegram_webapp_data(init_data: str) -> dict:
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
    if not x_telegram_init_data:
        raise HTTPException(401, "Telegram initData yuborilmagan")

    user_data = verify_telegram_webapp_data(x_telegram_init_data)
    user_id = user_data["id"]

    user = await db.get_user(user_id)
    if not user:
        raise HTTPException(404, "Foydalanuvchi topilmadi. Botga /start bosing.")
    if user.get("is_banned"):
        raise HTTPException(403, Texts.USER_BANNED)

    return user


async def check_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user["id"] not in BotConfig.ADMIN_IDS and not current_user.get("is_admin"):
        raise HTTPException(403, Texts.NOT_ADMIN)
    return current_user


# ==============================================================================
# YORDAMCHI FUNKSIYALAR
# ==============================================================================

def _parse_photos(photos) -> list:
    if isinstance(photos, str):
        try: photos = json.loads(photos)
        except: photos = []
    return photos if isinstance(photos, list) else []


async def _post_ad_to_channel(ad_data: dict) -> dict:
    if api_bot is None:
        raise HTTPException(500, "Bot instansiyasi mavjud emas")

    ad_type = ad_data.get("ad_type")
    address = ad_data.get("address") or "—"
    phone = ad_data.get("phone") or "—"
    price = ad_data.get("price") or "0"
    currency = ad_data.get("currency") or "so'm"

    cats_data = ad_data.get("cats_data") or []
    if isinstance(cats_data, str):
        try: cats_data = json.loads(cats_data)
        except: cats_data = []

    if not cats_data:
        cats_data = [{
            "breed": ad_data.get("breed") or "Noma'lum",
            "age": ad_data.get("age") or "—",
            "gender": ad_data.get("gender") or "—",
            "health": ad_data.get("health") or "—",
            "sterilization": ad_data.get("sterilization") or "—"
        }]

    cats_text = ""
    for i, cat in enumerate(cats_data, 1):
        cats_text += f"🐱 <b>{i}-mushuk:</b> {cat.get('breed', '—')} | {cat.get('age', '—')} | {cat.get('gender', '—')} | {cat.get('health', '—')} | {cat.get('sterilization', '—')}\n"

    footer = (
        '👤 <a href="https://t.me/zayd_catlover">Admin</a>\n'
        '📢 <a href="https://t.me/Uzbek_cat_bot?start=reklama">Reklama berish</a>\n\n'
        '<a href="https://youtu.be/vdwgSB7_amw">YouTube</a> | '
        '<a href="https://www.instagram.com/p/C-cZkgstVGK/">Instagram</a> | '
        '<a href="https://t.me/uzbek_cats">Telegram</a>'
    )

    if ad_type == "sotish":
        caption = f"#SOTILADI 💰\n\n{cats_text}\n📍 Manzil: {address}\n💵 Narxi: {price} {currency}\n📞 Tel: {phone}\n\n{footer}"
        target = BotConfig.CHANNEL_SOTISH_ID
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎁 Hadiya kanal", url=BotConfig.CHANNEL_HADIYA_LINK)],
            [InlineKeyboardButton(text="📢 Reklama berish", url=BotConfig.BOT_LINK)],
        ])
    elif ad_type == "hadiya":
        caption = f"#HADIYA 🎁\n\n{cats_text}\n📍 Manzil: {address}\n📞 Tel: {phone}\n\n{footer}"
        target = BotConfig.CHANNEL_HADIYA_ID
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💰 Sotiladi kanal", url=BotConfig.CHANNEL_SOTISH_LINK)],
            [InlineKeyboardButton(text="📢 Reklama berish", url=BotConfig.BOT_LINK)],
        ])
    else:
        raise HTTPException(400, f"Noma'lum ad_type: {ad_type}")

    photos = _parse_photos(ad_data.get("photos"))
    media_type = ad_data.get("media_type", "photo")

    try:
        if len(photos) > 1:
            media_group = []
            for i, p in enumerate(photos):
                if media_type == "video":
                    media = InputMediaVideo(media=p, caption=caption if i == 0 else None, parse_mode=ParseMode.HTML)
                else:
                    media = InputMediaPhoto(media=p, caption=caption if i == 0 else None, parse_mode=ParseMode.HTML)
                media_group.append(media)
            
            sent_messages = await api_bot.send_media_group(chat_id=target, media=media_group)
            sent = sent_messages[0]
            
            try:
                await api_bot.edit_message_reply_markup(chat_id=target, message_id=sent.message_id, reply_markup=kb)
            except TelegramBadRequest:
                pass 
                
        elif len(photos) == 1:
            p = photos[0]
            if media_type == "video":
                sent = await api_bot.send_video(chat_id=target, video=p, caption=caption, reply_markup=kb)
            else:
                sent = await api_bot.send_photo(chat_id=target, photo=p, caption=caption, reply_markup=kb)
        else:
            sent = await api_bot.send_message(chat_id=target, text=caption, reply_markup=kb)
            
        logger.info(f"✅ Kanalga yuborildi: chat={target} msg_id={sent.message_id}")
        return {"message_id": sent.message_id, "chat_id": sent.chat.id}
    except Exception as e:
        logger.error(f"❌ Kanalga yuborish xatosi (chat={target}): {e}")
        raise HTTPException(500, f"Kanalga yuborilmadi: {str(e)[:200]}")


async def _refund_ad(user_id: int, amount: int):
    if amount <= 0: return
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
    return {"status": "ok", "bot": BotConfig.BOT_USERNAME, "time": datetime.utcnow().isoformat()}


@app.get("/api/config")
async def get_frontend_config():
    ad_days = await db.get_setting("ad_duration_days", str(Settings.WEB_AD_DAYS))
    try:
        ad_days_int = int(ad_days)
    except:
        ad_days_int = Settings.WEB_AD_DAYS

    return {
        "bot_username": BotConfig.BOT_USERNAME,
        "bot_link": BotConfig.BOT_LINK,
        "web_app_url": BotConfig.WEB_APP_URL,
        "channels": {
            "sotish": {"username": BotConfig.CHANNEL_SOTISH_USERNAME, "link": BotConfig.CHANNEL_SOTISH_LINK, "title": "Sotish kanali"},
            "hadiya": {"username": BotConfig.CHANNEL_HADIYA_USERNAME, "link": BotConfig.CHANNEL_HADIYA_LINK, "title": "Hadiya kanali"},
        },
        "tariffs": WebAppConfig.TARIFFS,
        "min_topup": Settings.MIN_TOPUP_AMOUNT,
        "topup_timer_minutes": Settings.TOPUP_TIMER_MINUTES,
        "web_ad_days": ad_days_int,
        "viloyatlar": DataLists.VILOYATLAR,
        "ages": DataLists.AGES,
        "breeds": DataLists.BREEDS,
    }


# ==============================================================================
# 2. RASM YUKLASH
# ==============================================================================

@app.post("/api/upload")
async def upload_image(
    request: Request,
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user)
):
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "jpg"
    if ext not in ("jpg", "jpeg", "png", "webp", "mp4", "mov"):
        raise HTTPException(400, "Faqat rasm yoki video formatlar ruxsat etilgan")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "Fayl hajmi 10MB dan oshmasin")

    safe_name = f"ad_{user['id']}_{uuid.uuid4().hex[:8]}.{ext}"
    safe_path = os.path.join(UPLOAD_DIR, safe_name)
    
    with open(safe_path, "wb") as f:
        f.write(content)

    base_url = str(request.base_url).rstrip("/")
    file_url = f"{base_url}/uploads/{safe_name}"

    return {"status": "success", "url": file_url}


# ==============================================================================
# 3. AUTENTIFIKATSIYA VA FOYDALANUVCHI
# ==============================================================================

@app.post("/api/auth/telegram")
async def auth_telegram(req: TelegramAuthRequest):
    user_data = verify_telegram_webapp_data(req.init_data)
    user = await db.get_user(user_data["id"])
    if not user:
        raise HTTPException(404, "Foydalanuvchi topilmadi. Botga /start bosing.")
    if user.get("is_banned"):
        raise HTTPException(403, Texts.USER_BANNED)
    return {"status": "success", "user_id": user["id"]}


@app.get("/api/user/me")
async def get_me(user: dict = Depends(get_current_user)):
    return {
        "id": user["id"],
        "user_number": user["user_number"],
        "full_name": user["full_name"],
        "username": user["username"],
        "phone": user["phone"],
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
# 4. REKLAMALAR
# ==============================================================================

@app.get("/api/ads")
async def get_active_ads():
    try:
        await db.cleanup_expired_ads()
    except Exception as e:
        logger.warning(f"cleanup_expired_ads xatosi: {e}")
    return await db.get_active_web_ads()


@app.get("/api/ads/{ad_id}")
async def get_ad(ad_id: int):
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM ads WHERE id = $1 AND status = 'approved'", ad_id)
    if not row:
        raise HTTPException(404, "Reklama topilmadi")
    return dict(row)


# 🔴 RASM URL LARI TO'LIQ MANZIL BILAN QAYTARILADI
@app.post("/api/ads")
async def create_ad(
    request: Request, # To'liq URL olish uchun
    tariff: str = Form(...),
    cat_count: int = Form(...),
    cats_data: str = Form(...),
    address: str = Form(...),
    phone: str = Form(...),
    price: str = Form("0"),
    currency: str = Form("so'm"),
    media_type: str = Form("photo"),
    photos: List[UploadFile] = File(None),
    user: dict = Depends(get_current_user)
):
    tariff_info = WebAppConfig.TARIFFS.get(tariff)
    if not tariff_info:
        raise HTTPException(400, "Noto'g'ri tarif")

    price_val = tariff_info["prices"].get(cat_count)
    if price_val is None:
        raise HTTPException(400, "Bu mushuk soni uchun narx yo'q")

    if user["balance"] < price_val:
        raise HTTPException(402, Texts.ERROR_INSUFFICIENT_BALANCE.format(price=price_val, balance=user["balance"]))

    try:
        await db.update_user_balance(user["id"], price_val, operation="subtract")
    except ValueError:
        raise HTTPException(402, Texts.ERROR_BALANCE_SUBTRACT)

    saved_photos = []
    base_url = str(request.base_url).rstrip("/")
    
    if photos:
        for file in photos:
            if not file.filename: continue
            ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "jpg"
            safe_name = f"ad_{user['id']}_{uuid.uuid4().hex[:8]}.{ext}"
            safe_path = os.path.join(UPLOAD_DIR, safe_name)
            
            content = await file.read()
            if len(content) > 10 * 1024 * 1024:
                await _refund_ad(user["id"], price_val)
                raise HTTPException(400, "Fayl hajmi 10MB dan oshmasin")
                
            with open(safe_path, "wb") as f:
                f.write(content)
                
            # Mutlaqo to'liq URL manzil yasaymiz (Frontendda qora fon bo'lib qolmasligi uchun)
            saved_photos.append(f"{base_url}/uploads/{safe_name}")

    try:
        cats_data_list = json.loads(cats_data)
    except json.JSONDecodeError:
        await _refund_ad(user["id"], price_val)
        raise HTTPException(400, "Mushuk ma'lumotlari (cats_data) noto'g'ri formatda")

    try:
        new_ad = await db.create_ad(
            user_id=user["id"],
            ad_type="sotish",
            tariff=tariff,
            photos=saved_photos,
            cats_data=cats_data_list,
            media_type=media_type,
            address=address,
            phone=phone,
            price=price,
            currency=currency,
            ad_number=(user.get("ad_count") or 0) + 1,
            cat_count=cat_count,
            price_paid=price_val
        )
    except Exception as e:
        await _refund_ad(user["id"], price_val)
        logger.exception("create_ad xatosi")
        raise HTTPException(500, f"Reklama yaratilmadi: {str(e)[:200]}")

    return {"status": "success", "message": "Reklama yaratildi va admin tasdiqlashini kutmoqda", "ad": new_ad, "charged": price_val}


@app.delete("/api/ads/{ad_id}")
async def delete_my_ad(ad_id: int, user: dict = Depends(get_current_user)):
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM ads WHERE id = $1 AND user_id = $2", ad_id, user["id"])
        if not row:
            raise HTTPException(404, "Reklama topilmadi")
        if row["status"] not in ("pending", "approved"):
            raise HTTPException(400, "Bu reklamani o'chirib bo'lmaydi")
        await conn.execute("UPDATE ads SET status = 'rejected', reject_reason = 'Foydalanuvchi o''chirdi' WHERE id = $1", ad_id)
    return {"status": "success", "message": "Reklama o'chirildi"}


@app.get("/api/rating")
async def get_rating():
    top_users = await db.get_top_users(limit=50)
    result = []
    for u in top_users:
        name = u.get("full_name") or "Foydalanuvchi"
        result.append({
            "id": u["id"], "name": name, "score": u["score"], "user_number": u.get("user_number"),
            "avatar": f"https://ui-avatars.com/api/?name={urllib.parse.quote(name)}&background=3B82F6&color=fff",
        })
    return result


# ==============================================================================
# 5. HISOB TO'LDIRISH (TOPUP)
# ==============================================================================

@app.post("/api/topup")
async def create_topup(req: TopUpRequest, user: dict = Depends(get_current_user)):
    card = await db.get_active_card()
    if not card: raise HTTPException(404, Texts.TOPUP_NO_CARD)
    card_last4 = str(card["number"])[-4:]
    try:
        payment_id = await db.create_payment_request(user["id"], req.amount, card["id"], card_last4)
    except Exception as e:
        raise HTTPException(500, f"To'lov yaratilmadi: {str(e)[:200]}")

    return {
        "payment_id": payment_id, "card_number": card["number"], "card_holder": card["holder"],
        "amount": req.amount, "timer_seconds": Settings.TOPUP_TIMER_MINUTES * 60,
        "expires_at": (datetime.utcnow() + timedelta(minutes=Settings.TOPUP_TIMER_MINUTES)).isoformat(),
    }


@app.get("/api/topup/status/{payment_id}")
async def topup_status(payment_id: int, user: dict = Depends(get_current_user)):
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow("SELECT id, amount, status, created_at, expires_at, receipt_file_id FROM payments WHERE id = $1 AND user_id = $2", payment_id, user["id"])
    if not row: raise HTTPException(404, "To'lov topilmadi")
    return dict(row)


@app.post("/api/topup/receipt")
async def upload_receipt(
    request: Request,
    payment_id: int = Form(...),
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    async with db.pool.acquire() as conn:
        payment = await conn.fetchrow("SELECT * FROM payments WHERE id = $1 AND user_id = $2", payment_id, user["id"])
    if not payment: raise HTTPException(404, "To'lov topilmadi")
    if payment["status"] != "pending": raise HTTPException(400, "Bu to'lov allaqachon yopilgan")
    if payment["expires_at"] < datetime.utcnow(): raise HTTPException(400, "To'lov muddati tugagan. Yangi so'rov yarating.")

    filename = file.filename or "receipt.jpg"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
    if ext not in ("jpg", "jpeg", "png", "webp", "pdf"): raise HTTPException(400, "Faqat jpg, png, webp, pdf")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024: raise HTTPException(400, "Fayl hajmi 10MB dan oshmasin")
    if len(content) == 0: raise HTTPException(400, "Bo'sh fayl")

    safe_name = f"receipt_{payment_id}_{user['id']}_{uuid.uuid4().hex[:8]}.{ext}"
    safe_path = os.path.join(UPLOAD_DIR, safe_name)
    with open(safe_path, "wb") as f: f.write(content)

    try:
        await db.attach_receipt(payment_id, safe_name)
    except Exception as e:
        raise HTTPException(500, f"Chek saqlanmadi: {str(e)[:200]}")

    if api_bot:
        try:
            card = await db.get_active_card()
            card_num = card["number"] if card else "Noma'lum"
            await api_bot.send_message(
                BotConfig.TECH_ADMIN_ID,
                f"🧾 <b>Yangi chek (WebApp)!</b>\n\n👤 Foydalanuvchi: #{user['user_number']} ({user['full_name']})\n💰 Summa: {payment['amount']:,} so'm\n💳 Karta: {card_num}\n🆔 To'lov ID: <code>{payment_id}</code>\n\nAdmin panel orqali tasdiqlang.",
            )
        except Exception: pass

    base_url = str(request.base_url).rstrip("/")
    return {"status": "success", "message": "Chek yuklandi. Admin tasdiqlashini kuting.", "receipt_url": f"{base_url}/uploads/{safe_name}"}


# ==============================================================================
# 6. ADMIN — STATISTIKA VA KARTALAR
# ==============================================================================

@app.get("/api/admin/stats")
async def admin_stats(admin: dict = Depends(check_admin)):
    return await db.get_statistics()


@app.get("/api/admin/cards")
async def get_all_cards(admin: dict = Depends(check_admin)):
    return await db.get_all_cards()


@app.get("/api/admin/card")
async def get_active_card_endpoint(admin: dict = Depends(check_admin)):
    card = await db.get_active_card()
    return card or {}


@app.post("/api/admin/card")
async def add_card(req: AddCardRequest, admin: dict = Depends(check_admin)):
    try: card_id = await db.add_card(req.number, req.holder)
    except Exception as e: raise HTTPException(500, f"Karta qo'shilmadi: {str(e)[:200]}")
    return {"status": "success", "card_id": card_id, "message": "Karta o'zgartirildi"}


@app.delete("/api/admin/card/{card_id}")
async def delete_card(card_id: int, admin: dict = Depends(check_admin)):
    ok = await db.delete_card(card_id)
    if not ok: raise HTTPException(404, "Karta topilmadi")
    return {"status": "success", "message": "Karta o'chirildi"}


# ==============================================================================
# 7. ADMIN — TO'LOVLAR
# ==============================================================================

@app.get("/api/admin/payments")
async def list_payments(admin: dict = Depends(check_admin), limit: int = 100):
    async with db.pool.acquire() as conn:
        rows = await conn.fetch("SELECT p.*, u.user_number, u.full_name, u.username FROM payments p LEFT JOIN users u ON u.id = p.user_id ORDER BY p.created_at DESC LIMIT $1", limit)
    return [dict(r) for r in rows]


@app.post("/api/admin/payments/{payment_id}/approve")
async def approve_payment(payment_id: int, admin: dict = Depends(check_admin)):
    async with db.pool.acquire() as conn:
        async with conn.transaction():
            payment = await conn.fetchrow("SELECT * FROM payments WHERE id = $1 AND status = 'pending' FOR UPDATE", payment_id)
            if not payment: raise HTTPException(404, "To'lov topilmadi yoki allaqachon yopilgan")
            await conn.execute("UPDATE payments SET status = 'paid', userbot_matched = FALSE WHERE id = $1", payment_id)
            await conn.execute("UPDATE users SET balance = balance + $1 WHERE id = $2", payment["amount"], payment["user_id"])

    if api_bot:
        try:
            await api_bot.send_message(payment["user_id"], f"✅ <b>To'lov tasdiqlandi!</b>\n\nHisobingizga {payment['amount']:,} so'm qo'shildi.")
        except Exception: pass
    return {"status": "success", "message": "To'lov tasdiqlandi"}


@app.post("/api/admin/payments/{payment_id}/reject")
async def reject_payment(payment_id: int, req: AdminPaymentAction, admin: dict = Depends(check_admin)):
    async with db.pool.acquire() as conn:
        payment = await conn.fetchrow("SELECT * FROM payments WHERE id = $1 AND status = 'pending'", payment_id)
        if not payment: raise HTTPException(404, "To'lov topilmadi yoki allaqachon yopilgan")
        await conn.execute("UPDATE payments SET status = 'cancelled' WHERE id = $1", payment_id)

    if api_bot:
        try:
            reason = (req.reason or "Sabab ko'rsatilmadi")[:200]
            await api_bot.send_message(payment["user_id"], f"❌ <b>To'lov rad etildi.</b>\n\nSabab: {reason}")
        except Exception: pass
    return {"status": "success", "message": "To'lov rad etildi"}


# ==============================================================================
# 8. ADMIN — FOYDALANUVCHILAR (Kengaytirildi)
# ==============================================================================

@app.get("/api/admin/users")
async def get_users(admin: dict = Depends(check_admin), limit: int = 100, offset: int = 0):
    return await db.get_all_users(limit, offset)


# 🔴 FOYDALANUVCHI USTIGA BOSGANDA TO'LIQ MA'LUMOT OLISH
@app.get("/api/admin/user/{telegram_id}")
async def get_user_detail(telegram_id: int, admin: dict = Depends(check_admin)):
    # Yangi db.py dagi maxsus funksiya orqali barchasini birdaniga olamiz
    user_info = await db.get_user_full_info(telegram_id)
    if not user_info: raise HTTPException(404, "Foydalanuvchi topilmadi")
    return user_info


@app.post("/api/admin/user/block")
async def block_user(req: AdminActionRequest, admin: dict = Depends(check_admin)):
    ok = await db.block_user(req.telegram_id)
    if not ok: raise HTTPException(404, "Foydalanuvchi topilmadi")
    return {"status": "success"}


@app.post("/api/admin/user/unblock")
async def unblock_user(req: AdminActionRequest, admin: dict = Depends(check_admin)):
    ok = await db.unblock_user(req.telegram_id)
    if not ok: raise HTTPException(404, "Foydalanuvchi topilmadi")
    return {"status": "success"}


@app.post("/api/admin/user/balance")
async def add_balance(req: AdminActionRequest, admin: dict = Depends(check_admin)):
    if req.amount is None or req.amount == 0: raise HTTPException(400, "To'g'ri summani kiriting")
    op = "add" if req.amount > 0 else "subtract"
    try:
        new_bal = await db.update_user_balance(req.telegram_id, abs(req.amount), op)
    except ValueError as e: raise HTTPException(400, str(e))
    except Exception as e: raise HTTPException(500, str(e)[:200])

    if api_bot:
        try:
            msg = f"✅ Hisobingizga {req.amount:,} so'm qo'shildi." if req.amount > 0 else f"⚠️ Hisobingizdan {abs(req.amount):,} so'm yechildi."
            await api_bot.send_message(req.telegram_id, f"{msg}\n\n💰 Joriy balans: {new_bal:,} so'm")
        except Exception: pass
    return {"status": "success", "new_balance": new_bal}


@app.post("/api/admin/user/add-score")
async def add_score(req: AdminAddScoreRequest, admin: dict = Depends(check_admin)):
    ok = await db.add_score_by_phone_batch(req.phone, req.score)
    if not ok: raise HTTPException(404, "Bunday telefon raqamli foydalanuvchi topilmadi")
    return {"status": "success", "message": f"{req.score:+d} ball qo'shildi"}


# ==============================================================================
# 9. ADMIN — REKLAMALAR
# ==============================================================================

@app.get("/api/admin/pending_ads")
async def get_pending_ads(admin: dict = Depends(check_admin)):
    return await db.get_pending_ads()


@app.get("/api/admin/ads")
async def get_all_ads(admin: dict = Depends(check_admin), status: str = None):
    return await db.get_all_ads(status_filter=status)


@app.post("/api/admin/ads/approve/{ad_id}")
async def approve_ad(ad_id: int, admin: dict = Depends(check_admin)):
    async with db.pool.acquire() as conn:
        ad_row = await conn.fetchrow("SELECT * FROM ads WHERE id = $1", ad_id)
    if not ad_row: raise HTTPException(404, "Reklama topilmadi")

    ad_data = dict(ad_row)
    if ad_data["status"] == "approved": raise HTTPException(400, "Reklama allaqachon tasdiqlangan")

    msg_info = None
    if ad_data.get("tariff") in ("channel_only", "web_and_channel", "bot"):
        try:
            msg_info = await _post_ad_to_channel(ad_data)
        except HTTPException: raise
        except Exception as e: raise HTTPException(500, f"Kanalga yuborilmadi: {str(e)[:200]}")

    await db.update_ad_status(ad_id, "approved", channel_message_id=msg_info["message_id"] if msg_info else None)

    if api_bot:
        try:
            await api_bot.send_message(ad_data["user_id"], "✅ <b>Sizning e'loningiz tasdiqlandi va kanalga joylandi!</b>")
        except Exception: pass

    return {"status": "success", "message": "Reklama tasdiqlandi", "channel_message_id": msg_info["message_id"] if msg_info else None}


@app.post("/api/admin/ads/reject/{ad_id}")
async def reject_ad(ad_id: int, req: AdminPaymentAction, admin: dict = Depends(check_admin)):
    async with db.pool.acquire() as conn:
        ad_row = await conn.fetchrow("SELECT * FROM ads WHERE id = $1", ad_id)
    if not ad_row: raise HTTPException(404, "Reklama topilmadi")

    ad_data = dict(ad_row)
    reason = (req.reason or "Sabab ko'rsatilmadi")[:500]
    await db.update_ad_status(ad_id, "rejected", reason=reason)

    if api_bot:
        try:
            await api_bot.send_message(ad_data["user_id"], f"❌ <b>E'loningiz rad etildi.</b>\n\nSabab: {reason}")
        except Exception: pass
    return {"status": "success", "message": "Reklama rad etildi"}


@app.delete("/api/admin/ads/{ad_id}")
async def admin_delete_ad(ad_id: int, admin: dict = Depends(check_admin)):
    async with db.pool.acquire() as conn:
        result = await conn.execute("DELETE FROM ads WHERE id = $1", ad_id)
    if result == "DELETE 0": raise HTTPException(404, "Reklama topilmadi")
    return {"status": "success", "message": "Reklama o'chirildi"}


# 🔴 ADMIN UCHUN REKLAMANI TAHRIRLASH API'si QO'SHILDI
@app.post("/api/admin/ads/{ad_id}/edit")
async def admin_edit_ad(ad_id: int, req: AdEditRequest, admin: dict = Depends(check_admin)):
    async with db.pool.acquire() as conn:
        ad_row = await conn.fetchrow("SELECT * FROM ads WHERE id = $1", ad_id)
    if not ad_row: raise HTTPException(404, "Reklama topilmadi")
    
    update_data = req.dict(exclude_unset=True)
    if not update_data: raise HTTPException(400, "O'zgartirish uchun ma'lumot yo'q")
    
    await db.update_ad_details(ad_id, **update_data)
    return {"status": "success", "message": "Reklama tahrirlandi"}


# ==============================================================================
# 10. ADMIN — BOT VA SOZLAMALAR
# ==============================================================================

@app.post("/api/admin/bot/toggle")
async def toggle_bot(admin: dict = Depends(check_admin)):
    current = await db.get_setting("bot_enabled", "1")
    new_val = "0" if current == "1" else "1"
    await db.set_setting("bot_enabled", new_val)
    return {"status": "success", "bot_enabled": new_val == "1"}


# 🔴 YANGI: SOZLAMALARNI OLISH VA SAQLASH API'si
@app.get("/api/admin/settings")
async def get_settings(admin: dict = Depends(check_admin)):
    ad_days = await db.get_setting("ad_duration_days", str(Settings.WEB_AD_DAYS))
    bot_enabled = await db.get_setting("bot_enabled", "1")
    return {
        "ad_duration_days": int(ad_days) if ad_days.isdigit() else Settings.WEB_AD_DAYS,
        "bot_enabled": bot_enabled == "1"
    }


@app.post("/api/admin/settings")
async def update_settings(req: SettingsUpdateRequest, admin: dict = Depends(check_admin)):
    if req.ad_duration_days is not None:
        if req.ad_duration_days < 1 or req.ad_duration_days > 365:
            raise HTTPException(400, "Muddat 1 kundan 365 kungacha bo'lishi kerak")
        await db.set_setting("ad_duration_days", str(req.ad_duration_days))
    
    return {"status": "success", "message": "Sozlamalar saqlandi"}


# ==============================================================================
# 11. ADMIN — KONKURS VA REFERRAL
# ==============================================================================

@app.get("/api/admin/participants")
async def get_participants(admin: dict = Depends(check_admin)):
    return await db.get_top_participants(min_score=15)


@app.get("/api/admin/referrals/{telegram_id}")
async def get_referrals(telegram_id: int, admin: dict = Depends(check_admin)):
    refs = await db.get_referrals_by_user(telegram_id)
    referrer = await db.get_referrer_of_user(telegram_id)
    return {"referrals": refs, "referrer": referrer}


# ==============================================================================
# 12. ADMIN — USERBOT (Kengaytirilgan)
# ==============================================================================

userbot_temp_sessions: dict = {}


@app.get("/api/admin/userbot/sessions")
async def list_userbot_sessions(admin: dict = Depends(check_admin)):
    return await db.get_all_userbot_sessions()


@app.post("/api/admin/userbot/send_code")
async def userbot_send_code(req: UserbotRequestCode, admin: dict = Depends(check_admin)):
    try:
        client = TelegramClient(StringSession(), api_id=UserbotConfig.API_ID, api_hash=UserbotConfig.API_HASH)
        await client.connect()
        sent_code = await client.send_code_request(req.phone)
        userbot_temp_sessions[req.phone] = {
            "client": client,
            "phone_code_hash": sent_code.phone_code_hash,
            "created_at": datetime.utcnow(),
        }
        return {"status": "success", "message": "Kod yuborildi"}
    except Exception as e:
        logger.exception("userbot_send_code xatosi")
        raise HTTPException(400, f"Xatolik: {str(e)[:200]}")


@app.post("/api/admin/userbot/verify_code")
async def userbot_verify_code(req: UserbotVerifyCode, admin: dict = Depends(check_admin)):
    session_data = userbot_temp_sessions.get(req.phone)
    if not session_data: raise HTTPException(400, "Avval kod so'rang")

    client: TelegramClient = session_data["client"]
    phone_code_hash = session_data["phone_code_hash"]

    try:
        await client.sign_in(req.phone, req.code, phone_code_hash=phone_code_hash)
    except SessionPasswordNeededError:
        if not req.password: raise HTTPException(401, "Ikkinchi bosqich paroli (2FA) kerak")
        try: await client.sign_in(password=req.password)
        except Exception as e: raise HTTPException(400, f"2FA parol xato: {str(e)[:200]}")
    except Exception as e:
        raise HTTPException(400, f"Kod xato: {str(e)[:200]}")

    session_string = client.session.save()

    try:
        async with db.pool.acquire() as conn:
            await conn.execute("UPDATE userbot_sessions SET is_active = FALSE")
            await conn.execute("INSERT INTO userbot_sessions (phone, session_string, is_active) VALUES ($1, $2, TRUE)", req.phone, session_string)
    except Exception as e:
        await client.disconnect()
        raise HTTPException(500, f"Sessiya saqlanmadi: {str(e)[:200]}")

    await client.disconnect()
    userbot_temp_sessions.pop(req.phone, None)

    return {"status": "success", "message": "Userbot qo'shildi. Botni qayta ishga tushiring!"}


@app.post("/api/admin/userbot/logout")
async def userbot_logout(admin: dict = Depends(check_admin)):
    await db.deactivate_all_userbots()
    for phone, data in list(userbot_temp_sessions.items()):
        try: await data["client"].disconnect()
        except Exception: pass
        userbot_temp_sessions.pop(phone, None)
    return {"status": "success", "message": "Barcha sessiyalar o'chirildi"}


# ==============================================================================
# STARTUP / SHUTDOWN
# ==============================================================================

@app.on_event("startup")
async def startup():
    await db.connect()
    logger.info("✅ API va Database ishga tushdi")
    logger.info(f"🤖 Bot: {BotConfig.BOT_USERNAME}")


@app.on_event("shutdown")
async def shutdown():
    for phone, data in list(userbot_temp_sessions.items()):
        try: await data["client"].disconnect()
        except Exception: pass
        userbot_temp_sessions.pop(phone, None)

    if api_bot is not None:
        try: await api_bot.session.close()
        except Exception: pass

    await db.disconnect()
    logger.info("🔌 API to'xtatildi")


if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=False)
