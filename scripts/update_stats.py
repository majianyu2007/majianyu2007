#!/usr/bin/env python3
"""Render the profile's activity cards from public GitHub data.

Runs in GitHub Actions with the built-in GITHUB_TOKEN (read-only use). Everything is
fetched, validated and rendered in memory first; files are only replaced when all of
that succeeded, so a failed run leaves the previous good images untouched.
"""

import argparse
from collections import Counter
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen

from profile_svg import MONO, ROOT, SANS, THEMES, card_frame, document, esc, write_assets

USER = "majianyu2007"
API = "https://api.github.com"
CARD_W, CARD_H = 416, 300

CALENDAR_QUERY = """
query($login: String!) {
  user(login: $login) {
    followers { totalCount }
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""

# GitHub linguist colours; a few get a lighter stand-in on dark backgrounds.
LANGUAGE_COLOURS = {
    "C": "#555555", "C++": "#f34b7d", "C#": "#178600", "CSS": "#663399", "Dart": "#00B4AB",
    "Go": "#00ADD8", "HTML": "#e34c26", "Java": "#b07219", "JavaScript": "#f1e05a",
    "Kotlin": "#A97BFF", "Lua": "#000080", "Python": "#3572A5", "Rust": "#dea584",
    "Shell": "#89e051", "Swift": "#F05138", "TeX": "#3D6117", "TypeScript": "#3178c6",
    "Vue": "#41b883",
}
DARK_OVERRIDES = {"C": "#8b949e", "Lua": "#6f7fe0", "TeX": "#6a9a3a", "Python": "#4f8fd0"}


def language_colour(language, theme):
    if language == "Other":
        return THEMES[theme]["faint"]
    if theme == "dark" and language in DARK_OVERRIDES:
        return DARK_OVERRIDES[language]
    return LANGUAGE_COLOURS.get(language, "#8c959f")


# --------------------------------------------------------------------------- fetching
def _request(url, payload=None):
    token = os.environ.get("GITHUB_TOKEN")
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": f"{USER}-profile-stats",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    with urlopen(Request(url, data=data, headers=headers), timeout=30) as response:
        return json.load(response)


def fetch_repositories():
    """Every public repository owned by the user, across all pages."""
    repositories, page = [], 1
    while True:
        batch = _request(f"{API}/users/{USER}/repos?type=owner&sort=full_name&per_page=100&page={page}")
        if not isinstance(batch, list):
            raise ValueError("expected a repository list")
        repositories.extend(batch)
        if len(batch) < 100:
            return repositories
        page += 1


def fetch_calendar():
    if not os.environ.get("GITHUB_TOKEN"):
        raise ValueError("GITHUB_TOKEN is required for the GraphQL contribution calendar")
    result = _request(f"{API}/graphql", {"query": CALENDAR_QUERY, "variables": {"login": USER}})
    if not isinstance(result, dict) or result.get("errors") or not isinstance(result.get("data"), dict):
        raise ValueError("GraphQL query failed")
    return result["data"]["user"]


# --------------------------------------------------------------------------- summarising
def summarize_repositories(repositories):
    originals, seen = [], set()
    for repo in repositories:
        if not isinstance(repo, dict):
            raise ValueError("invalid repository record")
        identifier, stars, language = repo.get("id"), repo.get("stargazers_count"), repo.get("language")
        if (
            type(identifier) is not int or identifier in seen
            or not isinstance(repo.get("owner"), dict)
            or str(repo["owner"].get("login", "")).lower() != USER.lower()
            or repo.get("private") is not False
            or type(repo.get("fork")) is not bool
            or type(stars) is not int or stars < 0
            or (language is not None and (not isinstance(language, str) or not language))
        ):
            raise ValueError("incomplete, duplicate or non-public repository data")
        seen.add(identifier)
        if not repo["fork"]:
            originals.append(repo)
    languages = Counter(repo["language"] for repo in originals if repo["language"])
    return {
        "repositories": len(originals),
        "stars": sum(repo["stargazers_count"] for repo in originals),
        "languages": [list(item) for item in sorted(languages.items(), key=lambda kv: (-kv[1], kv[0]))],
    }


def summarize_calendar(user, today):
    if not isinstance(user, dict):
        raise ValueError("user missing from GraphQL response")
    followers = user.get("followers", {}).get("totalCount")
    calendar = user.get("contributionsCollection", {}).get("contributionCalendar", {})
    total, weeks = calendar.get("totalContributions"), calendar.get("weeks")
    if type(followers) is not int or followers < 0 or type(total) is not int or total < 0:
        raise ValueError("invalid follower or contribution totals")
    if not isinstance(weeks, list) or not 50 <= len(weeks) <= 54:
        raise ValueError("unexpected contribution calendar shape")
    days, weekly = [], []
    for week in weeks:
        entries = week.get("contributionDays") if isinstance(week, dict) else None
        if not isinstance(entries, list) or not 1 <= len(entries) <= 7:
            raise ValueError("invalid calendar week")
        week_total = 0
        for entry in entries:
            count = entry.get("contributionCount") if isinstance(entry, dict) else None
            if type(count) is not int or count < 0:
                raise ValueError("invalid contribution count")
            days.append((date.fromisoformat(entry["date"]), count))
            week_total += count
        weekly.append({"start": entries[0]["date"], "count": week_total})
    if [d for d, _ in days] != sorted({d for d, _ in days}) or sum(c for _, c in days) != total:
        raise ValueError("calendar days are unordered, duplicated or inconsistent")
    if days[-1][0] != today or any(
        right[0] - left[0] != timedelta(days=1) for left, right in zip(days, days[1:])
    ):
        raise ValueError("calendar is stale or has missing days")

    longest = run = 0
    for _, count in days:
        run = run + 1 if count else 0
        longest = max(longest, run)
    counts = [c for _, c in days]
    if counts and counts[-1] == 0:
        counts.pop()  # today may simply not have started yet
    current = 0
    for count in reversed(counts):
        if not count:
            break
        current += 1
    return {
        "followers": followers,
        "contributions": {
            "total": total,
            "active_days": sum(1 for _, c in days if c),
            "current_streak": current,
            "longest_streak": longest,
            "first_day": days[0][0].isoformat(),
            "last_day": days[-1][0].isoformat(),
            "weeks": weekly,
        },
    }


def summarize(repositories, calendar_user, updated):
    stats = {"user": USER, "updated": updated}
    stats.update(summarize_repositories(repositories))
    stats.update(summarize_calendar(calendar_user, date.fromisoformat(updated)))
    return stats


# --------------------------------------------------------------------------- rendering
def fmt(number):
    return f"{number:,}"


def header(title, right, t):
    return (
        f'<text x="24" y="40" font-family="{SANS}" font-size="16" font-weight="600" fill="{t["text"]}">{esc(title)}</text>'
        f'<text x="{CARD_W - 24}" y="40" text-anchor="end" font-family="{MONO}" font-size="10.5" fill="{t["faint"]}">{esc(right)}</text>'
    )


def render_overview(stats, theme):
    t = THEMES[theme]
    c = stats["contributions"]
    metrics = [
        (fmt(stats["followers"]), "", "followers", t["green"]),
        (fmt(c["current_streak"]), "d", "current streak", t["amber"]),
        (fmt(c["longest_streak"]), "d", "longest streak", t["violet"]),
        (fmt(c["active_days"]), "", "active days", t["blue"]),
        (fmt(stats["repositories"]), "", "public repos", t["green"]),
        (fmt(stats["stars"]), "", "stars earned", t["amber"]),
    ]
    parts = [card_frame(CARD_W, CARD_H, t, f"ov-{theme}"),
             header("GitHub at a glance", f"updated {stats['updated']}", t),
             f'<style>.seg{{animation:grow .9s cubic-bezier(.2,.7,.2,1) both;transform-box:fill-box;transform-origin:left}}'
             f'@keyframes grow{{from{{transform:scaleX(0)}}}}'
             f'@media (prefers-reduced-motion:reduce){{.seg{{animation:none}}}}</style>']
    for i, (value, unit, label, colour) in enumerate(metrics):
        x, y = 24 + (i % 3) * 128, 92 + (i // 3) * 62
        unit_svg = (f'<tspan font-size="14" font-weight="500" fill="{t["muted"]}" dx="2">{unit}</tspan>' if unit else "")
        parts.append(
            '<g>'
            f'<rect x="{x}" y="{y - 30}" width="14" height="3" rx="1.5" fill="{colour}"/>'
            f'<text x="{x}" y="{y}" font-family="{SANS}" font-size="25" font-weight="700" fill="{t["text"]}">{value}{unit_svg}</text>'
            f'<text x="{x}" y="{y + 18}" font-family="{SANS}" font-size="11.5" fill="{t["muted"]}">{esc(label)}</text></g>'
        )
    parts.append(f'<path d="M24 196H{CARD_W - 24}" stroke="{t["grid"]}"/>')
    parts.append(f'<text x="24" y="220" font-family="{MONO}" font-size="10.5" letter-spacing="1.2" fill="{t["faint"]}">'
                 f'PRIMARY LANGUAGE · {stats["repositories"]} REPOS</text>')

    languages = [tuple(item) for item in stats["languages"]]
    shown = languages[:5]
    rest = sum(count for _, count in languages[5:])
    if rest:
        shown.append(("Other", rest))
    total = sum(count for _, count in shown) or 1
    bar_w, x = CARD_W - 48, 24.0
    parts.append(f'<clipPath id="bar"><rect x="24" y="230" width="{bar_w}" height="10" rx="5"/></clipPath>'
                 f'<rect x="24" y="230" width="{bar_w}" height="10" rx="5" fill="{t["grid"]}"/><g clip-path="url(#bar)">')
    for i, (language, count) in enumerate(shown):
        width = bar_w * count / total
        parts.append(f'<rect class="seg" style="animation-delay:{0.25 + i * 0.08:.2f}s" x="{x:.1f}" y="230" '
                     f'width="{max(width - 2, 1):.1f}" height="10" fill="{language_colour(language, theme)}"/>')
        x += width
    parts.append("</g>")
    for i, (language, count) in enumerate(shown):
        lx, ly = 24 + (i % 3) * 128, 266 + (i // 3) * 20
        parts.append(
            f'<circle cx="{lx + 4}" cy="{ly - 4}" r="4" fill="{language_colour(language, theme)}"/>'
            f'<text x="{lx + 14}" y="{ly}" font-family="{SANS}" font-size="12" fill="{t["text"]}">{esc(language)}'
            f'<tspan font-family="{MONO}" font-size="11" fill="{t["faint"]}" dx="6">{count}</tspan></text>'
        )
    if not shown:
        parts.append(f'<text x="24" y="266" font-family="{SANS}" font-size="12" fill="{t["muted"]}">No primary languages reported.</text>')
    desc = (f"{stats['followers']} followers, {c['active_days']} active days in the last year, current streak "
            f"{c['current_streak']} days, longest streak {c['longest_streak']} days. {stats['repositories']} public "
            f"non-fork repositories with {stats['stars']} stars. Primary languages by repository count: "
            + ", ".join(f"{lang} {n}" for lang, n in shown) + f". Updated {stats['updated']} UTC.")
    return document(CARD_W, CARD_H, "GitHub at a glance", desc, "".join(parts))


def monotone_path(points):
    """Fritsch–Carlson monotone cubic: smooth, and never dips below zero."""
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
    c = stats["contributions"]
    weeks = c["weeks"]
    counts = [week["count"] for week in weeks]
    peak = max(counts) if counts else 0
    top = max(peak, 1)
    left, right, y_top, y_base = 24, CARD_W - 24, 112, 232
    step = (right - left) / max(len(counts) - 1, 1)
    points = [(left + i * step, y_base - (y_base - y_top) * count / top) for i, count in enumerate(counts)]
    line = monotone_path(points)
    area = f"{line}L{right:.1f} {y_base}L{left} {y_base}Z"
    accent = t["green"]
    parts = [
        card_frame(CARD_W, CARD_H, t, f"act-{theme}"),
        header("Contributions", "weekly · last 12 months", t),
        '<style>.ln{stroke-dasharray:1;animation:draw 2.4s cubic-bezier(.4,0,.2,1) both}'
        '.ar{animation:fade 1.6s .6s ease-out both}.pulse{animation:pulse 2.2s ease-out 2.4s infinite;transform-box:fill-box;transform-origin:center}'
        '@keyframes draw{from{stroke-dashoffset:1}to{stroke-dashoffset:0}}@keyframes fade{from{opacity:.25}}'
        '@keyframes pulse{0%{opacity:.7;transform:scale(1)}100%{opacity:0;transform:scale(3.2)}}'
        '@media (prefers-reduced-motion:reduce){.ln,.ar,.pulse{animation:none}.pulse{opacity:0}}</style>',
        f'<defs><linearGradient id="fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{accent}" stop-opacity=".32"/>'
        f'<stop offset="1" stop-color="{accent}" stop-opacity="0"/></linearGradient></defs>',
        f'<text x="24" y="84" font-family="{SANS}" font-size="30" font-weight="700" fill="{t["text"]}">{fmt(c["total"])}'
        f'<tspan font-size="13" font-weight="400" fill="{t["muted"]}" dx="8">contributions in the last year</tspan></text>',
    ]
    for fraction in (0.5, 1.0):
        y = y_base - (y_base - y_top) * fraction
        parts.append(f'<path d="M{left} {y:.1f}H{right}" stroke="{t["grid"]}" stroke-dasharray="3 4"/>'
                     f'<text x="{right}" y="{y - 5:.1f}" text-anchor="end" font-family="{MONO}" font-size="9.5" fill="{t["faint"]}">{round(top * fraction)}</text>')
    parts.append(f'<path d="M{left} {y_base}H{right}" stroke="{t["border"]}"/>')
    parts.append(f'<path class="ar" d="{area}" fill="url(#fill)"/>')
    parts.append(f'<path class="ln" pathLength="1" d="{line}" fill="none" stroke="{accent}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>')

    seen_month = None
    for i, week in enumerate(weeks):
        month = week["start"][:7]
        if month != seen_month:
            seen_month = month
            if 1 <= i <= len(weeks) - 3:
                label = datetime.strptime(month, "%Y-%m").strftime("%b")
                parts.append(f'<text x="{left + i * step:.1f}" y="252" text-anchor="middle" font-family="{MONO}" '
                             f'font-size="9.5" fill="{t["faint"]}">{label}</text>')
    if counts:
        peak_index = counts.index(peak)
        px, py = points[peak_index]
        lx, ly = points[-1]
        peak_day = date.fromisoformat(weeks[peak_index]["start"])
        peak_week = f"{peak_day:%b} {peak_day.day}"
        parts.append(
            f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3.5" fill="{t["bg_top"]}" stroke="{accent}" stroke-width="2"/>'
            f'<circle class="pulse" cx="{lx:.1f}" cy="{ly:.1f}" r="4" fill="{accent}"/>'
            f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="4" fill="{accent}"/>'
            f'<text x="24" y="280" font-family="{MONO}" font-size="10.5" fill="{t["muted"]}">peak {peak} · week of {peak_week}</text>'
            f'<text x="{right}" y="280" text-anchor="end" font-family="{MONO}" font-size="10.5" fill="{t["muted"]}">this week {counts[-1]}</text>'
        )
    desc = (f"Weekly contributions from {c['first_day']} to {c['last_day']}: {fmt(c['total'])} in total, "
            f"peaking at {peak} in one week. Updated {stats['updated']} UTC.")
    return document(CARD_W, CARD_H, "Contributions in the last year", desc, "".join(parts))


def render_all(stats):
    assets = {}
    for theme in THEMES:
        assets[f"overview-{theme}.svg"] = render_overview(stats, theme)
        assets[f"activity-{theme}.svg"] = render_activity(stats, theme)
    assets["github-stats.json"] = json.dumps(stats, indent=2, ensure_ascii=False) + "\n"
    return assets


def update(output):
    today = datetime.now(timezone.utc).date().isoformat()
    stats = summarize(fetch_repositories(), fetch_calendar(), today)
    write_assets(output, render_all(stats))  # publication is one workflow commit
    print(f"Generated profile statistics for {USER} ({today} UTC)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "assets" / "stats")
    parser.add_argument("--render-only", action="store_true",
                        help="re-render SVGs from the committed JSON snapshot without network access")
    args = parser.parse_args()
    try:
        if args.render_only:
            stats = json.loads((args.output_dir / "github-stats.json").read_text(encoding="utf-8"))
            write_assets(args.output_dir, render_all(stats))
            print("Re-rendered statistics SVGs from the existing snapshot")
        else:
            update(args.output_dir)
    except Exception as error:
        # Never print response bodies, headers or tokens.
        raise SystemExit(f"Statistics update failed ({type(error).__name__}); no update should be published.") from None


if __name__ == "__main__":
    main()
