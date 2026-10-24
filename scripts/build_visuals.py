#!/usr/bin/env python3
"""Build the static profile artwork (typing header, tech-stack grid, contact badges).

Runs offline from checked-in sources. `--check` exits non-zero when the committed SVGs
differ from what this script would produce, so stale artwork is caught in CI.
"""

import argparse
import sys

from profile_svg import (
    MONO, ROOT, SANS, THEMES, badge, brand, document, esc, glyph, load_icons, mono_width,
    write_assets,
)

OUTPUT = ROOT / "assets" / "profile"

# (theme colour, typed line). The first line is what non-animating renderers show.
TYPED = [
    ("text", "Software Engineering Undergraduate @ NWAFU"),
    ("green", "Building open-source campus tools"),
    ("violet", "Wiring LLM agents into dev workflows"),
    ("blue", "Learning data structures & databases"),
    ("amber", "Exploring Linux, networks & systems"),
]

BUILD = [  # languages and tools used in real projects
    ("c", "C"), ("cplusplus", "C++"), ("python", "Python"), ("javascript", "JavaScript"),
    ("typescript", "TypeScript"), ("go", "Go"), ("gnubash", "Bash"), ("nodedotjs", "Node.js"),
    ("docker", "Docker"), ("linux", "Linux"), ("openwrt", "OpenWrt"), ("claude", "Claude Code"),
]
LEARNING = [  # coursework, kept visually separate from project experience
    ("openjdk", "Java"), ("database", "SQL"), ("database", "Oracle"), ("tree", "Data structures"),
]
SETUP = [("laptop", "MacBook Air"), ("desktop", "Win 11 / Hackintosh PC"),
         ("router", "Cudy TR3000"), ("nas", "OECT NAS")]
LEARNING_TINT = {"SQL": "blue", "Oracle": "amber", "Data structures": "violet"}

# Brand colours that lack contrast on one theme get a readable stand-in.
ICON_COLOURS = {
    "light": {"c": "#5a6f8f", "javascript": "#a68c00", "linux": "#a87f00", "openwrt": "#0089ad",
              "go": "#007d9c", "openjdk": "#1f2328"},
    "dark": {"cplusplus": "#5b9be0", "python": "#5b9bd5", "typescript": "#5a9be6", "openjdk": "#e6edf3"},
}
TILE = {"light": "#f2f4f7", "dark": "#1c2230"}


class Timeline:
    """Discrete SMIL schedules sharing one duration, so every layer stays in sync."""

    def __init__(self, duration):
        self.duration = duration

    def discrete(self, attribute, events):
        points = {}
        for time, value in events:
            points[round(time / self.duration, 4)] = value
        times = sorted(points)
        if times[0] != 0:
            raise ValueError("schedule must start at t=0")
        return (
            f'<animate attributeName="{attribute}" dur="{self.duration:.2f}s" repeatCount="indefinite" '
            f'calcMode="discrete" keyTimes="{";".join(f"{t:g}" for t in times)}" '
            f'values="{";".join(str(points[t]) for t in times)}"/>'
        )


def header(theme):
    """Centered greeting with a typing line, transparent so it sits on the page itself."""
    t = THEMES[theme]
    width, height, centre = 680, 116, 340
    size, cw, base_y = 22, 13.2, 96          # monospace size and pinned per-glyph advance
    lead, type_step, hold, erase_step, gap = 0.5, 0.065, 2.0, 0.025, 0.4

    windows, clock = [], lead
    for _, line in TYPED:
        typed = clock + len(line) * type_step
        held = typed + hold
        erased = held + len(line) * erase_step
        windows.append((clock, typed, held, erased))
        clock = erased + gap
    tl = Timeline(clock)
    starts = [centre - (len(line) * cw + 14) / 2 for _, line in TYPED]
    colours = [t[key] for key, _ in TYPED]
    accent = [t["green"]] + colours[1:]       # cursor colour; identity line uses green

    parts = [
        '<defs><linearGradient id="name" x1="0" x2="1">'
        f'<stop offset="0" stop-color="{t["green"]}"/><stop offset="1" stop-color="{t["blue"]}"/>'
        '</linearGradient></defs>',
        f'<text x="{centre}" y="50" text-anchor="middle" font-family="{SANS}" font-size="36" font-weight="700" '
        f'letter-spacing="-.5" fill="{t["text"]}">Hi there, I’m <tspan fill="url(#name)">MaJianyu</tspan> 👋</text>',
    ]
    # Reduced-motion visitors get the first line as plain text instead of the typewriter.
    first_line = TYPED[0][1]
    first_xs = " ".join(f"{starts[0] + i * cw:.1f}" for i in range(len(first_line)))
    parts.append(f'<text class="still" x="{first_xs}" y="{base_y}" font-family="{MONO}" font-size="{size}" '
                 f'fill="{colours[0]}">{esc(first_line)}</text><g class="typing">')
    cursor_events = [(0, starts[0])]
    for index, (_, line) in enumerate(TYPED):
        start, _, held, erased = windows[index]
        x0, n = starts[index], len(line)
        width_events = [(0, 0)]
        for k in range(1, n + 1):
            width_events.append((start + k * type_step, k * cw))
            cursor_events.append((start + k * type_step, x0 + k * cw))
            width_events.append((held + k * erase_step, (n - k) * cw))
            cursor_events.append((held + k * erase_step, x0 + (n - k) * cw))
        cursor_events.append((erased + 0.001, starts[(index + 1) % len(TYPED)]))
        static = n * cw if index == 0 else 0
        xs = " ".join(f"{x0 + i * cw:.1f}" for i in range(n))
        parts.append(
            f'<clipPath id="line{index}"><rect x="{x0 - 1:.1f}" y="{base_y - 25}" width="{static:g}" height="34">'
            + tl.discrete("width", width_events) + '</rect></clipPath>'
            f'<text x="{xs}" y="{base_y}" font-family="{MONO}" font-size="{size}" fill="{colours[index]}" '
            f'clip-path="url(#line{index})">{esc(line)}</text>'
        )
    colour_events = [(0, accent[0])] + [(w[0], accent[i]) for i, w in enumerate(windows)]
    first_end = starts[0] + len(TYPED[0][1]) * cw
    parts.append(
        f'<rect x="{first_end + 3:.1f}" y="{base_y - 18}" width="11" height="23" rx="1.5" fill="{accent[0]}">'
        + tl.discrete("x", [(time, f"{x + 3:.1f}") for time, x in cursor_events])
        + tl.discrete("fill", colour_events)
        + '<animate attributeName="opacity" values="1;0" keyTimes="0;.5" dur="1s" calcMode="discrete" repeatCount="indefinite"/>'
        '</rect></g>'
    )
    style = ".still{display:none}@media (prefers-reduced-motion:reduce){.typing{display:none}.still{display:inline}}"
    desc = "Hi there, I'm MaJianyu. A typing line cycles through: " + "; ".join(line for _, line in TYPED) + "."
    return document(width, height, "Hi there, I'm MaJianyu", desc, "".join(parts), style)


def techstack(theme):
    """Skill-icon grid: project languages first, coursework and desk setup below."""
    t = THEMES[theme]
    icons = load_icons()
    tile, pitch, per_row = 48, 66, 6
    gutter, margin = 28, 10                  # space from the floated text / for edge labels
    grid_w = pitch * (per_row - 1) + tile

    def label(y, text):
        return (f'<text x="0" y="{y}" font-family="{MONO}" font-size="10.5" letter-spacing="1.2" '
                f'fill="{t["faint"]}">{esc(text)}</text>')

    def tiles(items, top):
        out = []
        for i, (name, text) in enumerate(items):
            x, y = (i % per_row) * pitch, top + (i // per_row) * 78
            out.append(f'<rect x="{x}" y="{y}" width="{tile}" height="{tile}" rx="12" fill="{TILE[theme]}" '
                       f'stroke="{t["border"]}" stroke-opacity=".6"/>')
            if name in icons:
                colour = ICON_COLOURS[theme].get(name, icons[name]["hex"])
                out.append(brand(icons[name]["path"], x + 11, y + 11, 26, colour))
            else:
                out.append(glyph(name, x + 10, y + 10, 28, t[LEARNING_TINT[text]], width=1.7))
            out.append(f'<text x="{x + tile / 2}" y="{y + tile + 16}" text-anchor="middle" font-family="{SANS}" '
                       f'font-size="11" fill="{t["muted"]}">{esc(text)}</text>')
        return out

    def chips(items, top):
        out, x, y = [], 0.0, top
        for name, text in items:
            w = 34 + mono_width(text, 10.5) + 12
            if x + w > grid_w:
                x, y = 0.0, y + 32
            out.append(f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="26" rx="13" fill="{TILE[theme]}" '
                       f'stroke="{t["border"]}" stroke-opacity=".6"/>'
                       + glyph(name, x + 11, y + 5, 16, t["muted"], width=1.8)
                       + f'<text x="{x + 34:.1f}" y="{y + 17}" font-family="{MONO}" font-size="10.5" '
                         f'fill="{t["muted"]}">{esc(text)}</text>')
            x += w + 8
        return out, y + 26

    rows = -(-len(BUILD) // per_row)
    learn_top = 26 + rows * 78 + 26
    setup_top = learn_top + 78 + 26
    parts = [label(14, "BUILD WITH")] + tiles(BUILD, 26)
    parts += [label(learn_top - 12, "LEARNING IN CLASS")] + tiles(LEARNING, learn_top)
    setup, bottom = chips(SETUP, setup_top)
    parts += [label(setup_top - 12, "DESK SETUP")] + setup
    body = f'<g transform="translate({gutter} 1)">' + "".join(parts) + "</g>"
    desc = ("Build with: " + ", ".join(text for _, text in BUILD)
            + ". Learning in class: " + ", ".join(text for _, text in LEARNING)
            + ". Desk setup: " + ", ".join(text for _, text in SETUP) + ".")
    return document(gutter + grid_w + margin, bottom + 4, "Tech stack and setup", desc, body)


def build():
    assets = {}
    for theme in THEMES:
        assets[f"header-{theme}.svg"] = header(theme)
        assets[f"techstack-{theme}.svg"] = techstack(theme)
    assets["badge-website.svg"] = badge("web", "mjy.js.org", "globe", "#0f8a5f")
    assets["badge-email.svg"] = badge("mail", "mjy20070413@gmail.com", "mail", "#2563eb")
    return assets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if committed SVGs are stale")
    args = parser.parse_args()
    assets = build()
    if args.check:
        stale = write_assets(OUTPUT, assets, check=True)
        extra = sorted(p.name for p in OUTPUT.glob("*.svg") if p.name not in assets)
        if stale or extra:
            sys.exit(f"Profile artwork is stale; run scripts/build_visuals.py ({', '.join(stale + extra)})")
        print(f"{len(assets)} profile SVGs match their source")
        return
    for old in OUTPUT.glob("*.svg"):
        if old.name not in assets:
            old.unlink()
    write_assets(OUTPUT, assets)
    print(f"Wrote {len(assets)} profile SVGs to {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
