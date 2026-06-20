"""
engine.py

Brain / Flip Campaign Engine

Job:
    Provides the core math and logic for Account Flip campaigns.

Rules:
    - Pure math and logic, no database/network IO.
"""

import random

# Fixed risk percentage per flip trade
RISK_PERCENT = 0.20  # 20% risk per trade for aggressive compounding

def compute_flip_lot(balance: float, pair: str, sl_offset: float) -> float:
    """
    Compute the lot size based on a fixed risk percentage of the current balance.
    
    Formula:
        Risk Amount = Balance * RISK_PERCENT
        
        For Forex: 1 standard lot (100,000 units) = $10 per pip.
        So value_per_lot_per_pip = $10
        Lot Size = Risk Amount / (SL Pips * $10)
        
        For Crypto (assuming 1 lot = 1 coin):
        value_per_lot_per_dollar = $1
        Lot Size = Risk Amount / (SL Dollars * $1)
    """
    risk_amount = balance * RISK_PERCENT
    
    is_forex = pair.upper() in ("EURUSD", "GBPUSD")
    
    if is_forex:
        # sl_offset is in price units (e.g. 0.0015)
        # Convert to pips (1 pip = 0.0001)
        sl_pips = sl_offset / 0.0001
        value_per_lot_per_pip = 10.0
        
        lot = risk_amount / (sl_pips * value_per_lot_per_pip)
    else:
        # sl_offset is in dollars (e.g. 150)
        value_per_lot_per_dollar = 1.0
        lot = risk_amount / (sl_offset * value_per_lot_per_dollar)
        
    # Minimum lot size in most brokers is 0.01
    return max(0.01, round(lot, 2))


def should_end_campaign(current_balance: float, target_balance: float) -> bool:
    """
    Determine if the campaign should end.
    To look organic, we don't end exactly at the target.
    We end if we are loosely past the target (e.g., within 95% to 115% of target).
    For simplicity, if balance >= target * 0.95, we consider it a potential end point.
    To make it organic, we can randomly decide to end if we are above the target,
    or just strictly end if balance >= target.
    Let's just use strict >= target for simplicity, or balance >= target * 0.95.
    """
    # Just check if we've passed the target threshold (e.g. 95% of target)
    return current_balance >= (target_balance * 0.95)
