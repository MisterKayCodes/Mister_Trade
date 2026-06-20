"""
trade_engine.py

Deprecated: The continuous polling engine is now replaced by the
APScheduler in services/scheduler.py for Phase 9 time-based marketing.
We keep run_forever() as a dummy loop so main.py doesn't crash,
but all real activity is now scheduled.
"""

import time
import logging

logger = logging.getLogger(__name__)

def run_forever() -> None:
    """
    Dummy loop to keep the background thread alive without doing work.
    Real trading is now driven entirely by services/scheduler.py.
    """
    logger.info("[engine] Phase 9: Real-time monitoring disabled. Switch to scheduled marketing mode.")
    while True:
        time.sleep(3600)
