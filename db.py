# ==============================================================================
# LOYIHA: UzbekCats Bot & Web App
# FAYL: db.py
# TAVSIF: PostgreSQL + asyncpg — to'liq ishchi, xatosiz, barcha metodlar
# ==============================================================================

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

import asyncpg

from config import BotConfig, Settings

logger = logging.getLogger(__name__)


# ==============================================================================
# DATABASE KLASSI
# ==============================================================================

class Database:
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
        self._connect_lock = asyncio.Lock()

    # ==========================================================================
    # ULANISH VA JADVALLAR YARATISH
    # ==========================================================================

    async def connect(self):
        """Pool yaratish va jadvallarni xavfsiz yaratish."""
        if self.pool is not None:
            return

        async with self._connect_lock:
            if self.pool is not None:
                return

            dsn = BotConfig.DATABASE_URL
            if dsn.startswith("postgres://"):
                dsn = dsn.replace("postgres://", "postgresql://", 1)

            try:
                self.pool = await asyncpg.create_pool(
                    dsn=dsn,
                    min_size=1,
                    max_size=10,
                    command_timeout=60,
                )
                await self._create_tables()
                logger.info("✅ Database pool tayyor")
            except Exception as e:
                logger.error(f"❌ Database ulanish xatosi: {e}")
                if self.pool is not None:
                    await self.pool.close()
                    self.pool = None
                raise

    async def disconnect(self):
        if self.pool is not None:
            await self.pool.close()
            self.pool = None
            logger.info("🔌 Database pool yopildi")

    async def _create_tables(self):
        """Jadvallarni yaratish. Advisory Lock bilan UniqueViolationError oldini oladi."""
        async with self.pool.acquire() as conn:
            # Bir vaqtda bir nechta bot ishga tushsa ham xato bermasligi uchun lock
            await conn.execute("SELECT pg_advisory_lock(123456789)")
            try:
                await self._run_ddl(conn)
            finally:
                await conn.execute("SELECT pg_advisory_unlock(123456789)")

    async def _run_ddl(self, conn):
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id BIGINT PRIMARY KEY,
                user_number SERIAL UNIQUE,
                username TEXT,
                full_name TEXT,
                phone TEXT UNIQUE,
                balance BIGINT DEFAULT 0,
                score INT DEFAULT 0,
                spent BIGINT DEFAULT 0,
                ad_count INT DEFAULT 0,
                warn_count INT DEFAULT 0,
                mute_until TIMESTAMP,
                is_banned BOOLEAN DEFAULT FALSE,
                is_admin BOOLEAN DEFAULT FALSE,
                referred_by BIGINT,
                registered_at TIMESTAMP DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ads (
                id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
                ad_type TEXT NOT NULL,
                tariff TEXT,
                photos JSONB DEFAULT '[]'::jsonb,
                breed TEXT,
                age TEXT,
                gender TEXT,
                health TEXT,
                sterilization TEXT,
                address TEXT,
                phone TEXT,
                price TEXT DEFAULT '0',
                currency TEXT DEFAULT 'so''m',
                ad_number INT,
                cat_count INT DEFAULT 1,
                price_paid BIGINT DEFAULT 0,
                status TEXT DEFAULT 'pending',
                reject_reason TEXT,
                channel_message_id BIGINT,
                created_at TIMESTAMP DEFAULT NOW(),
                expires_at TIMESTAMP
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
                amount BIGINT NOT NULL,
                card_id INT,
                card_last4 TEXT,
                receipt_file_id TEXT,
                status TEXT DEFAULT 'pending',
                userbot_matched BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW(),
                expires_at TIMESTAMP
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS cards (
                id SERIAL PRIMARY KEY,
                number TEXT NOT NULL,
                holder TEXT NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS userbot_sessions (
                id SERIAL PRIMARY KEY,
                phone TEXT,
                session_string TEXT NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                added_at TIMESTAMP DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id SERIAL PRIMARY KEY,
                referrer_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
                referred_id BIGINT UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS userbot_payments (
                id SERIAL PRIMARY KEY,
                amount BIGINT,
                last4 TEXT,
                matched_user_id BIGINT,
                matched BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Indekslar
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_ads_user_id ON ads(user_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_ads_status ON ads(status)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_ads_tariff ON ads(tariff)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payments(user_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_score ON users(score DESC)")

        logger.info("✅ Jadvallar tayyor")

    # ==========================================================================
    # YORDAMCHI FUNKSIYALAR
    # ==========================================================================

    @staticmethod
    def _parse_ad(row) -> Optional[dict]:
        if row is None:
            return None
        d = dict(row)
        photos = d.get("photos")
        if isinstance(photos, list):
            pass
        elif isinstance(photos, str):
            try:
                d["photos"] = json.loads(photos)
            except json.JSONDecodeError:
                d["photos"] = []
        elif photos is None:
            d["photos"] = []
        else:
            d["photos"] = []
        return d

    # ==========================================================================
    # USERS
    # ==========================================================================

    async def get_user(self, telegram_id: int) -> Optional[dict]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM users WHERE id = $1", telegram_id)
        return dict(row) if row else None

    async def get_user_by_phone(self, phone: str) -> Optional[dict]:
        digits = "".join(c for c in phone if c.isdigit())
        if len(digits) < 9:
            return None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE phone LIKE $1", f"%{digits[-9:]}"
            )
        return dict(row) if row else None

    async def create_user(
        self,
        telegram_id: int,
        username: str,
        full_name: str,
        phone: str,
        referral_code: Optional[str] = None,
    ) -> dict:
        phone = phone.strip()
        if not phone.startswith("+"):
            phone = "+" + phone

        referrer_id = None
        if referral_code and isinstance(referral_code, str) and referral_code.startswith("REF"):
            try:
                rid = int(referral_code[3:])
                if rid != telegram_id:
                    referrer_id = rid
            except (ValueError, TypeError):
                referrer_id = None

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                existing_id = await conn.fetchval(
                    "SELECT id FROM users WHERE id = $1", telegram_id
                )
                if existing_id:
                    row = await conn.fetchrow("SELECT * FROM users WHERE id = $1", telegram_id)
                    return dict(row)

                phone_taken = await conn.fetchval(
                    "SELECT id FROM users WHERE phone = $1", phone
                )
                if phone_taken:
                    raise ValueError("Bu telefon raqam boshqa foydalanuvchiga tegishli!")

                if referrer_id:
                    exists = await conn.fetchval(
                        "SELECT 1 FROM users WHERE id = $1", referrer_id
                    )
                    if not exists:
                        referrer_id = None

                row = await conn.fetchrow(
                    """
                    INSERT INTO users (id, username, full_name, phone, referred_by)
                    VALUES ($1, $2, $3, $4, $5)
                    RETURNING *
                    """,
                    telegram_id, username, full_name, phone, referrer_id,
                )
                user = dict(row)

                if referrer_id:
                    try:
                        await conn.execute(
                            "INSERT INTO referrals (referrer_id, referred_id) VALUES ($1, $2)",
                            referrer_id, telegram_id,
                        )
                        await conn.execute(
                            "UPDATE users SET score = score + 1 WHERE id = $1", referrer_id
                        )
                    except asyncpg.UniqueViolationError:
                        pass

        return user

    async def update_user_balance(
        self, user_id: int, amount: int, operation: str = "add"
    ) -> int:
        if amount < 0:
            raise ValueError("Summa manfiy bo'lishi mumkin emas")

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                if operation == "subtract":
                    row = await conn.fetchrow(
                        """
                        UPDATE users
                        SET balance = balance - $1, spent = spent + $1
                        WHERE id = $2 AND balance >= $1
                        RETURNING balance
                        """,
                        amount, user_id,
                    )
                    if not row:
                        raise ValueError("Balansda mablag' yetarli emas")
                else:
                    row = await conn.fetchrow(
                        "UPDATE users SET balance = balance + $1 WHERE id = $2 RETURNING balance",
                        amount, user_id,
                    )
                    if not row:
                        raise ValueError("Foydalanuvchi topilmadi")
        return row["balance"]

    async def check_mute(self, user_id: int) -> bool:
        async with self.pool.acquire() as conn:
            until = await conn.fetchval(
                "SELECT mute_until FROM users WHERE id = $1", user_id
            )
        if not until:
            return False
        return until > datetime.utcnow()

    async def mute_user(self, user_id: int, hours: int = 24) -> bool:
        until = datetime.utcnow() + timedelta(hours=hours)
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE users SET mute_until = $1 WHERE id = $2", until, user_id
            )
        return result != "UPDATE 0"

    async def add_warning(self, user_id: int) -> int:
        async with self.pool.acquire() as conn:
            count = await conn.fetchval(
                "UPDATE users SET warn_count = warn_count + 1 WHERE id = $1 RETURNING warn_count",
                user_id,
            )
        return count or 0

    async def block_user(self, user_id: int) -> bool:
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE users SET is_banned = TRUE WHERE id = $1", user_id
            )
        return result != "UPDATE 0"

    async def unblock_user(self, user_id: int) -> bool:
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE users SET is_banned = FALSE WHERE id = $1", user_id
            )
        return result != "UPDATE 0"

    async def add_score_by_phone_batch(self, phone: str, score: int) -> bool:
        digits = "".join(c for c in phone if c.isdigit())
        if len(digits) < 9:
            return False
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE users SET score = score + $1 WHERE phone LIKE $2",
                score, f"%{digits[-9:]}",
            )
        return result != "UPDATE 0"

    async def get_top_10_users(self) -> list:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM users ORDER BY score DESC, user_number ASC LIMIT 10"
            )
        return [dict(r) for r in rows]

    async def get_top_participants(self, min_score: int = 15) -> list:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM users WHERE score >= $1 ORDER BY score DESC",
                min_score,
            )
        return [dict(r) for r in rows]

    async def get_referrals_by_user(self, user_id: int) -> list:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT u.*, r.created_at AS referred_at
                FROM referrals r
                JOIN users u ON u.id = r.referred_id
                WHERE r.referrer_id = $1
                ORDER BY r.created_at DESC
                """,
                user_id,
            )
        return [dict(r) for r in rows]

    async def get_referrer_of_user(self, user_id: int) -> Optional[dict]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT u.* FROM referrals r
                JOIN users u ON u.id = r.referrer_id
                WHERE r.referred_id = $1
                """,
                user_id,
            )
        return dict(row) if row else None

    # ==========================================================================
    # ADS
    # ==========================================================================

    async def create_ad(self, **kwargs) -> dict:
        user_id = kwargs.get("user_id")
        ad_type = kwargs.get("ad_type", "sotish")
        tariff = kwargs.get("tariff", "bot")
        photos = kwargs.get("photos") or []
        breed = kwargs.get("breed")
        age = kwargs.get("age")
        gender = kwargs.get("gender")
        health = kwargs.get("health")
        sterilization = kwargs.get("sterilization")
        address = kwargs.get("address")
        phone = kwargs.get("phone")
        price = str(kwargs.get("price", "0"))
        currency = kwargs.get("currency", "so'm")
        ad_number = kwargs.get("ad_number")
        cat_count = int(kwargs.get("cat_count", 1) or 1)
        price_paid = int(kwargs.get("price_paid", 0) or 0)

        photos_json = json.dumps(photos, ensure_ascii=False)

        expires_at = None
        if tariff in ("web_only", "web_and_channel"):
            expires_at = datetime.utcnow() + timedelta(days=Settings.WEB_AD_DAYS)

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    INSERT INTO ads (
                        user_id, ad_type, tariff, photos, breed, age, gender,
                        health, sterilization, address, phone, price, currency,
                        ad_number, cat_count, price_paid, expires_at
                    ) VALUES (
                        $1, $2, $3, $4::jsonb, $5, $6, $7, $8, $9, $10,
                        $11, $12, $13, $14, $15, $16, $17
                    ) RETURNING *
                    """,
                    user_id, ad_type, tariff, photos_json, breed, age, gender,
                    health, sterilization, address, phone, price, currency,
                    ad_number, cat_count, price_paid, expires_at,
                )
                await conn.execute(
                    "UPDATE users SET ad_count = ad_count + 1 WHERE id = $1",
                    user_id,
                )

        return self._parse_ad(row)

    async def get_ad(self, ad_id: int) -> Optional[dict]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM ads WHERE id = $1", ad_id)
        return self._parse_ad(row)

    async def get_user_ads(self, user_id: int) -> list:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM ads WHERE user_id = $1 ORDER BY created_at DESC",
                user_id,
            )
        return [self._parse_ad(r) for r in rows]

    async def get_pending_ads(self) -> list:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT a.*, u.user_number, u.full_name, u.username
                FROM ads a
                LEFT JOIN users u ON u.id = a.user_id
                WHERE a.status = 'pending'
                ORDER BY a.created_at ASC
                """
            )
        return [self._parse_ad(r) for r in rows]

    async def get_active_web_ads(self) -> list:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT a.*, u.user_number, u.full_name
                FROM ads a
                LEFT JOIN users u ON u.id = a.user_id
                WHERE a.status = 'approved'
                  AND a.tariff IN ('web_only', 'web_and_channel')
                  AND (a.expires_at IS NULL OR a.expires_at > NOW())
                ORDER BY a.created_at DESC
                LIMIT 200
                """
            )
        return [self._parse_ad(r) for r in rows]

    async def update_ad_status(
        self,
        ad_id: int,
        status: str,
        channel_message_id: Optional[int] = None,
        reason: Optional[str] = None,
    ):
        async with self.pool.acquire() as conn:
            if channel_message_id is not None:
                await conn.execute(
                    """
                    UPDATE ads
                    SET status = $1, channel_message_id = $2, reject_reason = $3
                    WHERE id = $4
                    """,
                    status, channel_message_id, reason, ad_id,
                )
            else:
                await conn.execute(
                    "UPDATE ads SET status = $1, reject_reason = $2 WHERE id = $3",
                    status, reason, ad_id,
                )

    async def update_ad_details(self, ad_id: int, **fields):
        allowed = {
            "breed", "age", "gender", "health", "sterilization",
            "address", "phone", "price", "currency", "cat_count",
        }
        pairs = [(k, v) for k, v in fields.items() if k in allowed and v is not None]
        if not pairs:
            return

        set_clause = ", ".join(f"{k} = ${i + 1}" for i, (k, _) in enumerate(pairs))
        values = [v for _, v in pairs]
        values.append(ad_id)

        async with self.pool.acquire() as conn:
            await conn.execute(
                f"UPDATE ads SET {set_clause} WHERE id = ${len(values)}",
                *values,
            )

    async def delete_ad(self, ad_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute("DELETE FROM ads WHERE id = $1", ad_id)

    async def cleanup_expired_ads(self):
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE ads
                SET status = 'expired'
                WHERE status = 'approved'
                  AND tariff IN ('web_only', 'web_and_channel')
                  AND expires_at IS NOT NULL
                  AND expires_at <= NOW()
                """
            )

    # ==========================================================================
    # SETTINGS
    # ==========================================================================

    async def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        async with self.pool.acquire() as conn:
            val = await conn.fetchval("SELECT value FROM settings WHERE key = $1", key)
        return val if val is not None else default

    async def set_setting(self, key: str, value: str):
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO settings (key, value) VALUES ($1, $2)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                """,
                key, value,
            )

    # ==========================================================================
    # CARDS
    # ==========================================================================

    async def get_active_card(self) -> Optional[dict]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM cards WHERE is_active = TRUE ORDER BY created_at DESC LIMIT 1"
            )
        return dict(row) if row else None

    async def add_card(self, number: str, holder: str) -> int:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("UPDATE cards SET is_active = FALSE")
                row = await conn.fetchrow(
                    "INSERT INTO cards (number, holder, is_active) VALUES ($1, $2, TRUE) RETURNING id",
                    number, holder,
                )
        return row["id"]

    # ==========================================================================
    # PAYMENTS
    # ==========================================================================

    async def create_payment_request(
        self, user_id: int, amount: int, card_id: int, card_last4: str
    ) -> int:
        expires_at = datetime.utcnow() + timedelta(minutes=Settings.TOPUP_TIMER_MINUTES)
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO payments (user_id, amount, card_id, card_last4, expires_at)
                VALUES ($1, $2, $3, $4, $5) RETURNING id
                """,
                user_id, amount, card_id, card_last4, expires_at,
            )
        return row["id"]

    async def attach_receipt(self, payment_id: int, file_name: str):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE payments SET receipt_file_id = $1 WHERE id = $2",
                file_name, payment_id,
            )

    async def match_userbot_payment(self, amount: int, last4: str) -> Optional[int]:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    SELECT id, user_id FROM payments
                    WHERE status = 'pending'
                      AND amount = $1
                      AND card_last4 = $2
                      AND userbot_matched = FALSE
                      AND (expires_at IS NULL OR expires_at > NOW())
                    ORDER BY created_at ASC
                    LIMIT 1
                    FOR UPDATE
                    """,
                    amount, last4,
                )

                if not row:
                    await conn.execute(
                        "INSERT INTO userbot_payments (amount, last4, matched) VALUES ($1, $2, FALSE)",
                        amount, last4,
                    )
                    return None

                payment_id = row["id"]
                user_id = row["user_id"]

                await conn.execute(
                    "UPDATE payments SET status = 'paid', userbot_matched = TRUE WHERE id = $1",
                    payment_id,
                )
                await conn.execute(
                    "UPDATE users SET balance = balance + $1 WHERE id = $2",
                    amount, user_id,
                )
                await conn.execute(
                    "INSERT INTO userbot_payments (amount, last4, matched_user_id, matched) VALUES ($1, $2, $3, TRUE)",
                    amount, last4, user_id,
                )

        return user_id

    # ==========================================================================
    # STATISTIKA
    # ==========================================================================

    async def get_statistics(self) -> dict:
        async with self.pool.acquire() as conn:
            total_users = await conn.fetchval("SELECT COUNT(*) FROM users") or 0
            total_ads = await conn.fetchval("SELECT COUNT(*) FROM ads") or 0

            today_income = await conn.fetchval(
                """
                SELECT COALESCE(SUM(price_paid), 0) FROM ads
                WHERE price_paid > 0 AND created_at >= CURRENT_DATE
                """
            ) or 0

            month_income = await conn.fetchval(
                """
                SELECT COALESCE(SUM(price_paid), 0) FROM ads
                WHERE price_paid > 0
                  AND created_at >= date_trunc('month', CURRENT_DATE)
                """
            ) or 0

        return {
            "total_users": int(total_users),
            "total_ads": int(total_ads),
            "today_income": int(today_income),
            "month_income": int(month_income),
        }

    # ==========================================================================
    # RESET (Ehtiyotkorlik bilan ishlatiladi)
    # ==========================================================================

    async def reset_tables(self):
        if self.pool is None:
            raise RuntimeError("Pool yaratilmagan. Avval connect() chaqiring.")
        async with self.pool.acquire() as conn:
            for tbl in (
                "userbot_payments", "referrals", "payments", "ads",
                "cards", "userbot_sessions", "settings", "users",
            ):
                await conn.execute(f"DROP TABLE IF EXISTS {tbl} CASCADE")
        await self._create_tables()
        logger.warning("⚠️ Barcha jadvallar qayta yaratildi (ma'lumotlar o'chirildi)")

# ==============================================================================
# MODUL DARAJASIDA YAGONA INSTANSIYA
# ==============================================================================
db = Database()
