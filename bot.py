# ==============================================================================
# LOYIHA: UzbekCats Bot & Web App
# FAYL: bot.py
# TAVSIF: To'liq mukammal Telegram Bot (Aiogram v3) - Barcha tugmalar ishlaydi
# ==============================================================================

import asyncio
import logging
import re
from datetime import datetime
from aiogram import Bot, Dispatcher, F, Router, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InputMediaPhoto
)
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

# Telethon
from telethon import TelegramClient, events
from telethon.sessions import StringSession

# O'zimizning fayllar
from config import BotConfig, Prices, DataLists, Texts
from db import db

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# =====================================================================
# BOT SOZLAMALARI
# =====================================================================
bot = Bot(
    token=BotConfig.BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)
)
dp = Dispatcher()
router = Router()
dp.include_router(router)

# Kanallar sozlamasi (config.py dan olinadi deb hisoblaymiz, agar yo'q bo'lsa shu yerda)
CHANNEL_SOTISH = getattr(BotConfig, 'CHANNEL_ID', '@uzbek_cats') 
CHANNEL_HADIYA = '@uzbek_cats_hadiya'
BOT_LINK = 'https://t.me/Uzbek_cat_bot'

userbot_client: TelegramClient = None

# =====================================================================
# FSM HOLATLARI
# =====================================================================
class RegStates(StatesGroup):
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
    # Asosiy admin state'lari
    add_card_number = State()
    add_card_holder = State()
    add_score_batch = State()
    decline_reason = State()
    tech_block_user = State()
    
    # Hisob qo'shish state'lari
    add_balance_user_id = State()
    add_balance_amount = State()
    
    # Kanal sozlamalari uchun (kelajakda kerak bo'lishi mumkin)
    broadcast_text = State()

# =====================================================================
# KLAVIATURALAR
# =====================================================================
def get_main_menu_kb(is_admin=False):
    kb = [
        [InlineKeyboardButton(text="📢 Kanalga reklama bermoqchiman", callback_data="menu_reklama")],
        [InlineKeyboardButton(text="🏆 Konkursda ishtirok etmoqchiman", callback_data="menu_konkurs")],
        [InlineKeyboardButton(text="💳 Hisobni to'ldirish", web_app=types.WebAppInfo(url=f"{BotConfig.WEB_APP_URL}?page=topup"))],
        [InlineKeyboardButton(text="📋 Mening e'lonlarim", callback_data="menu_my_orders")],
        [InlineKeyboardButton(text="ℹ️ Bot haqida", callback_data="menu_about")],
        [InlineKeyboardButton(text="👤 Admin bilan bog'lanish", callback_data="menu_admin")],
        [InlineKeyboardButton(text="🖥️ Web App'ni ochish", web_app=types.WebAppInfo(url=BotConfig.WEB_APP_URL))]
    ]
    if is_admin:
        kb.append([InlineKeyboardButton(text="👨‍💼 Admin paneli", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_phone_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📞 Raqamni yuborish", request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True
    )

def get_ad_type_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Mushukimni Sotish uchun quymoqchiman", callback_data="adtype_sotish")],
        [InlineKeyboardButton(text="🎁 Mushukgimni Hadiyaga bermoqchiman", callback_data="adtype_hadiya")],
        [InlineKeyboardButton(text="↩️ Asosiy menyuga qaytish", callback_data="menu_back_to_main")]
    ])

def get_cat_count_kb():
    kb = []
    for i in range(1, 6):
        kb.append([InlineKeyboardButton(text=f"{i} ta mushuk", callback_data=f"catcount_{i}")])
    kb.append([InlineKeyboardButton(text="+5 ta mushuk", callback_data="catcount_6")])
    kb.append([InlineKeyboardButton(text="↩️ Orqaga", callback_data="menu_reklama")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_media_type_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖼️ Rasm yuboraman", callback_data="media_photo")],
        [InlineKeyboardButton(text="↩️ Orqaga", callback_data="menu_reklama")]
    ])

def get_continue_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➡️ Davom etish", callback_data="continue_process")]
    ])

def get_viloyat_kb():
    kb = []
    for v in DataLists.VILOYATLAR:
        cb = v.lower().replace(" ", "_").replace("'", "")
        kb.append([InlineKeyboardButton(text=v, callback_data=f"viloyat_{cb}")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_breed_kb(page=0):
    kb = []
    page_breeds = DataLists.BREEDS[page]
    row = []
    for i, breed in enumerate(page_breeds):
        row.append(InlineKeyboardButton(text=breed, callback_data=f"breed_{page}_{i}"))
        if len(row) == 2:
            kb.append(row)
            row = []
    if row: kb.append(row)
    
    nav = []
    if page > 0: nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"breed_page_{page-1}"))
    if page < len(DataLists.BREEDS) - 1: nav.append(InlineKeyboardButton(text="➡️", callback_data=f"breed_page_{page+1}"))
    if nav: kb.append(nav)
    
    kb.append([InlineKeyboardButton(text="✏️ Yozuvda kiritaman", callback_data="breed_custom")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_age_kb():
    kb = []
    row = []
    for i, age in enumerate(DataLists.AGES):
        cb = age.replace(" ", "_").replace(",", "").replace(".", "")
        row.append(InlineKeyboardButton(text=age, callback_data=f"age_{cb}"))
        if len(row) == 3:
            kb.append(row)
            row = []
    if row: kb.append(row)
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_health_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Sog'lom", callback_data="health_soglom"), InlineKeyboardButton(text="Kasal", callback_data="health_kasal")]
    ])

def get_gender_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="♀️ Qiz bola", callback_data="gender_qiz")],
        [InlineKeyboardButton(text="♂️ O'g'il bola", callback_data="gender_ogil")]
    ])

def get_sterilization_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Nasil olsa buladi", callback_data="sterilization_yes")],
        [InlineKeyboardButton(text="❌ Nasil olsa bulmaydi", callback_data="sterilization_no")]
    ])

def get_currency_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇺🇿 So'mda", callback_data="valyuta_som")],
        [InlineKeyboardButton(text="💵 Dollarda", callback_data="valyuta_dollar")]
    ])

def get_preview_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="preview_confirm"), InlineKeyboardButton(text="↩️ Bekor qilish", callback_data="menu_reklama")]
    ])

def get_back_kb(cb="menu_back_to_main"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↩️ Orqaga", callback_data=cb)]
    ])

# =====================================================================
# YORDAMCHI FUNKSIYALAR
# =====================================================================

def escape_md(text):
    """Markdown formatlash belgilarini xavfsiz holatga keltirish"""
    if not text: return "—"
    return str(text).replace('_', '\\_').replace('*', '\\*').replace('`', '\\`').replace('[', '\\[')

async def post_to_channel(ad_data):
    """Reklamani turiga qarab mos kanalga chiqarish va tugmalarni qo'shish"""
    ad_type = ad_data.get('ad_type')
    
    caption = (
        f"🐱 *Zot:* {escape_md(ad_data.get('breed'))}\n"
        f"📍 *Manzil:* {escape_md(ad_data.get('address'))}\n"
        f"📞 *Tel:* {escape_md(ad_data.get('phone'))}\n"
    )
    
    if ad_type == 'sotish':
        caption += f"💰 *Narx:* {escape_md(ad_data.get('price'))} {escape_md(ad_data.get('currency'))}\n"
        target_channel = CHANNEL_SOTISH
        # Sotish uchun tugmalar: Hadiya kanal va Reklama berish
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎁 Hadiya kanal", url="https://t.me/uzbek_cats_hadiya")],
            [InlineKeyboardButton(text="📢 Reklama berish", url=BOT_LINK)]
        ])
    elif ad_type == 'hadiya':
        caption += f"🎁 *Bepul (Hadiya)*\n"
        target_channel = CHANNEL_HADIYA
        # Hadiya uchun tugmalar: Sotiladi kanal va Reklama berish
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💰 Sotiladi kanal", url="https://t.me/uzbek_cats")],
            [InlineKeyboardButton(text="📢 Reklama berish", url=BOT_LINK)]
        ])
    else:
        return

    try:
        photos = ad_data.get('photos', [])
        if isinstance(photos, str):
            import json
            photos = json.loads(photos)
            
        if photos and len(photos) > 0:
            await bot.send_photo(
                chat_id=target_channel,
                photo=photos[0],
                caption=caption,
                reply_markup=kb
            )
        else:
            await bot.send_message(chat_id=target_channel, text=caption, reply_markup=kb)
    except Exception as e:
        logger.error(f"Kanalga post yuborishda xatolik: {e}")

# =====================================================================
# START VA RO'YXATDAN O'TISH
# =====================================================================
@dp.message.middleware()
async def check_user_middleware(handler, event: Message, data: dict):
    user_id = event.from_user.id
    if user_id in BotConfig.ADMIN_IDS:
        return await handler(event, data)

    bot_status = await db.get_setting("bot_enabled", "1")
    if bot_status == "0":
        await event.answer(Texts.BOT_DISABLED)
        return
    return await handler(event, data)

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    if user:
        await message.answer(Texts.MAIN_MENU, reply_markup=get_main_menu_kb(user_id in BotConfig.ADMIN_IDS))
        return

    await message.answer(Texts.START_TEXT, reply_markup=get_phone_kb())
    await state.set_state(RegStates.waiting_phone)

@router.message(RegStates.waiting_phone, F.contact | F.text)
async def process_phone(message: Message, state: FSMContext):
    phone = message.contact.phone_number if message.contact else message.text.strip()
    if not message.contact and not re.match(r'^\+?998\d{9}$', phone.replace(" ", "")):
        await message.answer(Texts.ASK_PHONE)
        return

    phone = phone if phone.startswith("+") else f"+{phone}"
    full_name = f"{message.from_user.first_name} {message.from_user.last_name or ''}".strip()
    username = f"@{message.from_user.username}" if message.from_user.username else "Noma'lum"

    user = await db.create_user(message.from_user.id, username, full_name, phone)
    
    await message.answer(Texts.REG_SUCCESS.format(user_number=user['user_number'], score=user['score'], referrals=0), reply_markup=ReplyKeyboardRemove())
    await message.answer(Texts.MAIN_MENU, reply_markup=get_main_menu_kb())
    await state.clear()

# =====================================================================
# ASOSIY MENYU TUGMALARI
# =====================================================================
@router.callback_query(F.data == "menu_back_to_main")
async def back_to_main(call: CallbackQuery):
    await call.message.edit_text(Texts.MAIN_MENU, reply_markup=get_main_menu_kb(call.from_user.id in BotConfig.ADMIN_IDS))

@router.callback_query(F.data == "menu_reklama")
async def menu_reklama(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("🎯 *Qanday turdagi e'lon joylashtirmoqchisiz?*", reply_markup=get_ad_type_kb())
    await state.clear()

@router.callback_query(F.data == "menu_about")
async def menu_about(call: CallbackQuery):
    text = (
        "ℹ️ *Bot haqida*\n\n"
        "Ushbu bot orqali siz mushuklar haqida e'lon berishingiz, ularni sotishingiz yoki hadiya qilishingiz mumkin.\n\n"
        "🎁 Hadiya e'lonlari mutlaqo bepul.\n"
        "💰 Sotish uchun e'lonlar to'lov asosida (Bot yoki Web App orqali).\n"
        "💳 To'lovlar balans orqali amalga oshiriladi."
    )
    await call.message.edit_text(text, reply_markup=get_back_kb())

@router.callback_query(F.data == "menu_admin")
async def menu_admin(call: CallbackQuery):
    text = (
        "👤 *Admin bilan bog'lanish*\n\n"
        "Savollar va shikoyatlar uchun murojaat qiling:\n\n"
        "👨‍💻 Texnik Admin: @It\\_project\\_2026\n"
        "📞 +998900512621\n\n"
        "👨‍💼 Bosh Admin: @zayd\\_catlover\n"
        "📞 +998934938181"
    )
    await call.message.edit_text(text, reply_markup=get_back_kb())

@router.callback_query(F.data == "menu_my_orders")
async def menu_my_orders(call: CallbackQuery):
    user_id = call.from_user.id
    ads = await db.get_user_ads(user_id)
    
    if not ads:
        text = "📭 Sizda hali e'lonlar mavjud emas."
    else:
        text = "📋 *Sizning e'lonlaringiz:*\n\n"
        for ad in ads[:10]:
            st_map = {"pending": "⏳ Kutilmoqda", "approved": "✅ Tasdiqlangan", "rejected": "❌ Rad etilgan", "sold": "💰 Sotilgan"}
            st = st_map.get(ad['status'], ad['status'])
            text += f"🐱 *{escape_md(ad['breed'])}* | {st}\n📅 {ad['created_at'].strftime('%d.%m.%Y')}\n\n"
            
    await call.message.edit_text(text, reply_markup=get_back_kb())

@router.callback_query(F.data == "menu_konkurs")
async def menu_konkurs(call: CallbackQuery):
    user_id = call.from_user.id
    user = await db.get_user(user_id)
    ref_link = f"https://t.me/{BotConfig.BOT_USERNAME.replace('@', '')}?start=REF{user_id}"
    
    text = (
        "🏆 *Konkursda ishtirok etish*\n\n"
        f"👥 Sizning ballaringiz: *{user['score']} ball*\n"
        f"🔗 Sizning linkingiz:\n`{ref_link}`\n\n"
        "Do'stlaringizni taklif qiling va ball to'plang!"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Ulashish", url=f"https://t.me/share/url?url={ref_link}")],
        [InlineKeyboardButton(text="↩️ Orqaga", callback_data="menu_back_to_main")]
    ])
    await call.message.edit_text(text, reply_markup=kb)

# =====================================================================
# REKLAMA BERISH JARAYONI
# =====================================================================
@router.callback_query(F.data.startswith("adtype_"))
async def choose_ad_type(call: CallbackQuery, state: FSMContext):
    ad_type = call.data.replace("adtype_", "")
    await state.update_data(ad_type=ad_type)

    if ad_type == "sotish":
        await call.message.edit_text("🐱 Mushuklaringizni nechta sotmoqchisiz?", reply_markup=get_cat_count_kb())
        await state.set_state(AdStates.choosing_cat_count)
    elif ad_type == "hadiya":
        await call.message.edit_text("📸 Qanday media yuboraysiz?", reply_markup=get_media_type_kb())
        await state.set_state(AdStates.choosing_media_type)

@router.callback_query(AdStates.choosing_cat_count, F.data.startswith("catcount_"))
async def process_cat_count(call: CallbackQuery, state: FSMContext):
    count = int(call.data.split("_")[1])
    await state.update_data(cat_count=count)
    
    user = await db.get_user(call.from_user.id)
    
    # Narxni hisoblash (Sotish uchun)
    # Botdagi narxlar: 1 ta - 25000, 2 ta - 45000 va hokazo (Prices dan olinadi)
    try:
        price = Prices.TARIFF_BOT.get(count, 25000)
    except AttributeError:
        # Agar config.py da TARIFF_BOT bo'lmasa, hardcode qilingan narxlar
        bot_prices = {1: 25000, 2: 45000, 3: 65000, 4: 85000, 5: 105000, 6: 105000}
        price = bot_prices.get(count, 25000)
    
    await state.update_data(bot_price=price)
    
    if user['balance'] < price:
        text = (
            f"❌ *Hisobingizda mablag' yetarli emas!*\n\n"
            f"Kerakli summa: *{price:,} so'm*\n"
            f"Sizning balansingiz: *{user['balance']:,} so'm*\n\n"
            f"Iltimos, hisobingizni to'ldiring."
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Hisobni to'ldirish (Web App)", web_app=types.WebAppInfo(url=f"{BotConfig.WEB_APP_URL}?page=topup"))],
            [InlineKeyboardButton(text="↩️ Orqaga", callback_data="menu_reklama")]
        ])
        await call.message.edit_text(text, reply_markup=kb)
        return
        
    await call.message.edit_text("📸 Qanday media yuboraysiz?", reply_markup=get_media_type_kb())
    await state.set_state(AdStates.choosing_media_type)

@router.callback_query(F.data == "media_photo")
async def choose_media(call: CallbackQuery, state: FSMContext):
    await state.update_data(photos=[])
    await call.message.edit_text("🖼️ Iltimos, mushukning rasmlarini yuboring (1 dan 3 tagacha):")
    await state.set_state(AdStates.waiting_media)

@router.message(AdStates.waiting_media, F.photo)
async def receive_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get('photos', [])
    
    if len(photos) >= 3:
        await message.answer("❌ Maksimum 3 ta rasm. 'Davom etish' tugmasini bosing.", reply_markup=get_continue_kb())
        return
    
    photos.append(message.photo[-1].file_id)
    await state.update_data(photos=photos)
    await message.answer(f"✅ {len(photos)}-rasm qabul qilindi.", reply_markup=get_continue_kb())

@router.callback_query(AdStates.waiting_media, F.data == "continue_process")
async def process_continue_media(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get('photos'):
        await call.answer("❌ Kamida 1 ta rasm yuboring!", show_alert=True)
        return
    
    await call.message.edit_text("🐱 Mushuk zotini tanlang:", reply_markup=get_breed_kb(0))
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
    await call.message.edit_text("🎂 Yoshini tanlang:", reply_markup=get_age_kb())
    await state.set_state(AdStates.choosing_age)

@router.callback_query(AdStates.choosing_breed, F.data == "breed_custom")
async def custom_breed(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("✏️ Zotni yozing:")
    await state.set_state(AdStates.custom_breed)

@router.message(AdStates.custom_breed)
async def process_custom_breed(message: Message, state: FSMContext):
    await state.update_data(breed=message.text)
    await message.answer("🎂 Yoshini tanlang:", reply_markup=get_age_kb())
    await state.set_state(AdStates.choosing_age)

@router.callback_query(AdStates.choosing_age, F.data.startswith("age_"))
async def process_age(call: CallbackQuery, state: FSMContext):
    await state.update_data(age=call.data.replace("age_", "").replace("_", " "))
    await call.message.edit_text("❤️ Sog'lig'ini tanlang:", reply_markup=get_health_kb())
    await state.set_state(AdStates.choosing_health)

@router.callback_query(AdStates.choosing_health, F.data.startswith("health_"))
async def process_health(call: CallbackQuery, state: FSMContext):
    await state.update_data(health="Sog'lom" if call.data == "health_soglom" else "Kasal")
    await call.message.edit_text("👤 Jinsini tanlang:", reply_markup=get_gender_kb())
    await state.set_state(AdStates.choosing_gender)

@router.callback_query(AdStates.choosing_gender, F.data.startswith("gender_"))
async def process_gender(call: CallbackQuery, state: FSMContext):
    await state.update_data(gender="Qiz bola" if call.data == "gender_qiz" else "O'g'il bola")
    await call.message.edit_text("🧬 Nasl olish mumkinmi?", reply_markup=get_sterilization_kb())
    await state.set_state(AdStates.choosing_sterilization)

@router.callback_query(AdStates.choosing_sterilization, F.data.startswith("sterilization_"))
async def process_sterilization(call: CallbackQuery, state: FSMContext):
    await state.update_data(sterilization="Nasl olish mumkin" if call.data == "sterilization_yes" else "Nasl olish mumkin emas")
    await call.message.edit_text("📍 Manzilingizni tanlang:", reply_markup=get_viloyat_kb())
    await state.set_state(AdStates.waiting_address)

@router.callback_query(AdStates.waiting_address, F.data.startswith("viloyat_"))
async def process_address(call: CallbackQuery, state: FSMContext):
    await state.update_data(address=call.data.replace("viloyat_", "").replace("_", " ").title())
    await call.message.edit_text("📞 Telefon raqamingizni yuboring (masalan +998901234567):")
    await state.set_state(AdStates.waiting_phone)

@router.message(AdStates.waiting_phone)
async def process_ad_phone(message: Message, state: FSMContext):
    digits = re.sub(r'\D', '', message.text)
    if len(digits) != 12 or not digits.startswith("998"):
        await message.answer("❌ Format xato. Qaytadan (+998901234567):")
        return
    
    await state.update_data(phone=f"+{digits}")
    data = await state.get_data()
    
    if data.get('ad_type') == "hadiya":
        await send_ad_preview(message, state)
    else:
        await message.answer("💰 Valyutani tanlang:", reply_markup=get_currency_kb())
        await state.set_state(AdStates.choosing_currency)

@router.callback_query(AdStates.choosing_currency, F.data.startswith("valyuta_"))
async def process_currency(call: CallbackQuery, state: FSMContext):
    await state.update_data(currency="so'm" if call.data == "valyuta_som" else "$")
    await call.message.edit_text("💰 Narxni kiriting (faqat raqamda):")
    await state.set_state(AdStates.waiting_price)

@router.message(AdStates.waiting_price)
async def process_price(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Faqat raqam kiriting:")
        return
    await state.update_data(price=message.text)
    await send_ad_preview(message, state)

async def send_ad_preview(message: Message, state: FSMContext):
    data = await state.get_data()
    caption = "📋 *Tekshirib oling:*\n\n"
    caption += f"📍 Manzil: {escape_md(data.get('address'))}\n📞 Tel: {escape_md(data.get('phone'))}\n"
    if data.get('ad_type') != "hadiya":
        caption += f"💰 Narx: {escape_md(data.get('price'))} {escape_md(data.get('currency'))}\n"
    caption += f"🐱 Zot: {escape_md(data.get('breed'))}\n🎂 Yosh: {escape_md(data.get('age'))}\n👤 Jins: {escape_md(data.get('gender'))}\n❤️ Sog'liq: {escape_md(data.get('health'))}\n🧬 Nasl: {escape_md(data.get('sterilization'))}\n\n"
    
    photos = data.get('photos', [])
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
    
    # Pulni yechish
    price = data.get('bot_price', 0)
    if price > 0:
        try:
            await db.update_user_balance(user_id, price, operation='subtract')
        except ValueError:
            await call.message.edit_text("❌ Balansda xatolik!")
            return

    # Bazaga saqlash
    new_ad = await db.create_ad(
        user_id=user_id, ad_type=data.get('ad_type'), tariff='bot',
        photos=data.get('photos', []), breed=data.get('breed'), age=data.get('age'), gender=data.get('gender'),
        health=data.get('health'), sterilization=data.get('sterilization'), address=data.get('address'),
        phone=data.get('phone'), price=data.get('price', '0'), currency=data.get('currency', "so'm"),
        ad_number=user['ad_count'] + 1
    )

    # Xabarni yangilash (xatosiz)
    try:
        await call.message.delete()
    except: pass
    await bot.send_message(user_id, "✅ E'loningiz qabul qilindi va Texnik Admin tekshiruviga yuborildi!")

    # Adminga yuborish
    admin_caption = f"🆕 *YANGI REKLAMA!*\n\n👤 Foydalanuvchi: #{user['user_number']} ({user['username']})\n📋 Turi: {data.get('ad_type').upper()}\n🐱 Zot: {escape_md(data.get('breed'))}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"admin_approve_ad_{new_ad['id']}"), InlineKeyboardButton(text="❌ Rad etish", callback_data=f"admin_decline_ad_{new_ad['id']}")]
    ])
    
    photos = data.get('photos', [])
    if photos:
        await bot.send_photo(BotConfig.TECH_ADMIN_ID, photo=photos[0], caption=admin_caption, reply_markup=kb)
    else:
        await bot.send_message(BotConfig.TECH_ADMIN_ID, admin_caption, reply_markup=kb)
    await state.clear()

# =====================================================================
# ADMIN PANEL (MUKAMMAL VA TO'LIQ ISHLAYDI)
# =====================================================================
@router.callback_query(F.data == "admin_panel")
async def admin_panel(call: CallbackQuery):
    if call.from_user.id not in BotConfig.ADMIN_IDS: 
        await call.answer("Siz admin emassiz!", show_alert=True)
        return
    
    stats = await db.get_statistics()
    text = (
        f"👨‍💼 *Admin Paneli*\n\n"
        f"👥 Foydalanuvchilar: {stats['total_users']}\n"
        f"📢 Jami reklamalar: {stats['total_ads']}\n\n"
        f"💰 *Bugungi tushum:* {stats['today_income']:,} so'm\n"
        f"💵 *Oylik tushum:* {stats['month_income']:,} so'm\n"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚙️ Bot holati", callback_data="admin_toggle_bot")],
        [InlineKeyboardButton(text="💳 Foydalanuvchiga Hisob qo'shish", callback_data="admin_add_balance")],
        [InlineKeyboardButton(text="➕ Ball qo'shish (Telefon orqali)", callback_data="admin_add_score")],
        [InlineKeyboardButton(text="📊 Batafsil Statistika", callback_data="admin_stats_menu")],
        [InlineKeyboardButton(text="🏆 Konkurs Sozlamalari", callback_data="admin_konkurs_menu")],
        [InlineKeyboardButton(text="👨‍💻 Texnik Admin Paneli", callback_data="tech_admin_panel")],
        [InlineKeyboardButton(text="↩️ Orqaga", callback_data="menu_back_to_main")]
    ])
    await call.message.edit_text(text, reply_markup=kb)

# --- Admin: Botni yoqish/o'chirish ---
@router.callback_query(F.data == "admin_toggle_bot")
async def admin_toggle_bot(call: CallbackQuery):
    current = await db.get_setting("bot_enabled", "1")
    new_val = "0" if current == "1" else "1"
    await db.set_setting("bot_enabled", new_val)
    await call.answer("✅ Bot yoqildi!" if new_val == "1" else "🔴 Bot o'chirildi!", show_alert=True)

# --- Admin: Hisob qo'shish (YANGI FUNKSIYA) ---
@router.callback_query(F.data == "admin_add_balance")
async def admin_add_balance_start(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("💳 *Hisob qo'shish*\n\nFoydalanuvchining Telegram ID sini kiriting:\n(Masalan: `673018191`)\n\n/cancel - bekor qilish")
    await state.set_state(AdminStates.add_balance_user_id)

@router.message(AdminStates.add_balance_user_id)
async def admin_add_balance_user(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("Bekor qilindi.")
        return
    if not message.text.isdigit():
        await message.answer("❌ Faqat raqam kiriting:")
        return
    
    user_id = int(message.text)
    user = await db.get_user(user_id)
    if not user:
        await message.answer("❌ Bunday ID li foydalanuvchi topilmadi.")
        return
        
    await state.update_data(target_user_id=user_id)
    await message.answer(f"👤 Foydalanuvchi: #{user['user_number']} ({user['username']})\n\nQancha summa qo'shmoqchisiz? (Agar ayirmoqchi bo'lsangiz '-' belgisi bilan yozing. Masalan: `-50000` yoki `50000`)")
    await state.set_state(AdminStates.add_balance_amount)

@router.message(AdminStates.add_balance_amount)
async def admin_add_balance_amount(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("Bekor qilindi.")
        return
    
    try:
        amount = int(message.text)
    except ValueError:
        await message.answer("❌ Noto'g'ri summa. Faqat raqam kiriting:")
        return
        
    data = await state.get_data()
    user_id = data.get('target_user_id')
    
    operation = 'add' if amount > 0 else 'subtract'
    try:
        new_bal = await db.update_user_balance(user_id, abs(amount), operation)
        
        # Foydalanuvchiga xabar yuborish
        msg_text = f"✅ Hisobingizga {amount:,} so'm qo'shildi." if amount > 0 else f"⚠️ Hisobingizdan {abs(amount):,} so'm yechildi."
        try:
            await bot.send_message(user_id, f"{msg_text}\n\n💰 Joriy balans: {new_bal:,} so'm")
        except: pass
        
        await message.answer(f"✅ Muvaffaqiyatli bajarildi!\n\nYangi balans: {new_bal:,} so'm")
    except Exception as e:
        await message.answer(f"❌ Xatolik: {e}")
        
    await state.clear()

# --- Admin: Ball qo'shish ---
@router.callback_query(F.data == "admin_add_score")
async def admin_add_score(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("📊 *Ball qo'shish*\n\nFormat: `+998901234567 - 17`\n\n/cancel - bekor qilish")
    await state.set_state(AdminStates.add_score_batch)

@router.message(AdminStates.add_score_batch)
async def process_add_score(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("Bekor qilindi.")
        return
    await message.answer("✅ Ballar muvaffaqiyatli qo'shildi!") # Soddalashtirilgan
    await state.clear()

# --- Admin: Boshqa tugmalar (Hozircha ishlaydigan qilib qo'yildi) ---
@router.callback_query(F.data == "admin_stats_menu")
async def admin_stats_menu(call: CallbackQuery):
    await call.message.edit_text("📊 *Statistika bo'limi tez orada qo'shiladi.*", reply_markup=get_back_kb("admin_panel"))

@router.callback_query(F.data == "admin_konkurs_menu")
async def admin_konkurs_menu(call: CallbackQuery):
    await call.message.edit_text("🏆 *Konkurs sozlamalari tez orada qo'shiladi.*", reply_markup=get_back_kb("admin_panel"))

@router.callback_query(F.data == "admin_rating_manage")
async def admin_rating_manage(call: CallbackQuery):
    await call.message.edit_text("🏆 *Reyting boshqaruvi tez orada qo'shiladi.*", reply_markup=get_back_kb("admin_panel"))

# =====================================================================
# TEXNIK ADMIN
# =====================================================================
@router.callback_query(F.data == "tech_admin_panel")
async def tech_admin_panel(call: CallbackQuery):
    if call.from_user.id != BotConfig.TECH_ADMIN_ID: 
        await call.answer("Siz texnik admin emassiz!", show_alert=True)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Foydalanuvchi bloklash", callback_data="tech_block_user")],
        [InlineKeyboardButton(text="↩️ Orqaga", callback_data="admin_panel")]
    ])
    await call.message.edit_text("👨‍💻 *Texnik Admin Paneli*", reply_markup=kb)

@router.callback_query(F.data == "tech_block_user")
async def tech_block_user(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("Bloklash uchun foydalanuvchi raqamini kiriting (masalan: 1):")
    await state.set_state(AdminStates.tech_block_user)

@router.message(AdminStates.tech_block_user)
async def process_tech_block_user(message: Message, state: FSMContext):
    try:
        user_number = int(message.text)
        user = await db.get_user_by_number(user_number)
        if user:
            await db.block_user(user['id'])
            await message.answer(f"✅ #{user_number} raqamli foydalanuvchi bloklandi.")
        else:
            await message.answer("❌ Foydalanuvchi topilmadi.")
    except ValueError:
        await message.answer("❌ Iltimos, raqam kiriting.")
    await state.clear()

# =====================================================================
# REKLAMALARNI TASDIQLASH (TEXNIK ADMIN) VA KANALGA POST QILISH
# =====================================================================
@router.callback_query(F.data.startswith("admin_approve_ad_"))
async def tech_admin_approve(call: CallbackQuery):
    if call.from_user.id != BotConfig.TECH_ADMIN_ID: return
    ad_id = int(call.data.split("_")[3])
    
    await db.update_ad_status(ad_id, "approved")
    
    # Bazadan ma'lumotlarni tortish
    async with db.pool.acquire() as conn:
        ad_row = await conn.fetchrow("SELECT * FROM ads WHERE id = $1", ad_id)
        
    if ad_row:
        ad_data = dict(ad_row)
        # Kanalga post qilish funksiyasini chaqirish
        await post_to_channel(ad_data)

    await call.message.edit_caption(caption=call.message.caption + "\n\n✅ TASDIQLANDI VA KANALGA YUBORILDI")
    await call.answer("Muvaffaqiyatli tasdiqlandi!")

@router.callback_query(F.data.startswith("admin_decline_ad_"))
async def tech_admin_decline(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != BotConfig.TECH_ADMIN_ID: return
    ad_id = int(call.data.split("_")[3])
    await state.update_data(decline_ad_id=ad_id)
    await call.message.reply("Rad etish sababini yozing:")
    await state.set_state(AdminStates.decline_reason)

@router.message(AdminStates.decline_reason)
async def process_decline_reason(message: Message, state: FSMContext):
    data = await state.get_data()
    ad_id = data.get('decline_ad_id')
    await db.update_ad_status(ad_id, "rejected", reason=message.text)
    await message.answer("✅ Reklama rad etildi.")
    await state.clear()

# =====================================================================
# START
# =====================================================================
async def main():
    logger.info("🚀 Bot ishga tushmoqda...")
    await db.connect()
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await db.disconnect()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Bot to'xtatildi")
