# Cheese Board pizza scraper — plan for Claude Code

## Goal
Daily-scrape https://cheeseboardcollective.coop/pizza/pizza-schedule/, extract
each day's pizza (name/date + ingredient list), skip salads, store results as
data for later stats. Runs as a scheduled GitHub Action.

## Starting point (already drafted, needs verification)
Two files are attached / included in this repo checkout:
- `scrape_cheeseboard.py` — parser, walks headings/paragraphs looking for a
  date line (`Fri Sep 11` style, no year), a `Pizza` heading, and the
  ingredient paragraph that follows it. Ignores `Salad` headings entirely.
- `scrape-pizza.yml` — GitHub Actions workflow: daily cron, runs the script,
  writes `data/<date>.json`, commits and pushes.

These were written **without ever seeing the live page's raw HTML** (only a
markdown-converted rendering of it), so the heading/tag assumptions
(`<h3>Pizza</h3>`, date as its own block-level element) are best-guesses, not
verified. Fixing that is step 1 below.

## Tasks

1. **Verify against the real DOM.** Fetch the live page and inspect actual
   tag names/classes for: the per-day container, the date text, the "Pizza"
   and "Salad" headings, and the ingredient paragraph. Adjust the BeautifulSoup
   selectors in `scrape_cheeseboard.py` to match reality (prefer scoping to
   whatever div/section wraps each day, rather than the current heuristic of
   walking all h1-h4/p tags on the page — that heuristic is a fallback, not
   the ideal).

2. **Handle edge cases found in the real markup:**
   - Year inference at the Dec→Jan boundary (`resolve_year` has a first pass
     at this — confirm it actually works with a couple of hand-written test
     dates).
   - Parenthetical asides embedded in the ingredient text (e.g. vegan/cashew
     footnotes) — currently stripped via regex before splitting on commas;
     confirm this doesn't eat real ingredients that happen to be in
     parentheses.
   - Days with no pizza (holidays/closures) — should be skipped without
     crashing.
   - Occasional extra pizza variants on the same day (e.g. a separate vegan
     pizza section), if the real site does this — decide whether to capture
     them as a second record or ignore.

3. **Add tests.** Save 2-3 real HTML fixtures (a normal day, a day with an
   announcement banner, a day with a parenthetical footnote) and write unit
   tests against `parse_schedule()` so future site redesigns fail loudly in
   CI instead of silently producing empty/wrong data.

4. **Decide on storage/dedup strategy.** Current plan is one JSON file per
   scraped date under `data/`. Since the site shows several upcoming days at
   once, daily runs will re-scrape days already captured — confirm that's
   fine (idempotent overwrite) or add a check to skip re-writing unchanged
   files.

5. **Wire up the GitHub Action.** Confirm repo permissions allow the workflow
   to commit back (`contents: write`), confirm the cron time makes sense
   against when the site actually updates its schedule, and add a failure
   notification (the script exits 1 with nothing scraped — hook that up to
   a Slack webhook, email, or just rely on GitHub's own failed-workflow
   notification).

6. **(Stretch) Build the stats.** Once a few weeks of `data/*.json` exist:
   ingredient frequency counts, most common pizza combos, seasonal patterns.
   Not urgent — only worth doing once there's real data to look at.

## Non-goals
- No interest in salads — parser should not bother extracting them.
- Not building a UI/dashboard right now, just the scrape + storage pipeline.
