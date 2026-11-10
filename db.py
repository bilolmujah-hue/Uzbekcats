# ==============================================================================
# LOYIHA: UzbekCats Bot & Web App
# FAYL: db.py
# TAVSIF: PostgreSQL ma'lumotlar bazasi bilan to'liq ishlash (CRUD, Tranzaksiyalar)
# KUTUBXONA: asyncpg
# ==============================================================================

import asyncpg
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

# config.py dan sozlamalarni olamiz
from config import BotConfig, Settings, UserbotConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Database:
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        """Bazaga ulanadi va jadvallarni yaratadi."""
        try:
            self.pool = await asyncpg.create_pool(
                dsn=BotConfig.DATABASE_URL,
                min_size=5,
                max_size=20
            )
            logger.info("✅ PostgreSQL bazasiga muvaffaqiyatli ulandi!")
            await self.create_tables()
        except Exception as e:
            logger.error(f"❌ Bazaga ulanishda xatolik: {e}")
            raise

    async def disconnect(self):
        """Bazadan uziladi."""
        if self.pool:
            await self.pool.close()
            logger.info("🔌 PostgreSQL bazasidan uzildi.")

    async def create_tables(self):
        """Barcha kerakli jadvallarni yaratadi (agar mavjud bo'lmasa)."""
        queries = [
            # 1. Foydalanuvchilar jadvali
            """
            CREATE TABLE IF NOT EXISTS users
            (
                id
                BIGINT
                PRIMARY
                KEY,
                username
                VARCHAR
            (
                255
            ),
                full_name VARCHAR
            (
                255
            ),
                phone VARCHAR
            (
                20
            ) UNIQUE,
                user_number SERIAL,
                balance INTEGER DEFAULT 0,
                score INTEGER DEFAULT 10,
                ad_count INTEGER DEFAULT 0,
                is_banned BOOLEAN DEFAULT FALSE,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_ad_time TIMESTAMP
                );
            """,
            # 2. Kartalar jadvali (Admin qo'shadi)
            """
            CREATE TABLE IF NOT EXISTS cards
            (
                id
                SERIAL
                PRIMARY
                KEY,
                number
                VARCHAR
            (
                20
            ) NOT NULL,
                holder VARCHAR
            (
                100
            ) NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """,
            # 3. To'lovlar jadvali (Hisob to'ldirish)
            """
            CREATE TABLE IF NOT EXISTS payments
            (
                id
                SERIAL
                PRIMARY
                KEY,
                user_id
                BIGINT
                REFERENCES
                users
            (
                id
            ) ON DELETE CASCADE,
                amount INTEGER NOT NULL,
                status VARCHAR
            (
                20
            ) DEFAULT 'pending', -- pending, paid, expired, cancelled
                card_id INTEGER REFERENCES cards
            (
                id
            ),
                card_last4 VARCHAR
            (
                4
            ),
                receipt_file_id VARCHAR
            (
                255
            ),
                userbot_matched BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL
                );
            """,
            # 4. Reklamalar jadvali
            """
            CREATE TABLE IF NOT EXISTS ads
            (
                id
                SERIAL
                PRIMARY
                KEY,
                user_id
                BIGINT
                REFERENCES
                users
            (
                id
            ) ON DELETE CASCADE,
                ad_type VARCHAR
            (
                20
            ) NOT NULL, -- sotish, hadiya, vyazka, yordam
                tariff VARCHAR
            (
                20
            ), -- web_only, channel_only, web_and_channel
                photos JSONB, -- Rasmlar ro'yxati (JSON formatda)
                breed VARCHAR
            (
                100
            ),
                age VARCHAR
            (
                50
            ),
                gender VARCHAR
            (
                50
            ),
                health VARCHAR
            (
                50
            ),
                sterilization VARCHAR
            (
                50
            ),
                address VARCHAR
            (
                255
            ),
                phone VARCHAR
            (
                20
            ),
                price VARCHAR
            (
                50
            ),
                currency VARCHAR
            (
                10
            ) DEFAULT 'so''m',
                ad_number INTEGER,
                status VARCHAR
            (
                20
            ) DEFAULT 'pending', -- pending, approved, rejected, sold, expired
                channel_message_id BIGINT,
                channel_link VARCHAR
            (
                255
            ),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP -- Web app uchun (7 kun)
                );
            """,
            # 5. Referrallar jadvali
            """
            CREATE TABLE IF NOT EXISTS referrals
            (
                referrer_id
                BIGINT
                REFERENCES
                users
            (
                id
            ) ON DELETE CASCADE,
                referred_id BIGINT REFERENCES users
            (
                id
            )
              ON DELETE CASCADE UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """,
            # 6. Sozlamalar jadvali (Konkurs, bot holati va h.k.)
            """
            CREATE TABLE IF NOT EXISTS settings
            (
                key
                VARCHAR
            (
                50
            ) PRIMARY KEY,
                value TEXT
                );
            """,
            # 7. Userbot sessiyalari
            """
            CREATE TABLE IF NOT EXISTS userbot_sessions
            (
                id
                SERIAL
                PRIMARY
                KEY,
                phone
                VARCHAR
            (
                20
            ) NOT NULL,
                session_string TEXT NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """,
            # 8. Userbot xabarlari (CardXabarBot dan kelgan xabarlar logi)
            """
            CREATE TABLE IF NOT EXISTS userbot_messages
            (
                id
                SERIAL
                PRIMARY
                KEY,
                raw_text
                TEXT,
                amount
                INTEGER,
                card_last4
                VARCHAR
            (
                4
            ),
                parsed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """
        ]

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                for query in queries:
                    await conn.execute(query)
        logger.info("✅ Barcha jadvallar yaratildi/tekshirildi.")

    # ==========================================================================
    # FOYDALANUVCHILAR BILAN ISHLASH (USERS)
    # ==========================================================================

    async def get_user(self, user_id: int) -> Optional[dict]:
        """Foydalanuvchini ID orqali olish."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
            return dict(row) if row else None

    async def get_user_by_phone(self, phone: str) -> Optional[dict]:
        """Foydalanuvchini telefon raqami orqali olish (Ball qo'shish uchun)."""
        clean_phone = phone.replace(" ", "")
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM users WHERE phone LIKE $1", f"%{clean_phone}%")
            return dict(row) if row else None

    async def create_user(self, user_id: int, username: str, full_name: str, phone: str,
                          referral_code: str = None) -> dict:
        """Yangi foydalanuvchi yaratish."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # 1. Bazaga qo'shish
                row = await conn.fetchrow(
                    """
                    INSERT INTO users (id, username, full_name, phone)
                    VALUES ($1, $2, $3, $4) RETURNING *
                    """, user_id, username, full_name, phone
                )
                user = dict(row)

                # 2. Agar referal kod bilan kelgan bo'lsa
                if referral_code and referral_code.startswith("REF"):
                    try:
                        referrer_id = int(referral_code.replace("REF", ""))
                        # O'zini o'zi taklif qilmagan bo'lsa
                        if referrer_id != user_id:
                            referrer = await conn.fetchrow("SELECT id FROM users WHERE id = $1", referrer_id)
                            if referrer:
                                await conn.execute(
                                    "INSERT INTO referrals (referrer_id, referred_id) VALUES ($1, $2)",
                                    referrer_id, user_id
                                )
                                # Referrerga +1 ball
                                await conn.execute(
                                    "UPDATE users SET score = score + 1 WHERE id = $1",
                                    referrer_id
                                )
                    except ValueError:
                        pass

                return user

    async def update_user_balance(self, user_id: int, amount: int, operation: str = 'add') -> int:
        """
        Foydalanuvchi balansini o'zgartirish.
        operation: 'add' (qo'shish) yoki 'subtract' (ayirish)
        """
        async with self.pool.acquire() as conn:
            if operation == 'add':
                new_balance = await conn.fetchval(
                    "UPDATE users SET balance = balance + $1 WHERE id = $2 RETURNING balance",
                    amount, user_id
                )
            else:
                # Atomic check: faqat balans yetarli bo'lsa ayiradi
                new_balance = await conn.fetchval(
                    "UPDATE users SET balance = balance - $1 WHERE id = $2 AND balance >= $1 RETURNING balance",
                    amount, user_id
                )
                if new_balance is None:
                    raise ValueError("Hisobda mablag' yetarli emas!")
            return new_balance

    async def update_user_score(self, user_id: int, score: int):
        """Foydalanuvchi ballarini yangilash."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET score = score + $1 WHERE id = $2",
                score, user_id
            )

    async def get_pending_scores(self, phone: str) -> int:
        """Ro'yxatdan o'tmagan userga yuborilgan ballarni olish (Pending score)."""
        async with self.pool.acquire() as conn:
            # Bu qism settings yoki alohida jadval orqali ham qilinishi mumkin,
            # hozircha settings dan qidiramiz: 'pending_score_+99890...'
            key = f"pending_score_{phone}"
            val = await conn.fetchval("SELECT value FROM settings WHERE key = $1", key)
            return int(val) if val else 0

    # ==========================================================================
    # REKLAMALAR BILAN ISHLASH (ADS)
    # ==========================================================================

    async def create_ad(self, user_id: int, ad_type: str, tariff: str, photos: list,
                        breed: str, age: str, gender: str, health: str, sterilization: str,
                        address: str, phone: str, price: str, currency: str, ad_number: int) -> dict:
        """Yangi reklama yaratish (Web App yoki Bot orqali)."""

        # Web app reklamalari uchun 7 kunlik muddat
        expires_at = None
        if tariff in ['web_only', 'web_and_channel']:
            expires_at = datetime.utcnow() + timedelta(days=Settings.WEB_AD_DAYS)

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO ads (user_id, ad_type, tariff, photos, breed, age, gender, health, sterilization, address,
                                 phone, price, currency, ad_number, expires_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15) RETURNING *
                """,
                user_id, ad_type, tariff, json.dumps(photos), breed, age, gender, health, sterilization, address, phone,
                price, currency, ad_number, expires_at
            )

            # Userning reklama sonini oshiramiz
            await conn.execute(
                "UPDATE users SET ad_count = ad_count + 1, last_ad_time = CURRENT_TIMESTAMP WHERE id = $1",
                user_id
            )

            return dict(row)

    async def get_user_ads(self, user_id: int) -> List[dict]:
        """Foydalanuvchining barcha reklamalarini olish."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM ads WHERE user_id = $1 ORDER BY created_at DESC",
                user_id
            )
            return [dict(row) for row in rows]

    async def get_active_web_ads(self) -> List[dict]:
        """Web App asosiy sahifasi uchun faol reklamalarni olish."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT *
                FROM ads
                WHERE status = 'approved'
                  AND tariff IN ('web_only', 'web_and_channel')
                  AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
                ORDER BY created_at DESC
                """
            )
            return [dict(row) for row in rows]

    async def update_ad_status(self, ad_id: int, status: str, channel_message_id: int = None, channel_link: str = None):
        """Reklama holatini yangilash."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE ads
                SET status             = $1,
                    channel_message_id = COALESCE($2, channel_message_id),
                    channel_link       = COALESCE($3, channel_link)
                WHERE id = $4
                """,
                status, channel_message_id, channel_link, ad_id
            )

    async def get_pending_ads_for_tech_admin(self) -> List[dict]:
        """Texnik admin tasdiqlashi uchun kutilayotgan reklamalar."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM ads WHERE status = 'pending' ORDER BY created_at DESC"
            )
            return [dict(row) for row in rows]

    async def cleanup_expired_web_ads(self):
        """Muddati o'tgan web reklamalarni o'chirish (statusni expired qilish)."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE ads
                SET status = 'expired'
                WHERE tariff IN ('web_only', 'web_and_channel')
                  AND expires_at < CURRENT_TIMESTAMP
                  AND status = 'approved'
                """
            )

    # ==========================================================================
    # TO'LOVLAR VA KARTALAR (PAYMENTS & CARDS)
    # ==========================================================================

    async def add_card(self, number: str, holder: str) -> int:
        """Yangi karta qo'shish (Admin panel)."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Eskisini o'chirib yuboramiz (faqat 1 ta aktiv karta bo'lishi uchun)
                await conn.execute("UPDATE cards SET is_active = FALSE")
                card_id = await conn.fetchval(
                    "INSERT INTO cards (number, holder, is_active) VALUES ($1, $2, TRUE) RETURNING id",
                    number, holder
                )
                return card_id

    async def get_active_card(self) -> Optional[dict]:
        """Hozirgi faol kartani olish."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM cards WHERE is_active = TRUE LIMIT 1")
            return dict(row) if row else None

    async def create_payment_request(self, user_id: int, amount: int, card_id: int, card_last4: str) -> int:
        """Hisob to'ldirish uchun so'rov yaratish."""
        expires_at = datetime.utcnow() + timedelta(minutes=Settings.TOPUP_TIMER_MINUTES)
        async with self.pool.acquire() as conn:
            payment_id = await conn.fetchval(
                """
                INSERT INTO payments (user_id, amount, card_id, card_last4, expires_at)
                VALUES ($1, $2, $3, $4, $5) RETURNING id
                """,
                user_id, amount, card_id, card_last4, expires_at
            )
            return payment_id

    async def attach_receipt(self, payment_id: int, file_id: str):
        """To'lov chekini (rasmini) saqlash."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE payments SET receipt_file_id = $1 WHERE id = $2",
                file_id, payment_id
            )

    async def match_userbot_payment(self, amount: int, card_last4: str) -> Optional[int]:
        """
        Userbotdan kelgan xabarni to'lovga moslashtirish.
        Agar summa va karta oxirgi 4 raqami mos kelsa va 10 daqiqa o'tmagan bo'lsa.
        """
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # 1. Kutilayotgan to'lovni qidiramiz
                payment = await conn.fetchrow(
                    """
                    SELECT id, user_id
                    FROM payments
                    WHERE amount = $1
                      AND card_last4 = $2
                      AND status = 'pending'
                      AND expires_at > CURRENT_TIMESTAMP
                    ORDER BY created_at ASC LIMIT 1
                    """,
                    amount, card_last4
                )

                if payment:
                    # 2. To'lovni 'paid' deb belgilaymiz
                    await conn.execute(
                        "UPDATE payments SET status = 'paid', userbot_matched = TRUE WHERE id = $1",
                        payment['id']
                    )
                    # 3. Foydalanuvchi balansiga pul qo'shamiz
                    await conn.execute(
                        "UPDATE users SET balance = balance + $1 WHERE id = $2",
                        amount, payment['user_id']
                    )
                    return payment['user_id']
                return None

    async def confirm_manual_payment(self, payment_id: int) -> int:
        """Admin tomonidan qo'lda tasdiqlash (Userbot topmagan bo'lsa)."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                payment = await conn.fetchrow(
                    "UPDATE payments SET status = 'paid' WHERE id = $1 AND status = 'pending' RETURNING user_id, amount",
                    payment_id
                )
                if payment:
                    await conn.execute(
                        "UPDATE users SET balance = balance + $1 WHERE id = $2",
                        payment['amount'], payment['user_id']
                    )
                    return payment['user_id']
                return None

    # ==========================================================================
    # SOZLAMALAR VA STATISTIKA (SETTINGS & STATISTICS)
    # ==========================================================================

    async def get_setting(self, key: str, default: str = None) -> str:
        """Sozlamani olish (masalan: konkurs matni, web ad kunlari)."""
        async with self.pool.acquire() as conn:
            val = await conn.fetchval("SELECT value FROM settings WHERE key = $1", key)
            return val if val else default

    async def set_setting(self, key: str, value: str):
        """Sozlamani saqlash."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO settings (key, value)
                VALUES ($1, $2) ON CONFLICT (key) DO
                UPDATE SET value = EXCLUDED.value
                """,
                key, value
            )

    async def get_statistics(self) -> dict:
        """Adminlar uchun umumiy statistika."""
        async with self.pool.acquire() as conn:
            total_users = await conn.fetchval("SELECT COUNT(*) FROM users")
            total_ads = await conn.fetchval("SELECT COUNT(*) FROM ads")

            # Bugungi tushum
            today_income = await conn.fetchval(
                "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'paid' AND created_at >= CURRENT_DATE"
            )

            # Oylik tushum
            month_income = await conn.fetchval(
                "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'paid' AND created_at >= date_trunc('month', CURRENT_DATE)"
            )

            tech_admin_cut_month = int(month_income * (Settings.TECH_ADMIN_PERCENT / 100))

            return {
                "total_users": total_users,
                "total_ads": total_ads,
                "today_income": today_income,
                "month_income": month_income,
                "tech_admin_cut_month": tech_admin_cut_month
            }


# ==============================================================================
# SINGLETON DB OBYEKTI
# Bot va API bir vaqtda ishlatishi uchun bitta global obyekt yaratamiz
# ==============================================================================
db = Database()