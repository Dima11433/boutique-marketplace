import asyncio
import logging
import uvicorn
import config
from database import init_db
from bot import dp, bot
from web import app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("main")

async def main():
    logger.info("Initializing database...")
    await init_db()
    logger.info("Database initialized successfully.")

    server_config = uvicorn.Config(
        app=app,
        host="0.0.0.0",
        port=config.SERVER_PORT,
        log_level="info",
        access_log=False
    )
    server = uvicorn.Server(server_config)

    logger.info(f"Starting Web Marketplace on http://localhost:{config.SERVER_PORT}")
    logger.info("Starting Telegram Worker Bot...")

    try:
        await asyncio.gather(
            server.serve(),
            dp.start_polling(bot)
        )
    except asyncio.CancelledError:
        logger.info("Shutting down services...")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Application stopped.")
