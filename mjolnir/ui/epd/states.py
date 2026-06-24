"""Display states for the e-Paper UI.

14 primary states with a strict priority order (highest first), plus one
overlay banner (BLOCKLIST_NEARBY) that can appear on top of any primary
state. See spec § E-Paper display.
"""
from enum import IntEnum


class DisplayState(IntEnum):
    """Priority-ordered display states. Lower number = higher priority."""
    SHUTTING_DOWN = 1
    STARTING_UP = 2
    FATAL_ERROR = 3
    KILL_SWITCH_ENGAGED = 4
    NO_INTERFACES_UP = 5
    NO_NETWORKS_VISIBLE = 6
    NO_KNOWN_NETWORKS = 7
    CONNECTING = 8
    NO_INTERNET = 9
    TAILSCALE_DOWN = 10
    ACTIVE_IDLE = 11
    VIEW_ONLY_PASSIVE = 12
    ACTIVE_WORKING = 13
    # Note: BLOCKLIST_NEARBY is handled separately as an overlay, not a primary state


from PIL import Image, ImageDraw, ImageFont

RENDER_WIDTH = 122
RENDER_HEIGHT = 250

# Try to load a small bitmap font; fall back to default if unavailable.
_FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONT_PATHS:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _new_image() -> Image.Image:
    """Create a blank white image at display resolution."""
    return Image.new("1", (RENDER_WIDTH, RENDER_HEIGHT), 255)


def _draw_header(draw: ImageDraw.ImageDraw, title: str) -> None:
    """Draw a header bar with title text."""
    font = _load_font(12)
    draw.rectangle([(0, 0), (RENDER_WIDTH, 16)], fill=0)
    draw.text((4, 2), title, font=font, fill=255)


def _draw_centered(draw: ImageDraw.ImageDraw, text: str, y: int, size: int = 14) -> None:
    font = _load_font(size)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    x = (RENDER_WIDTH - text_width) // 2
    draw.text((x, y), text, font=font, fill=0)


def _draw_blocklist_overlay(draw: ImageDraw.ImageDraw, ssid: str = "") -> None:
    """Draw a BLOCKED banner at the top of the image."""
    font = _load_font(10)
    banner_text = f"BLOCKED: {ssid}" if ssid else "BLOCKED NEARBY"
    draw.rectangle([(0, RENDER_HEIGHT - 14), (RENDER_WIDTH, RENDER_HEIGHT)], fill=0)
    bbox = draw.textbbox((0, 0), banner_text, font=font)
    text_width = bbox[2] - bbox[0]
    x = (RENDER_WIDTH - text_width) // 2
    draw.text((x, RENDER_HEIGHT - 12), banner_text, font=font, fill=255)


def render_state(state: DisplayState, conditions, overlay: bool = False) -> Image.Image:
    """Render the given state to a 122x250 PIL Image.

    `conditions` is a SystemConditions instance (used for dynamic content
    like error messages, network counts, etc.). `overlay=True` adds the
    BLOCKLIST_NEARBY banner.
    """
    img = _new_image()
    draw = ImageDraw.Draw(img)

    if state == DisplayState.SHUTTING_DOWN:
        _draw_header(draw, "SHUTDOWN")
        _draw_centered(draw, "Shutting down", 80)
        _draw_centered(draw, "Please wait", 100, size=12)
    elif state == DisplayState.STARTING_UP:
        _draw_header(draw, "BOOT")
        _draw_centered(draw, "Starting mjolnir", 80)
        _draw_centered(draw, "...", 100, size=12)
    elif state == DisplayState.FATAL_ERROR:
        _draw_header(draw, "ERROR")
        _draw_centered(draw, "FATAL ERROR", 60, size=14)
        msg = conditions.fatal_error or "unknown"
        # Wrap long error messages
        font = _load_font(10)
        words = msg.split()
        line = ""
        y = 90
        for word in words:
            test = f"{line} {word}".strip()
            bbox = draw.textbbox((0, 0), test, font=font)
            if bbox[2] - bbox[0] > RENDER_WIDTH - 8:
                draw.text((4, y), line, font=font, fill=0)
                y += 12
                line = word
            else:
                line = test
        if line:
            draw.text((4, y), line, font=font, fill=0)
    elif state == DisplayState.KILL_SWITCH_ENGAGED:
        _draw_header(draw, "KILLED")
        _draw_centered(draw, "KILL SWITCH", 70, size=16)
        _draw_centered(draw, "ENGAGED", 92, size=16)
        _draw_centered(draw, "All work halted", 130, size=11)
        _draw_centered(draw, "Release via WebUI", 150, size=11)
    elif state == DisplayState.NO_INTERFACES_UP:
        _draw_header(draw, "NO RADIO")
        _draw_centered(draw, "No WiFi", 80)
        _draw_centered(draw, "interface", 100)
        _draw_centered(draw, "Retrying...", 140, size=11)
    elif state == DisplayState.NO_NETWORKS_VISIBLE:
        _draw_header(draw, "SCAN")
        _draw_centered(draw, "Scanning...", 80)
        _draw_centered(draw, "No networks", 100)
        _draw_centered(draw, "in range", 120)
    elif state == DisplayState.NO_KNOWN_NETWORKS:
        _draw_header(draw, "SCAN")
        _draw_centered(draw, "Networks visible", 70, size=12)
        _draw_centered(draw, "but none", 90, size=12)
        _draw_centered(draw, "preferred", 110, size=12)
        _draw_centered(draw, "Add via WebUI", 150, size=11)
    elif state == DisplayState.CONNECTING:
        _draw_header(draw, "CONNECT")
        _draw_centered(draw, "Joining", 80)
        _draw_centered(draw, "network...", 100)
    elif state == DisplayState.NO_INTERNET:
        _draw_header(draw, "NO NET")
        _draw_centered(draw, "Connected to", 70, size=12)
        _draw_centered(draw, "WiFi", 90, size=12)
        _draw_centered(draw, "No internet", 130, size=12)
        _draw_centered(draw, "WebUI local", 160, size=10)
    elif state == DisplayState.TAILSCALE_DOWN:
        _draw_header(draw, "VPN")
        _draw_centered(draw, "Internet OK", 70, size=12)
        _draw_centered(draw, "Tailscale", 90, size=12)
        _draw_centered(draw, "not connected", 110, size=12)
        _draw_centered(draw, "WebUI local", 150, size=10)
    elif state == DisplayState.ACTIVE_IDLE:
        _draw_header(draw, "IDLE")
        _draw_centered(draw, "Mode: ACTIVE", 40, size=12)
        _draw_centered(draw, "All visible nets", 70, size=11)
        _draw_centered(draw, "exhausted/done", 86, size=11)
        font = _load_font(10)
        y = 110
        for ssid, reason in conditions.exhausted_in_range[:8]:
            draw.text((4, y), f"- {ssid[:14]}", font=font, fill=0)
            y += 12
    elif state == DisplayState.VIEW_ONLY_PASSIVE:
        _draw_header(draw, "VIEW-ONLY")
        _draw_centered(draw, "Passive mode", 40, size=12)
        _draw_centered(draw, f"{conditions.view_only_networks_in_range}", 80, size=20)
        _draw_centered(draw, "networks", 110, size=12)
        _draw_centered(draw, "in range", 128, size=12)
        _draw_centered(draw, "Toggle ACTIVE", 170, size=10)
        _draw_centered(draw, "via WebUI", 185, size=10)
    elif state == DisplayState.ACTIVE_WORKING:
        _draw_header(draw, "ACTIVE")
        _draw_centered(draw, "Working...", 40, size=12)
        _draw_centered(draw, "See WebUI", 150, size=10)
        _draw_centered(draw, "for details", 165, size=10)

    if overlay:
        _draw_blocklist_overlay(draw)

    return img
