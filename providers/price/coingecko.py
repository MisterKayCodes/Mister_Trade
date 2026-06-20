"""
coingecko.py

Eyes / Price Provider

Job:
Fetch the current USD price for a configured crypto pair
from the CoinGecko public API.

Rules:
    - Returns None on failure — never raises in the lifecycle loop
    - Retries up to MAX_RETRIES times before giving up
    - No Trade objects, no User objects, no Telegram
    - Only sees raw prices and symbols
"""

import time
import requests
from typing import Optional


API_URL = "https://api.coingecko.com/api/v3/simple/price"

COIN_MAP: dict[str, str] = {
    "BTCUSD": "bitcoin",
    "ETHUSD": "ethereum",
}

MAX_RETRIES  = 3
RETRY_DELAY  = 2   # seconds between retries
TIMEOUT      = 10  # seconds per request


_CACHE = {}
_CACHE_TTL = 15  # seconds

def get_crypto_price(pair: str) -> Optional[float]:
    """
    Return the current USD price for the given pair.

    Batches requests for all configured pairs and caches them 
    to avoid hitting the CoinGecko rate limits.
    """
    coin_id = COIN_MAP.get(pair.upper())
    if coin_id is None:
        raise ValueError(f"Unsupported pair: '{pair}'. Known pairs: {list(COIN_MAP)}")

    now = time.time()
    # Check cache first
    if coin_id in _CACHE:
        price, timestamp = _CACHE[coin_id]
        if now - timestamp < _CACHE_TTL:
            return price

    last_error: Optional[Exception] = None
    all_coin_ids = ",".join(COIN_MAP.values())

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(
                API_URL,
                params={"ids": all_coin_ids, "vs_currencies": "usd"},
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
            
            # Update cache for all fetched coins
            for cid in COIN_MAP.values():
                if cid in data and "usd" in data[cid]:
                    _CACHE[cid] = (float(data[cid]["usd"]), now)
            
            # Return requested price if available
            if coin_id in _CACHE:
                return _CACHE[coin_id][0]
                
            return None

        except Exception as exc:
            last_error = exc
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)

    # All retries exhausted
    return None
