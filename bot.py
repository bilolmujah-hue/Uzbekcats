# ==============================================================================
# LOYIHA: UzbekCats Bot & Web App
# FAYL: bot.py
# TAVSIF: To'liq mukammal Telegram Bot (Aiogram v3) — Barcha xatolar tuzatildi
# ==============================================================================

import asyncio
import json
import logging
import re
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
)

from telethon import TelegramClient, events
from telethon.sessions import StringSession

from config import BotConfig, DataLists, Prices, Settings, Texts, UserbotConfig
from db import db

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# =====================================================================
# BOT + DISPATCHER
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
# YORDAMCHI
# =====================================================================
async def safe_edit_text(message: Message, text: str, reply_markup=None):
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest:
        try:
            await message.delete()
        except Exception:
            pass
        await message.answer(text, reply_markup=reply_markup)

async def safe_delete(message: Message):
    try:
        await message.delete()
    except Exception:
        pass

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
        except TelegramBadRequest as e:
            logger.warning(f"Obuna tekshirish ({chat_id}): {e}")
        except Exception as e:
            logger.error(f"Obuna tekshirish xatosi ({chat_id}): {e}")
    return sotish_ok, hadiya_ok

def get_sub_text(sotish_ok: bool, hadiya_ok: bool) -> str:
    footer = "✅ <b>Barcha kanallarga obuna bo'lgansiz!</b>" if (sotish_ok and hadiya_ok) else "Obuna bo'lgach, <b>«🔄 Tekshirish»</b> tugmasini bosing."
    return Texts.SUB_REQUIRED_TEXT.format(
        sotish_icon="✅" if sotish_ok else "❌",
        hadiya_icon="✅" if hadiya_ok else "❌",
        footer=footer,
    )

def get_subscription_kb(sotish_ok: bool, hadiya_ok: bool) -> InlineKeyboardMarkup:
    kb: list[list[InlineKeyboardButton]] = []
    if sotish_ok and hadiya_ok:
        # Obuna bo'lgan bo'lsa, "Davom etish" emas, avtomatik o'tadi (bu tugma zaxira)
        kb.append([InlineKeyboardButton(text="➡️ Davom etish", callback_data="continue_reg")])
        return InlineKeyboardMarkup(inline_keyboard=kb)
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
# USERBOT
# =====================================================================
async def start_userbot(session_string: str):
    global userbot_client
    try:
        if userbot_client and userbot_client.is_connected():
            await userbot_client.disconnect()
        userbot_client = TelegramClient(
            StringSession(session_string),
            api_id=UserbotConfig.API_ID,
            api_hash=UserbotConfig.API_HASH,
        )
        await userbot_client.start()
        logger.info("✅ Userbot ishga tushdi")

        @userbot_client.on(events.NewMessage(chats=UserbotConfig.TARGET_BOT))
        async def handler(event):
            text = event.message.text or ""
            m = re.search(UserbotConfig.CARD_TRANSFER_REGEX, text)
            if not m:
                return
            amount = int(m.group(1).replace(" ", ""))
            last4 = m.group(2)
            user_id = await db.match_userbot_payment(amount, last4)
            if user_id:
                logger.info(f"✅ To'lov: {amount} UZS → user {user_id}")
                try:
                    await bot.send_message(user_id, Texts.TOPUP_PAID.format(amount=amount))
                except Exception:
                    pass
    except Exception as e:
        logger.error(f"❌ Userbot xatosi: {e}")

# =====================================================================
# FSM
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
    tech_block_user = State()

# =====================================================================
# KLAVIATURALAR
# =====================================================================
def get_main_menu_kb(is_admin: bool = False) -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton(text="📢 Kanalga reklama bermoqchiman", callback_data="menu_reklama")],
        [InlineKeyboardButton(text="🏆 Konkursda ishtirok etish", callback_data="menu_konkurs"), 
         InlineKeyboardButton(text="🥇 Reyting (Top 10)", callback_data="menu_rating")],
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
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📞 Raqamni yuborish", request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True,
    )

def get_back_kb(cb: str = "menu_back_to_main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="↩️ Orqaga", callback_data=cb)]])

def get_ad_type_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Mushukimni sotmoqchiman", callback_data="adtype_sotish")],
        [InlineKeyboardButton(text="🎁 Mushukimni hadiyaga bermoqchiman", callback_data="adtype_hadiya")],
        [InlineKeyboardButton(text="↩️ Asosiy menyuga qaytish", callback_data="menu_back_to_main")],
    ])

def get_cat_count_kb() -> InlineKeyboardMarkup:
    kb = [[InlineKeyboardButton(text=f"{i} ta mushuk", callback_data=f"catcount_{i}")] for i in range(1, 6)]
    kb.append([InlineKeyboardButton(text="↩️ Orqaga", callback_data="menu_reklama")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_media_type_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖼️ Rasm yoki Video yuboraman", callback_data="media_photo")],
        [InlineKeyboardButton(text="↩️ Orqaga", callback_data="menu_reklama")],
    ])

def get_continue_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➡️ Davom etish", callback_data="continue_process")]])

def get_viloyat_kb() -> InlineKeyboardMarkup:
    kb = [[InlineKeyboardButton(text=v, callback_data="viloyat_" + v.lower().replace(" ", "_").replace("'", ""))] for v in DataLists.VILOYATLAR]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_breed_kb(page: int = 0) -> InlineKeyboardMarkup:
    kb: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
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
    kb: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for age in DataLists.AGES:
        # VERGULNI SAQLAB QOLAMIZ (2,5 yosh -> 2,5_yosh)
        cb = age.replace(" ", "_")
        row.append(InlineKeyboardButton(text=age, callback_data=f"age_{cb}"))
        if len(row) == 3:
            kb.append(row)
            row = []
    if row:
        kb.append(row)
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_health_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Sog'lom", callback_data="health_soglom"),
        InlineKeyboardButton(text="Kasal", callback_data="health_kasal"),
    ]])

def get_gender_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="♀️ Qiz bola", callback_data="gender_qiz")],
        [InlineKeyboardButton(text="♂️ O'g'il bola", callback_data="gender_ogil")],
    ])

def get_sterilization_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Nasl olsa bo'ladi", callback_data="sterilization_yes")],
        [InlineKeyboardButton(text="❌ Nasl olsa bo'lmaydi", callback_data="sterilization_no")],
    ])

def get_currency_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇺🇿 So'mda", callback_data="valyuta_som")],
        [InlineKeyboardButton(text="💵 Dollarda", callback_data="valyuta_dollar")],
    ])

def get_preview_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="preview_confirm"),
        InlineKeyboardButton(text="↩️ Bekor qilish", callback_data="menu_reklama"),
    ]])

# =====================================================================
# KANALGA POST
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
    currency_raw = str(ad_data.get("currency") or "so'm")
    currency = html_escape(currency_raw)

    footer = (
        '👤 <a href="https://t.me/zayd_catlover">Admin</a>\n'
        '📢 <a href="https://t.me/Uzbek_cat_bot?start=reklama">Reklama berish</a>\n\n'
        '<a href="https://youtu.be/vdwgSB7_amw">YouTube</a> | '
        '<a href="https://www.instagram.com/p/C-cZkgstVGK/">Instagram</a> | '
        '<a href="https://t.me/uzbek_cats">Telegram</a>'
    )

    if ad_type == "sotish":
        caption = f"#SOTILADI 💰\n\n📝 {breed} | {age} | {gender} | {sterilization} | {health}\n\n📍 Manzil: {address}\n💵 Narxi: {price} {currency}\n📞 Tel: {phone}\n\n{footer}"
        target = CHANNEL_SOTISH_ID
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎁 Hadiya kanal", url=CHANNEL_HADIYA_LINK)],
            [InlineKeyboardButton(text="📢 Reklama berish", url=BOT_LINK)],
        ])
    elif ad_type == "hadiya":
        caption = f"#HADIYA 🎁\n\n📝 {breed} | {age} | {gender} | {sterilization} | {health}\n\n📍 Manzil: {address}\n📞 Tel: {phone}\n\n{footer}"
        target = CHANNEL_HADIYA_ID
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💰 Sotiladi kanal", url=CHANNEL_SOTISH_LINK)],
            [InlineKeyboardButton(text="📢 Reklama berish", url=BOT_LINK)],
        ])
    else:
        raise ValueError(f"Noma'lum ad_type: {ad_type}")

    photos = ad_data.get("photos") or []
    if isinstance(photos, str):
        try:
            photos = json.loads(photos)
        except json.JSONDecodeError:
            photos = []
    if not isinstance(photos, list):
        photos = []

    try:
        if photos:
            sent = await bot.send_photo(chat_id=target, photo=photos[0], caption=caption, reply_markup=kb)
        else:
            sent = await bot.send_message(chat_id=target, text=caption, reply_markup=kb)
        logger.info(f"✅ Kanalga yuborildi: chat={target} msg_id={sent.message_id}")
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

    return await handler(event, data)

dp.message.middleware(check_user_middleware)

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
    await call.answer(Texts.SUB_OK_ALERT)

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
    except TelegramBadRequest:
        pass
        
    missing = []
    if not sotish_ok: missing.append("Sotish kanali")
    if not hadiya_ok: missing.append("Hadiya kanali")
    await call.answer(Texts.SUB_MISSING_ALERT.format(missing=", ".join(missing)), show_alert=True)

@router.callback_query(F.data == "continue_reg")
async def cb_continue_reg(call: CallbackQuery, state: FSMContext):
    sotish_ok, hadiya_ok = await check_subscription(call.from_user.id)
    if not (sotish_ok and hadiya_ok):
        await call.answer(Texts.SUB_MISSING_ALERT.format(missing="Sotish/Hadiya"), show_alert=True)
        return
    await safe_edit_text(call.message, Texts.START_TEXT, reply_markup=None)
    await call.message.answer(Texts.START_TEXT, reply_markup=get_phone_kb())
    await state.set_state(RegStates.waiting_phone)

@router.message(RegStates.checking_subscription)
async def reg_waiting_sub_text(message: Message):
    sotish_ok, hadiya_ok = await check_subscription(message.from_user.id)
    await message.answer("Iltimos, quyidagi tugmalardan foydalaning:", reply_markup=get_subscription_kb(sotish_ok, hadiya_ok))

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
    referral_code = data.get("referral_code")

    try:
        user = await db.create_user(message.from_user.id, username, full_name, phone, referral_code)
    except Exception as e:
        await message.answer(f"❌ {e}")
        return

    await message.answer(Texts.REG_SUCCESS.format(user_number=user["user_number"], score=user["score"], referrals=0), reply_markup=ReplyKeyboardRemove())
    await message.answer(Texts.MAIN_MENU, reply_markup=get_main_menu_kb(message.from_user.id in BotConfig.ADMIN_IDS))
    await state.clear()

# =====================================================================
# ASOSIY MENYU
# =====================================================================
@router.callback_query(F.data == "menu_back_to_main")
async def back_to_main(call: CallbackQuery):
    await safe_edit_text(call.message, Texts.MAIN_MENU, reply_markup=get_main_menu_kb(call.from_user.id in BotConfig.ADMIN_IDS))

@router.callback_query(F.data == "menu_rating")
async def menu_rating(call: CallbackQuery):
    top_users = await db.get_top_10_users()
    text = "🥇 <b>Eng faol foydalanuvchilar (Top 10)</b>\n\n"
    
    if not top_users:
        text += "Hozircha reyting mavjud emas."
    else:
        for i, u in enumerate(top_users, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            name = u.get("full_name") or "Foydalanuvchi"
            text += f"{medal} {name} — <b>{u['score']} ball</b>\n"
            
    await safe_edit_text(call.message, text, reply_markup=get_back_kb())

@router.callback_query(F.data == "menu_reklama")
async def menu_reklama(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await safe_edit_text(call.message, Texts.AD_TYPE_SELECT, reply_markup=get_ad_type_kb())

@router.callback_query(F.data == "menu_about")
async def menu_about(call: CallbackQuery):
    text = (
        "ℹ️ <b>Bot haqida</b>\n\n"
        "Ushbu bot orqali siz mushuklar haqida e'lon berishingiz, ularni sotishingiz yoki hadiya qilishingiz mumkin.\n\n"
        "🎁 Hadiya e'lonlari mutlaqo bepul.\n"
        "💰 Sotish uchun e'lonlar to'lov asosida.\n"
        "💳 To'lovlar balans orqali amalga oshiriladi."
    )
    await safe_edit_text(call.message, text, reply_markup=get_back_kb())

@router.callback_query(F.data == "menu_admin")
async def menu_admin(call: CallbackQuery):
    text = (
        "👤 <b>Admin bilan bog'lanish</b>\n\n"
        "Savollar va shikoyatlar uchun murojaat qiling:\n\n"
        "👨‍💻 Texnik Admin: @It_project_2026\n📞 +998900512621\n\n"
        "👨‍💼 Bosh Admin: @zayd_catlover\n📞 +998934938181"
    )
    await safe_edit_text(call.message, text, reply_markup=get_back_kb())

@router.callback_query(F.data == "menu_my_orders")
async def menu_my_orders(call: CallbackQuery):
    ads = await db.get_user_ads(call.from_user.id)
    if not ads:
        text = Texts.NO_ADS
    else:
        st_map = {"pending": "⏳ Kutilmoqda", "approved": "✅ Tasdiqlangan", "rejected": "❌ Rad etilgan", "sold": "💰 Sotilgan", "expired": "⏰ Muddati o'tgan"}
        text = Texts.MY_ADS_HEADER
        for ad in ads[:10]:
            st = st_map.get(ad["status"], ad["status"])
            breed = html_escape(str(ad.get("breed") or "—"))
            text += f"🐱 <b>{breed}</b> | {st}\n📅 {ad['created_at'].strftime('%d.%m.%Y')}\n\n"
    await safe_edit_text(call.message, text, reply_markup=get_back_kb())

@router.callback_query(F.data == "menu_konkurs")
async def menu_konkurs(call: CallbackQuery):
    user = await db.get_user(call.from_user.id)
    if not user:
        await call.answer("Avval ro'yxatdan o'ting", show_alert=True)
        return
    ref_link = f"https://t.me/{BotConfig.BOT_USERNAME.replace('@', '')}?start=REF{user['id']}"
    text = Texts.KONKURS_TEXT.format(score=user["score"], ref_link=ref_link)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Ulashish", url=f"https://t.me/share/url?url={ref_link}")],
        [InlineKeyboardButton(text="↩️ Orqaga", callback_data="menu_back_to_main")],
    ])
    await safe_edit_text(call.message, text, reply_markup=kb)

# =====================================================================
# REKLAMA JARAYONI
# =====================================================================
@router.callback_query(F.data.startswith("adtype_"))
async def choose_ad_type(call: CallbackQuery, state: FSMContext):
    ad_type = call.data.replace("adtype_", "")
    await state.update_data(ad_type=ad_type)
    if ad_type == "sotish":
        await safe_edit_text(call.message, Texts.CAT_COUNT_ASK, reply_markup=get_cat_count_kb())
        await state.set_state(AdStates.choosing_cat_count)
    else:
        await safe_edit_text(call.message, Texts.MEDIA_ASK, reply_markup=get_media_type_kb())
        await state.set_state(AdStates.choosing_media_type)

@router.callback_query(AdStates.choosing_cat_count, F.data.startswith("catcount_"))
async def process_cat_count(call: CallbackQuery, state: FSMContext):
    count = int(call.data.split("_")[1])
    await state.update_data(cat_count=count)
    user = await db.get_user(call.from_user.id)
    price = Prices.get_bot_price(count)
    await state.update_data(bot_price=price)
    if user["balance"] < price:
        text = Texts.ERROR_INSUFFICIENT_BALANCE.format(price=price, balance=user["balance"])
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Hisobni to'ldirish", web_app=types.WebAppInfo(url=f"{BotConfig.WEB_APP_URL}?page=topup"))],
            [InlineKeyboardButton(text="↩️ Orqaga", callback_data="menu_reklama")],
        ])
        await safe_edit_text(call.message, text, reply_markup=kb)
        return
    await safe_edit_text(call.message, Texts.MEDIA_ASK, reply_markup=get_media_type_kb())
    await state.set_state(AdStates.choosing_media_type)

@router.callback_query(F.data == "media_photo")
async def choose_media(call: CallbackQuery, state: FSMContext):
    await state.update_data(photos=[])
    await safe_edit_text(call.message, Texts.PHOTOS_ASK, reply_markup=None)
    await state.set_state(AdStates.waiting_media)

# RASM YOKI VIDEO QABUL QILISH (1 daqiqagacha)
@router.message(AdStates.waiting_media, F.photo | F.video)
async def receive_media(message: Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get("photos", [])
    
    if len(photos) >= Settings.MAX_PHOTOS:
        await message.answer(Texts.PHOTOS_LIMIT, reply_markup=get_continue_kb())
        return
    
    if message.video:
        if message.video.duration > 60:
            await message.answer("❌ Video 1 daqiqadan oshmasligi kerak. Iltimos, qisqaroq video yuboring yoki rasm yuboring.")
            return
        photos.append(message.video.file_id)
        await state.update_data(photos=photos)
        await message.answer(f"✅ <b>Video qabul qilindi (1 ta video bilan cheklangan).</b>", reply_markup=get_continue_kb())
    elif message.photo:
        photos.append(message.photo[-1].file_id)
        await state.update_data(photos=photos)
        await message.answer(f"✅ <b>{len(photos)}-rasm qabul qilindi.</b>", reply_markup=get_continue_kb())

@router.callback_query(AdStates.waiting_media, F.data == "continue_process")
async def process_continue_media(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("photos"):
        await call.answer(Texts.PHOTOS_MIN, show_alert=True)
        return
    await safe_edit_text(call.message, Texts.BREED_ASK, reply_markup=get_breed_kb(0))
    await state.set_state(AdStates.choosing_breed)

@router.callback_query(AdStates.choosing_breed, F.data.startswith("breed_page_"))
async def breed_page(call: CallbackQuery):
    page = int(call.data.split("_")[2])
    await call.message.edit_reply_markup(reply_markup=get_breed_kb(page))

@router.callback_query(AdStates.choosing_breed, F.data.startswith("breed_") & ~F.data.startswith("breed_page_") & ~F.data.startswith("breed_custom"))
async def process_breed(call: CallbackQuery, state: FSMContext):
    parts = call.data.split("_")
    breed = DataLists.BREEDS[int(parts[1])][int(parts[2])]
    await state.update_data(breed=breed)
    await safe_edit_text(call.message, Texts.AGE_ASK, reply_markup=get_age_kb())
    await state.set_state(AdStates.choosing_age)

@router.callback_query(AdStates.choosing_breed, F.data == "breed_custom")
async def custom_breed(call: CallbackQuery, state: FSMContext):
    await safe_edit_text(call.message, Texts.BREED_CUSTOM_ASK, reply_markup=None)
    await state.set_state(AdStates.custom_breed)

@router.message(AdStates.custom_breed)
async def process_custom_breed(message: Message, state: FSMContext):
    await state.update_data(breed=(message.text or "").strip())
    await message.answer(Texts.AGE_ASK, reply_markup=get_age_kb())
    await state.set_state(AdStates.choosing_age)

# YOSHNI TO'G'RI QABUL QILISH (2,5 yosh -> 2,5 yosh)
@router.callback_query(AdStates.choosing_age, F.data.startswith("age_"))
async def process_age(call: CallbackQuery, state: FSMContext):
    age_raw = call.data.replace("age_", "").replace("_", " ") # "2,5_yosh" -> "2,5 yosh"
    await state.update_data(age=age_raw)
    await safe_edit_text(call.message, Texts.HEALTH_ASK, reply_markup=get_health_kb())
    await state.set_state(AdStates.choosing_health)

@router.callback_query(AdStates.choosing_health, F.data.startswith("health_"))
async def process_health(call: CallbackQuery, state: FSMContext):
    await state.update_data(health="Sog'lom" if call.data == "health_soglom" else "Kasal")
    await safe_edit_text(call.message, Texts.GENDER_ASK, reply_markup=get_gender_kb())
    await state.set_state(AdStates.choosing_gender)

@router.callback_query(AdStates.choosing_gender, F.data.startswith("gender_"))
async def process_gender(call: CallbackQuery, state: FSMContext):
    await state.update_data(gender="Qiz bola" if call.data == "gender_qiz" else "O'g'il bola")
    await safe_edit_text(call.message, Texts.STERILIZATION_ASK, reply_markup=get_sterilization_kb())
    await state.set_state(AdStates.choosing_sterilization)

@router.callback_query(AdStates.choosing_sterilization, F.data.startswith("sterilization_"))
async def process_sterilization(call: CallbackQuery, state: FSMContext):
    await state.update_data(sterilization="Nasl olish mumkin" if call.data == "sterilization_yes" else "Nasl olish mumkin emas")
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
        await message.answer(Texts.CURRENCY_ASK, reply_markup=get_currency_kb())
        await state.set_state(AdStates.choosing_currency)

@router.callback_query(AdStates.choosing_currency, F.data.startswith("valyuta_"))
async def process_currency(call: CallbackQuery, state: FSMContext):
    await state.update_data(currency="so'm" if call.data == "valyuta_som" else "$")
    await safe_edit_text(call.message, Texts.PRICE_ASK, reply_markup=None)
    await state.set_state(AdStates.waiting_price)

@router.message(AdStates.waiting_price)
async def process_price(message: Message, state: FSMContext):
    if not (message.text or "").isdigit():
        await message.answer(Texts.PRICE_INVALID)
        return
    await state.update_data(price=message.text)
    await send_ad_preview(message, state)

async def send_ad_preview(message: Message, state: FSMContext):
    data = await state.get_data()
    price_str = html_escape(str(data.get("price") or "0"))
    currency_str = html_escape(str(data.get("currency") or "so'm"))
    address_str = html_escape(str(data.get("address") or "—"))
    phone_str = html_escape(str(data.get("phone") or "—"))
    breed_str = html_escape(str(data.get("breed") or "—"))
    age_str = html_escape(str(data.get("age") or "—"))
    gender_str = html_escape(str(data.get("gender") or "—"))
    health_str = html_escape(str(data.get("health") or "—"))
    sterilization_str = html_escape(str(data.get("sterilization") or "—"))

    caption = Texts.PREVIEW_HEADER
    caption += f"📍 Manzil: {address_str}\n📞 Tel: {phone_str}\n"
    if data.get("ad_type") != "hadiya":
        caption += f"💰 Narx: {price_str} {currency_str}\n"
    caption += f"🐱 Zot: {breed_str}\n🎂 Yosh: {age_str}\n👤 Jins: {gender_str}\n❤️ Sog'liq: {health_str}\n🧬 Nasl: {sterilization_str}\n\n"
    
    photos = data.get("photos", [])
    if photos:
        await message.answer_photo(photo=photos[0], caption=caption, reply_markup=get_preview_kb())
    else:
        await message.answer(caption, reply_markup=get_preview_kb())
    await state.set_state(AdStates.preview)

@router.callback_query(AdStates.preview, F.data == "preview_confirm")
async def confirm_ad(call: CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    data = await state.get_data()
    user = await db.get_user(user_id)
    price = data.get("bot_price", 0)
    
    if price > 0:
        try:
            await db.update_user_balance(user_id, price, operation="subtract")
        except ValueError:
            await safe_edit_text(call.message, Texts.ERROR_INSUFFICIENT_BALANCE.format(price=price, balance=user["balance"]), reply_markup=None)
            return

    new_ad = await db.create_ad(
        user_id=user_id, ad_type=data.get("ad_type"), tariff="bot",
        photos=data.get("photos", []), breed=data.get("breed"), age=data.get("age"),
        gender=data.get("gender"), health=data.get("health"),
        sterilization=data.get("sterilization"), address=data.get("address"),
        phone=data.get("phone"), price=data.get("price", "0"),
        currency=data.get("currency", "so'm"), ad_number=(user.get("ad_count") or 0) + 1,
        cat_count=data.get("cat_count", 1), price_paid=price,
    )

    await safe_delete(call.message)
    try:
        await bot.send_message(user_id, Texts.AD_ACCEPTED)
    except Exception:
        pass

    ad_type_upper = str(data.get("ad_type")).upper()
    breed_safe = html_escape(str(data.get("breed") or "—"))
    username_safe = html_escape(user['username']) if user['username'] else '—'
    
    admin_caption = f"🆕 <b>YANGI REKLAMA!</b>\n\n👤 Foydalanuvchi: #{user['user_number']} ({username_safe})\n📋 Turi: {ad_type_upper}\n🐱 Zot: {breed_safe}"
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"admin_approve_ad_{new_ad['id']}"),
        InlineKeyboardButton(text="❌ Rad etish", callback_data=f"admin_decline_ad_{new_ad['id']}"),
    ]])

    photos = data.get("photos", [])
    try:
        if photos:
            await bot.send_photo(BotConfig.TECH_ADMIN_ID, photo=photos[0], caption=admin_caption, reply_markup=kb)
        else:
            await bot.send_message(BotConfig.TECH_ADMIN_ID, admin_caption, reply_markup=kb)
    except Exception as e:
        logger.error(f"Admin xabar yuborishda xato: {e}")

    await state.clear()

# =====================================================================
# ADMIN PANEL
# =====================================================================
@router.callback_query(F.data == "admin_panel")
async def admin_panel(call: CallbackQuery):
    if call.from_user.id not in BotConfig.ADMIN_IDS:
        await call.answer(Texts.NOT_ADMIN, show_alert=True)
        return
    stats = await db.get_statistics()
    text = (
        f"👨‍💼 <b>Admin Paneli</b>\n\n"
        f"👥 Foydalanuvchilar: {stats['total_users']}\n"
        f"📢 Jami reklamalar: {stats['total_ads']}\n\n"
        f"💰 <b>Bugungi tushum:</b> {stats['today_income']:,} so'm\n"
        f"💵 <b>Oylik tushum:</b> {stats['month_income']:,} so'm"
    )
    rows = [
        [InlineKeyboardButton(text="⚙️ Bot holati", callback_data="admin_toggle_bot")],
        [InlineKeyboardButton(text="💳 Hisob qo'shish", callback_data="admin_add_balance")],
        [InlineKeyboardButton(text="➕ Ball qo'shish (telefon)", callback_data="admin_add_score")],
    ]
    if call.from_user.id == BotConfig.TECH_ADMIN_ID:
        rows.append([InlineKeyboardButton(text="👨‍💻 Texnik Admin Paneli", callback_data="tech_admin_panel")])
    rows.append([InlineKeyboardButton(text="↩️ Orqaga", callback_data="menu_back_to_main")])
    await safe_edit_text(call.message, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

@router.callback_query(F.data == "admin_toggle_bot")
async def admin_toggle_bot(call: CallbackQuery):
    if call.from_user.id not in BotConfig.ADMIN_IDS: return
    current = await db.get_setting("bot_enabled", "1")
    new_val = "0" if current == "1" else "1"
    await db.set_setting("bot_enabled", new_val)
    await call.answer(Texts.BOT_ENABLED_ALERT if new_val == "1" else Texts.BOT_DISABLED_ALERT, show_alert=True)

@router.callback_query(F.data == "admin_add_balance")
async def admin_add_balance_start(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in BotConfig.ADMIN_IDS: return
    await safe_edit_text(call.message, "💳 <b>Hisob qo'shish</b>\n\nFoydalanuvchi Telegram ID sini kiriting:\n(Masalan: <code>673018191</code>)\n\n/cancel — bekor qilish", reply_markup=None)
    await state.set_state(AdminStates.add_balance_user_id)

@router.message(AdminStates.add_balance_user_id)
async def admin_add_balance_user(message: Message, state: FSMContext):
    if (message.text or "") == "/cancel":
        await state.clear(); await message.answer("Bekor qilindi."); return
    if not (message.text or "").isdigit():
        await message.answer("❌ Faqat raqam kiriting:"); return
    uid = int(message.text)
    user = await db.get_user(uid)
    if not user:
        await message.answer("❌ Bunday ID li foydalanuvchi topilmadi."); return
    await state.update_data(target_user_id=uid)
    username_safe = html_escape(user['username'] or '—')
    await message.answer(f"👤 #{user['user_number']} ({username_safe})\n\nSumma kiriting (ayirish uchun <code>-50000</code>):")
    await state.set_state(AdminStates.add_balance_amount)

@router.message(AdminStates.add_balance_amount)
async def admin_add_balance_amount(message: Message, state: FSMContext):
    if (message.text or "") == "/cancel":
        await state.clear(); await message.answer("Bekor qilindi."); return
    try:
        amount = int(message.text)
    except ValueError:
        await message.answer("❌ Noto'g'ri summa."); return
    data = await state.get_data()
    uid = data.get("target_user_id")
    op = "add" if amount > 0 else "subtract"
    try:
        new_bal = await db.update_user_balance(uid, abs(amount), op)
        msg = f"✅ Hisobingizga {amount:,} so'm qo'shildi." if amount > 0 else f"⚠️ Hisobingizdan {abs(amount):,} so'm yechildi."
        try: await bot.send_message(uid, f"{msg}\n\n💰 Joriy balans: {new_bal:,} so'm")
        except Exception: pass
        await message.answer(f"✅ Bajarildi!\nYangi balans: {new_bal:,} so'm")
    except Exception as e:
        await message.answer(Texts.ERROR_UNKNOWN.format(err=e))
    await state.clear()

@router.callback_query(F.data == "admin_add_score")
async def admin_add_score(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in BotConfig.ADMIN_IDS: return
    await safe_edit_text(call.message, "📊 <b>Ball qo'shish</b>\n\nFormat: <code>+998901234567 - 17</code>\n\n/cancel — bekor qilish", reply_markup=None)
    await state.set_state(AdminStates.add_score_batch)

@router.message(AdminStates.add_score_batch)
async def process_add_score(message: Message, state: FSMContext):
    if (message.text or "") == "/cancel":
        await state.clear(); await message.answer("Bekor qilindi."); return
    m = re.search(r"(\+?\d{9,15})\s*[-–—]?\s*(-?\d+)", message.text or "")
    if not m:
        await message.answer("❌ Format xato. Namuna: <code>+998901234567 - 17</code>"); return
    phone, score = m.group(1), int(m.group(2))
    ok = await db.add_score_by_phone_batch(phone, score)
    if ok:
        await message.answer(f"✅ <b>{phone}</b> ga <b>{score:+d}</b> ball qo'shildi!")
    else:
        await message.answer(f"❌ <b>{phone}</b> topilmadi.")
    await state.clear()

# =====================================================================
# TEXNIK ADMIN
# =====================================================================
@router.callback_query(F.data == "tech_admin_panel")
async def tech_admin_panel(call: CallbackQuery):
    if call.from_user.id != BotConfig.TECH_ADMIN_ID:
        await call.answer(Texts.NOT_TECH_ADMIN, show_alert=True); return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Foydalanuvchi bloklash", callback_data="tech_block_user")],
        [InlineKeyboardButton(text="↩️ Orqaga", callback_data="admin_panel")],
    ])
    await safe_edit_text(call.message, Texts.TECH_ADMIN_PANEL_WELCOME, reply_markup=kb)

@router.callback_query(F.data == "tech_block_user")
async def tech_block_user(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != BotConfig.TECH_ADMIN_ID: return
    await safe_edit_text(call.message, "Bloklash uchun foydalanuvchi <b>tartib raqami</b>ni kiriting (masalan: 1):", reply_markup=None)
    await state.set_state(AdminStates.tech_block_user)

@router.message(AdminStates.tech_block_user)
async def process_tech_block_user(message: Message, state: FSMContext):
    try:
        n = int(message.text)
        u = await db.get_user_by_number(n)
        if u:
            await db.block_user(u["id"])
            await message.answer(f"✅ #{n} raqamli foydalanuvchi bloklandi.")
        else:
            await message.answer("❌ Topilmadi.")
    except (ValueError, TypeError):
        await message.answer("❌ Raqam kiriting.")
    await state.clear()

@router.callback_query(F.data.startswith("admin_approve_ad_"))
async def tech_admin_approve(call: CallbackQuery):
    if call.from_user.id not in BotConfig.ADMIN_IDS:
        await call.answer(Texts.ERROR_NO_PERMISSION, show_alert=True); return
    ad_id = int(call.data.split("_")[3])

    async with db.pool.acquire() as conn:
        ad_row = await conn.fetchrow("SELECT * FROM ads WHERE id = $1", ad_id)
    if not ad_row:
        await call.answer(Texts.ERROR_AD_NOT_FOUND, show_alert=True); return

    ad_data = dict(ad_row)
    try:
        sent = await post_to_channel(ad_data)
        await db.update_ad_status(ad_id, "approved", channel_message_id=getattr(sent, "message_id", None))
        try:
            await bot.send_message(ad_data["user_id"], "✅ <b>Sizning e'loningiz tasdiqlandi va kanalga joylandi!</b>")
        except Exception: pass
        try: await call.message.edit_reply_markup(reply_markup=None)
        except TelegramBadRequest: pass
        await call.answer(Texts.AD_APPROVED_ALERT, show_alert=False)
        try: await call.message.reply(f"✅ Ad #{ad_id} kanalga yuborildi.")
        except Exception: pass
    except Exception as e:
        err = str(e)[:200]
        await call.answer(f"❌ Xato: {err}", show_alert=True)
        try:
            await bot.send_message(
                BotConfig.TECH_ADMIN_ID,
                f"❌ <b>Kanalga yuborishda xato!</b>\n\nAd ID: <code>{ad_id}</code>\nKanal: <code>{ad_data['ad_type']}</code>\nXato: <code>{html_escape(err)}</code>\n\n<b>Eslatma:</b> Botni kanalga admin qilib qo'shganingizni tekshiring!"
            )
        except Exception: pass

@router.callback_query(F.data.startswith("admin_decline_ad_"))
async def tech_admin_decline(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in BotConfig.ADMIN_IDS: return
    ad_id = int(call.data.split("_")[3])
    await state.update_data(decline_ad_id=ad_id)
    await call.message.reply(Texts.AD_REJECT_REASON_ASK)
    await state.set_state(AdminStates.decline_reason)

@router.message(AdminStates.decline_reason)
async def process_decline_reason(message: Message, state: FSMContext):
    data = await state.get_data()
    ad_id = data.get("decline_ad_id")
    reason = message.text or "Sabab ko'rsatilmadi"

    async with db.pool.acquire() as conn:
        ad_row = await conn.fetchrow("SELECT user_id, price_paid FROM ads WHERE id = $1", ad_id)

    await db.update_ad_status(ad_id, "rejected", reason=reason)

    if ad_row:
        if ad_row["price_paid"] and ad_row["price_paid"] > 0:
            try: await db.update_user_balance(ad_row["user_id"], ad_row["price_paid"], operation="add")
            except Exception as e: logger.error(f"Refund xatosi: {e}")
        try:
            await bot.send_message(ad_row["user_id"], f"❌ <b>E'loningiz rad etildi.</b>\n\nSabab: {html_escape(reason)}\n\nBalansingizga pul qaytarildi.")
        except Exception: pass

    await message.answer(Texts.AD_REJECTED)
    await state.clear()

# =====================================================================
# STARTUP / SHUTDOWN
# =====================================================================
@dp.startup()
async def on_startup():
    logger.info("🚀 Startup: DB ga ulanmoqda...")
    await db.connect()
    try: await bot.set_my_commands([BotCommand(command="start", description="Botni ishga tushirish")])
    except Exception as e: logger.warning(f"Komandalar o'rnatilmadi: {e}")

    me = await bot.get_me()
    logger.info(f"🤖 Bot: @{me.username} (id={me.id})")

    for ch_id, name in [(CHANNEL_SOTISH_ID, "Sotish"), (CHANNEL_HADIYA_ID, "Hadiya")]:
        try:
            chat = await bot.get_chat(ch_id)
            member = await bot.get_chat_member(ch_id, me.id)
            status = getattr(member.status, "value", member.status)
            if status in ("administrator", "creator"):
                logger.info(f"✅ Bot {name} kanalda admin: {chat.title}")
            else:
                logger.critical(f"⚠️ BOT {name} KANALDA ADMIN EMAS! chat_id={ch_id} status={status}")
        except Exception as e:
            logger.critical(f"❌ {name} kanal ({ch_id}) xatolik: {e}")

    try:
        async with db.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT session_string FROM userbot_sessions WHERE is_active = TRUE LIMIT 1")
        if row and row["session_string"]:
            await start_userbot(row["session_string"])
    except Exception as e:
        logger.warning(f"Userbot yuklashda xato: {e}")

@dp.shutdown()
async def on_shutdown():
    logger.info("🔌 Bot to'xtatilmoqda...")
    if userbot_client and userbot_client.is_connected():
        try: await userbot_client.disconnect()
        except Exception: pass
    await db.disconnect()

async def main():
    logger.info("🚀 Bot polling boshlandi")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⏹ Bot to'xtatildi (Ctrl+C)")
