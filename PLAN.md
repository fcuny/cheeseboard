# Cheese Board pizza scraper — status

## Goal
Daily-scrape https://cheeseboardcollective.coop/pizza/pizza-schedule/, extract
each day's pizza (name/date + ingredient list), skip salads, store results as
data for later stats. Runs as a scheduled GitHub Action.

Repo: https://github.com/fcuny/cheeseboard

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
   - Days with no `<h3>Pizza</h3>` block are skipped, not crashed on.
3. **Tests added** (`tests/`) against a saved real-page fixture
   (`tests/fixtures/single_day.html`, captured 2026-09-12).
4. **Storage/dedup decided:** one file per *pizza date*
   (`data/<pizza-date>.json`), upserted — not one file per scrape-run date.
   Verified end-to-end via a manual `workflow_dispatch` run.
5. **GitHub Action wired up and verified.** Daily cron at 09:00 UTC,
   `contents: write` permission, commits via `pizza-bot`. No failure
   notification beyond GitHub's own failed-run email (deliberate, per
   for-fun scope).

## Open / deferred
- **Multi-day fixture.** Only ever observed a single-pizza Saturday so far
  (today's schedule only lists one day). Add a second fixture + test once a
  Monday scrape shows the full week, to confirm the `article`-per-day
  structure repeats as expected across multiple days in one page.
- **Occasional extra pizza variants** (e.g. a separate vegan pizza section
  on the same day) — not observed yet. Current parser only captures the
  block after the first `<h3>Pizza</h3>`; revisit if/when the real site
  does this.
- **(Stretch) Build the stats.** Once a few weeks of `data/*.json` exist:
  ingredient frequency counts, most common pizza combos, seasonal patterns.

## Non-goals
- No interest in salads — parser does not extract them.
- Not building a UI/dashboard right now, just the scrape + storage pipeline.
