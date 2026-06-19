"""
generator.py

Brain / Signals

Job:
Convert a price movement into a structured trade signal
with direction, entry price, and TP/SL levels.

Rules:
    - No IO
    - No database imports
    - No Telegram imports
    - Same input always returns same output (pure function)
"""

from typing import Optional


# Per-pair rules: movement threshold and TP/SL offsets in price units.
# These are the Brain's knowledge of each instrument.
PAIR_RULES: dict = {
    "BTCUSD": {
        "threshold": 300,
        "tp1_offset": 300,
        "tp2_offset": 500,
        "tp3_offset": 700,
        "sl_offset":  150,
    },
    "ETHUSD": {
        "threshold": 30,
        "tp1_offset": 20,
        "tp2_offset": 35,
        "tp3_offset": 50,
        "sl_offset":  10,
    },
}


def get_pair_rules(pair: str) -> Optional[dict]:
    """Return the TP/SL rules for a given pair, or None if unsupported."""
    return PAIR_RULES.get(pair.upper())


def create_signal(
    pair: str,
    start_price: float,
    current_price: float,
) -> Optional[dict]:
    """
    Convert a detected price movement into a trade signal.

    Returns None if the movement is below the pair's threshold.

    Returns a dict with:
        pair        - Trading pair (e.g. 'BTCUSD')
        direction   - 'BUY' or 'SELL'
        entry       - Price at which movement started (reference price)
        tp1         - Take profit level 1
        tp2         - Take profit level 2
        tp3         - Take profit level 3
        sl          - Stop loss level

    Example (BUY):
        start = 100_000, current = 100_350, threshold = 300
        → entry = 100_000
        → TP1   = 100_300
        → TP2   = 100_500
        → TP3   = 100_700
        → SL    =  99_850
    """
    rules = get_pair_rules(pair)
    if rules is None:
        raise ValueError(f"Unsupported pair: {pair}")

    threshold = rules["threshold"]
    movement = current_price - start_price

    if abs(movement) < threshold:
        return None

    direction = "BUY" if movement > 0 else "SELL"

    if direction == "BUY":
        tp1 = start_price + rules["tp1_offset"]
        tp2 = start_price + rules["tp2_offset"]
        tp3 = start_price + rules["tp3_offset"]
        sl  = start_price - rules["sl_offset"]
    else:
        tp1 = start_price - rules["tp1_offset"]
        tp2 = start_price - rules["tp2_offset"]
        tp3 = start_price - rules["tp3_offset"]
        sl  = start_price + rules["sl_offset"]

    return {
        "pair":          pair,
        "direction":     direction,
        "entry":         start_price,
        "current_price": current_price,
        "tp1":           tp1,
        "tp2":           tp2,
        "tp3":           tp3,
        "sl":            sl,
    }
