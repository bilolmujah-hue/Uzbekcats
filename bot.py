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

# O'zimizning fayllar (config va db mavjud deb hisoblaymiz)
from config import BotConfig, Settings, Prices, DataLists, Texts, UserbotConfig
from db import db

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# =====================================================================
# BOT VA DISPATCHER SOZLAMALARI (Aiogram 3.7+ standarti)
# =====================================================================
bot = Bot(
    token=BotConfig.BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)
)
dp = Dispatcher()
router = Router()
dp.include_router(router)

# Global Userbot obyekti
userbot_client: TelegramClient = None


# =====================================================================
# FSM HOLATLARI (State Machine) - HAMMASI TO'LIQ QO'SHILDI
# =====================================================================
class RegStates(StatesGroup):
    waiting_phone = State()


class AdStates(StatesGroup):
    choosing_cat_count = State()
    choosing_tariff = State()
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

    yordam_media = State()
    yordam_address = State()
    yordam_phone = State()
    yordam_preview = State()


class AdminStates(StatesGroup):
    add_card_number = State()
    add_card_holder = State()
    broadcast_text = State()
    add_score_batch = State()
    decline_reason = State()
    set_konkurs_media = State()
    set_konkurs_text = State()
    set_mukofot_media = State()
    set_mukofot_text = State()
    topup_amount = State()  # <--- QO'SHILDI (Xato tuzatildi)
    topup_receipt = State()  # <--- QO'SHILDI (Xato tuzatildi)


# =====================================================================
# YORDAMCHI FUNKSIYALAR (Keyboards)
# =====================================================================

def get_main_menu_kb(is_admin=False):
    kb = [
        [InlineKeyboardButton(text="📢 Kanalga reklama bermoqchiman", callback_data="menu_reklama")],
        [InlineKeyboardButton(text="🏆 Konkursda ishtirok etmoqchiman", callback_data="menu_konkurs")],
        [InlineKeyboardButton(text="💳 Hisobni to'ldirish", callback_data="menu_topup")],
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
        [InlineKeyboardButton(text="💍 Mushukgimni Viyazkaga(kupaytirish uchun elon)", callback_data="adtype_vyazka")],
        [InlineKeyboardButton(text="🚑 Mushukgim kasal tekinga bermoqchian", callback_data="menu_yordam")],
        [InlineKeyboardButton(text="💰 Narxlar bilan tanishib chiqmoqchiman", callback_data="menu_narx")],
        [InlineKeyboardButton(text="↩️ Asosiy menyuga qaytish", callback_data="adtype_back")]
    ])


def get_cat_count_kb():
    kb = []
    for i in range(1, 6):
        kb.append([InlineKeyboardButton(text=f"{i} ta mushuk", callback_data=f"catcount_{i}")])
    kb.append([InlineKeyboardButton(text="+5 ta mushuk", callback_data="catcount_6")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def get_tariffs_kb(cat_count: int):
    count = cat_count if cat_count <= 5 else 5
    p_web = Prices.TARIFF_WEB[count]
    p_chan = Prices.TARIFF_CHANNEL[count]
    p_both = Prices.TARIFF_BOTH[count]

    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🖥️ Web App (1 hafta) - {p_web:,} so'm",
                              callback_data=f"tariff_web_only_{cat_count}")],
        [InlineKeyboardButton(text=f"📢 Kanal - {p_chan:,} so'm", callback_data=f"tariff_channel_only_{cat_count}")],
        [InlineKeyboardButton(text=f"🖥️+📢 Web & Kanal - {p_both:,} so'm",
                              callback_data=f"tariff_web_and_channel_{cat_count}")],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="adtype_back")]
    ])


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
    if page > 0: nav.append(InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"breed_page_{page - 1}"))
    if page < len(DataLists.BREEDS) - 1: nav.append(
        InlineKeyboardButton(text="Boshqa ➡️", callback_data=f"breed_page_{page + 1}"))
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
        [InlineKeyboardButton(text="Sog'lom", callback_data="health_soglom"),
         InlineKeyboardButton(text="Kasal", callback_data="health_kasal")]
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
        [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="preview_confirm"),
         InlineKeyboardButton(text="↩️ Orqaga", callback_data="preview_back")]
    ])


# =====================================================================
# YANGI QO'SHILGAN QISM: KANAL POSTI UCHUN TUGMA
# =====================================================================
def get_channel_post_kb():
    """Har bir kanal postining tagiga qo'shiladigan 'Hadiya Kanal' tugmasi."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Hadiya Kanal", url="https://t.me/uzbek_cats_hadiya")]
    ])


# =====================================================================
# USERBOT LOGIKASI (CardXabarBot ni tinglash)
# =====================================================================
async def start_userbot(session_string: str):
    global userbot_client
    try:
        if userbot_client and userbot_client.is_connected():
            await userbot_client.disconnect()

        userbot_client = TelegramClient(StringSession(session_string), api_id=6,
                                        api_hash="eb06d4abfb49dc3eeb1aeb98ae0f581e")
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
                        await bot.send_message(user_id,
                                               f"✅ *To'lov tasdiqlandi!*\n\nHisobingizga {amount:,} so'm qo'shildi.")
                    except:
                        pass
                else:
                    logger.warning(f"⚠️ To'lov topilmadi yoki muddati o'tgan: {amount} UZS, {card_last4}")

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
    args = message.text.split()

    user = await db.get_user(user_id)
    if user:
        await message.answer(Texts.MAIN_MENU, reply_markup=get_main_menu_kb(user_id in BotConfig.ADMIN_IDS))
        return

    ref_code = None
    if len(args) > 1:
        ref_code = args[1]
        await state.update_data(ref_code=ref_code)

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

    data = await state.get_data()
    ref_code = data.get('ref_code')

    full_name = f"{message.from_user.first_name} {message.from_user.last_name or ''}".strip()
    username = f"@{message.from_user.username}" if message.from_user.username else "Noma'lum"

    user = await db.create_user(
        user_id=message.from_user.id,
        username=username,
        full_name=full_name,
        phone=phone,
        referral_code=ref_code
    )

    admin_text = (
        f"🆕 *#{user['user_number']} FOYDALANUVCHI RO'YXATDAN O'TTI*\n\n"
        f"👤 *Ism-familiya:* {full_name}\n"
        f"🔗 *Telegram:* {username}\n"
        f"📞 *Telefon raqam:* {phone}\n"
        f"🆔 *Telegram ID:* {message.from_user.id}\n"
        f"🏆 *Boshlang'ich ball:* 10\n"
        f"⏰ *Ro'yxatdan o'tgan vaqt:* {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
    )
    try:
        await bot.send_message(BotConfig.TECH_ADMIN_ID, admin_text)
    except:
        pass

    text = Texts.REG_SUCCESS.format(
        user_number=user['user_number'],
        score=user['score'],
        referrals=0
    )
    await message.answer(text, reply_markup=ReplyKeyboardRemove())
    await message.answer(Texts.MAIN_MENU, reply_markup=get_main_menu_kb())
    await state.clear()


# =====================================================================
# 2. ASOSIY MENYU VA NAVIGATSIYA
# =====================================================================
@router.callback_query(F.data == "menu_back_to_main")
async def back_to_main(call: CallbackQuery):
    user_id = call.from_user.id
    await call.message.edit_text(Texts.MAIN_MENU, reply_markup=get_main_menu_kb(user_id in BotConfig.ADMIN_IDS))


@router.callback_query(F.data == "menu_reklama")
async def menu_reklama(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text(Texts.AD_TYPE_SELECT, reply_markup=get_ad_type_kb())
    await state.clear()


@router.callback_query(F.data == "menu_narx")
async def show_prices(call: CallbackQuery):
    text = (
        "💰 *REKLAMA NARXLARI*\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🖥️ *1-TARIF (Web App faqat)*\n"
        f"1 ta - {Prices.TARIFF_WEB[1]:,} so'm\n"
        f"2 ta - {Prices.TARIFF_WEB[2]:,} so'm\n"
        f"3 ta - {Prices.TARIFF_WEB[3]:,} so'm\n"
        f"4 ta - {Prices.TARIFF_WEB[4]:,} so'm\n"
        f"5 ta - {Prices.TARIFF_WEB[5]:,} so'm\n\n"
        "📢 *2-TARIF (Kanal faqat)*\n"
        f"1 ta - {Prices.TARIFF_CHANNEL[1]:,} so'm\n"
        f"2 ta - {Prices.TARIFF_CHANNEL[2]:,} so'm\n"
        f"3 ta - {Prices.TARIFF_CHANNEL[3]:,} so'm\n"
        f"4 ta - {Prices.TARIFF_CHANNEL[4]:,} so'm\n"
        f"5 ta - {Prices.TARIFF_CHANNEL[5]:,} so'm\n\n"
        "🖥️+📢 *3-TARIF (Web & Kanal)*\n"
        f"1 ta - {Prices.TARIFF_BOTH[1]:,} so'm\n"
        f"2 ta - {Prices.TARIFF_BOTH[2]:,} so'm\n"
        f"3 ta - {Prices.TARIFF_BOTH[3]:,} so'm\n"
        f"4 ta - {Prices.TARIFF_BOTH[4]:,} so'm\n"
        f"5 ta - {Prices.TARIFF_BOTH[5]:,} so'm\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🎁 Hadiya, Vyazka va Yordam e'lonlari *BEPUL*.\n\n"
        "💳 To'lov balans orqali amalga oshiriladi."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="↩️ Orqaga", callback_data="menu_reklama")]])
    await call.message.edit_text(text, reply_markup=kb)


# =====================================================================
# 3. REKLAMA BERISH (SOTISH, HADIYA, VYAZKA)
# =====================================================================
@router.callback_query(F.data.startswith("adtype_"))
async def choose_ad_type(call: CallbackQuery, state: FSMContext):
    ad_type = call.data.replace("adtype_", "")
    if ad_type == "back":
        await back_to_main(call)
        return

    await state.update_data(ad_type=ad_type)

    if ad_type == "sotish":
        text = "🐱 Mushuklaringizni nechta sotmoqchisiz?"
        await call.message.edit_text(text, reply_markup=get_cat_count_kb())
        await state.set_state(AdStates.choosing_cat_count)
    else:
        if ad_type == "vyazka":
            diniy_matn = (
                "Ассалому алайкум! Мени мушугим зотли. Бирон бир зотли мушукка чатиштиришга берсам ёки қўштирганимга пул олсам бўладими?\n\n"
                "«Зикр аҳлидан сўранг» ҳайъати:\n– Ва алайкум ассалом! Ҳалол эмас.\n\n"
                "Ибн Умар розияллоҳу анҳумодан ривоят қилинади: «Набий соллаллоҳу алайҳи васаллам эркак ҳайвоннинг қочириши (учун ҳақ олиш)дан наҳий қилдилар».\n\n"
                "Демак, мазкур нотўғри йўл билан мол касб қилиш ҳам жоиз эмас. Валлоҳу аълам!"
            )
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Ko'rib chiqdim, davom etish", callback_data="vyazka_confirm")]])
            await call.message.edit_text(diniy_matn, reply_markup=kb)
        else:
            await call.message.edit_text("📸 Qanday media yuboraysiz?", reply_markup=get_media_type_kb())
            await state.set_state(AdStates.choosing_media_type)


@router.callback_query(F.data == "vyazka_confirm")
async def vyazka_confirm(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("📸 Qanday media yuboraysiz?", reply_markup=get_media_type_kb())
    await state.set_state(AdStates.choosing_media_type)


@router.callback_query(AdStates.choosing_cat_count, F.data.startswith("catcount_"))
async def process_cat_count(call: CallbackQuery, state: FSMContext):
    count = int(call.data.split("_")[1])
    await state.update_data(cat_count=count)

    text = Texts.TARIFF_SELECT_TEXT.format(cat_count=count)
    await call.message.edit_text(text, reply_markup=get_tariffs_kb(count))
    await state.set_state(AdStates.choosing_tariff)


@router.callback_query(AdStates.choosing_tariff, F.data.startswith("tariff_"))
async def process_tariff(call: CallbackQuery, state: FSMContext):
    parts = call.data.split("_")
    tariff_type = "_".join(parts[1:-1])
    cat_count = int(parts[-1])

    user_id = call.from_user.id
    user = await db.get_user(user_id)

    count_idx = cat_count if cat_count <= 5 else 5
    price = 0
    if tariff_type == "web_only":
        price = Prices.TARIFF_WEB[count_idx]
    elif tariff_type == "channel_only":
        price = Prices.TARIFF_CHANNEL[count_idx]
    elif tariff_type == "web_and_channel":
        price = Prices.TARIFF_BOTH[count_idx]

    if user['balance'] < price:
        text = (
            f"❌ *Hisobingizda mablag' yetarli emas!*\n\n"
            f"Kerakli summa: *{price:,} so'm*\n"
            f"Sizning balansingiz: *{user['balance']:,} so'm*\n\n"
            f"Iltimos, hisobingizni to'ldiring."
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Hisobni to'ldirish", callback_data="menu_topup")],
            [InlineKeyboardButton(text="↩️ Orqaga", callback_data="menu_reklama")]
        ])
        await call.message.edit_text(text, reply_markup=kb)
        return

    await state.update_data(tariff=tariff_type, price=price)

    await call.message.edit_text("📸 Qanday media yuboraysiz?", reply_markup=get_media_type_kb())
    await state.set_state(AdStates.choosing_media_type)


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
        await message.answer("❌ Maksimum 3 ta rasm yuklashingiz mumkin. 'Davom etish' tugmasini bosing.")
        return

    file_id = message.photo[-1].file_id
    photos.append(file_id)
    await state.update_data(photos=photos)

    if len(photos) < 3:
        await message.answer(f"✅ {len(photos)}-rasm qabul qilindi. Yana yuborishingiz yoki davom etishingiz mumkin.")
    else:
        await message.answer("✅ 3 ta rasm qabul qilindi.", reply_markup=get_continue_kb())


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


@router.callback_query(AdStates.choosing_breed,
                       F.data.startswith("breed_") & ~F.data.startswith("breed_page_") & ~F.data.startswith(
                           "breed_custom"))
async def process_breed(call: CallbackQuery, state: FSMContext):
    parts = call.data.split("_")
    page = int(parts[1])
    idx = int(parts[2])
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

    await call.message.edit_text("📞 Endi telefon raqamingizni yuboring: (masalan +998 90 123 45 67)")
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
    ad_type = data.get('ad_type')

    if ad_type == "hadiya":
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

    caption += f"🐱 Zot: {data.get('breed', '—')}\n"
    caption += f"🎂 Yosh: {data.get('age', '—')}\n"
    caption += f"👤 Jins: {data.get('gender', '—')}\n"
    caption += f"❤️ Sog'lig'i: {data.get('health', '—')}\n"
    caption += f"🧬 Nasl olish: {data.get('sterilization', '—')}\n\n"

    if data.get('ad_type') == 'sotish':
        caption += f"💳 Tarif: {data.get('tariff')} | Narxi: {data.get('price', 0):,} so'm\n\n"

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


@router.callback_query(AdStates.preview, F.data == "preview_confirm")
async def confirm_ad(call: CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    data = await state.get_data()
    ad_type = data.get('ad_type')

    user = await db.get_user(user_id)

    if ad_type == "sotish":
        tariff_price = data.get('price')
        if user['balance'] < tariff_price:
            await call.message.edit_text("❌ Hisobingizda mablag' yetarli emas! Iltimos, qaytadan urinib ko'ring.")
            return
        try:
            await db.update_user_balance(user_id, tariff_price, operation='subtract')
        except ValueError:
            await call.message.edit_text("❌ Balansni yechishda xatolik!")
            return

    new_ad = await db.create_ad(
        user_id=user_id,
        ad_type=ad_type,
        tariff=data.get('tariff', 'none'),
        photos=data.get('photos', []),
        breed=data.get('breed'),
        age=data.get('age'),
        gender=data.get('gender'),
        health=data.get('health'),
        sterilization=data.get('sterilization'),
        address=data.get('address'),
        phone=data.get('phone'),
        price=data.get('ad_price', data.get('price', '0')),
        currency=data.get('currency', 'so''m'),
        ad_number=user['ad_count'] + 1
    )

    await call.message.edit_text("✅ E'loningiz qabul qilindi va Texnik Admin tekshiruviga yuborildi!")

    admin_caption = (
        f"🆕 *YANGI REKLAMA!*\n\n"
        f"👤 Foydalanuvchi: #{user['user_number']} ({user['username']})\n"
        f"📋 Turi: {ad_type.upper()}\n"
        f"💳 Tarif: {data.get('tariff', 'Bepul')}\n"
        f"🐱 Zot: {data.get('breed')}\n"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"admin_approve_ad_{new_ad['id']}"),
         InlineKeyboardButton(text="❌ Rad etish", callback_data=f"admin_decline_ad_{new_ad['id']}")]
    ])

    photos = data.get('photos', [])
    if photos:
        await bot.send_photo(BotConfig.TECH_ADMIN_ID, photo=photos[0], caption=admin_caption, reply_markup=kb)
    else:
        await bot.send_message(BotConfig.TECH_ADMIN_ID, admin_caption, reply_markup=kb)

    await state.clear()


# =====================================================================
# 4. TO'LOV (HISOB TO'LDIRISH) TIZIMI (YANGI STATE BILAN)
# =====================================================================
@router.callback_query(F.data == "menu_topup")
async def start_topup(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text(Texts.TOPUP_ASK_AMOUNT)
    await state.set_state(AdminStates.topup_amount)  # TO'G'RILANDI


@router.message(AdminStates.topup_amount)
async def process_topup_amount(message: Message, state: FSMContext):
    if not message.text.isdigit() or int(message.text) < 1000:
        await message.answer("❌ Iltimos, kamida 1000 so'm kiriting (faqat raqam):")
        return

    amount = int(message.text)
    card = await db.get_active_card()

    if not card:
        await message.answer("❌ Hozircha to'lov kartasi mavjud emas. Admin bilan bog'laning.")
        await state.clear()
        return

    card_last4 = card['number'][-4:]
    payment_id = await db.create_payment_request(message.from_user.id, amount, card['id'], card_last4)

    text = Texts.TOPUP_INSTRUCTIONS.format(
        card_number=card['number'],
        card_holder=card['holder'],
        amount=f"{amount:,}",
        minutes=Settings.TOPUP_TIMER_MINUTES
    )
    await message.answer(text)
    await state.set_state(AdminStates.topup_receipt)  # TO'G'RILANDI


@router.message(F.photo, AdminStates.topup_receipt)
async def process_receipt(message: Message, state: FSMContext):
    file_id = message.photo[-1].file_id

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"admin_confirm_payment_{message.from_user.id}")]
    ])
    await bot.send_photo(BotConfig.ADMIN_ID, photo=file_id,
                         caption=f"💳 Yangi to'lov cheki!\nUser: {message.from_user.id}", reply_markup=kb)
    await message.answer("✅ Chek qabul qilindi. Admin tekshirib, hisobingizni to'ldiradi.")
    await state.clear()


# =====================================================================
# 5. ADMIN VA TEXNIK ADMIN PANELLARI
# =====================================================================
@router.callback_query(F.data == "admin_panel")
async def admin_panel(call: CallbackQuery):
    if call.from_user.id not in BotConfig.ADMIN_IDS: return

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
        [InlineKeyboardButton(text="💳 Karta qo'shish", callback_data="admin_add_card")],
        [InlineKeyboardButton(text="📢 Broadcast", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="↩️ Orqaga", callback_data="menu_back_to_main")]
    ])
    await call.message.edit_text(text, reply_markup=kb)


@router.callback_query(F.data == "admin_add_card")
async def admin_add_card(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("💳 Karta raqamini kiriting (16 xonali):")
    await state.set_state(AdminStates.add_card_number)


@router.message(AdminStates.add_card_number)
async def process_card_num(message: Message, state: FSMContext):
    if not message.text.isdigit() or len(message.text) != 16:
        await message.answer("❌ 16 xonali raqam kiriting:")
        return
    await state.update_data(card_number=message.text)
    await message.answer("👤 Karta egasining ismini kiriting:")
    await state.set_state(AdminStates.add_card_holder)


@router.message(AdminStates.add_card_holder)
async def process_card_holder(message: Message, state: FSMContext):
    data = await state.get_data()
    await db.add_card(data['card_number'], message.text)
    await message.answer("✅ Karta muvaffaqiyatli qo'shildi!")
    await state.clear()


# =====================================================================
# 6. TEXNIK ADMIN - REKLAMALARNI TASDIQLASH VA KANALGA POST QILISH
# =====================================================================
@router.callback_query(F.data.startswith("admin_approve_ad_"))
async def tech_admin_approve(call: CallbackQuery):
    if call.from_user.id != BotConfig.TECH_ADMIN_ID: return

    ad_id = int(call.data.split("_")[3])

    await db.update_ad_status(ad_id, "approved")

    # Bazadan reklama ma'lumotlarini olish (db.py da get_ad_by_id funksiyasi bo'lishi shart)
    # Agar db.py da bo'lmasa, to'g'ridan-to'g'ri SQL query ishlatamiz:
    async with db.pool.acquire() as conn:
        ad_data = await conn.fetchrow("SELECT * FROM ads WHERE id = $1", ad_id)

    if ad_data:
        await post_to_channel_with_button(dict(ad_data))

    await call.message.edit_caption(caption=call.message.caption + "\n\n✅ TASDIQLANDI")
    await call.answer("Tasdiqlandi va kanalga yuborildi!")


async def post_to_channel_with_button(ad):
    """Kanalga post yuborish va tagiga 'Hadiya Kanal' tugmasini qo'shish."""
    # Caption yasash (Soddalashtirilgan)
    caption = f"🐱 Zot: {ad['breed']}\n📍 Manzil: {ad['address']}\n📞 Tel: {ad['phone']}\n💰 Narx: {ad['price']} {ad['currency']}"

    # Rasm massivini olish (JSONB dan list ga o'tkazish)
    import json
    photos = ad.get('photos', [])
    if isinstance(photos, str):
        try:
            photos = json.loads(photos)
        except:
            photos = []

    kb = get_channel_post_kb()  # Hadiya kanal tugmasi

    try:
        if len(photos) == 1:
            await bot.send_photo(
                chat_id=BotConfig.CHANNEL_ID,
                photo=photos[0],
                caption=caption,
                reply_markup=kb
            )
        elif len(photos) > 1:
            media = [InputMediaPhoto(media=p, caption=caption if i == 0 else None) for i, p in enumerate(photos)]
            await bot.send_media_group(chat_id=BotConfig.CHANNEL_ID, media=media)

            # Telegram albom ostiga tugma qo'ymaydi, shuning uchun alohida xabar yuboramiz
            await bot.send_message(
                chat_id=BotConfig.CHANNEL_ID,
                text="👇 Batafsil ma'lumot uchun",
                reply_markup=kb
            )
        else:
            await bot.send_message(BotConfig.CHANNEL_ID, text=caption, reply_markup=kb)

    except Exception as e:
        logger.error(f"Kanalga post yuborishda xatolik: {e}")


# =====================================================================
# 7. GURUH MODERATSIYASI (BANNED WORDS)
# =====================================================================
@dp.message(F.chat.type.in_({"group", "supergroup"}))
async def group_moderator(message: Message):
    if not message.text and not message.caption: return

    text = (message.text or message.caption).lower()

    for word in DataLists.BANNED_WORDS:
        if word in text:
            try:
                await message.delete()
                await message.answer(f"❌ {message.from_user.first_name}, reklama tarqatmang!")
            except:
                pass
            return

    if "http://" in text or "https://" in text or "t.me/" in text:
        try:
            await message.delete()
            await message.answer(f"❌ {message.from_user.first_name}, havola tarqatmang!")
        except:
            pass


# =====================================================================
# ISHGA TUSHIRISH (MAIN)
# =====================================================================
async def main():
    logger.info("🚀 Bot ishga tushmoqda...")

    await db.connect()

    try:
        async with db.pool.acquire() as conn:
            session = await conn.fetchval("SELECT session_string FROM userbot_sessions WHERE is_active = TRUE LIMIT 1")
            if session:
                asyncio.create_task(start_userbot(session))
    except Exception as e:
        logger.warning(f"Userbotni yuklashda xatolik: {e}")

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