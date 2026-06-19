"""
detector.py

Brain / Movement

Job:
Measure distance between two prices and determine
if the movement exceeds a configured threshold.

Rules:
    - No IO
    - No database imports
    - No Telegram imports
    - Same input always returns same output (pure function)
"""


def calculate_movement(start_price: float, current_price: float) -> float:
    """
    Return the signed difference between start and current price.

    Positive = price went up.
    Negative = price went down.

    Example:
        start = 100_000, current = 100_300 → result = 300.0
        start = 100_000, current = 99_700  → result = -300.0
    """
    return current_price - start_price


def has_moved(
    start_price: float,
    current_price: float,
    threshold: float,
) -> bool:
    """
    Return True if absolute price movement meets or exceeds the threshold.

    Example:
        BTC moved $300, threshold = $300 → True
        BTC moved $150, threshold = $300 → False
    """
    movement = abs(calculate_movement(start_price, current_price))
    return movement >= threshold


def get_direction(start_price: float, current_price: float) -> str:
    """
    Return 'BUY' if price moved up, 'SELL' if it moved down.

    Example:
        start = 100_000, current = 100_300 → 'BUY'
        start = 100_000, current = 99_700  → 'SELL'
    """
    return "BUY" if current_price > start_price else "SELL"
