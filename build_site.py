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
    write(
        "index.html",
        "index.html",
        root="",
        featured=day_page(featured) if featured else None,
        open_today=featured is not None and featured.date == today,
        week=sorted((d for d in days if dt.date.fromisoformat(d["date"]) >= cutoff), key=lambda d: d["date"]),
        leaderboards=stats.leaderboards(pizzas),
        base=stats.base_counts(pizzas),
        rarities=stats.rarities(pizzas),
        pairs=stats.most_similar_pairs(pizzas),
        seasonality=stats.seasonality(pizzas),
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
