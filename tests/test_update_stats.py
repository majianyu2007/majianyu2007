import copy
from datetime import date, timedelta
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import update_stats as stats

TODAY = date(2026, 10, 23)


def repo(identifier=1, **changes):
    return dict(id=identifier, owner={"login": stats.USER}, private=False,
                fork=False, language="Python", stargazers_count=3, **changes)


def calendar(tail=(1, 1, 0)):
    counts = [0] * (364 - len(tail)) + list(tail)
    days = [{"date": (TODAY - timedelta(days=363-i)).isoformat(), "contributionCount": n}
            for i, n in enumerate(counts)]
    return {"followers": {"totalCount": 12}, "contributionsCollection": {
        "contributionCalendar": {"totalContributions": sum(counts),
                                 "weeks": [{"contributionDays": days[i:i+7]} for i in range(0, 364, 7)]}}}


class StatisticsTests(unittest.TestCase):
    def test_originals_include_archived_and_exclude_forks(self):
        fork = repo(2); fork.update(fork=True, stargazers_count=100)
        archived = repo(3); archived.update(archived=True, language=None)
        result = stats.summarize_repositories([repo(), fork, archived])
        self.assertEqual(result, {"repositories": 2, "stars": 6, "languages": [["Python", 1]]})

    def test_rejects_private_foreign_duplicate_and_incomplete_records(self):
        cases = [[repo(), repo()], [{"id": 1}]]
        for field, value in [("private", True), ("owner", {"login": "another"}),
                             ("stargazers_count", -1), ("language", 17)]:
            record = repo(); record[field] = value; cases.append([record])
        for records in cases:
            with self.subTest(records=records), self.assertRaises(ValueError):
                stats.summarize_repositories(records)

    def test_pagination_does_not_truncate_at_one_hundred(self):
        with patch.object(stats, "_request", side_effect=[[repo(i) for i in range(100)], [repo(100)]]) as request:
            self.assertEqual(len(stats.fetch_repositories()), 101)
            self.assertIn("page=2", request.call_args.args[0])

    def test_streak_grace_and_reset(self):
        for tail, expected, longest in [((1, 1, 0), 2, 2), ((1, 0, 0), 0, 1),
                                        ((1, 1, 1), 3, 3), ((0, 0, 0), 0, 0)]:
            with self.subTest(tail=tail):
                result = stats.summarize_calendar(calendar(tail), TODAY)["contributions"]
                self.assertEqual(result["current_streak"], expected)
                self.assertEqual(result["longest_streak"], longest)
                self.assertEqual(result["total"], sum(tail))

    def test_calendar_rejects_missing_days_inconsistent_totals_and_staleness(self):
        for kind in ("gap", "total", "stale", "negative"):
            user = calendar()
            cal = user["contributionsCollection"]["contributionCalendar"]
            if kind == "gap": cal["weeks"][1]["contributionDays"].pop(0)
            if kind == "total": cal["totalContributions"] += 1
            if kind == "negative": cal["weeks"][0]["contributionDays"][0]["contributionCount"] = -1
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                stats.summarize_calendar(user, TODAY + timedelta(days=1) if kind == "stale" else TODAY)

    def test_graphql_partial_errors_are_not_accepted(self):
        with patch.dict("os.environ", {"GITHUB_TOKEN": "test-only"}), patch.object(
            stats, "_request", return_value={"data": {"user": calendar()}, "errors": [{"message": "denied"}]}
        ), self.assertRaises(ValueError):
            stats.fetch_calendar()

    def test_failures_preserve_every_previous_asset(self):
        snapshot = stats.summarize([repo()], calendar(), TODAY.isoformat())
        assets = stats.render_all(snapshot)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            for name, content in assets.items(): (output / name).write_text(content)
            failures = [("fetch_repositories", HTTPError(stats.API, 503, "Unavailable", {}, None)),
                        ("fetch_calendar", ValueError("GraphQL failure")),
                        ("render_all", ValueError("render failure"))]
            for target, error in failures:
                with patch.object(stats, "fetch_repositories", return_value=[repo()]), patch.object(
                    stats, "fetch_calendar", return_value=calendar()
                ), patch.object(stats, "summarize", return_value=snapshot), patch.object(
                    stats, target, side_effect=error
                ), self.assertRaises(type(error)):
                    stats.update(output)
                self.assertEqual({p.name: p.read_text() for p in output.iterdir()}, assets)

    def test_partial_repository_fetch_never_publishes(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "stats"
            with patch.object(stats, "_request", side_effect=[
                [repo(i) for i in range(100)], HTTPError(stats.API, 403, "Forbidden", {}, None)
            ]), self.assertRaises(HTTPError):
                stats.update(output)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
