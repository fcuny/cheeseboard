# cheeseboard

Daily scrape of the [Cheese Board Collective](https://cheeseboardcollective.coop/pizza/pizza-schedule/)
pizza schedule, for fun future stats (ingredient frequency, favorite combos, etc).
Salads are ignored on purpose.

A GitHub Action runs `scrape_cheeseboard.py` once a day. Each pizza is written to
`data/<pizza-date>.json`, keyed by the pizza's own date and upserted — since the
site usually lists the whole upcoming week at once, most days get scraped more
than once before their date arrives, and the file for that date is simply
overwritten each time. The same run also rewrites the table below from
`data/`, showing this week (Monday onwards, including days already gone by)
plus anything further ahead the site has posted. Rows only drop off when a
new week starts, so the whole week stays readable rather than shrinking a
day at a time — the full history lives in `data/` regardless.

## This week's pizzas

<!-- PIZZA-SCHEDULE:START -->
| Date | Day | Pizza |
| --- | --- | --- |
| 2026-10-19 | Mon | _Closed_ |
| 2026-10-20 | Tue | Cremini mushroom, red onion, Fontina and Voralberger Bergkäse cheese, mozzarella, garlic olive oil, oregano, parsley |
| 2026-10-21 | Wed | Organic heirloom tomato, fresh mozzarella made in Berkeley by Belfiore, mozzarella, garlic olive oil, basil |
| 2026-10-22 | Thu | Broccolini, red onion, cheddar cheese, mozzarella, garlic olive oil, organic lemon zest, parsley |
| 2026-10-23 | Fri | Organic baby chard and kale, leek, mozzarella, Montalbán cheese, garlic olive oil, organic orange and lemon zest, parsley |
| 2026-10-24 | Sat | Organic heirloom tomato, local corn, mozzarella, garlic olive oil, basil-Parmesan |
| 2026-10-25 | Sun | _Closed_ |
| 2026-10-26 | Mon | _Closed_ |
<!-- PIZZA-SCHEDULE:END -->

## Files

- `scrape_cheeseboard.py` — fetches the schedule page and parses each day's
  pizza (skips salads).
- `scrape-pizza.yml` — the GitHub Actions workflow (goes in
  `.github/workflows/`).
- `tests/` — unit tests against saved HTML fixtures of the real page.
- `data/` — one JSON file per pizza date, either a normal day:

  ```json
  {
    "date": "2026-09-12",
    "weekday": "Sat",
    "closed": false,
    "ingredients_raw": "Organic corn (Avalos Farm), red onion, mozzarella, ...",
    "ingredients": ["Organic corn", "red onion", "mozzarella", "..."],
    "ingredients_normalized": ["organic corn", "red onion", "mozzarella", "..."]
  }
  ```

  or a closed day (weekly closure, holiday, or next week's schedule not
  posted yet — the site marks all of these the same way, with no "Pizza"
  heading and a "The pizzeria is closed today." paragraph):

  ```json
  { "date": "2026-09-14", "weekday": "Mon", "closed": true }
  ```

  The scraper only fails (non-zero exit) when it can't find *any*
  recognizable day on the page at all — a real sign the site's structure
  changed, not that the pizzeria happened to be closed.
- `ingredients.toml` — hand-maintained ingredient taxonomy: maps each
  scraped `ingredients_normalized` string to a canonical ingredient and a
  category (cheese, produce, sauce, ...), so "organic tomato" and "organic
  heirloom tomato" count as one Tomato. A scrape that brings in an unknown
  ingredient lists it in the PR body; add it here on the PR branch before
  merging.
- `stats.py` + `build_site.py` + `templates/` — build the static stats site
  (today's pizza with "last seen" context, closest earlier pizza, this
  week, per-category leaderboards, rarities, most similar pizzas,
  ingredient-by-week table, and a page per day and per ingredient).
- `build-site.yml` — builds the site and deploys it to GitHub Pages on
  every push to `main` that touches the data or the site, plus once a day
  so "today" keeps moving.

## Local dev

Dependencies and script execution are managed with [uv](https://docs.astral.sh/uv/).

```
uv sync
uv run pytest
uv run scrape_cheeseboard.py --print
uv run scrape_cheeseboard.py --readme README.md  # also refresh the table above
uv run build_site.py                             # build the site into _site/
uv run build_site.py --today 2026-10-15          # ... as if it were another day
uv run build_site.py --list-unmapped             # ingredients missing from ingredients.toml
```
