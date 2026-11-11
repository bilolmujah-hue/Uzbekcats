# ==============================================================================
# LOYIHA: UzbekCats Bot & Web App
# FAYL: config.py
# TAVSIF: Bot va Web App uchun barcha statik ma'lumotlar, matnlar, narxlar, sozlamalar
# ==============================================================================

import os


def _env_int(key: str, default: int) -> int:
    """Env dan int olish (xato bo'lsa default)."""
    try:
        return int(os.getenv(key, str(default)))
    except (ValueError, TypeError):
        return default


# ==============================================================================
# 1. ASOSIY SOZLAMALAR
# ==============================================================================

class BotConfig:
    # --- Bot ---
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "8577521489:AAGbp2MvcMXZlnK-KbDdmPm8WArYlJ4PxWk")
    BOT_USERNAME: str = "@Uzbek_cat_bot"
    BOT_LINK: str = "https://t.me/Uzbek_cat_bot"

    # --- Adminlar ---
    ADMIN_ID: int = _env_int("ADMIN_ID", 673018191)
    TECH_ADMIN_ID: int = _env_int("TECH_ADMIN_ID", 7038296036)
    ADMIN_IDS: list[int] = [ADMIN_ID, TECH_ADMIN_ID]

    # --- Kanallar (raqamli ID — eng ishonchli usul) ---
    CHANNEL_SOTISH_ID: int = _env_int("CHANNEL_SOTISH_ID", -1001532366057)   # @uzbek_cats
    CHANNEL_HADIYA_ID: int = _env_int("CHANNEL_HADIYA_ID", -1003815754371)   # @uzbek_cats_hadiya

    CHANNEL_SOTISH_USERNAME: str = "@uzbek_cats"
    CHANNEL_HADIYA_USERNAME: str = "@uzbek_cats_hadiya"

    CHANNEL_SOTISH_LINK: str = "https://t.me/uzbek_cats"
    CHANNEL_HADIYA_LINK: str = "https://t.me/uzbek_cats_hadiya"

    # Qulaylik uchun dict ko'rinishida
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

    # Orqaga moslik uchun (eski kod ishlashi mumkin)
    CHANNEL_ID: int = CHANNEL_SOTISH_ID
    CHANNEL_USERNAME: str = CHANNEL_SOTISH_USERNAME

    # --- Database ---
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:password@localhost:5432/uzbekcats_db",
    )

    # --- Web App ---
    WEB_APP_URL: str = os.getenv("WEB_APP_URL", "https://bilolmujah-hue.github.io/Uzbekcats/")


class Settings:
    # Web App reklamasi necha kun turadi
    WEB_AD_DAYS: int = _env_int("WEB_AD_DAYS", 7)

    # Hisob to'ldirish taymeri (daqiqa)
    TOPUP_TIMER_MINUTES: int = _env_int("TOPUP_TIMER_MINUTES", 10)

    # Texnik admin ulushi (foiz)
    TECH_ADMIN_PERCENT: int = _env_int("TECH_ADMIN_PERCENT", 10)

    # Bot default holati (DB dagi qiymat ustuvor)
    BOT_ENABLED: bool = True

    # Minimal to'lov summasi (so'm)
    MIN_TOPUP_AMOUNT: int = 1000

    # Rasm limitlari
    MAX_PHOTOS: int = 3
    MIN_PHOTOS: int = 1

    # Majburiy obuna (True → /start da kanallarga obuna so'raladi)
    REQUIRE_SUBSCRIPTION: bool = True


# ==============================================================================
# 2. NARXLAR (TARIFLAR)
# Kalit: mushuklar soni (1–5), qiymat: so'mda
# ==============================================================================

class Prices:
    # 1-TARIF: Faqat Web App'da chiqadi
    TARIFF_WEB: dict[int, int] = {
        1: 10000, 2: 18000, 3: 25000, 4: 31000, 5: 38000,
    }

    # 2-TARIF: Faqat Kanalga chiqadi
    TARIFF_CHANNEL: dict[int, int] = {
        1: 25000, 2: 45000, 3: 65000, 4: 85000, 5: 105000,
    }

    # 3-TARIF: Web App + Kanal
    TARIFF_BOTH: dict[int, int] = {
        1: 32000, 2: 50000, 3: 75000, 4: 95000, 5: 115000,
    }

    # BOT orqali joylash (bot.py da ishlatiladi)
    BOT_PRICES: dict[int, int] = {
        1: 25000, 2: 45000, 3: 65000, 4: 85000, 5: 105000,
    }

    @classmethod
    def get_bot_price(cls, cat_count: int) -> int:
        """Mushuk soni bo'yicha bot narxini olish (chegaralangan)."""
        return cls.BOT_PRICES.get(max(1, min(5, cat_count)), 25000)


# ==============================================================================
# 3. RO'YXATLAR
# ==============================================================================

class DataLists:
    VILOYATLAR: list[str] = [
        "Andijon", "Buxoro", "Farg'ona", "Jizzax", "Xorazm",
        "Namangan", "Navoiy", "Qashqadaryo", "Samarqand",
        "Sirdaryo", "Surxondaryo", "Toshkent", "Toshkent shahar",
    ]

    AGES: list[str] = [
        "1 oylik", "2 oylik", "3 oylik", "4 oylik", "5 oylik",
        "6 oylik", "7 oylik", "8 oylik", "9 oylik", "10 oylik",
        "11 oylik", "1 yosh", "1,5 yosh", "2 yosh", "2,5 yosh",
        "3 yosh", "3,5 yosh", "4 yosh", "4,5 yosh", "5 yosh",
    ]

    BREEDS: list[list[str]] = [
        [
            "Scottish fold", "Scottish straight", "British blue", "British chinchilla",
            "Bengal cat", "Turkish angora", "Scottish chinchila", "Gibrid", "British Shorthair",
        ],
        [
            "British Shorthair Britan qisqa junli", "British Longhair Britan uzun junli",
            "Persian Cat Fors mushugi", "Maine Coon Meyn-kun", "Ragdoll Qo'g'irchoq mushuk",
            "Bengal Cat Bengal mushugi", "Siberian Cat Sibir mushugi", "Russian blue Rus moviy mushugi",
        ],
        [
            "Abyssinian Abissiniya", "Norwegian Forest Cat Norvegiya", "Turkish Angora Turkiya angora",
            "Turkish Van Turkiya Van", "Burmilla burma + chinchilla aralash", "British Longhair Britan uzun junli",
            "American Shorthair Amerika qisqa junli", "American Curl Amerika bukilgan quloqli",
            "Egyptian Mau Misr mau mushugi",
        ],
        [
            "Tonkinese Tonkin siam va birma", "Balinese Balin uzun junli", "Exotic Shorthair Egzotik qisqa junli",
            "Savannah Cat Savanna serval bilan aralash", "Munchkin kalta oyoqli mushuk", "Khao Manee Xao Mani",
            "Uy mushuki", "Mushuk",
        ],
    ]

    BANNED_WORDS: set[str] = {
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
    THREE_BUTTON_MENU = (
        "🎉 <b>Muvaffaqiyatli ro'yxatdan o'tdingiz!</b>\n\n"
        "🔢 Sizning raqamingiz: #{user_number}\n"
        "🏆 Ballaringiz: {score}\n"
        "👥 Takliflaringiz: {referrals} kishi\n\n"
        "Quyidagi imkoniyatlardan foydalaning:"
    )

    # --- Reklama ---
    AD_TYPE_SELECT = "🎯 <b>Qanday turdagi e'lon joylashtirmoqchisiz?</b>"
    TARIFF_SELECT_TEXT = (
        "💳 <b>Tarifni tanlang</b>\n\n"
        "Siz {cat_count} ta mushuk sotmoqchisiz.\n"
        "Quyidagi tariflardan birini tanlang:"
    )
    CAT_COUNT_ASK = "🐱 <b>Nechta mushuk sotmoqchisiz?</b>"
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
    AD_APPROVED_MSG = "\n\n✅ <b>TASDIQLANDI VA KANALGA YUBORILDI</b>"
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

    # --- To'lov (Topup) ---
    TOPUP_ASK_AMOUNT = (
        "💳 <b>Hisobni to'ldirish</b>\n\n"
        "Qancha miqdorda pul tashlamoqchisiz?\n"
        "Iltimos, summani raqamda kiriting (masalan: 10000):"
    )
    TOPUP_MIN_AMOUNT = "❌ Minimal to'lov {min_amount:,} so'm"
    TOPUP_NO_CARD = "❌ To'lov kartasi mavjud emas. Admin bilan bog'laning."
    TOPUP_INSTRUCTIONS = (
        "💳 <b>To'lov ma'lumotlari:</b>\n\n"
        "Karta raqami: <code>{card_number}</code>\n"
        "Karta egasi: {card_holder}\n"
        "Summa: <b>{amount:,} so'm</b>\n\n"
        "⏳ Ushbu to'lov uchun sizga <b>{minutes} daqiqa</b> vaqt berildi.\n"
        "Iltimos, shu vaqt ichida kartaga pul o'tkazing va chekni yuklang!"
    )
    TOPUP_PAID = "✅ <b>To'lov tasdiqlandi!</b>\n\nHisobingizga {amount:,} so'm qo'shildi."

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
            "desc": "Faqat asosiy sahifada chiqadi",
            "prices": Prices.TARIFF_WEB,
        },
        "channel_only": {
            "id": "channel_only",
            "name": "📢 Kanal faqat",
            "desc": "Faqat kanalga post qilinadi",
            "prices": Prices.TARIFF_CHANNEL,
        },
        "web_and_channel": {
            "id": "web_and_channel",
            "name": "🖥️+📢 Web va Kanal",
            "desc": "Ikkalasida ham chiqadi",
            "prices": Prices.TARIFF_BOTH,
        },
    }

    CHANNELS: dict = BotConfig.CHANNELS
    WEB_AD_DAYS: int = Settings.WEB_AD_DAYS
    TOPUP_TIMER_MINUTES: int = Settings.TOPUP_TIMER_MINUTES
    MIN_TOPUP_AMOUNT: int = Settings.MIN_TOPUP_AMOUNT


# ==============================================================================
# 6. TELEGRAM USERBOT
# ==============================================================================

class UserbotConfig:
    # @CardXabarBot dan keladigan xabarni tahlil qilish uchun regex
    # Masalan: "Perevod na kartu 10 000 UZS ***0956"
    CARD_TRANSFER_REGEX: str = r"([\d\s]+)\s*UZS.*\*{3}(\d{4})"

    # Telegram API (rasmiy desktop api_id/api_hash — userbot uchun)
    API_ID: int = _env_int("TELEGRAM_API_ID", 6)
    API_HASH: str = os.getenv("TELEGRAM_API_HASH", "eb06d4abfb49dc3eeb1aeb98ae0f581e")

    # Userbot tinglaydigan bot
    TARGET_BOT: str = os.getenv("USERBOT_TARGET_BOT", "CardXabarBot")

    # Sessiyalar papkasi
    SESSIONS_DIR: str = os.getenv("SESSIONS_DIR", "sessions")
