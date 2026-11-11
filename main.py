import asyncio
import logging
import uvicorn
from api import app
from bot import bot, dp, on_startup, on_shutdown, start_userbot
from db import db

logging.basicConfig(level=logging.INFO)

async def run_bot():
    try:
        await on_startup() # DB ga ulanish
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except Exception as e:
        logging.error(f"Bot xatosi: {e}")

async def run_api():
    config = uvicorn.Config("api:app", host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

async def main():
    # Bot va API ni bir vaqtda ishga tushirish
    await asyncio.gather(
        run_bot(),
        run_api()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
