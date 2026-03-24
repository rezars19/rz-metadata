"""
RZ Automedata - Theme Constants & Utilities
Shared color palette, preview settings, and helper functions used across all UI modules.
"""

from PIL import Image

# ─── Theme Colors ────────────────────────────────────────────────────────────────
COLORS = {
    "bg_darkest":       "#08061a",
    "bg_dark":          "#0f0a1e",
    "bg_card":          "#1a1035",
    "bg_card_hover":    "#221540",
    "bg_input":         "#140e2a",
    "border":           "#2a1f55",
    "border_glow":      "#6366f1",
    "neon_blue":        "#818cf8",
    "neon_blue_dim":    "#5558d4",
    "accent_blue":      "#6366f1",
    "accent_purple":    "#8b5cf6",
    "text_primary":     "#e8e0ff",
    "text_secondary":   "#9890c4",
    "text_muted":       "#5a4d80",
    "success":          "#00ff88",
    "error":            "#ff4466",
    "warning":          "#ffaa00",
    "stop_red":         "#ff2244",
    "clear_orange":     "#ff8800",
    "table_border":     "#2a1f55",
    "table_row_even":   "#140e2a",
    "table_row_odd":    "#1a1035",
    "table_header":     "#1e1440",
}

# Preview thumbnail size (small + compressed for speed)
PREVIEW_SIZE = (64, 48)


def compress_preview(img, max_size=PREVIEW_SIZE, quality=70):
    """Compress and resize preview image to reduce memory and speed up loading."""
    if img is None:
        return None
    img = img.copy()
    img.thumbnail(max_size, Image.LANCZOS)
    # Convert to RGB if RGBA
    if img.mode == "RGBA":
        bg = Image.new("RGB", img.size, (26, 16, 53))
        bg.paste(img, mask=img.split()[3])
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")
    return img
