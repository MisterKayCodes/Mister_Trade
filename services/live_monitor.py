"""
live_monitor.py

Services / Live Price Monitor

Job:
    Polls the real market price every POLL_INTERVAL seconds for every
    OPEN trade in the database.  Based on actual price movement it fires
    one of four events:

    TP2_HIT      — price reached TP2 level (trade stays open, waiting TP3)
    TP3_HIT      — price reached TP3 level (trade closes, full win)
    BREAK_EVEN   — price pumped past entry then reversed back to entry
                   (trade closes at break-even, partial win locked by TP1)
    SL_HIT       — price reached the stop-loss level (trade closes, loss)

This replaces the old time-travel approach in scheduler.py where TP2/TP3
were blindly scheduled in the future. Now every result is tied to a real,
verifiable price on TradingView.

Rules:
    - Pure async — runs as a background coroutine inside the aiogram event loop
    - Never crashes the bot — all exceptions are caught and logged
    - Only one event per trade per stage (guards prevent duplicate fires)
    - Uses providers.price.router as the single price source (CoinGecko / Yahoo)
"""

import asyncio
import logging
from datetime import datetime, timezone

from providers.price.router import get_current_price
import data.repository as repo
import services.event_bus as event_bus

logger = logging.getLogger(__name__)

# How often we check prices (seconds). 60s is safe for CoinGecko free tier.
POLL_INTERVAL: int = 60


# ==============================================================
# Helpers
# ==============================================================

def _profit_in_direction(direction: str, current: float, reference: float) -> float:
    """
    Returns a positive number when the current price is moving in
    the favour of the trade direction.
    BUY  → profit when current > reference
    SELL → profit when current < reference
    """
    if direction == "BUY":
        return current - reference
    return reference - current


def _reached_target(direction: str, current: float, target: float) -> bool:
    """True if current price has hit or passed the target in the trade direction."""
    if direction == "BUY":
        return current >= target
    return current <= target


def _breached_sl(direction: str, current: float, sl: float) -> bool:
    """True if the stop loss has been hit."""
    if direction == "BUY":
        return current <= sl
    return current >= sl


# ==============================================================
# Core monitor tick — processes a single open trade
# ==============================================================

async def _process_trade(trade: dict) -> None:
    """
    Evaluate a single open trade against the current live price.
    Fires the appropriate event and updates the database.
    """
    trade_id   = trade["id"]
    pair       = trade["pair"]
    direction  = trade["direction"]
    entry      = float(trade["entry_price"])
    tp2        = float(trade["tp2"])
    tp3        = float(trade["tp3"])
    sl         = float(trade["sl"])
    stage      = trade.get("stage", "TP1")
    lot_size   = float(trade.get("lot_size", 0.1))
    watermark  = trade.get("high_watermark")
    watermark  = float(watermark) if watermark is not None else float(trade.get("tp1", entry))

    # Fetch the real live price (blocking IO — run in thread to avoid blocking event loop)
    try:
        current = await asyncio.to_thread(get_current_price, pair)
    except Exception as exc:
        logger.warning(f"[monitor] Price fetch failed for {pair}: {exc}")
        return

    if current is None:
        logger.warning(f"[monitor] No price returned for {pair}, skipping.")
        return

    # --- Update High Watermark ---
    profit_move = _profit_in_direction(direction, current, entry)
    if profit_move > _profit_in_direction(direction, watermark, entry):
        watermark = current
        await asyncio.to_thread(repo.update_trade_watermark, trade_id, watermark)

    # Update current price snapshot in DB
    await asyncio.to_thread(repo.update_trade_price, trade_id, current)

    is_forex = pair.upper() in ("EURUSD", "GBPUSD")
    multiplier = 100_000 if is_forex else 1

    # ----------------------------------------------------------------
    # Gate 1: TP3 Hit — full win, close trade
    # ----------------------------------------------------------------
    if stage in ("TP1", "TP2") and _reached_target(direction, current, tp3):
        diff   = abs(tp3 - entry)
        profit = diff * lot_size * multiplier

        await asyncio.to_thread(repo.update_trade_stage, trade_id, "TP3")
        await asyncio.to_thread(repo.update_trade_price, trade_id, tp3)
        await asyncio.to_thread(repo.close_trade, trade_id, tp3, "TP3")
        await asyncio.to_thread(repo.increment_win_streak)

        event_bus.publish("TP3_HIT", {
            "trade_id":    trade_id,
            "pair":        pair,
            "direction":   direction,
            "entry":       entry,
            "close_price": tp3,
            "close_stage": "TP3",
            "lot_size":    lot_size,
            "profit":      profit,
            "tp1":         float(trade.get("tp1", entry)),
            "tp2":         tp2,
            "tp3":         tp3,
        })
        logger.info(f"[monitor] TP3 HIT — {pair} {direction} closed at {tp3:.2f}")
        return

    # ----------------------------------------------------------------
    # Gate 2: TP2 Hit — partial win, trade stays open for TP3
    # ----------------------------------------------------------------
    if stage == "TP1" and _reached_target(direction, current, tp2):
        diff   = abs(tp2 - entry)
        profit = diff * lot_size * multiplier

        await asyncio.to_thread(repo.update_trade_stage, trade_id, "TP2")
        await asyncio.to_thread(repo.update_trade_price, trade_id, tp2)

        event_bus.publish("TP2_HIT", {
            "trade_id":    trade_id,
            "pair":        pair,
            "direction":   direction,
            "entry":       entry,
            "close_price": tp2,
            "close_stage": "TP2",
            "lot_size":    lot_size,
            "profit":      profit,
            "tp1":         float(trade.get("tp1", entry)),
            "tp2":         tp2,
            "tp3":         tp3,
        })
        logger.info(f"[monitor] TP2 HIT — {pair} {direction} at {tp2:.2f}, watching for TP3.")
        return

    # ----------------------------------------------------------------
    # Gate 3: SL Hit — loss, close trade
    # ----------------------------------------------------------------
    if _breached_sl(direction, current, sl):
        diff        = abs(entry - sl)
        loss_amount = diff * lot_size * multiplier

        await asyncio.to_thread(repo.close_trade, trade_id, current, "SL")
        await asyncio.to_thread(repo.reset_win_streak, datetime.now(timezone.utc).strftime("%Y-%m-%d"))

        event_bus.publish("SL_HIT", {
            "trade_id":    trade_id,
            "pair":        pair,
            "direction":   direction,
            "entry":       entry,
            "close_price": current,
            "close_stage": "SL",
            "lot_size":    lot_size,
            "loss":        loss_amount,
        })
        logger.info(f"[monitor] SL HIT — {pair} {direction} closed at {current:.5f if is_forex else current:.2f}")
        return

    # ----------------------------------------------------------------
    # Gate 4: Break-Even — price pumped after TP1, then reversed to entry
    # High watermark must be meaningfully above entry (at least 30% of
    # TP1 distance) before we call it a break-even close, to avoid
    # triggering on tiny entry-level fluctuations.
    # ----------------------------------------------------------------
    tp1_dist = abs(float(trade.get("tp1", entry)) - entry)
    watermark_profit = _profit_in_direction(direction, watermark, entry)
    price_at_entry   = abs(_profit_in_direction(direction, current, entry)) <= (tp1_dist * 0.05)

    if stage == "TP1" and watermark_profit >= tp1_dist * 0.30 and price_at_entry:
        # We locked TP1. Now the reversal back to entry closes remainder at break-even.
        await asyncio.to_thread(repo.close_trade, trade_id, entry, "BREAK_EVEN")
        await asyncio.to_thread(repo.increment_win_streak)

        event_bus.publish("BREAK_EVEN", {
            "trade_id":    trade_id,
            "pair":        pair,
            "direction":   direction,
            "entry":       entry,
            "close_price": entry,
            "close_stage": "BREAK_EVEN",
            "lot_size":    lot_size,
            "high_watermark": watermark,
        })
        logger.info(f"[monitor] BREAK EVEN — {pair} {direction} reversed to entry {entry:.5f if is_forex else entry:.2f}")
        return

    logger.debug(f"[monitor] {pair} {direction} | current={current} | stage={stage} | watermark={watermark}")


# ==============================================================
# Main polling loop — runs forever as a background coroutine
# ==============================================================

async def run_live_monitor() -> None:
    """
    Entry point — call this from on_startup in main.py as an asyncio task.
    Polls all open trades on every POLL_INTERVAL tick.
    """
    logger.info(f"[monitor] Live price monitor started. Polling every {POLL_INTERVAL}s.")

    while True:
        try:
            open_trades = await asyncio.to_thread(repo.get_active_trades)

            if open_trades:
                logger.debug(f"[monitor] Checking {len(open_trades)} open trade(s).")
                for trade in open_trades:
                    try:
                        await _process_trade(trade)
                    except Exception as exc:
                        logger.error(f"[monitor] Error processing trade {trade.get('id')}: {exc}")
            else:
                logger.debug("[monitor] No open trades to monitor.")

        except Exception as exc:
            logger.error(f"[monitor] Polling loop error: {exc}")

        await asyncio.sleep(POLL_INTERVAL)
