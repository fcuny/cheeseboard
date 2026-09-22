# cheeseboard

Daily scrape of the [Cheese Board Collective](https://cheeseboardcollective.coop/pizza/pizza-schedule/)
pizza schedule, for fun future stats (ingredient frequency, favorite combos, etc).
Salads are ignored on purpose.

A GitHub Action runs `scrape_cheeseboard.py` once a day. Each pizza is written to
`data/<pizza-date>.json`, keyed by the pizza's own date and upserted — since the
site usually lists the whole upcoming week at once, most days get scraped more
than once before their date arrives, and the file for that date is simply
overwritten each time. The same run also rewrites the table below with
whatever's currently upcoming in `data/`.

## Upcoming pizzas

<!-- PIZZA-SCHEDULE:START -->
| Date | Day | Pizza |
| --- | --- | --- |
| 2026-09-22 | Tue | Organic zucchini, roasted leek and onion, Valbreso feta cheese, mozzarella, garlic olive oil, organic lemon and orange zest, parsley |
| 2026-09-23 | Wed | Organic corn and baby spinach, mozzarella, house made coconut curry sauce, lime, cilantro |
| 2026-09-24 | Thu | Organic sweet bell pepper, yellow onion, Kalamata olive, Capricho de Cabra goat cheese, mozzarella, garlic olive oil, parsley |
| 2026-09-25 | Fri | Cremini mushroom, red onion, mozzarella, toasted garlic Parmesan, garlic olive oil, oregano, parsley |
| 2026-09-26 | Sat | Organic tomato, red onion, Raclette cheese, mozzarella, garlic olive oil, oregano, parsley |
| 2026-09-27 | Sun | _Closed_ |
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

## Local dev

Dependencies and script execution are managed with [uv](https://docs.astral.sh/uv/).

```
uv sync
uv run pytest
uv run scrape_cheeseboard.py --print
uv run scrape_cheeseboard.py --readme README.md  # also refresh the table above
```
