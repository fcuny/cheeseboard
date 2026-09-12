#!/usr/bin/env python3
"""Scrape the Cheese Board Collective pizza schedule.

Pulls whatever days are currently shown on the schedule page (one on a
Saturday, the full week on a Monday), skips the salads, and writes one
JSON file per pizza date under a data directory, upserting each file as
that date gets re-scraped on subsequent runs.

Usage:
    python scrape_cheeseboard.py                # write to ./data/
    python scrape_cheeseboard.py --data-dir out  # write to ./out/ instead
    python scrape_cheeseboard.py --print         # also print what was scraped
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

URL = "https://cheeseboardcollective.coop/pizza/pizza-schedule/"

DATE_RE = re.compile(
    r"^(Sun|Mon|Tue|Wed|Thu|Fri|Sat)\s+"
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})$"
)
PAREN_RE = re.compile(r"\([^)]*\)")
WHITESPACE_RE = re.compile(r"\s+")


def fetch_soup(url: str = URL) -> BeautifulSoup:
    resp = requests.get(url, timeout=15, headers={"User-Agent": "cheeseboard-pizza-stats/1.0"})
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def resolve_year(month_abbr: str, day: int, today: dt.date) -> int:
    """The site never prints a year — infer it relative to today.

    A date that would land more than ~60 days in the past almost
    certainly belongs to next year's schedule (only matters at the
    Dec -> Jan boundary).
    """
    month = dt.datetime.strptime(month_abbr, "%b").month
    candidate = dt.date(today.year, month, day)
    if (today - candidate).days > 60:
        candidate = candidate.replace(year=today.year + 1)
    return candidate.year


def normalize_ingredient(raw: str) -> str:
    """Lowercase/whitespace-collapse an ingredient for stats matching.

    Deliberately mild: no attempt to strip descriptors like "organic" or
    "house made" since that's real information about the ingredient, not
    noise. Just enough to make "Mozzarella" and "mozzarella " compare equal.
    """
    text = WHITESPACE_RE.sub(" ", raw).strip().strip(".").strip()
    return text.lower()


def parse_ingredients(text: str) -> tuple[list[str], list[str]]:
    """Split an ingredient paragraph into raw and normalized lists.

    Parenthetical asides (farm attributions, vegan/cashew footnotes) are
    stripped before splitting on commas — they're sourcing notes, not
    ingredients.
    """
    cleaned = PAREN_RE.sub("", text)
    raw_parts = [part.strip(" .") for part in cleaned.split(",") if part.strip(" .")]
    normalized = [normalize_ingredient(part) for part in raw_parts]
    return raw_parts, normalized


def parse_day(article, today: dt.date) -> dict | None:
    date_p = article.select_one("div.date p")
    menu = article.select_one("div.menu")
    if date_p is None or menu is None:
        return None

    m = DATE_RE.match(date_p.get_text(" ", strip=True))
    if not m:
        return None
    weekday, month_abbr, day_str = m.groups()
    day = int(day_str)
    year = resolve_year(month_abbr, day, today)
    month = dt.datetime.strptime(month_abbr, "%b").month
    iso_date = dt.date(year, month, day).isoformat()

    # Walk the menu's headings/paragraphs in order: capture the paragraph(s)
    # between "<h3>Pizza</h3>" and the next heading (usually "<h3>Salad</h3>").
    # Skips announcement text (e.g. "special-hours-pizza") outside that span.
    capturing = False
    ingredient_texts: list[str] = []
    for el in menu.find_all(["h3", "p"], recursive=False):
        text = el.get_text(" ", strip=True)
        if el.name == "h3":
            capturing = text.strip().lower() == "pizza"
            continue
        if capturing and text:
            ingredient_texts.append(text)

    if not ingredient_texts:
        # A day can go by with no pizza listed (holiday/closure) — skip it.
        return None

    ingredients_raw = " ".join(ingredient_texts)
    ingredients, ingredients_normalized = parse_ingredients(ingredients_raw)

    return {
        "date": iso_date,
        "weekday": weekday,
        "ingredients_raw": ingredients_raw,
        "ingredients": ingredients,
        "ingredients_normalized": ingredients_normalized,
    }


def parse_schedule(soup: BeautifulSoup, today: dt.date | None = None) -> list[dict]:
    today = today or dt.date.today()
    days = []
    for article in soup.select("div.daily-pizza article"):
        day = parse_day(article, today)
        if day is not None:
            days.append(day)
    return days


def write_days(days: list[dict], data_dir: Path) -> list[Path]:
    data_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for day in days:
        path = data_dir / f"{day['date']}.json"
        path.write_text(json.dumps(day, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        written.append(path)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir", default="data", help="directory to upsert one <date>.json file per pizza into (default: data)"
    )
    parser.add_argument("--print", dest="do_print", action="store_true", help="also print the scraped days as JSON")
    args = parser.parse_args()

    soup = fetch_soup()
    days = parse_schedule(soup)

    if not days:
        print("No pizza entries found — the page structure may have changed.", file=sys.stderr)
        sys.exit(1)

    written = write_days(days, Path(args.data_dir))
    for path in written:
        print(f"wrote {path}", file=sys.stderr)

    if args.do_print:
        print(json.dumps(days, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
