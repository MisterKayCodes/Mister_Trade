"""
test_notifications.py

Tests for notification_handler.py.

Uses AsyncMock to simulate the Telegram Bot object so we can
verify message formatting without making real API calls.
"""

import pytest
from unittest.mock import AsyncMock, patch, mock_open
from bot.notification_handler import send_signal, send_close


# ==============================================================
# Signal post tests
# ==============================================================

@pytest.mark.asyncio
async def test_send_signal_buy_formatting():
    """BUY signal uses green emoji and correct price formatting."""
    bot_mock = AsyncMock()
    payload = {
        "pair":      "BTCUSD",
        "direction": "BUY",
        "entry":     60000.0,
        "tp1":       60300.0,
        "tp2":       60500.0,
        "tp3":       60700.0,
        "sl":        59850.0,
        "lot_size":  0.5,
    }

    with patch("bot.notification_handler.CHANNEL_ID", "@test_channel"):
        with patch("bot.notification_handler.render_signal_image", return_value="dummy.png"):
            with patch("os.path.exists", return_value=True):
                with patch("os.remove"):
                    with patch("builtins.open", mock_open(read_data=b"data")):
                        await send_signal(bot_mock, payload)

    bot_mock.send_photo.assert_called_once()
    caption = bot_mock.send_photo.call_args[1]["caption"]

    assert "🟢" in caption
    assert "BUY" in caption
    assert "0.5" in caption


@pytest.mark.asyncio
async def test_send_signal_sell_formatting():
    """SELL signal uses red emoji."""
    bot_mock = AsyncMock()
    payload = {
        "pair":      "ETHUSD",
        "direction": "SELL",
        "entry":     2000.0,
        "tp1":       1980.0,
        "tp2":       1965.0,
        "tp3":       1950.0,
        "sl":        2010.0,
        "lot_size":  0.1,
    }

    with patch("bot.notification_handler.CHANNEL_ID", "@test_channel"):
        with patch("bot.notification_handler.render_signal_image", return_value="dummy.png"):
            with patch("os.path.exists", return_value=True):
                with patch("os.remove"):
                    with patch("builtins.open", mock_open(read_data=b"data")):
                        await send_signal(bot_mock, payload)

    caption = bot_mock.send_photo.call_args[1]["caption"]
    assert "🔴" in caption
    assert "SELL" in caption


@pytest.mark.asyncio
async def test_send_signal_no_channel_skips_send():
    """If CHANNEL_ID is empty, bot.send_message is never called."""
    bot_mock = AsyncMock()
    payload = {
        "pair": "BTCUSD", "direction": "BUY",
        "entry": 60000.0, "tp1": 60300.0, "tp2": 60500.0,
        "tp3": 60700.0, "sl": 59850.0, "lot_size": 0.1,
    }

    with patch("bot.notification_handler.CHANNEL_ID", ""):
        with patch("bot.notification_handler.render_signal_image", return_value="dummy.png"):
            await send_signal(bot_mock, payload)

    bot_mock.send_photo.assert_not_called()


# ==============================================================
# Trade close tests
# ==============================================================

@pytest.mark.asyncio
async def test_send_close_sl_loss():
    """Stop Loss close uses red cross emoji."""
    bot_mock = AsyncMock()
    payload = {
        "pair":        "ETHUSD",
        "direction":   "SELL",
        "entry":       2000.0,
        "close_price": 2050.0,
        "close_stage": "SL",
        "lot_size":    0.1,
    }

    with patch("bot.notification_handler.CHANNEL_ID", "@test_channel"):
        await send_close(bot_mock, payload)

    text = bot_mock.send_message.call_args[1]["text"]
    assert "❌" in text
    assert "Stop Loss Hit" in text
    assert "2,050.00" in text


@pytest.mark.asyncio
async def test_send_close_tp2_win():
    """TP2 close uses money bag emoji."""
    bot_mock = AsyncMock()
    payload = {
        "pair":        "BTCUSD",
        "direction":   "BUY",
        "entry":       60000.0,
        "close_price": 60500.0,
        "close_stage": "TP2",
        "lot_size":    0.1,
    }

    with patch("bot.notification_handler.CHANNEL_ID", "@test_channel"):
        await send_close(bot_mock, payload)

    text = bot_mock.send_message.call_args[1]["text"]
    assert "💰" in text
    assert "TP2" in text


@pytest.mark.asyncio
async def test_send_close_time_limit():
    """TIME_LIMIT close uses clock emoji."""
    bot_mock = AsyncMock()
    payload = {
        "pair":        "BTCUSD",
        "direction":   "BUY",
        "entry":       60000.0,
        "close_price": 60050.0,
        "close_stage": "TIME_LIMIT",
        "lot_size":    0.1,
    }

    with patch("bot.notification_handler.CHANNEL_ID", "@test_channel"):
        await send_close(bot_mock, payload)

    text = bot_mock.send_message.call_args[1]["text"]
    assert "⏰" in text
