"""
news.py

Services / News

Job:
Fetch today's high-impact economic events from the ForexFactory
RSS feed and format them into a clean Telegram message.

Rules:
    - Returns empty string on failure — never raises
    - Only surfaces HIGH IMPACT events (red folder)
    - No Telegram I/O (that lives in bot/)
    - No database access
"""

import logging
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

RSS_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
TIMEOUT = 10

# Only post these impact levels
HIGH_IMPACT_LABEL = "High"

IMPACT_EMOJI = {
    "High":   "🔴",
    "Medium": "🟡",
    "Low":    "⚪",
}


def _fetch_events() -> list:
    """Fetch the current week's ForexFactory JSON calendar."""
    try:
        response = requests.get(RSS_URL, timeout=TIMEOUT, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        logger.error(f"[news] Failed to fetch ForexFactory feed: {exc}")
        return []


def get_daily_news_message() -> Optional[str]:
    """
    Build and return a formatted Telegram message with today's high-impact events.
    Returns None if there are no relevant events or the fetch fails.
    """
    from config import TEST_MODE
    
    if TEST_MODE:
        display_date = "TEST MODE (MOCK DATA)"
        todays_events = [
            {"time": "12:00", "currency": "USD", "title": "Fed Chair Powell Speaks (MOCK)", "impact": "High"},
            {"time": "14:30", "currency": "EUR", "title": "ECB Press Conference (MOCK)", "impact": "High"}
        ]
    else:
        events = _fetch_events()
        if not events:
            return None

        today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        display_date = datetime.now(timezone.utc).strftime('%B %d, %Y')

        todays_events = []
        for event in events:
            try:
                event_date = datetime.strptime(event.get("date", ""), "%m-%d-%Y").strftime("%Y-%m-%d")
                if event_date != today_utc:
                    continue
                if event.get("impact") != HIGH_IMPACT_LABEL:
                    continue

                todays_events.append({
                    "time":     event.get("time", "All Day"),
                    "currency": event.get("country", ""),
                    "title":    event.get("title", "Unknown Event"),
                    "impact":   event.get("impact", ""),
                })
            except Exception:
                continue

    if not todays_events:
        return None

    lines = [
        f"☀️ *DAILY MARKET UPDATE — {display_date}*\n",
        f"🔴 *High Impact Events Today:*\n",
    ]

    for ev in todays_events:
        emoji = IMPACT_EMOJI.get(ev["impact"], "⚪")
        lines.append(f"{emoji} `{ev['time']} UTC` — *{ev['currency']}* | {ev['title']}")

    lines.append(
        "\n💡 _Trade carefully around these times. "
        "We will be monitoring the market closely for VIP opportunities!_ 🎯"
    )

    return "\n".join(lines)
