import datetime as dt
from pathlib import Path

from bs4 import BeautifulSoup

import scrape_cheeseboard as sc

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> BeautifulSoup:
    html = (FIXTURES / name).read_text(encoding="utf-8")
    return BeautifulSoup(html, "html.parser")


def test_single_day_fixture():
    # Real page captured 2026-09-12 (a Saturday, end of the week — only one
    # day listed, with an announcement banner before the "Pizza" heading).
    soup = load("single_day.html")
    today = dt.date(2026, 9, 12)

    days = sc.parse_schedule(soup, today=today)

    assert len(days) == 1
    day = days[0]
    assert day["date"] == "2026-09-12"
    assert day["weekday"] == "Sat"
    assert day["closed"] is False
    assert "cilantro" in day["ingredients"]
    # Farm attribution and the vegan/cashew footnote are parenthetical asides,
    # not ingredients — should be stripped.
    assert not any("Avalos Farm" in i for i in day["ingredients"])
    assert not any("cashew" in i for i in day["ingredients"])
    # Salad should never show up.
    assert not any("cabbage" in i.lower() for i in day["ingredients"])
    # Normalized list is lowercased.
    assert day["ingredients_normalized"] == [i.lower() for i in day["ingredients"]]


def test_closed_days_fixture():
    # Real page captured 2026-09-13 (a Sunday — both Sunday and Monday show
    # "The pizzeria is closed today." with no "Pizza" heading at all, and
    # next week's schedule isn't posted yet). This must NOT be treated as a
    # scrape failure.
    soup = load("closed_days.html")
    today = dt.date(2026, 9, 13)

    days = sc.parse_schedule(soup, today=today)

    assert len(days) == 2
    assert [d["date"] for d in days] == ["2026-09-13", "2026-09-14"]
    for day in days:
        assert day["closed"] is True
        # Closed-day records carry no ingredient fields.
        assert "ingredients" not in day


def test_parse_schedule_returns_empty_when_page_structure_is_unrecognized():
    # No div.daily-pizza on the page at all — this is the real failure case
    # (site redesign), distinct from "every listed day happens to be closed".
    soup = BeautifulSoup("<html><body>nothing here</body></html>", "html.parser")
    assert sc.parse_schedule(soup, today=dt.date(2026, 9, 13)) == []


def test_resolve_year_handles_december_to_january_boundary():
    today = dt.date(2026, 12, 30)
    # A "Jan 2" listed near year-end belongs to next year.
    assert sc.resolve_year("Jan", 2, today) == 2027
    # A "Dec 29" listed near year-end belongs to this year.
    assert sc.resolve_year("Dec", 29, today) == 2026


def test_parse_ingredients_strips_parentheticals_only():
    raw = "Organic corn (Avalos Farm), red onion, mozzarella (a note, with a comma)"
    ingredients, normalized = sc.parse_ingredients(raw)
    assert ingredients == ["Organic corn", "red onion", "mozzarella"]
    assert normalized == ["organic corn", "red onion", "mozzarella"]
