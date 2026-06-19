from core.trades.tracker import evaluate_trade

def test_evaluate_trade_tp1_hit():
    trade = {
        "direction": "BUY",
        "stage": "OPEN",
        "entry_price": 100000,
        "tp1": 100300,
        "tp2": 100500,
        "tp3": 100700,
        "sl": 99850
    }
    result = evaluate_trade(trade, 100350, {})
    assert result["action"] == "UPDATE_STAGE"
    assert result["stage"] == "TP1"

def test_evaluate_trade_sl_hit():
    trade = {
        "direction": "BUY",
        "stage": "OPEN",
        "entry_price": 100000,
        "tp1": 100300,
        "tp2": 100500,
        "tp3": 100700,
        "sl": 99850
    }
    result = evaluate_trade(trade, 99800, {})
    assert result["action"] == "CLOSE"
    assert result["stage"] == "SL"

def test_forced_loss():
    trade = {
        "direction": "BUY",
        "stage": "OPEN",
        "entry_price": 100000,
        "tp1": 100300,
        "tp2": 100500,
        "tp3": 100700,
        "sl": 99850
    }
    settings = {"win_streak": 10} # Needs forced loss
    
    # If in profit, it holds until SL or natural movement
    result1 = evaluate_trade(trade, 100100, settings)
    assert result1["action"] == "HOLD"
    
    # If in loss, it forces a close to lock in the loss cleanly
    result2 = evaluate_trade(trade, 99900, settings)
    assert result2["action"] == "CLOSE"
    assert result2["stage"] == "FORCED_LOSS"

def test_time_limit():
    trade = {
        "direction": "BUY",
        "stage": "OPEN",
        "entry_price": 100000,
        "tp1": 100300,
        "tp2": 100500,
        "tp3": 100700,
        "sl": 99850,
        "created_at": "2020-01-01 12:00:00" # Very old date
    }
    result = evaluate_trade(trade, 100100, {})
    assert result["action"] == "CLOSE"
    assert result["stage"] == "TIME_LIMIT"
