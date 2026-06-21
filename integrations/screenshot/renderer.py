"""
renderer.py

Integrations / Screenshot

Job:
    Take a dictionary of trade data, inject it into an HTML template,
    and render it as a PNG using html2image.

Rules:
    - Pure synchronous IO (html2image blocks)
    - Always output to a temporary file, return the path
    - Smart Balance: auto-generates a realistic account balance
      that is always large enough to cover the selected lot size
    - Forex pairs use 5-decimal precision; Crypto uses 2-decimal
"""

import os
import random
from datetime import datetime
from html2image import Html2Image
from typing import Dict, Any

hti = Html2Image(size=(400, 350))
hti.browser.executable = '/usr/bin/google-chrome'

hti.browser.flags = [
    '--headless',
    '--disable-gpu',
    '--hide-scrollbars',
    '--mute-audio',
    '--no-sandbox',
    '--default-background-color=00000000'
]

TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "template.html")
OUTPUT_DIR    = os.path.join(os.path.dirname(__file__), "output")

if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)


# ==============================================================
# Helpers
# ==============================================================

def _is_forex(pair: str) -> bool:
    return pair.upper() in ("EURUSD", "GBPUSD")


def _fmt(v: float, precision: int = 2) -> str:
    """Format a number with space thousands separator (MT5 style)."""
    return f"{float(v):,.{precision}f}".replace(",", " ")


def _smart_balance(lot_size: float, today_str: str) -> float:
    """
    Generate a day-consistent account balance that is always large
    enough to make the lot size look legitimate.

    For whale lots (lot_size × $10,000 > $5k):
        Balance is randomised between  lot * $10k * 1.1  and  lot * $10k * 3.0
    For standard lots:
        Balance is a random value between $5,000 and $63,000
    """
    rng = random.Random(today_str)
    min_balance = lot_size * 10_000

    if min_balance <= 5_000:
        return rng.uniform(5_000, 63_000)
    return rng.uniform(min_balance * 1.1, min_balance * 3.0)


def render_signal_image(trade_data: Dict[str, Any], filename: str = "signal.png") -> str:
    """
    Renders an HTML template to a PNG and returns the absolute path.

    trade_data expects:
        pair, direction, entry, tp1, tp2, tp3, sl, lot_size
    """
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        html_content = f.read()

    pair      = trade_data.get("pair", "")
    direction = trade_data.get("direction", "BUY")
    lot_size  = float(trade_data.get("lot_size", 10.0))
    forex     = _is_forex(pair)

    direction_color = "#3096FA" if direction == "BUY" else "#F44336"
    direction_text  = f"{direction.lower()} {lot_size:g}"
    precision       = 5 if forex else 2

    raw_entry   = float(trade_data.get("entry", 0))
    raw_current = float(trade_data.get("tp1",   0))

    entry_price   = _fmt(raw_entry,   precision)
    current_price = _fmt(raw_current, precision)

    # Profit: Forex = $10/pip per lot (100k contract) | Crypto = $1 per $1 per lot
    diff       = (raw_current - raw_entry) if direction == "BUY" else (raw_entry - raw_current)
    multiplier = 100_000 if forex else 1
    profit_val = abs(diff * lot_size * multiplier)
    profit     = _fmt(profit_val, 2)

    # Smart Balance — day-consistent and always margin-safe
    if "override_balance" in trade_data:
        balance_val = float(trade_data["override_balance"])
    else:
        today_str        = datetime.now().strftime("%Y-%m-%d")
        balance_val      = _smart_balance(lot_size, today_str)
        
    equity_val       = balance_val + profit_val
    margin_val       = lot_size * (1_000 if forex else 500)
    free_margin_val  = equity_val - margin_val
    margin_level_val = (equity_val / margin_val) * 100 if margin_val > 0 else 0

    balance      = _fmt(balance_val,      2)
    equity       = _fmt(equity_val,       2)
    margin       = _fmt(margin_val,       2)
    free_margin  = _fmt(free_margin_val,  2)
    margin_level = _fmt(margin_level_val, 2)

    # Replace all template placeholders
    html_content = html_content.replace("{{pair}}",            pair)
    html_content = html_content.replace("{{direction_color}}", direction_color)
    html_content = html_content.replace("{{direction_text}}",  direction_text)
    html_content = html_content.replace("{{entry_price}}",     entry_price)
    html_content = html_content.replace("{{current_price}}",   current_price)
    html_content = html_content.replace("{{profit}}",          profit)
    html_content = html_content.replace("{{total_profit}}",    profit)
    html_content = html_content.replace("{{balance}}",         balance)
    html_content = html_content.replace("{{equity}}",          equity)
    html_content = html_content.replace("{{margin}}",          margin)
    html_content = html_content.replace("{{free_margin}}",     free_margin)
    html_content = html_content.replace("{{margin_level}}",    margin_level)

    hti.output_path = OUTPUT_DIR
    hti.screenshot(html_str=html_content, save_as=filename)

    output_path = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(output_path):
        raise FileNotFoundError(
            f"html2image failed to create screenshot at {output_path}. "
            "Chrome might have crashed."
        )

    return output_path
