"""Render images as half-block ASCII art for the terminal."""

from io import BytesIO

from PIL import Image
from rich.color import Color
from rich.style import Style
from rich.text import Text

# Half-block character: top pixel = foreground, bottom pixel = background
HALF_BLOCK = "\u2580"  # Upper half block

MAX_WIDTH = 40  # max columns for the image


def render_image(data: bytes, max_width: int = MAX_WIDTH) -> Text:
    """Convert image bytes to a Rich Text using half-block characters.

    Each character cell represents 2 vertical pixels using the upper half
    block character with foreground (top pixel) and background (bottom pixel)
    colors. This gives 2x vertical resolution.
    """
    img = Image.open(BytesIO(data))
    img = img.convert("RGB")

    # Resize to fit max_width, maintaining aspect ratio
    w, h = img.size
    if w > max_width:
        ratio = max_width / w
        w = max_width
        h = int(h * ratio)
    # Height must be even for half-block pairing
    if h % 2 != 0:
        h += 1
    img = img.resize((w, h), Image.LANCZOS)

    result = Text()
    pixels = img.load()

    for y in range(0, h, 2):
        for x in range(w):
            top_r, top_g, top_b = pixels[x, y]
            if y + 1 < h:
                bot_r, bot_g, bot_b = pixels[x, y + 1]
            else:
                bot_r, bot_g, bot_b = top_r, top_g, top_b

            fg = Color.from_rgb(top_r, top_g, top_b)
            bg = Color.from_rgb(bot_r, bot_g, bot_b)
            style = Style(color=fg, bgcolor=bg)
            result.append(HALF_BLOCK, style=style)
        result.append("\n")

    return result


def human_size(size_bytes: int) -> str:
    """Format byte count as human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.0f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
