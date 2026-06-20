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
        if not message: return
        await bot.send_message(chat_id=CHANNEL_ID, text=message, parse_mode=ParseMode.MARKDOWN)
        logger.info("[scheduler] Daily news posted.")
    except Exception as exc:
        logger.error(f"[scheduler] News post failed: {exc}")


async def execute_trade(bot: Bot, trade_num: int) -> None:
    """Creates a backdated trade, hits TP1, and schedules follow-ups."""
    try:
        settings = repo.get_settings()
        if not int(settings.get("trading_enabled", 1)):
            logger.info("[scheduler] Trading disabled, skipping trade.")
            return

        trade = generate_fake_trade()
        logger.info(f"[scheduler] Trade {trade_num} generated: {trade['pair']} {trade['direction']}")

        # 1. Post Signal (TP1 hit)
        event_bus.publish("SIGNAL_POST", trade)

        # 2. Schedule TP2 / TP3 closes later today
        # TP2: 1 to 3 hours later
        delay_tp2 = random.randint(60, 180)
        scheduler.add_job(
            close_trade_stage,
            trigger="date",
            run_date=datetime.now(timezone.utc) + timedelta(minutes=delay_tp2),
            args=[bot, trade, "TP2"]
        )

        # TP3: 4 to 6 hours later
        delay_tp3 = random.randint(240, 360)
        scheduler.add_job(
            close_trade_stage,
            trigger="date",
            run_date=datetime.now(timezone.utc) + timedelta(minutes=delay_tp3),
            args=[bot, trade, "TP3"]
        )

        # 3. Flip Campaign Logic (5 mins later)
        campaign = repo.get_active_flip_campaign()
        if campaign:
            scheduler.add_job(
                process_flip_update,
                trigger="date",
                run_date=datetime.now(timezone.utc) + timedelta(minutes=5),
                args=[trade, campaign]
            )

        # 4. Promotional Post (10 mins after Trade 2)
        if trade_num == 2:
            scheduler.add_job(
                post_promotion,
                trigger="date",
                run_date=datetime.now(timezone.utc) + timedelta(minutes=10),
                args=[bot]
            )

    except Exception as exc:
        logger.error(f"[scheduler] Trade execution failed: {exc}")


async def close_trade_stage(bot: Bot, trade: dict, stage: str) -> None:
    try:
        # Re-fetch trade to ensure it wasn't manually cleared
        active = repo.get_active_trade(trade["pair"])
        if not active or active["id"] != trade["id"]:
            return

        price = trade[stage.lower()]
        repo.update_trade_stage(trade["id"], stage)
        repo.update_trade_price(trade["id"], price)
        
        # If TP3, fully close it
        if stage == "TP3":
            repo.close_trade(trade["id"], price, stage)
            repo.increment_win_streak()

        event_bus.publish("TRADE_CLOSED", {
            "pair": trade["pair"],
            "direction": trade["direction"],
            "entry": trade["entry"],
            "close_price": price,
            "close_stage": stage,
            "lot_size": trade["lot_size"]
        })
    except Exception as exc:
        logger.error(f"[scheduler] Close trade stage {stage} failed: {exc}")


async def process_flip_update(trade: dict, campaign: dict) -> None:
    """Calculate compounding profit and publish flip update."""
    try:
        from core.flip.engine import compute_flip_lot, should_end_campaign
        from core.signals.generator import get_pair_rules
        
        pair = trade["pair"]
        rules = get_pair_rules(pair)
        flip_lot = compute_flip_lot(campaign["current_balance"], pair, rules["sl_offset"])
        
        diff = (trade["tp1"] - trade["entry"]) if trade["direction"] == "BUY" else (trade["entry"] - trade["tp1"])
        multiplier = 100_000 if pair.upper() in ("EURUSD", "GBPUSD") else 1
        profit = abs(diff * flip_lot * multiplier)
        
        new_balance = campaign["current_balance"] + profit
        repo.update_flip_campaign(campaign["id"], new_balance)
        
        event_bus.publish("FLIP_UPDATE", {
            "pair": pair,
            "direction": trade["direction"],
            "entry": trade["entry"],
            "tp1": trade["tp1"],
            "lot_size": flip_lot,
            "old_balance": campaign["current_balance"],
            "new_balance": new_balance,
            "target_balance": campaign["target_balance"],
            "trade_count": campaign["trade_count"] + 1,
            "profit": profit
        })
        
        if should_end_campaign(new_balance, campaign["target_balance"]):
            repo.complete_flip_campaign(campaign["id"])
            event_bus.publish("FLIP_COMPLETE", {
                "campaign_id": campaign["id"],
                "start_balance": campaign["start_balance"],
                "final_balance": new_balance,
                "target_balance": campaign["target_balance"],
                "trade_count": campaign["trade_count"] + 1
            })
            
    except Exception as exc:
        logger.error(f"[scheduler] Flip update failed: {exc}")


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
        if stats["total"] == 0: return

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
    except Exception as exc:
        logger.error(f"[scheduler] Weekly report failed: {exc}")


# ==============================================================
# Initialization & Rush Mode
# ==============================================================

def start_scheduler(bot: Bot) -> None:
    # 1. Register Daily Jobs
    scheduler.add_job(post_daily_news, trigger="cron", hour=8, minute=0, id="news", kwargs={"bot": bot}, replace_existing=True)
    
    # Trades with 2-hour jitter (random delay 0-7200 seconds)
    scheduler.add_job(execute_trade, trigger="cron", hour=9, minute=0, jitter=7200, id="trade1", kwargs={"bot": bot, "trade_num": 1}, replace_existing=True)
    scheduler.add_job(execute_trade, trigger="cron", hour=12, minute=0, jitter=7200, id="trade2", kwargs={"bot": bot, "trade_num": 2}, replace_existing=True)
    scheduler.add_job(execute_trade, trigger="cron", hour=16, minute=0, jitter=7200, id="trade3", kwargs={"bot": bot, "trade_num": 3}, replace_existing=True)
    
    # Testimonials at 14:30
    scheduler.add_job(trigger_testimonial_bomb, trigger="cron", hour=14, minute=30, id="testimonials", kwargs={"bot": bot}, replace_existing=True)
    
    # Weekly Report: Saturday 20:00 UTC
    scheduler.add_job(post_weekly_report, trigger="cron", day_of_week="sat", hour=20, minute=0, id="report", kwargs={"bot": bot}, replace_existing=True)

    # 2. RUSH MODE: Catch up if bot restarted and missed trades
    now = datetime.now(timezone.utc)
    # Check if we should have fired trades based on the hour:
    # Trade 1 by 11:00 UTC (jitter up to 11:00)
    # Trade 2 by 14:00 UTC
    # Trade 3 by 18:00 UTC
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
            args=[bot, trades_today + 1]
        )

    scheduler.start()
    logger.info("[scheduler] Phase 9 APScheduler started. All marketing events queued.")
