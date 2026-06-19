"""
trade_engine.py

Nervous System

Job:
Orchestrate the complete trade lifecycle for all configured pairs.
Carries signals between the Eyes (price), the Brain (logic),
and the Memory (database).

Rules:
    - No raw price calculations (those live in core/)
    - No SQL queries (those live in data/repository.py)
    - No Telegram (that lives in bot/)
    - Catches ALL exceptions per cycle so one bad pair never kills the loop

Lifecycle per pair per cycle:
    Fetch price
        ↓
    Active trade exists?
        YES → evaluate_trade() → HOLD / UPDATE_STAGE / CLOSE
        NO  → reference price exists?
                NO  → seed reference price, wait
                YES → has price moved enough?
                        NO  → wait
                        YES → create signal → save trade
"""

import time
import logging
from datetime import datetime, timezone

from config import PAIRS, CYCLE_INTERVAL
from providers.price.coingecko import get_crypto_price
from core.movement.detector import has_moved, calculate_movement
from core.signals.generator import create_signal, get_pair_rules
from core.trades.tracker import evaluate_trade
import data.repository as repo

logger = logging.getLogger(__name__)


# ==============================================================
# Internal helpers
# ==============================================================

def _dual_log(level: str, source: str, message: str) -> None:
    """Write to both the Python logger and the database system_log."""
    if level == "INFO":
        logger.info("[%s] %s", source, message)
    elif level == "WARNING":
        logger.warning("[%s] %s", source, message)
    elif level == "ERROR":
        logger.error("[%s] %s", source, message)
    repo.log(level, source, message)


def _is_trading_enabled() -> bool:
    settings = repo.get_settings()
    return bool(settings.get("trading_enabled", 1))


def _max_trades_reached(settings: dict) -> bool:
    max_allowed = int(settings.get("max_trades_per_day", 3))
    created_today = repo.count_trades_today()
    return created_today >= max_allowed


# ==============================================================
# Trade monitoring (active trade exists)
# ==============================================================

def _handle_active_trade(trade: dict, current_price: float, settings: dict) -> None:
    """
    Evaluate an open trade against the current price and act:
      HOLD         → update the stored price snapshot
      UPDATE_STAGE → advance the stage (TP1 → TP2 etc.), update price
      CLOSE        → close the trade, update reference price, update stats
    """
    trade_id = trade["id"]
    pair     = trade["pair"]

    result = evaluate_trade(trade, current_price, settings)
    action = result["action"]
    stage  = result["stage"]
    price  = result["price"]

    if action == "HOLD":
        repo.update_trade_price(trade_id, price)
        _dual_log(
            "INFO",
            f"monitor.{pair}",
            f"Trade #{trade_id} HOLD | stage={trade['stage']} | "
            f"price=${price:,.2f}",
        )

    elif action == "UPDATE_STAGE":
        repo.update_trade_stage(trade_id, stage)
        repo.update_trade_price(trade_id, price)
        _dual_log(
            "INFO",
            f"monitor.{pair}",
            f"Trade #{trade_id} reached {stage} ✅ | price=${price:,.2f}",
        )

    elif action == "CLOSE":
        repo.close_trade(trade_id, price, stage)

        # Critical: new reference = close price, not entry price.
        # Using entry price would re-trigger signals endlessly.
        repo.set_reference_price(pair, price)

        # Update win / loss streak counters
        if stage == "SL":
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            repo.reset_win_streak(today)
            _dual_log(
                "INFO",
                f"monitor.{pair}",
                f"Trade #{trade_id} CLOSED at {stage} ❌ | price=${price:,.2f}",
            )
        else:
            repo.increment_win_streak()
            _dual_log(
                "INFO",
                f"monitor.{pair}",
                f"Trade #{trade_id} CLOSED at {stage} 💰 | price=${price:,.2f}",
            )


# ==============================================================
# Signal detection (no active trade)
# ==============================================================

def _handle_no_trade(pair: str, current_price: float, settings: dict) -> None:
    """
    When no trade is open for a pair, check whether the price has
    moved enough from the reference to generate a new signal.
    """
    rules = get_pair_rules(pair)
    if not rules:
        return
    
    threshold = rules["threshold"]
    reference = repo.get_reference_price(pair)

    # No reference yet — this is the first ever cycle for this pair.
    if reference is None:
        repo.set_reference_price(pair, current_price)
        _dual_log(
            "INFO",
            f"lifecycle.{pair}",
            f"Reference price seeded: ${current_price:,.2f}",
        )
        return

    movement = calculate_movement(reference, current_price)

    _dual_log(
        "INFO",
        f"lifecycle.{pair}",
        f"Price=${current_price:,.2f} | Ref=${reference:,.2f} | "
        f"Δ={movement:+.2f} | Threshold=${threshold:,.0f}",
    )

    if not has_moved(reference, current_price, threshold):
        return  # Not enough movement yet — wait

    if _max_trades_reached(settings):
        _dual_log(
            "WARNING",
            f"lifecycle.{pair}",
            "Max trades per day reached. Signal skipped.",
        )
        return

    signal = create_signal(pair, reference, current_price)
    if signal is None:
        return  # Edge case: movement recalculated below threshold

    lot_size = float(settings.get("lot_size", 0.1))

    trade_id = repo.create_trade(
        pair        = signal["pair"],
        direction   = signal["direction"],
        entry_price = signal["entry"],
        tp1         = signal["tp1"],
        tp2         = signal["tp2"],
        tp3         = signal["tp3"],
        sl          = signal["sl"],
        lot_size    = lot_size,
    )

    _dual_log(
        "INFO",
        f"signal.{pair}",
        f"🚀 Trade #{trade_id} CREATED | "
        f"{signal['direction']} {pair} @ ${signal['entry']:,.2f} | "
        f"TP1=${signal['tp1']:,.2f} TP2=${signal['tp2']:,.2f} "
        f"TP3=${signal['tp3']:,.2f} SL=${signal['sl']:,.2f}",
    )


# ==============================================================
# Single cycle for one pair
# ==============================================================

def run_cycle(pair: str) -> None:
    """
    Execute one full lifecycle cycle for a single trading pair.
    All exceptions are caught so a failure on one pair never
    prevents the other pair from running.
    """
    try:
        current_price = get_crypto_price(pair)

        if current_price is None:
            _dual_log(
                "ERROR",
                f"price.{pair}",
                "Price fetch failed after all retries. Skipping cycle.",
            )
            return

        settings     = repo.get_settings()
        active_trade = repo.get_active_trade(pair)

        if active_trade:
            _handle_active_trade(active_trade, current_price, settings)
        else:
            _handle_no_trade(pair, current_price, settings)

    except Exception as exc:
        _dual_log(
            "ERROR",
            f"engine.{pair}",
            f"Unexpected error in cycle: {exc}",
        )


# ==============================================================
# Main loop
# ==============================================================

last_heartbeat = 0
HEARTBEAT_INTERVAL = 300  # 5 minutes

def run_forever() -> None:
    """
    Start the engine. Runs all configured pairs on every tick.
    Sleeps CYCLE_INTERVAL seconds between ticks.
    Never returns.
    """
    global last_heartbeat
    _dual_log("INFO", "engine", f"▶  Mister Trade engine started | Pairs: {PAIRS}")

    while True:
        now = time.time()
        if now - last_heartbeat > HEARTBEAT_INTERVAL:
            _dual_log("INFO", "engine", "💓 Heartbeat: Engine is alive and monitoring.")
            last_heartbeat = now

        if not _is_trading_enabled():
            _dual_log("INFO", "engine", "Trading is DISABLED. Sleeping...")
            time.sleep(CYCLE_INTERVAL)
            continue

        dt_now = datetime.now(timezone.utc)
        if dt_now.weekday() >= 5:  # 5=Saturday, 6=Sunday
            _dual_log("INFO", "engine", "Market is closed for the weekend. Sleeping...")
            time.sleep(CYCLE_INTERVAL * 5)
            continue

        for pair in PAIRS:
            run_cycle(pair)

        time.sleep(CYCLE_INTERVAL)
