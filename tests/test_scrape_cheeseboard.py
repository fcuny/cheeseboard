import datetime as dt
import json
from pathlib import Path

import pytest
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


def test_render_schedule_table_skips_earlier_weeks_and_marks_closed():
    days = [
        {"date": "2026-09-13", "weekday": "Sun", "closed": True},
        {"date": "2026-09-14", "weekday": "Mon", "closed": True},
        {"date": "2026-09-15", "weekday": "Tue", "closed": False, "ingredients": ["leek", "mozzarella"]},
    ]
    table = sc.render_schedule_table(days, today=dt.date(2026, 9, 14))

    assert "2026-09-13" not in table  # belongs to the previous week
    lines = table.splitlines()
    assert lines[0] == "| Date | Day | Pizza |"
    assert "| 2026-09-14 | Mon | _Closed_ |" in lines
    assert "| 2026-09-15 | Tue | leek, mozzarella |" in lines


def test_render_schedule_table_keeps_earlier_days_of_the_current_week():
    # Thursday: Monday through Wednesday have already passed, but they're
    # this week's pizzas and should still be in the table.
    days = [
        {"date": "2026-09-13", "weekday": "Sun", "closed": True},
        {"date": "2026-09-14", "weekday": "Mon", "closed": True},
        {"date": "2026-09-15", "weekday": "Tue", "closed": False, "ingredients": ["leek"]},
        {"date": "2026-09-16", "weekday": "Wed", "closed": False, "ingredients": ["corn"]},
        {"date": "2026-09-17", "weekday": "Thu", "closed": False, "ingredients": ["olive"]},
        {"date": "2026-09-18", "weekday": "Fri", "closed": False, "ingredients": ["cremini"]},
    ]
    table = sc.render_schedule_table(days, today=dt.date(2026, 9, 17))

    assert "2026-09-13" not in table  # previous week, dropped
    rows = [line.split(" | ")[0].removeprefix("| ") for line in table.splitlines()[2:]]
    assert rows == ["2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18"]


def test_render_schedule_table_keeps_whole_week_on_sunday():
    # Sunday is the last day of the week, so nothing has rolled off yet.
    days = [
        {"date": "2026-09-14", "weekday": "Mon", "closed": True},
        {"date": "2026-09-20", "weekday": "Sun", "closed": True},
    ]
    table = sc.render_schedule_table(days, today=dt.date(2026, 9, 20))

    assert "| 2026-09-14 | Mon | _Closed_ |" in table
    assert "| 2026-09-20 | Sun | _Closed_ |" in table


@pytest.mark.parametrize(
    "today,expected",
    [
        ("2026-09-14", "2026-09-14"),  # Monday — already the start of the week
        ("2026-09-17", "2026-09-14"),  # Thursday
        ("2026-09-20", "2026-09-14"),  # Sunday — still the same week
        ("2026-09-21", "2026-09-21"),  # the next Monday — a new week
    ],
)
def test_week_start_is_the_monday_of_that_week(today, expected):
    assert sc.week_start(dt.date.fromisoformat(today)) == dt.date.fromisoformat(expected)


def test_render_schedule_table_treats_missing_closed_key_as_open():
    # Older records (scraped before the "closed" field existed) omit it.
    days = [{"date": "2026-09-15", "weekday": "Tue", "ingredients": ["leek"]}]
    table = sc.render_schedule_table(days, today=dt.date(2026, 9, 15))
    assert "| 2026-09-15 | Tue | leek |" in table


def test_render_schedule_table_empty_when_nothing_this_week_or_later():
    days = [{"date": "2026-09-13", "weekday": "Sun", "closed": True}]
    table = sc.render_schedule_table(days, today=dt.date(2026, 9, 14))
    assert table == "_No pizza schedule posted yet._"


def test_update_readme_replaces_only_between_markers(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text(
        "before\n"
        f"{sc.README_MARKER_START}\n"
        "stale table\n"
        f"{sc.README_MARKER_END}\n"
        "after\n",
        encoding="utf-8",
    )

    sc.update_readme(readme, "fresh table")

    text = readme.read_text(encoding="utf-8")
    assert "before\n" in text
    assert "after\n" in text
    assert "stale table" not in text
    assert f"{sc.README_MARKER_START}\nfresh table\n{sc.README_MARKER_END}" in text


def test_update_readme_raises_if_markers_missing(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text("no markers here\n", encoding="utf-8")

    with pytest.raises(SystemExit):
        sc.update_readme(readme, "fresh table")


def test_load_days_reads_every_file_in_data_dir(tmp_path):
    (tmp_path / "2026-09-15.json").write_text(
        json.dumps({"date": "2026-09-15", "weekday": "Tue", "closed": True}), encoding="utf-8"
    )
    (tmp_path / "2026-09-16.json").write_text(
        json.dumps({"date": "2026-09-16", "weekday": "Wed", "closed": True}), encoding="utf-8"
    )

    days = sc.load_days(tmp_path)

    assert [d["date"] for d in days] == ["2026-09-15", "2026-09-16"]
