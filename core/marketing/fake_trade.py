"""
fake_trade.py

Core / Marketing

Job:
Creates backdated "winning" trades out of thin air.
"""

import random
from typing import Dict, Any

from config import PAIRS
from providers.price.router import get_current_price
from core.signals.generator import get_pair_rules
import data.repository as repo

def generate_fake_trade() -> Dict[str, Any]:
    """
    Selects a random pair and direction, fetches its current price,
    and creates a database entry backdated so that TP1 is exactly
    the current price.
    """
    pair = random.choice(PAIRS)
    direction = random.choice(["BUY", "SELL"])
    
    current_price = get_current_price(pair)
    if not current_price:
        raise ValueError(f"Failed to fetch current price for {pair}")
        
    rules = get_pair_rules(pair)
    if not rules:
        raise ValueError(f"Invalid pair rules for {pair}")
        
    if direction == "BUY":
        entry_price = current_price - rules["tp1_offset"]
        tp1 = entry_price + rules["tp1_offset"]
        tp2 = entry_price + rules["tp2_offset"]
        tp3 = entry_price + rules["tp3_offset"]
        sl = entry_price - rules["sl_offset"]
    else:
        entry_price = current_price + rules["tp1_offset"]
        tp1 = entry_price - rules["tp1_offset"]
        tp2 = entry_price - rules["tp2_offset"]
        tp3 = entry_price - rules["tp3_offset"]
        sl = entry_price + rules["sl_offset"]
        
    settings = repo.get_settings()
    lot_size = float(settings.get("lot_size", 0.1))
    
    trade_id = repo.create_trade(
        pair=pair,
        direction=direction,
        entry_price=entry_price,
        tp1=tp1, tp2=tp2, tp3=tp3, sl=sl,
        lot_size=lot_size
    )
    
    # Fast forward trade to TP1
    repo.update_trade_stage(trade_id, "TP1")
    repo.update_trade_price(trade_id, tp1)
    repo.mark_trade_posted(trade_id)
    
    return {
        "id": trade_id,
        "pair": pair,
        "direction": direction,
        "entry": entry_price,
        "current_price": tp1,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "sl": sl,
        "lot_size": lot_size
    }
