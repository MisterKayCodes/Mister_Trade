from core.movement.detector import calculate_movement, has_moved, get_direction

def test_calculate_movement():
    assert calculate_movement(100_000, 100_300) == 300
    assert calculate_movement(100_000, 99_700) == -300

def test_has_moved():
    assert has_moved(100_000, 100_300, 300) is True
    assert has_moved(100_000, 100_299, 300) is False
    assert has_moved(100_000, 99_700, 300) is True
    assert has_moved(100_000, 99_701, 300) is False

def test_get_direction():
    assert get_direction(100_000, 100_300) == "BUY"
    assert get_direction(100_000, 99_700) == "SELL"
