"""
repository.py

Memory / Repository

Job:
All database read and write operations for the entire system.

Rules:
    - No business logic (no pip calculations, no direction decisions)
    - No Telegram imports
    - No core/ imports
    - Every function opens, uses, and closes its own connection
    - The log() function must NEVER crash — it swallows its own exceptions
"""

import sqlite3
from datetime import datetime, timezone
from typing import Optional
from data.database import get_connection


# ==============================================================
# SETTINGS
# ==============================================================

def get_settings() -> dict:
    """Return the single settings row as a plain dict."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM settings WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else {}


def update_setting(key: str, value) -> None:
    """
    Update a single column in the settings row.

    WARNING: `key` is interpolated directly — only call with
    trusted, hard-coded column names, never with user input.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        f"UPDATE settings SET {key} = ? WHERE id = 1",
        (value,)
    )
    conn.commit()
    conn.close()


def increment_win_streak() -> None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE settings SET win_streak = win_streak + 1, total_wins = total_wins + 1 WHERE id = 1"
    )
    conn.commit()
    conn.close()


def reset_win_streak(loss_date: str) -> None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE settings SET win_streak = 0, total_losses = total_losses + 1, last_loss_date = ? WHERE id = 1",
        (loss_date,)
    )
    conn.commit()
    conn.close()


# ==============================================================
# REFERENCE PRICES
# ==============================================================

def get_reference_price(pair: str) -> Optional[float]:
    """Return the stored reference price for a pair, or None if not set."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT price FROM reference_prices WHERE pair = ?",
        (pair,)
    )
    row = cursor.fetchone()
    conn.close()
    return float(row["price"]) if row else None


def set_reference_price(pair: str, price: float) -> None:
    """
    Insert or update the reference price for a pair.
    Called:
      - On first startup for each pair (seed)
      - After every trade closes (new starting point)
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO reference_prices (pair, price, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(pair) DO UPDATE SET
            price      = excluded.price,
            updated_at = excluded.updated_at
        """,
        (pair, price)
    )
    conn.commit()
    conn.close()


# ==============================================================
# TRADES
# ==============================================================

def create_trade(
    pair: str,
    direction: str,
    entry_price: float,
    tp1: float,
    tp2: float,
    tp3: float,
    sl: float,
    lot_size: float = 0.1,
) -> int:
    """
    Insert a new trade record and return its auto-incremented ID.
    current_price is seeded to entry_price on creation.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO trades
            (pair, direction, entry_price, current_price, tp1, tp2, tp3, sl, lot_size)
        VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (pair, direction, entry_price, entry_price, tp1, tp2, tp3, sl, lot_size)
    )
    trade_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return trade_id


def get_active_trade(pair: str) -> Optional[dict]:
    """
    Return the most recent open trade for a specific pair, or None.
    One active trade per pair is the invariant.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT * FROM trades
        WHERE status = 'OPEN' AND pair = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (pair,)
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_active_trades() -> list[dict]:
    """Return all currently open trades across all pairs."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM trades WHERE status = 'OPEN' ORDER BY id DESC"
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_trade_stage(trade_id: int, stage: str) -> None:
    """Advance a trade to the given stage (TP1, TP2, TP3)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE trades SET stage = ? WHERE id = ?",
        (stage, trade_id)
    )
    conn.commit()
    conn.close()


def update_trade_price(trade_id: int, price: float) -> None:
    """Update the live price snapshot on a trade."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE trades SET current_price = ? WHERE id = ?",
        (price, trade_id)
    )
    conn.commit()
    conn.close()


def close_trade(trade_id: int, final_price: float, close_stage: str) -> None:
    """
    Mark a trade as closed.
    close_stage records HOW it closed: TP1, TP2, TP3, or SL.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE trades SET
            current_price = ?,
            status        = 'CLOSED',
            close_stage   = ?,
            closed_at     = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (final_price, close_stage, trade_id)
    )
    conn.commit()
    conn.close()


def mark_trade_posted(trade_id: int) -> None:
    """Flag that this trade's signal has been posted to Telegram."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE trades SET posted_to_telegram = 1 WHERE id = ?",
        (trade_id,)
    )
    conn.commit()
    conn.close()


def count_trades_today() -> int:
    """Return total trades (open + closed) created today (UTC)."""
    conn = get_connection()
    cursor = conn.cursor()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cursor.execute(
        "SELECT COUNT(*) AS cnt FROM trades WHERE date(created_at) = ?",
        (today,)
    )
    row = cursor.fetchone()
    conn.close()
    return int(row["cnt"]) if row else 0


def get_trade_history(limit: int = 50) -> list[dict]:
    """Return the most recent `limit` trades, newest first."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM trades ORDER BY id DESC LIMIT ?",
        (limit,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ==============================================================
# SYSTEM LOG
# ==============================================================

def log(level: str, source: str, message: str) -> None:
    """
    Write a structured log entry to the system_log table.

    level  : INFO | WARNING | ERROR
    source : module path string, e.g. 'engine.BTCUSD'
    message: human-readable description

    This function NEVER raises — logging must not crash the system.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO system_log (level, source, message) VALUES (?, ?, ?)",
            (level, source, message)
        )
        conn.commit()
        conn.close()
    except Exception:
        pass  # Intentional: logging failure must not kill the engine
