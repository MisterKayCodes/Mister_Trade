"""
main.py

Skeleton / Entry Point

Job:
Initialize the database and start the trade engine.
Nothing else lives here.

Usage:
    python main.py
"""

import logging
from data.database import init_db
from services.trade_engine import run_forever

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


if __name__ == "__main__":
    init_db()
    run_forever()
