#!/usr/bin/env python3
"""Scrape the Cheese Board Collective pizza schedule.

Pulls whatever days are currently shown on the schedule page (one on a
Saturday, the full week on a Monday), skips the salads, and writes one
JSON file per pizza date under a data directory, upserting each file as
that date gets re-scraped on subsequent runs. Closed days (weekly closures,
holidays) are written too, as {"closed": true} records, so their absence
from data/ can't be mistaken for "not scraped yet". The run only fails if
zero day-articles can be found at all, which means the page structure
itself changed, not that the pizzeria happened to be closed.

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
CLOSED_RE = re.compile(r"closed", re.IGNORECASE)


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
    menu_texts: list[str] = []
    for el in menu.find_all(["h3", "p"], recursive=False):
        text = el.get_text(" ", strip=True)
        menu_texts.append(text)
        if el.name == "h3":
            capturing = text.strip().lower() == "pizza"
            continue
        if capturing and text:
            ingredient_texts.append(text)

    if ingredient_texts:
        ingredients_raw = " ".join(ingredient_texts)
        ingredients, ingredients_normalized = parse_ingredients(ingredients_raw)
        return {
            "date": iso_date,
            "weekday": weekday,
            "closed": False,
            "ingredients_raw": ingredients_raw,
            "ingredients": ingredients,
            "ingredients_normalized": ingredients_normalized,
        }

    # No "<h3>Pizza</h3>" block found. The site marks closures (weekly
    # closed days, holidays) with a plain "The pizzeria is closed today."
    # paragraph and no heading at all — record that explicitly rather than
    # silently dropping the day, so a day of legitimate closures doesn't
    # look identical to zero days being scraped (which is a real failure).
    if CLOSED_RE.search(" ".join(menu_texts)):
        return {"date": iso_date, "weekday": weekday, "closed": True}

    # Some other, unrecognized menu shape — don't guess, just skip this day.
    return None


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


def load_days(data_dir: Path) -> list[dict]:
    """Load every day record on disk, e.g. to re-render the README table.

    Includes past dates — callers that want a narrower window should
    filter by date themselves (see render_schedule_table).
    """
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(data_dir.glob("*.json"))]


README_MARKER_START = "<!-- PIZZA-SCHEDULE:START -->"
README_MARKER_END = "<!-- PIZZA-SCHEDULE:END -->"


def week_start(today: dt.date) -> dt.date:
    """The Monday of the week `today` falls in."""
    return today - dt.timedelta(days=today.weekday())


def render_schedule_table(days: list[dict], today: dt.date) -> str:
    """Render a markdown table of this week's and future days, soonest first.

    The cutoff is the Monday of the current week, not today, so the days
    already gone by this week stay in the table instead of disappearing one
    at a time — the whole week reads as a unit, and rows only drop off when
    a new week starts. Closed days are shown too (so e.g. a weekly closure
    doesn't look like a gap), just without a pizza column value.
    """
    cutoff = week_start(today)
    shown = sorted(
        (day for day in days if dt.date.fromisoformat(day["date"]) >= cutoff),
        key=lambda day: day["date"],
    )
    if not shown:
        return "_No pizza schedule posted yet._"

    lines = ["| Date | Day | Pizza |", "| --- | --- | --- |"]
    for day in shown:
        pizza = "_Closed_" if day.get("closed", False) else ", ".join(day["ingredients"])
        lines.append(f"| {day['date']} | {day['weekday']} | {pizza} |")
    return "\n".join(lines)


def update_readme(readme_path: Path, table: str) -> None:
    text = readme_path.read_text(encoding="utf-8")
    if README_MARKER_START not in text or README_MARKER_END not in text:
        raise SystemExit(
            f"couldn't find {README_MARKER_START!r} / {README_MARKER_END!r} markers in {readme_path}"
        )
    pattern = re.compile(re.escape(README_MARKER_START) + r".*?" + re.escape(README_MARKER_END), re.DOTALL)
    new_text = pattern.sub(f"{README_MARKER_START}\n{table}\n{README_MARKER_END}", text, count=1)
    readme_path.write_text(new_text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir", default="data", help="directory to upsert one <date>.json file per pizza into (default: data)"
    )
    parser.add_argument("--print", dest="do_print", action="store_true", help="also print the scraped days as JSON")
    parser.add_argument(
        "--readme",
        help="if set, rewrite the upcoming-pizza table between the PIZZA-SCHEDULE markers in this README file",
    )
    args = parser.parse_args()

    soup = fetch_soup()
    days = parse_schedule(soup)

    if not days:
        print("No pizza entries found — the page structure may have changed.", file=sys.stderr)
        sys.exit(1)

    data_dir = Path(args.data_dir)
    written = write_days(days, data_dir)
    for path in written:
        print(f"wrote {path}", file=sys.stderr)

    if args.readme:
        table = render_schedule_table(load_days(data_dir), dt.date.today())
        update_readme(Path(args.readme), table)
        print(f"updated {args.readme}", file=sys.stderr)

    if args.do_print:
        print(json.dumps(days, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
