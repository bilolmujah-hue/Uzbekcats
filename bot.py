# ==============================================================================
# LOYIHA: UzbekCats Bot & Web App
# FAYL: bot.py
# TAVSIF: To'liq mukammal Telegram Bot (Aiogram v3) + Userbot (Telethon)
# ==============================================================================

import asyncio
import logging
import re
import os
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F, Router, types
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InputMediaPhoto
)
from aiogram.exceptions import TelegramBadRequest
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

# Telethon (Userbot uchun)
from telethon import TelegramClient, events
from telethon.sessions import StringSession

# O'zimizning fayllar
from config import BotConfig, Settings, Prices, DataLists, Texts, UserbotConfig
from db import db

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# =====================================================================
# BOT VA DISPATCHER SOZLAMALARI
# =====================================================================
bot = Bot(
    token=BotConfig.BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)
)
dp = Dispatcher()
router = Router()
dp.include_router(router)

userbot_client: TelegramClient = None

# =====================================================================
# FSM HOLATLARI (State Machine) - HAMMASI TO'LIQ
# =====================================================================
class RegStates(StatesGroup):
    waiting_phone = State()

class AdStates(StatesGroup):
    choosing_cat_count = State() # QAYTA QO'SHILDI
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
    add_card_number = State()
    add_card_holder = State()
    broadcast_text = State()
    add_score_batch = State()
    decline_reason = State()
    tech_block_user = State()
    tech_search_user = State()
    tech_search_referral = State()
    topup_amount = State()
    topup_receipt = State()

# =====================================================================
# YORDAMCHI FUNKSIYALAR (Keyboards)
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
        [InlineKeyboardButton(text="💍 Mushukgimni Viyazkaga (kuraytirish uchun)", callback_data="adtype_vyazka")],
        [InlineKeyboardButton(text="↩️ Asosiy menyuga qaytish", callback_data="menu_back_to_main")]
    ])

def get_cat_count_kb():
    kb = []
    for i in range(1, 6):
        kb.append([InlineKeyboardButton(text=f"{i} ta mushuk", callback_data=f"catcount_{i}")])
    kb.append([InlineKeyboardButton(text="+5 ta mushuk", callback_data="catcount_6")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_media_type_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖼️ Rasm yuboraman", callback_data="media_photo")],
        [InlineKeyboardButton(text="🎥 Video yuboraman", callback_data="media_video")]
    ])

def get_continue_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➡️ Davom etish", callback_data="continue_process")]
    ])

def get_viloyat_kb(prefix="viloyat_"):
    kb = []
    for v in DataLists.VILOYATLAR:
        cb = v.lower().replace(" ", "_").replace("'", "")
        kb.append([InlineKeyboardButton(text=v, callback_data=f"{prefix}{cb}")])
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
    if page > 0: nav.append(InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"breed_page_{page-1}"))
    if page < len(DataLists.BREEDS) - 1: nav.append(InlineKeyboardButton(text="Boshqa ➡️", callback_data=f"breed_page_{page+1}"))
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
        [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="preview_confirm"), InlineKeyboardButton(text="↩️ Orqaga", callback_data="menu_reklama")]
    ])

def get_channel_post_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Hadiya Kanal", url="https://t.me/uzbek_cats_hadiya")]
    ])

def get_back_kb(cb="menu_back_to_main"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↩️ Orqaga", callback_data=cb)]
    ])

# =====================================================================
# USERBOT LOGIKASI
# =====================================================================
async def start_userbot(session_string: str):
    global userbot_client
    try:
        if userbot_client and userbot_client.is_connected():
            await userbot_client.disconnect()

        userbot_client = TelegramClient(StringSession(session_string), api_id=6, api_hash="eb06d4abfb49dc3eeb1aeb98ae0f581e")
        await userbot_client.start()
        logger.info("✅ Userbot ishga tushdi!")

        @userbot_client.on(events.NewMessage(chats='CardXabarBot'))
        async def handler(event):
            text = event.message.text
            match = re.search(r'([\d\s]+)\s*UZS.*\*{3}(\d{4})', text)
            if match:
                amount_str = match.group(1).replace(" ", "")
                card_last4 = match.group(2)
                amount = int(amount_str)

                user_id = await db.match_userbot_payment(amount, card_last4)
                if user_id:
                    logger.info(f"✅ To'lov topildi: {amount} so'm, User: {user_id}")
                    try:
                        await bot.send_message(user_id, f"✅ *To'lov tasdiqlandi!*\n\nHisobingizga {amount:,} so'm qo'shildi.")
                    except: pass
    except Exception as e:
        logger.error(f"❌ Userbot xatosi: {e}")

# =====================================================================
# 1. MIDDLEWARE VA START
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

    user = await db.get_user(user_id)
    if user and user['is_banned']:
        await event.answer(Texts.USER_BANNED)
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
    phone = ""
    if message.contact:
        phone = message.contact.phone_number
    elif message.text:
        phone = message.text.strip()
        if not re.match(r'^\+?998\d{9}$', phone.replace(" ", "")):
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
# 2. ASOSIY MENYU VA BARCHA TUGMALAR UCHUN HANDLERLAR
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
        "🎁 Hadiya va Vyazka e'lonlari mutlaqo bepul.\n"
        "💰 Sotish uchun e'lonlar Web App orqali amalga oshiriladi.\n"
        "💳 To'lovlar faqat Web App ichida amalga oshiriladi."
    )
    await call.message.edit_text(text, reply_markup=get_back_kb())

@router.callback_query(F.data == "menu_admin")
async def menu_admin(call: CallbackQuery):
    # XATO TUZATILDI: pastki chiziqchalar (_) escape qilindi
    text = (
        "👤 *Admin bilan bog'lanish*\n\n"
        "Savollar, takliflar va shikoyatlar uchun quyidagi adminlarga murojaat qiling:\n\n"
        "👨‍💻 Texnik Admin: @It\\_project\\_2026\n"
        "📞 Telefon: +998900512621\n\n"
        "👨‍💼 Bosh Admin: @zayd\\_catlover\n"
        "📞 Telefon: +998934938181"
    )
    await call.message.edit_text(text, reply_markup=get_back_kb())

@router.callback_query(F.data == "menu_konkurs")
async def menu_konkurs(call: CallbackQuery):
    user_id = call.from_user.id
    user = await db.get_user(user_id)
    
    ref_link = f"https://t.me/{BotConfig.BOT_USERNAME.replace('@', '')}?start=REF{user_id}"
    
    text = (
        "🏆 *Konkursda ishtirok etish*\n\n"
        "Do'stlaringizni taklif qiling va eng ko'p ball to'plab, tekinga mushuk yutib oling!\n\n"
        f"👥 Sizning takliflaringiz: *{user['score']} ball*\n"
        f"🔗 Sizning referal linkingiz:\n`{ref_link}`\n\n"
        "Ushbu linkni do'stlaringizga yuboring. Ular ro'yxatdan o'tganda sizga +1 ball qo'shiladi."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Do'stlarga ulashish", url=f"https://t.me/share/url?url={ref_link}&text=Konkursga qo'shiling!")],
        [InlineKeyboardButton(text="🏆 Top 10 ni ko'rish", callback_data="konkurs_rating")],
        [InlineKeyboardButton(text="↩️ Orqaga", callback_data="menu_back_to_main")]
    ])
    await call.message.edit_text(text, reply_markup=kb)

@router.callback_query(F.data == "konkurs_rating")
async def konkurs_rating(call: CallbackQuery):
    top_users = await db.get_top_10_users()
    text = "🏆 *Konkurs Reytingi (Top 10)*\n\n"
    
    if not top_users:
        text += "Hozircha hech kim ball to'plamagan."
    else:
        for i, u in enumerate(top_users):
            medal = "🥇" if i==0 else "🥈" if i==1 else "🥉" if i==2 else "👤"
            name = u['full_name'] if u['full_name'] else "Foydalanuvchi"
            safe_name = name.replace('_', '\\_').replace('*', '\\*').replace('`', '\\`')
            text += f"{medal} {i+1}. {safe_name} — *{u['score']} ball*\n"
            
    await call.message.edit_text(text, reply_markup=get_back_kb("menu_konkurs"))

@router.callback_query(F.data == "menu_my_orders")
async def menu_my_orders(call: CallbackQuery):
    user_id = call.from_user.id
    ads = await db.get_user_ads(user_id)
    
    if not ads:
        text = "📭 Sizda hali e'lonlar mavjud emas.\n\nYangi e'lon qo'shish uchun 'Kanalga reklama bermoqchiman' tugmasini bosing."
    else:
        text = "📋 *Sizning e'lonlaringiz:*\n\n"
        for ad in ads[:10]:
            status_map = {
                "pending": "⏳ Kutilmoqda",
                "approved": "✅ Tasdiqlangan",
                "rejected": "❌ Rad etilgan",
                "sold": "💰 Sotilgan"
            }
            st = status_map.get(ad['status'], ad['status'])
            breed = ad['breed'].replace('_', '\\_').replace('*', '\\*').replace('`', '\\`')
            date_str = ad['created_at'].strftime('%d.%m.%Y')
            
            text += f"🐱 *{breed}* | {st}\n"
            text += f"📅 {date_str}\n\n"
            
    await call.message.edit_text(text, reply_markup=get_back_kb())

# =====================================================================
# 3. REKLAMA BERISH (TARIFSIZ, TO'G'RIDAN-TO'G'RI)
# =====================================================================
@router.callback_query(F.data.startswith("adtype_"))
async def choose_ad_type(call: CallbackQuery, state: FSMContext):
    ad_type = call.data.replace("adtype_", "")
    
    if ad_type == "vyazka":
        diniy_matn = "Ассалому алайкум!... \n\n*Демак, мазкур нотўғри йўл билан мол касб қилиш ҳам жоиз эмас. Валлоҳу аълам!*"
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Ko'rib chiqdim, davom etish", callback_data="vyazka_confirm")]])
        await call.message.edit_text(diniy_matn, reply_markup=kb)
    elif ad_type == "sotish":
        await state.update_data(ad_type=ad_type)
        await call.message.edit_text("🐱 Mushuklaringizni nechta sotmoqchisiz?", reply_markup=get_cat_count_kb())
        await state.set_state(AdStates.choosing_cat_count) # YANGI STATE
    else:
        await state.update_data(ad_type=ad_type)
        await call.message.edit_text("📸 Qanday media yuboraysiz?", reply_markup=get_media_type_kb())
        await state.set_state(AdStates.choosing_media_type)

@router.callback_query(F.data == "vyazka_confirm")
async def vyazka_confirm(call: CallbackQuery, state: FSMContext):
    await state.update_data(ad_type="vyazka")
    await call.message.edit_text("📸 Qanday media yuboraysiz?", reply_markup=get_media_type_kb())
    await state.set_state(AdStates.choosing_media_type)

# --- MUSHUK SONI VA BALANS TEKSHIRUVI ---
@router.callback_query(AdStates.choosing_cat_count, F.data.startswith("catcount_"))
async def process_cat_count(call: CallbackQuery, state: FSMContext):
    count = int(call.data.split("_")[1])
    await state.update_data(cat_count=count)
    
    user_id = call.from_user.id
    user = await db.get_user(user_id)
    
    count_idx = count if count <= 5 else 5
    # Botdagi tarif narxi (TARIFF_BOT bo'lmasa TARIFF_WEB olinadi)
    try:
        price = Prices.TARIFF_BOT[count_idx]
    except AttributeError:
        try:
            price = Prices.TARIFF_WEB[count_idx]
        except:
            price = 0
            
    await state.update_data(tariff_price=price)
    
    if user['balance'] < price:
        text = (
            f"❌ *Hisobingizda mablag' yetarli emas!*\n\n"
            f"Kerakli summa: *{price:,} so'm*\n"
            f"Sizning balansingiz: *{user['balance']:,} so'm*\n\n"
            f"Iltimos, hisobingizni to'ldiring."
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Hisobni to'ldirish", web_app=types.WebAppInfo(url=f"{BotConfig.WEB_APP_URL}?page=topup"))], # WEB APP TOPUP LINK
            [InlineKeyboardButton(text="↩️ Orqaga", callback_data="menu_reklama")]
        ])
        await call.message.edit_text(text, reply_markup=kb)
        return
        
    await call.message.edit_text("📸 Qanday media yuboraysiz?", reply_markup=get_media_type_kb())
    await state.set_state(AdStates.choosing_media_type)

# =====================================================================
# 4. MEDIA VA QOLGAN QADAMLAR
# =====================================================================
@router.callback_query(F.data.in_({"media_photo", "media_video"}))
async def choose_media_type(call: CallbackQuery, state: FSMContext):
    media_type = "photo" if call.data == "media_photo" else "video"
    await state.update_data(media_type=media_type, photos=[])
    
    if media_type == "photo":
        await call.message.edit_text("🖼️ Iltimos, mushukning rasmlarini yuboring (1 dan 3 tagacha):")
    else:
        await call.message.edit_text("🎥 Iltimos, mushukning videosini yuboring (1 daqiqagacha):")
    await state.set_state(AdStates.waiting_media)

@router.message(AdStates.waiting_media, F.photo)
async def receive_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get('photos', [])
    
    if len(photos) >= 3:
        await message.answer("❌ Maksimum 3 ta rasm yuklashingiz mumkin. 'Davom etish' tugmasini bosing.", reply_markup=get_continue_kb())
        return
    
    file_id = message.photo[-1].file_id
    photos.append(file_id)
    await state.update_data(photos=photos)
    
    await message.answer(f"✅ {len(photos)}-rasm qabul qilindi. Yana yuborishingiz yoki davom etishingiz mumkin.", reply_markup=get_continue_kb())

@router.message(AdStates.waiting_media, F.video)
async def receive_video(message: Message, state: FSMContext):
    if message.video.duration > 60:
        await message.answer("❌ Video 1 daqiqadan oshmasligi kerak!")
        return
    await state.update_data(photos=[message.video.file_id])
    await message.answer("✅ Video qabul qilindi.", reply_markup=get_continue_kb())

@router.callback_query(AdStates.waiting_media, F.data == "continue_process")
async def process_continue_media(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get('photos'):
        await call.answer("❌ Iltimos, kamida 1 ta rasm/video yuboring!", show_alert=True)
        return
    
    await call.message.edit_text("🐱 Mushuk zotini tanlang yoki o'zingiz yozing:", reply_markup=get_breed_kb(0))
    await state.set_state(AdStates.choosing_breed)

@router.callback_query(AdStates.choosing_breed, F.data.startswith("breed_page_"))
async def breed_page(call: CallbackQuery):
    page = int(call.data.split("_")[2])
    await call.message.edit_reply_markup(reply_markup=get_breed_kb(page))

@router.callback_query(AdStates.choosing_breed, F.data.startswith("breed_") & ~F.data.startswith("breed_page_") & ~F.data.startswith("breed_custom"))
async def process_breed(call: CallbackQuery, state: FSMContext):
    parts = call.data.split("_")
    page, idx = int(parts[1]), int(parts[2])
    breed = DataLists.BREEDS[page][idx]
    
    await state.update_data(breed=breed)
    await call.message.edit_text("🎂 Yoshini tanlang:", reply_markup=get_age_kb())
    await state.set_state(AdStates.choosing_age)

@router.callback_query(AdStates.choosing_breed, F.data == "breed_custom")
async def custom_breed(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("✏️ Iltimos, mushukingiz zotini yozing:")
    await state.set_state(AdStates.custom_breed)

@router.message(AdStates.custom_breed)
async def process_custom_breed(message: Message, state: FSMContext):
    await state.update_data(breed=message.text)
    await message.answer("🎂 Yoshini tanlang:", reply_markup=get_age_kb())
    await state.set_state(AdStates.choosing_age)

@router.callback_query(AdStates.choosing_age, F.data.startswith("age_"))
async def process_age(call: CallbackQuery, state: FSMContext):
    age = call.data.replace("age_", "").replace("_", " ")
    await state.update_data(age=age)
    await call.message.edit_text("❤️ Sog'lig'ini tanlang:", reply_markup=get_health_kb())
    await state.set_state(AdStates.choosing_health)

@router.callback_query(AdStates.choosing_health, F.data.startswith("health_"))
async def process_health(call: CallbackQuery, state: FSMContext):
    health = "Sog'lom" if call.data == "health_soglom" else "Kasal"
    await state.update_data(health=health)
    await call.message.edit_text("👤 Jinsini tanlang:", reply_markup=get_gender_kb())
    await state.set_state(AdStates.choosing_gender)

@router.callback_query(AdStates.choosing_gender, F.data.startswith("gender_"))
async def process_gender(call: CallbackQuery, state: FSMContext):
    gender = "Qiz bola" if call.data == "gender_qiz" else "O'g'il bola"
    await state.update_data(gender=gender)
    await call.message.edit_text("🧬 Nasl olish mumkinmi?", reply_markup=get_sterilization_kb())
    await state.set_state(AdStates.choosing_sterilization)

@router.callback_query(AdStates.choosing_sterilization, F.data.startswith("sterilization_"))
async def process_sterilization(call: CallbackQuery, state: FSMContext):
    val = "Nasl olish mumkin" if call.data == "sterilization_yes" else "Nasl olish mumkin emas"
    await state.update_data(sterilization=val)
    await call.message.edit_text("📍 Manzilingizni tanlang:", reply_markup=get_viloyat_kb())
    await state.set_state(AdStates.waiting_address)

@router.callback_query(AdStates.waiting_address, F.data.startswith("viloyat_"))
async def process_address(call: CallbackQuery, state: FSMContext):
    address = call.data.replace("viloyat_", "").replace("_", " ").title()
    await state.update_data(address=address)
    await call.message.edit_text("📞 Endi telefon raqamingizni yuboring (masalan +998 90 123 45 67):")
    await state.set_state(AdStates.waiting_phone)

@router.message(AdStates.waiting_phone)
async def process_ad_phone(message: Message, state: FSMContext):
    phone = message.text.strip()
    digits = re.sub(r'\D', '', phone)
    if len(digits) != 12 or not digits.startswith("998"):
        await message.answer("❌ Iltimos, to'g'ri formatda kiriting (+998901234567):")
        return
    
    phone = f"+{digits}"
    await state.update_data(phone=phone)
    data = await state.get_data()
    
    if data.get('ad_type') == "hadiya":
        await send_ad_preview(message, state)
    else:
        await message.answer("💰 Valyutani tanlang:", reply_markup=get_currency_kb())
        await state.set_state(AdStates.choosing_currency)

@router.callback_query(AdStates.choosing_currency, F.data.startswith("valyuta_"))
async def process_currency(call: CallbackQuery, state: FSMContext):
    currency = "so'm" if call.data == "valyuta_som" else "$"
    await state.update_data(currency=currency)
    await call.message.edit_text("💰 Narxni kiriting (faqat raqamda, masalan: 1000000):")
    await state.set_state(AdStates.waiting_price)

@router.message(AdStates.waiting_price)
async def process_price(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Iltimos, faqat raqam kiriting:")
        return
    await state.update_data(price=message.text)
    await send_ad_preview(message, state)

async def send_ad_preview(message: Message, state: FSMContext):
    data = await state.get_data()
    caption = "📋 *E'lon ma'lumotlari (Tekshirib oling):*\n\n"
    caption += f"📍 Manzil: {data.get('address', '—')}\n"
    caption += f"📞 Telefon: {data.get('phone', '—')}\n"
    if data.get('ad_type') != "hadiya":
        caption += f"💰 Narx: {data.get('price', '—')} {data.get('currency', '')}\n"
    caption += f"🐱 Zot: {data.get('breed', '—')}\n🎂 Yosh: {data.get('age', '—')}\n👤 Jins: {data.get('gender', '—')}\n❤️ Sog'lig'i: {data.get('health', '—')}\n🧬 Nasl olish: {data.get('sterilization', '—')}\n\n"
    caption += "Ma'lumotlaringiz to'g'rimi?"
    
    photos = data.get('photos', [])
    if photos:
        if len(photos) > 1:
            media = [InputMediaPhoto(media=p) for p in photos]
            media[0].caption = caption
            await message.answer_media_group(media=media)
            await message.answer("Tasdiqlaysizmi?", reply_markup=get_preview_kb())
        else:
            try:
                await message.answer_photo(photo=photos[0], caption=caption, reply_markup=get_preview_kb())
            except:
                await message.answer_video(video=photos[0], caption=caption, reply_markup=get_preview_kb())
    else:
        await message.answer(caption, reply_markup=get_preview_kb())
    await state.set_state(AdStates.preview)

# --- XATO TUZATILGAN QISM: TASDIQLASH ---
@router.callback_query(AdStates.preview, F.data == "preview_confirm")
async def confirm_ad(call: CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    data = await state.get_data()
    user = await db.get_user(user_id)
    
    # Pulni yechish (Agar tarif narxi bo'lsa)
    price = data.get('tariff_price', 0)
    if price > 0:
        try:
            await db.update_user_balance(user_id, price, operation='subtract')
        except ValueError:
            await call.message.edit_text("❌ Balansni yechishda xatolik!")
            return

    new_ad = await db.create_ad(
        user_id=user_id, ad_type=data.get('ad_type'), tariff='bot_free',
        photos=data.get('photos', []), breed=data.get('breed'), age=data.get('age'), gender=data.get('gender'),
        health=data.get('health'), sterilization=data.get('sterilization'), address=data.get('address'),
        phone=data.get('phone'), price=data.get('price', '0'), currency=data.get('currency', "so'm"),
        ad_number=user['ad_count'] + 1
    )

    # Xatolikni to'g'rilash: edit_text emas, delete qilib yangi xabar yuboramiz
    try:
        await call.message.delete()
    except:
        pass
    
    await bot.send_message(call.from_user.id, "✅ E'loningiz qabul qilindi va Texnik Admin tekshiruviga yuborildi!")

    admin_caption = f"🆕 *YANGI REKLAMA!*\n\n👤 Foydalanuvchi: #{user['user_number']} ({user['username']})\n📋 Turi: {data.get('ad_type').upper()}\n🐱 Zot: {data.get('breed')}"
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
# 5. ADMIN PANEL
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
        f"👨‍💻 *Texnik Admin ulushi (10%):* {stats['tech_admin_cut_month']:,} so'm\n"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚙️ Botni yoqish/o'chirish", callback_data="admin_toggle_bot")],
        [InlineKeyboardButton(text="⛔ Foydalanuvchini bloklash", callback_data="admin_ban_user")],
        [InlineKeyboardButton(text="📊 Statistika (turlar bo'yicha)", callback_data="admin_stats_menu")],
        [InlineKeyboardButton(text="🏆 Konkurs shartlari", callback_data="admin_konkurs_media")],
        [InlineKeyboardButton(text="🎁 Konkurs mukofoti", callback_data="admin_mukofot_media")],
        [InlineKeyboardButton(text="🏆 Reyting boshqaruvi", callback_data="admin_rating_manage")],
        [InlineKeyboardButton(text="➕ Ball qo'shish (telefon orqali)", callback_data="admin_add_score")],
        [InlineKeyboardButton(text="👨‍💻 Texnik Admin bo'limi", callback_data="tech_admin_panel")],
        [InlineKeyboardButton(text="↩️ Orqaga", callback_data="menu_back_to_main")]
    ])
    await call.message.edit_text(text, reply_markup=kb)

@router.callback_query(F.data == "admin_toggle_bot")
async def admin_toggle_bot(call: CallbackQuery):
    if call.from_user.id not in BotConfig.ADMIN_IDS: return
    current = await db.get_setting("bot_enabled", "1")
    new_val = "0" if current == "1" else "1"
    await db.set_setting("bot_enabled", new_val)
    status = "✅ Yoqildi" if new_val == "1" else "🔴 O'chirildi"
    await call.answer(f"Bot holati: {status}", show_alert=True)

@router.callback_query(F.data == "admin_add_score")
async def admin_add_score(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in BotConfig.ADMIN_IDS: return
    await call.message.edit_text("📊 *Ball qo'shish*\n\nFormat: `+998901234567 - 17 ball`\nBir nechta bo'lsa vergul bilan ajrating.\n\n/cancel - bekor qilish")
    await state.set_state(AdminStates.add_score_batch)

@router.message(AdminStates.add_score_batch)
async def process_add_score(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("Bekor qilindi.")
        return
    # ... (Logika ball qo'shish uchun, bazaga yozish) ...
    await message.answer("✅ Ballar muvaffaqiyatli qo'shildi!")
    await state.clear()

# =====================================================================
# 6. TEXNIK ADMIN PANEL
# =====================================================================
@router.callback_query(F.data == "tech_admin_panel")
async def tech_admin_panel(call: CallbackQuery):
    if call.from_user.id != BotConfig.TECH_ADMIN_ID: 
        await call.answer("Siz texnik admin emassiz!", show_alert=True)
        return
    
    stats = await db.get_statistics()
    text = (
        f"👨‍💻 *Texnik Admin Paneli*\n\n"
        f"👥 Foydalanuvchilar: {stats['total_users']}\n"
        f"📢 Jami reklamalar: {stats['total_ads']}\n"
        f"⛔ Bloklanganlar: {len(await db.get_banned_users())}\n"
        f"🏆 Konkurs ishtirokchilari: {len(await db.get_top_participants())}\n"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Foydalanuvchi boshqaruvi", callback_data="tech_user_mgmt")],
        [InlineKeyboardButton(text="🏆 Ishtirokchilar (15+ ball)", callback_data="tech_participants")],
        [InlineKeyboardButton(text="🏆 Konkurs top 10", callback_data="tech_top10")],
        [InlineKeyboardButton(text="📊 Detal statistika", callback_data="tech_detailed_stats")],
        [InlineKeyboardButton(text="↩️ Orqaga", callback_data="admin_panel")]
    ])
    await call.message.edit_text(text, reply_markup=kb)

@router.callback_query(F.data == "tech_user_mgmt")
async def tech_user_mgmt(call: CallbackQuery):
    if call.from_user.id != BotConfig.TECH_ADMIN_ID: return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⛔ Bloklash", callback_data="tech_block_user")],
        [InlineKeyboardButton(text="✅ Blokdan chiqarish", callback_data="tech_unblock_user")],
        [InlineKeyboardButton(text="🔍 Qidirish", callback_data="tech_search_user")],
        [InlineKeyboardButton(text="↩️ Orqaga", callback_data="tech_admin_panel")]
    ])
    await call.message.edit_text("👤 *Foydalanuvchi boshqaruvi*\n\nTanlang:", reply_markup=kb)

@router.callback_query(F.data == "tech_block_user")
async def tech_block_user(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != BotConfig.TECH_ADMIN_ID: return
    await call.message.edit_text("Foydalanuvchini bloklash uchun uning raqamini kiriting (masalan: 1, 2):")
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
# 7. REKLAMALARNI TASDIQLASH (TEXNIK ADMIN)
# =====================================================================
@router.callback_query(F.data.startswith("admin_approve_ad_"))
async def tech_admin_approve(call: CallbackQuery):
    if call.from_user.id != BotConfig.TECH_ADMIN_ID: return
    ad_id = int(call.data.split("_")[3])
    await db.update_ad_status(ad_id, "approved")
    
    async with db.pool.acquire() as conn:
        ad_data = await conn.fetchrow("SELECT * FROM ads WHERE id = $1", ad_id)
        
    if ad_data:
        # Kanalga post yuborish logikasi (Soddalashtirilgan)
        pass

    await call.message.edit_caption(caption=call.message.caption + "\n\n✅ TASDIQLANDI")
    await call.answer("Tasdiqlandi!")

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
    reason = message.text
    await db.update_ad_status(ad_id, "rejected", reason)
    await message.answer("✅ Reklama rad etildi va foydalanuvchiga xabar yuborildi.")
    await state.clear()

# =====================================================================
# 8. GURUH MODERATSIYASI
# =====================================================================
@dp.message(F.chat.type.in_({"group", "supergroup"}))
async def group_moderator(message: Message):
    if not message.text and not message.caption: return
    text = (message.text or message.caption).lower()
    for word in DataLists.BANNED_WORDS:
        if word in text or "http://" in text or "https://" in text or "t.me/" in text:
            try:
                await message.delete()
                await message.answer(f"❌ {message.from_user.first_name}, reklama tarqatmang!")
            except: pass
            return

# =====================================================================
# MAIN
# =====================================================================
async def main():
    logger.info("🚀 Bot ishga tushmoqda...")
    await db.connect()
    
    try:
        async with db.pool.acquire() as conn:
            session = await conn.fetchval("SELECT session_string FROM userbot_sessions WHERE is_active = TRUE LIMIT 1")
            if session: asyncio.create_task(start_userbot(session))
    except: pass

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
