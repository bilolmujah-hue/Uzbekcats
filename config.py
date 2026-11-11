# ==============================================================================
# LOYIHA: UzbekCats Bot & Web App
# FAYL: config.py
# TAVSIF: Barcha sozlamalar, matnlar, narxlar, ro'yxatlar — TO'LIQ MUKAMMAL VERSIYA
# ==============================================================================

import os
import copy


# ==============================================================================
# ENV YORDAMCHI FUNKSIYALAR
# ==============================================================================

def _env(key: str, default: str = "") -> str:
    val = os.getenv(key)
    return val if val else default


def _env_int(key: str, default: int) -> int:
    try:
        val = os.getenv(key)
        return int(val) if val else default
    except (ValueError, TypeError):
        return default


def _env_bool(key: str, default: bool = False) -> bool:
    val = os.getenv(key)
    if not val:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on", "ha")


# ==============================================================================
# 1. ASOSIY SOZLAMALAR
# ==============================================================================

class BotConfig:
    # --- Bot ---
    BOT_TOKEN: str = _env("BOT_TOKEN", "8577521489:AAGbp2MvcMXZlnK-KbDdmPm8WArYlJ4PxWk")
    BOT_USERNAME: str = _env("BOT_USERNAME", "@Uzbek_cat_bot")
    BOT_LINK: str = _env("BOT_LINK", "https://t.me/Uzbek_cat_bot")

    # --- Adminlar ---
    ADMIN_ID: int = _env_int("ADMIN_ID", 673018191)
    TECH_ADMIN_ID: int = _env_int("TECH_ADMIN_ID", 7038296036)
    ADMIN_IDS: tuple = (ADMIN_ID, TECH_ADMIN_ID)

    # --- Kanallar ---
    CHANNEL_SOTISH_ID: int = _env_int("CHANNEL_SOTISH_ID", -1001532366057)
    CHANNEL_HADIYA_ID: int = _env_int("CHANNEL_HADIYA_ID", -1003815754371)

    CHANNEL_SOTISH_USERNAME: str = _env("CHANNEL_SOTISH_USERNAME", "@uzbek_cats")
    CHANNEL_HADIYA_USERNAME: str = _env("CHANNEL_HADIYA_USERNAME", "@uzbek_cats_hadiya")

    CHANNEL_SOTISH_LINK: str = _env("CHANNEL_SOTISH_LINK", "https://t.me/uzbek_cats")
    CHANNEL_HADIYA_LINK: str = _env("CHANNEL_HADIYA_LINK", "https://t.me/uzbek_cats_hadiya")

    CHANNELS: dict = {
        "sotish": {
            "id": CHANNEL_SOTISH_ID,
            "username": CHANNEL_SOTISH_USERNAME,
            "link": CHANNEL_SOTISH_LINK,
            "title": "Sotish kanali",
        },
        "hadiya": {
            "id": CHANNEL_HADIYA_ID,
            "username": CHANNEL_HADIYA_USERNAME,
            "link": CHANNEL_HADIYA_LINK,
            "title": "Hadiya kanali",
        },
    }

    # Eski kod uchun (orqaga moslik)
    CHANNEL_ID: int = CHANNEL_SOTISH_ID
    CHANNEL_USERNAME: str = CHANNEL_SOTISH_USERNAME

    # --- Database ---
    DATABASE_URL: str = _env(
        "DATABASE_URL",
        "postgresql://postgres:password@localhost:5432/uzbekcats_db",
    )

    # --- Web App ---
    WEB_APP_URL: str = _env("WEB_APP_URL", "https://bilolmujah-hue.github.io/Uzbekcats/")
    API_BASE_URL: str = _env("API_BASE_URL", "https://uzbekcats-production.up.railway.app")


class Settings:
    WEB_AD_DAYS: int = _env_int("WEB_AD_DAYS", 7)
    TOPUP_TIMER_MINUTES: int = _env_int("TOPUP_TIMER_MINUTES", 10)
    TECH_ADMIN_PERCENT: int = _env_int("TECH_ADMIN_PERCENT", 10)
    BOT_ENABLED: bool = _env_bool("BOT_ENABLED", True)
    MIN_TOPUP_AMOUNT: int = _env_int("MIN_TOPUP_AMOUNT", 1000)
    MAX_PHOTOS: int = _env_int("MAX_PHOTOS", 3)
    MIN_PHOTOS: int = _env_int("MIN_PHOTOS", 1)
    REQUIRE_SUBSCRIPTION: bool = _env_bool("REQUIRE_SUBSCRIPTION", True)


# ==============================================================================
# 2. NARXLAR (TARIFLAR)
# ==============================================================================

class Prices:
    # 1-TARIF: Web App faqat
    TARIFF_WEB: dict = {1: 10000, 2: 18000, 3: 25000, 4: 31000, 5: 38000}
    # 2-TARIF: Kanal faqat
    TARIFF_CHANNEL: dict = {1: 25000, 2: 45000, 3: 65000, 4: 85000, 5: 105000}
    # 3-TARIF: Web App + Kanal
    TARIFF_BOTH: dict = {1: 32000, 2: 50000, 3: 75000, 4: 95000, 5: 115000}
    # Bot orqali joylash (faqat kanalga tushadi)
    BOT_PRICES: dict = {1: 25000, 2: 45000, 3: 65000, 4: 85000, 5: 105000}

    @classmethod
    def get_bot_price(cls, cat_count: int) -> int:
        try:
            n = int(cat_count)
        except (ValueError, TypeError):
            n = 1
        return cls.BOT_PRICES.get(max(1, min(5, n)), 25000)


# ==============================================================================
# 3. RO'YXATLAR
# ==============================================================================

class DataLists:
    # O'zbekistonning barcha viloyatlari va shaharlari
    VILOYATLAR: list = [
        "Toshkent shahar", "Toshkent viloyati", "Andijon", "Buxoro", 
        "Farg'ona", "Jizzax", "Xorazm", "Namangan", "Navoiy", 
        "Qashqadaryo", "Samarqand", "Sirdaryo", "Surxondaryo", "Qoraqalpog'iston"
    ]

    # Mushuk yoshlari (Siz so'raganidek to'liq)
    AGES: list = [
        "1 oylik", "2 oylik", "3 oylik", "4 oylik", "5 oylik",
        "6 oylik", "7 oylik", "8 oylik", "9 oylik", "10 oylik",
        "11 oylik", "1 yosh", "1,5 yosh", "2 yosh", "2,5 yosh",
        "3 yosh", "3,5 yosh", "4 yosh", "4,5 yosh", "5 yosh",
        "6 yosh", "7 yosh", "8 yosh", "9 yosh", "10 yosh"
    ]

    # Mushuk zotlari (Bitta katta ro'yxat, Web App va Botda ishlatish oson)
    BREEDS: list = [
        "Scottish fold", "Scottish straight", "British blue", "British chinchilla",
        "Bengal cat", "Turkish angora", "Scottish chinchila", "Gibrid", 
        "British Shorthair", "British Longhair", "Persian Cat", "Maine Coon", 
        "Ragdoll", "Siberian Cat", "Russian blue", "Abyssinian", 
        "Norwegian Forest Cat", "Turkish Van", "Burmilla", "American Shorthair", 
        "American Curl", "Egyptian Mau", "Tonkinese", "Balinese", 
        "Exotic Shorthair", "Savannah Cat", "Munchkin", "Khao Manee", 
        "Uy mushuki", "Boshqa"
    ]

    BANNED_WORDS: set = {
        "mushuk sotiladi", "mushuk bor", "sotaman", "sotiladi", "mushu bor", "muwu bor", "muwu bo",
        "Mushuk bor", "sotuvda", "arzonga mushuk", "hadiyaga", "mendayam bor", "atrofida bor",
        "sotman", "kimga mushuk kerak", "Mandayam bor", "beramiz", "beraman", "сотаман",
        "мушук бор", "бор", "бера", "hadyaga", "кимга мушук керак", "мушук сотилади",
    }


# ==============================================================================
# 4. MATNLAR
# ==============================================================================

class Texts:
    # --- Umumiy ---
    WARNING_BANNED_WORD = "❌ Iltimos, reklama tarqatmang!"
    BOT_DISABLED = (
        "❌ Bot hozirda ishlamayapti. Iltimos, keyinroq urinib ko'ring.\n"
        "Agar reklama bermoqchi bo'lsangiz, adminga murojaat qiling: @It_project_2026"
    )
    USER_BANNED = "❌ Siz botdan foydalanish huquqidan mahrum qilingansiz!"

    # --- Majburiy obuna ---
    SUB_REQUIRED_TEXT = (
        "👋 <b>Assalomu alaykum!</b>\n\n"
        "Botdan foydalanish uchun quyidagi <b>2 ta kanalga</b> obuna bo'ling:\n\n"
        "{sotish_icon} <b>Sotish kanali</b> — @uzbek_cats\n"
        "{hadiya_icon} <b>Hadiya kanali</b> — @uzbek_cats_hadiya\n\n"
        "{footer}"
    )
    SUB_CONFIRMED_TEXT = "✅ <b>Barcha kanallarga obuna bo'lgansiz!</b>\n«Davom etish» tugmasini bosing."
    SUB_MISSING_HINT = "Obuna bo'lgach, <b>«🔄 Tekshirish»</b> tugmasini bosing."
    SUB_OK_ALERT = "✅ Barcha kanallarga obuna bo'lgansiz!"
    SUB_MISSING_ALERT = "❌ Hali obuna bo'lmagan: {missing}"

    # --- Ro'yxatdan o'tish ---
    START_TEXT = (
        "📱 <b>Assalomu alaykum! Uzbek Cats botiga xush kelibsiz!</b>\n\n"
        "Botdan foydalanish uchun telefon raqamingizni yuboring:\n\n"
        "Pastdagi <b>«📞 Raqamni yuborish»</b> tugmasini bosing yoki telefon raqamingizni kiriting."
    )
    ASK_PHONE = "❌ Iltimos, to'g'ri telefon raqam kiriting yoki «📞 Raqamni yuborish» tugmasini bosing."
    REG_SUCCESS = (
        "✅ Ro'yxatdan muvaffaqiyatli o'tdingiz!\n"
        "🔢 Sizning raqamingiz: #{user_number}\n"
        "🏆 Ballaringiz: {score}\n"
        "👥 Takliflaringiz: {referrals} kishi"
    )
    PHONE_TAKEN = "❌ Bu telefon raqam boshqa foydalanuvchiga tegishli!"

    # --- Asosiy menyu ---
    MAIN_MENU = "🏠 <b>Asosiy menyu</b>\n\nQuyidagi imkoniyatlardan foydalaning:"
    
    # --- Reklama ---
    AD_TYPE_SELECT = "🎯 <b>Qanday turdagi e'lon joylashtirmoqchisiz?</b>"
    MEDIA_ASK = "📸 <b>Qanday media yuboraysiz?</b>"
    PHOTOS_ASK = "🖼️ <b>Mushuk rasmlarini yuboring (1–3 ta):</b>"
    PHOTOS_LIMIT = "❌ Maksimum 3 ta rasm. «Davom etish» tugmasini bosing."
    PHOTOS_MIN = "❌ Kamida 1 ta rasm yuboring!"
    BREED_ASK = "🐱 <b>Zotni tanlang:</b>"
    BREED_CUSTOM_ASK = "✏️ <b>Zotni yozing:</b>"
    AGE_ASK = "🎂 <b>Yoshini tanlang:</b>"
    HEALTH_ASK = "❤️ <b>Sog'lig'ini tanlang:</b>"
    GENDER_ASK = "👤 <b>Jinsini tanlang:</b>"
    STERILIZATION_ASK = "🧬 <b>Nasl olish mumkinmi?</b>"
    ADDRESS_ASK = "📍 <b>Manzilingizni tanlang:</b>"
    AD_PHONE_ASK = "📞 <b>Telefon raqam (masalan +998901234567):</b>"
    AD_PHONE_INVALID = "❌ Format xato. Qaytadan (+998901234567):"
    CURRENCY_ASK = "💰 <b>Valyutani tanlang:</b>"
    PRICE_ASK = "💰 <b>Narxni kiriting (faqat raqamda):</b>"
    PRICE_INVALID = "❌ Faqat raqam kiriting:"
    PREVIEW_HEADER = "📋 <b>Tekshirib oling:</b>\n\n"
    AD_ACCEPTED = "✅ <b>E'loningiz qabul qilindi va Texnik Admin tekshiruviga yuborildi!</b>"
    AD_APPROVED_ALERT = "✅ Kanalga yuborildi!"
    AD_REJECTED = "✅ Reklama rad etildi."
    AD_REJECT_REASON_ASK = "Rad etish sababini yozing:"
    NO_ADS = "📭 Sizda hali e'lonlar mavjud emas."
    MY_ADS_HEADER = "📋 <b>Sizning e'lonlaringiz:</b>\n\n"

    # --- Xatoliklar ---
    ERROR_INSUFFICIENT_BALANCE = (
        "❌ <b>Balansda mablag' yetarli emas!</b>\n\n"
        "Kerakli: <b>{price:,} so'm</b>\nSizda: <b>{balance:,} so'm</b>"
    )
    ERROR_BALANCE_SUBTRACT = "Mablag' yechishda xatolik (balans yetarli emas)."
    ERROR_AD_NOT_FOUND = "❌ Reklama topilmadi!"
    ERROR_NO_PERMISSION = "Ruxsat yo'q"
    ERROR_UNKNOWN = "❌ Xatolik: {err}"

    # --- Admin ---
    ADMIN_PANEL_WELCOME = "👨‍💼 <b>Admin Paneliga xush kelibsiz!</b>\n\nQuyidagilardan birini tanlang:"
    TECH_ADMIN_PANEL_WELCOME = "👨‍💻 <b>Texnik Admin Paneli</b>\n\nQuyidagilardan birini tanlang:"
    NOT_ADMIN = "Siz admin emassiz!"
    NOT_TECH_ADMIN = "Siz texnik admin emassiz!"
    BOT_ENABLED_ALERT = "✅ Bot yoqildi!"
    BOT_DISABLED_ALERT = "🔴 Bot o'chirildi!"

    # --- YANGI TO'LOV TIZIMI (TOPUP) MATNLARI ---
    TOPUP_MENU = (
        "💳 <b>Hisobni to'ldirish</b>\n\n"
        "Qaysi usulda to'lov qilmoqchisiz?"
    )
    TOPUP_WEBAPP_BTN = "🌐 Web App orqali to'lash"
    TOPUP_ADMIN_BTN = "💳 Admin tasdiqlashi orqali"
    
    TOPUP_ASK_AMOUNT = (
        "💳 <b>Hisobni to'ldirish</b>\n\n"
        "Qancha miqdorda pul tashlamoqchisiz?\n"
        "Iltimos, summani raqamda kiriting (masalan: 20000):"
    )
    TOPUP_MIN_AMOUNT = "❌ Minimal to'lov {min_amount:,} so'm"
    TOPUP_NO_CARD = "❌ To'lov kartasi mavjud emas. Admin bilan bog'laning."
    
    TOPUP_INSTRUCTIONS = (
        "💳 <b>To'lov ma'lumotlari:</b>\n\n"
        "Karta raqami: <code>{card_number}</code>\n"
        "Karta egasi: {card_holder}\n"
        "Summa: <b>{amount:,} so'm</b>\n\n"
        "⏳ Ushbu to'lov uchun sizga <b>{minutes} daqiqa</b> vaqt berildi.\n"
        "Iltimos, shu vaqt ichida kartaga pul o'tkazing va chekni rasmga olib, shu yerga yuboring!\n\n"
        "👇 <i>Chekni yuboring:</i>"
    )
    
    TOPUP_ADMIN_RECEIPT_ACCEPTED = (
        "✅ <b>Chek qabul qilindi!</b>\n\n"
        "Iltimos, biroz kuting. Texnik admin to'lovni tekshirib, tasdiqlaydi.\n\n"
        "👨‍💻 Admin: @It_project_2026"
    )

    TOPUP_ADMIN_NEW_PAYMENT = (
        "🚨 <b>YANGI TO'LOV CHEKI!</b>\n\n"
        "👤 <b>Foydalanuvchi:</b> {full_name} ({username})\n"
        "🆔 <b>Chat ID:</b> <code>{chat_id}</code>\n"
        "📞 <b>Tel:</b> {phone}\n"
        "💰 <b>Summa:</b> {amount:,} so'm\n"
        "💳 <b>Karta:</b> {card_number}\n"
        "🕐 <b>Vaqt:</b> {time}\n\n"
        "Quyidagi tugmalar orqali tasdiqlang yoki rad eting:"
    )

    TOPUP_PAID = "✅ <b>To'lov tasdiqlandi!</b>\n\nHisobingizga {amount:,} so'm qo'shildi."
    TOPUP_REJECTED = "❌ <b>To'lovingiz rad etildi.</b>\n\nAdmin bilan bog'laning: @It_project_2026"

    # --- Konkurs ---
    KONKURS_TEXT = (
        "🏆 <b>Konkursda ishtirok etish</b>\n\n"
        "👥 Sizning ballaringiz: <b>{score} ball</b>\n"
        "🔗 Sizning linkingiz:\n<code>{ref_link}</code>\n\n"
        "Do'stlaringizni taklif qiling va ball to'plang!"
    )


# ==============================================================================
# 5. WEB APP KONFIGURATSIYASI
# ==============================================================================

class WebAppConfig:
    TARIFFS: dict = {
        "web_only": {
            "id": "web_only",
            "name": "🖥️ Web App faqat",
            "desc": "Faqat Web App asosiy sahifasida chiqadi (7 kun)",
            "prices": Prices.TARIFF_WEB,
        },
        "channel_only": {
            "id": "channel_only",
            "name": "📢 Kanal faqat",
            "desc": "Faqat kanalga post qilinadi (Umrbod)",
            "prices": Prices.TARIFF_CHANNEL,
        },
        "web_and_channel": {
            "id": "web_and_channel",
            "name": "🔥 Web + Kanal",
            "desc": "Web App'da (7 kun) va Kanallarda (Umrbod) chiqadi",
            "prices": Prices.TARIFF_BOTH,
        },
    }

    CHANNELS: dict = copy.deepcopy(BotConfig.CHANNELS)
    WEB_AD_DAYS: int = Settings.WEB_AD_DAYS
    TOPUP_TIMER_MINUTES: int = Settings.TOPUP_TIMER_MINUTES
    MIN_TOPUP_AMOUNT: int = Settings.MIN_TOPUP_AMOUNT


# ==============================================================================
# 6. TELEGRAM USERBOT (CARD XABAR)
# ==============================================================================

class UserbotConfig:
    # CardXabarBot dan keladigan xabarni tahlil qilish uchun regex
    CARD_TRANSFER_REGEX: str = r"([\d\s]+)\s*UZS.*\*{3}(\d{4})"
    
    # Telegram API (Rasmiy Telegram Desktop API)
    API_ID: int = _env_int("TELEGRAM_API_ID", 6)
    API_HASH: str = _env("TELEGRAM_API_HASH", "eb06d4abfb49dc3eeb1aeb98ae0f581e")
    
    # Userbot tinglaydigan bot
    TARGET_BOT: str = _env("USERBOT_TARGET_BOT", "CardXabarBot")
    
    # Sessiyalar papkasi
    SESSIONS_DIR: str = _env("SESSIONS_DIR", "sessions")
