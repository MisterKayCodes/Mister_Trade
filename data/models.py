"""
models.py

Memory / Models

Job:
Define all database table schemas as SQL strings.

Rules:
    - No queries
    - No connections
    - No business logic
    - Only CREATE TABLE and seed INSERT statements
"""


# ------------------------------------------------------------------
# Table: settings
# Single-row config store (id is always 1).
# ------------------------------------------------------------------
CREATE_SETTINGS = """
CREATE TABLE IF NOT EXISTS settings (
    id                  INTEGER PRIMARY KEY CHECK (id = 1),
    mode                TEXT    DEFAULT 'crypto',
    trading_enabled     INTEGER DEFAULT 1,
    pip_threshold       REAL    DEFAULT 300,
    max_trades_per_day  INTEGER DEFAULT 3,
    starting_balance    REAL    DEFAULT 10000,
    current_balance     REAL    DEFAULT 10000,
    risk_percent        REAL    DEFAULT 1.0,
    lot_size            REAL    DEFAULT 0.1,
    win_streak          INTEGER DEFAULT 0,
    total_wins          INTEGER DEFAULT 0,
    total_losses        INTEGER DEFAULT 0,
    last_loss_date      TEXT    DEFAULT NULL,
    admin_name          TEXT    DEFAULT 'Mike',
    admin_contact       TEXT    DEFAULT '@MisterTrade'
)
"""

# ------------------------------------------------------------------
# Table: reference_prices
# One row per pair. Updated after every trade close.
# ------------------------------------------------------------------
CREATE_REFERENCE_PRICES = """
CREATE TABLE IF NOT EXISTS reference_prices (
    pair        TEXT PRIMARY KEY,
    price       REAL    NOT NULL,
    updated_at  TEXT    DEFAULT CURRENT_TIMESTAMP
)
"""

# ------------------------------------------------------------------
# Table: trades
# Full history of every paper trade.
# ------------------------------------------------------------------
CREATE_TRADES = """
CREATE TABLE IF NOT EXISTS trades (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    pair                TEXT    NOT NULL,
    direction           TEXT    NOT NULL,
    entry_price         REAL    NOT NULL,
    current_price       REAL,
    tp1                 REAL,
    tp2                 REAL,
    tp3                 REAL,
    sl                  REAL,
    lot_size            REAL    DEFAULT 0.1,
    stage               TEXT    DEFAULT 'OPEN',
    status              TEXT    DEFAULT 'OPEN',
    close_stage         TEXT    DEFAULT NULL,
    posted_to_telegram  INTEGER DEFAULT 0,
    created_at          TEXT    DEFAULT CURRENT_TIMESTAMP,
    closed_at           TEXT    DEFAULT NULL
)
"""

# ------------------------------------------------------------------
# Table: system_log
# Structured log entries from all modules.
# ------------------------------------------------------------------
CREATE_SYSTEM_LOG = """
CREATE TABLE IF NOT EXISTS system_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    level       TEXT    NOT NULL,
    source      TEXT    NOT NULL,
    message     TEXT    NOT NULL,
    created_at  TEXT    DEFAULT CURRENT_TIMESTAMP
)
"""

# ------------------------------------------------------------------
# Table: testimonials
# Pool of testimonial scripts managed from the admin panel.
# ------------------------------------------------------------------
CREATE_TESTIMONIALS = """
CREATE TABLE IF NOT EXISTS testimonials (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    script      TEXT    NOT NULL,
    enabled     INTEGER DEFAULT 1,
    created_at  TEXT    DEFAULT CURRENT_TIMESTAMP
)
"""

# ------------------------------------------------------------------
# Table: flip_campaigns
# Tracks multi-trade compounding challenges.
# ------------------------------------------------------------------
CREATE_FLIP_CAMPAIGNS = """
CREATE TABLE IF NOT EXISTS flip_campaigns (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    start_balance   REAL    NOT NULL,
    target_balance  REAL    NOT NULL,
    current_balance REAL    NOT NULL,
    status          TEXT    DEFAULT 'ACTIVE',
    trade_count     INTEGER DEFAULT 0,
    created_at      TEXT    DEFAULT CURRENT_TIMESTAMP,
    completed_at    TEXT    DEFAULT NULL
)
"""

# ------------------------------------------------------------------
# Seed: default settings row
# INSERT OR IGNORE so it only runs once.
# ------------------------------------------------------------------
SEED_SETTINGS = """
INSERT OR IGNORE INTO settings (
    id, mode, trading_enabled, pip_threshold, max_trades_per_day,
    starting_balance, current_balance, risk_percent, lot_size,
    win_streak, total_wins, total_losses, last_loss_date, admin_name, admin_contact
)
VALUES (
    1, 'crypto', 1, 300, 3,
    10000, 10000, 1.0, 0.1,
    0, 0, 0, NULL, 'Mike', '@MisterTrade'
)
"""

MIGRATION_ADMIN_CONTACT = """
ALTER TABLE settings ADD COLUMN admin_contact TEXT DEFAULT '@MisterTrade'
"""

# ------------------------------------------------------------------
# Ordered list used by database.init_db()
# ------------------------------------------------------------------
ALL_TABLES: list[str] = [
    CREATE_SETTINGS,
    CREATE_REFERENCE_PRICES,
    CREATE_TRADES,
    CREATE_SYSTEM_LOG,
    CREATE_TESTIMONIALS,
    CREATE_FLIP_CAMPAIGNS,
]
