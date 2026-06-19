from core.signals.generator import create_signal

def test_create_signal_buy():
    # BTC threshold is 300
    signal = create_signal("BTCUSD", 100_000, 100_350)
    assert signal is not None
    assert signal["pair"] == "BTCUSD"
    assert signal["direction"] == "BUY"
    assert signal["entry"] == 100_000
    assert signal["tp1"] == 100_300
    assert signal["sl"] == 99_850

def test_create_signal_sell():
    signal = create_signal("BTCUSD", 100_000, 99_650)
    assert signal is not None
    assert signal["direction"] == "SELL"
    assert signal["entry"] == 100_000
    assert signal["tp1"] == 99_700
    assert signal["sl"] == 100_150

def test_create_signal_below_threshold():
    signal = create_signal("BTCUSD", 100_000, 100_200)
    assert signal is None
