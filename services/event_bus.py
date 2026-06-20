"""
event_bus.py

Nervous System / Event Bus

Job:
Safely pass messages from the synchronous trading engine
to the asynchronous Telegram bot.

Rules:
    - Pure queue operations
    - No Telegram imports
    - No core logic
"""

import queue
from typing import Any

# Thread-safe queue
_bus: queue.Queue = queue.Queue()

def publish(event_type: str, payload: dict[str, Any]) -> None:
    """Publish an event to the bus."""
    _bus.put({"type": event_type, "payload": payload})

def consume_all() -> list[dict[str, Any]]:
    """Retrieve all pending events from the bus without blocking."""
    events = []
    while not _bus.empty():
        try:
            events.append(_bus.get_nowait())
        except queue.Empty:
            break
    return events
