"""
notification_handler.py

Mouth & Ears / Notification Handler

Job:
    Read events from the event_bus and distribute them to ALL registered
    copier channels, each with its own tone, risk settings, and admin name.

    Event types handled:
        SIGNAL_POST  — initial TP1 signal screenshot
        TP2_HIT      — TP2 reached, screenshot + update caption
        TP3_HIT      — TP3 reached, screenshot + win caption, close trade
        BREAK_EVEN   — price reversed to entry after TP1, protective close
        SL_HIT       — stop loss hit, text-only humble post
        FLIP_UPDATE  — flip campaign balance update with screenshot
        FLIP_COMPLETE— flip challenge completed, final balance post

Rules:
    - aiogram v2 style (Bot imported, not injected via v3 DI)
    - Pure async operations — runs inside the aiogram event loop
    - No trading logic — only formatting and sending
    - All errors are caught — a bad send must never crash the engine
    - The master CHANNEL_ID (from config) is ALWAYS included as a recipient
      so the owner's own channel always receives every signal
"""

import os
import io
import random
import asyncio
import logging
from aiogram import Bot
from aiogram.types import ParseMode, InputFile
from config import CHANNEL_ID
import services.event_bus as event_bus
from integrations.screenshot.renderer import render_signal_image
import data.repository as repo

logger = logging.getLogger(__name__)


# ==============================================================
# Tone Caption Templates
# ==============================================================

# SIGNAL captions (TP1 hit, trade just opened)
SIGNAL_CAPTIONS = {
    "HYPE": [
        "⚡️ WE ARE IN!! Trade is LIVE and already printing! 🔥",
        "🚀 BOOM! Caught the exact entry! VIPs are eating RIGHT NOW!",
        "💸 We snapped the bottom like PROS! Don't miss the next one!",
        "🎯 ZERO drawdown. Perfect sniper entry. LFG!! 🚀",
    ],
    "STOIC": [
        "Position entered. Trade is live.",
        "Setup confirmed. Entry executed at TP1.",
        "Trade is open. Monitor for TP2.",
        "Clean entry. Watching price action.",
    ],
    "PROFESSIONAL": [
        "⚡️ _Trade is live and already in profit._",
        "🔥 _Another strong sniper entry. VIPs are positioned._",
        "🚀 _Caught the exact move. Don't miss the next signal._",
        "🎯 _Zero drawdown. Perfect execution._",
    ],
}

# TP2 captions
TP2_CAPTIONS = {
    "HYPE": [
        "TP2 SMASHED!! 🚀🚀 We are going ALL THE WAY BABY! TP3 next!!",
        "ANOTHER ONE!! TP2 secured! This is what VIP looks like! 💰💰",
        "WE KEEP WINNING!! TP2 done!! Now let's go get that TP3! 🔥",
    ],
    "STOIC": [
        "TP2 reached. Partial profit secured. Watching for TP3.",
        "Second target hit. Position remains open for TP3.",
        "TP2 confirmed. Trade continues.",
    ],
    "PROFESSIONAL": [
        "💰 *TP2 SECURED* — Partial profits banked. Watching for TP3. 🎯",
        "✅ Second target reached. Excellent execution so far.",
        "📈 TP2 hit cleanly. Remaining position open for TP3.",
    ],
}

# TP3 captions (full close)
TP3_CAPTIONS = {
    "HYPE": [
        "ALL THREE TPs HIT!! WE WENT ALL THE WAY!! 🏆🏆🏆 VIPs CASHED OUT FULLY! 💰💰💰",
        "TP3 DESTROYED!! FULL WIN!! This is why you stay in VIP! 🚀🚀",
        "CLEAN SWEEP!! TP1 ✅ TP2 ✅ TP3 ✅ We don't miss! 🎯🎯🎯",
    ],
    "STOIC": [
        "TP3 reached. Trade closed. Full target achieved.",
        "All three targets hit. Position closed at maximum profit.",
        "TP3 confirmed. Clean trade from entry to close.",
    ],
    "PROFESSIONAL": [
        "🏆 *TP3 SECURED — Full win!* All targets hit. Another clean trade. 💰",
        "✅ TP1 ✅ TP2 ✅ TP3 — Perfect execution from entry to close.",
        "📈 Full profit secured. Trade closed at TP3. Consistency is the game.",
    ],
}

# SL captions (text-only, no screenshot on a loss)
SL_CAPTIONS = {
    "HYPE": [
        "Okay okay the market got us on this one 😅 That's trading! We bounce back HARDER 💪 Next signal incoming!",
        "Small L today but we stay focused 🎯 The market giveth and the market taketh. Next trade we go again! 🔥",
        "SL hit. It happens to the best of us. That's why we risk manage! Next one's a banger 🚀",
    ],
    "STOIC": [
        "Stop loss hit. Controlled loss. Risk management executed as planned.",
        "Market reversed. SL triggered. Moving to the next setup.",
        "Loss recorded. This is part of the process. On to the next trade.",
    ],
    "PROFESSIONAL": [
        "🔴 *SL Hit.* The market reversed sharply. Risk management kept the drawdown small. We move forward 💪",
        "📉 Controlled loss. News spike caught us off guard. Next setup is already loaded. 🎯",
        "⚠️ SL triggered. No big deal — this is how pros manage risk. Stay tuned for the next signal. 👀",
    ],
}

# Break-even captions
BREAK_EVEN_CAPTIONS = {
    "HYPE": [
        "Market tried to reverse on us BUT we already LOCKED TP1! Closing the rest at break-even 🛡️ WE DON'T LOSE!",
        "Reversal detected! Good thing we secured TP1 already! Closing at break-even, staying protected 💪",
    ],
    "STOIC": [
        "Price reversed after TP1. Closing remainder at break-even. TP1 profit is banked.",
        "Break-even close triggered. Remaining position protected. TP1 profit secured.",
    ],
    "PROFESSIONAL": [
        "🛡️ *Break-Even Close* — Market reversed after TP1. Remainder closed at entry. TP1 profit is already banked. No loss.",
        "⚖️ Price reversed toward entry. Smart close at break-even. TP1 win is locked in. Professional risk management.",
    ],
}


# ==============================================================
# PnL Calculator
# ==============================================================

def _calculate_pnl(channel: dict, entry: float, close_price: float, direction: str, pair: str) -> tuple[float, float]:
    """
    Calculate PnL and effective lot size for a channel based on its risk settings.

    risk_type:
        USD_RISK  — channel risks a fixed USD amount per trade
                    lot_size is back-calculated from the pip/dollar move
        LOT_SIZE  — channel uses a fixed lot size directly

    Returns (lot_size, pnl_usd)
    """
    is_forex   = pair.upper() in ("EURUSD", "GBPUSD")
    multiplier = 100_000 if is_forex else 1
    diff       = abs(close_price - entry)

    risk_type  = channel.get("risk_type", "USD_RISK")
    risk_value = float(channel.get("risk_value", 50.0))

    if risk_type == "USD_RISK":
        # Back-calculate lot size: lot = risk_usd / (pip_move * multiplier)
        # We use the pip move to SL to determine how many lots achieve the risk
        # For simplicity, we use a fixed 0.5% balance model: lot = risk / 1000
        lot_size = max(0.01, risk_value / 1000)
    else:
        lot_size = risk_value

    pnl = diff * lot_size * multiplier
    return lot_size, pnl


# ==============================================================
# Channel Distributor — sends to all active channels
# ==============================================================

async def _get_recipients() -> list[dict]:
    """
    Build the list of all channels to send to.
    Always includes the master CHANNEL_ID from config as a fallback,
    plus all registered active copier channels.
    """
    channels = await asyncio.to_thread(repo.get_all_active_copier_channels)

    # Ensure master channel is always included
    master_ids = {str(ch["channel_id"]) for ch in channels}
    if CHANNEL_ID and str(CHANNEL_ID) not in master_ids:
        channels.insert(0, {
            "channel_id":         CHANNEL_ID,
            "name":               "Master Channel",
            "tone":               "PROFESSIONAL",
            "risk_type":          "LOT_SIZE",
            "risk_value":         0.1,
            "max_trades_per_day": 99,
            "admin_name":         "Admin",
        })

    return channels


async def _send_photo_to_channel(bot: Bot, channel_id: str, image_payload: dict,
                                  caption: str, filename: str) -> None:
    """Generate a screenshot and send it as a photo to one channel."""
    image_path = None
    try:
        image_path = await asyncio.to_thread(render_signal_image, image_payload, filename)
        with open(image_path, "rb") as f:
            image_bytes = io.BytesIO(f.read())
        image_bytes.name = filename
        photo = InputFile(image_bytes, filename=filename)
        await bot.send_photo(
            chat_id=channel_id,
            photo=photo,
            caption=caption,
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as exc:
        logger.error(f"[notification] Failed to send photo to {channel_id}: {exc}")
    finally:
        if image_path and os.path.exists(image_path):
            try:
                os.remove(image_path)
            except OSError:
                pass


async def _send_text_to_channel(bot: Bot, channel_id: str, text: str) -> None:
    """Send a plain text message to one channel."""
    try:
        await bot.send_message(
            chat_id=channel_id,
            text=text,
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as exc:
        logger.error(f"[notification] Failed to send text to {channel_id}: {exc}")


# ==============================================================
# Signal post (TP1 — trade opened, already in profit)
# ==============================================================

async def send_signal(bot: Bot, payload: dict) -> None:
    """Distribute the initial trade signal + screenshot to all copier channels."""
    pair      = payload["pair"]
    direction = payload["direction"]
    entry     = float(payload["entry"])
    tp1       = float(payload["tp1"])
    tp2       = float(payload["tp2"])
    tp3       = float(payload["tp3"])
    sl        = float(payload["sl"])
    trade_id  = payload.get("trade_id", payload.get("id", "new"))

    is_forex  = pair.upper() in ("EURUSD", "GBPUSD")
    precision = 5 if is_forex else 2
    emoji     = "🟢" if direction == "BUY" else "🔴"

    def fmt(v): return f"{float(v):,.{precision}f}"

    recipients = await _get_recipients()

    for ch in recipients:
        try:
            # Check daily quota
            trades_today = await asyncio.to_thread(
                repo.count_channel_trades_today, str(ch["channel_id"])
            )
            if trades_today >= ch.get("max_trades_per_day", 99):
                logger.info(f"[notification] Channel {ch['channel_id']} at daily quota. Skipping signal.")
                continue

            tone    = ch.get("tone", "PROFESSIONAL")
            captions = SIGNAL_CAPTIONS.get(tone, SIGNAL_CAPTIONS["PROFESSIONAL"])
            fomo    = random.choice(captions)

            lot_size, pnl = _calculate_pnl(ch, entry, tp1, direction, pair)

            caption = (
                f"🚨 *VIP SIGNAL ALERT* 🚨\n\n"
                f"{emoji} *{pair}* — *{direction}*\n\n"
                f"📍 Entry: `{fmt(entry)}`\n"
                f"✅ TP1: `{fmt(tp1)}`\n"
                f"✅ TP2: `{fmt(tp2)}`\n"
                f"✅ TP3: `{fmt(tp3)}`\n"
                f"❌ SL: `{fmt(sl)}`\n\n"
                f"{fomo}\n\n"
                f"🔐 _VIP members get these signals first._"
            )

            image_payload = {
                "pair":      pair,
                "direction": direction,
                "entry":     entry,
                "tp1":       tp1,
                "lot_size":  lot_size,
            }
            filename = f"signal_{pair}_{trade_id}_{ch['channel_id']}.png"
            await _send_photo_to_channel(bot, str(ch["channel_id"]), image_payload, caption, filename)

        except Exception as exc:
            logger.error(f"[notification] send_signal failed for channel {ch.get('channel_id')}: {exc}")

    logger.info(f"[notification] Signal distributed for {pair} {direction} to {len(recipients)} channel(s).")


# ==============================================================
# TP2 Hit
# ==============================================================

async def send_tp2_hit(bot: Bot, payload: dict) -> None:
    """Distribute TP2 screenshot + update to all channels."""
    pair      = payload["pair"]
    direction = payload["direction"]
    entry     = float(payload["entry"])
    tp2       = float(payload["close_price"])
    tp3       = float(payload["tp3"])
    trade_id  = payload.get("trade_id", "x")

    is_forex  = pair.upper() in ("EURUSD", "GBPUSD")
    precision = 5 if is_forex else 2
    def fmt(v): return f"{float(v):,.{precision}f}"

    recipients = await _get_recipients()

    for ch in recipients:
        try:
            tone     = ch.get("tone", "PROFESSIONAL")
            lot_size, pnl = _calculate_pnl(ch, entry, tp2, direction, pair)
            captions = TP2_CAPTIONS.get(tone, TP2_CAPTIONS["PROFESSIONAL"])

            caption = (
                f"📈 *TP2 HIT — {pair}* 📈\n\n"
                f"{'🟢' if direction == 'BUY' else '🔴'} *{direction}*\n"
                f"Entry `{fmt(entry)}` → TP2 `{fmt(tp2)}`\n\n"
                f"💰 Profit so far: `+${pnl:,.2f}`\n"
                f"🎯 Next target: `{fmt(tp3)}`\n\n"
                f"{random.choice(captions)}"
            )

            image_payload = {
                "pair":      pair,
                "direction": direction,
                "entry":     entry,
                "tp1":       tp2,   # Use TP2 as the current price shown in screenshot
                "lot_size":  lot_size,
            }
            filename = f"tp2_{pair}_{trade_id}_{ch['channel_id']}.png"
            await _send_photo_to_channel(bot, str(ch["channel_id"]), image_payload, caption, filename)

        except Exception as exc:
            logger.error(f"[notification] send_tp2_hit failed for channel {ch.get('channel_id')}: {exc}")

    logger.info(f"[notification] TP2 update distributed for {pair}.")


# ==============================================================
# TP3 Hit (Full Close)
# ==============================================================

async def send_tp3_hit(bot: Bot, payload: dict) -> None:
    """Distribute TP3 full win screenshot + close message to all channels."""
    pair      = payload["pair"]
    direction = payload["direction"]
    entry     = float(payload["entry"])
    tp3       = float(payload["close_price"])
    trade_id  = payload.get("trade_id", "x")

    is_forex  = pair.upper() in ("EURUSD", "GBPUSD")
    precision = 5 if is_forex else 2
    def fmt(v): return f"{float(v):,.{precision}f}"

    recipients = await _get_recipients()

    for ch in recipients:
        try:
            tone     = ch.get("tone", "PROFESSIONAL")
            lot_size, pnl = _calculate_pnl(ch, entry, tp3, direction, pair)
            captions = TP3_CAPTIONS.get(tone, TP3_CAPTIONS["PROFESSIONAL"])

            caption = (
                f"🏆 *TP3 HIT — FULL WIN! — {pair}* 🏆\n\n"
                f"{'🟢' if direction == 'BUY' else '🔴'} *{direction}*\n"
                f"Entry `{fmt(entry)}` → TP3 `{fmt(tp3)}`\n\n"
                f"💰 *Total Profit: `+${pnl:,.2f}`*\n\n"
                f"{random.choice(captions)}"
            )

            image_payload = {
                "pair":      pair,
                "direction": direction,
                "entry":     entry,
                "tp1":       tp3,
                "lot_size":  lot_size,
            }
            filename = f"tp3_{pair}_{trade_id}_{ch['channel_id']}.png"
            await _send_photo_to_channel(bot, str(ch["channel_id"]), image_payload, caption, filename)

            # Check and fire flip update for this channel after a TP3 close
            await _maybe_post_flip_update(bot, ch, payload, lot_size, pnl)

        except Exception as exc:
            logger.error(f"[notification] send_tp3_hit failed for channel {ch.get('channel_id')}: {exc}")

    logger.info(f"[notification] TP3 full-win distributed for {pair}.")


# ==============================================================
# Break-Even Close
# ==============================================================

async def send_break_even(bot: Bot, payload: dict) -> None:
    """Distribute break-even close message to all channels."""
    pair      = payload["pair"]
    direction = payload["direction"]
    entry     = float(payload["entry"])
    watermark = float(payload.get("high_watermark", entry))
    trade_id  = payload.get("trade_id", "x")

    is_forex  = pair.upper() in ("EURUSD", "GBPUSD")
    precision = 5 if is_forex else 2
    def fmt(v): return f"{float(v):,.{precision}f}"

    recipients = await _get_recipients()

    for ch in recipients:
        try:
            tone     = ch.get("tone", "PROFESSIONAL")
            captions = BREAK_EVEN_CAPTIONS.get(tone, BREAK_EVEN_CAPTIONS["PROFESSIONAL"])

            # PnL for TP1 portion (already banked) shown as reference
            lot_size, tp1_pnl = _calculate_pnl(ch, entry, watermark, direction, pair)

            caption = (
                f"⚖️ *Break-Even Close — {pair}*\n\n"
                f"{'🟢' if direction == 'BUY' else '🔴'} *{direction}*\n"
                f"Market reversed after reaching `{fmt(watermark)}`.\n"
                f"Remaining position closed at entry `{fmt(entry)}`.\n\n"
                f"✅ TP1 profit of `+${tp1_pnl:,.2f}` already banked.\n\n"
                f"{random.choice(captions)}"
            )

            await _send_text_to_channel(bot, str(ch["channel_id"]), caption)

        except Exception as exc:
            logger.error(f"[notification] send_break_even failed for channel {ch.get('channel_id')}: {exc}")

    logger.info(f"[notification] Break-even close distributed for {pair}.")


# ==============================================================
# SL Hit (Loss)
# ==============================================================

async def send_sl_hit(bot: Bot, payload: dict) -> None:
    """Distribute SL hit (text-only, no screenshot) to all channels."""
    pair      = payload["pair"]
    direction = payload["direction"]
    entry     = float(payload["entry"])
    sl_price  = float(payload["close_price"])

    is_forex  = pair.upper() in ("EURUSD", "GBPUSD")
    precision = 5 if is_forex else 2
    def fmt(v): return f"{float(v):,.{precision}f}"

    recipients = await _get_recipients()

    for ch in recipients:
        try:
            tone     = ch.get("tone", "PROFESSIONAL")
            captions = SL_CAPTIONS.get(tone, SL_CAPTIONS["PROFESSIONAL"])
            _, loss  = _calculate_pnl(ch, entry, sl_price, direction, pair)

            caption = (
                f"🔴 *SL Hit — {pair}*\n\n"
                f"_Entry:_ `{fmt(entry)}`\n"
                f"_Closed:_ `{fmt(sl_price)}`\n"
                f"_Loss:_ `-${loss:,.2f}`\n\n"
                f"{random.choice(captions)}"
            )

            await _send_text_to_channel(bot, str(ch["channel_id"]), caption)

        except Exception as exc:
            logger.error(f"[notification] send_sl_hit failed for channel {ch.get('channel_id')}: {exc}")

    logger.info(f"[notification] SL hit distributed for {pair}.")


# ==============================================================
# Flip Campaign Helpers
# ==============================================================

async def _maybe_post_flip_update(bot: Bot, ch: dict, trade_payload: dict,
                                   lot_size: float, pnl: float) -> None:
    """If this channel has an active flip campaign, calculate and post the update."""
    try:
        channel_id = str(ch["channel_id"])
        campaign   = await asyncio.to_thread(repo.get_active_flip_campaign)
        if not campaign:
            return

        old_balance = float(campaign["current_balance"])
        new_balance = old_balance + pnl
        count       = campaign["trade_count"] + 1
        target      = float(campaign["target_balance"])

        await asyncio.to_thread(repo.update_flip_campaign, campaign["id"], new_balance)

        # Build the flip update caption
        flip_caption = (
            f"🔄 *FLIP CHALLENGE UPDATE*\n\n"
            f"✅ Trade Won: `+${pnl:,.2f}`\n"
            f"💰 *Current Balance:* `${new_balance:,.2f}`\n"
            f"🎯 Target: `${target:,.2f}`\n\n"
            f"Trade #{count} complete. We keep pushing! 💪"
        )

        # Screenshot showing the floating profit
        image_payload = {
            "pair":             trade_payload["pair"],
            "direction":        trade_payload["direction"],
            "entry":            trade_payload["entry"],
            "tp1":              trade_payload["close_price"],
            "lot_size":         lot_size,
            "override_balance": old_balance,
        }
        filename = f"flip_{channel_id}_{count}.png"
        await _send_photo_to_channel(bot, channel_id, image_payload, flip_caption, filename)

        # Check if flip is complete
        from core.flip.engine import should_end_campaign
        if should_end_campaign(new_balance, target):
            await asyncio.to_thread(repo.complete_flip_campaign, campaign["id"])
            complete_text = (
                f"🏆 *FLIP CHALLENGE COMPLETE!!* 🏆\n\n"
                f"What an incredible journey!\n\n"
                f"💰 Started with: `${campaign['start_balance']:,.2f}`\n"
                f"🎯 Target was:   `${target:,.2f}`\n"
                f"🏁 Final Balance: `${new_balance:,.2f}`\n"
                f"📊 Total Trades: {count}\n\n"
                f"VIPs ate GOOD! Ready for the next challenge? 🚀"
            )
            await _send_text_to_channel(bot, channel_id, complete_text)

    except Exception as exc:
        logger.error(f"[notification] Flip update failed for channel {ch.get('channel_id')}: {exc}")


# ==============================================================
# Legacy handlers (kept for backward compatibility with scheduler.py)
# ==============================================================

async def send_close(bot: Bot, payload: dict) -> None:
    """Legacy TRADE_CLOSED handler — routes to the correct new sender."""
    stage = payload.get("close_stage", "")
    if stage in ("SL", "FORCED_LOSS"):
        await send_sl_hit(bot, payload)
    elif stage == "TP2":
        await send_tp2_hit(bot, payload)
    elif stage == "TP3":
        await send_tp3_hit(bot, payload)
    elif stage == "BREAK_EVEN":
        await send_break_even(bot, payload)


async def send_flip_update(bot: Bot, payload: dict) -> None:
    """Legacy FLIP_UPDATE handler \u2014 kept for event bus compatibility."""
    pair    = payload["pair"]
    profit  = payload["profit"]
    old_bal = payload["old_balance"]
    new_bal = payload["new_balance"]
    target  = payload["target_balance"]
    count   = payload["trade_count"]

    recipients = await _get_recipients()

    for ch in recipients:
        try:
            lot_size  = float(ch.get("risk_value", 0.1))
            pnl_str   = f"+${profit:,.2f}" if profit > 0 else f"-${abs(profit):,.2f}"

            flip_caption = (
                f"🔄 *FLIP CHALLENGE UPDATE*\n\n"
                f"{'✅' if profit > 0 else '📉'} Trade #{count}: `{pnl_str}`\n"
                f"💰 *Balance:* `${old_bal:,.2f}` → `${new_bal:,.2f}`\n"
                f"🎯 Target: `${target:,.2f}`\n\n"
                f"_We keep pushing!_"
            )

            if profit > 0:
                image_payload = {
                    "pair":             pair,
                    "direction":        payload.get("direction", "BUY"),
                    "entry":            payload.get("entry", 0),
                    "tp1":              payload.get("tp1", 0),
                    "lot_size":         lot_size,
                    "override_balance": old_bal,
                }
                filename = f"flip_{pair}_{count}_{ch['channel_id']}.png"
                await _send_photo_to_channel(bot, str(ch["channel_id"]), image_payload, flip_caption, filename)
            else:
                await _send_text_to_channel(bot, str(ch["channel_id"]), flip_caption)

        except Exception as exc:
            logger.error(f"[notification] send_flip_update failed for {ch.get('channel_id')}: {exc}")


async def send_flip_complete(bot: Bot, payload: dict) -> None:
    """Legacy FLIP_COMPLETE handler."""
    start = payload["start_balance"]
    final = payload["final_balance"]
    count = payload["trade_count"]
    target = payload.get("target_balance", final)

    text = (
        f"🏆 *FLIP CHALLENGE COMPLETE!* 🏆\n\n"
        f"What a journey!\n\n"
        f"💰 Started: `${start:,.2f}`\n"
        f"🎯 Target:  `${target:,.2f}`\n"
        f"🏁 Final:   `${final:,.2f}`\n"
        f"📊 Trades:  {count}\n\n"
        f"VIPs ate good! Ready for the next one? 🚀"
    )

    recipients = await _get_recipients()
    for ch in recipients:
        await _send_text_to_channel(bot, str(ch["channel_id"]), text)


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

            try:
                if event_type == "SIGNAL_POST":
                    await send_signal(bot, payload)
                elif event_type == "TP2_HIT":
                    await send_tp2_hit(bot, payload)
                elif event_type == "TP3_HIT":
                    await send_tp3_hit(bot, payload)
                elif event_type == "BREAK_EVEN":
                    await send_break_even(bot, payload)
                elif event_type == "SL_HIT":
                    await send_sl_hit(bot, payload)
                elif event_type == "TRADE_CLOSED":
                    await send_close(bot, payload)
                elif event_type == "FLIP_UPDATE":
                    await send_flip_update(bot, payload)
                elif event_type == "FLIP_COMPLETE":
                    await send_flip_complete(bot, payload)
            except Exception as exc:
                logger.error(f"[notification] Unhandled error dispatching {event_type}: {exc}")

        await asyncio.sleep(1)
