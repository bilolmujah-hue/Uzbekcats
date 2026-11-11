# ==============================================================================
# LOYIHA: UzbekCats Bot & Web App
# FAYL: db.py
# TAVSIF: PostgreSQL ma'lumotlar bazasi (Eng mukammal, xatosiz, migratsiyali)
# ==============================================================================

import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import asyncpg

from config import BotConfig, Prices, Settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==============================================================================
# XATOLIKLAR
# ==============================================================================
class DBError(Exception): pass
class InsufficientBalanceError(DBError): pass
class PhoneTakenError(DBError): pass
class UserNotFoundError(DBError): pass

# ==============================================================================
# YORDAMCHI
# ==============================================================================
def _normalize_phone(phone: str) -> str:
    """+998XXXXXXXXX formatiga keltiradi."""
    digits = re.sub(r"\D", "", phone or "")
    if not digits:
        return ""
    if not digits.startswith("998"):
        digits = "998" + digits
    return f"+{digits}"

def _parse_photos(photos) -> list:
    if isinstance(photos, list):
        return photos
    if isinstance(photos, str):
        try:
            val = json.loads(photos)
            return val if isinstance(val, list) else []
        except json.JSONDecodeError:
            return []
    return []

# ==============================================================================
# DATABASE KLASSI
# ==============================================================================
class Database:
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
        self._settings_cache: Dict[str, str] = {}
        self._last_cleanup: Optional[datetime] = None

    async def _init_connection(self, conn: asyncpg.Connection):
        try:
            await conn.execute("SET application_name = 'uzbekcats_bot'")
        except Exception:
            pass

    async def connect(self):
        try:
            self.pool = await asyncpg.create_pool(
                dsn=BotConfig.DATABASE_URL,
                min_size=5,
                max_size=25,
                max_queries=50000,
                max_inactive_connection_lifetime=300,
                statement_cache_size=100,
                command_timeout=30,
                timeout=15,
                init=self._init_connection,
            )
            logger.info("✅ PostgreSQL ulanish pool tayyor")
            await self.create_tables()
            await self._warm_cache()
        except Exception as e:
            logger.critical(f"❌ Bazaga ulanishda xatolik: {e}")
            raise

    async def disconnect(self):
        if self.pool:
            await self.pool.close()
            logger.info("🔌 PostgreSQL uzildi")

    async def _warm_cache(self):
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("SELECT key, value FROM settings")
            for row in rows:
                self._settings_cache[row["key"]] = row["value"]
            logger.info(f"✅ Kesh tayyor: {len(self._settings_cache)} sozlama")
        except Exception as e:
            logger.warning(f"Kesh yuklashda xato: {e}")

    # ==========================================================================
    # JADVALLAR VA MIGRATSIYALAR (Barcha yangi ustunlar bilan)
    # ==========================================================================
    async def create_tables(self):
        queries = [
            # 1. USERS (Ogohlantirish va Mute qo'shildi)
            """
            CREATE TABLE IF NOT EXISTS users (
                id BIGINT PRIMARY KEY,
                username VARCHAR(255),
                full_name VARCHAR(255),
                phone VARCHAR(20) UNIQUE,
                user_number SERIAL,
                balance INTEGER DEFAULT 0,
                spent INTEGER DEFAULT 0,
                score INTEGER DEFAULT 10,
                ad_count INTEGER DEFAULT 0,
                is_banned BOOLEAN DEFAULT FALSE,
                is_admin BOOLEAN DEFAULT FALSE,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_ad_time TIMESTAMP,
                warnings INTEGER DEFAULT 0,
                muted_until TIMESTAMP
            );
            """,
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS spent INTEGER DEFAULT 0;",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE;",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_ad_time TIMESTAMP;",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS warnings INTEGER DEFAULT 0;",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS muted_until TIMESTAMP;",

            # 2. CARDS
            """
            CREATE TABLE IF NOT EXISTS cards (
                id SERIAL PRIMARY KEY,
                number VARCHAR(20) NOT NULL,
                holder VARCHAR(100) NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,

            # 3. PAYMENTS
            """
            CREATE TABLE IF NOT EXISTS payments (
                id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
                amount INTEGER NOT NULL,
                status VARCHAR(20) DEFAULT 'pending',
                card_id INTEGER REFERENCES cards(id),
                card_last4 VARCHAR(4),
                receipt_file_id VARCHAR(255),
                userbot_matched BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL
            );
            """,

            # 4. ADS (Barcha kerakli ustunlar)
            """
            CREATE TABLE IF NOT EXISTS ads (
                id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
                ad_type VARCHAR(20) NOT NULL,
                tariff VARCHAR(20),
                photos JSONB,
                breed VARCHAR(100),
                age VARCHAR(50),
                gender VARCHAR(50),
                health VARCHAR(50),
                sterilization VARCHAR(50),
                address VARCHAR(255),
                phone VARCHAR(20),
                price VARCHAR(50),
                currency VARCHAR(10) DEFAULT 'so''m',
                ad_number INTEGER,
                cat_count INTEGER DEFAULT 1,
                price_paid INTEGER DEFAULT 0,
                status VARCHAR(20) DEFAULT 'pending',
                channel_message_id BIGINT,
                channel_link VARCHAR(255),
                reject_reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP
            );
            """,
            # Eski bazalar uchun majburiy migratsiya
            "ALTER TABLE ads ADD COLUMN IF NOT EXISTS cat_count INTEGER DEFAULT 1;",
            "ALTER TABLE ads ADD COLUMN IF NOT EXISTS price_paid INTEGER DEFAULT 0;",
            "ALTER TABLE ads ADD COLUMN IF NOT EXISTS reject_reason TEXT;",
            "ALTER TABLE ads ADD COLUMN IF NOT EXISTS channel_message_id BIGINT;",
            "ALTER TABLE ads ADD COLUMN IF NOT EXISTS channel_link VARCHAR(255);",
            "ALTER TABLE ads ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP;",

            # 5. REFERRALS
            """
            CREATE TABLE IF NOT EXISTS referrals (
                referrer_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
                referred_id BIGINT REFERENCES users(id) ON DELETE CASCADE UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (referrer_id, referred_id)
            );
            """,

            # 6. SETTINGS
            """
            CREATE TABLE IF NOT EXISTS settings (
                key VARCHAR(50) PRIMARY KEY,
                value TEXT
            );
            """,

            # 7. USERBOT SESSIONS
            """
            CREATE TABLE IF NOT EXISTS userbot_sessions (
                id SERIAL PRIMARY KEY,
                phone VARCHAR(20) NOT NULL,
                session_string TEXT NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,

            # INDEKSLAR (Tezlik uchun)
            "CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone);",
            "CREATE INDEX IF NOT EXISTS idx_users_number ON users(user_number);",
            "CREATE INDEX IF NOT EXISTS idx_users_muted ON users(muted_until) WHERE muted_until IS NOT NULL;",
            "CREATE INDEX IF NOT EXISTS idx_ads_user_id ON ads(user_id);",
            "CREATE INDEX IF NOT EXISTS idx_ads_status ON ads(status);",
            "CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status);",
        ]

        async with self.pool.acquire() as conn:
            for q in queries:
                try:
                    await conn.execute(q)
                except Exception as e:
                    logger.error(f"❌ Migratsiya xatosi: {e}")
        logger.info("✅ Jadvallar va ustunlar to'liq tekshirildi")

    # ==========================================================================
    # USERS (Foydalanuvchilar, Ogohlantirish va Mute)
    # ==========================================================================
    async def get_user(self, user_id: int) -> Optional[dict]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
        return dict(row) if row else None

    async def get_user_by_number(self, user_number: int) -> Optional[dict]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM users WHERE user_number = $1", user_number)
        return dict(row) if row else None

    async def create_user(self, user_id: int, username: str, full_name: str, phone: str, referral_code: str = None) -> dict:
        normalized_phone = _normalize_phone(phone)
        if not normalized_phone: raise DBError("Telefon raqam bo'sh")

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                existing = await conn.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
                if existing: return dict(existing)

                try:
                    row = await conn.fetchrow(
                        "INSERT INTO users (id, username, full_name, phone) VALUES ($1, $2, $3, $4) RETURNING *",
                        user_id, username, full_name, normalized_phone,
                    )
                except asyncpg.UniqueViolationError:
                    raise PhoneTakenError("Bu telefon raqam boshqa foydalanuvchiga tegishli!")

                user = dict(row)
                if referral_code and str(referral_code).startswith("REF"):
                    try:
                        referrer_id = int(str(referral_code).replace("REF", ""))
                        if referrer_id != user_id:
                            await conn.execute("INSERT INTO referrals (referrer_id, referred_id) VALUES ($1, $2) ON CONFLICT DO NOTHING", referrer_id, user_id)
                            await conn.execute("UPDATE users SET score = score + 1 WHERE id = $1", referrer_id)
                    except ValueError: pass
                return user

    async def update_user_balance(self, user_id: int, amount: int, operation: str = "add") -> int:
        if amount < 0: raise DBError("Summa manfiy bo'lmaydi")
        async with self.pool.acquire() as conn:
            if operation == "add":
                new_balance = await conn.fetchval("UPDATE users SET balance = balance + $1 WHERE id = $2 RETURNING balance", amount, user_id)
                if new_balance is None: raise UserNotFoundError("Foydalanuvchi topilmadi")
                return new_balance
            else:
                new_balance = await conn.fetchval(
                    "UPDATE users SET balance = balance - $1, spent = spent + $1 WHERE id = $2 AND balance >= $1 RETURNING balance",
                    amount, user_id,
                )
                if new_balance is None: raise InsufficientBalanceError("Hisobda mablag' yetarli emas!")
                return new_balance

    async def add_warning(self, user_id: int) -> int:
        """Ogohlantirish qo'shadi va joriy ogohlantirishlar sonini qaytaradi."""
        async with self.pool.acquire() as conn:
            new_count = await conn.fetchval("UPDATE users SET warnings = warnings + 1 WHERE id = $1 RETURNING warnings", user_id)
        return new_count or 0

    async def reset_warnings(self, user_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute("UPDATE users SET warnings = 0 WHERE id = $1", user_id)

    async def mute_user(self, user_id: int, hours: int = 24):
        """Foydalanuvchini vaqtincha yozishdan mahrum qiladi."""
        muted_until = datetime.utcnow() + timedelta(hours=hours)
        async with self.pool.acquire() as conn:
            await conn.execute("UPDATE users SET muted_until = $1 WHERE id = $2", muted_until, user_id)

    async def check_mute(self, user_id: int) -> bool:
        """Foydalanuvchi mute bo'lganmi? (True - mute, False - yo'q)"""
        async with self.pool.acquire() as conn:
            muted_until = await conn.fetchval("SELECT muted_until FROM users WHERE id = $1", user_id)
        if not muted_until: return False
        return muted_until > datetime.utcnow()

    async def block_user(self, user_id: int) -> bool:
        async with self.pool.acquire() as conn:
            result = await conn.execute("UPDATE users SET is_banned = TRUE WHERE id = $1", user_id)
        return result != "UPDATE 0"

    async def get_top_10_users(self) -> List[dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT id, user_number, full_name, phone, score, username FROM users WHERE is_banned = FALSE ORDER BY score DESC, registered_at ASC LIMIT 10")
        return [dict(r) for r in rows]

    # ==========================================================================
    # ADS (E'lonlar: Yaratish, O'zgartirish, O'chirish)
    # ==========================================================================
    async def create_ad(
        self, user_id: int, ad_type: str, tariff: str, photos: list, breed: str, age: str,
        gender: str, health: str, sterilization: str, address: str, phone: str,
        price: str, currency: str, ad_number: int, cat_count: int = 1, price_paid: Optional[int] = None,
    ) -> dict:
        expires_at = None
        if tariff in ("web_only", "web_and_channel", "web"):
            days = await self.get_setting("web_ad_days", str(Settings.WEB_AD_DAYS))
            try: expires_at = datetime.utcnow() + timedelta(days=int(days))
            except (ValueError, TypeError): expires_at = datetime.utcnow() + timedelta(days=Settings.WEB_AD_DAYS)

        if price_paid is None:
            price_map = {"web_only": Prices.TARIFF_WEB, "channel_only": Prices.TARIFF_CHANNEL, "web_and_channel": Prices.TARIFF_BOTH, "bot": Prices.BOT_PRICES}
            mapping = price_map.get(tariff, {})
            price_paid = mapping.get(max(1, min(5, cat_count)), 0)

        photos_json = json.dumps(photos or [])

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                actual_ad_number = await conn.fetchval(
                    "UPDATE users SET ad_count = ad_count + 1, last_ad_time = CURRENT_TIMESTAMP WHERE id = $1 RETURNING ad_count", user_id,
                )
                if actual_ad_number is None: raise UserNotFoundError("Foydalanuvchi topilmadi")

                row = await conn.fetchrow(
                    """
                    INSERT INTO ads (
                        user_id, ad_type, tariff, photos, breed, age, gender,
                        health, sterilization, address, phone, price, currency,
                        ad_number, cat_count, price_paid, expires_at
                    ) VALUES ($1,$2,$3,$4::jsonb,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17) RETURNING *
                    """,
                    user_id, ad_type, tariff, photos_json, breed, age, gender,
                    health, sterilization, address, phone, price, currency,
                    actual_ad_number, cat_count, price_paid, expires_at,
                )
        return dict(row)

    async def get_ad(self, ad_id: int) -> Optional[dict]:
        """Bitta e'lonni ID orqali olish"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM ads WHERE id = $1", ad_id)
        return dict(row) if row else None

    async def get_user_ads(self, user_id: int) -> List[dict]:
        """Faqat foydalanuvchining haqiqiy e'lonlarini olish (Demo emas)"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM ads WHERE user_id = $1 ORDER BY created_at DESC", user_id)
        return [dict(r) for r in rows]

    async def get_pending_ads(self) -> List[dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM ads WHERE status = 'pending' ORDER BY created_at DESC")
        return [dict(r) for r in rows]

    async def update_ad_status(self, ad_id: int, status: str, reason: str = None, channel_message_id: int = None, channel_link: str = None):
        """E'lon holatini o'zgartirish (approved, rejected, sold, given_away)"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE ads SET status = $1,
                    reject_reason = COALESCE($2, reject_reason),
                    channel_message_id = COALESCE($3, channel_message_id),
                    channel_link = COALESCE($4, channel_link)
                WHERE id = $5
                """,
                status, reason, channel_message_id, channel_link, ad_id,
            )

    async def update_ad_details(self, ad_id: int, **kwargs):
        """Admin yoki foydalanuvchi tomonidan e'lon ma'lumotlarini o'zgartirish"""
        allowed_fields = ["breed", "age", "gender", "health", "sterilization", "address", "phone", "price", "currency"]
        updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
        
        if not updates: return
        
        set_clause = ", ".join([f"{key} = ${i+1}" for i, key in enumerate(updates.keys())])
        values = list(updates.values())
        values.append(ad_id)
        
        async with self.pool.acquire() as conn:
            await conn.execute(f"UPDATE ads SET {set_clause} WHERE id = ${len(values)}", *values)

    async def delete_ad(self, ad_id: int):
        """E'lonni butunlay o'chirish (Sotildi/Berildi qilinganda)"""
        async with self.pool.acquire() as conn:
            await conn.execute("DELETE FROM ads WHERE id = $1", ad_id)

    async def cleanup_expired_ads(self, force: bool = False) -> int:
        now = datetime.utcnow()
        if not force and self._last_cleanup and (now - self._last_cleanup).total_seconds() < 60: return 0
        async with self.pool.acquire() as conn:
            result = await conn.execute("UPDATE ads SET status = 'expired' WHERE status = 'approved' AND expires_at IS NOT NULL AND expires_at < CURRENT_TIMESTAMP")
        self._last_cleanup = now
        try: return int(result.split()[-1])
        except: return 0

    # ==========================================================================
    # SETTINGS & STATISTICS
    # ==========================================================================
    async def get_setting(self, key: str, default: str = None) -> Optional[str]:
        if key in self._settings_cache: return self._settings_cache[key]
        async with self.pool.acquire() as conn:
            val = await conn.fetchval("SELECT value FROM settings WHERE key = $1", key)
        if val is None: return default
        self._settings_cache[key] = val
        return val

    async def set_setting(self, key: str, value: str):
        async with self.pool.acquire() as conn:
            await conn.execute("INSERT INTO settings (key, value) VALUES ($1, $2) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", key, value)
        self._settings_cache[key] = value

    async def get_statistics(self) -> dict:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    (SELECT COUNT(*) FROM users) AS total_users,
                    (SELECT COUNT(*) FROM ads) AS total_ads,
                    (SELECT COUNT(*) FROM ads WHERE status = 'pending') AS pending_ads,
                    (SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'paid' AND created_at >= CURRENT_DATE) AS today_income,
                    (SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'paid' AND created_at >= date_trunc('month', CURRENT_DATE)) AS month_income
                """
            )
        return dict(row)

# ==============================================================================
# SINGLETON
# ==============================================================================
db = Database()
