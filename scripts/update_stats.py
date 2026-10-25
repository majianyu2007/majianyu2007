#!/usr/bin/env python3
"""Render the profile's GitHub statistics cards from public GitHub data.

Runs in GitHub Actions with the built-in GITHUB_TOKEN; no personal access token.
Everything is fetched, validated and rendered in memory first, and files are only
replaced when all of that succeeded, so a failed run leaves the previous images intact.
"""

import argparse
from collections import Counter
from datetime import date, datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
from urllib.request import Request, urlopen

from profile_svg import (
    MONO, ROOT, SANS, THEMES, badge, card_frame, document, esc, glyph, write_assets,
)

USER = "majianyu2007"
GRAPHQL = "https://api.github.com/graphql"
CARD_W, CARD_H = 416, 200
# Build-system and docs-format entries say little about what someone writes.
IGNORED_LANGUAGES = {"CMake", "Makefile", "Dockerfile", "Batchfile", "MDX", "Procfile"}

QUERY = """
query($login: String!, $cursor: String) {
  user(login: $login) {
    followers { totalCount }
    pullRequests { totalCount }
    issues { totalCount }
    repositories(first: 100, after: $cursor, ownerAffiliations: OWNER, privacy: PUBLIC,
                 isFork: false, orderBy: {field: NAME, direction: ASC}) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        name isFork isPrivate stargazerCount
        languages(first: 20, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
    contributionsCollection {
      totalCommitContributions
      totalRepositoriesWithContributedCommits
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""


# --------------------------------------------------------------------------- fetching
def graphql(variables):
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise ValueError("GITHUB_TOKEN is required")
    request = Request(
        GRAPHQL,
        data=json.dumps({"query": QUERY, "variables": variables}).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                 "User-Agent": f"{USER}-profile-stats"},
    )
    with urlopen(request, timeout=30) as response:
        result = json.load(response)
    if not isinstance(result, dict) or result.get("errors") or not isinstance(result.get("data"), dict):
        raise ValueError("GraphQL query failed")
    user = result["data"].get("user")
    if not isinstance(user, dict):
        raise ValueError("user missing from response")
    return user


def fetch():
    """First page carries the profile fields; later pages only add repositories."""
    user = graphql({"login": USER, "cursor": None})
    repositories = list(user["repositories"]["nodes"])
    page = user["repositories"]["pageInfo"]
    while page["hasNextPage"]:
        more = graphql({"login": USER, "cursor": page["endCursor"]})["repositories"]
        repositories.extend(more["nodes"])
        page = more["pageInfo"]
    user["repositories"]["nodes"] = repositories
    return user


# --------------------------------------------------------------------------- summarising
def _count(value, what):
    if type(value) is not int or value < 0:
        raise ValueError(f"invalid {what}")
    return value


def summarize_languages(repositories):
    """Share of each language with every repository weighted equally.

    Weighting by raw bytes would let one repository with vendored C code outweigh
    everything else; equal weights describe what the projects are actually written in.
    """
    weights, colours, counted = Counter(), {}, 0
    for repo in repositories:
        sizes = {}
        for edge in repo["languages"]["edges"]:
            name, size = edge["node"]["name"], _count(edge["size"], "language size")
            if name in IGNORED_LANGUAGES or not size:
                continue
            sizes[name] = sizes.get(name, 0) + size
            colours[name] = edge["node"].get("color") or "#8c959f"
        total = sum(sizes.values())
        if total:
            counted += 1
            for name, size in sizes.items():
                weights[name] += size / total
    ranked = sorted(weights.items(), key=lambda kv: (-kv[1], kv[0]))
    return counted, [
        {"name": name, "color": colours[name], "share": round(100 * weight / counted, 2)}
        for name, weight in ranked
    ] if counted else []


def summarize_repositories(user):
    block = user.get("repositories") or {}
    nodes = block.get("nodes")
    if not isinstance(nodes, list) or _count(block.get("totalCount"), "repository count") != len(nodes):
        raise ValueError("incomplete repository list")
    names = set()
    for repo in nodes:
        if (
            not isinstance(repo, dict) or repo.get("isFork") is not False or repo.get("isPrivate") is not False
            or not isinstance(repo.get("name"), str) or repo["name"] in names
            or not isinstance((repo.get("languages") or {}).get("edges"), list)
        ):
            raise ValueError("unexpected repository record")
        names.add(repo["name"])
        _count(repo.get("stargazerCount"), "star count")
    counted, languages = summarize_languages(nodes)
    return {
        "repositories": len(nodes),
        "stars": sum(repo["stargazerCount"] for repo in nodes),
        "language_repositories": counted,
        "languages": languages,
    }


def _runs(days):
    """Yield (start, end, length) for every run of active days."""
    start = previous = None
    for day, count in days:
        if count and start is not None and day == previous + timedelta(days=1):
            previous = day
            continue
        if start is not None:
            yield start, previous, (previous - start).days + 1
            start = None
        if count:
            start = previous = day
    if start is not None:
        yield start, previous, (previous - start).days + 1


def summarize_calendar(collection):
    calendar = collection.get("contributionCalendar") or {}
    total, weeks = _count(calendar.get("totalContributions"), "total"), calendar.get("weeks")
    if not isinstance(weeks, list) or not 50 <= len(weeks) <= 54:
        raise ValueError("unexpected calendar shape")
    days, weekly = [], []
    for week in weeks:
        entries = week.get("contributionDays") if isinstance(week, dict) else None
        if not isinstance(entries, list) or not 1 <= len(entries) <= 7:
            raise ValueError("invalid calendar week")
        counts = [_count(entry.get("contributionCount"), "daily count") for entry in entries]
        days.extend((date.fromisoformat(entry["date"]), count) for entry, count in zip(entries, counts))
        weekly.append({"start": entries[0]["date"], "count": sum(counts)})
    dates = [day for day, _ in days]
    # The headline total need not equal the sum of the days: GitHub's "last year" window and the
    # calendar's day boundaries differ slightly, so only the day sequence itself is checked.
    if any(b - a != timedelta(days=1) for a, b in zip(dates, dates[1:])):
        raise ValueError("calendar days are not contiguous")

    runs = list(_runs(days))
    longest = max(runs, key=lambda run: (run[2], run[1]), default=None)
    # The current streak may end today or yesterday: today simply might not have started yet.
    current = runs[-1] if runs and runs[-1][1] >= dates[-1] - timedelta(days=1) else None

    def span(run):
        return {"length": run[2], "start": run[0].isoformat(), "end": run[1].isoformat()} if run else \
            {"length": 0, "start": None, "end": None}

    return {
        "total": total,
        "commits": _count(collection.get("totalCommitContributions"), "commits"),
        "contributed_to": _count(collection.get("totalRepositoriesWithContributedCommits"), "repositories"),
        "active_days": sum(1 for _, count in days if count),
        "first_day": dates[0].isoformat(),
        "last_day": dates[-1].isoformat(),
        "current_streak": span(current),
        "longest_streak": span(longest),
        "weeks": weekly,
    }


def summarize(user, updated):
    stats = {
        "user": USER,
        "updated": updated,
        "followers": _count((user.get("followers") or {}).get("totalCount"), "followers"),
        "pull_requests": _count((user.get("pullRequests") or {}).get("totalCount"), "pull requests"),
        "issues": _count((user.get("issues") or {}).get("totalCount"), "issues"),
    }
    stats.update(summarize_repositories(user))
    stats["contributions"] = summarize_calendar(user.get("contributionsCollection") or {})
    return stats


# --------------------------------------------------------------------------- rendering
def fmt(number):
    return f"{number:,}"


def short_date(iso, with_year=False):
    day = date.fromisoformat(iso)
    return f"{day:%b} {day.day}" + (f", {day.year}" if with_year else "")


def readable(colour, theme):
    """Lift near-black language colours on the dark theme."""
    if theme != "dark":
        return colour
    r, g, b = (int(colour[i:i + 2], 16) for i in (1, 3, 5))
    if 0.2126 * r + 0.7152 * g + 0.0722 * b > 90:
        return colour
    return "#{:02x}{:02x}{:02x}".format(*(round(c + (255 - c) * 0.45) for c in (r, g, b)))


STYLE = (
    ".draw{stroke-dasharray:1;animation:draw 1.8s cubic-bezier(.4,0,.2,1) both}"
    ".grow{animation:grow .9s cubic-bezier(.2,.7,.2,1) both;transform-box:fill-box;transform-origin:left}"
    ".fade{animation:fade 1.4s .5s ease-out both}"
    ".pulse{animation:pulse 2.2s ease-out 2s infinite;transform-box:fill-box;transform-origin:center}"
    "@keyframes draw{from{stroke-dashoffset:1}}@keyframes grow{from{transform:scaleX(0)}}"
    "@keyframes fade{from{opacity:.25}}@keyframes pulse{from{opacity:.7}to{opacity:0;transform:scale(3)}}"
    "@media (prefers-reduced-motion:reduce){.draw,.grow,.fade,.pulse{animation:none}.pulse{opacity:0}}"
)


def title(text, t, right=""):
    out = f'<text x="24" y="38" font-family="{SANS}" font-size="15" font-weight="600" fill="{t["text"]}">{esc(text)}</text>'
    if right:
        out += (f'<text x="{CARD_W - 24}" y="38" text-anchor="end" font-family="{MONO}" font-size="10" '
                f'fill="{t["faint"]}">{esc(right)}</text>')
    return out


def render_stats(stats, theme):
    t = THEMES[theme]
    c = stats["contributions"]
    rows = [
        ("star", "Stars earned", stats["stars"], t["amber"]),
        ("commit", "Commits (last year)", c["commits"], t["green"]),
        ("pull", "Pull requests", stats["pull_requests"], t["violet"]),
        ("issue", "Issues", stats["issues"], t["blue"]),
        ("repo", "Contributed to (last year)", c["contributed_to"], t["muted"]),
    ]
    parts = [card_frame(CARD_W, CARD_H, t, f"st-{theme}"), title("MaJianyu’s GitHub Stats", t)]
    for i, (icon, label, value, colour) in enumerate(rows):
        y = 70 + i * 25
        parts.append(
            glyph(icon, 24, y - 12, 15, colour, width=2)
            + f'<text x="48" y="{y}" font-family="{SANS}" font-size="12.5" fill="{t["muted"]}">{esc(label)}:</text>'
            + f'<text x="238" y="{y}" text-anchor="end" font-family="{SANS}" font-size="13" font-weight="600" fill="{t["text"]}">{fmt(value)}</text>'
        )
    days = (date.fromisoformat(c["last_day"]) - date.fromisoformat(c["first_day"])).days + 1
    ratio = c["active_days"] / days if days else 0
    cx, cy, r = 330, 108, 46
    parts.append(
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{t["grid"]}" stroke-width="7"/>'
        f'<circle class="draw" cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{t["green"]}" stroke-width="7" '
        f'stroke-linecap="round" pathLength="1" stroke-dasharray="{ratio:.3f} 1" transform="rotate(-90 {cx} {cy})" '
        f'style="stroke-dasharray:{ratio:.3f} 1"/>'
        f'<text x="{cx}" y="{cy + 2}" text-anchor="middle" font-family="{SANS}" font-size="22" font-weight="700" fill="{t["text"]}">{fmt(c["active_days"])}</text>'
        f'<text x="{cx}" y="{cy + 19}" text-anchor="middle" font-family="{SANS}" font-size="10" fill="{t["muted"]}">active days</text>'
        f'<text x="{cx}" y="{cy + r + 24}" text-anchor="middle" font-family="{MONO}" font-size="10" fill="{t["faint"]}">{round(ratio * 100)}% of the last year</text>'
    )
    desc = (f"{stats['stars']} stars earned, {c['commits']} commits in the last year, {stats['pull_requests']} pull requests, "
            f"{stats['issues']} issues, contributed to {c['contributed_to']} repositories in the last year; "
            f"active on {c['active_days']} of the last {days} days.")
    return document(CARD_W, CARD_H, "MaJianyu's GitHub Stats", desc, "".join(parts), STYLE.replace(
        "stroke-dasharray:1;", ""))


def render_languages(stats, theme):
    t = THEMES[theme]
    languages = stats["languages"]
    shown = [dict(item) for item in languages[:9]]
    rest = round(100 - sum(item["share"] for item in shown), 2)
    if len(languages) > 9 and rest > 0:
        shown.append({"name": "Other", "color": t["faint"], "share": rest})
    parts = [card_frame(CARD_W, CARD_H, t, f"lg-{theme}"),
             title("Most Used Languages", t, f"{stats['language_repositories']} repos, equal weight")]
    bar_w, x = CARD_W - 48, 24.0
    parts.append(f'<clipPath id="bar"><rect x="24" y="56" width="{bar_w}" height="10" rx="5"/></clipPath>'
                 f'<rect x="24" y="56" width="{bar_w}" height="10" rx="5" fill="{t["grid"]}"/><g clip-path="url(#bar)">')
    for i, item in enumerate(shown):
        width = bar_w * item["share"] / 100
        parts.append(f'<rect class="grow" style="animation-delay:{.15 + i * .07:.2f}s" x="{x:.1f}" y="56" '
                     f'width="{max(width - 1.5, .8):.1f}" height="10" fill="{readable(item["color"], theme)}"/>')
        x += width
    parts.append("</g>")
    for i, item in enumerate(shown):
        col, row = i % 2, i // 2
        lx, ly = 24 + col * 196, 96 + row * 21
        parts.append(
            f'<circle cx="{lx + 5}" cy="{ly - 4}" r="4.5" fill="{readable(item["color"], theme)}"/>'
            f'<text x="{lx + 18}" y="{ly}" font-family="{SANS}" font-size="12" fill="{t["text"]}">{esc(item["name"])}</text>'
            f'<text x="{lx + 172}" y="{ly}" text-anchor="end" font-family="{MONO}" font-size="11" fill="{t["muted"]}">{item["share"]:.1f}%</text>'
        )
    if not shown:
        parts.append(f'<text x="24" y="98" font-family="{SANS}" font-size="12.5" fill="{t["muted"]}">No languages reported.</text>')
    desc = ("Most used languages across public non-fork repositories, each repository weighted equally: "
            + ", ".join(f"{item['name']} {item['share']:.1f}%" for item in shown) + ".")
    return document(CARD_W, CARD_H, "Most Used Languages", desc, "".join(parts), STYLE)


def render_streak(stats, theme):
    t = THEMES[theme]
    c = stats["contributions"]
    current, longest = c["current_streak"], c["longest_streak"]

    def span(run):
        if not run["length"]:
            return "No active streak"
        if run["start"] == run["end"]:
            return short_date(run["start"])
        return f'{short_date(run["start"])} – {short_date(run["end"])}'

    third = CARD_W / 3
    cols = [third / 2, CARD_W / 2, CARD_W - third / 2]
    parts = [card_frame(CARD_W, CARD_H, t, f"sk-{theme}")]
    parts.append(f'<path d="M{third:.1f} 46V154M{2 * third:.1f} 46V154" stroke="{t["grid"]}"/>')
    for x, value, label, sub in [
        (cols[0], c["total"], "Total contributions", f'{short_date(c["first_day"], True)} – now'),
        (cols[2], longest["length"], "Longest streak", span(longest)),
    ]:
        parts.append(
            f'<text x="{x:.1f}" y="104" text-anchor="middle" font-family="{SANS}" font-size="26" font-weight="700" fill="{t["text"]}">{fmt(value)}</text>'
            f'<text x="{x:.1f}" y="130" text-anchor="middle" font-family="{SANS}" font-size="12" fill="{t["text"]}">{label}</text>'
            f'<text x="{x:.1f}" y="150" text-anchor="middle" font-family="{MONO}" font-size="9.5" fill="{t["faint"]}">{esc(sub)}</text>'
        )
    cx, cy, r = cols[1], 92, 34
    accent = t["amber"]
    parts.append(
        f'<circle cx="{cx:.1f}" cy="{cy}" r="{r}" fill="none" stroke="{t["grid"]}" stroke-width="5"/>'
        f'<circle class="draw" cx="{cx:.1f}" cy="{cy}" r="{r}" fill="none" stroke="{accent}" stroke-width="5" '
        f'stroke-linecap="round" pathLength="1" transform="rotate(-90 {cx:.1f} {cy})"/>'
        f'<circle cx="{cx:.1f}" cy="{cy - r}" r="12" fill="{t["bg_top"]}"/>'
        + glyph("flame", cx - 9, cy - r - 10, 18, accent, width=1.8)
        + f'<text x="{cx:.1f}" y="{cy + 10}" text-anchor="middle" font-family="{SANS}" font-size="28" font-weight="700" fill="{t["text"]}">{fmt(current["length"])}</text>'
        f'<text x="{cx:.1f}" y="150" text-anchor="middle" font-family="{SANS}" font-size="12.5" font-weight="600" fill="{accent}">Current streak</text>'
        f'<text x="{cx:.1f}" y="170" text-anchor="middle" font-family="{MONO}" font-size="9.5" fill="{t["faint"]}">{esc(span(current))}</text>'
    )
    parts.append(f'<text x="{CARD_W / 2}" y="188" text-anchor="middle" font-family="{MONO}" font-size="9" '
                 f'fill="{t["faint"]}" opacity=".8">within the last 12 months · updated {stats["updated"]}</text>')
    desc = (f"{c['total']} contributions since {c['first_day']}. Current streak {current['length']} days "
            f"({span(current)}); longest streak in this period {longest['length']} days ({span(longest)}).")
    return document(CARD_W, CARD_H, "Contribution streak", desc, "".join(parts), STYLE)


def monotone_path(points):
    """Fritsch–Carlson monotone cubic: smooth, without dipping below the baseline."""
    n = len(points)
    if n < 2:
        return f"M{points[0][0]:.1f} {points[0][1]:.1f}"
    dx = [points[i + 1][0] - points[i][0] for i in range(n - 1)]
    slope = [(points[i + 1][1] - points[i][1]) / dx[i] for i in range(n - 1)]
    tangent = [slope[0]] + [0.0] * (n - 2) + [slope[-1]]
    for i in range(1, n - 1):
        if slope[i - 1] * slope[i] > 0:
            tangent[i] = 3 * (dx[i - 1] + dx[i]) / ((2 * dx[i] + dx[i - 1]) / slope[i - 1] + (dx[i] + 2 * dx[i - 1]) / slope[i])
    path = [f"M{points[0][0]:.1f} {points[0][1]:.1f}"]
    for i in range(n - 1):
        (x0, y0), (x1, y1) = points[i], points[i + 1]
        h = dx[i] / 3
        path.append(f"C{x0 + h:.1f} {y0 + tangent[i] * h:.1f} {x1 - h:.1f} {y1 - tangent[i + 1] * h:.1f} {x1:.1f} {y1:.1f}")
    return "".join(path)


def render_activity(stats, theme):
    t = THEMES[theme]
    weeks = stats["contributions"]["weeks"]
    counts = [week["count"] for week in weeks]
    peak = max(counts, default=0)
    top = max(peak, 1)
    left, right, y_top, y_base = 24, CARD_W - 24, 62, 150
    step = (right - left) / max(len(counts) - 1, 1)
    points = [(left + i * step, y_base - (y_base - y_top) * count / top) for i, count in enumerate(counts)]
    line = monotone_path(points)
    accent = t["green"]
    parts = [
        card_frame(CARD_W, CARD_H, t, f"ac-{theme}"),
        title("Contribution Activity", t, "weekly · last 12 months"),
        f'<defs><linearGradient id="fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{accent}" stop-opacity=".35"/>'
        f'<stop offset="1" stop-color="{accent}" stop-opacity="0"/></linearGradient></defs>',
    ]
    for fraction in (0.5, 1.0):
        y = y_base - (y_base - y_top) * fraction
        parts.append(f'<path d="M{left} {y:.1f}H{right}" stroke="{t["grid"]}" stroke-dasharray="3 4"/>'
                     f'<text x="{right}" y="{y - 4:.1f}" text-anchor="end" font-family="{MONO}" font-size="9" fill="{t["faint"]}">{math.ceil(top * fraction)}</text>')
    parts.append(f'<path d="M{left} {y_base}H{right}" stroke="{t["border"]}"/>')
    if counts:
        parts.append(f'<path class="fade" d="{line}L{right:.1f} {y_base}L{left} {y_base}Z" fill="url(#fill)"/>')
        parts.append(f'<path class="draw" pathLength="1" d="{line}" fill="none" stroke="{accent}" stroke-width="2" '
                     f'stroke-linecap="round" stroke-linejoin="round"/>')
    seen = None
    for i, week in enumerate(weeks):
        month = week["start"][:7]
        if month != seen:
            seen = month
            if 1 <= i <= len(weeks) - 3:
                parts.append(f'<text x="{left + i * step:.1f}" y="168" text-anchor="middle" font-family="{MONO}" font-size="9" '
                             f'fill="{t["faint"]}">{datetime.strptime(month, "%Y-%m"):%b}</text>')
    if counts:
        index = counts.index(peak)
        px, py = points[index]
        lx, ly = points[-1]
        parts.append(
            f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3.5" fill="{t["bg_top"]}" stroke="{accent}" stroke-width="2"/>'
            f'<circle class="pulse" cx="{lx:.1f}" cy="{ly:.1f}" r="3.5" fill="{accent}"/>'
            f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="3.5" fill="{accent}"/>'
            f'<text x="24" y="188" font-family="{MONO}" font-size="10" fill="{t["muted"]}">peak {peak} · week of {short_date(weeks[index]["start"])}</text>'
            f'<text x="{right}" y="188" text-anchor="end" font-family="{MONO}" font-size="10" fill="{t["muted"]}">this week {counts[-1]}</text>'
        )
    desc = (f"Weekly contributions from {stats['contributions']['first_day']} to {stats['contributions']['last_day']}, "
            f"peaking at {peak} in one week.")
    return document(CARD_W, CARD_H, "Contribution activity", desc, "".join(parts), STYLE)


def render_all(stats):
    assets = {}
    for theme in THEMES:
        assets[f"stats-{theme}.svg"] = render_stats(stats, theme)
        assets[f"languages-{theme}.svg"] = render_languages(stats, theme)
        assets[f"streak-{theme}.svg"] = render_streak(stats, theme)
        assets[f"activity-{theme}.svg"] = render_activity(stats, theme)
    assets["badge-followers.svg"] = badge("followers", fmt(stats["followers"]), "users", "#7c3aed")
    assets["badge-stars.svg"] = badge("stars", fmt(stats["stars"]), "star", "#b45309")
    assets["github-stats.json"] = json.dumps(stats, indent=2, ensure_ascii=False) + "\n"
    return assets


def publish(output, assets):
    write_assets(output, assets)  # all-or-nothing replacement
    for old in output.glob("*.svg"):
        if old.name not in assets:
            old.unlink()  # retire files from earlier layouts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "assets" / "stats")
    parser.add_argument("--render-only", action="store_true",
                        help="re-render the SVGs from the committed JSON snapshot, without network access")
    args = parser.parse_args()
    try:
        if args.render_only:
            stats = json.loads((args.output_dir / "github-stats.json").read_text(encoding="utf-8"))
        else:
            stats = summarize(fetch(), datetime.now(timezone.utc).date().isoformat())
        publish(args.output_dir, render_all(stats))
    except Exception as error:
        # Never print response bodies, headers or tokens.
        raise SystemExit(f"Statistics update failed ({type(error).__name__}); previous files were kept.") from None
    print(f"Statistics for {USER} rendered ({stats['updated']} UTC)")


if __name__ == "__main__":
    main()
