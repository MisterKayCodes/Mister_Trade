"""
renderer.py

Integrations / Testimonial Screenshot

Job:
Take a conversation script and an admin name, render it as a
realistic Telegram chat screenshot using html2image.

Rules:
    - Max 6 lines (3 exchanges) enforced — never more
    - Canvas height is calculated dynamically based on bubble count
    - Profile photo is a coloured circle with initials (zero external deps)
    - Returns absolute path to PNG on success, raises on failure
    - No Telegram I/O here — caller handles sending

Script format (stored in DB):
    "THEM: Thank you {{admin}}! | ME: No problem! | THEM: I made $200!"
"""

import os
import random
import hashlib
from datetime import datetime
from html2image import Html2Image
from typing import List, Tuple

TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "template.html")
OUTPUT_DIR    = os.path.join(os.path.dirname(__file__), "output")

os.makedirs(OUTPUT_DIR, exist_ok=True)

# A palette of nice avatar background colors
AVATAR_COLORS = [
    "#7C4DFF", "#E91E63", "#00BCD4", "#FF5722",
    "#009688", "#3F51B5", "#FF9800", "#607D8B",
]

# Max bubbles enforced for UI safety (3 THEM + 3 ME = 6)
MAX_LINES = 6

# Approx pixel height per bubble for dynamic canvas sizing
BASE_HEIGHT  = 60   # date pill + padding
HEIGHT_PER_BUBBLE = 75


hti = Html2Image()
hti.browser.flags = [
    '--headless',
    '--disable-gpu',
    '--hide-scrollbars',
    '--mute-audio',
    '--no-sandbox',
    '--default-background-color=00000000'
]


# Fake first names pool — used to randomise the "them" name
THEM_NAMES = [
    "James", "Luca", "Emma", "Amara", "Noah", "Chloe",
    "Marcus", "Aisha", "Daniel", "Priya", "Ryan", "Sofia",
]

# Fake send times for authenticity
def _fake_times(n: int) -> List[str]:
    """Generate n ascending fake HH:MM times within business hours."""
    base_hour = random.randint(9, 16)
    base_min  = random.randint(0, 55)
    times = []
    for i in range(n):
        total = base_hour * 60 + base_min + i * random.randint(3, 15)
        h, m = divmod(total % (24 * 60), 60)
        times.append(f"{h:02d}:{m:02d}")
    return times


def _avatar_html(initials: str, color: str) -> str:
    return (
        f'<div class="avatar" style="background-color:{color};">'
        f'{initials}</div>'
    )


def _parse_script(raw_script: str, admin_name: str, them_name: str) -> List[Tuple[str, str]]:
    """
    Parse pipe-separated script into [(side, text), ...].
    Replaces {{admin}} with the admin name.
    Supports DATE: tags for custom date pills.
    """
    lines = [l.strip() for l in raw_script.split("|") if l.strip()]
    lines = lines[:10]  # Cap raised slightly to accommodate date pills

    # Auto-inject DATE: TODAY if first line isn't a date
    if lines and not lines[0].upper().startswith("DATE:"):
        lines.insert(0, "DATE: TODAY")

    parsed = []
    for line in lines:
        if line.upper().startswith("ME:"):
            text = line[3:].strip().replace("{{admin}}", admin_name).replace("{{them}}", them_name)
            parsed.append(("ME", text))
        elif line.upper().startswith("THEM:"):
            text = line[5:].strip().replace("{{admin}}", admin_name).replace("{{them}}", them_name)
            parsed.append(("THEM", text))
        elif line.upper().startswith("DATE:"):
            text = line[5:].strip()
            parsed.append(("DATE", text))

    return parsed


def render_testimonial(script: str, admin_name: str, filename: str = "testimonial.png") -> str:
    """
    Render a testimonial conversation as a PNG and return its path.

    Args:
        script:      Pipe-separated conversation e.g. "THEM: Hi {{admin}}! | ME: Hey!"
        admin_name:  The admin's display name used to replace {{admin}} tokens.
        filename:    Output filename.

    Returns:
        Absolute path to the generated PNG.
    """
    # Pick a consistent them-name for the day
    today_str  = datetime.now().strftime("%Y-%m-%d")
    rng = random.Random(today_str + script[:10])
    them_name  = rng.choice(THEM_NAMES)
    them_color = rng.choice(AVATAR_COLORS)
    them_initial = them_name[0].upper()

    sender_color = them_color

    parsed = _parse_script(script, admin_name, them_name)
    if not parsed:
        raise ValueError("Testimonial script produced zero valid lines after parsing.")

    bubble_count = len([p for p in parsed if p[0] in ("ME", "THEM")])
    times = _fake_times(bubble_count)

    # Build bubble HTML
    bubble_html_parts = []
    
    for side, text in parsed:
        if side == "DATE":
            if text.upper() == "TODAY":
                text = "Today"
            bubble_html_parts.append(f'<div class="date-pill"><span>{text}</span></div>')
            continue
            
        t = times.pop(0) if times else "12:00"
        
        if side == "THEM":
            bubble = (
                f'<div class="bubble-wrapper">'
                f'  <div class="bubble them">'
                f'    {text}'
                f'    <div class="time-container">'
                f'      <span class="time">{t}</span>'
                f'    </div>'
                f'    <div class="spacer-clear"></div>'
                f'  </div>'
                f'</div>'
            )
        else:
            bubble = (
                f'<div class="bubble-wrapper right">'
                f'  <div class="bubble us">'
                f'    {text}'
                f'    <div class="time-container">'
                f'      <span class="time">{t}</span>'
                f'      <span class="checks">'
                f'         <svg viewBox="0 0 24 24"><path d="M18 7l-1.41-1.41-6.34 6.34 1.41 1.41L18 7zm4.24-1.41L11.66 16.17 7.48 12l-1.41 1.41L11.66 19l12-12-1.42-1.41zM.41 13.41L6 19l1.41-1.41L1.83 12 .41 13.41z"/></svg>'
                f'      </span>'
                f'    </div>'
                f'    <div class="spacer-clear"></div>'
                f'  </div>'
                f'</div>'
            )
        bubble_html_parts.append(bubble)

    messages_html = "\n".join(bubble_html_parts)

    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        html = f.read()

    html = html.replace("{{messages}}", messages_html)
    html = html.replace("{{them_name}}", them_name)
    html = html.replace("{{them_initial}}", them_initial)
    html = html.replace("{{sender_color}}", sender_color)

    # Dynamic canvas height based on bubble count
    canvas_height = BASE_HEIGHT + HEIGHT_PER_BUBBLE * len(parsed)

    hti.output_path = OUTPUT_DIR
    hti.browser.flags[0] = '--headless'  # ensure flag intact

    hti_instance = Html2Image(size=(400, canvas_height))
    hti_instance.browser.flags = [
        '--headless', '--disable-gpu', '--hide-scrollbars',
        '--mute-audio', '--no-sandbox', '--default-background-color=00000000'
    ]
    hti_instance.output_path = OUTPUT_DIR
    hti_instance.screenshot(html_str=html, save_as=filename)

    output_path = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(output_path):
        raise FileNotFoundError(f"html2image failed to create: {output_path}")

    return output_path
