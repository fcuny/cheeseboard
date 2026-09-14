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


def test_full_week_fixture():
    # Real page captured 2026-09-14 (a Monday) — the first observed case of
    # a full week listed at once: a closed Monday, five real pizza days,
    # and a closed Sunday. Confirms the article-per-day structure holds
    # across multiple days on one page, not just the single-day case.
    soup = load("full_week.html")
    today = dt.date(2026, 9, 14)

    days = sc.parse_schedule(soup, today=today)

    assert [(d["date"], d["weekday"], d["closed"]) for d in days] == [
        ("2026-09-14", "Mon", True),
        ("2026-09-15", "Tue", False),
        ("2026-09-16", "Wed", False),
        ("2026-09-17", "Thu", False),
        ("2026-09-18", "Fri", False),
        ("2026-09-19", "Sat", False),
        ("2026-09-20", "Sun", True),
    ]

    pizza_days = {d["date"]: d for d in days if not d["closed"]}

    # Spot-check parenthetical asides are stripped even when the source
    # wraps them in inline <b>/<i> tags (e.g. Saturday's allergen footnote).
    tuesday = pizza_days["2026-09-15"]
    assert tuesday["ingredients"] == [
        "Cremini mushroom",
        "leek",
        "mozzarella",
        "garlic olive oil",
        "Montalbán cheese",
        "parsley",
    ]

    saturday = pizza_days["2026-09-19"]
    assert saturday["ingredients"] == [
        "House made Romesco sauce",
        "organic zucchini",
        "red onion",
        "Valbreso feta cheese",
        "mozzarella",
    ]
    assert not any("almond" in i.lower() for i in saturday["ingredients"])

    # Wednesday's salad has its own "(dressing contains dairy)" footnote and
    # a "spicy citrus crema dressing" line — none of it should leak into the
    # pizza day.
    wednesday = pizza_days["2026-09-16"]
    assert not any("dairy" in i.lower() or "crema dressing" in i.lower() for i in wednesday["ingredients"])


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
