import asyncio
import logging
import uvicorn
import config
from database import init_db
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

    logger.info(f"Starting MODEVA Luxury Marketplace on http://localhost:{config.SERVER_PORT}")

    try:
        await server.serve()
    except asyncio.CancelledError:
        logger.info("Shutting down marketplace server...")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Application stopped.")
