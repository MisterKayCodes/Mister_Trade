"""
router.py

Eyes / Price Router

Job:
    Single entry point for fetching prices for ALL supported pairs.
    Routes Crypto pairs to CoinGecko, Forex pairs to Yahoo Finance.

Rules:
    - This is the ONLY file the rest of the codebase imports for prices
    - Never import coingecko.py or yahoo.py directly outside providers/
    - Returns None on failure — never raises
"""

from typing import Optional
from providers.price.coingecko import get_crypto_price, COIN_MAP
from providers.price.yahoo import get_forex_price, FOREX_MAP


def get_current_price(pair: str) -> Optional[float]:
    """
    Fetch the current price for any supported pair.

    Automatically routes:
        BTCUSD / ETHUSD  → CoinGecko
        EURUSD / GBPUSD  → Yahoo Finance

    Returns None on failure.
    """
    pair = pair.upper()

    if pair in COIN_MAP:
        return get_crypto_price(pair)

    if pair in FOREX_MAP:
        return get_forex_price(pair)

    raise ValueError(
        f"Unsupported pair: '{pair}'. "
        f"Known crypto: {list(COIN_MAP)}, Known forex: {list(FOREX_MAP)}"
    )
