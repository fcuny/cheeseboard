#!/usr/bin/env python3
"""Build the static stats site from data/ and ingredients.toml.

Writes plain HTML into an output directory (default: _site/):

    style.css                   copied from static/
    index.html                  today's pizza, this week, leaderboards, ...
    days/index.html             every scraped day
    days/<date>.html            one pizza day, with déjà vu and ingredient context
    ingredients/index.html      every ingredient, by category
    ingredients/<slug>.html     one ingredient's full history

"Today" is Berkeley time, since that's when the pizzeria's day turns over.
The home page is rendered for the build date, and static/today.js redoes its
date-dependent parts (featured pizza, this week) in the visitor's browser, so
the page stays right between builds.

Usage:
    python build_site.py                        # build into ./_site/
    python build_site.py --today 2026-10-15     # pretend it's another day
    python build_site.py --list-unmapped        # print ingredients missing from the taxonomy, build nothing
"""
from __future__ import annotations

import argparse
import datetime as dt
import shutil
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader, StrictUndefined

import stats
from scrape_cheeseboard import load_days, week_start

BERKELEY = ZoneInfo("America/Los_Angeles")
CHEESE_BOARD_URL = "https://cheeseboardcollective.coop/pizza/"
SCHEDULE_URL = "https://cheeseboardcollective.coop/pizza/pizza-schedule/"
TEMPLATES = Path(__file__).parent / "templates"
STATIC = Path(__file__).parent / "static"


def berkeley_today() -> dt.date:
    return dt.datetime.now(BERKELEY).date()


def featured_pizza(pizzas: list[stats.Pizza], today: dt.date) -> stats.Pizza | None:
    """Today's pizza; on a closed day the next one posted, else the latest one."""
    for pizza in pizzas:
        if pizza.date >= today:
            return pizza
    return pizzas[-1] if pizzas else None


def week_rows(days: list[dict], today: dt.date) -> list[dict]:
    """The days of `today`'s week, Monday through Sunday, then any later days posted.

    A date with no scraped record gets a {"missing": True} placeholder, so a
    gap shows up as "not posted yet" instead of silently vanishing. Mirrored
    by weekRows() in static/today.js.
    """
    by_date = {dt.date.fromisoformat(d["date"]): d for d in days}
    start = week_start(today)
    end = max([start + dt.timedelta(days=6), *(d for d in by_date if d > start)])
    rows = []
    for offset in range((end - start).days + 1):
        date = start + dt.timedelta(days=offset)
        rows.append(by_date.get(date) or {"date": date.isoformat(), "weekday": date.strftime("%a"), "missing": True})
    return rows


def today_status(days: list[dict], today: dt.date) -> str:
    """'open', 'closed' or 'missing' (nothing scraped for today)."""
    for d in days:
        if d["date"] == today.isoformat():
            return "closed" if d.get("closed", False) else "open"
    return "missing"


def make_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=True,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["day"] = lambda d: d.strftime("%a %b %-d, %Y")
    env.filters["short"] = lambda d: d.strftime("%b %-d")
    env.filters["isodate"] = dt.date.fromisoformat
    env.filters["pct"] = lambda x: f"{x:.0%}"
    env.globals["categories"] = stats.CATEGORIES
    env.globals["cheese_board_url"] = CHEESE_BOARD_URL
    env.globals["schedule_url"] = SCHEDULE_URL
    return env


def build(days: list[dict], taxonomy: stats.Taxonomy, out: Path, today: dt.date) -> None:
    pizzas = stats.to_pizzas(days, taxonomy)
    histories = stats.histories(pizzas)
    coverage = stats.coverage(days, pizzas)
    since = coverage.first if coverage else None
    env = make_env()

    def write(path: str, template: str, root: str, **context) -> None:
        target = out / path
        target.parent.mkdir(parents=True, exist_ok=True)
        html = env.get_template(template).render(root=root, today=today, since=since, **context)
        target.write_text(html, encoding="utf-8")

    def day_page(pizza: stats.Pizza) -> dict:
        return {
            "pizza": pizza,
            "context": stats.ingredient_context(pizza, pizzas),
            "match": stats.closest_earlier(pizza, pizzas),
        }

    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(STATIC, out)

    featured = featured_pizza(pizzas, today)
    cutoff = week_start(today)
    # Any later visitor's today is >= the build date, so their featured pizza
    # is one posted from today on, or else the latest one; render each of
    # those (hidden) for today.js to pick from.
    candidates = [p for p in pizzas if p.date >= today] or pizzas[-1:]
    write(
        "index.html",
        "index.html",
        root="",
        featured=featured,
        candidates=[day_page(p) for p in candidates],
        status=today_status(days, today),
        latest=max((dt.date.fromisoformat(d["date"]) for d in days), default=None),
        week=week_rows(days, today),
        schedule=[
            {k: d[k] for k in ("date", "weekday", "closed", "ingredients") if k in d}
            for d in sorted(days, key=lambda d: d["date"])
            if dt.date.fromisoformat(d["date"]) >= cutoff
        ],
        leaderboards=stats.leaderboards(pizzas, stats.FEATURED, per_category=5),
        base=stats.base_counts(pizzas),
        rarities=stats.rarities(pizzas),
        pairs=stats.most_similar_pairs(pizzas),
        seasonality=stats.seasonality(pizzas, stats.FEATURED, per_category=3),
        coverage=coverage,
        unmapped=stats.unmapped(pizzas),
        ingredient_count=len(histories),
    )

    write(
        "days/index.html",
        "days.html",
        root="../",
        days=sorted(days, key=lambda d: d["date"], reverse=True),
    )
    for pizza in pizzas:
        write(f"days/{pizza.date.isoformat()}.html", "day.html", root="../", **day_page(pizza))

    by_category = {
        category: sorted((i for i in histories if i.category == category), key=lambda i: i.name)
        for category in [stats.BASE, *stats.CATEGORIES]
    }
    write(
        "ingredients/index.html",
        "ingredients.html",
        root="../",
        by_category={c: items for c, items in by_category.items() if items},
        histories=histories,
    )
    for ingredient, appearances in histories.items():
        write(
            f"ingredients/{ingredient.slug}.html",
            "ingredient.html",
            root="../",
            ingredient=ingredient,
            appearances=list(reversed(appearances)),
            total=len(pizzas),
            variants=sorted({a.written for a in appearances}),
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", default="data", help="directory of scraped <date>.json files (default: data)")
    parser.add_argument("--taxonomy", default="ingredients.toml", help="ingredient taxonomy (default: ingredients.toml)")
    parser.add_argument("--out", default="_site", help="output directory, replaced on each build (default: _site)")
    parser.add_argument("--today", type=dt.date.fromisoformat, help="override today's date (default: today in Berkeley)")
    parser.add_argument(
        "--list-unmapped",
        action="store_true",
        help="print ingredients missing from the taxonomy as a markdown list (nothing if none) and exit",
    )
    args = parser.parse_args()

    days = load_days(Path(args.data_dir))
    taxonomy = stats.load_taxonomy(Path(args.taxonomy))

    if args.list_unmapped:
        for ingredient in stats.unmapped(stats.to_pizzas(days, taxonomy)):
            print(f"- `{ingredient.name}`")
        return

    out = Path(args.out)
    build(days, taxonomy, out, args.today or berkeley_today())
    print(f"built {out}/ from {len(days)} days", file=sys.stderr)


if __name__ == "__main__":
    main()
