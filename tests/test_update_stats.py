import json
from datetime import date, timedelta
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import build_visuals  # noqa: E402
import update_stats as stats  # noqa: E402

END = date(2026, 10, 24)


def calendar(active=None, weeks=53):
    """A contiguous calendar ending on END; `active` maps days-before-END to counts."""
    active = active or {}
    days = [END - timedelta(days=i) for i in range(weeks * 7 - 1, -1, -1)]
    entries = [{"date": d.isoformat(), "contributionCount": active.get((END - d).days, 0)} for d in days]
    return {
        "totalCommitContributions": 5,
        "totalRepositoriesWithContributedCommits": 2,
        "contributionCalendar": {
            "totalContributions": sum(e["contributionCount"] for e in entries),
            "weeks": [{"contributionDays": entries[i:i + 7]} for i in range(0, len(entries), 7)],
        },
    }


def repo(name, stars=1, languages=(("Python", 100, "#3572A5"),), **changes):
    record = {
        "name": name, "isFork": False, "isPrivate": False, "stargazerCount": stars,
        "languages": {"edges": [{"size": size, "node": {"name": lang, "color": colour}}
                                for lang, size, colour in languages]},
    }
    record.update(changes)
    return record


def user(repositories=None, collection=None):
    repositories = [repo("a")] if repositories is None else repositories
    return {
        "followers": {"totalCount": 3}, "pullRequests": {"totalCount": 4}, "issues": {"totalCount": 1},
        "repositories": {"totalCount": len(repositories), "nodes": repositories,
                         "pageInfo": {"hasNextPage": False, "endCursor": None}},
        "contributionsCollection": collection or calendar({0: 1, 1: 2}),
    }


class SummaryTests(unittest.TestCase):
    def test_totals_and_equal_weight_languages(self):
        summary = stats.summarize(user([
            repo("big", stars=2, languages=(("C", 10_000_000, "#555555"), ("CMake", 9_000_000, "#DA3434"))),
            repo("app", stars=3, languages=(("Python", 300, "#3572A5"), ("Shell", 100, "#89e051"))),
            repo("docs", stars=0, languages=()),
        ]), "2026-10-24")
        self.assertEqual((summary["repositories"], summary["stars"], summary["followers"]), (3, 5, 3))
        self.assertEqual(summary["language_repositories"], 2)
        shares = {item["name"]: item["share"] for item in summary["languages"]}
        # A huge repository counts once; build-system languages are ignored.
        self.assertEqual(shares, {"C": 50.0, "Python": 37.5, "Shell": 12.5})

    def test_streaks(self):
        # Active yesterday and the two days before, idle today: the streak is still current.
        summary = stats.summarize_calendar(calendar({1: 1, 2: 4, 3: 2, 10: 1, 11: 1, 12: 1, 13: 1, 14: 1}))
        self.assertEqual(summary["current_streak"],
                         {"length": 3, "start": "2026-10-21", "end": "2026-10-23"})
        self.assertEqual(summary["longest_streak"]["length"], 5)
        self.assertEqual((summary["active_days"], summary["total"]), (8, 12))
        # Two idle days end it.
        self.assertEqual(stats.summarize_calendar(calendar({2: 1}))["current_streak"]["length"], 0)
        self.assertEqual(stats.summarize_calendar(calendar())["longest_streak"]["length"], 0)

    def test_rejects_inconsistent_or_unexpected_data(self):
        broken_calendar = calendar({0: 1})
        broken_calendar["contributionCalendar"]["totalContributions"] = 7
        gap = calendar()
        del gap["contributionCalendar"]["weeks"][5]["contributionDays"][3]
        cases = [
            user([repo("a", isFork=True)]), user([repo("a", isPrivate=True)]),
            user([repo("a"), repo("a")]), user([repo("a", stars=-1)]), user([repo("a", stars=True)]),
            user(collection=broken_calendar), user(collection=gap), user(collection=calendar(weeks=20)),
        ]
        partial = user([repo("a"), repo("b")])
        partial["repositories"]["totalCount"] = 3
        cases.append(partial)
        for case in cases:
            with self.subTest(case=case), self.assertRaises((ValueError, KeyError, TypeError)):
                stats.summarize(case, "2026-10-24")

    def test_follows_repository_pagination(self):
        first, second = user([repo("a")]), user([repo("b", stars=4)])
        first["repositories"]["totalCount"] = second["repositories"]["totalCount"] = 2
        first["repositories"]["pageInfo"] = {"hasNextPage": True, "endCursor": "c1"}
        with patch.object(stats, "graphql", side_effect=[first, second]) as call:
            merged = stats.fetch()
        self.assertEqual(call.call_args_list[1].args[0]["cursor"], "c1")
        self.assertEqual(stats.summarize(merged, "2026-10-24")["stars"], 5)


class OutputTests(unittest.TestCase):
    def assert_self_contained(self, name, svg):
        ET.fromstring(svg)
        stripped = svg.replace('xmlns="http://www.w3.org/2000/svg"', "")
        self.assertNotIn("http", stripped, name)
        self.assertNotIn("<image", stripped, name)

    def test_statistics_svgs_are_valid_and_self_contained(self):
        assets = stats.render_all(stats.summarize(user(), "2026-10-24"))
        self.assertEqual(len([n for n in assets if n.endswith(".svg")]), 10)
        for name, content in assets.items():
            if name.endswith(".svg"):
                self.assert_self_contained(name, content)
        json.loads(assets["github-stats.json"])

    def test_static_artwork_is_valid_and_matches_committed_files(self):
        assets = build_visuals.build()
        for name, content in assets.items():
            self.assert_self_contained(name, content)
        self.assertEqual(stats.write_assets(build_visuals.OUTPUT, assets, check=True), [])

    def test_failed_update_keeps_previous_files(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory, "stats")
            output.mkdir()
            old = output / "stats-light.svg"
            old.write_text("<svg>previous good image</svg>", encoding="utf-8")
            argv = ["update_stats.py", "--output-dir", str(output)]
            for failure in (OSError("network down"), ValueError("bad data")):
                with self.subTest(failure=failure), patch.object(sys, "argv", argv), \
                        patch.object(stats, "fetch", side_effect=failure), self.assertRaises(SystemExit):
                    stats.main()
            with patch.object(sys, "argv", argv), patch.dict(os.environ, {"GITHUB_TOKEN": ""}), \
                    self.assertRaises(SystemExit):
                stats.main()  # no token: refuse rather than publish partial data
            self.assertEqual(old.read_text(encoding="utf-8"), "<svg>previous good image</svg>")
            self.assertEqual(sorted(p.name for p in output.iterdir()), ["stats-light.svg"])

    def test_successful_update_replaces_all_files_and_retires_old_ones(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory, "stats")
            output.mkdir()
            (output / "overview-light.svg").write_text("<svg/>", encoding="utf-8")
            with patch.object(sys, "argv", ["update_stats.py", "--output-dir", str(output)]), \
                    patch.object(stats, "fetch", return_value=user()):
                stats.main()
            names = sorted(p.name for p in output.iterdir())
            self.assertNotIn("overview-light.svg", names)
            self.assertIn("github-stats.json", names)
            self.assertEqual(len(names), 11)


if __name__ == "__main__":
    unittest.main()
