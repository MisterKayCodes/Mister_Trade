"""
tracker.py

Brain / Trades

Job:
Evaluate the current state of a trade against a live price
and return the action the Nervous System should take.

Rules:
    - No IO
    - No database imports
    - No Telegram imports
    - Same input always returns same output (pure function)

Stage fallback logic:
    BUY trade reached TP2, price drops back below TP2 → close (lock TP2 profit)
    BUY trade reached TP1, price drops back below TP1 → close (lock TP1 profit)
    SELL trade mirrors the same logic in reverse.
"""

from typing import Literal
from datetime import datetime, timezone

Action = Literal["HOLD", "UPDATE_STAGE", "CLOSE"]
Stage  = Literal["OPEN", "TP1", "TP2", "TP3", "SL", "TIME_LIMIT", "FORCED_LOSS"]


def _hours_open(created_at_str: str) -> float:
    if not created_at_str:
        return 0.0
    try:
        # Expected format from SQLite CURRENT_TIMESTAMP
        dt = datetime.strptime(created_at_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return (now - dt).total_seconds() / 3600.0
    except Exception:
        return 0.0


def _is_loss(direction: str, current_price: float, entry_price: float) -> bool:
    if direction == "BUY":
        return current_price < entry_price
    return current_price > entry_price


def _needs_forced_loss(settings: dict) -> bool:
    streak = int(settings.get("win_streak", 0))
    if streak >= 10:
        return True
    
    last_loss = settings.get("last_loss_date")
    if not last_loss:
        return False
        
    try:
        dt = datetime.strptime(last_loss, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        days_since = (now - dt).total_seconds() / 86400.0
        return days_since >= 3.0
    except Exception:
        return False


def evaluate_trade(trade: dict, current_price: float, settings: dict) -> dict:
    """
    Evaluate a trade against the current market price and system settings.

    Returns:
        {
            "action": "HOLD" | "UPDATE_STAGE" | "CLOSE",
            "stage":  "TP1" | "TP2" | "TP3" | "SL" | "TIME_LIMIT" | "FORCED_LOSS" | <current_stage>,
            "price":  float
        }

    The Nervous System reads this result and calls the repository.
    This function never touches the database.
    """
    direction     = trade["direction"]
    current_stage = trade.get("stage", "OPEN")
    tp1           = float(trade["tp1"])
    tp2           = float(trade["tp2"])
    tp3           = float(trade["tp3"])
    sl            = float(trade["sl"])
    entry_price   = float(trade["entry_price"])

    # 1. Guard: Duration Limit (> 6 hours)
    hours = _hours_open(trade.get("created_at", ""))
    if hours >= 6.0:
        return _result("CLOSE", "TIME_LIMIT", current_price)

    # 2. Guard: Forced Loss
    if _needs_forced_loss(settings):
        # If we need a loss, and the trade is currently in a loss, lock it in early
        if _is_loss(direction, current_price, entry_price):
            return _result("CLOSE", "FORCED_LOSS", current_price)

    if direction == "BUY":
        return _evaluate_buy(current_stage, current_price, tp1, tp2, tp3, sl)
    else:
        return _evaluate_sell(current_stage, current_price, tp1, tp2, tp3, sl)


# ------------------------------------------------------------------
# BUY evaluation
# ------------------------------------------------------------------

def _evaluate_buy(
    stage: str,
    price: float,
    tp1: float,
    tp2: float,
    tp3: float,
    sl: float,
) -> dict:

    # TP3 hit → close at max profit
    if price >= tp3:
        return _result("CLOSE", "TP3", price)

    # TP2 hit → update stage (not a close yet, let it run to TP3)
    if price >= tp2 and stage in ("OPEN", "TP1"):
        return _result("UPDATE_STAGE", "TP2", price)

    # TP1 hit → update stage (not a close yet, let it run to TP2)
    if price >= tp1 and stage == "OPEN":
        return _result("UPDATE_STAGE", "TP1", price)

    # Fallback: was at TP2, price fell back below TP2 → lock profit
    if stage == "TP2" and price < tp2:
        return _result("CLOSE", "TP2", price)

    # Fallback: was at TP1, price fell back below TP1 → lock profit
    if stage == "TP1" and price < tp1:
        return _result("CLOSE", "TP1", price)

    # Stop loss hit
    if price <= sl:
        return _result("CLOSE", "SL", price)

    # Nothing to do
    return _result("HOLD", stage, price)


# ------------------------------------------------------------------
# SELL evaluation
# ------------------------------------------------------------------

def _evaluate_sell(
    stage: str,
    price: float,
    tp1: float,
    tp2: float,
    tp3: float,
    sl: float,
) -> dict:

    # TP3 hit → close at max profit
    if price <= tp3:
        return _result("CLOSE", "TP3", price)

    # TP2 hit → update stage
    if price <= tp2 and stage in ("OPEN", "TP1"):
        return _result("UPDATE_STAGE", "TP2", price)

    # TP1 hit → update stage
    if price <= tp1 and stage == "OPEN":
        return _result("UPDATE_STAGE", "TP1", price)

    # Fallback: was at TP2, price bounced back above TP2 → lock profit
    if stage == "TP2" and price > tp2:
        return _result("CLOSE", "TP2", price)

    # Fallback: was at TP1, price bounced back above TP1 → lock profit
    if stage == "TP1" and price > tp1:
        return _result("CLOSE", "TP1", price)

    # Stop loss hit
    if price >= sl:
        return _result("CLOSE", "SL", price)

    # Nothing to do
    return _result("HOLD", stage, price)


# ------------------------------------------------------------------
# Helper
# ------------------------------------------------------------------

def _result(action: str, stage: str, price: float) -> dict:
    return {"action": action, "stage": stage, "price": price}
