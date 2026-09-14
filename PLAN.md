# Cheese Board pizza scraper — status

## Goal
Daily-scrape https://cheeseboardcollective.coop/pizza/pizza-schedule/, extract
each day's pizza (name/date + ingredient list), skip salads, store results as
data for later stats. Runs as a scheduled GitHub Action.

Repo: https://github.com/fcuny/cheeseboard (public)

## Done
1. **Verified against the real DOM.** Each day is
   `div.daily-pizza > article`, with the date in `div.date p` and ingredients
   in the `<p>` following `<h3>Pizza</h3>` (up to the next `<h3>`, usually
   `Salad`). `scrape_cheeseboard.py` scopes to that structure instead of
   walking all headings/paragraphs on the page.
2. **Edge cases handled:**
   - `resolve_year()` infers the year at the Dec→Jan boundary; covered by a
     unit test.
   - Parenthetical asides (farm attribution, vegan/cashew footnotes) are
     stripped before splitting on commas; covered by a unit test.
   - **Closed days** (weekly closures, holidays, or next week not posted
     yet) are detected from the site's own "The pizzeria is closed today."
     text and written as `{"closed": true}` records instead of causing a
     failure. The scrape only fails when zero recognizable day-articles are
     found at all (real site/structure breakage) — not tied to any
     particular weekday. Covered by a unit test against a real Sun/Mon
     closed-days fixture.
3. **Tests added** (`tests/`) against saved real-page fixtures:
   `single_day.html` (2026-09-12, one pizza day), `closed_days.html`
   (2026-09-13, Sunday+Monday both closed), and `full_week.html`
   (2026-09-14, a full week: closed Monday, five real pizza days, closed
   Sunday — confirms the `article`-per-day structure holds across multiple
   days on one page, not just the single-day case).
4. **Storage/dedup decided:** one file per *pizza date*
   (`data/<pizza-date>.json`), upserted — not one file per scrape-run date.
5. **PR-based review flow.** The Action opens a PR per run (branch
   `pizza-schedule/<date>`, `pizza-data` label) via
   `peter-evans/create-pull-request` instead of pushing straight to `main`,
   so scraper bugs or data cleanup can be caught before merging. No PR is
   opened when a run produces no diff.
6. **uv for dependency management.** `pyproject.toml` + `uv.lock` +
   `.python-version` (3.12); CI uses `astral-sh/setup-uv` + `uv sync` +
   `uv run`.
7. **GitHub Action wired up and verified**, including the closed-day fix,
   via real `workflow_dispatch` runs. Daily cron at 09:00 UTC. No failure
   notification beyond GitHub's own failed-run email (deliberate, per
   for-fun scope).

## Open / deferred
- **Occasional extra pizza variants** (e.g. a separate vegan pizza section
  on the same day) — not observed yet. Current parser only captures the
  block after the first `<h3>Pizza</h3>`; revisit if/when the real site
  does this.
- **(Stretch) Build the stats.** Once a few weeks of `data/*.json` exist:
  ingredient frequency counts, most common pizza combos, seasonal patterns,
  closed-day frequency.

## Non-goals
- No interest in salads — parser does not extract them.
- Not building a UI/dashboard right now, just the scrape + storage pipeline.
