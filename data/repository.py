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


def clear_active_trades() -> int:
    """Force close (delete) all OPEN trades. Returns count."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM trades WHERE status = 'OPEN'")
    count = cursor.rowcount
    conn.commit()
    conn.close()
    return count


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


def update_trade_watermark(trade_id: int, watermark: float) -> None:
    """Update the high watermark (highest price reached in favour of trade)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE trades SET high_watermark = ? WHERE id = ?",
        (watermark, trade_id)
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


# ==============================================================
# TESTIMONIALS
# ==============================================================

def add_testimonial(script: str) -> int:
    """Insert a new testimonial script. Returns its ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO testimonials (script) VALUES (?)", (script,))
    tid = cursor.lastrowid
    conn.commit()
    conn.close()
    return tid


def get_random_testimonial() -> Optional[dict]:
    """Return a random enabled testimonial, or None if the pool is empty."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM testimonials WHERE enabled = 1 ORDER BY RANDOM() LIMIT 1"
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def list_testimonials() -> list:
    """Return all testimonials for admin display."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, script, enabled FROM testimonials ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_testimonial(tid: int) -> None:
    """Permanently remove a testimonial by ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM testimonials WHERE id = ?", (tid,))
    conn.commit()
    conn.close()


# ==============================================================
# WEEKLY STATS
# ==============================================================

def get_weekly_stats() -> dict:
    """
    Return a summary of all closed trades from the current Mon-Sun week (UTC).
    Returns: {wins, losses, total, win_rate, best_stage}
    """
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    monday = now - timedelta(days=now.weekday())
    week_start = monday.strftime("%Y-%m-%d")

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT close_stage, COUNT(*) AS cnt
        FROM trades
        WHERE status = 'CLOSED'
          AND date(closed_at) >= ?
        GROUP BY close_stage
        """,
        (week_start,)
    )
    rows = cursor.fetchall()
    conn.close()

    wins   = 0
    losses = 0
    for row in rows:
        stage = row["close_stage"]
        cnt   = row["cnt"]
        if stage in ("TP1", "TP2", "TP3"):
            wins += cnt
        elif stage in ("SL", "FORCED_LOSS"):
            losses += cnt

    total    = wins + losses
    win_rate = round((wins / total * 100), 1) if total > 0 else 0.0

    return {
        "wins":     wins,
        "losses":   losses,
        "total":    total,
        "win_rate": win_rate,
    }


# ==============================================================
# FLIP CAMPAIGNS
# ==============================================================

def create_flip_campaign(start_balance: float, target_balance: float) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO flip_campaigns (start_balance, target_balance, current_balance, status)
        VALUES (?, ?, ?, 'ACTIVE')
        """,
        (start_balance, target_balance, start_balance)
    )
    cid = cursor.lastrowid
    conn.commit()
    conn.close()
    return cid


def get_active_flip_campaign() -> Optional[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM flip_campaigns WHERE status = 'ACTIVE' ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def update_flip_campaign(cid: int, new_balance: float) -> None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE flip_campaigns SET current_balance = ?, trade_count = trade_count + 1 WHERE id = ?",
        (new_balance, cid)
    )
    conn.commit()
    conn.close()


def complete_flip_campaign(cid: int) -> None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE flip_campaigns SET status = 'COMPLETED', completed_at = CURRENT_TIMESTAMP WHERE id = ?",
        (cid,)
    )
    conn.commit()
    conn.close()


def stop_flip_campaign(cid: int) -> None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE flip_campaigns SET status = 'STOPPED', completed_at = CURRENT_TIMESTAMP WHERE id = ?",
        (cid,)
    )
    conn.commit()
    conn.close()


# ==============================================================
# COPIER CHANNELS
# ==============================================================

def create_copier_channel(
    channel_id: str,
    name: str,
    tone: str = "PROFESSIONAL",
    risk_type: str = "USD_RISK",
    risk_value: float = 50.0,
    max_trades_per_day: int = 3,
    admin_name: str = "Admin",
    owner_user_id: int = None,
) -> int:
    """Register a new copier channel. Returns its database ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT OR IGNORE INTO copier_channels
            (channel_id, owner_user_id, name, tone, risk_type, risk_value, max_trades_per_day, admin_name)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (channel_id, owner_user_id, name, tone, risk_type, risk_value, max_trades_per_day, admin_name)
    )
    cid = cursor.lastrowid
    conn.commit()
    conn.close()
    return cid


def get_all_active_copier_channels() -> list[dict]:
    """Return all active copier channels."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM copier_channels WHERE active = 1 ORDER BY id")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_copier_channels() -> list[dict]:
    """Return all copier channels (active + inactive) for admin display."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM copier_channels ORDER BY id")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_copier_channel_by_id(channel_id: str) -> Optional[dict]:
    """Look up a single copier channel by its Telegram channel ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM copier_channels WHERE channel_id = ?", (channel_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def toggle_copier_channel(channel_id: str) -> bool:
    """Toggle a channel active <-> inactive. Returns the new active state."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE copier_channels SET active = CASE WHEN active = 1 THEN 0 ELSE 1 END WHERE channel_id = ?",
        (channel_id,)
    )
    cursor.execute("SELECT active FROM copier_channels WHERE channel_id = ?", (channel_id,))
    row = cursor.fetchone()
    conn.commit()
    conn.close()
    return bool(row["active"]) if row else False


def update_copier_channel(channel_id: str, **kwargs) -> None:
    """
    Update one or more fields on a copier channel.
    Allowed keys: name, tone, risk_type, risk_value, max_trades_per_day, admin_name

    WARNING: keys are interpolated — only call with hard-coded column names.
    """
    allowed = {"name", "tone", "risk_type", "risk_value", "max_trades_per_day", "admin_name"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [channel_id]
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"UPDATE copier_channels SET {set_clause} WHERE channel_id = ?", values)
    conn.commit()
    conn.close()


def delete_copier_channel(channel_id: str) -> None:
    """Permanently remove a copier channel."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM copier_channels WHERE channel_id = ?", (channel_id,))
    conn.commit()
    conn.close()


def count_channel_trades_today(channel_id: str) -> int:
    """
    Count how many trades have already been distributed to a specific channel today.
    We use the master trades table since all channels receive the same base trade.
    This serves as a quota check before sending a signal to a channel.
    """
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
