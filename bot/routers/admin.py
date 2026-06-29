"""
admin.py

Mouth & Ears / Routers / Admin

Job:
Handle all admin commands and callback queries.
Gate every handler behind ADMIN_IDS — unauthorized users
are silently ignored.

Rules:
    - aiogram v2 style (register_handlers pattern, no Router)
    - No price math or trading logic here
    - All DB reads go through data/repository.py
    - No direct SQL here
"""

from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from config import ADMIN_IDS
from bot.keyboards.admin_kb import (
    main_menu_kb, force_pair_kb, force_dir_kb,
    settings_kb, testimonials_kb, flip_kb,
    copier_channels_kb, copier_channel_detail_kb
)
import data.repository as repo
from providers.price.router import get_current_price
from core.signals.generator import get_pair_rules


# ==============================================================
# Guards
# ==============================================================

def _is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# ==============================================================
# FSM States (for multi-step admin inputs)
# ==============================================================

class AdminStates(StatesGroup):
    waiting_for_json_names     = State()
    waiting_for_json_convos    = State()
    waiting_for_json_promos    = State()
    waiting_for_admin_name     = State()
    waiting_for_admin_contact  = State()
    waiting_for_flip_start     = State()
    waiting_for_flip_target    = State()
    # Copier Channel add flow
    copier_waiting_channel_id  = State()
    copier_waiting_name        = State()
    copier_waiting_tone        = State()
    copier_waiting_risk_type   = State()
    copier_waiting_risk_value  = State()
    copier_waiting_max_trades  = State()
    copier_waiting_admin_name  = State()


# ==============================================================
# Message Handlers
# ==============================================================

async def cmd_admin(message: types.Message):
    """
    /admin — opens the admin panel.
    Silently ignored if sender is not in ADMIN_IDS.
    """
    if not _is_admin(message.from_user.id):
        return

    await message.answer(
        "👋 *Mister Trade Admin Panel*\n\nSelect an option below:",
        reply_markup=main_menu_kb(),
        parse_mode=types.ParseMode.MARKDOWN,
    )


# ==============================================================
# Callback Handlers
# ==============================================================

async def cb_main_menu(callback: types.CallbackQuery):
    """Return to main menu."""
    if not _is_admin(callback.from_user.id):
        return

    await callback.message.edit_text(
        "👋 *Mister Trade Admin Panel*\n\nSelect an option below:",
        reply_markup=main_menu_kb(),
        parse_mode=types.ParseMode.MARKDOWN,
    )
    await callback.answer()

async def cb_schedule(callback: types.CallbackQuery):
    if not _is_admin(callback.from_user.id): return
    from services.scheduler import get_schedule_text
    
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    back_kb = InlineKeyboardMarkup().add(InlineKeyboardButton(text="← Back to Admin", callback_data="admin_main"))

    await callback.message.edit_text(
        get_schedule_text(),
        reply_markup=back_kb,
        parse_mode=types.ParseMode.MARKDOWN,
    )
    await callback.answer()


async def cb_toggle_trading(callback: types.CallbackQuery):
    """Toggle trading on or off and reflect the change immediately."""
    if not _is_admin(callback.from_user.id):
        return

    settings    = repo.get_settings()
    current     = int(settings.get("trading_enabled", 1))
    new_status  = 0 if current else 1

    repo.update_setting("trading_enabled", new_status)

    status_str = "ENABLED ✅" if new_status else "DISABLED ❌"

    await callback.message.edit_text(
        f"Trading is now *{status_str}*.\n\nSelect an option below:",
        reply_markup=main_menu_kb(),
        parse_mode=types.ParseMode.MARKDOWN,
    )
    await callback.answer(f"Trading {status_str}")


async def cb_stats(callback: types.CallbackQuery):
    """Show basic performance stats."""
    if not _is_admin(callback.from_user.id):
        return

    settings = repo.get_settings()
    history  = repo.get_trade_history(limit=100)

    wins   = sum(1 for t in history if t.get("close_stage") not in ("SL", "FORCED_LOSS", None) and t["status"] == "CLOSED")
    losses = sum(1 for t in history if t.get("close_stage") in ("SL", "FORCED_LOSS") and t["status"] == "CLOSED")
    total  = wins + losses
    rate   = f"{(wins / total * 100):.1f}%" if total else "N/A"

    text = (
        f"📊 *Performance Stats*\n\n"
        f"Total Closed Trades: {total}\n"
        f"✅ Wins: {wins}\n"
        f"❌ Losses: {losses}\n"
        f"🎯 Win Rate: {rate}\n\n"
        f"🔥 Current Win Streak: {settings.get('win_streak', 0)}\n"
        f"💰 Starting Balance: ${settings.get('starting_balance', 0):,.2f}\n"
        f"📈 Current Balance: ${settings.get('current_balance', 0):,.2f}"
    )

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    back_kb = InlineKeyboardMarkup()
    back_kb.add(InlineKeyboardButton(text="← Back", callback_data="admin_main"))

    await callback.message.edit_text(
        text,
        reply_markup=back_kb,
        parse_mode=types.ParseMode.MARKDOWN,
    )
    await callback.answer()


async def cb_clear(callback: types.CallbackQuery):
    if not _is_admin(callback.from_user.id): return
    count = repo.clear_active_trades()
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    back_kb = InlineKeyboardMarkup().add(InlineKeyboardButton(text="← Back to Admin", callback_data="admin_main"))

    await callback.message.edit_text(
        f"🗑️ *Clear Active Trades*\n\n✅ Successfully deleted `{count}` active trades from the database.",
        reply_markup=back_kb,
        parse_mode=types.ParseMode.MARKDOWN,
    )
    await callback.answer(f"Cleared {count} trades")


# ==============================================================
# Settings Handlers
# ==============================================================

async def cb_settings(callback: types.CallbackQuery):
    if not _is_admin(callback.from_user.id): return

    settings = repo.get_settings()
    current_lot  = float(settings.get("lot_size", 0.1))
    admin_name   = settings.get("admin_name", "Mike")
    admin_contact = settings.get("admin_contact", "@MisterTrade")
    market_mode  = settings.get("market_mode", "FOREX")

    await callback.message.edit_text(
        f"⚙️ *Settings*\n\n"
        f"Admin Name: `{admin_name}`\n"
        f"Admin Contact: `{admin_contact}`\n\n"
        f"Select a default Lot Size:",
        reply_markup=settings_kb(current_lot, market_mode),
        parse_mode=types.ParseMode.MARKDOWN,
    )
    await callback.answer()


async def cb_set_lot(callback: types.CallbackQuery):
    if not _is_admin(callback.from_user.id): return
    new_lot = float(callback.data.split("_")[2])
    repo.update_setting("lot_size", new_lot)
    settings = repo.get_settings()
    admin_name = settings.get("admin_name", "Mike")
    market_mode = settings.get("market_mode", "FOREX")
    await callback.message.edit_text(
        f"⚙️ *Settings*\n\n"
        f"Admin Name: `{admin_name}`\n\n"
        f"✅ Lot size updated to `{new_lot}`.\nSelect a new default Lot Size:",
        reply_markup=settings_kb(new_lot, market_mode),
        parse_mode=types.ParseMode.MARKDOWN,
    )
    await callback.answer("Lot size updated!")


async def cb_toggle_market_mode(callback: types.CallbackQuery):
    if not _is_admin(callback.from_user.id): return
    
    settings = repo.get_settings()
    current_mode = settings.get("market_mode", "FOREX")
    new_mode = "CRYPTO" if current_mode == "FOREX" else "FOREX"
    
    repo.update_setting("market_mode", new_mode)
    
    # Reload scheduler
    from services.scheduler import start_scheduler
    from bot.setup import bot
    start_scheduler(bot)
    
    current_lot = float(settings.get("lot_size", 0.1))
    await callback.message.edit_text(
        f"⚙️ *Settings*\n\n"
        f"✅ Market Mode changed to `{new_mode}`.\n"
        f"The scheduler has been successfully reloaded for this mode.",
        reply_markup=settings_kb(current_lot, new_mode),
        parse_mode=types.ParseMode.MARKDOWN,
    )
    await callback.answer(f"Switched to {new_mode}")


# ==============================================================
# Force Signal Handlers
# ==============================================================

async def cb_force_main(callback: types.CallbackQuery):
    if not _is_admin(callback.from_user.id): return
    await callback.message.edit_text(
        "📈 *Force Signal*\n\nWhich pair do you want to force?",
        reply_markup=force_pair_kb(),
        parse_mode=types.ParseMode.MARKDOWN,
    )
    await callback.answer()


async def cb_force_pair(callback: types.CallbackQuery):
    if not _is_admin(callback.from_user.id): return
    # data is "force_pair_BTCUSD"
    pair = callback.data.split("_")[2]
    await callback.message.edit_text(
        f"📈 *Force Signal: {pair}*\n\nWhich direction?",
        reply_markup=force_dir_kb(pair),
        parse_mode=types.ParseMode.MARKDOWN,
    )
    await callback.answer()


async def cb_force_dir(callback: types.CallbackQuery):
    if not _is_admin(callback.from_user.id): return
    # data is "force_dir_BTCUSD_BUY"
    parts = callback.data.split("_")
    pair = parts[2]
    direction = parts[3]
    
    # Validate active trade doesn't exist
    if repo.get_active_trade(pair):
        await callback.answer("⚠️ Active trade already exists for this pair!", show_alert=True)
        return
        
    price = get_current_price(pair)
    if not price:
        await callback.answer("❌ Failed to fetch current price.", show_alert=True)
        return
        
    rules = get_pair_rules(pair)
    if not rules:
        await callback.answer("❌ Invalid pair rules.", show_alert=True)
        return
        
    # To make the forced signal post to Telegram immediately for UI testing,
    # we artificially set the entry price so that TP1 is exactly the current price.
    from core.marketing.fake_trade import generate_fake_trade
    try:
        trade = generate_fake_trade(forced_pair=pair, forced_direction=direction)
    except Exception as e:
        await callback.answer(f"❌ Error: {e}", show_alert=True)
        return

    import services.event_bus as event_bus
    event_bus.publish("SIGNAL_POST", trade)
    
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    back_kb = InlineKeyboardMarkup().add(InlineKeyboardButton(text="← Back to Admin", callback_data="admin_main"))

    await callback.message.edit_text(
        f"✅ *Forced {trade['direction']} signal for {trade['pair']}!*\n\n"
        f"Fake Entry: `${trade['entry']:,.2f}`\n"
        f"Current Price (TP1): `${trade['tp1']:,.2f}`\n"
        f"SL: `${trade['sl']:,.2f}`\n\n"
        f"The screenshot has been instantly generated and posted to the channel!",
        reply_markup=back_kb,
        parse_mode=types.ParseMode.MARKDOWN,
    )
    await callback.answer("Signal forced!")


# ==============================================================
# Content Manager Handlers
# ==============================================================

async def cb_content_menu(callback: types.CallbackQuery):
    if not _is_admin(callback.from_user.id): return
    from bot.keyboards.admin_kb import content_manager_kb
    await callback.message.edit_text(
        "🗃️ *Content Manager*\n\nSelect which JSON database to update:",
        reply_markup=content_manager_kb(),
        parse_mode=types.ParseMode.MARKDOWN,
    )
    await callback.answer()

async def cb_content_update(callback: types.CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id): return
    target = callback.data.split("_")[2] # names, convos, promos
    
    if target == "names":
        await AdminStates.waiting_for_json_names.set()
        example = '[\n  "John",\n  "Emma"\n]'
    elif target == "convos":
        await AdminStates.waiting_for_json_convos.set()
        example = '[\n  "THEM: Hello | ME: Hi",\n  "THEM: Thanks | ME: Welcome"\n]'
    else:
        await AdminStates.waiting_for_json_promos.set()
        example = '[\n  "Promo 1 {{admin_contact}}",\n  "Promo 2"\n]'
        
    await callback.message.answer(
        f"📝 *Update {target.capitalize()}*\n\n"
        f"Send me a valid JSON array of strings. Example:\n"
        f"`{example}`\n\n"
        "Send /cancel to abort.",
        parse_mode=types.ParseMode.MARKDOWN,
    )
    await callback.answer()

async def _handle_json_input(message: types.Message, state: FSMContext, filename: str):
    import json
    import os
    if not _is_admin(message.from_user.id):
        await state.finish()
        return
        
    try:
        data = json.loads(message.text)
        if not isinstance(data, list) or not all(isinstance(x, str) for x in data):
            raise ValueError("Input must be a JSON array of strings.")
            
        filepath = os.path.join("data", "content", filename)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
            
        await state.finish()
        await message.reply(f"✅ Successfully updated `{filename}` with {len(data)} items!", parse_mode=types.ParseMode.MARKDOWN)
    except json.JSONDecodeError as e:
        await message.reply(f"❌ *JSON Parse Error:*\n`{e}`\n\nPlease send a valid JSON array or /cancel.", parse_mode=types.ParseMode.MARKDOWN)
    except Exception as e:
        await message.reply(f"❌ *Error:*\n`{e}`\n\nPlease try again or /cancel.", parse_mode=types.ParseMode.MARKDOWN)

async def msg_receive_json_names(message: types.Message, state: FSMContext):
    await _handle_json_input(message, state, "names.json")

async def msg_receive_json_convos(message: types.Message, state: FSMContext):
    await _handle_json_input(message, state, "conversations.json")
    
async def msg_receive_json_promos(message: types.Message, state: FSMContext):
    await _handle_json_input(message, state, "promotions.json")


# ==============================================================
# Admin Name Handler
# ==============================================================

async def cb_set_admin_name(callback: types.CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id): return
    await AdminStates.waiting_for_admin_name.set()
    await callback.message.answer(
        "✏️ *Change Admin Name*\n\n"
        "Type the name you want to appear as in testimonials.\n"
        "Send /cancel to abort.",
        parse_mode=types.ParseMode.MARKDOWN,
    )
    await callback.answer()


async def msg_receive_admin_name(message: types.Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        await state.finish()
        return
    new_name = message.text.strip()
    if not new_name or len(new_name) > 30:
        await message.reply("❌ Name must be 1-30 characters. Try again or /cancel.")
        return
    repo.update_setting("admin_name", new_name)
    await state.finish()
    await message.reply(f"✅ Admin name updated to *{new_name}*.", parse_mode=types.ParseMode.MARKDOWN)


async def cb_set_admin_contact(callback: types.CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id): return
    await AdminStates.waiting_for_admin_contact.set()
    await callback.message.answer(
        "📞 *Change Admin Contact*\n\n"
        "Type the contact handle you want to use (e.g. @YourUsername).\n"
        "Send /cancel to abort.",
        parse_mode=types.ParseMode.MARKDOWN,
    )
    await callback.answer()


async def msg_receive_admin_contact(message: types.Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        await state.finish()
        return
    new_contact = message.text.strip()
    if not new_contact or len(new_contact) > 50:
        await message.reply("❌ Contact must be 1-50 characters. Try again or /cancel.")
        return
    repo.update_setting("admin_contact", new_contact)
    await state.finish()
    await message.reply(f"✅ Admin contact updated to *{new_contact}*.", parse_mode=types.ParseMode.MARKDOWN)


async def cmd_cancel(message: types.Message, state: FSMContext):
    if not _is_admin(message.from_user.id): return
    current = await state.get_state()
    if current:
        await state.finish()
        await message.reply("❌ Cancelled.")


# ==============================================================
# Test Mode Handlers
# ==============================================================

async def cb_test_mode_menu(callback: types.CallbackQuery):
    if not _is_admin(callback.from_user.id): return
    from config import TEST_MODE
    if not TEST_MODE:
        await callback.answer("Test Mode is disabled.", show_alert=True)
        return
        
    from bot.keyboards.admin_kb import test_scheduler_kb
    await callback.message.edit_text(
        "🧪 *Test Mode (Scheduler)*\n\nTrigger background tasks instantly for testing:",
        reply_markup=test_scheduler_kb(),
        parse_mode=types.ParseMode.MARKDOWN,
    )
    await callback.answer()

async def cb_test_news(callback: types.CallbackQuery):
    if not _is_admin(callback.from_user.id): return
    from services.scheduler import post_daily_news
    from bot.setup import bot
    await callback.answer("Posting news... check the channel.")
    await post_daily_news(bot)

async def cb_test_testimonial(callback: types.CallbackQuery):
    if not _is_admin(callback.from_user.id): return
    from services.scheduler import post_daily_testimonial
    from bot.setup import bot
    await callback.answer("Posting testimonial... check the channel.")
    await post_daily_testimonial(bot)

async def cb_test_report(callback: types.CallbackQuery):
    if not _is_admin(callback.from_user.id): return
    from services.scheduler import post_weekly_report
    from bot.setup import bot
    await callback.answer("Posting weekly report... check the channel.")
    await post_weekly_report(bot)


    await post_weekly_report(bot)


# ==============================================================
# Flip Campaign Handlers
# ==============================================================

async def cb_flip_menu(callback: types.CallbackQuery):
    if not _is_admin(callback.from_user.id): return
    campaign = repo.get_active_flip_campaign()
    
    if campaign:
        text = (
            "🔄 *Flip Campaign*\n\n"
            f"An active campaign is running.\n"
            f"Start Balance: `${campaign['start_balance']:,.2f}`\n"
            f"Target Balance: `${campaign['target_balance']:,.2f}`\n"
            f"Current Balance: `${campaign['current_balance']:,.2f}`\n"
            f"Trades taken: {campaign['trade_count']}"
        )
    else:
        text = "🔄 *Flip Campaign*\n\nNo active campaign running."
        
    await callback.message.edit_text(
        text,
        reply_markup=flip_kb(bool(campaign)),
        parse_mode=types.ParseMode.MARKDOWN,
    )
    await callback.answer()


async def cb_flip_start(callback: types.CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id): return
    await AdminStates.waiting_for_flip_start.set()
    await callback.message.answer(
        "🔄 *Start New Flip*\n\n"
        "Enter the starting balance (e.g., `50`):\n"
        "Send /cancel to abort.",
        parse_mode=types.ParseMode.MARKDOWN,
    )
    await callback.answer()


async def msg_flip_start(message: types.Message, state: FSMContext):
    if not _is_admin(message.from_user.id): return
    try:
        start_bal = float(message.text.strip())
        await state.update_data(start_bal=start_bal)
        await AdminStates.waiting_for_flip_target.set()
        await message.reply(
            "Enter the target balance (e.g., `5000`):\n"
            "Send /cancel to abort.",
        )
    except ValueError:
        await message.reply("❌ Invalid amount. Enter a number or /cancel.")


async def msg_flip_target(message: types.Message, state: FSMContext):
    if not _is_admin(message.from_user.id): return
    try:
        target_bal = float(message.text.strip())
        data = await state.get_data()
        start_bal = data['start_bal']
        
        repo.create_flip_campaign(start_bal, target_bal)
        await state.finish()
        
        await message.reply(
            f"✅ *Flip Campaign Started!*\n\n"
            f"Start: `${start_bal:,.2f}`\nTarget: `${target_bal:,.2f}`\n\n"
            f"The engine will automatically track and post flip trades.",
            parse_mode=types.ParseMode.MARKDOWN
        )
    except ValueError:
        await message.reply("❌ Invalid amount. Enter a number or /cancel.")


async def cb_flip_view(callback: types.CallbackQuery):
    if not _is_admin(callback.from_user.id): return
    campaign = repo.get_active_flip_campaign()
    if not campaign:
        await callback.answer("No active campaign.", show_alert=True)
        return
        
    text = (
        "📊 *Active Flip Progress*\n\n"
        f"Start: `${campaign['start_balance']:,.2f}`\n"
        f"Target: `${campaign['target_balance']:,.2f}`\n"
        f"Current: `${campaign['current_balance']:,.2f}`\n"
        f"Trades: {campaign['trade_count']}"
    )
    await callback.message.edit_text(
        text,
        reply_markup=flip_kb(True),
        parse_mode=types.ParseMode.MARKDOWN,
    )
    await callback.answer()


async def cb_flip_stop(callback: types.CallbackQuery):
    if not _is_admin(callback.from_user.id): return
    campaign = repo.get_active_flip_campaign()
    if campaign:
        repo.stop_flip_campaign(campaign['id'])
        await callback.answer("Campaign stopped.")
        
    await callback.message.edit_text(
        "🔄 *Flip Campaign*\n\nNo active campaign running.",
        reply_markup=flip_kb(False),
        parse_mode=types.ParseMode.MARKDOWN,
    )


# ==============================================================
# Copier Channels Handlers
# ==============================================================

async def cb_copiers_menu(callback: types.CallbackQuery):
    if not _is_admin(callback.from_user.id): return
    channels = repo.get_all_copier_channels()

    if channels:
        lines = []
        for ch in channels:
            status = "✅" if ch["active"] else "⏸️"
            lines.append(f"{status} *{ch['name']}* | Tone: `{ch['tone']}` | Risk: `{ch['risk_type']}` `{ch['risk_value']}`")
        body = "\n".join(lines)
    else:
        body = "_No channels registered yet. Add your first one!_"

    from bot.keyboards.admin_kb import copier_channels_kb
    await callback.message.edit_text(
        f"📡 *Copier Channels*\n\n{body}",
        reply_markup=copier_channels_kb(channels),
        parse_mode=types.ParseMode.MARKDOWN,
    )
    await callback.answer()


async def cb_copier_view(callback: types.CallbackQuery):
    if not _is_admin(callback.from_user.id): return
    # data: copier_view_<channel_id>
    channel_id = callback.data[len("copier_view_"):]
    ch = repo.get_copier_channel_by_id(channel_id)
    if not ch:
        await callback.answer("Channel not found.", show_alert=True)
        return

    from bot.keyboards.admin_kb import copier_channel_detail_kb
    text = (
        f"📡 *{ch['name']}*\n\n"
        f"Channel ID: `{ch['channel_id']}`\n"
        f"Tone: `{ch['tone']}`\n"
        f"Risk Type: `{ch['risk_type']}`\n"
        f"Risk Value: `{ch['risk_value']}`\n"
        f"Max Trades/Day: `{ch['max_trades_per_day']}`\n"
        f"Admin Name: `{ch['admin_name']}`\n"
        f"Status: {'✅ Active' if ch['active'] else '⏸️ Paused'}"
    )
    await callback.message.edit_text(
        text,
        reply_markup=copier_channel_detail_kb(channel_id, bool(ch["active"])),
        parse_mode=types.ParseMode.MARKDOWN,
    )
    await callback.answer()


async def cb_copier_toggle(callback: types.CallbackQuery):
    if not _is_admin(callback.from_user.id): return
    channel_id = callback.data[len("copier_toggle_"):]
    new_state  = repo.toggle_copier_channel(channel_id)
    status_str = "Active ✅" if new_state else "Paused ⏸️"
    await callback.answer(f"Channel is now {status_str}")
    # Refresh the view
    ch = repo.get_copier_channel_by_id(channel_id)
    if ch:
        from bot.keyboards.admin_kb import copier_channel_detail_kb
        text = (
            f"📡 *{ch['name']}*\n\n"
            f"Channel ID: `{ch['channel_id']}`\n"
            f"Tone: `{ch['tone']}`\n"
            f"Status: {status_str}"
        )
        await callback.message.edit_text(
            text,
            reply_markup=copier_channel_detail_kb(channel_id, new_state),
            parse_mode=types.ParseMode.MARKDOWN,
        )


async def cb_copier_delete(callback: types.CallbackQuery):
    if not _is_admin(callback.from_user.id): return
    channel_id = callback.data[len("copier_delete_"):]
    repo.delete_copier_channel(channel_id)
    channels = repo.get_all_copier_channels()
    from bot.keyboards.admin_kb import copier_channels_kb
    await callback.message.edit_text(
        "📡 *Copier Channels*\n\n✅ Channel removed.",
        reply_markup=copier_channels_kb(channels),
        parse_mode=types.ParseMode.MARKDOWN,
    )
    await callback.answer("Channel deleted.")


async def cb_copier_add(callback: types.CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id): return
    await AdminStates.copier_waiting_channel_id.set()
    await callback.message.answer(
        "📡 *Add New Copier Channel*\n\n"
        "Step 1/7: Send the *Telegram Channel ID* for the channel the bot should post to.\n"
        "_(e.g. `-1001234567890` — you can get this by forwarding a message from the channel to @userinfobot)_\n\n"
        "Send /cancel to abort.",
        parse_mode=types.ParseMode.MARKDOWN,
    )
    await callback.answer()


async def msg_copier_channel_id(message: types.Message, state: FSMContext):
    if not _is_admin(message.from_user.id): return
    cid = message.text.strip()
    await state.update_data(channel_id=cid)
    await AdminStates.copier_waiting_name.set()
    await message.reply(
        "✅ Got it!\n\n"
        "Step 2/7: Enter a *display name* for this channel (e.g. `BTC Signals Channel`).\n"
        "Send /cancel to abort.",
        parse_mode=types.ParseMode.MARKDOWN,
    )


async def msg_copier_name(message: types.Message, state: FSMContext):
    if not _is_admin(message.from_user.id): return
    await state.update_data(name=message.text.strip())
    await AdminStates.copier_waiting_tone.set()

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    tone_kb = InlineKeyboardMarkup(row_width=1)
    tone_kb.add(
        InlineKeyboardButton(text="🔥 HYPE  — Energetic, loud, celebratory",     callback_data="copier_tone_HYPE"),
        InlineKeyboardButton(text="🧊 STOIC — Calm, minimal, no emojis",          callback_data="copier_tone_STOIC"),
        InlineKeyboardButton(text="💼 PROFESSIONAL — Balanced, clean, confident", callback_data="copier_tone_PROFESSIONAL"),
    )
    await message.reply(
        "Step 3/7: Select the *tone* for this channel's posts:",
        reply_markup=tone_kb,
        parse_mode=types.ParseMode.MARKDOWN,
    )


async def cb_copier_tone(callback: types.CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id): return
    tone = callback.data.split("_")[2]
    await state.update_data(tone=tone)
    await AdminStates.copier_waiting_risk_type.set()

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    rtype_kb = InlineKeyboardMarkup(row_width=1)
    rtype_kb.add(
        InlineKeyboardButton(text="💵 USD_RISK — Fixed dollar amount risked per trade", callback_data="copier_rtype_USD_RISK"),
        InlineKeyboardButton(text="📊 LOT_SIZE — Fixed lot size per trade",              callback_data="copier_rtype_LOT_SIZE"),
    )
    await callback.message.edit_text(
        f"✅ Tone set to *{tone}*.\n\n"
        "Step 4/7: How should risk be defined for this channel?",
        reply_markup=rtype_kb,
        parse_mode=types.ParseMode.MARKDOWN,
    )
    await callback.answer()


async def cb_copier_risk_type(callback: types.CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id): return
    risk_type = callback.data.split("_", 2)[2]
    await state.update_data(risk_type=risk_type)
    await AdminStates.copier_waiting_risk_value.set()

    prompt = (
        "Step 5/7: Enter the *risk value*.\n"
        "_(e.g. `50` means $50 USD risked per trade if USD_RISK, or `0.5` lot if LOT_SIZE)_\n\n"
        "Send /cancel to abort."
    )
    await callback.message.answer(prompt, parse_mode=types.ParseMode.MARKDOWN)
    await callback.answer()


async def msg_copier_risk_value(message: types.Message, state: FSMContext):
    if not _is_admin(message.from_user.id): return
    try:
        val = float(message.text.strip())
        await state.update_data(risk_value=val)
        await AdminStates.copier_waiting_max_trades.set()
        await message.reply(
            "Step 6/7: Enter the *max number of signals* to post per day for this channel.\n"
            "_(e.g. `5` means only the first 5 signals of the day are forwarded)_\n\n"
            "Send /cancel to abort.",
            parse_mode=types.ParseMode.MARKDOWN,
        )
    except ValueError:
        await message.reply("❌ Enter a valid number (e.g. `50` or `0.5`). Try again or /cancel.")


async def msg_copier_max_trades(message: types.Message, state: FSMContext):
    if not _is_admin(message.from_user.id): return
    try:
        max_t = int(message.text.strip())
        await state.update_data(max_trades_per_day=max_t)
        await AdminStates.copier_waiting_admin_name.set()
        await message.reply(
            "Step 7/7: Enter the *admin name* to appear in this channel's posts.\n"
            "_(e.g. `Antop`, `Mike`, `Alex`)_\n\n"
            "Send /cancel to abort.",
            parse_mode=types.ParseMode.MARKDOWN,
        )
    except ValueError:
        await message.reply("❌ Enter a whole number (e.g. `5`). Try again or /cancel.")


async def msg_copier_admin_name(message: types.Message, state: FSMContext):
    if not _is_admin(message.from_user.id): return
    admin_name = message.text.strip()
    data = await state.get_data()

    repo.create_copier_channel(
        channel_id=data["channel_id"],
        name=data["name"],
        tone=data["tone"],
        risk_type=data["risk_type"],
        risk_value=data["risk_value"],
        max_trades_per_day=data["max_trades_per_day"],
        admin_name=admin_name,
        owner_user_id=message.from_user.id,
    )
    await state.finish()

    await message.reply(
        f"✅ *Copier Channel Added!*\n\n"
        f"📡 Name: *{data['name']}*\n"
        f"Channel ID: `{data['channel_id']}`\n"
        f"Tone: `{data['tone']}`\n"
        f"Risk: `{data['risk_type']}` — `{data['risk_value']}`\n"
        f"Max Trades/Day: `{data['max_trades_per_day']}`\n"
        f"Admin Name: `{admin_name}`\n\n"
        f"_The bot will now forward signals to this channel automatically._",
        parse_mode=types.ParseMode.MARKDOWN,
    )


# ==============================================================
# Registration (v2 pattern — called from bot/setup.py)
# ==============================================================

def register_handlers(dp: Dispatcher) -> None:
    """Register all admin handlers to the dispatcher."""

    dp.register_message_handler(cmd_admin, commands=["admin"])
    dp.register_message_handler(cmd_cancel, commands=["cancel"], state="*")

    # Core callbacks
    dp.register_callback_query_handler(cb_main_menu,     lambda c: c.data == "admin_main")
    dp.register_callback_query_handler(cb_toggle_trading, lambda c: c.data == "admin_toggle")
    dp.register_callback_query_handler(cb_stats,          lambda c: c.data == "admin_stats")
    dp.register_callback_query_handler(cb_clear,          lambda c: c.data == "admin_clear")

    # Settings
    dp.register_callback_query_handler(cb_settings,      lambda c: c.data == "admin_settings",  state="*")
    dp.register_callback_query_handler(cb_set_lot,        lambda c: c.data.startswith("set_lot_"), state="*")
    dp.register_callback_query_handler(cb_set_admin_name, lambda c: c.data == "set_admin_name",  state="*")
    dp.register_message_handler(msg_receive_admin_name,   state=AdminStates.waiting_for_admin_name)
    dp.register_callback_query_handler(cb_set_admin_contact, lambda c: c.data == "set_admin_contact",  state="*")
    dp.register_message_handler(msg_receive_admin_contact,   state=AdminStates.waiting_for_admin_contact)
    dp.register_callback_query_handler(cb_toggle_market_mode, lambda c: c.data == "toggle_market_mode")

    # Force Signal
    dp.register_callback_query_handler(cb_force_main, lambda c: c.data == "admin_force")
    dp.register_callback_query_handler(cb_force_pair, lambda c: c.data.startswith("force_pair_"))
    dp.register_callback_query_handler(cb_force_dir,  lambda c: c.data.startswith("force_dir_"))

    dp.register_callback_query_handler(cb_schedule,       lambda c: c.data == "admin_schedule")
    
    # Content Manager
    dp.register_callback_query_handler(cb_content_menu,   lambda c: c.data == "admin_content",         state="*")
    dp.register_callback_query_handler(cb_content_update, lambda c: c.data.startswith("content_update_"), state="*")
    dp.register_message_handler(msg_receive_json_names,   state=AdminStates.waiting_for_json_names)
    dp.register_message_handler(msg_receive_json_convos,  state=AdminStates.waiting_for_json_convos)
    dp.register_message_handler(msg_receive_json_promos,  state=AdminStates.waiting_for_json_promos)

    # Test Mode
    dp.register_callback_query_handler(cb_test_mode_menu, lambda c: c.data == "admin_test_mode")
    dp.register_callback_query_handler(cb_test_news,      lambda c: c.data == "test_news")
    dp.register_callback_query_handler(cb_test_testimonial, lambda c: c.data == "test_testimonial")
    dp.register_callback_query_handler(cb_test_report,    lambda c: c.data == "test_report")

    # Flip Campaign
    dp.register_callback_query_handler(cb_flip_menu,  lambda c: c.data == "admin_flip")
    dp.register_callback_query_handler(cb_flip_start, lambda c: c.data == "flip_start", state="*")
    dp.register_callback_query_handler(cb_flip_view,  lambda c: c.data == "flip_view")
    dp.register_callback_query_handler(cb_flip_stop,  lambda c: c.data == "flip_stop")
    dp.register_message_handler(msg_flip_start,  state=AdminStates.waiting_for_flip_start)
    dp.register_message_handler(msg_flip_target, state=AdminStates.waiting_for_flip_target)

    # Copier Channels
    dp.register_callback_query_handler(cb_copiers_menu,    lambda c: c.data == "admin_copiers")
    dp.register_callback_query_handler(cb_copier_view,     lambda c: c.data.startswith("copier_view_"))
    dp.register_callback_query_handler(cb_copier_toggle,   lambda c: c.data.startswith("copier_toggle_"))
    dp.register_callback_query_handler(cb_copier_delete,   lambda c: c.data.startswith("copier_delete_"))
    dp.register_callback_query_handler(cb_copier_add,      lambda c: c.data == "copier_add", state="*")
    dp.register_message_handler(msg_copier_channel_id,     state=AdminStates.copier_waiting_channel_id)
    dp.register_message_handler(msg_copier_name,           state=AdminStates.copier_waiting_name)
    dp.register_callback_query_handler(cb_copier_tone,     lambda c: c.data.startswith("copier_tone_"), state="*")
    dp.register_callback_query_handler(cb_copier_risk_type, lambda c: c.data.startswith("copier_rtype_"), state="*")
    dp.register_message_handler(msg_copier_risk_value,     state=AdminStates.copier_waiting_risk_value)
    dp.register_message_handler(msg_copier_max_trades,     state=AdminStates.copier_waiting_max_trades)
    dp.register_message_handler(msg_copier_admin_name,     state=AdminStates.copier_waiting_admin_name)
