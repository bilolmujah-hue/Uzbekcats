# ==============================================================================
# LOYIHA: UzbekCats Bot & Web App
# FAYL: bot.py
# TAVSIF: To'liq, xatosiz, Web App va yangi DB strukturasiga to'liq moslashgan.
# ==============================================================================

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta
from html import escape as html_escape

from aiogram import Bot, Dispatcher, F, Router, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BotCommand, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, Message, ReplyKeyboardMarkup, ReplyKeyboardRemove,
    ChatPermissions, InputMediaPhoto, InputMediaVideo
)

from telethon import TelegramClient, events
from telethon.sessions import StringSession

from config import BotConfig, DataLists, Prices, Settings, Texts, UserbotConfig
from db import db

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# =====================================================================
# BOT VA DISPATCHER
# =====================================================================
bot = Bot(
    token=BotConfig.BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()
router = Router()
dp.include_router(router)

CHANNEL_SOTISH_ID = BotConfig.CHANNEL_SOTISH_ID
CHANNEL_HADIYA_ID = BotConfig.CHANNEL_HADIYA_ID
CHANNEL_SOTISH_LINK = BotConfig.CHANNEL_SOTISH_LINK
CHANNEL_HADIYA_LINK = BotConfig.CHANNEL_HADIYA_LINK
BOT_LINK = BotConfig.BOT_LINK

userbot_client: TelegramClient | None = None

# =====================================================================
# YORDAMCHI FUNKSIYALAR
# =====================================================================
async def safe_answer(call: CallbackQuery, text: str = None, show_alert: bool = False):
    try:
        await call.answer(text=text, show_alert=show_alert)
    except TelegramBadRequest:
        pass

async def safe_edit_text(message: Message, text: str, reply_markup=None):
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest:
        try:
            await message.delete()
        except:
            pass
        await message.answer(text, reply_markup=reply_markup)

async def safe_delete(message: Message):
    try:
        await message.delete()
    except:
        pass

# =====================================================================
# USERBOT (EOF XATOSI TUZATILGAN)
# =====================================================================
async def start_userbot(session_string: str):
    global userbot_client
    if not session_string or len(session_string) < 10:
        return
    try:
        if userbot_client and userbot_client.is_connected():
            await userbot_client.disconnect()

        userbot_client = TelegramClient(
            StringSession(session_string),
            api_id=UserbotConfig.API_ID,
            api_hash=UserbotConfig.API_HASH,
        )
        await userbot_client.connect()

        if not await userbot_client.is_user_authorized():
            logger.error("❌ Userbot sessiyasi yaroqsiz! Qaytadan ulang.")
            await userbot_client.disconnect()
            userbot_client = None
            return

        logger.info("✅ Userbot ishga tushdi")

        @userbot_client.on(events.NewMessage(chats=UserbotConfig.TARGET_BOT))
        async def handler(event):
            text = event.message.text or ""
            m = re.search(UserbotConfig.CARD_TRANSFER_REGEX, text)
            if not m:
                return
            try:
                amount = int(m.group(1).replace(" ", ""))
                last4 = m.group(2)
                user_id = await db.match_userbot_payment(amount, last4)
                if user_id:
                    try:
                        await bot.send_message(user_id, Texts.TOPUP_PAID.format(amount=amount))
                    except Exception:
                        pass
            except Exception as e:
                logger.warning(f"Userbot to'lovini tahlil qilishda xato: {e}")

    except Exception as e:
        logger.error(f"❌ Userbot ishga tushish xatosi: {e}")
        userbot_client = None

# =====================================================================
# MAJBURIY OBUNA
# =====================================================================
async def check_subscription(user_id: int) -> tuple[bool, bool]:
    sotish_ok = hadiya_ok = False
    for chat_id, key in [(CHANNEL_SOTISH_ID, "sotish"), (CHANNEL_HADIYA_ID, "hadiya")]:
        try:
            m = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
            status = getattr(m.status, "value", m.status)
            ok = status in ("member", "administrator", "creator")
            if status == "restricted":
                ok = getattr(m, "is_member", False)
            if key == "sotish":
                sotish_ok = ok
            else:
                hadiya_ok = ok
        except Exception:
            pass
    return sotish_ok, hadiya_ok

def get_sub_text(sotish_ok: bool, hadiya_ok: bool) -> str:
    footer = "✅ <b>Barcha kanallarga obuna bo'lgansiz!</b>" if (sotish_ok and hadiya_ok) else "Obuna bo'lgach, <b>«🔄 Tekshirish»</b> tugmasini bosing."
    return Texts.SUB_REQUIRED_TEXT.format(
        sotish_icon="✅" if sotish_ok else "❌",
        hadiya_icon="✅" if hadiya_ok else "❌",
        footer=footer,
    )

def get_subscription_kb(sotish_ok: bool, hadiya_ok: bool) -> InlineKeyboardMarkup:
    kb = []
    if sotish_ok:
        kb.append([InlineKeyboardButton(text="✅ Sotish kanali", callback_data="noop")])
    else:
        kb.append([InlineKeyboardButton(text="📢 Sotish kanalga obuna", url=CHANNEL_SOTISH_LINK)])
    if hadiya_ok:
        kb.append([InlineKeyboardButton(text="✅ Hadiya kanali", callback_data="noop")])
    else:
        kb.append([InlineKeyboardButton(text="🎁 Hadiya kanalga obuna", url=CHANNEL_HADIYA_LINK)])
    kb.append([InlineKeyboardButton(text="🔄 Tekshirish", callback_data="check_sub")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

# =====================================================================
# FSM HOLATLARI
# =====================================================================
class RegStates(StatesGroup):
    checking_subscription = State()
    waiting_phone = State()

class AdStates(StatesGroup):
    choosing_cat_count = State()
    choosing_media_type = State()
    waiting_media = State()
    choosing_breed = State()
    custom_breed = State()
    choosing_age = State()
    choosing_health = State()
    choosing_gender = State()
    choosing_sterilization = State()
    waiting_address = State()
    waiting_phone = State()
    choosing_currency = State()
    waiting_price = State()
    preview = State()

class AdminStates(StatesGroup):
    add_balance_user_id = State()
    add_balance_amount = State()
    add_score_batch = State()
    decline_reason = State()
    editing_ad_field = State()
    editing_ad_value = State()

# =====================================================================
# KLAVIATURALAR
# =====================================================================
def get_main_menu_kb(is_admin: bool = False) -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton(text="📢 Kanalga reklama bermoqchiman", callback_data="menu_reklama")],
        [InlineKeyboardButton(text="🏆 Konkurs", callback_data="menu_konkurs")],
        [InlineKeyboardButton(text="💳 Hisobni to'ldirish", web_app=types.WebAppInfo(url=f"{BotConfig.WEB_APP_URL}?page=topup"))],
        [InlineKeyboardButton(text="📋 Mening e'lonlarim", callback_data="menu_my_orders")],
        [InlineKeyboardButton(text="ℹ️ Bot haqida", callback_data="menu_about")],
        [InlineKeyboardButton(text="👤 Admin bilan bog'lanish", callback_data="menu_admin")],
        [InlineKeyboardButton(text="🖥️ Web App'ni ochish", web_app=types.WebAppInfo(url=BotConfig.WEB_APP_URL))],
    ]
    if is_admin:
        kb.append([InlineKeyboardButton(text="👨‍💼 Admin paneli", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_phone_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📞 Raqamni yuborish", request_contact=True)]], resize_keyboard=True, one_time_keyboard=True)

def get_ad_type_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Mushukimni sotmoqchiman", callback_data="adtype_sotish")],
        [InlineKeyboardButton(text="🎁 Mushukimni hadiyaga bermoqchiman", callback_data="adtype_hadiya")],
        [InlineKeyboardButton(text="↩️ Asosiy menyuga qaytish", callback_data="menu_back_to_main")],
    ])

def get_media_type_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖼️ Rasm yuboraman", callback_data="media_photo")],
        [InlineKeyboardButton(text="🎥 Video yuboraman (1 daqiqagacha)", callback_data="media_video")],
        [InlineKeyboardButton(text="↩️ Orqaga", callback_data="menu_reklama")],
    ])

def get_preview_kb(balance: int, price: int) -> InlineKeyboardMarkup:
    kb = []
    if balance < price:
        kb.append([InlineKeyboardButton(text="💳 Hisobni to'ldirish", web_app=types.WebAppInfo(url=f"{BotConfig.WEB_APP_URL}?page=topup"))])
    kb.append([InlineKeyboardButton(text="✅ Ha, roziman va Tasdiqlash", callback_data="preview_confirm")])
    kb.append([InlineKeyboardButton(text="❌ Bekor qilish", callback_data="menu_reklama")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_viloyat_kb() -> InlineKeyboardMarkup:
    kb = [[InlineKeyboardButton(text=v, callback_data="viloyat_" + v.lower().replace(" ", "_").replace("'", ""))] for v in DataLists.VILOYATLAR]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_breed_kb(page: int = 0) -> InlineKeyboardMarkup:
    kb, row = [], []
    for i, breed in enumerate(DataLists.BREEDS[page]):
        row.append(InlineKeyboardButton(text=breed, callback_data=f"breed_{page}_{i}"))
        if len(row) == 2:
            kb.append(row)
            row = []
    if row:
        kb.append(row)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"breed_page_{page-1}"))
    if page < len(DataLists.BREEDS) - 1:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"breed_page_{page+1}"))
    if nav:
        kb.append(nav)
    kb.append([InlineKeyboardButton(text="✏️ O'zim yozaman", callback_data="breed_custom")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_age_kb() -> InlineKeyboardMarkup:
    kb, row = [], []
    for age in DataLists.AGES:
        cb = age.replace(" ", "_").replace(",", "")
        row.append(InlineKeyboardButton(text=age, callback_data=f"age_{cb}"))
        if len(row) == 3:
            kb.append(row)
            row = []
    if row:
        kb.append(row)
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_simple_kb(options: list, prefix: str) -> InlineKeyboardMarkup:
    kb = [[InlineKeyboardButton(text=text, callback_data=f"{prefix}_{val}")] for text, val in options]
    return InlineKeyboardMarkup(inline_keyboard=kb)

# =====================================================================
# KANALGA POST ("message is not modified" tuzatilgan, JSON qo'llab-quvvatlanadi)
# =====================================================================
async def post_to_channel(ad_data: dict):
    ad_type = ad_data.get("ad_type")
    cats_data = ad_data.get("cats_data") or []
    address = html_escape(str(ad_data.get("address") or "—"))
    phone = html_escape(str(ad_data.get("phone") or "—"))
    price = html_escape(str(ad_data.get("price") or "0"))
    currency = html_escape(str(ad_data.get("currency") or "so'm"))

    footer = (
        '👤 <a href="https://t.me/zayd_catlover">Admin</a>\n'
        '📢 <a href="https://t.me/Uzbek_cat_bot?start=reklama">Reklama berish</a>\n\n'
        '<a href="https://youtu.be/vdwgSB7_amw">YouTube</a> | <a href="https://www.instagram.com/p/C-cZkgstVGK/">Instagram</a> | <a href="https://t.me/uzbek_cats">Telegram</a>'
    )

    cats_text = ""
    if cats_data:
        for i, cat in enumerate(cats_data):
            c_breed = html_escape(str(cat.get('breed', '—')))
            c_age = html_escape(str(cat.get('age', '—')))
            c_gender = html_escape(str(cat.get('gender', '—')))
            c_health = html_escape(str(cat.get('health', '—')))
            cats_text += f"🐱 <b>{i+1}-mushuk:</b> {c_breed} | {c_age} | {c_gender} | {c_health}\n"
    else:
        c_breed = html_escape(str(ad_data.get("breed") or "—"))
        c_age = html_escape(str(ad_data.get("age") or "—"))
        cats_text = f"🐱 {c_breed} | {c_age}\n"

    if ad_type == "sotish":
        caption = f"#SOTILADI 💰\n\n{cats_text}\n📍 Manzil: {address}\n💵 Narxi: {price} {currency}\n📞 Tel: {phone}\n\n{footer}"
        target = CHANNEL_SOTISH_ID
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎁 Hadiya kanal", url=CHANNEL_HADIYA_LINK)], [InlineKeyboardButton(text="📢 Reklama berish", url=BOT_LINK)]])
    else:
        caption = f"#HADIYA 🎁\n\n{cats_text}\n📍 Manzil: {address}\n📞 Tel: {phone}\n\n{footer}"
        target = CHANNEL_HADIYA_ID
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💰 Sotiladi kanal", url=CHANNEL_SOTISH_LINK)], [InlineKeyboardButton(text="📢 Reklama berish", url=BOT_LINK)]])

    photos = ad_data.get("photos") or []
    if isinstance(photos, str):
        try: photos = json.loads(photos)
        except: photos = []

    # URL dan fayl nomini olish
    if photos:
        photo_val = photos[0]
        if photo_val.startswith("/uploads/"):
            # Web App'dan kelgan rasm
            import os
            from aiogram.types import FSInputFile
            filename = photo_val.split("/")[-1]
            filepath = os.path.join("uploads", filename)
            if os.path.exists(filepath):
                photo_val = FSInputFile(filepath)
            else:
                photo_val = None
        else:
            # Bot orqali kelgan file_id
            pass
    else:
        photo_val = None

    try:
        if len(photos) > 1:
            media_group = []
            for i, p in enumerate(photos):
                media_obj = None
                if p.startswith("/uploads/"):
                    import os
                    from aiogram.types import FSInputFile
                    filepath = os.path.join("uploads", p.split("/")[-1])
                    if os.path.exists(filepath):
                        media_obj = FSInputFile(filepath)
                else:
                    media_obj = p
                
                if not media_obj: continue

                if str(media_obj).startswith("BQAC") or (isinstance(media_obj, str) and media_obj.endswith(".mp4")):
                    media = InputMediaVideo(media=media_obj, caption=caption if i==0 else None, parse_mode=ParseMode.HTML)
                else:
                    media = InputMediaPhoto(media=media_obj, caption=caption if i==0 else None, parse_mode=ParseMode.HTML)
                media_group.append(media)
            
            if media_group:
                sent_messages = await bot.send_media_group(chat_id=target, media=media_group)
                sent = sent_messages[0]
                try:
                    await bot.edit_message_reply_markup(chat_id=target, message_id=sent.message_id, reply_markup=kb)
                except TelegramBadRequest as e:
                    if "message is not modified" not in str(e): raise e
                return sent
                
        if photo_val:
            if isinstance(photo_val, str) and (photo_val.startswith("BQAC") or photo_val.endswith(".mp4")):
                sent = await bot.send_video(chat_id=target, video=photo_val, caption=caption, reply_markup=kb)
            else:
                sent = await bot.send_photo(chat_id=target, photo=photo_val, caption=caption, reply_markup=kb)
        else:
            sent = await bot.send_message(chat_id=target, text=caption, reply_markup=kb)
        return sent
    except Exception as e:
        logger.error(f"❌ Kanalga yuborishda xato (chat={target}): {e}")
        raise

# =====================================================================
# MIDDLEWARE
# =====================================================================
async def check_user_middleware(handler, event: Message, data: dict):
    user_id = event.from_user.id
    if user_id in BotConfig.ADMIN_IDS:
        return await handler(event, data)
    text = event.text or ""
    if text.startswith("/start"):
        return await handler(event, data)

    if await db.get_setting("bot_enabled", "1") == "0":
        await event.answer(Texts.BOT_DISABLED)
        return

    user = await db.get_user(user_id)
    if user and user.get("is_banned"):
        await event.answer(Texts.USER_BANNED)
        return
    
    if await db.check_mute(user_id):
        await event.answer("❌ Siz vaqtincha yozish huquqidan mahrum qilingansiz. (24 soat)")
        return

    return await handler(event, data)

dp.message.middleware(check_user_middleware)

# =====================================================================
# TAQIQLANGAN SO'ZLAR
# =====================================================================
@router.message(F.chat.type.in_({"group", "supergroup"}), ~F.from_user.is_bot)
async def handle_banned_words(message: Message):
    if message.from_user.id in BotConfig.ADMIN_IDS:
        return
    text = message.text or ""
    if not text:
        return

    text_lower = text.lower()
    for word in DataLists.BANNED_WORDS:
        if word.lower() in text_lower:
            try: await message.delete()
            except: pass
            
            user_id = message.from_user.id
            warn_count = await db.add_warning(user_id)
            user_link = f'<a href="tg://user?id={user_id}">{html_escape(message.from_user.first_name)}</a>'
            
            if warn_count >= 3:
                await db.mute_user(user_id, hours=24)
                try:
                    await bot.restrict_chat_member(
                        chat_id=message.chat.id, user_id=user_id,
                        permissions=ChatPermissions(can_send_messages=False),
                        until_date=datetime.now() + timedelta(hours=24)
                    )
                except: pass
                warn_text = f"🚫 {user_link}, siz 3 marta qoidani buzdingiz! 1 kunga yozish huquqidan mahrum qilindingiz."
            else:
                warn_text = f"⚠️ {user_link}, Iltimos reklama tarqatmang!\n\nSiz {warn_count}-marta reklama tarqatdingiz. Yana {3 - warn_count} ta reklama tarqatsangiz, 1 kunga bloklanasiz."
            
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📢 Reklama berish", url=BOT_LINK)]])
            await message.answer(warn_text, reply_markup=kb)
            return

# =====================================================================
# START VA RO'YXATDAN O'TISH
# =====================================================================
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    
    if user and user.get("is_banned"):
        await message.answer(Texts.USER_BANNED)
        return
    if user:
        await message.answer(Texts.MAIN_MENU, reply_markup=get_main_menu_kb(user_id in BotConfig.ADMIN_IDS))
        return

    args = message.text.split(maxsplit=1)
    if len(args) > 1 and args[1].startswith("REF"):
        await state.update_data(referral_code=args[1])

    if Settings.REQUIRE_SUBSCRIPTION:
        sotish_ok, hadiya_ok = await check_subscription(user_id)
        await message.answer(get_sub_text(sotish_ok, hadiya_ok), reply_markup=get_subscription_kb(sotish_ok, hadiya_ok))
        await state.set_state(RegStates.checking_subscription)
    else:
        await message.answer(Texts.START_TEXT, reply_markup=get_phone_kb())
        await state.set_state(RegStates.waiting_phone)

@router.callback_query(F.data == "noop")
async def cb_noop(call: CallbackQuery):
    await safe_answer(call, Texts.SUB_OK_ALERT)

@router.callback_query(F.data == "check_sub")
async def cb_check_sub(call: CallbackQuery, state: FSMContext):
    sotish_ok, hadiya_ok = await check_subscription(call.from_user.id)
    if sotish_ok and hadiya_ok:
        await safe_edit_text(call.message, "✅ Obuna tasdiqlandi!")
        await call.message.answer(Texts.START_TEXT, reply_markup=get_phone_kb())
        await state.set_state(RegStates.waiting_phone)
        return
    try:
        await call.message.edit_text(get_sub_text(sotish_ok, hadiya_ok), reply_markup=get_subscription_kb(sotish_ok, hadiya_ok))
    except: pass
    await safe_answer(call, "❌ Iltimos, barcha kanallarga obuna bo'ling!", show_alert=True)

@router.message(RegStates.waiting_phone, F.contact | F.text)
async def process_phone(message: Message, state: FSMContext):
    phone = message.contact.phone_number if message.contact else (message.text or "").strip()
    if not message.contact and not re.match(r"^\+?998\d{9}$", phone.replace(" ", "")):
        await message.answer(Texts.ASK_PHONE)
        return
    phone = phone if phone.startswith("+") else f"+{phone}"

    full_name = f"{message.from_user.first_name} {message.from_user.last_name or ''}".strip()
    username = f"@{message.from_user.username}" if message.from_user.username else "Noma'lum"
    data = await state.get_data()
    
    try:
        user = await db.create_user(message.from_user.id, username, full_name, phone, data.get("referral_code"))
    except Exception as e:
        await message.answer(f"❌ Xatolik: {e}")
        return

    await message.answer(Texts.REG_SUCCESS.format(user_number=user["user_number"], score=user["score"], referrals=0), reply_markup=ReplyKeyboardRemove())
    await message.answer(Texts.MAIN_MENU, reply_markup=get_main_menu_kb(message.from_user.id in BotConfig.ADMIN_IDS))
    await state.clear()

# =====================================================================
# ASOSIY MENYU VA KONKURS
# =====================================================================
@router.callback_query(F.data == "menu_back_to_main")
async def back_to_main(call: CallbackQuery):
    await safe_edit_text(call.message, Texts.MAIN_MENU, reply_markup=get_main_menu_kb(call.from_user.id in BotConfig.ADMIN_IDS))

@router.callback_query(F.data == "menu_konkurs")
async def menu_konkurs(call: CallbackQuery):
    user = await db.get_user(call.from_user.id)
    ref_link = f"https://t.me/{BotConfig.BOT_USERNAME.replace('@', '')}?start=REF{user['id']}"
    
    text = "🏆 <b>Konkurs</b>\n\n"
    text += f"👥 Sizning ballaringiz: <b>{user['score']} ball</b>\n"
    text += f"🔗 Sizning linkingiz:\n<code>{ref_link}</code>\n\n"
    text += "Do'stlaringizni taklif qiling va ball to'plang!\n"
    text += "Eng ko'p ball to'plagan 10 kishi g'olib bo'ladi."
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Ulashish", url=f"https://t.me/share/url?url={ref_link}")],
        [InlineKeyboardButton(text="🏆 Reyting (Top 10)", callback_data="menu_rating")],
        [InlineKeyboardButton(text="↩️ Orqaga", callback_data="menu_back_to_main")],
    ])
    await safe_edit_text(call.message, text, reply_markup=kb)

@router.callback_query(F.data == "menu_rating")
async def menu_rating(call: CallbackQuery):
    top_users = await db.get_top_users(limit=10)
    text = "🥇 <b>Eng faol foydalanuvchilar (Top 10)</b>\n\n"
    if not top_users:
        text += "Hozircha reyting mavjud emas."
    else:
        for i, u in enumerate(top_users, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            name_safe = html_escape(u['full_name'] or 'Foydalanuvchi')
            text += f"{medal} {name_safe} — <b>{u['score']} ball</b>\n"
            
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="↩️ Orqaga", callback_data="menu_konkurs")]])
    await safe_edit_text(call.message, text, reply_markup=kb)

@router.callback_query(F.data == "menu_reklama")
async def menu_reklama(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await safe_edit_text(call.message, Texts.AD_TYPE_SELECT, reply_markup=get_ad_type_kb())

@router.callback_query(F.data == "menu_about")
async def menu_about(call: CallbackQuery):
    text = "ℹ️ <b>Bot haqida</b>\n\nUshbu bot orqali siz mushuklar haqida e'lon berishingiz, ularni sotishingiz yoki hadiya qilishingiz mumkin.\n\n🎁 Hadiya e'lonlari mutlaqo bepul.\n💰 Sotish uchun e'lonlar to'lov asosida."
    await safe_edit_text(call.message, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="↩️ Orqaga", callback_data="menu_back_to_main")]]))

@router.callback_query(F.data == "menu_admin")
async def menu_admin(call: CallbackQuery):
    text = "👤 <b>Admin bilan bog'lanish</b>\n\n👨‍💻 Texnik Admin: @It_project_2026\n📞 +998900512621\n\n👨‍💼 Bosh Admin: @zayd_catlover\n📞 +998934938181"
    await safe_edit_text(call.message, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="↩️ Orqaga", callback_data="menu_back_to_main")]]))

# =====================================================================
# MENING E'LONLARIM
# =====================================================================
@router.callback_query(F.data == "menu_my_orders")
async def menu_my_orders(call: CallbackQuery):
    ads = await db.get_user_ads(call.from_user.id)
    
    await safe_edit_text(call.message, "⏳ E'lonlaringiz yuklanmoqda...", reply_markup=None)
    
    if not ads:
        await call.message.answer(Texts.NO_ADS, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="↩️ Orqaga", callback_data="menu_back_to_main")]]))
        return

    st_map = {"pending": "⏳ Kutilmoqda", "approved": "✅ Tasdiqlangan", "rejected": "❌ Rad etilgan", "sold": "💰 Sotilgan", "expired": "⏰ Muddati o'tgan"}
    
    for ad in ads:
        st = st_map.get(ad["status"], ad["status"])
        cats_data = ad.get("cats_data") or []
        if cats_data:
            breed = html_escape(cats_data[0].get('breed', '—')) + " va boshqalar"
        else:
            breed = html_escape(str(ad.get("breed") or "—"))
            
        text = f"🐱 <b>{breed}</b> | {st}\n📅 {ad['created_at'].strftime('%d.%m.%Y')}"
        
        kb = None
        if ad["status"] == "approved":
            action_text = "✅ Berib bo'ldim" if ad["ad_type"] == "hadiya" else "💰 Sotildi"
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=action_text, callback_data=f"user_ad_done_{ad['id']}")]])
            
        photos = ad.get("photos") or []
        if isinstance(photos, str):
            try: photos = json.loads(photos)
            except: photos = []
            
        if photos:
            from aiogram.types import FSInputFile
            p0 = photos[0]
            if p0.startswith("/uploads/"):
                import os
                filepath = os.path.join("uploads", p0.split("/")[-1])
                if os.path.exists(filepath):
                    await call.message.answer_photo(photo=FSInputFile(filepath), caption=text, reply_markup=kb)
                else:
                    await call.message.answer(text, reply_markup=kb)
            else:
                await call.message.answer_photo(photo=p0, caption=text, reply_markup=kb)
        else:
            await call.message.answer(text, reply_markup=kb)
            
    await call.message.answer("Barcha e'lonlaringiz ko'rsatildi.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="↩️ Asosiy menyu", callback_data="menu_back_to_main")]]))

@router.callback_query(F.data.startswith("user_ad_done_"))
async def user_mark_ad_done(call: CallbackQuery):
    ad_id = int(call.data.split("_")[3])
    ad = await db.get_ad(ad_id)
    
    if not ad or ad["user_id"] != call.from_user.id:
        await safe_answer(call, "Xatolik: E'lon topilmadi.", show_alert=True)
        return

    action_text = "BERILDI" if ad["ad_type"] == "hadiya" else "SOTILDI"
    await db.delete_ad(ad_id) # Bazadan o'chirish (yoki status 'sold' qilish mumkin, lekin siz o'chishni xohlagansiz)
    
    if ad.get("channel_message_id"):
        try:
            target_chat = CHANNEL_SOTISH_ID if ad["ad_type"] == "sotish" else CHANNEL_HADIYA_ID
            new_caption = f"#{action_text} 💰\n\n📝 Ushbu e'lon o'z egasini topdi!\n\n✅ <b>E'LON YOPILDI</b>"
            
            await bot.edit_message_caption(chat_id=target_chat, message_id=ad["channel_message_id"], caption=new_caption, reply_markup=None)
        except Exception as e:
            logger.error(f"Kanal xabarini tahrirlashda xato: {e}")

    await safe_answer(call, f"✅ E'lon {action_text.lower()} deb belgilandi!", show_alert=True)
    await safe_delete(call.message)

# =====================================================================
# REKLAMA JARAYONI (Bot orqali)
# =====================================================================
@router.callback_query(F.data.startswith("adtype_"))
async def choose_ad_type(call: CallbackQuery, state: FSMContext):
    ad_type = call.data.replace("adtype_", "")
    await state.update_data(ad_type=ad_type)
    if ad_type == "sotish":
        await safe_edit_text(call.message, "🐱 <b>Nechta mushuk sotmoqchisiz?</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"{i} ta mushuk", callback_data=f"catcount_{i}")] for i in range(1, 6)]))
        await state.set_state(AdStates.choosing_cat_count)
    else:
        await safe_edit_text(call.message, Texts.MEDIA_ASK, reply_markup=get_media_type_kb())
        await state.set_state(AdStates.choosing_media_type)

@router.callback_query(AdStates.choosing_cat_count, F.data.startswith("catcount_"))
async def process_cat_count(call: CallbackQuery, state: FSMContext):
    count = int(call.data.split("_")[1])
    await state.update_data(cat_count=count, bot_price=Prices.get_bot_price(count), current_cat_idx=0, cats_data=[])
    await safe_edit_text(call.message, Texts.MEDIA_ASK, reply_markup=get_media_type_kb())
    await state.set_state(AdStates.choosing_media_type)

@router.callback_query(F.data.startswith("media_"))
async def choose_media_type(call: CallbackQuery, state: FSMContext):
    media_type = call.data.replace("media_", "")
    await state.update_data(media_type=media_type, photos=[])
    text = "🖼️ <b>Mushuk rasmlarini yuboring (1-3 ta):</b>" if media_type == "photo" else "🎥 <b>Mushuk videosini yuboring (1 daqiqagacha):</b>"
    await safe_edit_text(call.message, text, reply_markup=None)
    await state.set_state(AdStates.waiting_media)

@router.message(AdStates.waiting_media, F.photo)
async def receive_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("media_type") != "photo":
        await message.answer("❌ Iltimos, faqat video yuboring!")
        return
    photos = data.get("photos", [])
    if len(photos) >= 3:
        await message.answer("❌ Maksimum 3 ta rasm.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➡️ Davom etish", callback_data="continue_process")]]))
        return
    
    photos.append(message.photo[-1].file_id)
    await state.update_data(photos=photos)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➡️ Davom etish", callback_data="continue_process")]])
    await message.answer(f"✅ <b>{len(photos)}-rasm qabul qilindi.</b>", reply_markup=kb)

@router.message(AdStates.waiting_media, F.video)
async def receive_video(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("media_type") != "video":
        await message.answer("❌ Iltimos, faqat rasm yuboring!")
        return
    if message.video.duration > 60:
        await message.answer("❌ Video 1 daqiqadan oshmasligi kerak.")
        return
    
    await state.update_data(photos=[message.video.file_id])
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➡️ Davom etish", callback_data="continue_process")]])
    await message.answer("✅ <b>Video qabul qilindi.</b>", reply_markup=kb)

@router.callback_query(AdStates.waiting_media, F.data == "continue_process")
async def process_continue_media(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("photos"):
        await safe_answer(call, "❌ Iltimos, media yuboring!", show_alert=True)
        return
    
    # Mushuk ma'lumotlarini yig'ishni boshlash
    data = await state.get_data()
    if data.get("ad_type") == "sotish":
        await state.update_data(current_cat_idx=0, cats_data=[])
        await safe_edit_text(call.message, "1-mushuk zotini tanlang:", reply_markup=get_breed_kb(0))
        await state.set_state(AdStates.choosing_breed)
    else:
        # Hadiya uchun bitta mushuk (idx=0)
        await state.update_data(current_cat_idx=0, cats_data=[])
        await safe_edit_text(call.message, "Mushuk zotini tanlang:", reply_markup=get_breed_kb(0))
        await state.set_state(AdStates.choosing_breed)

@router.callback_query(AdStates.choosing_breed, F.data.startswith("breed_page_"))
async def breed_page(call: CallbackQuery):
    page = int(call.data.split("_")[2])
    await call.message.edit_reply_markup(reply_markup=get_breed_kb(page))

@router.callback_query(AdStates.choosing_breed, F.data.startswith("breed_") & ~F.data.startswith("breed_page_") & ~F.data.startswith("breed_custom"))
async def process_breed(call: CallbackQuery, state: FSMContext):
    parts = call.data.split("_")
    breed = DataLists.BREEDS[int(parts[1])][int(parts[2])]
    await state.update_data(current_breed=breed)
    await safe_edit_text(call.message, "Yoshini tanlang:", reply_markup=get_age_kb())
    await state.set_state(AdStates.choosing_age)

@router.callback_query(AdStates.choosing_breed, F.data == "breed_custom")
async def custom_breed(call: CallbackQuery, state: FSMContext):
    await safe_edit_text(call.message, Texts.BREED_CUSTOM_ASK, reply_markup=None)
    await state.set_state(AdStates.custom_breed)

@router.message(AdStates.custom_breed)
async def process_custom_breed(message: Message, state: FSMContext):
    await state.update_data(current_breed=message.text)
    await message.answer("Yoshini tanlang:", reply_markup=get_age_kb())
    await state.set_state(AdStates.choosing_age)

@router.callback_query(AdStates.choosing_age, F.data.startswith("age_"))
async def process_age(call: CallbackQuery, state: FSMContext):
    age = call.data.replace("age_", "").replace("_", " ")
    await state.update_data(current_age=age)
    await safe_edit_text(call.message, Texts.HEALTH_ASK, reply_markup=get_simple_kb([("Sog'lom", "soglom"), ("Kasal", "kasal")], "health"))
    await state.set_state(AdStates.choosing_health)

@router.callback_query(AdStates.choosing_health, F.data.startswith("health_"))
async def process_health(call: CallbackQuery, state: FSMContext):
    await state.update_data(current_health="Sog'lom" if "soglom" in call.data else "Kasal")
    await safe_edit_text(call.message, Texts.GENDER_ASK, reply_markup=get_simple_kb([("♀️ Qiz bola", "qiz"), ("♂️ O'g'il bola", "ogil")], "gender"))
    await state.set_state(AdStates.choosing_gender)

@router.callback_query(AdStates.choosing_gender, F.data.startswith("gender_"))
async def process_gender(call: CallbackQuery, state: FSMContext):
    gender = "Qiz bola" if "qiz" in call.data else "O'g'il bola"
    await state.update_data(current_gender=gender)
    
    data = await state.get_data()
    idx = data.get("current_cat_idx", 0)
    total = data.get("cat_count", 1) if data.get("ad_type") == "sotish" else 1
    cats = data.get("cats_data", [])
    
    # Joriy mushukni saqlash
    cats.append({
        "breed": data.get("current_breed"),
        "age": data.get("current_age"),
        "health": data.get("current_health"),
        "gender": gender
    })
    await state.update_data(cats_data=cats)
    
    if idx + 1 < total:
        # Keyingi mushukka o'tish
        await state.update_data(current_cat_idx=idx+1)
        await safe_edit_text(call.message, f"<b>{idx+2}-mushuk zotini tanlang:</b>", reply_markup=get_breed_kb(0))
        await state.set_state(AdStates.choosing_breed)
    else:
        # Barcha mushuklar kiritildi, manzilga o'tish
        await safe_edit_text(call.message, Texts.ADDRESS_ASK, reply_markup=get_viloyat_kb())
        await state.set_state(AdStates.waiting_address)

@router.callback_query(AdStates.waiting_address, F.data.startswith("viloyat_"))
async def process_address(call: CallbackQuery, state: FSMContext):
    await state.update_data(address=call.data.replace("viloyat_", "").replace("_", " ").title())
    await safe_edit_text(call.message, Texts.AD_PHONE_ASK, reply_markup=None)
    await state.set_state(AdStates.waiting_phone)

@router.message(AdStates.waiting_phone)
async def process_ad_phone(message: Message, state: FSMContext):
    digits = re.sub(r"\D", "", message.text or "")
    if len(digits) != 12 or not digits.startswith("998"):
        await message.answer(Texts.AD_PHONE_INVALID)
        return
    await state.update_data(phone=f"+{digits}")
    data = await state.get_data()
    if data.get("ad_type") == "hadiya":
        await send_ad_preview(message, state)
    else:
        await message.answer(Texts.CURRENCY_ASK, reply_markup=get_simple_kb([("🇺🇿 So'mda", "som"), ("💵 Dollarda", "dollar")], "valyuta"))
        await state.set_state(AdStates.choosing_currency)

@router.callback_query(AdStates.choosing_currency, F.data.startswith("valyuta_"))
async def process_currency(call: CallbackQuery, state: FSMContext):
    await state.update_data(currency="so'm" if "som" in call.data else "$")
    await safe_edit_text(call.message, Texts.PRICE_ASK, reply_markup=None)
    await state.set_state(AdStates.waiting_price)

@router.message(AdStates.waiting_price)
async def process_price(message: Message, state: FSMContext):
    if not (message.text or "").isdigit():
        await message.answer(Texts.PRICE_INVALID)
        return
    await state.update_data(price=message.text)
    await send_ad_preview(message, state)

# =====================================================================
# PREVIEW (BOT UCHUN)
# =====================================================================
async def send_ad_preview(message: Message, state: FSMContext):
    data = await state.get_data()
    user = await db.get_user(message.from_user.id)
    price = data.get("bot_price", 0)
    
    caption = "📋 <b>Ma'lumotlaringizni tekshiring:</b>\n\n"
    
    for i, cat in enumerate(data.get("cats_data", [])):
        caption += f"🐱 <b>{i+1}-mushuk:</b> {cat['breed']} | {cat['age']} | {cat['gender']}\n"
    
    caption += f"\n📍 Manzil: {data.get('address')}\n📞 Tel: {data.get('phone')}\n"
    if data.get("ad_type") != "hadiya":
        caption += f"💰 Narx: {data.get('price')} {data.get('currency')}\n"
    
    if price > 0:
        caption += f"\n💳 <b>Hisobingiz:</b> {user['balance']:,} so'm\n"
        caption += f"💸 <b>Yechiladi:</b> {price:,} so'm\n\n"
        if user['balance'] < price:
            caption += "❌ <b>Diqqat! Mablag' yetarli emas.</b>"
        else:
            caption += "❓ <b>Tasdiqlaysizmi?</b>"
    
    photos = data.get("photos", [])
    kb = get_preview_kb(user['balance'], price)
    
    if photos:
        if data.get("media_type") == "video":
            await message.answer_video(video=photos[0], caption=caption, reply_markup=kb)
        else:
            await message.answer_photo(photo=photos[0], caption=caption, reply_markup=kb)
    else:
        await message.answer(caption, reply_markup=kb)
    await state.set_state(AdStates.preview)

@router.callback_query(AdStates.preview, F.data == "preview_confirm")
async def confirm_ad(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user = await db.get_user(call.from_user.id)
    price = data.get("bot_price", 0)
    
    if user["balance"] < price:
        await safe_answer(call, "❌ Hisobingizda mablag' yetarli emas!", show_alert=True)
        return
        
    if price > 0:
        try: await db.update_user_balance(user["id"], price, "subtract")
        except: return await safe_answer(call, "❌ Mablag' yechishda xatolik!", show_alert=True)

    new_ad = await db.create_ad(
        user_id=user["id"], 
        ad_type=data.get("ad_type"), 
        tariff="bot",
        photos=data.get("photos", []), 
        cats_data=data.get("cats_data", []),
        address=data.get("address"), 
        phone=data.get("phone"), 
        price=data.get("price", "0"),
        currency=data.get("currency", "so'm"), 
        cat_count=data.get("cat_count", 1), 
        price_paid=price,
    )

    await safe_delete(call.message)
    await bot.send_message(call.from_user.id, Texts.AD_ACCEPTED)

    # Adminga yuborish
    u_name = html_escape(user['username'] or '—')
    admin_caption = f"🆕 <b>YANGI REKLAMA (BOT)</b>\n\n👤 Foydalanuvchi: #{user['user_number']} ({u_name})\n🐱 Soni: {data.get('cat_count', 1)} ta\n💵 To'landi: {price:,} so'm"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"adm_ok_{new_ad['id']}"),
        InlineKeyboardButton(text="❌ Rad etish", callback_data=f"adm_no_{new_ad['id']}")
    ]])

    photos = data.get("photos", [])
    try:
        if photos:
            if data.get("media_type") == "video": 
                await bot.send_video(BotConfig.TECH_ADMIN_ID, video=photos[0], caption=admin_caption, reply_markup=kb)
            else: 
                await bot.send_photo(BotConfig.TECH_ADMIN_ID, photo=photos[0], caption=admin_caption, reply_markup=kb)
        else:
            await bot.send_message(BotConfig.TECH_ADMIN_ID, admin_caption, reply_markup=kb)
    except Exception as e: 
        logger.error(f"Admin xabar yuborishda xato: {e}")

    await state.clear()

# =====================================================================
# ADMIN TASDIQLASH VA RAD ETISH (Web App va Bot uchun umumiy)
# =====================================================================
@router.callback_query(F.data.startswith("adm_ok_"))
async def tech_admin_approve(call: CallbackQuery):
    if call.from_user.id not in BotConfig.ADMIN_IDS: return
    ad_id = int(call.data.split("_")[2])
    
    ad = await db.get_ad(ad_id)
    if not ad: 
        return await safe_answer(call, "E'lon topilmadi", show_alert=True)
    if ad["status"] != "pending":
        await call.message.edit_reply_markup(reply_markup=None)
        return await safe_answer(call, "⚠️ Bu e'lon allaqachon ko'rilgan!", show_alert=True)

    try: await call.message.edit_reply_markup(reply_markup=None)
    except: pass

    try:
        sent = await post_to_channel(ad)
        await db.update_ad_status(ad_id, "approved", channel_message_id=sent.message_id)
        
        action_text = "Berib bo'ldim" if ad["ad_type"] == "hadiya" else "Sotildi"
        user_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"✅ {action_text}", callback_data=f"user_ad_done_{ad_id}")]])
        
        await bot.send_message(ad["user_id"], f"✅ <b>Sizning e'loningiz tasdiqlandi va kanalga joylandi!</b>", reply_markup=user_kb)
        await safe_answer(call, "✅ Kanalga yuborildi!")
    except Exception as e:
        await safe_answer(call, f"❌ Xato: {e}", show_alert=True)

@router.callback_query(F.data.startswith("adm_no_"))
async def tech_admin_decline(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in BotConfig.ADMIN_IDS: return
    ad_id = int(call.data.split("_")[2])
    
    try: await call.message.edit_reply_markup(reply_markup=None)
    except: pass
    
    await state.update_data(decline_ad_id=ad_id)
    await call.message.reply("Rad etish sababini yozing:")
    await state.set_state(AdminStates.decline_reason)

@router.message(AdminStates.decline_reason)
async def process_decline_reason(message: Message, state: FSMContext):
    ad_id = (await state.get_data()).get("decline_ad_id")
    ad = await db.get_ad(ad_id)
    
    await db.update_ad_status(ad_id, "rejected", reason=message.text)
    
    if ad and ad.get("price_paid", 0) > 0:
        await db.update_user_balance(ad["user_id"], ad["price_paid"], "add")
        await bot.send_message(ad["user_id"], f"❌ <b>E'loningiz rad etildi.</b>\n\nSabab: {html_escape(message.text)}\n\nHisobingizga {ad['price_paid']:,} so'm qaytarildi.")
    elif ad:
        await bot.send_message(ad["user_id"], f"❌ <b>E'loningiz rad etildi.</b>\n\nSabab: {html_escape(message.text)}")

    await message.answer("✅ Rad etildi va pul qaytarildi.")
    await state.clear()

# =====================================================================
# STARTUP / SHUTDOWN
# =====================================================================
@dp.startup()
async def on_startup():
    await db.connect()
    try: await bot.set_my_commands([BotCommand(command="start", description="Botni ishga tushirish")])
    except: pass
    logger.info("🚀 Bot polling boshlandi")

    try:
        async with db.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT session_string FROM userbot_sessions WHERE is_active = TRUE LIMIT 1")
        if row and row["session_string"]:
            await start_userbot(row["session_string"])
    except Exception as e:
        logger.warning(f"Userbot yuklashda xato: {e}")

@dp.shutdown()
async def on_shutdown():
    if userbot_client and userbot_client.is_connected(): await userbot_client.disconnect()
    await db.disconnect()

async def main():
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
