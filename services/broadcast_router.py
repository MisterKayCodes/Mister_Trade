"""
services/broadcast_router.py

Sibling Broadcast Router & Dynamic Managed Channel Registry for Mister_Trade.

Responsibilities:
1. Query and cache active managed channel policies from Mister_Channels (GET /api/v1/managed-channels).
2. Dynamically provide managed channels with their custom tone, risk settings, and trading quotas.
3. Route signal screenshots through the private internal Vault channel (-1004355665952) and invoke
   Mister_Channels broadcast gateway (POST /api/v1/broadcast) so client channels only need
   Mister_Channels bot installed as an administrator.
"""

import time
import requests
import asyncio
import logging
from typing import Optional, Union, Tuple, Dict, Any, List
from aiogram import Bot
from aiogram.types import InputFile, ParseMode

import config

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────
# In-Memory Cache for Managed Channels Registry (60s TTL)
# ─────────────────────────────────────────────────────────────────
_managed_cache: Dict[str, Any] = {"timestamp": 0.0, "data": []}
CACHE_TTL_SECONDS = 60.0


def normalize_channel_id(channel_id: Union[str, int]) -> str:
    """Standardize channel identifier for robust comparison."""
    return str(channel_id).strip()


def _fetch_managed_channels_sync() -> List[Dict[str, Any]]:
    """Synchronous HTTP call to Mister_Channels managed-channels registry."""
    url = f"{config.MISTER_CHANNELS_URL.rstrip('/')}/api/v1/managed-channels"
    headers = {"X-API-Key": config.MISTER_CHANNELS_BROADCAST_KEY}
    try:
        resp = requests.get(url, headers=headers, timeout=8.0)
        if resp.status_code == 200:
            payload = resp.json()
            return payload.get("channels", [])
        else:
            logger.warning(
                f"[broadcast_router] Failed to fetch managed channels: HTTP {resp.status_code} - {resp.text}"
            )
    except Exception as e:
        logger.warning(f"[broadcast_router] Could not reach Mister_Channels at {url}: {e}")
    return []


async def get_managed_channels_cached(force_refresh: bool = False) -> List[Dict[str, Any]]:
    """
    Fetch active managed channels from Mister_Channels with a 60-second in-memory cache.
    Runs HTTP fetch inside asyncio.to_thread to maintain async loop responsiveness.
    """
    global _managed_cache
    now = time.time()

    if not force_refresh and (now - _managed_cache["timestamp"] < CACHE_TTL_SECONDS):
        return _managed_cache["data"]

    channels = await asyncio.to_thread(_fetch_managed_channels_sync)
    if channels:
        _managed_cache = {"timestamp": now, "data": channels}
        return channels

    return _managed_cache.get("data", [])


async def is_managed_channel(channel_id: Union[str, int]) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Check if a target channel is managed by Mister_Channels and has signals_policy enabled.
    Returns (True, channel_info) or (False, None).
    """
    clean_id = normalize_channel_id(channel_id)
    channels = await get_managed_channels_cached()

    for ch in channels:
        managed_target = normalize_channel_id(ch.get("target_channel", ""))
        if clean_id == managed_target:
            signals_pol = ch.get("policies", {}).get("signals_policy", {})
            if signals_pol.get("enabled", False):
                return True, ch
            else:
                return False, ch

    return False, None


def _format_vault_message_link(vault_channel_id: Union[str, int], message_id: int) -> str:
    """
    Formats the private Telegram link expected by Mister_Channels' broadcast parser:
    e.g. -1004355665952 -> 4355665952 -> https://t.me/c/4355665952/{message_id}
    """
    raw = str(vault_channel_id).strip()
    if raw.startswith("-100"):
        clean_channel_id = raw[4:]
    elif raw.startswith("-"):
        clean_channel_id = raw[1:]
    else:
        clean_channel_id = raw

    return f"https://t.me/c/{clean_channel_id}/{message_id}"


def _post_broadcast_sync(target_chat_id: int, message_link: Optional[str] = None, text: Optional[str] = None) -> bool:
    """Synchronous POST to Mister_Channels broadcast gateway."""
    broadcast_url = f"{config.MISTER_CHANNELS_URL.rstrip('/')}/api/v1/broadcast"
    headers = {
        "X-API-Key": config.MISTER_CHANNELS_BROADCAST_KEY,
        "Content-Type": "application/json",
    }
    payload: Dict[str, Any] = {"chat_id": target_chat_id}
    if message_link:
        payload["message_link"] = message_link
    if text:
        payload["text"] = text

    try:
        resp = requests.post(broadcast_url, headers=headers, json=payload, timeout=20.0)
        if resp.status_code == 200:
            logger.info(f"[broadcast_router] Broadcast SUCCESS to {target_chat_id}")
            return True
        else:
            logger.error(
                f"[broadcast_router] Broadcast gateway returned HTTP {resp.status_code}: {resp.text}"
            )
            return False
    except Exception as e:
        logger.error(f"[broadcast_router] Error calling broadcast gateway at {broadcast_url}: {e}")
        return False


async def deliver_signal_via_broadcast(
    bot: Bot,
    target_channel: Union[str, int],
    photo: InputFile,
    caption: str,
) -> bool:
    """
    Stages the rendered signal photo in the private Vault channel (-1004355665952)
    and routes delivery to the client's channel via Mister_Channels broadcast gateway.
    """
    vault_id = config.VAULT_CHANNEL_ID
    logger.info(f"[broadcast_router] Uploading signal photo to vault {vault_id} for target {target_channel}...")

    try:
        sent_msg = await bot.send_photo(
            chat_id=vault_id,
            photo=photo,
            caption=caption,
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as e:
        logger.error(f"[broadcast_router] Failed uploading signal photo to vault {vault_id}: {e}")
        return False

    if not sent_msg or not hasattr(sent_msg, "message_id"):
        logger.error("[broadcast_router] Vault upload did not return message_id.")
        return False

    vault_link = _format_vault_message_link(vault_id, sent_msg.message_id)
    logger.info(f"[broadcast_router] Signal staged in vault. Link: {vault_link}")

    try:
        numeric_target = int(str(target_channel).strip())
    except ValueError:
        logger.error(f"[broadcast_router] Target channel {target_channel} must be numeric.")
        return False

    return await asyncio.to_thread(_post_broadcast_sync, numeric_target, message_link=vault_link)


async def deliver_text_via_broadcast(
    target_channel: Union[str, int],
    text: str,
) -> bool:
    """Routes a plain text trading notification (e.g. SL hit) through the broadcast gateway."""
    try:
        numeric_target = int(str(target_channel).strip())
    except ValueError:
        logger.error(f"[broadcast_router] Target channel {target_channel} must be numeric.")
        return False

    return await asyncio.to_thread(_post_broadcast_sync, numeric_target, text=text)
