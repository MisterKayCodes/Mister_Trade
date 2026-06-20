"""
setup.py

Mouth & Ears / Bot Setup

Job:
Create the Bot and Dispatcher instances and register
all command/callback handlers.

Rules:
    - aiogram v2 style
    - No business logic here
    - Handlers registered via register_handlers() pattern
"""

from aiogram import Bot, Dispatcher
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from config import BOT_TOKEN

# ------------------------------------------------------------------
# Bot instance
# Dummy token guard: if no real token is set, import still succeeds
# so the engine can run in token-free mode.
# ------------------------------------------------------------------
_token = BOT_TOKEN if (BOT_TOKEN and "your_bot_token" not in BOT_TOKEN) else "0:AAFakeTokenForImportOnly"
bot = Bot(token=_token)

# aiogram v2: Dispatcher is bound to the bot at creation time.
# MemoryStorage is required for FSM (multi-step admin inputs).
dp = Dispatcher(bot=bot, storage=MemoryStorage())

# ------------------------------------------------------------------
# Register all routers (v2 uses register_handlers functions,
# not include_router like v3)
# ------------------------------------------------------------------
from bot.routers.admin import register_handlers as register_admin
register_admin(dp)
