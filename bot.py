# ==============================================================================
# LOYIHA: UzbekCats Bot & Web App
# FAYL: bot.py
# TAVSIF: Premium dizayn, to'liq funksiyalar, xatosiz Aiogram v3 bot
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
bot = Bot(token=BotConfig.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
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
    try: await call.answer(text=text, show_alert=show_alert)
    except TelegramBadRequest: pass

async def safe_edit_text(message: Message, text: str, reply_markup=None):
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower(): return
        try: await message.delete()
        except: pass
        await message.answer(text, reply_markup=reply_markup)

async def safe_delete(message: Message):
    try: await message.delete()
    except: pass

# =====================================================================
# USERBOT (EOF XATOSI TUZATILDI)
# =====================================================================
async def start_userbot(session_string: str):
    global userbot_client
    if not session_string or len(session_string) < 10:
        return
    try:
        if userbot_client and userbot_client.is_connected():
            await userbot_client.disconnect()
            
        userbot_client = TelegramClient(StringSession(session_string), api_id=UserbotConfig.API_ID, api_hash=UserbotConfig.API_HASH)
        await userbot_client.connect() # start() o'rniga connect()
        
        if not await userbot_client.is_user_authorized():
            logger.error("❌ Userbot sessiyasi eskirgan! Iltimos, qaytadan kod orqali ulang.")
            await userbot_client.disconnect()
            userbot_client = None
            return

        logger.info("✅ Userbot muvaffaqiyatli ishga tushdi")
        
        @userbot_client.on(events.NewMessage(chats=UserbotConfig.TARGET_BOT))
        async def handler(event):
            text = event.message.text or ""
            m = re.search(UserbotConfig.CARD_TRANSFER_REGEX, text)
            if not m: return
            try:
                amount = int(m.group(1).replace(" ", ""))
                last4 = m.group(2)
                user_id = await db.match_userbot_payment(amount, last4)
                if user_id:
                    try: await bot.send_message(user_id, Texts.TOPUP_PAID.format(amount=amount))
                    except: pass
            except Exception as e: 
                logger.warning(f"Userbot parse xatosi: {e}")
    except Exception as e: 
        logger.error(f"❌ Userbot xatosi: {e}")
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
            if status == "restricted": ok = getattr(m, "is_member", False)
            if key == "sotish": sotish_ok = ok
            else: hadiya_ok = ok
        except: pass
    return sotish_ok, hadiya_ok

def get_sub_kb(sotish_ok: bool, hadiya_ok: bool) -> InlineKeyboardMarkup:
    kb = []
    if sotish_ok: kb.append([InlineKeyboardButton(text="✅ Sotish kanali", callback_data="noop")])
    else: kb.append([InlineKeyboardButton(text="📢 Sotish kanaliga obuna", url=CHANNEL_SOTISH_LINK)])
    if hadiya_ok: kb.append([InlineKeyboardButton(text="✅ Hadiya kanali", callback_data="noop")])
    else: kb.append([InlineKeyboardButton(text="🎁 Hadiya kanaliga obuna", url=CHANNEL_HADIYA_LINK)])
    
    if not (sotish_ok and hadiya_ok): 
        kb.append([InlineKeyboardButton(text="🔄 Obunani tekshirish", callback_data="check_sub")])
    else: 
        kb.append([InlineKeyboardButton(text="➡️ Davom etish", callback_data="continue_reg")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

# =====================================================================
# FSM HOLATLARI
# =====================================================================
class RegStates(StatesGroup): 
    waiting_phone = State()

class AdStates(StatesGroup):
    cat_count = State()
    media_type = State()
    media = State()
    breed = State()
    custom_breed = State()
    age = State()
    health = State()
    gender = State()
    sterilization = State()
    address = State()
    phone = State()
    price = State()
    preview = State()

class AdminStates(StatesGroup): 
    balance_id = State()
    balance_amount = State()
    score = State()
    decline = State()
    edit_id = State()
    edit_val = State()

# =====================================================================
# PREMIUM MENYULAR VA KLAVIATURALAR
# =====================================================================
def main_menu(is_admin=False):
    kb = [
        [InlineKeyboardButton(text="🛒 E'lon joylashtirish", callback_data="menu_reklama")],
        [InlineKeyboardButton(text="🏆 Konkurs va Takliflar", callback_data="menu_konkurs")],
        [InlineKeyboardButton(text="💳 Hisobni to'ldirish", web_app=types.WebAppInfo(url=f"{BotConfig.WEB_APP_URL}?page=topup"))],
        [InlineKeyboardButton(text="📋 Mening e'lonlarim", callback_data="menu_my_orders")],
        [InlineKeyboardButton(text="ℹ️ Bot haqida ma'lumot", callback_data="menu_about")],
        [InlineKeyboardButton(text="👤 Qo'llab-quvvatlash (Admin)", callback_data="menu_admin")],
        [InlineKeyboardButton(text="🖥️ Premium Web App", web_app=types.WebAppInfo(url=BotConfig.WEB_APP_URL))],
    ]
    if is_admin: 
        kb.append([InlineKeyboardButton(text="👨‍💼 Boshqaruv paneli", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_phone_kb(): 
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📞 Raqamni ulashish", request_contact=True)]], resize_keyboard=True, one_time_keyboard=True)

def get_viloyat_kb():
    kb, row = [], []
    for v in DataLists.VILOYATLAR:
        row.append(InlineKeyboardButton(text=v, callback_data=f"vil_{v}"))
        if len(row) == 2: kb.append(row); row = []
    if row: kb.append(row)
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_breed_kb(page=0):
    kb, row = [], []
    for i, breed in enumerate(DataLists.BREEDS[page]):
        row.append(InlineKeyboardButton(text=breed, callback_data=f"br_{page}_{i}"))
        if len(row) == 2: kb.append(row); row = []
    if row: kb.append(row)
    
    nav = []
    if page > 0: nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"br_p_{page-1}"))
    if page < len(DataLists.BREEDS) - 1: nav.append(InlineKeyboardButton(text="➡️", callback_data=f"br_p_{page+1}"))
    if nav: kb.append(nav)
    kb.append([InlineKeyboardButton(text="✏️ Zotni o'zim yozaman", callback_data="br_custom")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_age_kb():
    kb, row = [], []
    for age in DataLists.AGES:
        cb = age.replace(" ", "_").replace(",", "")
        row.append(InlineKeyboardButton(text=age, callback_data=f"age_{cb}"))
        if len(row) == 3: kb.append(row); row = []
    if row: kb.append(row)
    return InlineKeyboardMarkup(inline_keyboard=kb)

# =====================================================================
# PREMIUM KANALGA POST QILISH (ALBOM VA XATOLAR TUZATILGAN)
# =====================================================================
async def post_to_channel(ad_data: dict):
    ad_type = ad_data.get("ad_type")
    breed = html_escape(str(ad_data.get("breed") or "—"))
    age = html_escape(str(ad_data.get("age") or "—"))
    gender = html_escape(str(ad_data.get("gender") or "—"))
    sterilization = html_escape(str(ad_data.get("sterilization") or "—"))
    health = html_escape(str(ad_data.get("health") or "—"))
    address = html_escape(str(ad_data.get("address") or "—"))
    phone = html_escape(str(ad_data.get("phone") or "—"))
    price = html_escape(str(ad_data.get("price") or "0"))
    currency = html_escape(str(ad_data.get("currency") or "so'm"))

    footer = (
        '➖➖➖➖➖➖➖➖➖➖➖➖\n'
        '👤 <a href="https://t.me/zayd_catlover">Admin</a> | 📢 <a href="https://t.me/Uzbek_cat_bot?start=reklama">Reklama</a>\n'
        '🌐 <a href="https://t.me/uzbek_cats">Telegram</a> | <a href="https://www.instagram.com/p/C-cZkgstVGK/">Instagram</a> | <a href="https://youtu.be/vdwgSB7_amw">YouTube</a>'
    )

    if ad_type == "sotish":
        caption = (
            f"💰 <b>MUSHUK SOTILADI</b> 💰\n"
            f"➖➖➖➖➖➖➖➖➖➖➖➖\n"
            f"🐱 <b>Zoti:</b> {breed}\n"
            f"🎂 <b>Yoshi:</b> {age}\n"
            f"👤 <b>Jinsi:</b> {gender}\n"
            f"❤️ <b>Sog'lig'i:</b> {health}\n"
            f"🧬 <b>Nasl olish:</b> {sterilization}\n"
            f"📍 <b>Manzil:</b> {address}\n"
            f"💵 <b>Narxi:</b> {price} {currency}\n"
            f"📞 <b>Tel:</b> {phone}\n\n{footer}"
        )
        target = CHANNEL_SOTISH_ID
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎁 Hadiya kanali", url=CHANNEL_HADIYA_LINK)],
            [InlineKeyboardButton(text="📢 E'lon berish", url=BOT_LINK)]
        ])
    else:
        caption = (
            f"🎁 <b>MUSHUK HADIYA</b> 🎁\n"
            f"➖➖➖➖➖➖➖➖➖➖➖➖\n"
            f"🐱 <b>Zoti:</b> {breed}\n"
            f"🎂 <b>Yoshi:</b> {age}\n"
            f"👤 <b>Jinsi:</b> {gender}\n"
            f"❤️ <b>Sog'lig'i:</b> {health}\n"
            f"🧬 <b>Nasl olish:</b> {sterilization}\n"
            f"📍 <b>Manzil:</b> {address}\n"
            f"📞 <b>Tel:</b> {phone}\n\n{footer}"
        )
        target = CHANNEL_HADIYA_ID
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💰 Sotuv kanali", url=CHANNEL_SOTISH_LINK)],
            [InlineKeyboardButton(text="📢 E'lon berish", url=BOT_LINK)]
        ])

    photos = ad_data.get("photos") or []
    if isinstance(photos, str):
        try: photos = json.loads(photos)
        except: photos = []

    try:
        if len(photos) > 1:
            media_group = []
            for i, p in enumerate(photos):
                if p.startswith("BQAC") or p.endswith(".mp4") or len(p) > 100:
                    media = InputMediaVideo(media=p, caption=caption if i==0 else None, parse_mode=ParseMode.HTML)
                else:
                    media = InputMediaPhoto(media=p, caption=caption if i==0 else None, parse_mode=ParseMode.HTML)
                media_group.append(media)
            
            sent_messages = await bot.send_media_group(chat_id=target, media=media_group)
            sent = sent_messages[0]
            # "message is not modified" xatosini ushlab qolish
            try:
                await bot.edit_message_reply_markup(chat_id=target, message_id=sent.message_id, reply_markup=kb)
            except TelegramBadRequest as e:
                if "message is not modified" not in str(e):
                    raise e
        elif len(photos) == 1:
            p = photos[0]
            if p.startswith("BQAC") or p.endswith(".mp4") or len(p) > 100:
                sent = await bot.send_video(chat_id=target, video=p, caption=caption, reply_markup=kb)
            else:
                sent = await bot.send_photo(chat_id=target, photo=p, caption=caption, reply_markup=kb)
        else:
            sent = await bot.send_message(chat_id=target, text=caption, reply_markup=kb)
        return sent
    except Exception as e:
        logger.error(f"❌ Kanalga yuborishda xato: {e}")
        raise e

# =====================================================================
# MIDDLEWARE VA GURUH NAZORATI
# =====================================================================
async def check_middleware(handler, event: Message, data: dict):
    if event.from_user.id in BotConfig.ADMIN_IDS: return await handler(event, data)
    if (event.text or "").startswith("/start"): return await handler(event, data)
    
    if await db.get_setting("bot_enabled", "1") == "0": 
        return await event.answer(Texts.BOT_DISABLED)
        
    user = await db.get_user(event.from_user.id)
    if user and user.get("is_banned"): 
        return await event.answer(Texts.USER_BANNED)
    if await db.check_mute(event.from_user.id): 
        return await event.answer("❌ Siz vaqtincha yozish huquqidan mahrum qilingansiz (24 soat).")
        
    return await handler(event, data)

dp.message.middleware(check_middleware)

@router.message(F.chat.type.in_({"group", "supergroup"}), ~F.from_user.is_bot)
async def banned_words(message: Message):
    if message.from_user.id in BotConfig.ADMIN_IDS: return
    text = (message.text or "").lower()
    if not text: return
    
    for word in DataLists.BANNED_WORDS:
        if word.lower() in text:
            try: await message.delete()
            except: pass
            
            warns = await db.add_warning(message.from_user.id)
            u_link = f'<a href="tg://user?id={message.from_user.id}">{html_escape(message.from_user.first_name)}</a>'
            
            if warns >= 3:
                await db.mute_user(message.from_user.id, 24)
                try: 
                    await bot.restrict_chat_member(message.chat.id, message.from_user.id, ChatPermissions(can_send_messages=False), until_date=datetime.now() + timedelta(hours=24))
                except: pass
                msg = f"🚫 {u_link}, siz qoidalarni 3 marta buzdingiz! 1 kunga yozish huquqidan mahrum qilindingiz."
            else:
                msg = f"⚠️ {u_link}, iltimos reklama tarqatmang!\n\nSiz {warns}-marta qoidani buzdingiz. Yana {3-warns} marta takrorlansa, bloklanasiz."
                
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📢 Reklama berish", url=BOT_LINK)]])
            await message.answer(msg, reply_markup=kb)
            return

# =====================================================================
# START VA RO'YXATDAN O'TISH
# =====================================================================
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user = await db.get_user(message.from_user.id)
    
    if user:
        if user.get("is_banned"): return await message.answer(Texts.USER_BANNED)
        return await message.answer(Texts.MAIN_MENU, reply_markup=main_menu(message.from_user.id in BotConfig.ADMIN_IDS))
    
    args = message.text.split(maxsplit=1)
    if len(args) > 1 and args[1].startswith("REF"): 
        await state.update_data(ref=args[1])
    
    s_ok, h_ok = await check_subscription(message.from_user.id)
    if s_ok and h_ok:
        await message.answer(Texts.START_TEXT, reply_markup=get_phone_kb())
        await state.set_state(RegStates.waiting_phone)
    else:
        await message.answer("👋 <b>Assalomu alaykum!</b>\n\nBotdan foydalanish uchun quyidagi kanallarga obuna bo'ling:", reply_markup=get_sub_kb(s_ok, h_ok))

@router.callback_query(F.data == "noop")
async def noop(call: CallbackQuery): await safe_answer(call, "✅ Obuna tasdiqlangan!")

@router.callback_query(F.data == "check_sub")
async def check_sub(call: CallbackQuery, state: FSMContext):
    s_ok, h_ok = await check_subscription(call.from_user.id)
    if s_ok and h_ok:
        await safe_edit_text(call.message, Texts.START_TEXT, reply_markup=get_phone_kb())
        await state.set_state(RegStates.waiting_phone)
    else: 
        await safe_answer(call, "❌ Iltimos, barcha kanallarga to'liq obuna bo'ling!", True)

@router.callback_query(F.data == "continue_reg")
async def cont_reg(call: CallbackQuery, state: FSMContext):
    await safe_edit_text(call.message, Texts.START_TEXT, reply_markup=get_phone_kb())
    await state.set_state(RegStates.waiting_phone)

@router.message(RegStates.waiting_phone, F.contact | F.text)
async def process_phone(message: Message, state: FSMContext):
    phone = message.contact.phone_number if message.contact else (message.text or "").strip()
    if not message.contact and not re.match(r"^\+?998\d{9}$", phone.replace(" ", "")): 
        return await message.answer(Texts.ASK_PHONE)
    
    phone = phone if phone.startswith("+") else f"+{phone}"
    data = await state.get_data()
    try:
        user = await db.create_user(message.from_user.id, f"@{message.from_user.username}" if message.from_user.username else "Noma'lum", message.from_user.full_name, phone, data.get("ref"))
        await message.answer(Texts.REG_SUCCESS.format(user_number=user["user_number"], score=user["score"], referrals=0), reply_markup=ReplyKeyboardRemove())
        await message.answer(Texts.MAIN_MENU, reply_markup=main_menu(message.from_user.id in BotConfig.ADMIN_IDS))
        await state.clear()
    except Exception as e: 
        await message.answer(f"❌ Xatolik yuz berdi: {e}")

# =====================================================================
# ASOSIY MENYU VA KONKURS
# =====================================================================
@router.callback_query(F.data == "menu_back_to_main")
async def back_main(call: CallbackQuery): 
    await safe_edit_text(call.message, Texts.MAIN_MENU, main_menu(call.from_user.id in BotConfig.ADMIN_IDS))

@router.callback_query(F.data == "menu_konkurs")
async def konkurs(call: CallbackQuery):
    user = await db.get_user(call.from_user.id)
    ref = f"https://t.me/{BotConfig.BOT_USERNAME.replace('@', '')}?start=REF{user['id']}"
    text = f"🏆 <b>Konkurs va Takliflar</b>\n➖➖➖➖➖➖➖➖➖➖➖➖\n\n👥 Sizning ballaringiz: <b>{user['score']}</b>\n🔗 Havolangiz:\n<code>{ref}</code>\n\nDo'stlaringizni taklif qiling, ball to'plang va eng yaxshi 10 talikka kiring!"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Do'stlarga ulashish", url=f"https://t.me/share/url?url={ref}")], 
        [InlineKeyboardButton(text="🏆 Reytingni ko'rish", callback_data="menu_rating")], 
        [InlineKeyboardButton(text="↩️ Orqaga", callback_data="menu_back_to_main")]
    ])
    await safe_edit_text(call.message, text, kb)

@router.callback_query(F.data == "menu_rating")
async def rating(call: CallbackQuery):
    top = await db.get_top_10_users()
    text = "🥇 <b>Top 10 Faol Foydalanuvchilar</b>\n➖➖➖➖➖➖➖➖➖➖➖➖\n\n"
    if not top:
        text += "Hozircha reyting mavjud emas."
    else:
        for i, u in enumerate(top, 1):
            medal = "🥇" if i==1 else "🥈" if i==2 else "🥉" if i==3 else f"{i}."
            text += f"{medal} {html_escape(u['full_name'])} — <b>{u['score']} ball</b>\n"
            
    await safe_edit_text(call.message, text, InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="↩️ Orqaga", callback_data="menu_konkurs")]]))

@router.callback_query(F.data == "menu_about")
async def about(call: CallbackQuery):
    text = (
        "ℹ️ <b>Bot haqida ma'lumot</b>\n"
        "➖➖➖➖➖➖➖➖➖➖➖➖\n\n"
        "Ushbu bot orqali siz uy hayvonlaringizni sotishingiz yoki hadiya qilishingiz mumkin.\n\n"
        "🎁 <b>Hadiya e'lonlari mutlaqo bepul.</b>\n"
        "💰 <b>Sotuv e'lonlari to'lov asosida.</b>\n\n"
        "Qulaylik uchun Web App xizmatidan ham foydalanishingiz mumkin."
    )
    await safe_edit_text(call.message, text, InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="↩️ Orqaga", callback_data="menu_back_to_main")]]))

@router.callback_query(F.data == "menu_admin")
async def contact_admin(call: CallbackQuery):
    text = "👤 <b>Qo'llab-quvvatlash xizmati</b>\n➖➖➖➖➖➖➖➖➖➖➖➖\n\n👨‍💻 Texnik Admin: @It_project_2026\n📞 +998900512621\n\n👨‍💼 Bosh Admin: @zayd_catlover\n📞 +998934938181"
    await safe_edit_text(call.message, text, InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="↩️ Orqaga", callback_data="menu_back_to_main")]]))

# =====================================================================
# MENING E'LONLARIM
# =====================================================================
@router.callback_query(F.data == "menu_my_orders")
async def my_orders(call: CallbackQuery):
    ads = await db.get_user_ads(call.from_user.id)
    await safe_edit_text(call.message, "⏳ <i>E'lonlaringiz yuklanmoqda...</i>", None)
    
    if not ads: 
        return await call.message.answer("📭 Sizda hali e'lonlar mavjud emas.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="↩️ Orqaga", callback_data="menu_back_to_main")]]))
    
    st_map = {"pending": "⏳ Kutilmoqda", "approved": "✅ Tasdiqlangan", "rejected": "❌ Rad etilgan"}
    for ad in ads:
        st = st_map.get(ad["status"], ad["status"])
        text = f"🐱 <b>{html_escape(str(ad['breed']))}</b>\nHolat: {st}\n📅 Sana: {ad['created_at'].strftime('%d.%m.%Y')}"
        
        kb = None
        if ad['status'] == "approved":
            action = "🎁 Berib bo'ldim" if ad['ad_type'] == "hadiya" else "💰 Sotildi"
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=action, callback_data=f"done_ad_{ad['id']}")]])
        
        photos = json.loads(ad['photos']) if isinstance(ad['photos'], str) else (ad['photos'] or [])
        if photos:
            if len(photos[0]) > 100 or photos[0].endswith(".mp4"): 
                await call.message.answer_video(photos[0], caption=text, reply_markup=kb)
            else: 
                await call.message.answer_photo(photos[0], caption=text, reply_markup=kb)
        else: 
            await call.message.answer(text, reply_markup=kb)
            
    await call.message.answer("Asosiy menyuga qaytish:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="↩️ Orqaga", callback_data="menu_back_to_main")]]))

@router.callback_query(F.data.startswith("done_ad_"))
async def user_done_ad(call: CallbackQuery):
    ad_id = int(call.data.split("_")[2])
    ad = await db.get_ad(ad_id)
    if not ad or ad["user_id"] != call.from_user.id: 
        return await safe_answer(call, "Xatolik!", True)
    
    action = "BERILDI 🎁" if ad["ad_type"] == "hadiya" else "SOTILDI 💰"
    await db.delete_ad(ad_id)
    
    if ad.get("channel_message_id"):
        try:
            target = CHANNEL_SOTISH_ID if ad["ad_type"] == "sotish" else CHANNEL_HADIYA_ID
            new_cap = f"#{action}\n\n📝 {html_escape(str(ad['breed']))} | {html_escape(str(ad['age']))}\n\n📍 {html_escape(str(ad['address']))}\n📞 <i>Yashirilgan</i>\n\n✅ <b>E'LON YOPILDI</b>"
            if ad['photos']: 
                await bot.edit_message_caption(target, ad["channel_message_id"], caption=new_cap, reply_markup=None)
            else: 
                await bot.edit_message_text(target, ad["channel_message_id"], text=new_cap, reply_markup=None)
        except: pass
        
    await safe_answer(call, f"✅ E'lon {action} deb belgilandi va o'chirildi!", True)
    await safe_delete(call.message)

# =====================================================================
# PREMIUM E'LON YARATISH JARAYONI
# =====================================================================
@router.callback_query(F.data == "menu_reklama")
async def start_ad(call: CallbackQuery, state: FSMContext):
    await state.clear()
    text = "🛒 <b>E'lon joylashtirish</b>\n➖➖➖➖➖➖➖➖➖➖➖➖\n\nQanday turdagi e'lon bermoqchisiz?"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Mushuk sotmoqchiman", callback_data="adtype_sotish")], 
        [InlineKeyboardButton(text="🎁 Hadiya qilmoqchiman", callback_data="adtype_hadiya")], 
        [InlineKeyboardButton(text="↩️ Bekor qilish", callback_data="menu_back_to_main")]
    ])
    await safe_edit_text(call.message, text, kb)

@router.callback_query(F.data.startswith("adtype_"))
async def choose_type(call: CallbackQuery, state: FSMContext):
    ad_type = call.data.split("_")[1]
    await state.update_data(ad_type=ad_type)
    
    if ad_type == "sotish":
        await state.set_state(AdStates.cat_count)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"{i} ta mushuk", callback_data=f"cat_{i}")] for i in range(1, 6)
        ])
        await safe_edit_text(call.message, "🐱 <b>Nechta mushuk sotmoqchisiz?</b>", kb)
    else:
        await state.set_state(AdStates.media_type)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🖼️ Rasm yuboraman", callback_data="m_photo")], 
            [InlineKeyboardButton(text="🎥 Video yuboraman (1 daqiqagacha)", callback_data="m_video")]
        ])
        await safe_edit_text(call.message, "📸 <b>Qanday media yuborasiz?</b>", kb)

@router.callback_query(AdStates.cat_count, F.data.startswith("cat_"))
async def process_cat(call: CallbackQuery, state: FSMContext):
    count = int(call.data.split("_")[1])
    await state.update_data(cat_count=count, bot_price=Prices.get_bot_price(count))
    await state.set_state(AdStates.media_type)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖼️ Rasm yuboraman", callback_data="m_photo")], 
        [InlineKeyboardButton(text="🎥 Video yuboraman (1 daqiqagacha)", callback_data="m_video")]
    ])
    await safe_edit_text(call.message, "📸 <b>Qanday media yuborasiz?</b>", kb)

@router.callback_query(F.data.startswith("m_"))
async def choose_media(call: CallbackQuery, state: FSMContext):
    m_type = call.data.split("_")[1]
    await state.update_data(media_type=m_type, photos=[])
    await state.set_state(AdStates.media)
    
    text = "🖼️ <b>Rasmlarni yuboring (1-3 ta):</b>" if m_type == "photo" else "🎥 <b>Videoni yuboring (1 daqiqagacha):</b>"
    await safe_edit_text(call.message, text, None)

@router.message(AdStates.media, F.photo | F.video)
async def receive_media(message: Message, state: FSMContext):
    data = await state.get_data()
    m_type = data.get("media_type")
    
    if message.photo and m_type != "photo": return await message.answer("❌ Faqat rasm yuboring!")
    if message.video and m_type != "video": return await message.answer("❌ Faqat video yuboring!")
    if message.video and message.video.duration > 60: return await message.answer("❌ Video 1 daqiqadan oshmasin!")
    
    photos = data.get("photos", [])
    if len(photos) >= 3: return await message.answer("❌ Maksimum 3 ta rasm.")
    
    photos.append(message.photo[-1].file_id if message.photo else message.video.file_id)
    await state.update_data(photos=photos)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➡️ Davom etish", callback_data="next_step")]])
    await message.answer(f"✅ <b>{len(photos)}-media qabul qilindi.</b>\nYana yuborishingiz yoki davom etishingiz mumkin.", reply_markup=kb)

@router.callback_query(F.data == "next_step")
async def next_step(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("photos"): 
        return await safe_answer(call, "❌ Iltimos, avval media yuboring!", True)
        
    await state.set_state(AdStates.breed)
    await safe_edit_text(call.message, "🐱 <b>Zotni tanlang (yoki o'zim yozaman):</b>", get_breed_kb(0))

@router.callback_query(AdStates.breed, F.data.startswith("br_p_"))
async def breed_page(call: CallbackQuery, state: FSMContext):
    page = int(call.data.split("_")[2])
    await call.message.edit_reply_markup(reply_markup=get_breed_kb(page))

@router.callback_query(AdStates.breed, F.data.startswith("br_") & ~F.data.startswith("br_p_") & ~F.data.startswith("br_custom"))
async def save_breed_cb(call: CallbackQuery, state: FSMContext):
    parts = call.data.split("_")
    breed = DataLists.BREEDS[int(parts[1])][int(parts[2])]
    await state.update_data(breed=breed)
    await state.set_state(AdStates.age)
    await safe_edit_text(call.message, "🎂 <b>Yoshini tanlang:</b>", get_age_kb())

@router.callback_query(AdStates.breed, F.data == "br_custom")
async def custom_breed_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(AdStates.custom_breed)
    await safe_edit_text(call.message, "✏️ <b>Zotni yozib yuboring:</b>", None)

@router.message(AdStates.custom_breed)
async def save_custom_breed(message: Message, state: FSMContext):
    await state.update_data(breed=message.text)
    await state.set_state(AdStates.age)
    await message.answer("🎂 <b>Yoshini tanlang:</b>", reply_markup=get_age_kb())

@router.callback_query(AdStates.age, F.data.startswith("age_"))
async def save_age(call: CallbackQuery, state: FSMContext):
    age = call.data.replace("age_", "").replace("_", " ")
    await state.update_data(age=age)
    await state.set_state(AdStates.health)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Sog'lom", callback_data="health_sog")],
        [InlineKeyboardButton(text="⚠️ Kasal", callback_data="health_kas")]
    ])
    await safe_edit_text(call.message, "❤️ <b>Sog'lig'ini tanlang:</b>", kb)

@router.callback_query(AdStates.health, F.data.startswith("health_"))
async def save_health(call: CallbackQuery, state: FSMContext):
    health = "Sog'lom" if "sog" in call.data else "Kasal"
    await state.update_data(health=health)
    await state.set_state(AdStates.gender)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="♀️ Qiz bola", callback_data="gen_qiz")],
        [InlineKeyboardButton(text="♂️ O'g'il bola", callback_data="gen_ogil")]
    ])
    await safe_edit_text(call.message, "👤 <b>Jinsini tanlang:</b>", kb)

@router.callback_query(AdStates.gender, F.data.startswith("gen_"))
async def save_gender(call: CallbackQuery, state: FSMContext):
    gender = "Qiz bola" if "qiz" in call.data else "O'g'il bola"
    await state.update_data(gender=gender)
    await state.set_state(AdStates.sterilization)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Ha, nasl olsa bo'ladi", callback_data="ster_yes")],
        [InlineKeyboardButton(text="❌ Yo'q, nasl olsa bo'lmaydi", callback_data="ster_no")]
    ])
    await safe_edit_text(call.message, "🧬 <b>Nasl olish xususiyati:</b>", kb)

@router.callback_query(AdStates.sterilization, F.data.startswith("ster_"))
async def save_ster(call: CallbackQuery, state: FSMContext):
    ster = "Nasl olish mumkin" if "yes" in call.data else "Nasl olish mumkin emas"
    await state.update_data(sterilization=ster)
    await state.set_state(AdStates.address)
    await safe_edit_text(call.message, "📍 <b>Viloyatni tanlang:</b>", get_viloyat_kb())

@router.callback_query(AdStates.address, F.data.startswith("vil_"))
async def save_addr(call: CallbackQuery, state: FSMContext):
    addr = call.data.replace("vil_", "")
    await state.update_data(address=addr, phone="+998901234567")
    
    data = await state.get_data()
    if data["ad_type"] == "hadiya": 
        await state.set_state(AdStates.preview)
        await preview_ad(call.message, state)
    else:
        await state.set_state(AdStates.price)
        await safe_edit_text(call.message, "💰 <b>Narxni kiriting (faqat raqamda, so'mda):</b>", None)

@router.message(AdStates.price)
async def save_price(message: Message, state: FSMContext):
    if not message.text.isdigit(): 
        return await message.answer("❌ Faqat raqam kiriting:")
    await state.update_data(price=message.text, currency="so'm")
    await state.set_state(AdStates.preview)
    await preview_ad(message, state)

async def preview_ad(msg: Message, state: FSMContext):
    data = await state.get_data()
    user = await db.get_user(msg.from_user.id)
    price = data.get("bot_price", 0)
    
    text = (
        f"📋 <b>E'lonni tekshirib oling</b>\n"
        f"➖➖➖➖➖➖➖➖➖➖➖➖\n"
        f"🐱 <b>Zoti:</b> {html_escape(data['breed'])}\n"
        f"🎂 <b>Yoshi:</b> {html_escape(data['age'])}\n"
        f"👤 <b>Jinsi:</b> {html_escape(data['gender'])}\n"
        f"❤️ <b>Sog'lig'i:</b> {html_escape(data['health'])}\n"
        f"🧬 <b>Nasl olish:</b> {html_escape(data['sterilization'])}\n"
        f"📍 <b>Manzil:</b> {html_escape(data['address'])}\n"
    )
    if data['ad_type'] != "hadiya": 
        text += f"💵 <b>Narxi:</b> {html_escape(data['price'])} {html_escape(data['currency'])}\n"
        
    text += f"\n💳 <b>Sizning balansingiz:</b> {user['balance']:,} so'm\n"
    if price > 0: 
        text += f"💸 <b>Yechiladigan summa:</b> {price:,} so'm\n"
        
    if user['balance'] < price:
        text += f"\n❌ <b>Diqqat! Mablag' yetarli emas. Iltimos, hisobni to'ldiring.</b>"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Hisobni to'ldirish", web_app=types.WebAppInfo(url=f"{BotConfig.WEB_APP_URL}?page=topup"))],
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="menu_back_to_main")]
        ])
    else:
        text += f"\n❓ <b>E'lonni tasdiqlaysizmi?</b>"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Ha, tasdiqlash", callback_data="final_confirm")], 
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="menu_back_to_main")]
        ])
    
    photos = data.get("photos", [])
    try:
        if photos:
            if data["media_type"] == "video": await msg.answer_video(photos[0], caption=text, reply_markup=kb)
            else: await msg.answer_photo(photos[0], caption=text, reply_markup=kb)
        else: 
            await msg.answer(text, reply_markup=kb)
    except:
        await msg.answer(text, reply_markup=kb)

@router.callback_query(AdStates.preview, F.data == "final_confirm")
async def confirm_ad(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user = await db.get_user(call.from_user.id)
    price = data.get("bot_price", 0)
    
    if user["balance"] < price: 
        return await safe_answer(call, "❌ Mablag' yetarli emas!", True)
    
    if price > 0: await db.update_user_balance(user["id"], price, "subtract")
    
    new_ad = await db.create_ad(
        user_id=user["id"], ad_type=data["ad_type"], tariff="bot", 
        photos=data["photos"], breed=data["breed"], age=data["age"], 
        gender=data["gender"], health=data["health"], sterilization=data["sterilization"], 
        address=data["address"], phone=data["phone"], price=data.get("price", "0"), 
        currency=data.get("currency", "so'm"), ad_number=(user.get("ad_count") or 0) + 1, 
        cat_count=data.get("cat_count", 1), price_paid=price
    )
    
    await safe_delete(call.message)
    await call.message.answer("✅ <b>E'loningiz qabul qilindi!</b>\n\nAdmin tekshiruvidan so'ng kanalga joylanadi.", reply_markup=main_menu(call.from_user.id in BotConfig.ADMIN_IDS))
    
    # Adminga yuborish
    admin_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"adm_ok_{new_ad['id']}"), 
        InlineKeyboardButton(text="❌ Rad etish", callback_data=f"adm_no_{new_ad['id']}")
    ]])
    admin_text = f"🆕 <b>YANGI E'LON KELDI!</b>\n\n👤 Foydalanuvchi: #{user['user_number']}\n🐱 Zoti: {html_escape(data['breed'])}\n💰 To'lov: {price:,} so'm"
    
    try:
        if data["photos"]:
            if data["media_type"] == "video": await bot.send_video(BotConfig.TECH_ADMIN_ID, data["photos"][0], caption=admin_text, reply_markup=admin_kb)
            else: await bot.send_photo(BotConfig.TECH_ADMIN_ID, data["photos"][0], caption=admin_text, reply_markup=admin_kb)
        else: 
            await bot.send_message(BotConfig.TECH_ADMIN_ID, admin_text, reply_markup=admin_kb)
    except Exception as e:
        logger.error(f"Adminga yuborishda xato: {e}")
        
    await state.clear()

# =====================================================================
# ADMIN AMALLARI VA TASDIQLASH
# =====================================================================
@router.callback_query(F.data.startswith("adm_ok_"))
async def adm_ok(call: CallbackQuery):
    if call.from_user.id not in BotConfig.ADMIN_IDS: return
    ad_id = int(call.data.split("_")[2])
    ad = await db.get_ad(ad_id)
    
    if not ad or ad["status"] != "pending":
        await call.message.edit_reply_markup(reply_markup=None)
        return await safe_answer(call, "⚠️ Bu e'lon allaqachon ko'rib chiqilgan!", True)
    
    try: await call.message.edit_reply_markup(reply_markup=None)
    except: pass
    
    try:
        sent = await post_to_channel(ad)
        await db.update_ad_status(ad_id, "approved", channel_message_id=sent.message_id)
        
        ch_id = str(CHANNEL_SOTISH_ID if ad["ad_type"] == "sotish" else CHANNEL_HADIYA_ID).replace("-100", "")
        link = f"https://t.me/c/{ch_id}/{sent.message_id}"
        
        act = "🎁 Berib bo'ldim" if ad["ad_type"] == "hadiya" else "💰 Sotildi"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=act, callback_data=f"done_ad_{ad_id}")], 
            [InlineKeyboardButton(text="👁 E'lonni ko'rish", url=link)]
        ])
        await bot.send_message(ad["user_id"], f"✅ <b>Sizning e'loningiz tasdiqlandi va kanalga joylandi!</b>\n\n<i>E'lon o'z joyiga ega bo'lgach, «{act}» tugmasini bosing.</i>", reply_markup=kb)
        await safe_answer(call, "✅ Kanalga yuborildi!")
    except Exception as e:
        await safe_answer(call, f"❌ Xato: {e}", True)

@router.callback_query(F.data.startswith("adm_no_"))
async def adm_no(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in BotConfig.ADMIN_IDS: return
    ad_id = int(call.data.split("_")[2])
    try: await call.message.edit_reply_markup(reply_markup=None)
    except: pass
    
    await state.update_data(decline_id=ad_id)
    await state.set_state(AdminStates.decline)
    await call.message.reply("✍️ <b>Rad etish sababini yozing:</b>")

@router.message(AdminStates.decline)
async def do_decline(message: Message, state: FSMContext):
    ad_id = (await state.get_data()).get("decline_id")
    ad = await db.get_ad(ad_id)
    await db.update_ad_status(ad_id, "rejected", reason=message.text)
    
    if ad and ad.get("price_paid", 0) > 0:
        await db.update_user_balance(ad["user_id"], ad["price_paid"], "add")
        await bot.send_message(ad["user_id"], f"❌ <b>E'loningiz rad etildi.</b>\n\nSabab: {html_escape(message.text)}\n\nHisobingizga {ad['price_paid']:,} so'm qaytarildi.")
    elif ad:
        await bot.send_message(ad["user_id"], f"❌ <b>E'loningiz rad etildi.</b>\n\nSabab: {html_escape(message.text)}")
        
    await message.answer("✅ E'lon rad etildi va pul qaytarildi.")
    await state.clear()

# =====================================================================
# ADMIN PANEL
# =====================================================================
@router.callback_query(F.data == "admin_panel")
async def admin_panel(call: CallbackQuery):
    if call.from_user.id not in BotConfig.ADMIN_IDS: return
    stats = await db.get_statistics()
    
    text = (
        f"👨‍💼 <b>Admin Boshqaruv Paneli</b>\n"
        f"➖➖➖➖➖➖➖➖➖➖➖➖\n"
        f"👥 Foydalanuvchilar: <b>{stats['total_users']}</b>\n"
        f"📢 Jami e'lonlar: <b>{stats['total_ads']}</b>\n\n"
        f"💰 Bugungi tushum: <b>{stats['today_income']:,} so'm</b>\n"
        f"💵 Oylik tushum: <b>{stats['month_income']:,} so'm</b>"
    )
    
    rows = [
        [InlineKeyboardButton(text="⚙️ Bot holati (Yoq/O'chir)", callback_data="admin_toggle_bot")],
        [InlineKeyboardButton(text="💳 Hisob qo'shish", callback_data="admin_add_balance")],
        [InlineKeyboardButton(text="➕ Ball qo'shish (Telefon orqali)", callback_data="admin_add_score")],
        [InlineKeyboardButton(text="↩️ Orqaga", callback_data="menu_back_to_main")]
    ]
    await safe_edit_text(call.message, text, InlineKeyboardMarkup(inline_keyboard=rows))

@router.callback_query(F.data == "admin_toggle_bot")
async def admin_toggle_bot(call: CallbackQuery):
    if call.from_user.id not in BotConfig.ADMIN_IDS: return
    current = await db.get_setting("bot_enabled", "1")
    new_val = "0" if current == "1" else "1"
    await db.set_setting("bot_enabled", new_val)
    await safe_answer(call, "✅ Bot yoqildi!" if new_val == "1" else "🔴 Bot o'chirildi!", True)

@router.callback_query(F.data == "admin_add_balance")
async def admin_add_balance_start(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in BotConfig.ADMIN_IDS: return
    await safe_edit_text(call.message, "💳 <b>Hisob qo'shish</b>\n\nFoydalanuvchining Telegram ID sini kiriting:\n(Masalan: <code>673018191</code>)\n\nBekor qilish: /cancel", None)
    await state.set_state(AdminStates.balance_id)

@router.message(AdminStates.balance_id)
async def admin_add_balance_user(message: Message, state: FSMContext):
    if (message.text or "") == "/cancel": await state.clear(); return await message.answer("Bekor qilindi.")
    if not (message.text or "").isdigit(): return await message.answer("❌ Faqat raqam kiriting:")
    
    uid = int(message.text)
    user = await db.get_user(uid)
    if not user: return await message.answer("❌ Bunday ID li foydalanuvchi topilmadi.")
    
    await state.update_data(target_id=uid)
    await message.answer(f"👤 Foydalanuvchi: #{user['user_number']} ({html_escape(user['full_name'])})\n\nQancha summa qo'shmoqchisiz? (Ayirish uchun: <code>-50000</code>):")
    await state.set_state(AdminStates.balance_amount)

@router.message(AdminStates.balance_amount)
async def admin_add_balance_amount(message: Message, state: FSMContext):
    if (message.text or "") == "/cancel": await state.clear(); return await message.answer("Bekor qilindi.")
    try: amount = int(message.text)
    except: return await message.answer("❌ Noto'g'ri summa.")
    
    uid = (await state.get_data()).get("target_id")
    op = "add" if amount > 0 else "subtract"
    
    try:
        new_bal = await db.update_user_balance(uid, abs(amount), op)
        msg = f"✅ Hisobingizga {amount:,} so'm qo'shildi." if amount > 0 else f"⚠️ Hisobingizdan {abs(amount):,} so'm yechildi."
        try: await bot.send_message(uid, f"{msg}\n\n💰 Joriy balans: {new_bal:,} so'm")
        except: pass
        await message.answer(f"✅ Bajarildi!\nYangi balans: {new_bal:,} so'm")
    except Exception as e: 
        await message.answer(f"❌ Xatolik: {e}")
    await state.clear()

@router.callback_query(F.data == "admin_add_score")
async def admin_add_score(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in BotConfig.ADMIN_IDS: return
    await safe_edit_text(call.message, "📊 <b>Ball qo'shish</b>\n\nFormat: <code>+998901234567 - 17</code>\n\nBekor qilish: /cancel", None)
    await state.set_state(AdminStates.score)

@router.message(AdminStates.score)
async def process_add_score(message: Message, state: FSMContext):
    if (message.text or "") == "/cancel": await state.clear(); return await message.answer("Bekor qilindi.")
    m = re.search(r"(\+?\d{9,15})\s*[-–—]?\s*(-?\d+)", message.text or "")
    if not m: return await message.answer("❌ Format xato. Namuna: <code>+998901234567 - 17</code>")
    
    ok = await db.add_score_by_phone_batch(m.group(1), int(m.group(2)))
    await message.answer("✅ Ball muvaffaqiyatli qo'shildi!" if ok else "❌ Topilmadi.")
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
    logger.info("🔌 Bot to'xtatildi")

async def main():
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
