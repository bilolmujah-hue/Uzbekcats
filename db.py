# ==============================================================================
# LOYIHA: UzbekCats Bot & Web App
# FAYL: db.py
# TAVSIF: PostgreSQL — ultra tez, to'liq CRUD, indekslar, kesh, pool
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

class DBError(Exception):
    pass


class InsufficientBalanceError(DBError):
    pass


class PhoneTakenError(DBError):
    pass


class UserNotFoundError(DBError):
    pass


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
    """photos'ni har xil formatdan listga keltiradi."""
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

    # ==========================================================================
    # ULANISH / UZILISH
    # ==========================================================================

    async def _init_connection(self, conn: asyncpg.Connection):
        """Har bir yangi ulanish uchun sozlamalar."""
        try:
            await conn.execute("SET application_name = 'uzbekcats_bot'")
        except Exception:
            pass

    async def connect(self):
        """Bazaga ulanadi va jadvallarni yaratadi (tezlashtirilgan pool)."""
        try:
            self.pool = await asyncpg.create_pool(
                dsn=BotConfig.DATABASE_URL,
                min_size=10,
                max_size=40,
                max_queries=50000,
                max_inactive_connection_lifetime=300,
                max_cached_statement_lifetime=300,
                max_cacheable_statement_size=16384,
                statement_cache_size=500,
                command_timeout=30,
                timeout=15,
                init=self._init_connection,
            )
            logger.info("✅ PostgreSQL ulanish pool tayyor (10–40)")
            await self.create_tables()
            await self._warm_cache()
        except Exception as e:
            logger.critical(f"❌ Bazaga ulanishda xatolik: {e}")
            raise

    async def disconnect(self):
        """Bazadan uziladi."""
        if self.pool:
            await self.pool.close()
            logger.info("🔌 PostgreSQL uzildi")

    async def _warm_cache(self):
        """Sozlamalarni keshga oldindan yuklaydi."""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("SELECT key, value FROM settings")
            for row in rows:
                self._settings_cache[row["key"]] = row["value"]
            logger.info(f"✅ Kesh tayyor: {len(self._settings_cache)} sozlama")
        except Exception as e:
            logger.warning(f"Kesh yuklashda xato: {e}")

    # ==========================================================================
    # JADVALLAR + INDEKSLAR (migratsiya)
    # ==========================================================================

    async def create_tables(self):
        """Barcha jadval va indekslarni yaratadi (idempotent)."""
        queries = [
            # -------- USERS --------
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
                last_ad_time TIMESTAMP
            );
            """,
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS spent INTEGER DEFAULT 0;",

            # -------- CARDS --------
            """
            CREATE TABLE IF NOT EXISTS cards (
                id SERIAL PRIMARY KEY,
                number VARCHAR(20) NOT NULL,
                holder VARCHAR(100) NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,

            # -------- PAYMENTS --------
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

            # -------- ADS --------
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
            "ALTER TABLE ads ADD COLUMN IF NOT EXISTS cat_count INTEGER DEFAULT 1;",
            "ALTER TABLE ads ADD COLUMN IF NOT EXISTS price_paid INTEGER DEFAULT 0;",

            # -------- REFERRALS --------
            """
            CREATE TABLE IF NOT EXISTS referrals (
                referrer_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
                referred_id BIGINT REFERENCES users(id) ON DELETE CASCADE UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (referrer_id, referred_id)
            );
            """,

            # -------- SETTINGS --------
            """
            CREATE TABLE IF NOT EXISTS settings (
                key VARCHAR(50) PRIMARY KEY,
                value TEXT
            );
            """,

            # -------- USERBOT SESSIONS --------
            """
            CREATE TABLE IF NOT EXISTS userbot_sessions (
                id SERIAL PRIMARY KEY,
                phone VARCHAR(20) NOT NULL,
                session_string TEXT NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,

            # ================= INDEKSLAR =================
            "CREATE INDEX IF NOT EXISTS idx_users_user_number ON users(user_number);",
            "CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone);",
            "CREATE INDEX IF NOT EXISTS idx_users_score ON users(score DESC) WHERE is_banned = FALSE;",
            "CREATE INDEX IF NOT EXISTS idx_users_banned ON users(is_banned) WHERE is_banned = TRUE;",
            "CREATE INDEX IF NOT EXISTS idx_users_registered ON users(registered_at DESC);",

            "CREATE INDEX IF NOT EXISTS idx_ads_user_id ON ads(user_id);",
            "CREATE INDEX IF NOT EXISTS idx_ads_status ON ads(status);",
            "CREATE INDEX IF NOT EXISTS idx_ads_status_created ON ads(status, created_at DESC);",
            "CREATE INDEX IF NOT EXISTS idx_ads_web_active ON ads(created_at DESC) "
            "WHERE status = 'approved' AND tariff IN ('web_only', 'web_and_channel', 'web');",
            "CREATE INDEX IF NOT EXISTS idx_ads_pending ON ads(created_at DESC) WHERE status = 'pending';",
            "CREATE INDEX IF NOT EXISTS idx_ads_expires ON ads(expires_at) "
            "WHERE expires_at IS NOT NULL AND status = 'approved';",
            "CREATE INDEX IF NOT EXISTS idx_ads_photos_gin ON ads USING GIN (photos);",

            "CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payments(user_id);",
            "CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status);",
            "CREATE INDEX IF NOT EXISTS idx_payments_pending ON payments(status, expires_at) WHERE status = 'pending';",
            "CREATE INDEX IF NOT EXISTS idx_payments_match ON payments(amount, card_last4, expires_at) "
            "WHERE status = 'pending';",

            "CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_id);",
            "CREATE INDEX IF NOT EXISTS idx_referrals_referred ON referrals(referred_id);",

            "CREATE INDEX IF NOT EXISTS idx_userbot_active ON userbot_sessions(is_active) WHERE is_active = TRUE;",
        ]

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                for q in queries:
                    try:
                        await conn.execute(q)
                    except Exception as e:
                        logger.warning(f"SQL xato (davom etamiz): {e}")
        logger.info("✅ Jadvallar va indekslar tayyor")

    # ==========================================================================
    # USERS
    # ==========================================================================

    async def get_user(self, user_id: int) -> Optional[dict]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
        return dict(row) if row else None

    async def get_user_by_number(self, user_number: int) -> Optional[dict]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE user_number = $1", user_number
            )
        return dict(row) if row else None

    async def get_user_by_phone(self, phone: str) -> Optional[dict]:
        normalized = _normalize_phone(phone)
        if not normalized:
            return None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE phone = $1", normalized
            )
        return dict(row) if row else None

    async def create_user(
        self,
        user_id: int,
        username: str,
        full_name: str,
        phone: str,
        referral_code: str = None,
    ) -> dict:
        """
        Yangi foydalanuvchi yaratish. Agar mavjud bo'lsa — qaytaradi.
        Phone boshqa foydalanuvchida bo'lsa — PhoneTakenError.
        Referral kod bilan kelgan bo'lsa — referal qo'shiladi +1 ball.
        """
        normalized_phone = _normalize_phone(phone)
        if not normalized_phone:
            raise DBError("Telefon raqam bo'sh")

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # 1. Mavjud foydalanuvchini tekshirish (1 round trip)
                existing = await conn.fetchrow(
                    "SELECT * FROM users WHERE id = $1", user_id
                )
                if existing:
                    return dict(existing)

                # 2. INSERT (phone unique buzilsa IntegrityError)
                try:
                    row = await conn.fetchrow(
                        """
                        INSERT INTO users (id, username, full_name, phone)
                        VALUES ($1, $2, $3, $4) RETURNING *
                        """,
                        user_id, username, full_name, normalized_phone,
                    )
                except asyncpg.UniqueViolationError:
                    raise PhoneTakenError("Bu telefon raqam boshqa foydalanuvchiga tegishli!")

                user = dict(row)

                # 3. Referral (agar bo'lsa)
                if referral_code and str(referral_code).startswith("REF"):
                    try:
                        referrer_id = int(str(referral_code).replace("REF", ""))
                    except ValueError:
                        referrer_id = None

                    if referrer_id and referrer_id != user_id:
                        try:
                            await conn.execute(
                                """
                                INSERT INTO referrals (referrer_id, referred_id)
                                VALUES ($1, $2) ON CONFLICT DO NOTHING
                                """,
                                referrer_id, user_id,
                            )
                            await conn.execute(
                                "UPDATE users SET score = score + 1 WHERE id = $1",
                                referrer_id,
                            )
                        except Exception as e:
                            logger.warning(f"Referral qo'shishda xato: {e}")

                return user

    async def update_user_balance(
        self, user_id: int, amount: int, operation: str = "add"
    ) -> int:
        """Balansni o'zgartirish. Atomic. 'subtract' da balans yetmasa — xato."""
        if amount < 0:
            raise DBError("Summa manfiy bo'lmaydi")
        async with self.pool.acquire() as conn:
            if operation == "add":
                new_balance = await conn.fetchval(
                    "UPDATE users SET balance = balance + $1 WHERE id = $2 RETURNING balance",
                    amount, user_id,
                )
                if new_balance is None:
                    raise UserNotFoundError("Foydalanuvchi topilmadi")
                return new_balance
            else:
                new_balance = await conn.fetchval(
                    """
                    UPDATE users SET balance = balance - $1, spent = spent + $1
                    WHERE id = $2 AND balance >= $1
                    RETURNING balance
                    """,
                    amount, user_id,
                )
                if new_balance is None:
                    raise InsufficientBalanceError("Hisobda mablag' yetarli emas!")
                return new_balance

    async def update_user_score(self, user_id: int, score: int) -> int:
        async with self.pool.acquire() as conn:
            new = await conn.fetchval(
                "UPDATE users SET score = score + $1 WHERE id = $2 RETURNING score",
                score, user_id,
            )
        return new or 0

    async def add_score_by_phone_batch(self, phone: str, score: int) -> bool:
        normalized = _normalize_phone(phone)
        if not normalized:
            return False
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE users SET score = score + $1 WHERE phone = $2",
                score, normalized,
            )
        return result != "UPDATE 0"

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

    async def get_banned_users(self) -> List[dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM users WHERE is_banned = TRUE ORDER BY user_number ASC"
            )
        return [dict(r) for r in rows]

    async def get_top_10_users(self) -> List[dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, user_number, full_name, phone, score, username
                FROM users WHERE is_banned = FALSE
                ORDER BY score DESC, registered_at ASC LIMIT 10
                """
            )
        return [dict(r) for r in rows]

    async def get_top_participants(self, min_score: int = 15, limit: int = 100) -> List[dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, user_number, full_name, phone, score, username
                FROM users
                WHERE score >= $1 AND is_banned = FALSE
                ORDER BY score DESC, registered_at ASC LIMIT $2
                """,
                min_score, limit,
            )
        return [dict(r) for r in rows]

    async def get_detailed_user_stats(self, user_id: int) -> Optional[dict]:
        """Bitta query bilan: user + ads_count + referrals_count + paid_total."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT u.*,
                    (SELECT COUNT(*) FROM ads WHERE user_id = u.id) AS ads_count,
                    (SELECT COUNT(*) FROM referrals WHERE referrer_id = u.id) AS referrals_count,
                    (SELECT COALESCE(SUM(amount), 0) FROM payments
                        WHERE user_id = u.id AND status = 'paid') AS paid_total
                FROM users u WHERE u.id = $1
                """,
                user_id,
            )
        return dict(row) if row else None

    # ==========================================================================
    # REFERRALS
    # ==========================================================================

    async def get_referrals_by_user(self, user_id: int) -> List[dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT u.id, u.user_number, u.full_name, u.username, u.score,
                       r.created_at AS referred_at
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
                SELECT u.id, u.user_number, u.full_name, u.username, u.score,
                       r.created_at AS referred_at
                FROM referrals r
                JOIN users u ON u.id = r.referrer_id
                WHERE r.referred_id = $1
                """,
                user_id,
            )
        return dict(row) if row else None

    # ==========================================================================
    # ADS
    # ==========================================================================

    async def create_ad(
        self,
        user_id: int,
        ad_type: str,
        tariff: str,
        photos: list,
        breed: str,
        age: str,
        gender: str,
        health: str,
        sterilization: str,
        address: str,
        phone: str,
        price: str,
        currency: str,
        ad_number: int,
        cat_count: int = 1,
        price_paid: Optional[int] = None,
    ) -> dict:
        """Yangi reklama + user.ad_count++. price_paid avtomatik hisoblanadi."""
        expires_at = None
        if tariff in ("web_only", "web_and_channel", "web"):
            days = await self.get_setting("web_ad_days", str(Settings.WEB_AD_DAYS))
            try:
                expires_at = datetime.utcnow() + timedelta(days=int(days))
            except (ValueError, TypeError):
                expires_at = datetime.utcnow() + timedelta(days=Settings.WEB_AD_DAYS)

        # price_paid ni avtomatik hisoblash (agar berilmagan bo'lsa)
        if price_paid is None:
            price_map = {
                "web_only": Prices.TARIFF_WEB,
                "channel_only": Prices.TARIFF_CHANNEL,
                "web_and_channel": Prices.TARIFF_BOTH,
                "bot": Prices.BOT_PRICES,
            }
            mapping = price_map.get(tariff, {})
            price_paid = mapping.get(max(1, min(5, cat_count)), 0)

        photos_json = json.dumps(photos or [])

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                actual_ad_number = await conn.fetchval(
                    """
                    UPDATE users SET ad_count = ad_count + 1,
                                     last_ad_time = CURRENT_TIMESTAMP
                    WHERE id = $1 RETURNING ad_count
                    """,
                    user_id,
                )
                if actual_ad_number is None:
                    raise UserNotFoundError("Foydalanuvchi topilmadi")

                row = await conn.fetchrow(
                    """
                    INSERT INTO ads (
                        user_id, ad_type, tariff, photos, breed, age, gender,
                        health, sterilization, address, phone, price, currency,
                        ad_number, cat_count, price_paid, expires_at
                    )
                    VALUES ($1,$2,$3,$4::jsonb,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17)
                    RETURNING *
                    """,
                    user_id, ad_type, tariff, photos_json, breed, age, gender,
                    health, sterilization, address, phone, price, currency,
                    actual_ad_number, cat_count, price_paid, expires_at,
                )
        return dict(row)

    async def get_user_ads(self, user_id: int) -> List[dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM ads WHERE user_id = $1 ORDER BY created_at DESC",
                user_id,
            )
        return [dict(r) for r in rows]

    async def get_active_web_ads(self) -> List[dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM ads
                WHERE status = 'approved'
                  AND tariff IN ('web_only', 'web_and_channel', 'web')
                  AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
                ORDER BY created_at DESC
                """
            )
        return [dict(r) for r in rows]

    async def get_pending_ads(self) -> List[dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM ads WHERE status = 'pending' ORDER BY created_at DESC"
            )
        return [dict(r) for r in rows]

    async def update_ad_status(
        self,
        ad_id: int,
        status: str,
        reason: str = None,
        channel_message_id: int = None,
        channel_link: str = None,
    ):
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

    async def cleanup_expired_ads(self, force: bool = False) -> int:
        """Muddati o'tgan reklamalarni o'chirish (60 sek throttled)."""
        now = datetime.utcnow()
        if not force and self._last_cleanup and (now - self._last_cleanup).total_seconds() < 60:
            return 0
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE ads SET status = 'expired'
                WHERE status = 'approved'
                  AND expires_at IS NOT NULL
                  AND expires_at < CURRENT_TIMESTAMP
                """
            )
        self._last_cleanup = now
        try:
            return int(result.split()[-1])
        except (ValueError, IndexError):
            return 0

    # ==========================================================================
    # CARDS
    # ==========================================================================

    async def add_card(self, number: str, holder: str) -> int:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("UPDATE cards SET is_active = FALSE")
                card_id = await conn.fetchval(
                    """
                    INSERT INTO cards (number, holder, is_active)
                    VALUES ($1, $2, TRUE) RETURNING id
                    """,
                    number, holder,
                )
        return card_id

    async def get_active_card(self) -> Optional[dict]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM cards WHERE is_active = TRUE ORDER BY id DESC LIMIT 1"
            )
        return dict(row) if row else None

    # ==========================================================================
    # PAYMENTS
    # ==========================================================================

    async def create_payment_request(
        self, user_id: int, amount: int, card_id: int, card_last4: str
    ) -> int:
        expires_at = datetime.utcnow() + timedelta(minutes=Settings.TOPUP_TIMER_MINUTES)
        async with self.pool.acquire() as conn:
            payment_id = await conn.fetchval(
                """
                INSERT INTO payments (user_id, amount, card_id, card_last4, expires_at)
                VALUES ($1, $2, $3, $4, $5) RETURNING id
                """,
                user_id, amount, card_id, card_last4, expires_at,
            )
        return payment_id

    async def attach_receipt(self, payment_id: int, file_id: str):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE payments SET receipt_file_id = $1 WHERE id = $2",
                file_id, payment_id,
            )

    async def match_userbot_payment(self, amount: int, card_last4: str) -> Optional[int]:
        """
        Userbot xabarini to'lovga moslashtirish (atomic).
        Mos kelsa: status='paid' + balans qo'shiladi.
        """
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                payment = await conn.fetchrow(
                    """
                    SELECT id, user_id FROM payments
                    WHERE amount = $1 AND card_last4 = $2 AND status = 'pending'
                      AND expires_at > CURRENT_TIMESTAMP
                    ORDER BY created_at ASC LIMIT 1
                    FOR UPDATE SKIP LOCKED
                    """,
                    amount, card_last4,
                )
                if not payment:
                    return None

                await conn.execute(
                    "UPDATE payments SET status = 'paid', userbot_matched = TRUE WHERE id = $1",
                    payment["id"],
                )
                await conn.execute(
                    "UPDATE users SET balance = balance + $1 WHERE id = $2",
                    amount, payment["user_id"],
                )
                return payment["user_id"]

    # ==========================================================================
    # SETTINGS (in-memory cache)
    # ==========================================================================

    async def get_setting(self, key: str, default: str = None) -> Optional[str]:
        if key in self._settings_cache:
            return self._settings_cache[key]
        async with self.pool.acquire() as conn:
            val = await conn.fetchval(
                "SELECT value FROM settings WHERE key = $1", key
            )
        if val is None:
            return default
        self._settings_cache[key] = val
        return val

    async def set_setting(self, key: str, value: str):
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO settings (key, value) VALUES ($1, $2)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                """,
                key, value,
            )
        self._settings_cache[key] = value

    # ==========================================================================
    # STATISTIKA (1 query — 1 round trip)
    # ==========================================================================

    async def get_statistics(self) -> dict:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    (SELECT COUNT(*) FROM users) AS total_users,
                    (SELECT COUNT(*) FROM users WHERE is_banned = TRUE) AS banned_users,
                    (SELECT COUNT(*) FROM ads) AS total_ads,
                    (SELECT COUNT(*) FROM ads WHERE status = 'pending') AS pending_ads,
                    (SELECT COALESCE(SUM(amount), 0) FROM payments
                        WHERE status = 'paid' AND created_at >= CURRENT_DATE) AS today_income,
                    (SELECT COALESCE(SUM(amount), 0) FROM payments
                        WHERE status = 'paid' AND created_at >= date_trunc('month', CURRENT_DATE)) AS month_income,
                    (SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'paid') AS total_income
                """
            )

        month_income = int(row["month_income"] or 0)
        tech_cut = int(month_income * (Settings.TECH_ADMIN_PERCENT / 100))

        return {
            "total_users": int(row["total_users"] or 0),
            "banned_users": int(row["banned_users"] or 0),
            "total_ads": int(row["total_ads"] or 0),
            "pending_ads": int(row["pending_ads"] or 0),
            "today_income": int(row["today_income"] or 0),
            "month_income": month_income,
            "total_income": int(row["total_income"] or 0),
            "tech_admin_cut_month": tech_cut,
        }


# ==============================================================================
# SINGLETON
# ==============================================================================
db = Database()
