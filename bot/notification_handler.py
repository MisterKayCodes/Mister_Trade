"""
notification_handler.py

Mouth & Ears / Notification Handler

Job:
Read events from the event_bus and format them into
Telegram messages. Send them to the channel.

Rules:
    - aiogram v2 style (Bot is imported, not injected via v3 DI)
    - Pure async operations — runs inside the aiogram event loop
    - No trading logic — only formatting and sending
    - All errors are caught — a bad send must never crash the engine
"""

import os
import random
import asyncio
import logging
from aiogram import Bot
from aiogram.types import ParseMode, InputFile
from config import CHANNEL_ID
import services.event_bus as event_bus
from integrations.screenshot.renderer import render_signal_image

logger = logging.getLogger(__name__)


# ==============================================================
# Signal post (fired when TP1 is first hit)
# ==============================================================

async def send_signal(bot: Bot, payload: dict) -> None:
    """
    Format and send a VIP signal post to the channel.

    payload keys: pair, direction, entry, tp1, tp2, tp3, sl, lot_size
    """
    pair      = payload["pair"]
    direction = payload["direction"]
    entry     = float(payload["entry"])
    tp1       = float(payload["tp1"])
    tp2       = float(payload["tp2"])
    tp3       = float(payload["tp3"])
    sl        = float(payload["sl"])
    lot_size  = payload["lot_size"]

    emoji = "🟢" if direction == "BUY" else "🔴"

    FOMO_CAPTIONS = [
        "⚡️ _Trade is live and already in profit!_",
        "🔥 _Another massive sniper entry! VIPs are eating good today._",
        "🚀 _We caught the exact bottom! Don't miss the next one._",
        "💸 _Printing money while everyone else is sleeping!_",
        "🎯 _Zero drawdown. Perfect execution._",
        "💎 _This is why VIP members always win._"
    ]
    random_fomo = random.choice(FOMO_CAPTIONS)

    caption = (
        f"🚨 *VIP SIGNAL ALERT* 🚨\n\n"
        f"{emoji} *{pair}* — *{direction}*\n\n"
        f"{random_fomo}\n\n"
        f"🔐 _VIP members get these signals first._"
    )

    image_path = None
    try:
        if not CHANNEL_ID:
            logger.warning("[notification] CHANNEL_ID not set — signal not posted.")
            return

        # Generate screenshot (blocking IO, run in thread to keep bot responsive)
        filename = f"signal_{pair}_{payload.get('trade_id', 'new')}.png"
        image_path = await asyncio.to_thread(render_signal_image, payload, filename)

        with open(image_path, "rb") as f:
            photo = InputFile(f, filename=filename)
            await bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=photo,
                caption=caption,
                parse_mode=ParseMode.MARKDOWN,
            )
        logger.info(f"[notification] Signal image posted for {pair} {direction}")

    except Exception as exc:
        logger.error(f"[notification] Failed to post signal for {pair}: {exc}")
    finally:
        # Clean up the temp image
        if image_path and os.path.exists(image_path):
            try:
                os.remove(image_path)
            except OSError:
                pass


# ==============================================================
# Trade close post (fired when trade is fully closed)
# ==============================================================

async def send_close(bot: Bot, payload: dict) -> None:
    """
    Format and send a trade close result to the channel.

    payload keys: pair, direction, entry, close_price, close_stage, lot_size

    Rules:
        - SL / FORCED_LOSS  → humble text-only post (no screenshot)
        - TIME_LIMIT        → neutral text-only post
        - TP1/TP2/TP3       → full win celebration post
    """
    pair        = payload["pair"]
    direction   = payload["direction"]
    entry       = float(payload["entry"])
    close_price = float(payload["close_price"])
    close_stage = payload["close_stage"]
    forex       = pair.upper() in ("EURUSD", "GBPUSD")
    precision   = 5 if forex else 2

    def fmt(v: float) -> str:
        return f"{v:,.{precision}f}"

    if close_stage in ("SL", "FORCED_LOSS"):
        # Text-only — never post an ugly red screenshot
        SL_MESSAGES = [
            "The market reversed sharply. Risk management kept the drawdown small. We bounce back stronger 💪",
            "News spike caught us off guard. Small loss, part of the game. Next setup is already loaded 🎯",
            "SL was tight, market was volatile. No big deal — this is how pros manage risk. Stay tuned 👀",
            "We took a controlled loss. That's the plan working exactly as intended. Back to hunting 🔍",
        ]
        import random
        text = (
            f"🔴 *SL Hit — {pair}*\n\n"
            f"{random.choice(SL_MESSAGES)}\n\n"
            f"_Entry:_ `{fmt(entry)}`\n"
            f"_Closed:_ `{fmt(close_price)}`"
        )

    elif close_stage == "TIME_LIMIT":
        text = (
            f"⏰ *Trade Expired — {pair}*\n\n"
            f"Position closed after max hold time. Flat. Moving on. 🧊"
        )

    else:
        WIN_CAPTIONS = [
            "Another one banked. VIPs always eat 💰",
            "Clean execution. No noise, just profit 🎯",
            "That's what sniper entries look like. On to the next 🚀",
            "Textbook setup. Your account is growing 📈",
        ]
        import random
        dir_emoji = "🟢" if direction == "BUY" else "🔴"
        text = (
            f"💰 *{close_stage} SECURED — {pair}* 💰\n\n"
            f"{dir_emoji} *{direction}* | "
            f"Entry `{fmt(entry)}` → Close `{fmt(close_price)}`\n\n"
            f"_{random.choice(WIN_CAPTIONS)}_"
        )

    try:
        if not CHANNEL_ID:
            logger.warning("[notification] CHANNEL_ID not set — close not posted.")
            return

        await bot.send_message(
            chat_id=CHANNEL_ID,
            text=text,
            parse_mode=ParseMode.MARKDOWN,
        )
        logger.info(f"[notification] Close result posted for {pair} at {close_stage}")

    except Exception as exc:
        logger.error(f"[notification] Failed to post close for {pair}: {exc}")


# ==============================================================
# Flip Campaign Posts
# ==============================================================

async def send_flip_update(bot: Bot, payload: dict) -> None:
    """
    Format and send a flip campaign update.
    """
    pair = payload["pair"]
    profit = payload["profit"]
    old_bal = payload["old_balance"]
    new_bal = payload["new_balance"]
    target = payload["target_balance"]
    count = payload["trade_count"]
    
    if profit > 0:
        emoji = "📈"
        profit_str = f"+${profit:,.2f}"
        
        text = (
            f"🔄 *Flip Challenge Update* {emoji}\n\n"
            f"Trade #{count} completed on {pair}.\n"
            f"💵 Balance: `${old_bal:,.2f}` → `${new_bal:,.2f}` ({profit_str})\n"
            f"🎯 Target: `~${target:,.0f}`\n\n"
            f"_We keep pushing!_"
        )
        
        image_path = None
        try:
            if not CHANNEL_ID:
                return
                
            image_payload = {
                "pair": pair,
                "direction": payload.get("direction", "BUY"),
                "entry": payload.get("entry", 0),
                "tp1": payload.get("tp1", 0),
                "lot_size": payload.get("lot_size", 0.1),
                "override_balance": old_bal
            }
            filename = f"flip_{pair}_{count}.png"
            image_path = await asyncio.to_thread(render_signal_image, image_payload, filename)

            with open(image_path, "rb") as f:
                photo = InputFile(f, filename=filename)
                await bot.send_photo(
                    chat_id=CHANNEL_ID,
                    photo=photo,
                    caption=text,
                    parse_mode=ParseMode.MARKDOWN,
                )
        except Exception as exc:
            logger.error(f"[notification] Failed to post flip update: {exc}")
        finally:
            if image_path and os.path.exists(image_path):
                try:
                    os.remove(image_path)
                except OSError:
                    pass

    else:
        emoji = "📉"
        profit_str = f"-${abs(profit):,.2f}"

        text = (
            f"🔄 *Flip Challenge Update* {emoji}\n\n"
            f"Trade #{count} completed on {pair}.\n"
            f"💵 Balance: `${old_bal:,.2f}` → `${new_bal:,.2f}` ({profit_str})\n"
            f"🎯 Target: `~${target:,.0f}`\n\n"
            f"_We keep pushing!_"
        )
        
        try:
            if not CHANNEL_ID:
                return
            await bot.send_message(
                chat_id=CHANNEL_ID,
                text=text,
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as exc:
            logger.error(f"[notification] Failed to post flip update: {exc}")


async def send_flip_complete(bot: Bot, payload: dict) -> None:
    """
    Format and send a flip campaign completion post.
    """
    start = payload["start_balance"]
    final = payload["final_balance"]
    count = payload["trade_count"]
    
    text = (
        f"🏆 *FLIP CHALLENGE COMPLETE* 🏆\n\n"
        f"What a journey! We successfully flipped the account.\n\n"
        f"💰 Start: `${start:,.2f}`\n"
        f"💰 Final: `${final:,.2f}`\n"
        f"📊 Total Trades: {count}\n\n"
        f"VIPs ate good! Ready for the next one? 🚀"
    )
    
    try:
        if not CHANNEL_ID:
            return
        await bot.send_message(
            chat_id=CHANNEL_ID,
            text=text,
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as exc:
        logger.error(f"[notification] Failed to post flip complete: {exc}")


# ==============================================================
# Event bus consumer — runs forever alongside the bot
# ==============================================================

async def process_events(bot: Bot) -> None:
    """
    Poll the event bus every second and dispatch events to the
    correct handler function.

    Runs as a background coroutine — started from on_startup in main.py.
    """
    logger.info("[notification] Event bus consumer started.")

    while True:
        events = event_bus.consume_all()

        for event in events:
            event_type = event["type"]
            payload    = event["payload"]

            if event_type == "SIGNAL_POST":
                await send_signal(bot, payload)
            elif event_type == "TRADE_CLOSED":
                await send_close(bot, payload)
            elif event_type == "FLIP_UPDATE":
                await send_flip_update(bot, payload)
            elif event_type == "FLIP_COMPLETE":
                await send_flip_complete(bot, payload)

        await asyncio.sleep(1)
