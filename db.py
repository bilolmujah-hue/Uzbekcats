# ==============================================================================
# LOYIHA: UzbekCats Bot & Web App
# FAYL: bot.py
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BotConfig.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
router = Router()
dp.include_router(router)

CHANNEL_SOTISH_ID = BotConfig.CHANNEL_SOTISH_ID
CHANNEL_HADIYA_ID = BotConfig.CHANNEL_HADIYA_ID
userbot_client: TelegramClient | None = None

# =====================================================================
# YORDAMCHI (Eski tugmalar xatosini oldini olish)
# =====================================================================
async def safe_answer(call: CallbackQuery, text: str = None, show_alert: bool = False):
    try: await call.answer(text=text, show_alert=show_alert)
    except TelegramBadRequest: pass # Eski tugma bosilganda xato bermaydi

async def safe_edit_text(message: Message, text: str, reply_markup=None):
    try: await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest:
        try: await message.delete()
        except: pass
        await message.answer(text, reply_markup=reply_markup)

# =====================================================================
# USERBOT (EOF XATOSI TUZATILDI)
# =====================================================================
async def start_userbot(session_string: str):
    global userbot_client
    if not session_string or len(session_string) < 10: return
    try:
        if userbot_client and userbot_client.is_connected(): await userbot_client.disconnect()
        
        userbot_client = TelegramClient(StringSession(session_string), api_id=UserbotConfig.API_ID, api_hash=UserbotConfig.API_HASH)
        await userbot_client.connect()
        
        if not await userbot_client.is_user_authorized():
            logger.error("❌ Userbot sessiyasi eskirgan! Iltimos, qaytadan kod orqali ulang.")
            return

        logger.info("✅ Userbot ishga tushdi")
        @userbot_client.on(events.NewMessage(chats=UserbotConfig.TARGET_BOT))
        async def handler(event):
            text = event.message.text or ""
            m = re.search(UserbotConfig.CARD_TRANSFER_REGEX, text)
            if not m: return
            try:
                amount = int(m.group(1).replace(" ", ""))
                last4 = m.group(2)
                user_id = await db.match_userbot_payment(amount, last4) if hasattr(db, 'match_userbot_payment') else None
                # Agar db da bu funksiya bo'lsa ishlaydi
                if user_id: await bot.send_message(user_id, Texts.TOPUP_PAID.format(amount=amount))
            except: pass
    except Exception as e: logger.error(f"❌ Userbot xatosi: {e}")

# =====================================================================
# MAJBURIY OBUNA
# =====================================================================
async def check_subscription(user_id: int) -> tuple[bool, bool]:
    s_ok = h_ok = False
    for chat_id, key in [(CHANNEL_SOTISH_ID, "s"), (CHANNEL_HADIYA_ID, "h")]:
        try:
            m = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
            ok = getattr(m.status, "value", m.status) in ("member", "administrator", "creator")
            if key == "s": s_ok = ok
            else: h_ok = ok
        except: pass
    return s_ok, h_ok

def get_sub_kb(s_ok: bool, h_ok: bool) -> InlineKeyboardMarkup:
    kb = []
    if s_ok: kb.append([InlineKeyboardButton(text="✅ Sotish", callback_data="noop")])
    else: kb.append([InlineKeyboardButton(text="📢 Sotish kanal", url=BotConfig.CHANNEL_SOTISH_LINK)])
    if h_ok: kb.append([InlineKeyboardButton(text="✅ Hadiya", callback_data="noop")])
    else: kb.append([InlineKeyboardButton(text="🎁 Hadiya kanal", url=BotConfig.CHANNEL_HADIYA_LINK)])
    if not (s_ok and h_ok): kb.append([InlineKeyboardButton(text="🔄 Tekshirish", callback_data="check_sub")])
    else: kb.append([InlineKeyboardButton(text="➡️ Davom etish", callback_data="continue_reg")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

# =====================================================================
# FSM
# =====================================================================
class RegStates(StatesGroup): waiting_phone = State()
class AdStates(StatesGroup):
    cat_count = State(); media = State(); breed = State(); custom_breed = State()
    age = State(); health = State(); gender = State(); sterilization = State()
    address = State(); phone = State(); currency = State(); price = State(); preview = State()
class AdminStates(StatesGroup): balance_id = State(); balance_amount = State(); score = State(); decline = State(); edit_id = State(); edit_val = State()

# =====================================================================
# MENYULAR
# =====================================================================
def main_menu(is_admin=False):
    kb = [
        [InlineKeyboardButton(text="📢 Kanalga reklama bermoqchiman", callback_data="menu_reklama")],
        [InlineKeyboardButton(text="🏆 Konkurs", callback_data="menu_konkurs")],
        [InlineKeyboardButton(text="💳 Hisobni to'ldirish", web_app=types.WebAppInfo(url=f"{BotConfig.WEB_APP_URL}?page=topup"))],
        [InlineKeyboardButton(text="📋 Mening e'lonlarim", callback_data="menu_my_orders")],
        [InlineKeyboardButton(text="ℹ️ Bot haqida", callback_data="menu_about")],
        [InlineKeyboardButton(text="👤 Admin bilan bog'lanish", callback_data="menu_admin")],
        [InlineKeyboardButton(text="🖥️ Web App", web_app=types.WebAppInfo(url=BotConfig.WEB_APP_URL))],
    ]
    if is_admin: kb.append([InlineKeyboardButton(text="👨‍💼 Admin paneli", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def phone_kb(): return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📞 Raqamni yuborish", request_contact=True)]], resize_keyboard=True, one_time_keyboard=True)

# =====================================================================
# POST TO CHANNEL (ALBOM BILAN)
# =====================================================================
async def post_to_channel(ad: dict):
    b_safe = html_escape(str(ad.get("breed") or "—")); a_safe = html_escape(str(ad.get("age") or "—"))
    g_safe = html_escape(str(ad.get("gender") or "—")); st_safe = html_escape(str(ad.get("sterilization") or "—"))
    h_safe = html_escape(str(ad.get("health") or "—")); addr = html_escape(str(ad.get("address") or "—"))
    ph = html_escape(str(ad.get("phone") or "—")); p = html_escape(str(ad.get("price") or "0")); c = html_escape(str(ad.get("currency") or "so'm"))
    footer = '👤 <a href="https://t.me/zayd_catlover">Admin</a>\n📢 <a href="https://t.me/Uzbek_cat_bot?start=reklama">Reklama berish</a>'
    
    if ad["ad_type"] == "sotish":
        cap = f"#SOTILADI 💰\n\n📝 {b_safe} | {a_safe} | {g_safe} | {st_safe} | {h_safe}\n\n📍 {addr}\n💵 {p} {c}\n📞 {ph}\n\n{footer}"
        target = CHANNEL_SOTISH_ID
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎁 Hadiya kanal", url=BotConfig.CHANNEL_HADIYA_LINK)]])
    else:
        cap = f"#HADIYA 🎁\n\n📝 {b_safe} | {a_safe} | {g_safe} | {st_safe} | {h_safe}\n\n📍 {addr}\n📞 {ph}\n\n{footer}"
        target = CHANNEL_HADIYA_ID
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💰 Sotiladi kanal", url=BotConfig.CHANNEL_SOTISH_LINK)]])

    photos = ad.get("photos") or []
    if isinstance(photos, str):
        try: photos = json.loads(photos)
        except: photos = []

    try:
        if len(photos) > 1:
            media = []
            for i, p_id in enumerate(photos):
                if p_id.startswith("BQAC") or p_id.endswith(".mp4") or len(p_id) > 100:
                    media.append(InputMediaVideo(media=p_id, caption=cap if i==0 else None))
                else:
                    media.append(InputMediaPhoto(media=p_id, caption=cap if i==0 else None))
            msgs = await bot.send_media_group(chat_id=target, media=media)
            await bot.edit_message_reply_markup(chat_id=target, message_id=msgs[0].message_id, reply_markup=kb)
            return msgs[0]
        elif len(photos) == 1:
            p_id = photos[0]
            if p_id.startswith("BQAC") or p_id.endswith(".mp4") or len(p_id) > 100:
                return await bot.send_video(chat_id=target, video=p_id, caption=cap, reply_markup=kb)
            else:
                return await bot.send_photo(chat_id=target, photo=p_id, caption=cap, reply_markup=kb)
        else:
            return await bot.send_message(chat_id=target, text=cap, reply_markup=kb)
    except Exception as e:
        logger.error(f"Kanalga yuborishda xato: {e}")
        raise e

# =====================================================================
# MIDDLEWARE VA BANNED WORDS
# =====================================================================
async def check_middleware(handler, event: Message, data: dict):
    if event.from_user.id in BotConfig.ADMIN_IDS: return await handler(event, data)
    if (event.text or "").startswith("/start"): return await handler(event, data)
    if await db.get_setting("bot_enabled", "1") == "0": return await event.answer(Texts.BOT_DISABLED)
    user = await db.get_user(event.from_user.id)
    if user and user.get("is_banned"): return await event.answer(Texts.USER_BANNED)
    if await db.check_mute(event.from_user.id): return await event.answer("❌ Siz vaqtincha yozish huquqidan mahrum qilingansiz. (24 soat)")
    return await handler(event, data)
dp.message.middleware(check_middleware)

@router.message(F.chat.type.in_({"group", "supergroup"}), ~F.from_user.is_bot)
async def banned_words(message: Message):
    if message.from_user.id in BotConfig.ADMIN_IDS: return
    text = (message.text or "").lower()
    for word in DataLists.BANNED_WORDS:
        if word.lower() in text:
            try: await message.delete()
            except: pass
            warns = await db.add_warning(message.from_user.id)
            u_link = f'<a href="tg://user?id={message.from_user.id}">{html_escape(message.from_user.first_name)}</a>'
            if warns >= 3:
                await db.mute_user(message.from_user.id, 24)
                try: await bot.restrict_chat_member(message.chat.id, message.from_user.id, ChatPermissions(can_send_messages=False), until_date=datetime.now() + timedelta(hours=24))
                except: pass
                msg = f"🚫 {u_link}, siz 3 marta qoidani buzdingiz! 1 kunga yozish huquqidan mahrum qilindingiz."
            else:
                msg = f"⚠️ {u_link}, Iltimos reklama tarqatmang!\n\nSiz {warns}-marta qoidani buzdingiz. Yana {3-warns} marta qilsangiz, 1 kunga bloklanasiz."
            await message.answer(msg, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📢 Reklama berish", url=BotConfig.BOT_LINK)]]))
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
    if len(args) > 1 and args[1].startswith("REF"): await state.update_data(ref=args[1])
    
    s_ok, h_ok = await check_subscription(message.from_user.id)
    if s_ok and h_ok:
        await message.answer(Texts.START_TEXT, reply_markup=phone_kb())
        await state.set_state(RegStates.waiting_phone)
    else:
        await message.answer("👋 <b>Assalomu alaykum!</b>\n\nBotdan foydalanish uchun kanallarga obuna bo'ling:", reply_markup=get_sub_kb(s_ok, h_ok))

@router.callback_query(F.data == "noop")
async def noop(call: CallbackQuery): await safe_answer(call, Texts.SUB_OK_ALERT)

@router.callback_query(F.data == "check_sub")
async def check_sub(call: CallbackQuery, state: FSMContext):
    s_ok, h_ok = await check_subscription(call.from_user.id)
    if s_ok and h_ok:
        await safe_edit_text(call.message, Texts.START_TEXT, reply_markup=phone_kb())
        await state.set_state(RegStates.waiting_phone)
    else: await safe_answer(call, "❌ Iltimos, barcha kanallarga obuna bo'ling!", True)

@router.callback_query(F.data == "continue_reg")
async def cont_reg(call: CallbackQuery, state: FSMContext):
    await safe_edit_text(call.message, Texts.START_TEXT, reply_markup=phone_kb())
    await state.set_state(RegStates.waiting_phone)

@router.message(RegStates.waiting_phone, F.contact | F.text)
async def process_phone(message: Message, state: FSMContext):
    phone = message.contact.phone_number if message.contact else (message.text or "").strip()
    if not message.contact and not re.match(r"^\+?998\d{9}$", phone.replace(" ", "")): return await message.answer(Texts.ASK_PHONE)
    phone = phone if phone.startswith("+") else f"+{phone}"
    data = await state.get_data()
    try:
        user = await db.create_user(message.from_user.id, f"@{message.from_user.username}" if message.from_user.username else "Noma'lum", message.from_user.full_name, phone, data.get("ref"))
        await message.answer(Texts.REG_SUCCESS.format(user_number=user["user_number"], score=user["score"], referrals=0), reply_markup=ReplyKeyboardRemove())
        await message.answer(Texts.MAIN_MENU, reply_markup=main_menu(message.from_user.id in BotConfig.ADMIN_IDS))
        await state.clear()
    except Exception as e: await message.answer(f"❌ {e}")

# =====================================================================
# MENYULAR
# =====================================================================
@router.callback_query(F.data == "menu_back_to_main")
async def back_main(call: CallbackQuery): await safe_edit_text(call.message, Texts.MAIN_MENU, main_menu(call.from_user.id in BotConfig.ADMIN_IDS))

@router.callback_query(F.data == "menu_konkurs")
async def konkurs(call: CallbackQuery):
    user = await db.get_user(call.from_user.id)
    ref = f"https://t.me/{BotConfig.BOT_USERNAME.replace('@', '')}?start=REF{user['id']}"
    text = f"🏆 <b>Konkurs</b>\n\n👥 Sizning ballaringiz: <b>{user['score']}</b>\n🔗 Havolangiz:\n<code>{ref}</code>\n\nDo'stlaringizni taklif qiling va ball to'plang!"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📤 Ulashish", url=f"https://t.me/share/url?url={ref}")], [InlineKeyboardButton(text="🏆 Reyting", callback_data="menu_rating")], [InlineKeyboardButton(text="↩️ Orqaga", callback_data="menu_back_to_main")]])
    await safe_edit_text(call.message, text, kb)

@router.callback_query(F.data == "menu_rating")
async def rating(call: CallbackQuery):
    top = await db.get_top_10_users()
    text = "🥇 <b>Top 10 Foydalanuvchilar</b>\n\n"
    for i, u in enumerate(top, 1):
        medal = "🥇" if i==1 else "🥈" if i==2 else "🥉" if i==3 else f"{i}."
        text += f"{medal} {html_escape(u['full_name'])} — <b>{u['score']} ball</b>\n"
    await safe_edit_text(call.message, text, InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="↩️ Orqaga", callback_data="menu_konkurs")]]))

@router.callback_query(F.data == "menu_reklama")
async def reklama(call: CallbackQuery, state: FSMContext):
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💰 Sotish", callback_data="adtype_sotish")], [InlineKeyboardButton(text="🎁 Hadiya", callback_data="adtype_hadiya")], [InlineKeyboardButton(text="↩️ Orqaga", callback_data="menu_back_to_main")]])
    await safe_edit_text(call.message, "🎯 <b>E'lon turini tanlang:</b>", kb)

@router.callback_query(F.data == "menu_my_orders")
async def my_orders(call: CallbackQuery):
    ads = await db.get_user_ads(call.from_user.id)
    await safe_edit_text(call.message, "⏳ Yuklanmoqda...", None)
    if not ads: return await call.message.answer("📭 Sizda e'lonlar yo'q.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="↩️ Orqaga", callback_data="menu_back_to_main")]]))
    
    st_map = {"pending": "⏳ Kutilmoqda", "approved": "✅ Tasdiqlangan", "rejected": "❌ Rad etilgan"}
    for ad in ads:
        text = f"🐱 <b>{html_escape(str(ad['breed']))}</b> | {st_map.get(ad['status'], ad['status'])}\n📅 {ad['created_at'].strftime('%d.%m.%Y')}"
        kb = None
        if ad['status'] == "approved":
            action = "✅ Berib bo'ldim" if ad['ad_type'] == "hadiya" else "💰 Sotildi"
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=action, callback_data=f"done_ad_{ad['id']}")]])
        
        photos = json.loads(ad['photos']) if isinstance(ad['photos'], str) else (ad['photos'] or [])
        if photos:
            if len(photos[0]) > 100 or photos[0].endswith(".mp4"): await call.message.answer_video(photos[0], caption=text, reply_markup=kb)
            else: await call.message.answer_photo(photos[0], caption=text, reply_markup=kb)
        else: await call.message.answer(text, reply_markup=kb)
    await call.message.answer("Menyu:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="↩️ Orqaga", callback_data="menu_back_to_main")]]))

@router.callback_query(F.data.startswith("done_ad_"))
async def user_done_ad(call: CallbackQuery):
    ad_id = int(call.data.split("_")[2])
    ad = await db.get_ad(ad_id)
    if not ad or ad["user_id"] != call.from_user.id: return await safe_answer(call, "Xato!", True)
    
    action = "BERILDI 🎁" if ad["ad_type"] == "hadiya" else "SOTILDI 💰"
    await db.delete_ad(ad_id)
    if ad.get("channel_message_id"):
        try:
            target = CHANNEL_SOTISH_ID if ad["ad_type"] == "sotish" else CHANNEL_HADIYA_ID
            new_cap = f"#{action}\n\n📝 {html_escape(str(ad['breed']))} | {html_escape(str(ad['age']))}\n\n📍 {html_escape(str(ad['address']))}\n📞 <i>Yashirilgan</i>\n\n✅ <b>E'LON YOPILDI</b>"
            if ad['photos']: await bot.edit_message_caption(target, ad["channel_message_id"], caption=new_cap, reply_markup=None)
            else: await bot.edit_message_text(target, ad["channel_message_id"], text=new_cap, reply_markup=None)
        except: pass
    await safe_answer(call, "✅ E'lon o'chirildi!", True)
    await call.message.delete()

# =====================================================================
# E'LON YARATISH JARAYONI
# =====================================================================
@router.callback_query(F.data.startswith("adtype_"))
async def choose_type(call: CallbackQuery, state: FSMContext):
    ad_type = call.data.split("_")[1]
    await state.update_data(ad_type=ad_type)
    if ad_type == "sotish":
        await state.set_state(AdStates.cat_count)
        await safe_edit_text(call.message, "🐱 Nechta sotmoqchisiz?", InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"{i}", callback_data=f"cat_{i}") for i in range(1, 6)]]))
    else:
        await state.set_state(AdStates.media)
        await safe_edit_text(call.message, "📸 Media yuboring:", InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🖼️ Rasm", callback_data="m_photo")], [InlineKeyboardButton(text="🎥 Video", callback_data="m_video")]]))

@router.callback_query(AdStates.cat_count, F.data.startswith("cat_"))
async def process_cat(call: CallbackQuery, state: FSMContext):
    count = int(call.data.split("_")[1])
    await state.update_data(cat_count=count, bot_price=Prices.get_bot_price(count))
    await state.set_state(AdStates.media)
    await safe_edit_text(call.message, "📸 Media yuboring:", InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🖼️ Rasm", callback_data="m_photo")], [InlineKeyboardButton(text="🎥 Video", callback_data="m_video")]]))

@router.callback_query(F.data.startswith("m_"))
async def choose_media(call: CallbackQuery, state: FSMContext):
    await state.update_data(m_type=call.data.split("_")[1], photos=[])
    await state.set_state(AdStates.media)
    await safe_edit_text(call.message, "Rasm yoki video yuboring:", None)

@router.message(AdStates.media, F.photo | F.video)
async def receive_media(message: Message, state: FSMContext):
    data = await state.get_data()
    if message.photo and data.get("m_type") != "photo": return await message.answer("❌ Faqat video yuboring!")
    if message.video and data.get("m_type") != "video": return await message.answer("❌ Faqat rasm yuboring!")
    if message.video and message.video.duration > 60: return await message.answer("❌ Video 1 daqiqadan oshmasin!")
    
    photos = data.get("photos", [])
    if len(photos) >= 3: return await message.answer("❌ Maksimum 3 ta rasm.")
    
    photos.append(message.photo[-1].file_id if message.photo else message.video.file_id)
    await state.update_data(photos=photos)
    await message.answer(f"✅ Qabul qilindi ({len(photos)}).", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➡️ Davom etish", callback_data="next_step")]]))

@router.callback_query(F.data == "next_step")
async def next_step(call: CallbackQuery, state: FSMContext):
    await state.set_state(AdStates.breed)
    await safe_edit_text(call.message, "🐱 Zotni tanlang (yoki yozing):", InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✏️ O'zim yozaman", callback_data="custom_breed")], [InlineKeyboardButton(text="Mushuk", callback_data="b_Mushuk")]]))

@router.callback_query(AdStates.breed, F.data == "custom_breed")
async def custom_b(call: CallbackQuery, state: FSMContext):
    await safe_edit_text(call.message, "✏️ Zotni yozing:", None)
    await state.set_state(AdStates.custom_breed)

@router.message(AdStates.custom_breed)
async def save_b(message: Message, state: FSMContext):
    await state.update_data(breed=message.text)
    await state.set_state(AdStates.age)
    await message.answer("🎂 Yoshni tanlang:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="1 yosh", callback_data="a_1 yosh"), InlineKeyboardButton(text="2 yosh", callback_data="a_2 yosh")]]))

@router.callback_query(AdStates.breed, F.data.startswith("b_"))
async def save_b_cb(call: CallbackQuery, state: FSMContext):
    await state.update_data(breed=call.data.replace("b_", ""))
    await state.set_state(AdStates.age)
    await safe_edit_text(call.message, "🎂 Yoshni tanlang:", InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="1 yosh", callback_data="a_1 yosh"), InlineKeyboardButton(text="2 yosh", callback_data="a_2 yosh")]]))

@router.callback_query(AdStates.age, F.data.startswith("a_"))
async def save_a(call: CallbackQuery, state: FSMContext):
    await state.update_data(age=call.data.replace("a_", ""))
    await state.set_state(AdStates.address)
    await safe_edit_text(call.message, "📍 Manzilni yozing:", None)

@router.message(AdStates.address)
async def save_addr(message: Message, state: FSMContext):
    await state.update_data(address=message.text, phone="+998901234567", gender="Qiz", health="Sog'lom", sterilization="Ha")
    data = await state.get_data()
    if data["ad_type"] == "hadiya": return await preview_ad(message, state)
    await state.set_state(AdStates.price)
    await message.answer("💰 Narxni kiriting (so'mda):")

@router.message(AdStates.price)
async def save_price(message: Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("❌ Faqat raqam!")
    await state.update_data(price=message.text, currency="so'm")
    await preview_ad(message, state)

async def preview_ad(msg: Message, state: FSMContext):
    data = await state.get_data()
    user = await db.get_user(msg.from_user.id)
    price = data.get("bot_price", 0)
    
    cap = f"📋 <b>Tekshirish:</b>\n\n🐱 {data['breed']} | {data['age']}\n📍 {data['address']}\n"
    if data['ad_type'] != "hadiya": cap += f"💰 {data['price']} {data['currency']}\n"
    cap += f"\n💳 Balans: {user['balance']:,} so'm\n"
    if price > 0: cap += f"💸 Yechiladi: {price:,} so'm\n\n❓ <b>Tasdiqlaysizmi?</b>"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Ha, tasdiqlash", callback_data="final_confirm")], [InlineKeyboardButton(text="❌ Bekor", callback_data="menu_reklama")]])
    await state.set_state(AdStates.preview)
    
    photos = data.get("photos", [])
    if photos:
        if data["m_type"] == "video": await msg.answer_video(photos[0], caption=cap, reply_markup=kb)
        else: await msg.answer_photo(photos[0], caption=cap, reply_markup=kb)
    else: await msg.answer(cap, reply_markup=kb)

@router.callback_query(AdStates.preview, F.data == "final_confirm")
async def confirm(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user = await db.get_user(call.from_user.id)
    price = data.get("bot_price", 0)
    if user["balance"] < price: return await safe_answer(call, "❌ Mablag' yetarli emas!", True)
    
    if price > 0: await db.update_user_balance(user["id"], price, "subtract")
    new_ad = await db.create_ad(user["id"], data["ad_type"], "bot", data["photos"], data["breed"], data["age"], data["gender"], data["health"], data["sterilization"], data["address"], data["phone"], data.get("price", "0"), data.get("currency", "so'm"), 1, data.get("cat_count", 1), price)
    
    await call.message.delete()
    await call.message.answer("✅ Adminga yuborildi!")
    
    admin_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"adm_ok_{new_ad['id']}"), InlineKeyboardButton(text="❌ Rad etish", callback_data=f"adm_no_{new_ad['id']}")]])
    admin_cap = f"🆕 <b>YANGI E'LON</b>\n\n👤 #{user['user_number']}\n🐱 {data['breed']}\n💰 To'landi: {price}"
    
    if data["photos"]:
        if data["m_type"] == "video": await bot.send_video(BotConfig.TECH_ADMIN_ID, data["photos"][0], caption=admin_cap, reply_markup=admin_kb)
        else: await bot.send_photo(BotConfig.TECH_ADMIN_ID, data["photos"][0], caption=admin_cap, reply_markup=admin_kb)
    else: await bot.send_message(BotConfig.TECH_ADMIN_ID, admin_cap, reply_markup=admin_kb)
    await state.clear()

# =====================================================================
# ADMIN TASDIQLASH
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
        
        act = "Berib bo'ldim" if ad["ad_type"] == "hadiya" else "Sotildi"
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"✅ {act}", callback_data=f"done_ad_{ad_id}")], [InlineKeyboardButton(text="👁 Ko'rish", url=link)]])
        await bot.send_message(ad["user_id"], "✅ E'loningiz kanalga chiqdi!", reply_markup=kb)
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
    await call.message.reply("Rad etish sababini yozing:")

@router.message(AdminStates.decline)
async def do_decline(message: Message, state: FSMContext):
    ad_id = (await state.get_data()).get("decline_id")
    ad = await db.get_ad(ad_id)
    await db.update_ad_status(ad_id, "rejected", reason=message.text)
    if ad and ad.get("price_paid", 0) > 0:
        await db.update_user_balance(ad["user_id"], ad["price_paid"], "add")
        await bot.send_message(ad["user_id"], f"❌ Rad etildi. Sabab: {message.text}\n\nPul qaytarildi.")
    await message.answer("✅ Rad etildi.")
    await state.clear()

# =====================================================================
# STARTUP
# =====================================================================
@dp.startup()
async def on_startup():
    await db.connect()
    try: await bot.set_my_commands([BotCommand(command="start", description="Ishga tushirish")])
    except: pass
    logger.info("🚀 Bot ishga tushdi")

    try:
        async with db.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT session_string FROM userbot_sessions WHERE is_active = TRUE LIMIT 1")
        if row and row["session_string"]: await start_userbot(row["session_string"])
    except Exception as e: logger.warning(f"Userbot xatosi: {e}")

@dp.shutdown()
async def on_shutdown():
    if userbot_client and userbot_client.is_connected(): await userbot_client.disconnect()
    await db.disconnect()

async def main(): await dp.start_polling(bot)

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
