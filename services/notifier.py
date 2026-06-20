"""
notifier.py

Services / Alerts

Job:
Sends direct Telegram alerts to all ADMIN_IDS for system health
monitoring. Differentiates between soft errors (handled) and
red errors (requires attention).
"""

import logging
from aiogram import Bot
from aiogram.types import ParseMode

from config import ADMIN_IDS

logger = logging.getLogger(__name__)

async def notify_soft_error(bot: Bot, message: str) -> None:
    """
    Soft Error: Something didn't go as planned, but the bot handled it
    gracefully (e.g., skipped a post because there was no data).
    """
    text = f"🟡 *Soft Error*\n\n{message}"
    logger.warning(f"[notifier] Soft Error: {message}")
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            logger.error(f"[notifier] Failed to alert admin {admin_id}: {e}")

async def notify_red_error(bot: Bot, message: str) -> None:
    """
    Red Error: A critical failure occurred that requires admin attention
    (e.g., API limits maxed out, database locked, crashes).
    """
    text = f"🔴 *CRITICAL ERROR*\n\n{message}\n\n_Attention needed._"
    logger.error(f"[notifier] Red Error: {message}")
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            logger.error(f"[notifier] Failed to alert admin {admin_id}: {e}")
