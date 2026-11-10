# ==============================================================================
# LOYIHA: UzbekCats Bot & Web App
# FAYL: main.py
# TAVSIF: Bot (aiogram) va API (FastAPI) ni bitta jarayonda ishga tushirish
# ==============================================================================

import asyncio
import uvicorn
import logging
from db import db
from bot import bot, dp, start_userbot
from api import app

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# DB connect() ni ikki marta chaqirilmasligi uchun xavfsiz qilamiz
_original_connect = db.connect
async def _safe_connect():
    if db.pool is None:
        await _original_connect()
db.connect = _safe_connect


async def start_bot_polling():
    """Botni polling rejimida ishga tushirish."""
    logger.info("🤖 Bot polling boshlanmoqda...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


async def start_api_server():
    """FastAPI serverni ishga tushirish (0.0.0.0:PORT)."""
    logger.info("🌐 FastAPI server boshlanmoqda...")
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
        access_log=False
    )
    server = uvicorn.Server(config)
    await server.serve()


async def initialize_userbot():
    """Bazada saqlangan userbot sessiyasini yuklash."""
    try:
        async with db.pool.acquire() as conn:
            session = await conn.fetchval(
                "SELECT session_string FROM userbot_sessions WHERE is_active = TRUE LIMIT 1"
            )
            if session:
                asyncio.create_task(start_userbot(session))
                logger.info("✅ Userbot ishga tushirildi")
            else:
                logger.info("ℹ️ Userbot sessiyasi topilmadi (hali qo'shilmagan)")
    except Exception as e:
        logger.warning(f"⚠️ Userbot yuklanmadi: {e}")


async def main():
    logger.info("=" * 60)
    logger.info("🚀 UzbekCats Bot & API ishga tushmoqda...")
    logger.info("=" * 60)

    # 1. Bazaga ulanish
    await db.connect()

    # 2. Userbot (agar mavjud bo'lsa)
    await initialize_userbot()

    # 3. Bot va API ni parallel ishga tushirish
    await asyncio.gather(
        start_bot_polling(),
        start_api_server()
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Dastur foydalanuvchi tomonidan to'xtatildi")
    except Exception as e:
        logger.error(f"❌ Xatolik: {e}")