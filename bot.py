# ==============================================================================
# LOYIHA: UzbekCats Bot & Web App
# FAYL: bot.py
# TAVSIF: To'liq, xatosiz, barcha funksiyalar ishlaydigan Telegram Bot (Aiogram v3)
# ==============================================================================

import asyncio
import json
import logging
import re
import traceback
from datetime import datetime, timedelta
from html import escape as html_escape

from aiogram import Bot, Dispatcher, F, Router, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BotCommand, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, Message, ReplyKeyboardMarkup, ReplyKeyboardRemove,
    ChatPermissions, InputMediaPhoto, InputMediaVideo, ErrorEvent
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
# GLOBAL XATOLARNI USHLAGICH (Error Handler)
# =====================================================================
@dp.errors()
async def global_error_handler(event: ErrorEvent):
    """
    Botda yuz beradigan har qanday kutilmagan xatoni ushlaydi va logga yozadi.
    Bot qotib qolmaydi, foydalanuvchiga xabar yuboradi.
    """
    logger.error(f"❌ Kutilmagan xato: {event.exception}\n{traceback.format_exc()}")
    
    # Agar xabar foydalanuvchidan kelgan bo'lsa, unga xabar berishga harakat qilamiz
    update = event.update
    if update.message:
        try:
            await update.message.answer("❌ Kechirasiz, tizimda kutilmagan xatolik yuz berdi. Iltimos, keyinroq qayta urinib ko'ring yoki adminga murojaat qiling.")
        except Exception:
            pass
    elif update.callback_query:
        try:
            await update.callback_query.answer("❌ Tizim xatosi. Iltimos qaytadan urinib ko'ring.", show_alert=True)
        except Exception:
            pass
    return True

# =====================================================================
# YORDAMCHI FUNKSIYALAR (Eski xabarlar va xatolarni oldini olish)
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
# USERBOT (EOF XATOSI TO'LIQ TUZATILDI)
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
        await userbot_client.connect()  # start() emas, connect() ishlatiladi

        if not await userbot_client.is_user_authorized():
            logger.error("❌ Userbot sessiyasi eskirgan yoki yaroqsiz! Qaytadan ulang.")
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
        except Exception as e:
            logger.warning(f"Obunani tekshirishda xato (chat_id={chat_id}): {e}")
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
# KANALGA POST (XATO TUZATILDI: "message is not modified" va Albom)
# =====================================================================
async def post_to_channel(ad_data: dict):
    ad_type = ad_data.get("ad_type")
    address = html_escape(str(ad_data.get("address") or "—"))
    phone = html_escape(str(ad_data.get("phone") or "—"))
    price = html_escape(str(ad_data.get("price") or "0"))
    currency = html_escape(str(ad_data.get("currency") or "so'm"))

    cats_data = ad_data.get("cats_data") or []
    if isinstance(cats_data, str):
        try: cats_data = json.loads(cats_data)
        except: cats_data = []

    if not cats_data:
        cats_data = [{
            "breed": ad_data.get("breed") or "—",
            "age": ad_data.get("age") or "—",
            "gender": ad_data.get("gender") or "—",
            "health": ad_data.get("health") or "—",
            "sterilization": ad_data.get("sterilization") or "—"
        }]

    cats_text = ""
    for i, cat in enumerate(cats_data, 1):
        cats_text += f"🐱 <b>{i}-mushuk:</b> {html_escape(str(cat.get('breed', '—')))} | {html_escape(str(cat.get('age', '—')))} | {html_escape(str(cat.get('gender', '—')))} | {html_escape(str(cat.get('health', '—')))} | {html_escape(str(cat.get('sterilization', '—')))}\n"

    footer = (
        '👤 <a href="https://t.me/zayd_catlover">Admin</a>\n'
        '📢 <a href="https://t.me/Uzbek_cat_bot?start=reklama">Reklama berish</a>\n\n'
        '<a href="https://youtu.be/vdwgSB7_amw">YouTube</a> | <a href="https://www.instagram.com/p/C-cZkgstVGK/">Instagram</a> | <a href="https://t.me/uzbek_cats">Telegram</a>'
    )

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
        logger.error(f"❌ Kanalga yuborishda xato (chat={target}): {e}")
        raise

# =====================================================================
# MIDDLEWARE (Mute va Ban)
# =====================================================================
async def check_user_middleware(handler, event: Message, data: dict):
    if not hasattr(event, 'from_user') or not event.from_user:
        return await handler(event, data)

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
            try:
                await message.delete()
            except:
                pass
            
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
                except:
                    pass
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
    except:
        pass
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
    except ValueError as ve:
        # Telefon raqam bandligi xatosi
        await message.answer(f"❌ {str(ve)}")
        return
    except Exception as e:
        # Boshqa DB xatolari
        logger.error(f"Ro'yxatdan o'tishda xato: {e}")
        await message.answer(f"❌ Tizimda xatolik yuz berdi. Iltimos keyinroq qayta urinib ko'ring.")
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
    top_users = await db.get_top_users(limit=50)
    text = "🥇 <b>Eng faol foydalanuvchilar (Top 50)</b>\n\n"
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
# MENING E'LONLARIM (HAR BIRI ALOHIDA POST)
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
        if isinstance(cats_data, str):
            try: cats_data = json.loads(cats_data)
            except: cats_data = []
            
        breed_display = cats_data[0].get("breed", "—") if cats_data else ad.get("breed", "—")
        
        text = f"🐱 <b>{html_escape(str(breed_display))}</b> | {st}\n📅 {ad['created_at'].strftime('%d.%m.%Y')}"
        
        kb = None
        if ad["status"] == "approved":
            action_text = "✅ Berib bo'ldim" if ad["ad_type"] == "hadiya" else "💰 Sotildi"
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=action_text, callback_data=f"user_ad_done_{ad['id']}")]])
            
        photos = ad.get("photos") or []
        if isinstance(photos, str):
            try: photos = json.loads(photos)
            except: photos = []
            
        if photos:
            if len(photos[0]) > 100 or photos[0].endswith(".mp4"):
                await call.message.answer_video(video=photos[0], caption=text, reply_markup=kb)
            else:
                await call.message.answer_photo(photo=photos[0], caption=text, reply_markup=kb)
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

    action_text = "Berib bo'lindi" if ad["ad_type"] == "hadiya" else "Sotildi"
    await db.delete_ad(ad_id)
    
    if ad.get("channel_message_id"):
        try:
            target_chat = CHANNEL_SOTISH_ID if ad["ad_type"] == "sotish" else CHANNEL_HADIYA_ID
            old_caption = f"#SOTILDI 💰" if ad["ad_type"] == "sotish" else f"#BERILDI 🎁"
            address = html_escape(str(ad.get("address") or "—"))
            
            new_caption = f"{old_caption}\n\n📍 Manzil: {address}\n📞 Tel: <i>Yashirilgan</i>\n\n✅ <b>E'LON {action_text.upper()}!</b>"
            
            if ad.get("photos"):
                await bot.edit_message_caption(chat_id=target_chat, message_id=ad["channel_message_id"], caption=new_caption, reply_markup=None)
            else:
                await bot.edit_message_text(chat_id=target_chat, message_id=ad["channel_message_id"], text=new_caption, reply_markup=None)
        except Exception as e:
            logger.error(f"Kanal xabarini tahrirlashda xato: {e}")

    await safe_answer(call, f"✅ E'lon {action_text} deb belgilandi va o'chirildi!", show_alert=True)
    await safe_delete(call.message)

# =====================================================================
# REKLAMA JARAYONI
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
    await state.update_data(cat_count=count, bot_price=Prices.get_bot_price(count))
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
    await message.answer(f"✅ <b>{len(photos)}-rasm qabul qilindi.</b> Yana yuborishingiz yoki davom etishingiz mumkin.", reply_markup=kb)

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
    await state.update_data(current_cat_index=1, cats_data=[])
    await safe_edit_text(call.message, f"🐱 <b>1-mushuk zotini tanlang:</b>", reply_markup=get_breed_kb(0))
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
    data = await state.get_data()
    idx = data.get("current_cat_index", 1)
    await safe_edit_text(call.message, f"🎂 <b>{idx}-mushuk yoshini tanlang:</b>", reply_markup=get_age_kb())
    await state.set_state(AdStates.choosing_age)

@router.callback_query(AdStates.choosing_breed, F.data == "breed_custom")
async def custom_breed(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    idx = data.get("current_cat_index", 1)
    await safe_edit_text(call.message, f"✏️ <b>{idx}-mushuk zotini yozing:</b>", reply_markup=None)
    await state.set_state(AdStates.custom_breed)

@router.message(AdStates.custom_breed)
async def process_custom_breed(message: Message, state: FSMContext):
    await state.update_data(current_breed=message.text)
    data = await state.get_data()
    idx = data.get("current_cat_index", 1)
    await message.answer(f"🎂 <b>{idx}-mushuk yoshini tanlang:</b>", reply_markup=get_age_kb())
    await state.set_state(AdStates.choosing_age)

@router.callback_query(AdStates.choosing_age, F.data.startswith("age_"))
async def process_age(call: CallbackQuery, state: FSMContext):
    age = call.data.replace("age_", "").replace("_", " ")
    await state.update_data(current_age=age)
    data = await state.get_data()
    idx = data.get("current_cat_index", 1)
    await safe_edit_text(call.message, f"❤️ <b>{idx}-mushuk sog'lig'ini tanlang:</b>", reply_markup=get_simple_kb([("Sog'lom", "soglom"), ("Kasal", "kasal")], "health"))
    await state.set_state(AdStates.choosing_health)

@router.callback_query(AdStates.choosing_health, F.data.startswith("health_"))
async def process_health(call: CallbackQuery, state: FSMContext):
    health = "Sog'lom" if "soglom" in call.data else "Kasal"
    await state.update_data(current_health=health)
    data = await state.get_data()
    idx = data.get("current_cat_index", 1)
    await safe_edit_text(call.message, f"👤 <b>{idx}-mushuk jinsini tanlang:</b>", reply_markup=get_simple_kb([("♀️ Qiz bola", "qiz"), ("♂️ O'g'il bola", "ogil")], "gender"))
    await state.set_state(AdStates.choosing_gender)

@router.callback_query(AdStates.choosing_gender, F.data.startswith("gender_"))
async def process_gender(call: CallbackQuery, state: FSMContext):
    gender = "Qiz bola" if "qiz" in call.data else "O'g'il bola"
    await state.update_data(current_gender=gender)
    data = await state.get_data()
    idx = data.get("current_cat_index", 1)
    await safe_edit_text(call.message, f"🧬 <b>{idx}-mushuk nasl olishi mumkinmi?</b>", reply_markup=get_simple_kb([("✅ Ha", "yes"), ("❌ Yo'q", "no")], "sterilization"))
    await state.set_state(AdStates.choosing_sterilization)

@router.callback_query(AdStates.choosing_sterilization, F.data.startswith("sterilization_"))
async def process_sterilization(call: CallbackQuery, state: FSMContext):
    sterilization = "Nasl olish mumkin" if "yes" in call.data else "Nasl olish mumkin emas"
    data = await state.get_data()
    
    new_cat = {
        "breed": data.get("current_breed", "—"),
        "age": data.get("current_age", "—"),
        "health": data.get("current_health", "—"),
        "gender": data.get("current_gender", "—"),
        "sterilization": sterilization
    }
    
    cats_data = data.get("cats_data", [])
    cats_data.append(new_cat)
    await state.update_data(cats_data=cats_data)
    
    idx = data.get("current_cat_index", 1)
    total = data.get("cat_count", 1)
    
    if idx < total:
        next_idx = idx + 1
        await state.update_data(current_cat_index=next_idx)
        await safe_edit_text(call.message, f"🐱 <b>{next_idx}-mushuk zotini tanlang:</b>", reply_markup=get_breed_kb(0))
        await state.set_state(AdStates.choosing_breed)
    else:
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
# PREVIEW (PUL YECHISHDAN OLDIN TASDIQLASH)
# =====================================================================
async def send_ad_preview(message: Message, state: FSMContext):
    data = await state.get_data()
    user = await db.get_user(message.from_user.id if message.from_user else message.chat.id)
    price = data.get("bot_price", 0)
    
    address_safe = html_escape(str(data.get('address') or '—'))
    phone_safe = html_escape(str(data.get('phone') or '—'))
    price_safe = html_escape(str(data.get('price') or '0'))
    currency_safe = html_escape(str(data.get('currency') or "so'm"))
    
    cats_data = data.get("cats_data", [])
    cats_text = ""
    for i, cat in enumerate(cats_data, 1):
        cats_text += f"🐱 <b>{i}-mushuk:</b> {html_escape(str(cat.get('breed')))} | {html_escape(str(cat.get('age')))} | {html_escape(str(cat.get('gender')))}\n"

    caption = "📋 <b>Ma'lumotlaringizni tekshiring:</b>\n\n"
    caption += f"{cats_text}\n"
    caption += f"📍 Manzil: {address_safe}\n📞 Tel: {phone_safe}\n"
    if data.get("ad_type") != "hadiya":
        caption += f"💰 Narx: {price_safe} {currency_safe}\n"
    
    if price > 0:
        caption += f"\n💳 <b>Hisobingiz:</b> {user['balance']:,} so'm\n"
        caption += f"💸 <b>Yechiladi:</b> {price:,} so'm\n\n"
        if user['balance'] < price:
            caption += "❌ <b>Diqqat! Mablag' yetarli emas. Iltimos, hisobni to'ldiring.</b>"
        else:
            caption += "❓ <b>Shuncha summa yechishga tayyormisiz?</b>"
    
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
        try:
            await db.update_user_balance(user["id"], price, "subtract")
        except Exception:
            await safe_answer(call, "❌ Mablag' yechishda xatolik!", show_alert=True)
            return

    new_ad = await db.create_ad(
        user_id=user["id"], ad_type=data.get("ad_type"), tariff="bot",
        photos=data.get("photos", []), cats_data=data.get("cats_data", []),
        address=data.get("address"), phone=data.get("phone"), price=data.get("price", "0"),
        currency=data.get("currency", "so'm"), ad_number=(user.get("ad_count") or 0) + 1,
        cat_count=data.get("cat_count", 1), price_paid=price,
    )

    await safe_delete(call.message)
    await bot.send_message(call.from_user.id, Texts.AD_ACCEPTED)

    admin_caption = f"🆕 <b>YANGI REKLAMA!</b>\n\n👤 Foydalanuvchi: #{user['user_number']} ({html_escape(user['username'] or '—')})\n📋 Turi: {str(data.get('ad_type')).upper()}\n📍 Manzil: {html_escape(str(data.get('address') or '—'))}\n📞 Tel: {html_escape(str(data.get('phone') or '—'))}\n💵 To'landi: {price:,} so'm\n\n"
    
    cats_data = data.get("cats_data", [])
    for i, cat in enumerate(cats_data, 1):
        admin_caption += f"🐱 {i}-mushuk: {cat.get('breed')} | {cat.get('age')} | {cat.get('gender')}\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"admin_approve_ad_{new_ad['id']}"),
        InlineKeyboardButton(text="✏️ O'zgartirish", callback_data=f"admin_edit_ad_{new_ad['id']}"),
        InlineKeyboardButton(text="❌ Rad etish", callback_data=f"admin_decline_ad_{new_ad['id']}")
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
# ADMIN: TASDIQLASH VA RAD ETISH
# =====================================================================
@router.callback_query(F.data.startswith("admin_approve_ad_"))
async def tech_admin_approve(call: CallbackQuery):
    if call.from_user.id not in BotConfig.ADMIN_IDS:
        await safe_answer(call, "Ruxsat yo'q", show_alert=True)
        return
    ad_id = int(call.data.split("_")[3])
    
    ad = await db.get_ad(ad_id)
    if not ad: 
        await safe_answer(call, "E'lon topilmadi", show_alert=True)
        return
    if ad["status"] != "pending":
        await call.message.edit_reply_markup(reply_markup=None)
        await safe_answer(call, "⚠️ Bu e'lon allaqachon tasdiqlangan yoki rad etilgan!", show_alert=True)
        return

    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except:
        pass

    try:
        sent = await post_to_channel(ad)
        await db.update_ad_status(ad_id, "approved", channel_message_id=sent.message_id)
        
        ch_id_str = str(BotConfig.CHANNEL_SOTISH_ID if ad["ad_type"] == "sotish" else BotConfig.CHANNEL_HADIYA_ID).replace("-100", "")
        post_link = f"https://t.me/c/{ch_id_str}/{sent.message_id}"
        
        action_text = "Berib bo'ldim" if ad["ad_type"] == "hadiya" else "Sotildi"
        user_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"✅ {action_text}", callback_data=f"user_ad_done_{ad_id}")],
            [InlineKeyboardButton(text="👁 Reklamani ko'rish", url=post_link)],
            [InlineKeyboardButton(text="🏠 Asosiy menyu", callback_data="menu_back_to_main")]
        ])
        await bot.send_message(ad["user_id"], f"✅ <b>Sizning e'loningiz tasdiqlandi va kanalga joylandi!</b>\n\n<i>E'lon o'z joyiga ega bo'lgach, «{action_text}» tugmasini bosing.</i>", reply_markup=user_kb)
        
        await safe_answer(call, "✅ Kanalga yuborildi!", show_alert=False)
    except Exception as e:
        await safe_answer(call, f"❌ Xato: {e}", show_alert=True)

@router.callback_query(F.data.startswith("admin_decline_ad_"))
async def tech_admin_decline(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in BotConfig.ADMIN_IDS:
        return
    ad_id = int(call.data.split("_")[3])
    
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    
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
# ADMIN: E'LONNI TAHRIRLASH (EDIT)
# =====================================================================
@router.callback_query(F.data.startswith("admin_edit_ad_"))
async def admin_edit_ad_menu(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in BotConfig.ADMIN_IDS:
        return
    ad_id = int(call.data.split("_")[3])
    await state.update_data(edit_ad_id=ad_id)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📍 Manzilni o'zgartirish", callback_data="edit_field_address"), InlineKeyboardButton(text="📞 Telefonni o'zgartirish", callback_data="edit_field_phone")],
        [InlineKeyboardButton(text="💰 Narxni o'zgartirish", callback_data="edit_field_price")],
        [InlineKeyboardButton(text="↩️ Bekor qilish", callback_data="admin_cancel_edit")]
    ])
    await call.message.reply("✏️ <b>Qaysi maydonni o'zgartirmoqchisiz?</b>", reply_markup=kb)
    await state.set_state(AdminStates.editing_ad_field)

@router.callback_query(AdminStates.editing_ad_field, F.data.startswith("edit_field_"))
async def admin_edit_field_choose(call: CallbackQuery, state: FSMContext):
    field = call.data.replace("edit_field_", "")
    await state.update_data(edit_field=field)
    
    field_names = {"address": "Manzilni", "phone": "Telefon raqamni", "price": "Narxni"}
    await safe_edit_text(call.message, f"Yangi {field_names.get(field, 'qiymatni')} kiriting:")
    await state.set_state(AdminStates.editing_ad_value)

@router.message(AdminStates.editing_ad_value)
async def admin_edit_value_save(message: Message, state: FSMContext):
    data = await state.get_data()
    ad_id, field = data.get("edit_ad_id"), data.get("edit_field")
    
    await db.update_ad_details(ad_id, **{field: message.text})
    await message.answer("✅ Muvaffaqiyatli o'zgartirildi!")
    
    ad = await db.get_ad(ad_id)
    
    admin_caption = f"🔄 <b>YANGILANGAN REKLAMA!</b>\n\n👤 User ID: {ad['user_id']}\n📍 Manzil: {html_escape(str(ad.get('address') or '—'))}\n📞 Tel: {html_escape(str(ad.get('phone') or '—'))}\n💰 Narx: {html_escape(str(ad.get('price') or '0'))}\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"admin_approve_ad_{ad_id}"),
        InlineKeyboardButton(text="✏️ O'zgartirish", callback_data=f"admin_edit_ad_{ad_id}"),
        InlineKeyboardButton(text="❌ Rad etish", callback_data=f"admin_decline_ad_{ad_id}")
    ]])
    
    photos = ad.get("photos") or []
    if isinstance(photos, str): 
        try: photos = json.loads(photos)
        except: photos = []
    
    if photos:
        if len(photos[0]) > 50:
            await message.answer_video(video=photos[0], caption=admin_caption, reply_markup=kb)
        else:
            await message.answer_photo(photo=photos[0], caption=admin_caption, reply_markup=kb)
    else:
        await message.answer(admin_caption, reply_markup=kb)
    await state.clear()

@router.callback_query(F.data == "admin_cancel_edit")
async def admin_cancel_edit(call: CallbackQuery, state: FSMContext):
    await safe_delete(call.message)
    await state.clear()

# =====================================================================
# ADMIN PANEL
# =====================================================================
@router.callback_query(F.data == "admin_panel")
async def admin_panel(call: CallbackQuery):
    if call.from_user.id not in BotConfig.ADMIN_IDS:
        return
    stats = await db.get_statistics()
    text = f"👨‍💼 <b>Admin Paneli</b>\n\n👥 Foydalanuvchilar: {stats['total_users']}\n📢 Jami reklamalar: {stats['total_ads']}\n\n💰 <b>Bugungi tushum:</b> {stats['today_income']:,} so'm\n💵 <b>Oylik tushum:</b> {stats['month_income']:,} so'm"
    
    rows = [
        [InlineKeyboardButton(text="⚙️ Bot holati", callback_data="admin_toggle_bot")],
        [InlineKeyboardButton(text="💳 Hisob qo'shish", callback_data="admin_add_balance")],
        [InlineKeyboardButton(text="➕ Ball qo'shish", callback_data="admin_add_score")],
    ]
    if call.from_user.id == BotConfig.TECH_ADMIN_ID:
        rows.append([InlineKeyboardButton(text="👨‍💻 Texnik Admin", callback_data="tech_admin_panel")])
    rows.append([InlineKeyboardButton(text="↩️ Orqaga", callback_data="menu_back_to_main")])
    await safe_edit_text(call.message, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

@router.callback_query(F.data == "admin_toggle_bot")
async def admin_toggle_bot(call: CallbackQuery):
    if call.from_user.id not in BotConfig.ADMIN_IDS:
        return
    current = await db.get_setting("bot_enabled", "1")
    new_val = "0" if current == "1" else "1"
    await db.set_setting("bot_enabled", new_val)
    await safe_answer(call, "✅ Bot yoqildi!" if new_val == "1" else "🔴 Bot o'chirildi!", show_alert=True)

@router.callback_query(F.data == "admin_add_balance")
async def admin_add_balance_start(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in BotConfig.ADMIN_IDS:
        return
    await safe_edit_text(call.message, "💳 <b>Hisob qo'shish</b>\n\nFoydalanuvchi Telegram ID sini kiriting:\n(Masalan: <code>673018191</code>)\n\n/cancel — bekor qilish", reply_markup=None)
    await state.set_state(AdminStates.add_balance_user_id)

@router.message(AdminStates.add_balance_user_id)
async def admin_add_balance_user(message: Message, state: FSMContext):
    if (message.text or "") == "/cancel":
        await state.clear()
        await message.answer("Bekor qilindi.")
        return
    if not (message.text or "").isdigit():
        await message.answer("❌ Faqat raqam kiriting:")
        return
    uid = int(message.text)
    user = await db.get_user(uid)
    if not user:
        await message.answer("❌ Bunday ID li foydalanuvchi topilmadi.")
        return
    await state.update_data(target_user_id=uid)
    await message.answer(f"👤 #{user['user_number']} ({html_escape(user['username'] or '—')})\n\nSumma kiriting (ayirish uchun <code>-50000</code>):")
    await state.set_state(AdminStates.add_balance_amount)

@router.message(AdminStates.add_balance_amount)
async def admin_add_balance_amount(message: Message, state: FSMContext):
    if (message.text or "") == "/cancel":
        await state.clear()
        await message.answer("Bekor qilindi.")
        return
    try:
        amount = int(message.text)
    except:
        await message.answer("❌ Noto'g'ri summa.")
        return
    
    uid = (await state.get_data()).get("target_user_id")
    op = "add" if amount > 0 else "subtract"
    try:
        new_bal = await db.update_user_balance(uid, abs(amount), op)
        msg = f"✅ Hisobingizga {amount:,} so'm qo'shildi." if amount > 0 else f"⚠️ Hisobingizdan {abs(amount):,} so'm yechildi."
        try:
            await bot.send_message(uid, f"{msg}\n\n💰 Joriy balans: {new_bal:,} so'm")
        except:
            pass
        await message.answer(f"✅ Bajarildi!\nYangi balans: {new_bal:,} so'm")
    except Exception as e:
        await message.answer(f"❌ Xatolik: {e}")
    await state.clear()

@router.callback_query(F.data == "admin_add_score")
async def admin_add_score(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in BotConfig.ADMIN_IDS:
        return
    await safe_edit_text(call.message, "📊 <b>Ball qo'shish</b>\n\nFormat: <code>+998901234567 - 17</code>\n\n/cancel — bekor qilish", reply_markup=None)
    await state.set_state(AdminStates.add_score_batch)

@router.message(AdminStates.add_score_batch)
async def process_add_score(message: Message, state: FSMContext):
    if (message.text or "") == "/cancel":
        await state.clear()
        await message.answer("Bekor qilindi.")
        return
    m = re.search(r"(\+?\d{9,15})\s*[-–—]?\s*(-?\d+)", message.text or "")
    if not m:
        await message.answer("❌ Format xato. Namuna: <code>+998901234567 - 17</code>")
        return
    ok = await db.add_score_by_phone_batch(m.group(1), int(m.group(2)))
    await message.answer("✅ Ball qo'shildi!" if ok else "❌ Topilmadi.")
    await state.clear()

# =====================================================================
# STARTUP / SHUTDOWN
# =====================================================================
@dp.startup()
async def on_startup():
    await db.connect()
    try:
        await bot.set_my_commands([BotCommand(command="start", description="Botni ishga tushirish")])
    except:
        pass
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
    if userbot_client and userbot_client.is_connected():
        await userbot_client.disconnect()
    await db.disconnect()

async def main():
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
