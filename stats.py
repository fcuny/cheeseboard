"""Turn the scraped data/ records into the stats the site shows.

Everything here works on canonical ingredients from ingredients.toml rather
than the scraped strings, so "organic tomato" and "organic heirloom tomato"
count as the same thing. Ingredients missing from the taxonomy aren't
dropped: they become their own "unmapped" ingredient so they still show up
(and get flagged) instead of silently skewing the counts.
"""
from __future__ import annotations

import datetime as dt
import itertools
import re
import tomllib
import unicodedata
from dataclasses import dataclass
from pathlib import Path

# Display order of the leaderboards. "base" is deliberately absent: it's on
# (nearly) every pizza, so it would top every chart and say nothing.
CATEGORIES = {
    "cheese": "Cheese",
    "produce": "Produce",
    "allium": "Onions & co",
    "sauce": "Sauce",
    "nut": "Nuts",
    "herb": "Herbs",
    "citrus": "Citrus",
    "unmapped": "Unmapped",
}
BASE = "base"
UNMAPPED = "unmapped"

SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return SLUG_RE.sub("-", ascii_name.lower()).strip("-")


@dataclass(frozen=True)
class Ingredient:
    name: str
    category: str

    @property
    def slug(self) -> str:
        return slugify(self.name)


@dataclass
class Taxonomy:
    by_alias: dict[str, Ingredient]
    splits: dict[str, list[str]]

    def resolve(self, normalized: str) -> list[Ingredient]:
        parts = self.splits.get(normalized, [normalized])
        return [self.by_alias.get(part) or Ingredient(part, UNMAPPED) for part in parts]


def load_taxonomy(path: Path) -> Taxonomy:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    by_alias: dict[str, Ingredient] = {}
    for name, entry in data.get("ingredients", {}).items():
        ingredient = Ingredient(name, entry["category"])
        if ingredient.category != BASE and ingredient.category not in CATEGORIES:
            raise ValueError(f"{name!r}: unknown category {ingredient.category!r}")
        for alias in entry["aliases"]:
            if alias in by_alias:
                raise ValueError(f"alias {alias!r} listed under both {by_alias[alias].name!r} and {name!r}")
            by_alias[alias] = ingredient
    return Taxonomy(by_alias=by_alias, splits=data.get("splits", {}))


@dataclass
class Pizza:
    date: dt.date
    weekday: str
    # (canonical ingredient, how the site wrote it), in the site's order.
    items: list[tuple[Ingredient, str]]

    @property
    def ingredients(self) -> list[Ingredient]:
        return [ingredient for ingredient, _ in self.items]

    @property
    def toppings(self) -> frozenset[Ingredient]:
        """Non-base ingredients — what actually distinguishes one pizza from another."""
        return frozenset(i for i in self.ingredients if i.category != BASE)


def to_pizzas(days: list[dict], taxonomy: Taxonomy) -> list[Pizza]:
    """Open days only, oldest first."""
    pizzas = []
    for day in days:
        if day.get("closed", False):
            continue
        items = []
        for written, normalized in zip(day["ingredients"], day["ingredients_normalized"], strict=True):
            for ingredient in taxonomy.resolve(normalized):
                if ingredient not in (i for i, _ in items):
                    items.append((ingredient, written))
        pizzas.append(Pizza(dt.date.fromisoformat(day["date"]), day["weekday"], items))
    return sorted(pizzas, key=lambda p: p.date)


def unmapped(pizzas: list[Pizza]) -> list[Ingredient]:
    seen = {i for p in pizzas for i in p.ingredients if i.category == UNMAPPED}
    return sorted(seen, key=lambda i: i.name)


# --- per-ingredient history -------------------------------------------------


@dataclass
class Appearance:
    ingredient: Ingredient
    pizza: Pizza
    written: str


def histories(pizzas: list[Pizza]) -> dict[Ingredient, list[Appearance]]:
    """Every pizza each ingredient appeared on, oldest first."""
    result: dict[Ingredient, list[Appearance]] = {}
    for pizza in pizzas:
        for ingredient, written in pizza.items:
            result.setdefault(ingredient, []).append(Appearance(ingredient, pizza, written))
    return result


@dataclass
class IngredientContext:
    """How an ingredient on a given pizza relates to the pizzas before it."""

    ingredient: Ingredient
    written: str
    times_before: int
    last_seen: dt.date | None
    days_since: int | None


def ingredient_context(pizza: Pizza, pizzas: list[Pizza]) -> list[IngredientContext]:
    earlier = [p for p in pizzas if p.date < pizza.date]
    contexts = []
    for ingredient, written in pizza.items:
        dates = [p.date for p in earlier if ingredient in p.ingredients]
        last = max(dates) if dates else None
        days_since = (pizza.date - last).days if last else None
        contexts.append(IngredientContext(ingredient, written, len(dates), last, days_since))
    return contexts


# --- similarity ("déjà vu") -------------------------------------------------


@dataclass
class Match:
    pizza: Pizza
    other: Pizza
    score: float
    shared: list[Ingredient]
    only_pizza: list[Ingredient]
    only_other: list[Ingredient]


def by_name(ingredients) -> list[Ingredient]:
    return sorted(ingredients, key=lambda i: i.name)


def compare(pizza: Pizza, other: Pizza) -> Match:
    """Jaccard similarity of the two pizzas' toppings (base ingredients ignored)."""
    a, b = pizza.toppings, other.toppings
    union = a | b
    score = len(a & b) / len(union) if union else 0.0
    return Match(pizza, other, score, by_name(a & b), by_name(a - b), by_name(b - a))


def closest_earlier(pizza: Pizza, pizzas: list[Pizza]) -> Match | None:
    """The most similar pizza served before this one; ties go to the most recent."""
    candidates = [compare(pizza, p) for p in pizzas if p.date < pizza.date]
    candidates = [m for m in candidates if m.score > 0]
    if not candidates:
        return None
    return max(candidates, key=lambda m: (m.score, m.other.date))


def most_similar_pairs(pizzas: list[Pizza], limit: int = 5) -> list[Match]:
    """Closest pairs of distinct pizza days ever, newest pizza first within each pair."""
    matches = [compare(b, a) for a, b in itertools.combinations(pizzas, 2)]
    matches.sort(key=lambda m: (m.score, m.pizza.date), reverse=True)
    return [m for m in matches if m.score > 0][:limit]


# --- leaderboards ------------------------------------------------------------


@dataclass
class Standing:
    ingredient: Ingredient
    count: int
    last_seen: dt.date


def leaderboards(pizzas: list[Pizza]) -> dict[str, list[Standing]]:
    """Per category (in CATEGORIES order), ingredients by how many pizzas they were on."""
    hist = histories(pizzas)
    boards: dict[str, list[Standing]] = {}
    for category in CATEGORIES:
        standings = [
            Standing(ingredient, len(apps), apps[-1].pizza.date)
            for ingredient, apps in hist.items()
            if ingredient.category == category
        ]
        if standings:
            standings.sort(key=lambda s: (-s.count, -s.last_seen.toordinal(), s.ingredient.name))
            boards[category] = standings
    return boards


def base_counts(pizzas: list[Pizza]) -> list[Standing]:
    hist = histories(pizzas)
    standings = [
        Standing(ingredient, len(apps), apps[-1].pizza.date)
        for ingredient, apps in hist.items()
        if ingredient.category == BASE
    ]
    return sorted(standings, key=lambda s: -s.count)


def rarities(pizzas: list[Pizza]) -> list[Appearance]:
    """Non-base ingredients seen on exactly one pizza, newest first."""
    once = [apps[0] for i, apps in histories(pizzas).items() if len(apps) == 1 and i.category != BASE]
    return sorted(once, key=lambda a: a.pizza.date, reverse=True)


# --- seasonality ----------------------------------------------------------


def week_of(date: dt.date) -> dt.date:
    return date - dt.timedelta(days=date.weekday())


@dataclass
class Seasonality:
    weeks: list[dt.date]  # Mondays, oldest first, with no gaps
    rows: list[tuple[Ingredient, list[int]]]  # pizzas per week, aligned with weeks


def seasonality(pizzas: list[Pizza]) -> Seasonality:
    """Ingredient × week counts, so seasonal swaps show up as the history grows."""
    if not pizzas:
        return Seasonality([], [])
    first, last = week_of(pizzas[0].date), week_of(pizzas[-1].date)
    weeks = [first + dt.timedelta(weeks=n) for n in range((last - first).days // 7 + 1)]
    index = {week: n for n, week in enumerate(weeks)}
    counts: dict[Ingredient, list[int]] = {}
    for pizza in pizzas:
        for ingredient in pizza.toppings:
            counts.setdefault(ingredient, [0] * len(weeks))[index[week_of(pizza.date)]] += 1
    order = list(CATEGORIES)
    rows = sorted(counts.items(), key=lambda kv: (order.index(kv[0].category), -sum(kv[1]), kv[0].name))
    return Seasonality(weeks, rows)


# --- coverage -------------------------------------------------------------


@dataclass
class Coverage:
    first: dt.date
    last: dt.date
    pizzas: int
    closed: int
    missing: list[dt.date]  # dates in [first, last] with no record at all
    avg_ingredients: float


def coverage(days: list[dict], pizzas: list[Pizza]) -> Coverage | None:
    if not days:
        return None
    dates = {dt.date.fromisoformat(d["date"]) for d in days}
    first, last = min(dates), max(dates)
    span = ((first + dt.timedelta(days=n)) for n in range((last - first).days + 1))
    return Coverage(
        first=first,
        last=last,
        pizzas=len(pizzas),
        closed=sum(1 for d in days if d.get("closed", False)),
        missing=[d for d in span if d not in dates],
        avg_ingredients=sum(len(p.items) for p in pizzas) / len(pizzas) if pizzas else 0.0,
    )
