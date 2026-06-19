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


def get_crypto_price(pair: str) -> Optional[float]:
    """
    Return the current USD price for the given pair.

    Retries up to MAX_RETRIES times on any network or parse error.
    Returns None if all attempts fail — the caller handles None gracefully.

    Raises ValueError for unknown pairs (programming error, not runtime).
    """
    coin_id = COIN_MAP.get(pair.upper())
    if coin_id is None:
        raise ValueError(f"Unsupported pair: '{pair}'. Known pairs: {list(COIN_MAP)}")

    last_error: Optional[Exception] = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(
                API_URL,
                params={"ids": coin_id, "vs_currencies": "usd"},
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
            price = float(data[coin_id]["usd"])
            return price

        except Exception as exc:
            last_error = exc
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)

    # All retries exhausted — log context is handled by caller
    return None
