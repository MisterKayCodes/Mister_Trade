"""
admin_kb.py

Mouth & Ears / Keyboards

Job:
Build inline keyboard layouts for the admin panel.

Rules:
    - aiogram v2 style (InlineKeyboardMarkup + add())
    - No logic here, only keyboard structure
    - No database imports
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def main_menu_kb() -> InlineKeyboardMarkup:
    """Main admin panel keyboard."""
    from config import TEST_MODE
    keyboard = InlineKeyboardMarkup(row_width=3)
    keyboard.add(
        InlineKeyboardButton(text="📊 Stats",             callback_data="admin_stats"),
        InlineKeyboardButton(text="⚙️ Settings",          callback_data="admin_settings"),
        InlineKeyboardButton(text="💬 Testimonials",      callback_data="admin_testimonials"),
        InlineKeyboardButton(text="📈 Force Signal",      callback_data="admin_force"),
        InlineKeyboardButton(text="🗑️ Clear Trades",      callback_data="admin_clear"),
        InlineKeyboardButton(text="🔄 Toggle Trading",    callback_data="admin_toggle"),
        InlineKeyboardButton(text="🔄 Flip Campaign",     callback_data="admin_flip"),
    )
    
    if TEST_MODE:
        keyboard.add(InlineKeyboardButton(text="🧪 Test Mode (Scheduler)", callback_data="admin_test_mode"))
        
    return keyboard


def force_pair_kb() -> InlineKeyboardMarkup:
    """Select which pair to force."""
    from config import PAIRS
    keyboard = InlineKeyboardMarkup(row_width=2)
    buttons = [InlineKeyboardButton(text=p, callback_data=f"force_pair_{p}") for p in PAIRS]
    keyboard.add(*buttons)
    keyboard.add(InlineKeyboardButton(text="← Back", callback_data="admin_main"))
    return keyboard


def force_dir_kb(pair: str) -> InlineKeyboardMarkup:
    """Select direction to force."""
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton(text="🟢 BUY",  callback_data=f"force_dir_{pair}_BUY"),
        InlineKeyboardButton(text="🔴 SELL", callback_data=f"force_dir_{pair}_SELL"),
    )
    keyboard.add(InlineKeyboardButton(text="← Back", callback_data="admin_force"))
    return keyboard


def settings_kb(current_lot: float) -> InlineKeyboardMarkup:
    """Settings menu (lot size + admin name)."""
    keyboard = InlineKeyboardMarkup(row_width=3)
    keyboard.add(
        InlineKeyboardButton(text="5.0"  + (" ✅" if current_lot == 5.0  else ""), callback_data="set_lot_5.0"),
        InlineKeyboardButton(text="10.0" + (" ✅" if current_lot == 10.0 else ""), callback_data="set_lot_10.0"),
        InlineKeyboardButton(text="50.0" + (" ✅" if current_lot == 50.0 else ""), callback_data="set_lot_50.0"),
    )
    keyboard.add(InlineKeyboardButton(text="✏️ Change Admin Name", callback_data="set_admin_name"))
    keyboard.add(InlineKeyboardButton(text="📞 Change Admin Contact", callback_data="set_admin_contact"))
    keyboard.add(InlineKeyboardButton(text="← Back", callback_data="admin_main"))
    return keyboard


def testimonials_kb(testimonials: list) -> InlineKeyboardMarkup:
    """List existing testimonials with delete buttons, plus Add button."""
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(InlineKeyboardButton(text="➕ Add New Testimonial", callback_data="testimonial_add"))
    for t in testimonials:
        # Truncate script preview to 30 chars
        preview = t["script"][:30].replace("\n", " ") + ("..." if len(t["script"]) > 30 else "")
        keyboard.add(
            InlineKeyboardButton(
                text=f"#{t['id']} {preview}",
                callback_data=f"testimonial_view_{t['id']}"
            )
        )
    keyboard.add(InlineKeyboardButton(text="← Back", callback_data="admin_main"))
    return keyboard


def confirm_kb(confirm_data: str, cancel_data: str = "admin_main") -> InlineKeyboardMarkup:
    """Yes / No confirmation keyboard. Used before destructive actions."""
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton(text="✅ Yes", callback_data=confirm_data),
        InlineKeyboardButton(text="❌ No",  callback_data=cancel_data),
    )
    return keyboard


def test_scheduler_kb() -> InlineKeyboardMarkup:
    """Test Mode keyboard to manually trigger scheduled tasks."""
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton(text="📰 Post Daily News",       callback_data="test_news"),
        InlineKeyboardButton(text="💬 Post Testimonial",    callback_data="test_testimonial"),
        InlineKeyboardButton(text="📊 Post Weekly Report", callback_data="test_report"),
        InlineKeyboardButton(text="← Back",                 callback_data="admin_main")
    )
    return keyboard


def flip_kb(active_campaign: bool) -> InlineKeyboardMarkup:
    """Flip Campaign menu."""
    keyboard = InlineKeyboardMarkup(row_width=1)
    if active_campaign:
        keyboard.add(
            InlineKeyboardButton(text="📊 View Active Flip", callback_data="flip_view"),
            InlineKeyboardButton(text="🛑 Stop Flip", callback_data="flip_stop")
        )
    else:
        keyboard.add(
            InlineKeyboardButton(text="▶️ Start New Flip", callback_data="flip_start")
        )
    keyboard.add(InlineKeyboardButton(text="← Back", callback_data="admin_main"))
    return keyboard
