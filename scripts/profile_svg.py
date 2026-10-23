"""Shared palette, glyphs and file helpers for the profile artwork.

Everything here is dependency-free so it runs on a stock GitHub Actions runner.
All SVGs are self-contained: system fonts only, no external URLs.
"""

from html import escape
import json
import os
from pathlib import Path
import re
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, 'Liberation Mono', monospace"
MONO_ADVANCE = 0.6  # used only for chips; per-glyph x positions are pinned where it matters

THEMES = {
    "light": {
        "bg_top": "#ffffff", "bg_bottom": "#f6f8fa", "border": "#d1d9e0",
        "text": "#1f2328", "muted": "#59636e", "faint": "#8c959f", "grid": "#e6eaef",
        "green": "#0f8a5f", "violet": "#7c3aed", "blue": "#2563eb", "amber": "#b45309",
        "tile": 0.10, "glow": 0.10,
    },
    "dark": {
        "bg_top": "#161b22", "bg_bottom": "#0d1117", "border": "#30363d",
        "text": "#e6edf3", "muted": "#9198a1", "faint": "#6e7681", "grid": "#21262d",
        "green": "#34d399", "violet": "#a78bfa", "blue": "#60a5fa", "amber": "#fbbf24",
        "tile": 0.14, "glow": 0.16,
    },
}

# 24x24 stroke glyphs drawn for this profile (not brand marks).
GLYPHS = {
    "code": "M8.5 7 3.5 12l5 5M15.5 7l5 5-5 5M13.5 4.5l-3 15",
    "sparkle": "M12 3c.7 4.6 3.4 7.3 8 8-4.6.7-7.3 3.4-8 8-.7-4.6-3.4-7.3-8-8 4.6-.7 7.3-3.4 8-8Z",
    "tree": "M12 6.5v3M12 9.5 6.5 14.5M12 9.5l5.5 5M6.5 14.5v2.5M17.5 14.5v2.5M12 3.5a2 2 0 1 1 0 4 2 2 0 0 1 0-4ZM6.5 17a2 2 0 1 1 0 4 2 2 0 0 1 0-4ZM17.5 17a2 2 0 1 1 0 4 2 2 0 0 1 0-4Z",
    "terminal": "M5 4.5h14a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-11a2 2 0 0 1 2-2ZM7 9.5l3 2.5-3 2.5M12.5 15H17",
    "calendar": "M5 5h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2ZM3 10h18M8 3v4M16 3v4M7 14h3M14 14h3M7 17.5h3",
    "shield": "M12 3 4.5 6v5.5c0 4.6 3.1 8.2 7.5 9.5 4.4-1.3 7.5-4.9 7.5-9.5V6L12 3ZM12 10.5v3.5M12 8.5a2 2 0 1 1 0 4 2 2 0 0 1 0-4Z",
    "gauge": "M4 17a8 8 0 1 1 16 0M12 17l4-5M7 13.5l1 .6M12 9v1.2M17 13.5l-1 .6",
    "wifi": "M2.5 9a14 14 0 0 1 19 0M5.5 12.5a9.5 9.5 0 0 1 13 0M8.5 16a5 5 0 0 1 7 0M12 19.5h.01",
    "laptop": "M5 5.5h14v10H5zM2.5 18.5h19",
    "desktop": "M3.5 4.5h17v11h-17zM9 20h6M12 15.5V20",
    "router": "M4 13h16a1 1 0 0 1 1 1v4a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-4a1 1 0 0 1 1-1ZM7 13 5.5 5.5M17 13l1.5-7.5M7 16h.01M10 16h.01",
    "nas": "M6.5 3h11a1.5 1.5 0 0 1 1.5 1.5v15a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 5 19.5v-15A1.5 1.5 0 0 1 6.5 3ZM8.5 7h7M8.5 10h7M12 16.5h.01",
    "database": "M12 3c4.4 0 8 1.3 8 3s-3.6 3-8 3-8-1.3-8-3 3.6-3 8-3ZM4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3",
    "globe": "M12 3a9 9 0 1 1 0 18 9 9 0 0 1 0-18ZM3 12h18M12 3c2.5 2.6 3.7 5.6 3.7 9s-1.2 6.4-3.7 9c-2.5-2.6-3.7-5.6-3.7-9S9.5 5.6 12 3Z",
    "mail": "M4 5.5h16a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-11a1 1 0 0 1 1-1ZM3.5 6.5 12 13l8.5-6.5",
    "merge": "M6 3.5a2 2 0 1 1 0 4 2 2 0 0 1 0-4ZM6 16.5a2 2 0 1 1 0 4 2 2 0 0 1 0-4ZM18 16.5a2 2 0 1 1 0 4 2 2 0 0 1 0-4ZM6 7.5v9M6 7.5c0 4.5 4 5.5 12 9",
}


def esc(value):
    return escape(str(value), quote=True)


def load_icons():
    data = json.loads((ROOT / "assets" / "vendor" / "simple-icons.json").read_text(encoding="utf-8"))
    return data["icons"]


def mono_width(text, size):
    return len(text) * size * MONO_ADVANCE


def glyph(name, x, y, size, color, width=1.8, opacity=1):
    scale = size / 24
    return (
        f'<path d="{GLYPHS[name]}" transform="translate({x:.1f} {y:.1f}) scale({scale:.4f})" '
        f'fill="none" stroke="{color}" stroke-width="{width}" stroke-linecap="round" '
        f'stroke-linejoin="round" opacity="{opacity}"/>'
    )


def brand(path, x, y, size, color):
    return f'<path d="{path}" transform="translate({x:.1f} {y:.1f}) scale({size / 24:.4f})" fill="{color}"/>'


def card_frame(width, height, t, uid, radius=16):
    return (
        f'<defs><linearGradient id="{uid}-bg" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{t["bg_top"]}"/><stop offset="1" stop-color="{t["bg_bottom"]}"/>'
        f'</linearGradient></defs>'
        f'<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="{radius}" '
        f'fill="url(#{uid}-bg)" stroke="{t["border"]}"/>'
    )


def chip(x, y, text, color, t, size=10.5, anchor="start", fill_opacity=None):
    """Monospace pill; returns (svg, width). y is the vertical centre."""
    width = mono_width(text, size) + 16
    left = x - width if anchor == "end" else x
    return (
        f'<rect x="{left:.1f}" y="{y - 10:.1f}" width="{width:.1f}" height="20" rx="10" fill="{color}" '
        f'fill-opacity="{t["tile"] if fill_opacity is None else fill_opacity}"/>'
        f'<text x="{left + 8:.1f}" y="{y + 3.6:.1f}" font-family="{MONO}" font-size="{size}" fill="{color}">{esc(text)}</text>',
        width,
    )


def document(width, height, title, desc, body, style=""):
    if "<animate" in body:
        # SMIL cannot be disabled by CSS animation:none. Switch to a static copy.
        still = ET.fromstring(f"<g>{body}</g>")
        for parent in still.iter():
            for child in list(parent):
                if child.tag in {"animate", "animateMotion", "animateTransform"}:
                    parent.remove(child)
        static = ET.tostring(still, encoding="unicode")
        static = re.sub(r'id="([^"]+)"', r'id="\1-still"', static)
        static = re.sub(r'url\(#([^)]+)\)', r'url(#\1-still)', static)
        body = f'<g class="motion">{body}</g><g class="still">{static}</g>'
        style += ".still{display:none}@media(prefers-reduced-motion:reduce){.motion{display:none}.still{display:inline}}"
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">'
        f'<title id="title">{esc(title)}</title><desc id="desc">{esc(desc)}</desc>'
        + (f"<style>{style}</style>" if style else "")
        + body + "</svg>\n"
    )
    ET.fromstring(svg)  # refuse to emit malformed XML
    return svg


def write_assets(output, assets, check=False):
    """Replace each complete file atomically; the workflow publishes one Git commit."""
    if check:
        return sorted(
            name for name, content in assets.items()
            if not (output / name).is_file() or (output / name).read_text(encoding="utf-8") != content
        )
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".staging-", dir=output.parent) as staging:
        for name, content in assets.items():
            Path(staging, name).write_text(content, encoding="utf-8")
        for name in assets:
            os.replace(Path(staging, name), output / name)
    return []
