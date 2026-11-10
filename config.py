# ==============================================================================
# LOYIHA: UzbekCats Bot & Web App
# FAYL: config.py
# TAVSIF: Bot va Web App uchun barcha statik ma'lumotlar, matnlar, narxlar va sozlamalar
# ==============================================================================

import os


# ==============================================================================
# 1. ASOSIY SOZLAMALAR (BOT VA WEB APP)
# ==============================================================================

class BotConfig:
    # Bot tokeni (Railway'ga deploy qilganda Environment Variable orqali olinadi)
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "8577521489:AAGbp2MvcMXZlnK-KbDdmPm8WArYlJ4PxWk")

    # Botning username (Web App va havolalar uchun)
    BOT_USERNAME: str = "@Uzbek_cat_bot"

    # Adminlar ID lari
    ADMIN_ID: int = 673018191
    TECH_ADMIN_ID: int = 7038296036

    # Adminlar ro'yxati (tekshirish uchun qulaylik)
    ADMIN_IDS: list[int] = [ADMIN_ID, TECH_ADMIN_ID]

    # Kanal ma'lumotlari
    CHANNEL_USERNAME: str = "@uzbek_cats"
    CHANNEL_ID: str = "@uzbek_cats"  # Agar kanal ID si raqam bo'lsa (-100...) shuni yozing

    # Database URL (PostgreSQL)
    # Railway'da avtomatik beriladi, lokalda o'zingiznikini yozasiz
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/uzbekcats_db")

    # Web App URL (GitHub Pages'ga joylagandan keyin shu yerga yozasiz)
    WEB_APP_URL: str = os.getenv("WEB_APP_URL", "https://bilolmujah-hue.github.io/Uzbekcats/")


class Settings:
    # Web App'dagi reklamalar necha kun turadi (kunlik)
    WEB_AD_DAYS: int = 7

    # Hisob to'ldirish uchun beriladigan vaqt (daqiqa)
    TOPUP_TIMER_MINUTES: int = 10

    # Texnik admin ulushi (foizda)
    TECH_ADMIN_PERCENT: int = 10

    # Botning umumiy holati (db dan ham boshqarish mumkin, lekin default)
    BOT_ENABLED: bool = True


# ==============================================================================
# 2. NARXLAR (TARIFLAR)
# Kalit: Mushuklar soni (1 dan 5 gacha)
# Qiymat: Narx (so'mda)
# ==============================================================================

class Prices:
    # 1-TARIF: Faqat Web App'da chiqadi
    TARIFF_WEB: dict[int, int] = {
        1: 10000,
        2: 18000,
        3: 25000,
        4: 31000,
        5: 38000
    }

    # 2-TARIF: Faqat Kanalga chiqadi
    TARIFF_CHANNEL: dict[int, int] = {
        1: 25000,
        2: 45000,
        3: 65000,
        4: 85000,
        5: 105000
    }

    # 3-TARIF: Web App + Kanalga chiqadi
    TARIFF_BOTH: dict[int, int] = {
        1: 32000,
        2: 50000,
        3: 75000,
        4: 95000,
        5: 115000  # Tuzatildi (100,000 emas)
    }


# ==============================================================================
# 3. RO'YXATLAR (Viloyatlar, Yoshlar, Zotlar, Taqiqlangan so'zlar)
# ==============================================================================

class DataLists:
    VILOYATLAR: list[str] = [
        "Andijon", "Buxoro", "Farg'ona", "Jizzax", "Xorazm",
        "Namangan", "Navoiy", "Qashqadaryo", "Samarqand",
        "Sirdaryo", "Surxondaryo", "Toshkent", "Toshkent shahar"
    ]

    AGES: list[str] = [
        "1 oylik", "2 oylik", "3 oylik", "4 oylik", "5 oylik",
        "6 oylik", "7 oylik", "8 oylik", "9 oylik", "10 oylik",
        "11 oylik", "1 yosh", "1,5 yosh", "2 yosh", "2,5 yosh",
        "3 yosh", "3,5 yosh", "4 yosh", "4,5 yosh", "5 yosh"
    ]

    BREEDS: list[list[str]] = [
        # 1-sahifa
        [
            "Scottish fold", "Scottish straight", "British blue", "British chinchilla",
            "Bengal cat", "Turkish angora", "Scottish chinchila", "Gibrid", "British Shorthair"
        ],
        # 2-sahifa
        [
            "British Shorthair Britan qisqa junli", "British Longhair Britan uzun junli",
            "Persian Cat Fors mushugi", "Maine Coon Meyn-kun", "Ragdoll Qo'g'irchoq mushuk",
            "Bengal Cat Bengal mushugi", "Siberian Cat Sibir mushugi", "Russian blue Rus moviy mushugi"
        ],
        # 3-sahifa
        [
            "Abyssinian Abissiniya", "Norwegian Forest Cat Norvegiya", "Turkish Angora Turkiya angora",
            "Turkish Van Turkiya Van", "Burmilla burma + chinchilla aralash", "British Longhair Britan uzun junli",
            "American Shorthair Amerika qisqa junli", "American Curl Amerika bukilgan quloqli",
            "Egyptian Mau Misr mau mushugi"
        ],
        # 4-sahifa
        [
            "Tonkinese Tonkin siam va birma", "Balinese Balin uzun junli", "Exotic Shorthair Egzotik qisqa junli",
            "Savannah Cat Savanna serval bilan aralash", "Munchkin kalta oyoqli mushuk", "Khao Manee Xao Mani",
            "Uy mushuki", "Mushuk"
        ]
    ]

    BANNED_WORDS: set[str] = {
        "mushuk sotiladi", "mushuk bor", "sotaman", "sotiladi", "mushu bor", "muwu bor", "muwu bo", "Mushuk bor",
        "sotuvda", "arzonga mushuk", "hadiyaga", "mendayam bor",
        "atrofida bor", "sotman", "kimga mushuk kerak", "Mandayam bor",
        "beramiz", "beraman", "сотаман", "мушук бор", "бор", "бера",
        "hadyaga", "кимга мушук керак", "мушук сотилади"
    }


# ==============================================================================
# 4. MATNLAR (Xabarlar, Tugmalar, Ogohlantirishlar)
# ==============================================================================

class Texts:
    # --- Umumiy ---
    WARNING_BANNED_WORD = "❌ Iltimos, reklama tarqatmang!"
    BOT_DISABLED = "❌ Bot hozirda ishlamayapti. Iltimos, keyinroq urinib ko'ring."
    USER_BANNED = "❌ Siz botdan foydalanish huquqidan mahrum qilingansiz!"

    # --- Ro'yxatdan o'tish ---
    START_TEXT = (
        "📱 *Assalomu alaykum! Uzbek Cats botiga xush kelibsiz!*\n\n"
        "Botdan foydalanish uchun telefon raqamingizni yuboring:\n\n"
        "Pastdagi \"📞 Raqamni yuborish\" tugmasini bosing yoki telefon raqamingizni kiriting."
    )

    ASK_PHONE = "❌ Iltimos, to'g'ri telefon raqam kiriting yoki \"📞 Raqamni yuborish\" tugmasini bosing."

    REG_SUCCESS = (
        "✅ Ro'yxatdan muvaffaqiyatli o'tdingiz!\n"
        "🔢 Sizning raqamingiz: #{user_number}\n"
        "🏆 Ballaringiz: {score}\n"
        "👥 Takliflaringiz: {referrals} kishi"
    )

    # --- Asosiy Menyu ---
    MAIN_MENU = (
        "🏠 *Asosiy menyu*\n\n"
        "Quyidagi imkoniyatlardan foydalaning:"
    )

    THREE_BUTTON_MENU = (
        "🎉 *Muvaffaqiyatli ro'yxatdan o'tdingiz!*\n\n"
        "🔢 Sizning raqamingiz: #{user_number}\n"
        "🏆 Ballaringiz: {score}\n"
        "👥 Takliflaringiz: {referrals} kishi\n\n"
        "Quyidagi imkoniyatlardan foydalaning:"
    )

    # --- Reklama berish ---
    AD_TYPE_SELECT = "🎯 Quyidagilardan birini tanlang:"

    # --- Tariflar ---
    TARIFF_SELECT_TEXT = (
        "💳 *Tarifni tanlang*\n\n"
        "Siz {cat_count} ta mushuk sotmoqchisiz.\n"
        "Quyidagi tariflardan birini tanlang:"
    )

    # --- Xatoliklar ---
    ERROR_INSUFFICIENT_BALANCE = "❌ Hisobingizda mablag' yetarli emas!\n\nKerakli summa: {price} so'm\nSizning balansingiz: {balance} so'm"

    # --- Admin va Texnik Admin ---
    ADMIN_PANEL_WELCOME = "👨‍💼 *Admin Paneliga xush kelibsiz!*\n\nQuyidagilardan birini tanlang:"
    TECH_ADMIN_PANEL_WELCOME = "👨‍💻 *Texnik Admin Paneli*\n\nQuyidagilardan birini tanlang:"

    # --- To'lov (Hisob to'ldirish) ---
    TOPUP_ASK_AMOUNT = (
        "💳 *Hisobni to'ldirish*\n\n"
        "Qancha miqdorda pul tashlamoqchisiz?\n"
        "Iltimos, summani raqamda kiriting (masalan: 10000):"
    )

    TOPUP_INSTRUCTIONS = (
        "💳 *To'lov ma'lumotlari:*\n\n"
        "Karta raqami: `{card_number}`\n"
        "Karta egasi: {card_holder}\n"
        "Summa: *{amount} so'm*\n\n"
        "⏳ Ushbu to'lov uchun sizga *{minutes} daqiqa* vaqt berildi.\n"
        "Iltimos, shu vaqt ichida kartaga pul o'tkazing va chekni yuklang!"
    )


# ==============================================================================
# 5. WEB APP UCHUN KONFIGURATSIYA
# ==============================================================================

class WebAppConfig:
    # Web App'da ko'rsatiladigan tariflar ro'yxati (Frontend uchun JSON)
    TARIFFS = {
        "web_only": {
            "id": "web_only",
            "name": "🖥️ Web App faqat",
            "desc": "Faqat asosiy sahifada chiqadi",
            "prices": Prices.TARIFF_WEB
        },
        "channel_only": {
            "id": "channel_only",
            "name": "📢 Kanal faqat",
            "desc": "Faqat kanalga post qilinadi",
            "prices": Prices.TARIFF_CHANNEL
        },
        "web_and_channel": {
            "id": "web_and_channel",
            "name": "🖥️+📢 Web va Kanal",
            "desc": "Ikkalasida ham chiqadi",
            "prices": Prices.TARIFF_BOTH
        }
    }


# ==============================================================================
# 6. TELEGRAM USERBOT (To'lovlarni tekshirish uchun)
# ==============================================================================

class UserbotConfig:
    # @CardXabarBot dan keladigan xabarlarni tahlil qilish uchun Regex
    # Masalan: "Perevod na kartu 10 000 UZS ***0956"
    CARD_TRANSFER_REGEX = r"([\d\s]+)\s*UZS.*\*{3}(\d{4})"

    # Userbot sessiyalari saqlanadigan papka
    SESSIONS_DIR = "sessions"