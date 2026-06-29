"""
main.py

Skeleton / Entry Point

Job:
Initialize the database, start the trade engine in a background
thread, and start the aiogram v2 polling loop on the main thread.

Nothing else lives here.

Usage:
    python main.py
"""

import logging
import asyncio
import threading
from aiogram import executor

from data.database import init_db
from services.trade_engine import run_forever
from services.scheduler import start_scheduler
from services.live_monitor import run_live_monitor
from bot.setup import bot, dp
from bot.notification_handler import process_events
from config import BOT_TOKEN

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# aiogram v2 startup hook
# Runs inside the event loop right before polling begins.
# We use it to launch the event bus consumer as a background task.
# ------------------------------------------------------------------
async def on_startup(dispatcher) -> None:
    logger.info("[main] Bot polling started.")
    asyncio.create_task(process_events(bot))
    asyncio.create_task(run_live_monitor())
    start_scheduler(bot)
    logger.info("[main] All services running (event bus + live monitor + scheduler).")


async def on_shutdown(dispatcher) -> None:
    logger.info("[main] Bot shutting down.")


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------
if __name__ == "__main__":
    init_db()

    # Run the synchronous trade engine in a background daemon thread.
    # Daemon=True means it auto-stops when the main process exits.
    engine_thread = threading.Thread(target=run_forever, daemon=True, name="TradeEngine")
    engine_thread.start()
    logger.info("[main] Trade engine thread started.")

    # Decide whether to start polling or run engine-only mode.
    token_is_real = BOT_TOKEN and "your_bot_token" not in BOT_TOKEN

    if token_is_real:
        # aiogram v2: executor.start_polling blocks until Ctrl+C
        executor.start_polling(
            dp,
            skip_updates=True,
            on_startup=on_startup,
            on_shutdown=on_shutdown,
        )
    else:
        # No token set — run the engine without Telegram for local testing
        logger.warning("[main] No valid BOT_TOKEN found. Running in engine-only mode.")
        try:
            engine_thread.join()
        except KeyboardInterrupt:
            logger.info("[main] Shutting down.")