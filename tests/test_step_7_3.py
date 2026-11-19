"""
tests/test_step_7_3.py

Unit test suite for Step 7.3: Mister_Trade Broadcast Router & Dynamic Recipient Injection.
Tests:
1. Vault link generation.
2. Channel lookup and policy evaluation with caching.
3. Dynamic injection of managed channels into _get_recipients().
4. Signal photo broadcast delivery via Vault and Mister_Channels gateway.
5. Text notification broadcast delivery.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

import config
from services.broadcast_router import (
    normalize_channel_id,
    _format_vault_message_link,
    is_managed_channel,
    deliver_signal_via_broadcast,
    deliver_text_via_broadcast,
    _managed_cache,
)
from bot.notification_handler import _get_recipients


async def test_vault_message_link_format():
    """Verify private vault links are correctly formatted without -100 prefix."""
    link = _format_vault_message_link("-1004355665952", 45)
    assert link == "https://t.me/c/4355665952/45"

    link2 = _format_vault_message_link(-1004355665952, 777)
    assert link2 == "https://t.me/c/4355665952/777"


async def test_is_managed_channel_cached():
    """Verify is_managed_channel matches active channels and checks signals_policy."""
    mock_channels = [
        {
            "target_channel": "-1004424471209",
            "campaign_name": "BitForge",
            "policies": {
                "signals_policy": {
                    "enabled": True,
                    "tone": "PROFESSIONAL",
                    "risk_value": 0.7
                }
            }
        },
        {
            "target_channel": "-1009999999999",
            "campaign_name": "Disabled Campaign",
            "policies": {
                "signals_policy": {
                    "enabled": False,
                    "tone": "HYPE"
                }
            }
        }
    ]

    _managed_cache["timestamp"] = 9999999999.0
    _managed_cache["data"] = mock_channels

    # Test managed and enabled
    is_managed, data = await is_managed_channel("-1004424471209")
    assert is_managed is True
    assert data["campaign_name"] == "BitForge"

    # Test managed but policy disabled
    is_managed_dis, _ = await is_managed_channel("-1009999999999")
    assert is_managed_dis is False

    # Test unmanaged channel (e.g. Ansem)
    is_managed_un, _ = await is_managed_channel("-1004437901038")
    assert is_managed_un is False


async def test_dynamic_recipient_injection():
    """Verify managed channels from Mister_Channels are dynamically injected into _get_recipients."""
    mock_db_copiers = [
        {
            "channel_id": "-1004437901038",
            "name": "Ansem",
            "tone": "HYPE",
            "risk_type": "USD_RISK",
            "risk_value": 2000.0,
            "max_trades_per_day": 3,
            "admin_name": "Admin",
        }
    ]

    mock_managed_channels = [
        {
            "target_channel": "-1004424471209",
            "campaign_name": "BitForge",
            "primary_handle": "@mybitforgeadmin",
            "policies": {
                "signals_policy": {
                    "enabled": True,
                    "tone": "PROFESSIONAL",
                    "risk_type": "LOT_SIZE",
                    "risk_value": 0.70,
                    "max_trades_per_day": 5
                }
            }
        }
    ]

    with patch("data.repository.get_all_active_copier_channels", return_value=mock_db_copiers), \
         patch("services.broadcast_router.get_managed_channels_cached", new_callable=AsyncMock, return_value=mock_managed_channels):

        recipients = await _get_recipients()

        # Both Ansem (DB copier) and BitForge (managed channel) must be present
        channel_ids = [r["channel_id"] for r in recipients]
        assert "-1004437901038" in channel_ids
        assert "-1004424471209" in channel_ids

        # Verify BitForge policy settings mapped correctly
        bitforge = next(r for r in recipients if r["channel_id"] == "-1004424471209")
        assert bitforge["name"] == "BitForge"
        assert bitforge["tone"] == "PROFESSIONAL"
        assert bitforge["risk_value"] == 0.70
        assert bitforge["max_trades_per_day"] == 5
        assert bitforge.get("is_managed") is True


async def test_deliver_signal_via_broadcast():
    """Verify signal delivery uploads to vault then calls Mister_Channels broadcast endpoint."""
    bot = MagicMock()
    mock_sent_msg = MagicMock()
    mock_sent_msg.message_id = 88
    bot.send_photo = AsyncMock(return_value=mock_sent_msg)

    with patch("services.broadcast_router._post_broadcast_sync", return_value=True) as mock_post:
        photo = MagicMock()
        success = await deliver_signal_via_broadcast(
            bot=bot,
            target_channel="-1004424471209",
            photo=photo,
            caption="*BTC/USD TP1 Hit!*"
        )

        assert success is True
        # Verify photo sent to vault
        bot.send_photo.assert_called_once()
        assert bot.send_photo.call_args.kwargs["chat_id"] == config.VAULT_CHANNEL_ID

        # Verify broadcast post called with parsed link
        mock_post.assert_called_once()
        target_id, kwargs = mock_post.call_args[0][0], mock_post.call_args[1]
        assert target_id == -1004424471209
        assert "4355665952/88" in kwargs["message_link"]


async def test_deliver_text_via_broadcast():
    """Verify text delivery calls broadcast endpoint with text payload."""
    with patch("services.broadcast_router._post_broadcast_sync", return_value=True) as mock_post:
        success = await deliver_text_via_broadcast(
            target_channel="-1004424471209",
            text="Stop loss hit on EURUSD."
        )

        assert success is True
        mock_post.assert_called_once()
        target_id, kwargs = mock_post.call_args[0][0], mock_post.call_args[1]
        assert target_id == -1004424471209
        assert kwargs["text"] == "Stop loss hit on EURUSD."


async def run_all_tests():
    print("=" * 60)
    print("RUNNING STEP 7.3 MISTER_TRADE BROADCAST WIRING TESTS")
    print("=" * 60)

    print("[TEST 1] Testing Vault Message Link Format...")
    await test_vault_message_link_format()
    print("  -> PASS: Vault links format cleanly.")

    print("[TEST 2] Testing Managed Channel Resolution & Cache...")
    await test_is_managed_channel_cached()
    print("  -> PASS: Managed channels resolved and non-managed channels bypassed.")

    print("[TEST 3] Testing Dynamic Recipient Injection...")
    await test_dynamic_recipient_injection()
    print("  -> PASS: Managed channels dynamically injected into copier recipient list.")

    print("[TEST 4] Testing Signal Photo Delivery via Vault & Broadcast...")
    await test_deliver_signal_via_broadcast()
    print("  -> PASS: Signal photo staged in vault and broadcast invoked.")

    print("[TEST 5] Testing Text Notification Delivery via Broadcast...")
    await test_deliver_text_via_broadcast()
    print("  -> PASS: Text notification broadcast invoked.")

    print("=" * 60)
    print("ALL STEP 7.3 UNIT TESTS PASSED (5/5)! 100% GREEN.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_all_tests())
