"""
scheduler.py

Services / Scheduler (Phase 9 Marketing Engine)

Job:
Orchestrates the entire time-based trading and marketing lifecycle.
Replaces the old continuous polling engine.

Schedule (UTC):
08:00 - Daily News
09:00 - Trade 1 (+ up to 2 hours random delay)
12:00 - Trade 2 (+ up to 2 hours random delay)
14:30 - Testimonial Bomb (3 posts, 2 mins apart)
16:00 - Trade 3 (+ up to 2 hours random delay)
Sat 20:00 - Weekly Report
"""

import os
import json
import random
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot
from aiogram.types import ParseMode, InputFile

from config import CHANNEL_ID
import data.repository as repo
from services.news import get_daily_news_message
import services.event_bus as event_bus
from core.marketing.fake_trade import generate_fake_trade
from integrations.testimonial.renderer import render_testimonial
import services.notifier as notifier

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")

CONTENT_DIR = os.path.join("data", "content")
CONVERSATIONS_FILE = os.path.join(CONTENT_DIR, "conversations.json")
PROMOTIONS_FILE = os.path.join(CONTENT_DIR, "promotions.json")
NAMES_FILE = os.path.join(CONTENT_DIR, "names.json")


def _get_random_json(filepath: str) -> str:
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            items = json.load(f)
            return random.choice(items) if items else ""
    except Exception as exc:
        logger.error(f"[scheduler] Failed to load {filepath}: {exc}")
        return ""


# ==============================================================
# Tasks
# ==============================================================

async def post_daily_news(bot: Bot) -> None:
    try:
        message = get_daily_news_message()
        if not message:
            await notifier.notify_soft_error(bot, "Daily News skipped — no news message was returned from the feed.")
            return
        await bot.send_message(chat_id=CHANNEL_ID, text=message, parse_mode=ParseMode.MARKDOWN)
        logger.info("[scheduler] Daily news posted.")
    except Exception as exc:
        logger.error(f"[scheduler] News post failed: {exc}")
        await notifier.notify_red_error(bot, f"Daily News post crashed: `{exc}`")


async def execute_trade(bot: Bot, trade_num: int) -> None:
    """Creates a backdated trade at TP1 and fires the SIGNAL_POST event.
    
    The live_monitor service (services/live_monitor.py) takes over from here,
    polling the real price every 60 seconds and firing TP2/TP3/SL/BREAK_EVEN
    events as the market actually moves. No more time-travel scheduling.
    """
    try:
        settings = repo.get_settings()
        if not int(settings.get("trading_enabled", 1)):
            logger.info("[scheduler] Trading disabled, skipping trade.")
            return

        trade = generate_fake_trade()
        logger.info(f"[scheduler] Trade {trade_num} generated: {trade['pair']} {trade['direction']}")

        # Fire signal — live_monitor will handle all follow-up events
        event_bus.publish("SIGNAL_POST", trade)

        # Promotional Post (10 mins after Trade 2)
        if trade_num == 2:
            scheduler.add_job(
                post_promotion,
                trigger="date",
                run_date=datetime.now(timezone.utc) + timedelta(minutes=10),
                args=[bot]
            )

    except Exception as exc:
        logger.error(f"[scheduler] Trade {trade_num} execution failed: {exc}")

        # Reschedule to try again in 15 minutes
        retry_time = datetime.now(timezone.utc) + timedelta(minutes=15)
        scheduler.add_job(
            execute_trade,
            trigger="date",
            run_date=retry_time,
            args=[bot, trade_num],
            id=f"trade{trade_num}_retry_{int(retry_time.timestamp())}"
        )

        await notifier.notify_red_error(
            bot,
            f"Trade {trade_num} failed to fire. *Retrying in 15 minutes*.\n\nError: `{exc}`\n\nCheck the log for details."
        )


async def post_promotion(bot: Bot) -> None:
    try:
        promo = _get_random_json(PROMOTIONS_FILE)
        if not promo: return
        
        settings = repo.get_settings()
        admin_contact = settings.get("admin_contact", "@MisterTrade")
        text = promo.replace("{{admin_contact}}", admin_contact)
        
        await bot.send_message(chat_id=CHANNEL_ID, text=text, parse_mode=ParseMode.MARKDOWN)
    except Exception as exc:
        logger.error(f"[scheduler] Promo post failed: {exc}")


async def trigger_testimonial_bomb(bot: Bot) -> None:
    """Posts 3 testimonials spaced 2 minutes apart."""
    try:
        for i in range(3):
            scheduler.add_job(
                _post_single_testimonial,
                trigger="date",
                run_date=datetime.now(timezone.utc) + timedelta(minutes=i*2),
                args=[bot, i+1]
            )
    except Exception as exc:
        logger.error(f"[scheduler] Testimonial bomb trigger failed: {exc}")


async def _post_single_testimonial(bot: Bot, index: int) -> None:
    try:
        script = _get_random_json(CONVERSATIONS_FILE)
        if not script: return
        
        settings = repo.get_settings()
        admin_name = settings.get("admin_name", "Mike")
        
        filename = f"testimonial_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{index}.png"
        image_path = await asyncio.to_thread(render_testimonial, script, admin_name, filename)
        
        with open(image_path, "rb") as f:
            await bot.send_photo(chat_id=CHANNEL_ID, photo=InputFile(f, filename=filename))
            
        if os.path.exists(image_path):
            os.remove(image_path)
    except Exception as exc:
        logger.error(f"[scheduler] Single testimonial post failed: {exc}")


async def post_weekly_report(bot: Bot) -> None:
    try:
        stats = repo.get_weekly_stats()
        if stats["total"] == 0:
            await notifier.notify_soft_error(bot, "Weekly Report skipped because there were 0 trades this week.")
            return

        win_rate = stats["win_rate"]
        if win_rate >= 80: verdict = "🔥 *INSANE week! VIPs are printing.*"
        elif win_rate >= 60: verdict = "✅ *Solid performance. Consistent as always.*"
        else: verdict = "📈 *Tough week. We adapt and come back stronger.*"

        report = (
            f"📊 *MISTER TRADE — WEEKLY PERFORMANCE REPORT*\n\n"
            f"🗓️ Week ending {datetime.now(timezone.utc).strftime('%B %d, %Y')}\n\n"
            f"✅ Wins:     `{stats['wins']}`\n"
            f"❌ Losses:   `{stats['losses']}`\n"
            f"📈 Total:    `{stats['total']}` trades\n"
            f"🎯 Accuracy: `{win_rate}%`\n\n"
            f"{verdict}\n\n"
            f"🔐 _Stay locked in. Next week is going to be even bigger._ 🚀"
        )
        await bot.send_message(chat_id=CHANNEL_ID, text=report, parse_mode=ParseMode.MARKDOWN)
        logger.info("[scheduler] Weekly report posted.")
    except Exception as exc:
        logger.error(f"[scheduler] Weekly report failed: {exc}")
        await notifier.notify_red_error(bot, f"Weekly Report crashed and was not posted: `{exc}`")


async def post_weekend_motivation(bot: Bot) -> None:
    try:
        promo = _get_random_json(PROMOTIONS_FILE)
        if not promo: return
        settings = repo.get_settings()
        admin_contact = settings.get("admin_contact", "@MisterTrade")
        text = f"🔥 *Weekend Motivation*\n\n{promo}".replace("{{admin_contact}}", admin_contact)
        await bot.send_message(chat_id=CHANNEL_ID, text=text, parse_mode=ParseMode.MARKDOWN)
    except Exception as exc:
        logger.error(f"[scheduler] Weekend motivation failed: {exc}")
        await notifier.notify_red_error(bot, f"Weekend motivation failed: {exc}")

async def post_sunday_prep(bot: Bot) -> None:
    try:
        settings = repo.get_settings()
        admin_contact = settings.get("admin_contact", "@MisterTrade")
        text = (
            "⏳ *Get ready for tomorrow trading*\n\n"
            "We have been analyzing EUR/USD all weekend and the setups are looking perfect. "
            "Can't wait to trade and make money... you have to be part of us.\n\n"
            f"Message {admin_contact} to get ready."
        )
        await bot.send_message(chat_id=CHANNEL_ID, text=text, parse_mode=ParseMode.MARKDOWN)
    except Exception as exc:
        logger.error(f"[scheduler] Sunday prep failed: {exc}")
        await notifier.notify_red_error(bot, f"Sunday prep failed: {exc}")

# ==============================================================
# Initialization & Rush Mode
# ==============================================================

def get_schedule_text() -> str:
    """Helper to return a string of the upcoming scheduled jobs and their times."""
    jobs = scheduler.get_jobs()
    if not jobs:
        return "No jobs scheduled."
        
    now = datetime.now(timezone.utc)
    lines = []
    
    sorted_jobs = [j for j in jobs if j.next_run_time]
    sorted_jobs.sort(key=lambda j: j.next_run_time)
    
    for job in sorted_jobs:
        delta = job.next_run_time - now
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, _ = divmod(remainder, 60)
        
        name = job.id.replace("_", " ").title()
        if "Trade" in name: emoji = "📈"
        elif "News" in name: emoji = "📰"
        elif "Testimonial" in name: emoji = "💬"
        elif "Report" in name: emoji = "📊"
        elif "Motivation" in name: emoji = "🔥"
        elif "Prep" in name: emoji = "⏳"
        else: emoji = "⏱️"
            
        time_str = f"in {hours}h {minutes}m" if hours > 0 else f"in {minutes}m"
        if delta.total_seconds() < 0:
            time_str = "Running now..."
            
        lines.append(f"{emoji} {name}: {time_str}")
        
    return "📅 *Today's Itinerary:*\n\n" + "\n".join(lines)


def start_scheduler(bot: Bot) -> None:
    scheduler.remove_all_jobs()
    
    market_mode = str(repo.get_settings().get("market_mode", "FOREX")).strip().upper()
    days = "mon-fri" if market_mode == "FOREX" else "mon-sun"

    # 1. Register Core Jobs
    scheduler.add_job(post_daily_news, trigger="cron", day_of_week=days, hour=8, minute=0, id="news", kwargs={"bot": bot}, replace_existing=True)
    scheduler.add_job(execute_trade, trigger="cron", day_of_week=days, hour=9, minute=0, jitter=7200, id="trade1", kwargs={"bot": bot, "trade_num": 1}, replace_existing=True)
    scheduler.add_job(execute_trade, trigger="cron", day_of_week=days, hour=12, minute=0, jitter=7200, id="trade2", kwargs={"bot": bot, "trade_num": 2}, replace_existing=True)
    scheduler.add_job(execute_trade, trigger="cron", day_of_week=days, hour=16, minute=0, jitter=7200, id="trade3", kwargs={"bot": bot, "trade_num": 3}, replace_existing=True)
    scheduler.add_job(trigger_testimonial_bomb, trigger="cron", day_of_week=days, hour=14, minute=30, id="testimonials", kwargs={"bot": bot}, replace_existing=True)
    
    # Weekly Report: Saturday 19:00 UTC (7 PM)
    scheduler.add_job(post_weekly_report, trigger="cron", day_of_week="sat", hour=19, minute=0, id="report", kwargs={"bot": bot}, replace_existing=True)

    # 2. Weekend specific jobs for FOREX mode
    if market_mode == "FOREX":
        scheduler.add_job(post_weekend_motivation, trigger="cron", day_of_week="sat,sun", hour=9, minute=0, id="weekend_motivation_am", kwargs={"bot": bot}, replace_existing=True)
        scheduler.add_job(post_weekend_motivation, trigger="cron", day_of_week="sat,sun", hour=17, minute=0, id="weekend_motivation_pm", kwargs={"bot": bot}, replace_existing=True)
        scheduler.add_job(post_sunday_prep, trigger="cron", day_of_week="sun", hour=19, minute=0, id="sunday_prep", kwargs={"bot": bot}, replace_existing=True)

    # 3. RUSH MODE: Catch up if bot restarted and missed trades (Only run if today matches the schedule)
    now = datetime.now(timezone.utc)
    is_weekend = now.weekday() >= 5
    should_trade_today = (market_mode == "CRYPTO") or (not is_weekend)

    if should_trade_today:
        trades_today = repo.count_trades_today()
        expected = 0
        if now.hour >= 11: expected = 1
        if now.hour >= 14: expected = 2
        if now.hour >= 18: expected = 3
        
        if trades_today < expected:
            catch_up_needed = expected - trades_today
            logger.warning(f"[scheduler] Rush Mode: Missed {catch_up_needed} trades today. Firing catch-up in 30 seconds.")
            scheduler.add_job(
                execute_trade,
                trigger="date",
                run_date=now + timedelta(seconds=30),
                args=[bot, trades_today + 1],
                id="rush_catch_up"
            )

    if not scheduler.running:
        scheduler.start()
    logger.info(f"[scheduler] Started in {market_mode} mode. Jobs queued: {len(scheduler.get_jobs())}")
