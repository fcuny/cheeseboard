import datetime as dt
from pathlib import Path

import pytest

import build_site
import stats
from scrape_cheeseboard import load_days

ROOT = Path(__file__).parent.parent

TAXONOMY_TOML = """
[splits]
"corn and spinach" = ["corn", "spinach"]

[ingredients."Mozzarella"]
category = "base"
aliases = ["mozzarella"]

[ingredients."Corn"]
category = "produce"
aliases = ["corn", "local corn"]

[ingredients."Spinach"]
category = "produce"
aliases = ["spinach"]

[ingredients."Feta"]
category = "cheese"
aliases = ["feta"]

[ingredients."Parsley"]
category = "herb"
aliases = ["parsley"]
"""


@pytest.fixture
def taxonomy(tmp_path):
    path = tmp_path / "ingredients.toml"
    path.write_text(TAXONOMY_TOML, encoding="utf-8")
    return stats.load_taxonomy(path)


def day(date: str, *ingredients: str, weekday: str = "Tue") -> dict:
    return {
        "date": date,
        "weekday": weekday,
        "closed": False,
        "ingredients": list(ingredients),
        "ingredients_normalized": [i.lower() for i in ingredients],
    }


def closed(date: str, weekday: str = "Mon") -> dict:
    return {"date": date, "weekday": weekday, "closed": True}


def names(ingredients) -> list[str]:
    return [i.name for i in ingredients]


def test_taxonomy_covers_all_scraped_data():
    # Fails when a scrape brings in an ingredient nobody has mapped yet —
    # add it to ingredients.toml.
    taxonomy = stats.load_taxonomy(ROOT / "ingredients.toml")
    pizzas = stats.to_pizzas(load_days(ROOT / "data"), taxonomy)
    assert names(stats.unmapped(pizzas)) == []


def test_duplicate_alias_is_rejected(tmp_path):
    path = tmp_path / "ingredients.toml"
    path.write_text(
        '[ingredients."A"]\ncategory = "cheese"\naliases = ["x"]\n'
        '[ingredients."B"]\ncategory = "cheese"\naliases = ["x"]\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="'x'"):
        stats.load_taxonomy(path)


def test_resolve_aliases_splits_and_unmapped(taxonomy):
    [pizza] = stats.to_pizzas([day("2026-09-15", "Local corn", "Corn and spinach", "Truffle")], taxonomy)
    # "Local corn" and the corn half of the split collapse into one Corn;
    # the split keeps the site's original wording for both halves.
    assert pizza.items == [
        (stats.Ingredient("Corn", "produce"), "Local corn"),
        (stats.Ingredient("Spinach", "produce"), "Corn and spinach"),
        (stats.Ingredient("truffle", "unmapped"), "Truffle"),
    ]
    assert names(stats.unmapped([pizza])) == ["truffle"]


def test_records_without_closed_key_count_as_open(taxonomy):
    record = day("2026-09-12", "Corn")
    del record["closed"]
    assert len(stats.to_pizzas([record, closed("2026-09-13")], taxonomy)) == 1


def test_compare_ignores_base(taxonomy):
    a, b = stats.to_pizzas(
        [day("2026-09-15", "Corn", "Feta", "Mozzarella"), day("2026-09-16", "Corn", "Parsley")], taxonomy
    )
    match = stats.compare(b, a)
    assert match.score == pytest.approx(1 / 3)
    assert names(match.shared) == ["Corn"]
    assert names(match.only_pizza) == ["Parsley"]
    assert names(match.only_other) == ["Feta"]


def test_closest_earlier_only_looks_back_and_prefers_recent_ties(taxonomy):
    pizzas = stats.to_pizzas(
        [
            day("2026-09-15", "Corn", "Feta"),
            day("2026-09-16", "Corn", "Feta"),
            day("2026-09-17", "Spinach"),
            day("2026-09-18", "Corn", "Feta"),
            day("2026-09-19", "Corn", "Feta"),
        ],
        taxonomy,
    )
    match = stats.closest_earlier(pizzas[3], pizzas)
    assert match.other.date == dt.date(2026, 9, 16)
    assert match.score == 1.0
    assert stats.closest_earlier(pizzas[0], pizzas) is None
    # Nothing in common with anything earlier counts as no match.
    assert stats.closest_earlier(pizzas[2], pizzas) is None


def test_ingredient_context(taxonomy):
    pizzas = stats.to_pizzas(
        [day("2026-09-15", "Corn"), day("2026-09-18", "Corn"), day("2026-09-22", "Corn", "Feta")], taxonomy
    )
    corn, feta = stats.ingredient_context(pizzas[2], pizzas)
    assert (corn.times_before, corn.last_seen, corn.days_since) == (2, dt.date(2026, 9, 18), 4)
    assert (feta.times_before, feta.last_seen, feta.days_since) == (0, None, None)


def test_leaderboards_skip_base_and_rarities(taxonomy):
    pizzas = stats.to_pizzas(
        [day("2026-09-15", "Corn", "Mozzarella"), day("2026-09-16", "Corn", "Feta", "Mozzarella")], taxonomy
    )
    boards = stats.leaderboards(pizzas)
    assert list(boards) == ["cheese", "produce"]
    assert [(s.ingredient.name, s.count) for s in boards["produce"]] == [("Corn", 2)]
    assert names(a.ingredient for a in stats.rarities(pizzas)) == ["Feta"]
    assert [(s.ingredient.name, s.count) for s in stats.base_counts(pizzas)] == [("Mozzarella", 2)]


def test_seasonality_keeps_empty_weeks(taxonomy):
    pizzas = stats.to_pizzas([day("2026-09-15", "Corn"), day("2026-09-30", "Corn", "Feta")], taxonomy)
    season = stats.seasonality(pizzas)
    assert season.weeks == [dt.date(2026, 9, 14), dt.date(2026, 9, 21), dt.date(2026, 9, 28)]
    assert [(i.name, counts) for i, counts in season.rows] == [("Feta", [0, 0, 1]), ("Corn", [1, 0, 1])]


def test_seasonality_filters_and_keeps_top_per_category(taxonomy):
    pizzas = stats.to_pizzas(
        [
            day("2026-09-15", "Corn", "Spinach", "Feta"),
            day("2026-09-22", "Corn", "Parsley"),
            day("2026-09-29", "Spinach"),
        ],
        taxonomy,
    )
    season = stats.seasonality(pizzas, categories=("produce", "herb"), per_category=1)
    # Corn and Spinach tie on 2 pizzas; Spinach was seen more recently.
    # Feta's category isn't asked for at all.
    assert names(i for i, _ in season.rows) == ["Spinach", "Parsley"]
    assert len(season.weeks) == 3


def test_leaderboards_only_requested_categories(taxonomy):
    pizzas = stats.to_pizzas([day("2026-09-15", "Corn", "Feta", "Parsley")], taxonomy)
    assert list(stats.leaderboards(pizzas, ("herb", "cheese"))) == ["herb", "cheese"]


def test_leaderboards_keep_top_per_category(taxonomy):
    pizzas = stats.to_pizzas(
        [day("2026-09-15", "Corn", "Spinach"), day("2026-09-16", "Corn"), day("2026-09-17", "Spinach")], taxonomy
    )
    # Tie on 2 pizzas each; Spinach was seen more recently.
    [top] = stats.leaderboards(pizzas, ("produce",), per_category=1)["produce"]
    assert (top.ingredient.name, top.count) == ("Spinach", 2)


def test_coverage_reports_missing_dates(taxonomy):
    days = [day("2026-10-09", "Corn"), day("2026-10-10", "Feta"), closed("2026-10-12")]
    cov = stats.coverage(days, stats.to_pizzas(days, taxonomy))
    assert (cov.pizzas, cov.closed) == (2, 1)
    assert cov.missing == [dt.date(2026, 10, 11)]


@pytest.mark.parametrize(
    "today, expected",
    [
        (dt.date(2026, 9, 15), dt.date(2026, 9, 15)),  # open today
        (dt.date(2026, 9, 14), dt.date(2026, 9, 15)),  # closed today, next one posted
        (dt.date(2026, 9, 20), dt.date(2026, 9, 16)),  # nothing posted ahead, show the latest
    ],
)
def test_featured_pizza(taxonomy, today, expected):
    pizzas = stats.to_pizzas([day("2026-09-15", "Corn"), day("2026-09-16", "Feta")], taxonomy)
    assert build_site.featured_pizza(pizzas, today).date == expected


def test_build_real_data(tmp_path):
    out = tmp_path / "site"
    (out / "stale.html").parent.mkdir()
    (out / "stale.html").write_text("old")
    days = load_days(ROOT / "data")
    build_site.build(days, stats.load_taxonomy(ROOT / "ingredients.toml"), out, dt.date(2026, 10, 15))

    assert not (out / "stale.html").exists()
    index = (out / "index.html").read_text(encoding="utf-8")
    assert "Today · Thu Oct 15, 2026" in index
    assert (out / "style.css").exists()
    assert (out / "days" / "2026-10-15.html").exists()
    assert (out / "ingredients" / "valbreso-feta.html").exists()
    assert (out / "ingredients" / "montalban.html").exists()
    # Every pizza day gets a page; closed days don't.
    pizza_days = [d for d in days if not d.get("closed", False)]
    assert len(list((out / "days").glob("2026-*.html"))) == len(pizza_days)
