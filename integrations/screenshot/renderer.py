"""
renderer.py

Integrations / Screenshot

Job:
    Take a dictionary of trade data and render it as a PNG using
    Pillow (pure Python). No browser, no Chrome, no AppArmor issues.

Rules:
    - Pure synchronous IO
    - Always output to a temporary file, return the path
    - Smart Balance: auto-generates a realistic account balance
      that is always large enough to cover the selected lot size
    - Forex pairs use 5-decimal precision; Crypto uses 2-decimal
"""

import os
import random
from datetime import datetime
from typing import Dict, Any

from PIL import Image, ImageDraw, ImageFont

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")

if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

# ==============================================================
# Colour palette (MT5 dark theme inspired)
# ==============================================================
BG_COLOR        = (13,  17,  23)    # near-black background
CARD_COLOR      = (22,  27,  34)    # card surface
BORDER_COLOR    = (48,  54,  61)    # subtle border
GREEN           = (0,   200, 83)    # buy / profit green
RED             = (244, 67,  54)    # sell / loss red
BLUE            = (48,  150, 250)   # accent blue
WHITE           = (255, 255, 255)
GREY            = (139, 148, 158)
LIGHT_GREY      = (201, 209, 217)
DARK_GREEN_BG   = (0,   60,  25)    # profit badge bg
DARK_RED_BG     = (80,  10,  10)    # sell badge bg

WIDTH  = 420
HEIGHT = 390


# ==============================================================
# Helpers
# ==============================================================

def _is_forex(pair: str) -> bool:
    return pair.upper() in ("EURUSD", "GBPUSD")


def _fmt(v: float, precision: int = 2) -> str:
    """Format number with space as thousands separator (MT5 style)."""
    formatted = f"{float(v):,.{precision}f}"
    return formatted.replace(",", " ")


def _get_font(size: int, bold: bool = False):
    """Try to load a system font, fall back to default."""
    font_candidates_bold = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/calibrib.ttf",
    ]
    font_candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibri.ttf",
    ]
    candidates = font_candidates_bold if bold else font_candidates
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _smart_balance(lot_size: float, today_str: str) -> float:
    rng = random.Random(today_str)
    min_balance = lot_size * 10_000
    if min_balance <= 5_000:
        return rng.uniform(5_000, 63_000)
    return rng.uniform(min_balance * 1.1, min_balance * 3.0)


def _rounded_rect(draw: ImageDraw.ImageDraw, xy, radius: int, fill, outline=None, width=1):
    """Draw a rectangle with rounded corners."""
    x1, y1, x2, y2 = xy
    draw.rounded_rectangle([x1, y1, x2, y2], radius=radius, fill=fill,
                            outline=outline, width=width)


# ==============================================================
# Main renderer
# ==============================================================

def render_signal_image(trade_data: Dict[str, Any], filename: str = "signal.png") -> str:
    """
    Renders a Pillow-drawn signal card as a PNG and returns the absolute path.

    trade_data expects:
        pair, direction, entry, tp1, tp2, tp3, sl, lot_size
    """
    pair      = trade_data.get("pair", "")
    direction = trade_data.get("direction", "BUY")
    lot_size  = float(trade_data.get("lot_size", 10.0))
    forex     = _is_forex(pair)
    precision = 5 if forex else 2

    raw_entry   = float(trade_data.get("entry", 0))
    raw_tp1     = float(trade_data.get("tp1",   0))
    raw_tp2     = float(trade_data.get("tp2",   0))
    raw_tp3     = float(trade_data.get("tp3",   0))
    raw_sl      = float(trade_data.get("sl",    0))

    # Profit calculation
    diff       = (raw_tp1 - raw_entry) if direction == "BUY" else (raw_entry - raw_tp1)
    multiplier = 100_000 if forex else 1
    profit_val = abs(diff * lot_size * multiplier)

    # Balance
    if "override_balance" in trade_data:
        balance_val = float(trade_data["override_balance"])
    else:
        today_str   = datetime.now().strftime("%Y-%m-%d")
        balance_val = _smart_balance(lot_size, today_str)

    equity_val       = balance_val + profit_val
    margin_val       = lot_size * (1_000 if forex else 500)
    free_margin_val  = equity_val - margin_val
    margin_level_val = (equity_val / margin_val) * 100 if margin_val > 0 else 0

    is_buy   = direction == "BUY"
    dir_color = GREEN if is_buy else RED
    dir_bg    = DARK_GREEN_BG if is_buy else DARK_RED_BG
    now_str  = datetime.now().strftime("%Y.%m.%d  %H:%M:%S")

    # ==============================================================
    # Canvas
    # ==============================================================
    img  = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Fonts
    f_tiny   = _get_font(11)
    f_small  = _get_font(13)
    f_med    = _get_font(15)
    f_large  = _get_font(20, bold=True)
    f_xlarge = _get_font(26, bold=True)
    f_pair   = _get_font(22, bold=True)

    # ------ Header bar ------
    draw.rectangle([0, 0, WIDTH, 52], fill=(18, 22, 30))
    draw.text((18, 10), "MetaTrader 5", font=f_med, fill=GREY)
    draw.text((18, 30), now_str, font=f_tiny, fill=(80, 90, 100))
    # Green dot to imply live
    draw.ellipse([WIDTH - 30, 18, WIDTH - 18, 30], fill=GREEN)

    # ------ Main card ------
    _rounded_rect(draw, [14, 60, WIDTH - 14, HEIGHT - 14], radius=10,
                  fill=CARD_COLOR, outline=BORDER_COLOR, width=1)

    # ------ Pair + direction badge ------
    draw.text((30, 75), pair, font=f_xlarge, fill=WHITE)

    badge_text = f"  {direction} {lot_size:g} lot  "
    bbox = draw.textbbox((0, 0), badge_text, font=f_med)
    bw = bbox[2] - bbox[0] + 10
    bh = bbox[3] - bbox[1] + 8
    badge_x = WIDTH - 30 - bw
    _rounded_rect(draw, [badge_x, 76, badge_x + bw, 76 + bh],
                  radius=5, fill=dir_bg)
    draw.text((badge_x + 5, 79), badge_text.strip(), font=f_med, fill=dir_color)

    # Separator
    draw.line([30, 110, WIDTH - 30, 110], fill=BORDER_COLOR, width=1)

    # ------ Price table ------
    row_y = 122
    row_h = 28

    def price_row(label, value, val_color=LIGHT_GREY, y=None):
        nonlocal row_y
        _y = y if y is not None else row_y
        draw.text((30, _y), label, font=f_small, fill=GREY)
        draw.text((WIDTH - 30, _y), value,
                  font=f_small, fill=val_color,
                  anchor="ra")  # right-align
        row_y += row_h

    price_row("Entry Price",    _fmt(raw_entry,   precision))
    price_row("Current Price",  _fmt(raw_tp1,     precision), val_color=dir_color)
    price_row("TP 1",           _fmt(raw_tp1,     precision), val_color=GREEN)
    price_row("TP 2",           _fmt(raw_tp2,     precision), val_color=GREEN)
    price_row("TP 3",           _fmt(raw_tp3,     precision), val_color=GREEN)
    price_row("Stop Loss",      _fmt(raw_sl,      precision), val_color=RED)

    # Separator
    draw.line([30, row_y, WIDTH - 30, row_y], fill=BORDER_COLOR, width=1)
    row_y += 10

    # ------ Profit highlight ------
    profit_str = f"+${_fmt(profit_val, 2)}"
    draw.text((30, row_y), "Profit", font=f_med, fill=GREY)
    draw.text((WIDTH - 30, row_y), profit_str,
              font=f_large, fill=GREEN, anchor="ra")
    row_y += 35

    # ------ Account stats (mini row) ------
    stats = [
        ("Balance",      f"${_fmt(balance_val,      2)}"),
        ("Equity",       f"${_fmt(equity_val,        2)}"),
        ("Free Margin",  f"${_fmt(free_margin_val,   2)}"),
        ("Margin Lvl",   f"{_fmt(margin_level_val,   1)}%"),
    ]

    col_w = (WIDTH - 60) // 4
    for i, (lbl, val) in enumerate(stats):
        cx = 30 + i * col_w
        draw.text((cx, row_y),      lbl, font=f_tiny, fill=GREY)
        draw.text((cx, row_y + 14), val, font=f_tiny, fill=LIGHT_GREY)

    # ------ Bottom watermark ------
    draw.text((WIDTH // 2, HEIGHT - 20), "Mister Trade VIP",
              font=f_tiny, fill=(50, 60, 70), anchor="mm")

    # ------ Save ------
    output_path = os.path.join(OUTPUT_DIR, filename)
    img.save(output_path, "PNG")

    if not os.path.exists(output_path):
        raise FileNotFoundError(
            f"Pillow failed to save image at {output_path}."
        )

    return output_path
