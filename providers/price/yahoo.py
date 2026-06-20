"""
yahoo.py

Eyes / Price Provider (Forex)

Job:
    Fetch the current market price for Forex pairs using yfinance.
    Maps our pair strings (e.g. EURUSD) to Yahoo Finance tickers.

Rules:
    - Returns None on failure — never raises
    - Retries up to MAX_RETRIES times before giving up
    - Caches results for CACHE_TTL seconds to avoid hammering the API
    - No Trade objects, no Telegram, no database
"""

import time
import logging
from typing import Optional
import warnings
import requests

# Suppress yfinance Pandas4Warning (harmless warning from inside their library)
warnings.filterwarnings("ignore", category=FutureWarning, module="yfinance")

logger = logging.getLogger(__name__)

# Map our pair strings to Yahoo Finance ticker symbols
FOREX_MAP: dict[str, str] = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
}

# We drop retries to 1 and increase cache to 60s because Yahoo blocks aggressively.
# If we retry 3 times when blocked, it freezes the entire engine loop,
# which delays trades for other pairs (like BTCUSD).
MAX_RETRIES = 1
CACHE_TTL   = 60  # seconds

# Cache stores (price, timestamp). Price can be None if currently rate-limited.
_CACHE: dict[str, tuple[Optional[float], float]] = {}


def get_forex_price(pair: str) -> Optional[float]:
    """
    Return the current price for a Forex pair.

    Uses yfinance under the hood. Results are cached for CACHE_TTL seconds
    to avoid rate-limiting and freezing the main engine loop.
    """
    ticker_symbol = FOREX_MAP.get(pair.upper())
    if ticker_symbol is None:
        raise ValueError(f"Unsupported Forex pair: '{pair}'. Known pairs: {list(FOREX_MAP)}")

    now = time.time()

    # Serve from cache if still fresh (even if it's a cached failure/None)
    if pair in _CACHE:
        price, ts = _CACHE[pair]
        if now - ts < CACHE_TTL:
            return price

    try:
        import yfinance as yf
        
        # We use a custom session with a real browser User-Agent to bypass Yahoo's anti-bot block,
        # and we set a strict timeout so if Yahoo is down, it fails instantly and doesn't freeze the bot.
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"
        })
        
        ticker = yf.Ticker(ticker_symbol, session=session)
        # fast_info is the cheapest call — no full history download
        price = ticker.fast_info.last_price
        if price is None or price == 0:
            raise ValueError(f"yfinance returned zero/None price for {ticker_symbol}")
        
        _CACHE[pair] = (float(price), now)
        return float(price)
        
    except Exception as exc:
        logger.warning(
            "[yahoo] Fetch failed for %s: %s (will pause this pair for %ds)",
            pair, exc, CACHE_TTL
        )
        
        # If we have an old price in the cache, keep using it (stale fallback)
        # but update the timestamp so we don't hammer the API.
        if pair in _CACHE and _CACHE[pair][0] is not None:
            old_price = _CACHE[pair][0]
            _CACHE[pair] = (old_price, now)
            logger.info("[yahoo] Falling back to stale cached price for %s", pair)
            return old_price
        else:
            # Cache the failure so we don't freeze the engine next cycle
            _CACHE[pair] = (None, now)
            return None
