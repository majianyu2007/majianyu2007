# Profile maintenance

## Layout and artwork

The README uses a local animated hero, paired focus/toolkit panels, four linked project cards, and two activity cards. The 416px cards flow inline: two fit an 838px GitHub content column; narrow screens stack them without a fixed-width HTML table. Every image has descriptive alternative text. Theme-specific `<picture>` sources follow GitHub's light/dark appearance.

All images are committed SVGs. They use system fonts, embedded vector paths, and local gradients; visitors do not contact a typing-animation service, badge service, icon CDN, or chart-rendering API. The hero's typewriter and network motif animate inside the SVG without JavaScript. Reduced-motion users see a complete static hero; chart animations also respect reduced motion.

Edit `scripts/build_visuals.py` for hero text, project descriptions, toolkit and setup. Shared colours and drawing primitives live in `scripts/profile_svg.py`. Regenerate and commit the artwork with its source:

```sh
python3 scripts/build_visuals.py
python3 scripts/build_visuals.py --check
```

Both commands work offline with Python 3.9+. `--check` rejects missing, obsolete or stale profile SVGs. Vendored brand icons and their provenance are in `assets/vendor/simple-icons.json`; the CC0 license is retained alongside it. Keep attribution/legal records here rather than adding design-reference acknowledgments to the public profile.

Keep the identity year-independent, coursework distinct from project experience, and equipment concise. Never include credentials, personal network addresses, or private configuration.

## Project facts

Descriptions were checked against the public repositories, including implementation files:

- [nwafu-bksxk](https://github.com/majianyu2007/nwafu-bksxk): Flutter academic assistant; `pubspec.yaml`, `lib/data/ehall_service.dart`, `lib/data/enroll_service.dart`, `lib/data/monitor_engine.dart`, and `PLATFORMS.md`. Platform features differ, especially browser connectivity and background work.
- [nwafu-connect](https://github.com/majianyu2007/nwafu-connect): unofficial aTrust client, forked from [Mythologyli/zju-connect](https://github.com/Mythologyli/zju-connect). Proxy access remains limited to authorized campus resources. Implementation: `main.go`, `client/atrust/client.go`, `internal/managedbrowser/browser.go`, desktop entry point under `cmd/`.
- [QuotaPeek](https://github.com/majianyu2007/QuotaPeek): SwiftUI/AppKit, macOS 14+, specific VM2API-compatible usage schema, not a universal provider/billing tracker. Implementation: `Package.swift` and `Sources/QuotaCore/`.
- [smart-srun](https://github.com/majianyu2007/smart-srun): fork of [matthewlu070111/smart-srun](https://github.com/matthewlu070111/smart-srun). The inspected fork uses Python/Lua/JavaScript, with OpenWrt CLI/LuCI integration. The profile owner's upstream fixes were confirmed merged: [#33](https://github.com/matthewlu070111/smart-srun/pull/33) daemon lock state, [#34](https://github.com/matthewlu070111/smart-srun/pull/34) portal detection fallback, [#35](https://github.com/matthewlu070111/smart-srun/pull/35) wireless radio detection.

The website and email come from the original public README. Website retrieval was checked; email delivery was not tested.

## Statistics and scope

`scripts/update_stats.py` fetches every page of `GET /users/majianyu2007/repos`, then uses GitHub GraphQL for follower count and the contribution calendar. It saves only aggregate counts, dates, and weekly totals, not repository response bodies, contribution details, credentials, or private repository names.

- Repositories: public, owned, non-fork repositories, including archived repositories.
- Stars: sum on those repositories only, excluding fork and organization totals.
- Languages: one primary language per repository; null languages omitted. The top five are shown individually, with the rest grouped as Other. This is neither code volume nor proficiency.
- Contributions: GitHub's returned calendar, aggregated into weeks. The calendar may include a partial first/last week; its exact dates are stored in the JSON. Visibility follows GitHub's calendar and the credential used; local account credentials and the repository-scoped Actions token can have different visibility. Do not interpret the calendar as proof of public-only commits.
- Active days: dates in that calendar with a positive contribution count.
- Current streak: consecutive active days ending today, or yesterday if today still has zero contributions (UTC).
- Longest streak: longest run in the returned calendar, **not** an all-time record.
- Update date: successful retrieval date in UTC, not real-time data.

The five outputs are `overview-light.svg`, `overview-dark.svg`, `activity-light.svg`, `activity-dark.svg`, and `github-stats.json`, under `assets/stats/`.

## Update workflow and failure protection

`.github/workflows/update-stats.yml` runs daily at **06:23 UTC**, supports **Run workflow**, and runs on relevant source, artwork, vendor, test or workflow changes pushed to `main`.

It uses the built-in `GITHUB_TOKEN` with job-level `contents: write`. No additional PAT is required. Checkout is pinned to a full SHA; generators use only Python's standard library.

1. Verify committed profile artwork matches its source.
2. Run behavior tests covering aggregation, pagination, contribution calendars, streak boundaries, GraphQL errors, and failed-update preservation.
3. Fetch and validate all data, then render all statistics before touching existing files.
4. Stage complete files, replacing each atomically. Commit only the five named outputs in one Git commit, then push normally. Unchanged output produces no commit.

API errors, malformed data, incomplete calendars and render failures stop before replacement. A disk error during replacement could leave a local mixture of complete files, but the failed job cannot publish it. A rejected push leaves the previous remote snapshot untouched. Runs are serialized; there is no force push. If a concurrent human push rejects an update, rerun it on the new head.

Schedule delays and GitHub's automatic disabling of scheduled workflows after prolonged public-repository inactivity can leave a stale date, but do not break the committed images. Check Actions and re-enable or manually run the job when necessary.

## Local commands

```sh
python3 scripts/build_visuals.py --check
python3 -B -m unittest discover -s tests -v
python3 scripts/update_stats.py
```

The last command requires `GITHUB_TOKEN` because GitHub GraphQL requires authentication. Supply it through your environment, never through a command argument or a checked-in file. With an existing GitHub CLI login, an in-memory environment handoff is also possible; do not log the credential. An authenticated local run does not prove that the hosted token and repository policies permit the same operation.

To restyle statistics from the existing snapshot without API access:

```sh
python3 scripts/update_stats.py --render-only
```

`--output-dir /temporary/path` selects a separate destination. For `--render-only`, place the snapshot in that destination first. If installed, run `actionlint .github/workflows/update-stats.yml` to validate workflow syntax.

## First deployment

Commit the README, scripts, tests, workflow, guide, vendor files, and **all generated assets** together, then push to `main`. The current README already has every required image, so its first display does not depend on a successful Action run.

Open **Actions → Update profile statistics** and inspect the push-triggered run, or select **Run workflow → main**. Confirm artwork checks, tests, generation and publishing succeed; publishing may correctly report that statistics are unchanged. Check the actual profile in both themes and on mobile.

If Actions policy or branch rules prohibit bot writes, publishing fails safely. Resolve the intended repository policy rather than adding a broad PAT or force-pushing. A real hosted Actions run has not been performed as part of this local delivery; that remains the deployment check after publication.
