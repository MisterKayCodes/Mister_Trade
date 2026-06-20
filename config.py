"""
config.py

Skeleton / Configuration

Job:
Load environment variables and expose typed constants
to all other modules.

Rules:
    - No business logic
    - No IO beyond reading env vars
    - Import this module; never read os.environ directly elsewhere
"""

import os
from dotenv import load_dotenv

load_dotenv()


# ------------------------------------------------------------------
# Database
# ------------------------------------------------------------------
DB_PATH: str = os.getenv("DB_PATH", "mister_trade.db")


# ------------------------------------------------------------------
# Telegram  (populated from Phase 3 onwards)
# ------------------------------------------------------------------
BOT_TOKEN: str  = os.getenv("BOT_TOKEN", "")
CHANNEL_ID: str = os.getenv("CHANNEL_ID", "")

_raw_admin_ids = os.getenv("ADMIN_IDS", "")
ADMIN_IDS: list[int] = [
    int(x.strip())
    for x in _raw_admin_ids.split(",")
    if x.strip().isdigit()
]


# ------------------------------------------------------------------
# Trading Engine
# ------------------------------------------------------------------
# Pairs monitored by the engine
PAIRS: list[str] = ["BTCUSD", "ETHUSD", "EURUSD", "GBPUSD"]

# Pairs that are Forex (pip-based movement) vs Crypto (dollar-based)
FOREX_PAIRS: list[str] = ["EURUSD", "GBPUSD"]
CRYPTO_PAIRS: list[str] = ["BTCUSD", "ETHUSD"]

# Pip threshold for Forex pairs (30 pips = 0.0030)
FOREX_PIP_THRESHOLD: float = 0.0030

# How often the lifecycle loop runs (seconds)
CYCLE_INTERVAL: int = int(os.getenv("CYCLE_INTERVAL", "30"))

# ------------------------------------------------------------------
# Testing
# ------------------------------------------------------------------
TEST_MODE: bool = os.getenv("TEST_MODE", "True").lower() in ("true", "1", "yes")
