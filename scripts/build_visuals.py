#!/usr/bin/env python3
"""Build the static profile artwork (hero, cards, badges) from checked-in sources.

Runs offline. `--check` exits non-zero when committed SVGs differ from this source,
so the workflow catches edits that were never regenerated.
"""

import argparse
import sys

from profile_svg import (
    MONO, ROOT, SANS, THEMES, brand, card_frame, chip, document, esc, glyph, load_icons,
    mono_width, write_assets,
)

OUTPUT = ROOT / "assets" / "profile"
SIDE_H = 360  # focus and toolkit cards share a row, so they share a height
CARD_W = 416  # two cards + inline gap fit GitHub's 846px profile column; they stack below that

# --------------------------------------------------------------------------- content
DIRECTIONS = [  # (colour, glyph, motif label, typed line, focus title, focus detail)
    ("green", "code", "open-source", "building campus tools in the open",
     "Open source", "Campus tools and practical software"),
    ("violet", "sparkle", "llm-agents", "wiring LLM agents into dev workflows",
     "LLMs & agents", "Claude Code, Skills, workflow automation"),
    ("blue", "tree", "cs-core", "learning data structures & databases",
     "Computer science", "Data structures, databases, Java"),
    ("amber", "terminal", "systems", "exploring Linux, networks & systems",
     "Systems & networking", "Linux, networks, OS, hardware"),
]

PROJECTS = [
    {
        "name": "nwafu-bksxk", "colour": "green", "glyph": "calendar",
        "subtitle": "Academic assistant for NWAFU",
        "lines": ["Timetable, grades, exams, free rooms and course",
                  "selection, plus a seat monitor, on-device OCR",
                  "and nwafu-connect embedded through Go FFI."],
        "stack": "Dart · Flutter · Riverpod", "platform": "mobile · desktop · web",
    },
    {
        "name": "nwafu-connect", "colour": "amber", "glyph": "shield", "fork": True,
        "subtitle": "Unofficial aTrust VPN client · Go",
        "lines": ["Reaches NWAFU campus resources over aTrust:",
                  "SOCKS5/HTTP proxies, LDAP+TOTP and WeCom login,",
                  "a managed browser mode and a desktop tray app."],
        "stack": "Go · Fyne · Docker", "platform": "macOS · Windows · Linux",
    },
    {
        "name": "QuotaPeek", "colour": "violet", "glyph": "gauge",
        "subtitle": "Menu-bar quota viewer",
        "lines": ["Shows 5-hour and 7-day usage from VM2API",
                  "or endpoints matching its /v1/usage schema,",
                  "with profiles, alerts and Keychain-held keys."],
        "stack": "Swift · SwiftUI · AppKit", "platform": "macOS 14+",
    },
    {
        "name": "smart-srun", "colour": "blue", "glyph": "wifi", "fork": True,
        "subtitle": "SRun campus login on OpenWrt",
        "lines": ["Auto-login with reconnects, multiple accounts",
                  "and scheduled hotspot switching. I fixed radio",
                  "detection, portal fallback and daemon status."],
        "stack": "OpenWrt · LuCI", "platform": "3 PRs merged upstream",
    },
]

BUILD = [  # (icon, label) — languages and tools used in real projects
    ("c", "C"), ("cplusplus", "C++"), ("python", "Python"), ("javascript", "JavaScript"),
    ("typescript", "TypeScript"), ("go", "Go"), ("gnubash", "Bash"), ("nodedotjs", "Node.js"),
    ("docker", "Docker"), ("linux", "Linux"), ("openwrt", "OpenWrt"), ("claude", "Claude Code"),
]
STUDY = [("openjdk", "Java"), ("database", "SQL"), ("database", "Oracle"), ("tree", "Data structures")]
SETUP = [("laptop", "MacBook Air"), ("desktop", "Win 11 + macOS desktop"),
         ("router", "Cudy TR3000"), ("nas", "OECT NAS")]

# Brand colours that lack contrast on one theme get a readable stand-in.
ICON_COLOURS = {
    "light": {"c": "#5a6f8f", "javascript": "#a68c00", "linux": "#a87f00", "openwrt": "#0089ad",
              "go": "#007d9c", "openjdk": "#1f2328"},
    "dark": {"cplusplus": "#5b9be0", "python": "#5b9bd5", "typescript": "#5a9be6", "openjdk": "#e6edf3"},
}


def icon_colour(name, hexcode, theme):
    return ICON_COLOURS[theme].get(name, hexcode)


# --------------------------------------------------------------------------- hero
class Timeline:
    """Discrete SMIL schedules that share one duration, so every layer stays in sync."""

    def __init__(self, duration):
        self.duration = duration

    def discrete(self, attribute, events, extra=""):
        points = {}
        for time, value in events:
            points[round(time / self.duration, 4)] = value
        times = sorted(points)
        if times[0] != 0:
            raise ValueError("schedule must start at t=0")
        return (
            f'<animate attributeName="{attribute}" dur="{self.duration:.2f}s" repeatCount="indefinite" '
            f'calcMode="discrete" keyTimes="{";".join(f"{t:g}" for t in times)}" '
            f'values="{";".join(str(points[t]) for t in times)}"{extra}/>'
        )


def hero(theme):
    t = THEMES[theme]
    width, height = 846, 228
    size, cw = 22, 13.2                      # mono size and pinned per-glyph advance
    prompt_x, text_x, base_y = 48, 48 + 2 * cw, 180
    lead, type_step, hold, erase_step, gap = 0.6, 0.07, 1.9, 0.028, 0.45

    # schedule
    windows, clock = [], lead
    for _, _, _, line, _, _ in DIRECTIONS:
        typed = clock + len(line) * type_step
        held = typed + hold
        erased = held + len(line) * erase_step
        windows.append((clock, typed, held, erased))
        clock = erased + gap
    tl = Timeline(clock)

    cx, cy, half = 714, 114, 30
    nodes = [(626, 58), (802, 58), (626, 170), (802, 170)]
    order = [0, 1, 2, 3]  # DIRECTIONS index for each node

    parts = [card_frame(width, height, t, f"hero-{theme}", radius=20)]
    parts.append(
        '<defs>'
        f'<pattern id="dots" width="16" height="16" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1" fill="{t["faint"]}"/></pattern>'
        '<linearGradient id="fade" x1="0" x2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".45" stop-color="#fff" stop-opacity=".55"/><stop offset="1" stop-color="#fff" stop-opacity=".9"/></linearGradient>'
        f'<mask id="dotmask"><rect x="480" y="0" width="{width - 480}" height="{height}" fill="url(#fade)"/></mask>'
        f'<radialGradient id="glow"><stop offset="0" stop-color="{t["green"]}" stop-opacity="{t["glow"] * 2}"/><stop offset="1" stop-color="{t["green"]}" stop-opacity="0"/></radialGradient>'
        '</defs>'
        f'<rect x="480" y="1" width="{width - 482}" height="{height - 2}" fill="url(#dots)" mask="url(#dotmask)" opacity=".55"/>'
        f'<circle cx="{cx}" cy="{cy}" r="120" fill="url(#glow)"/>'
    )

    # left: greeting, name, typing line
    parts.append(
        f'<text x="48" y="70" font-family="{SANS}" font-size="18" fill="{t["muted"]}">Hi, I’m</text>'
        f'<text x="46" y="130" font-family="{SANS}" font-size="58" font-weight="700" letter-spacing="-1" fill="{t["text"]}">MaJianyu</text>'
    )
    colours = [t[d[0]] for d in DIRECTIONS]
    colour_events = [(0, colours[0])] + [(w[0], colours[i]) for i, w in enumerate(windows)]
    parts.append(
        f'<text x="{prompt_x}" y="{base_y}" font-family="{MONO}" font-size="{size}" font-weight="700" fill="{colours[0]}">$'
        + tl.discrete("fill", colour_events) + '</text>'
    )
    cursor_events = [(0, text_x)]
    for index, (_, _, _, line, _, _) in enumerate(DIRECTIONS):
        start, typed, held, erased = windows[index]
        width_events = [(0, 0)]
        for k in range(1, len(line) + 1):
            width_events.append((start + k * type_step, k * cw))
            cursor_events.append((start + k * type_step, text_x + k * cw))
        for k in range(1, len(line) + 1):
            width_events.append((held + k * erase_step, (len(line) - k) * cw))
            cursor_events.append((held + k * erase_step, text_x + (len(line) - k) * cw))
        static = len(line) * cw if index == 0 else 0  # what non-animating renderers show
        xs = " ".join(f"{text_x + i * cw:g}" for i in range(len(line)))
        parts.append(
            f'<clipPath id="type{index}"><rect x="{text_x - 1}" y="{base_y - 24}" width="{static:g}" height="34">'
            + tl.discrete("width", width_events) + '</rect></clipPath>'
            f'<text x="{xs}" y="{base_y}" font-family="{MONO}" font-size="{size}" fill="{t["text"]}" clip-path="url(#type{index})">{esc(line)}</text>'
        )
    first = len(DIRECTIONS[0][3]) * cw
    parts.append(
        f'<rect x="{text_x + first + 2:g}" y="{base_y - 18}" width="11" height="23" rx="1.5" fill="{colours[0]}" opacity=".85">'
        + tl.discrete("x", [(time, f"{x + 2:g}") for time, x in cursor_events])
        + tl.discrete("fill", colour_events)
        + '<animate attributeName="opacity" values=".9;0" keyTimes="0;.5" dur="1s" calcMode="discrete" repeatCount="indefinite"/>'
        + '</rect>'
    )

    # right: a chip wired to the four directions; the active trace lights up with the typed line
    traces = []
    for slot, (nx, ny) in enumerate(nodes):
        sx = 1 if nx > cx else -1
        px = cx + sx * half
        py = cy - 14 if ny < cy else cy + 14
        h1 = px + sx * 18
        traces.append(f"M{px} {py}H{h1}L{h1 + sx * abs(ny - py)} {ny}")
    for slot, path in enumerate(traces):
        index = order[slot]
        start, typed, held, erased = windows[index]
        colour = colours[index]
        on = "1" if index == 0 else "0"
        parts.append(f'<path d="{path}" fill="none" stroke="{t["border"]}" stroke-width="2"/>')
        parts.append(
            f'<path d="{path}" fill="none" stroke="{colour}" stroke-width="2" stroke-linecap="round" opacity="{on}">'
            + tl.discrete("opacity", [(0, 0), (start, 1), (erased, 0)]) + '</path>'
        )
        a, b = round(start / tl.duration, 4), round(typed / tl.duration, 4)
        parts.append(
            f'<circle r="4" fill="{colour}" opacity="0">'
            f'<animateMotion path="{path}" dur="{tl.duration:.2f}s" repeatCount="indefinite" calcMode="linear" '
            f'keyPoints="0;0;1;1" keyTimes="0;{a:g};{b:g};1"/>'
            + tl.discrete("opacity", [(0, 0), (start, 1), (typed, 0)]) + '</circle>'
        )
    for slot, (nx, ny) in enumerate(nodes):
        index = order[slot]
        colour_key, glyph_name, label = DIRECTIONS[index][:3]
        start, typed, held, erased = windows[index]
        colour = t[colour_key]
        on = "1" if index == 0 else "0"
        label_y = ny + 38
        parts.append(
            f'<circle cx="{nx}" cy="{ny}" r="31" fill="{colour}" opacity="{float(on) * 0.18:g}">'
            + tl.discrete("opacity", [(0, 0), (typed, 0.18), (erased, 0)]) + '</circle>'
            f'<circle cx="{nx}" cy="{ny}" r="22" fill="{t["bg_top"]}" stroke="{t["border"]}" stroke-width="1.5"/>'
            f'<circle cx="{nx}" cy="{ny}" r="22" fill="none" stroke="{colour}" stroke-width="2" opacity="{on}">'
            + tl.discrete("opacity", [(0, 0), (typed, 1), (erased, 0)]) + '</circle>'
            + glyph(glyph_name, nx - 10, ny - 10, 20, colour)
            + f'<text x="{nx}" y="{label_y}" text-anchor="middle" font-family="{MONO}" font-size="10.5" fill="{t["muted"]}">{label}</text>'
        )
    pins = "".join(
        f'<path d="M{cx + d} {cy - half}v-7M{cx + d} {cy + half}v7" stroke="{t["faint"]}" stroke-width="2" stroke-linecap="round"/>'
        for d in (-15, 0, 15)
    )
    parts.append(
        pins
        + f'<rect x="{cx - half}" y="{cy - half}" width="{half * 2}" height="{half * 2}" rx="10" fill="{t["bg_top"]}" stroke="{t["faint"]}" stroke-width="1.5"/>'
        + f'<rect x="{cx - half + 7}" y="{cy - half + 7}" width="{half * 2 - 14}" height="{half * 2 - 14}" rx="5" fill="none" stroke="{t["border"]}"/>'
        + f'<text x="{cx}" y="{cy + 7}" text-anchor="middle" font-family="{MONO}" font-size="19" font-weight="700" fill="{t["text"]}">mj</text>'
    )
    desc = ("Hi, I'm MaJianyu. An animated terminal line cycles through what I'm working on: "
            + "; ".join(d[3] for d in DIRECTIONS) + ".")
    return document(width, height, "MaJianyu", desc, "".join(parts))


# --------------------------------------------------------------------------- cards
def section_label(x, y, text, t):
    return (f'<text x="{x}" y="{y}" font-family="{MONO}" font-size="10.5" letter-spacing="1.2" '
            f'fill="{t["faint"]}">{esc(text.upper())}</text>')


def card_title(text, t, right=""):
    out = f'<text x="24" y="40" font-family="{SANS}" font-size="16" font-weight="600" fill="{t["text"]}">{esc(text)}</text>'
    if right:
        out += (f'<text x="{CARD_W - 24}" y="40" text-anchor="end" font-family="{MONO}" font-size="10.5" '
                f'fill="{t["faint"]}">{esc(right)}</text>')
    return out


def focus_card(theme):
    t = THEMES[theme]
    height = SIDE_H
    parts = [card_frame(CARD_W, height, t, f"focus-{theme}"), card_title("Currently exploring", t)]
    for i, (colour_key, glyph_name, _, _, title, detail) in enumerate(DIRECTIONS):
        y = 70 + i * 70
        colour = t[colour_key]
        parts.append(
            f'<rect x="24" y="{y}" width="40" height="40" rx="11" fill="{colour}" fill-opacity="{t["tile"]}"/>'
            + glyph(glyph_name, 34, y + 10, 20, colour)
            + f'<text x="80" y="{y + 17}" font-family="{SANS}" font-size="14.5" font-weight="600" fill="{t["text"]}">{esc(title)}</text>'
            + f'<text x="80" y="{y + 35}" font-family="{SANS}" font-size="12.5" fill="{t["muted"]}">{esc(detail)}</text>'
        )
        if i < len(DIRECTIONS) - 1:
            parts.append(f'<path d="M80 {y + 55}H{CARD_W - 24}" stroke="{t["grid"]}"/>')
    desc = "Currently exploring: " + "; ".join(f"{d[4]}: {d[5]}" for d in DIRECTIONS) + "."
    return document(CARD_W, height, "Currently exploring", desc, "".join(parts))


def flow_chips(items, top, t, icons, colour):
    """Lay out icon chips left to right, wrapping inside the card; returns (svg, bottom)."""
    x, y, parts = 24, top, []
    for icon, label in items:
        width = 30 + mono_width(label, 10.5) + 10
        if x + width > CARD_W - 24:
            x, y = 24, y + 28
        parts.append(f'<rect x="{x:.1f}" y="{y}" width="{width:.1f}" height="22" rx="11" fill="none" stroke="{t["border"]}"/>')
        if icon in icons:
            parts.append(brand(icons[icon]["path"], x + 9, y + 4, 14, icon_colour(icon, icons[icon]["hex"], theme_of(t))))
        else:
            parts.append(glyph(icon, x + 8, y + 3, 16, colour))
        parts.append(f'<text x="{x + 30:.1f}" y="{y + 15}" font-family="{MONO}" font-size="10.5" fill="{t["muted"]}">{esc(label)}</text>')
        x += width + 6
    return "".join(parts), y + 22


def theme_of(t):
    return next(name for name, values in THEMES.items() if values is t)


def toolkit_card(theme):
    t = THEMES[theme]
    icons = load_icons()
    height = SIDE_H
    parts = [card_frame(CARD_W, height, t, f"tools-{theme}"), card_title("Toolkit", t)]
    parts.append(section_label(24, 66, "Used in projects", t))
    pitch = (CARD_W - 48 - 44) / 5
    for i, (name, label) in enumerate(BUILD):
        col, row = i % 6, i // 6
        x, y = 24 + col * pitch, 76 + row * 66
        colour = icon_colour(name, icons[name]["hex"], theme)
        parts.append(
            f'<rect x="{x:.1f}" y="{y}" width="44" height="40" rx="10" fill="{colour}" fill-opacity="{t["tile"]}"/>'
            + brand(icons[name]["path"], x + 11, y + 9, 22, colour)
            + f'<text x="{x + 22:.1f}" y="{y + 56}" text-anchor="middle" font-family="{SANS}" font-size="11" fill="{t["muted"]}">{esc(label)}</text>'
        )
    parts.append(section_label(24, 222, "Coursework", t))
    chips, _ = flow_chips(STUDY, 232, t, icons, t["blue"])
    parts.append(chips)
    parts.append(section_label(24, 282, "Setup", t))
    chips, bottom = flow_chips(SETUP, 290, t, icons, t["muted"])
    parts.append(chips)
    desc = ("Toolkit. Used in projects: " + ", ".join(label for _, label in BUILD)
            + ". Learning through coursework: " + ", ".join(label for _, label in STUDY)
            + ". Setup: " + ", ".join(label for _, label in SETUP) + ".")
    if bottom > height - 16:
        raise ValueError("toolkit card overflow")
    return document(CARD_W, height, "Toolkit", desc, "".join(parts))


def project_card(project, theme):
    t = THEMES[theme]
    height = 196
    colour = t[project["colour"]]
    parts = [card_frame(CARD_W, height, t, f"p-{theme}")]
    # oversized watermark glyph, tucked into the corner and clipped to the card
    parts.append(
        f'<clipPath id="clip"><rect x="1" y="1" width="{CARD_W - 2}" height="{height - 2}" rx="15"/></clipPath>'
        f'<g clip-path="url(#clip)">{glyph(project["glyph"], CARD_W - 92, 4, 116, colour, width=1.1, opacity=0.05)}</g>'
    )
    parts.append(
        f'<rect x="22" y="22" width="40" height="40" rx="11" fill="{colour}" fill-opacity="{t["tile"]}"/>'
        + glyph(project["glyph"], 32, 32, 20, colour)
        + f'<text x="76" y="39" font-family="{SANS}" font-size="17" font-weight="600" fill="{t["text"]}">{esc(project["name"])}</text>'
        + f'<text x="76" y="57" font-family="{SANS}" font-size="12.5" fill="{t["muted"]}">{esc(project["subtitle"])}</text>'
    )
    if project.get("fork"):
        svg, _ = chip(CARD_W - 22, 32, "fork", t["amber"], t, anchor="end")
        parts.append(svg)
    for i, line in enumerate(project["lines"]):
        parts.append(f'<text x="22" y="{94 + i * 20}" font-family="{SANS}" font-size="13" fill="{t["text"]}" opacity=".88">{esc(line)}</text>')
    parts.append(f'<path d="M22 150H{CARD_W - 22}" stroke="{t["grid"]}"/>')
    parts.append(
        f'<circle cx="27" cy="171" r="4" fill="{colour}"/>'
        f'<text x="38" y="175" font-family="{MONO}" font-size="11" fill="{t["muted"]}">{esc(project["stack"])}</text>'
        f'<text x="{CARD_W - 22}" y="175" text-anchor="end" font-family="{MONO}" font-size="11" fill="{t["faint"]}">{esc(project["platform"])}</text>'
    )
    desc = (f'{project["name"]}{" (fork)" if project.get("fork") else ""}: {project["subtitle"]}. '
            + " ".join(project["lines"]) + f' {project["stack"]}. {project["platform"]}.')
    return document(CARD_W, height, project["name"], desc, "".join(parts))


def badge(label, value, glyph_name, colour):
    left = 30 + mono_width(label, 11) + 10
    right = mono_width(value, 11) + 20
    width = round(left + right)
    body = (
        '<clipPath id="r"><rect width="100%" height="28" rx="7"/></clipPath><g clip-path="url(#r)">'
        f'<rect width="{left:.1f}" height="28" fill="#24292f"/><rect x="{left:.1f}" width="{right:.1f}" height="28" fill="{colour}"/></g>'
        + glyph(glyph_name, 10, 7, 14, "#ffffff", width=2)
        + f'<text x="30" y="18" font-family="{MONO}" font-size="11" fill="#d0d7de">{esc(label)}</text>'
        + f'<text x="{left + 10:.1f}" y="18" font-family="{MONO}" font-size="11" font-weight="600" fill="#ffffff">{esc(value)}</text>'
    )
    return document(width, 28, f"{label}: {value}", f"{label}: {value}", body)


def build():
    assets = {}
    for theme in THEMES:
        assets[f"hero-{theme}.svg"] = hero(theme)
        assets[f"focus-{theme}.svg"] = focus_card(theme)
        assets[f"toolkit-{theme}.svg"] = toolkit_card(theme)
        for project in PROJECTS:
            assets[f"project-{project['name'].lower()}-{theme}.svg"] = project_card(project, theme)
    assets["badge-website.svg"] = badge("web", "mjy.js.org", "globe", "#0f8a5f")
    assets["badge-email.svg"] = badge("mail", "mjy20070413@gmail.com", "mail", "#2563eb")
    return assets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if committed SVGs are stale")
    args = parser.parse_args()
    assets = build()
    stale = write_assets(OUTPUT, assets, check=args.check)
    if args.check:
        extra = sorted(p.name for p in OUTPUT.glob("*.svg") if p.name not in assets)
        if stale or extra:
            sys.exit(f"Profile artwork is stale; run scripts/build_visuals.py ({', '.join(stale + extra)})")
        print(f"{len(assets)} profile SVGs match their source")
    else:
        print(f"Wrote {len(assets)} profile SVGs to {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
