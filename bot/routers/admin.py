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
    settings_kb, testimonials_kb, flip_kb
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
    waiting_for_testimonial = State()  # Waiting for the user to type the script
    waiting_for_admin_name  = State()  # Waiting for the user to type the new name
    waiting_for_admin_contact = State()
    waiting_for_flip_start  = State()
    waiting_for_flip_target = State()


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

    await callback.message.edit_text(
        f"⚙️ *Settings*\n\n"
        f"Admin Name: `{admin_name}`\n"
        f"Admin Contact: `{admin_contact}`\n\n"
        f"Select a default Lot Size:",
        reply_markup=settings_kb(current_lot),
        parse_mode=types.ParseMode.MARKDOWN,
    )
    await callback.answer()


async def cb_set_lot(callback: types.CallbackQuery):
    if not _is_admin(callback.from_user.id): return
    new_lot = float(callback.data.split("_")[2])
    repo.update_setting("lot_size", new_lot)
    settings = repo.get_settings()
    admin_name = settings.get("admin_name", "Mike")
    await callback.message.edit_text(
        f"⚙️ *Settings*\n\n"
        f"Admin Name: `{admin_name}`\n\n"
        f"✅ Lot size updated to `{new_lot}`.\nSelect a new default Lot Size:",
        reply_markup=settings_kb(new_lot),
        parse_mode=types.ParseMode.MARKDOWN,
    )
    await callback.answer("Lot size updated!")


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
    if direction == "BUY":
        entry_price = price - rules["tp1_offset"]
        tp1 = entry_price + rules["tp1_offset"]
        tp2 = entry_price + rules["tp2_offset"]
        tp3 = entry_price + rules["tp3_offset"]
        sl = entry_price - rules["sl_offset"]
    else:
        entry_price = price + rules["tp1_offset"]
        tp1 = entry_price - rules["tp1_offset"]
        tp2 = entry_price - rules["tp2_offset"]
        tp3 = entry_price - rules["tp3_offset"]
        sl = entry_price + rules["sl_offset"]

    settings = repo.get_settings()
    lot_size = float(settings.get("lot_size", 0.1))
    
    trade_id = repo.create_trade(
        pair=pair,
        direction=direction,
        entry_price=entry_price,
        tp1=tp1, tp2=tp2, tp3=tp3, sl=sl,
        lot_size=lot_size
    )
    
    # Fast forward trade to TP1
    repo.update_trade_stage(trade_id, "TP1")
    repo.update_trade_price(trade_id, tp1)
    repo.mark_trade_posted(trade_id)
    
    import services.event_bus as event_bus
    event_bus.publish("SIGNAL_POST", {
        "id": trade_id,
        "pair": pair,
        "direction": direction,
        "entry": entry_price,
        "current_price": tp1,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "sl": sl,
        "lot_size": lot_size
    })
    
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    back_kb = InlineKeyboardMarkup().add(InlineKeyboardButton(text="← Back to Admin", callback_data="admin_main"))

    await callback.message.edit_text(
        f"✅ *Forced {direction} signal for {pair}!*\n\n"
        f"Fake Entry: `${entry_price:,.2f}`\n"
        f"Current Price (TP1): `${tp1:,.2f}`\n"
        f"SL: `${sl:,.2f}`\n\n"
        f"The screenshot has been instantly generated and posted to the channel!",
        reply_markup=back_kb,
        parse_mode=types.ParseMode.MARKDOWN,
    )
    await callback.answer("Signal forced!")


# ==============================================================
# Testimonial Handlers
# ==============================================================

async def cb_testimonials(callback: types.CallbackQuery):
    if not _is_admin(callback.from_user.id): return
    items = repo.list_testimonials()
    await callback.message.edit_text(
        f"💬 *Testimonials* ({len(items)} in pool)\n\n"
        "Tap one to view/delete, or add a new script below.",
        reply_markup=testimonials_kb(items),
        parse_mode=types.ParseMode.MARKDOWN,
    )
    await callback.answer()


async def cb_testimonial_add(callback: types.CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id): return
    await AdminStates.waiting_for_testimonial.set()
    await callback.message.answer(
        "📝 *New Testimonial Script*\n\n"
        "Type the conversation in pipe-separated format:\n\n"
        "`THEM: Yo {{admin}} I hit TP3! | ME: Let's go! | THEM: Thanks so much!`\n\n"
        "⚠️ Max 6 lines. Use `{{admin}}` as a placeholder for your admin name.\n\n"
        "Send /cancel to abort.",
        parse_mode=types.ParseMode.MARKDOWN,
    )
    await callback.answer()


async def msg_receive_testimonial(message: types.Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        await state.finish()
        return
    script = message.text.strip()
    if len(script) < 10:
        await message.reply("❌ Script is too short. Please try again or send /cancel.")
        return
    repo.add_testimonial(script)
    await state.finish()
    await message.reply(
        "✅ Testimonial saved to the pool! It will be randomly posted daily at 2:00 PM UTC."
    )


async def cb_testimonial_view(callback: types.CallbackQuery):
    if not _is_admin(callback.from_user.id): return
    tid = int(callback.data.split("_")[2])
    items = repo.list_testimonials()
    item  = next((t for t in items if t["id"] == tid), None)
    if not item:
        await callback.answer("❌ Not found.", show_alert=True)
        return
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(text="🗑️ Delete", callback_data=f"testimonial_del_{tid}"),
        InlineKeyboardButton(text="← Back",    callback_data="admin_testimonials"),
    )
    await callback.message.edit_text(
        f"*Testimonial #{tid}:*\n\n`{item['script']}`",
        reply_markup=kb,
        parse_mode=types.ParseMode.MARKDOWN,
    )
    await callback.answer()


async def cb_testimonial_delete(callback: types.CallbackQuery):
    if not _is_admin(callback.from_user.id): return
    tid = int(callback.data.split("_")[2])
    repo.delete_testimonial(tid)
    items = repo.list_testimonials()
    await callback.message.edit_text(
        f"✅ Testimonial #{tid} deleted.\n\n💬 *Testimonials* ({len(items)} in pool)",
        reply_markup=testimonials_kb(items),
        parse_mode=types.ParseMode.MARKDOWN,
    )
    await callback.answer(f"Deleted #{tid}")


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

    # Force Signal
    dp.register_callback_query_handler(cb_force_main, lambda c: c.data == "admin_force")
    dp.register_callback_query_handler(cb_force_pair, lambda c: c.data.startswith("force_pair_"))
    dp.register_callback_query_handler(cb_force_dir,  lambda c: c.data.startswith("force_dir_"))

    # Testimonials
    dp.register_callback_query_handler(cb_testimonials,       lambda c: c.data == "admin_testimonials",         state="*")
    dp.register_callback_query_handler(cb_testimonial_add,    lambda c: c.data == "testimonial_add",            state="*")
    dp.register_callback_query_handler(cb_testimonial_view,   lambda c: c.data.startswith("testimonial_view_"), state="*")
    dp.register_callback_query_handler(cb_testimonial_delete, lambda c: c.data.startswith("testimonial_del_"),  state="*")
    dp.register_message_handler(msg_receive_testimonial,      state=AdminStates.waiting_for_testimonial)

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
