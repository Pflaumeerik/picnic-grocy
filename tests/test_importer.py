"""Importer and parser tests (no Home Assistant needed)."""

from datetime import date

from custom_components.picnic_grocy.const import DEFAULT_OPTIONS
from custom_components.picnic_grocy.importer import (
    CREATED,
    FAILED,
    MATCHED_BY_NAME,
    NEVER_EXPIRES,
    SKIPPED,
    UNMATCHED,
    Importer,
    best_before,
)
from custom_components.picnic_grocy.picnic_api import parse_articles

from .fakes import DELIVERY, FakeGrocy

TODAY = date(2026, 11, 21)


def test_parse_merges_and_counts():
    arts = {a.article_id: a for a in parse_articles(DELIVERY)}
    assert set(arts) == {"s100", "s200", "s300"}
    milk = arts["s100"]
    assert milk.amount == 3  # 2 in first order + 1 in second
    assert milk.line_price_cents == 358 + 179
    assert milk.price_per_unit == round(537 / 3 / 100, 2)
    assert arts["s200"].price_per_unit == 1.29


def test_best_before():
    assert best_before(7, TODAY) == "2026-11-28"
    assert best_before(0, TODAY) == NEVER_EXPIRES
    assert best_before(None, TODAY) == NEVER_EXPIRES


async def test_full_import_creates_matches_and_skips():
    grocy = FakeGrocy()
    result = await Importer(grocy, dict(DEFAULT_OPTIONS)).run(
        "D1", parse_articles(DELIVERY), dry_run=False, today=TODAY
    )
    status = {i.article_id: i.status for i in result.items}
    assert status == {"s100": CREATED, "s200": MATCHED_BY_NAME, "s300": SKIPPED}

    milk_id = grocy.barcodes["picnic:s100"]
    milk = grocy.prods[milk_id]
    assert milk["default_best_before_days"] == 7
    assert milk["qu_id_stock"] == 2  # "Stück" preferred over first unit
    assert milk["location_id"] == 2
    assert grocy.barcodes["picnic:s200"] == 1

    booked = {pid: f for pid, f in grocy.stock}
    assert booked[milk_id]["amount"] == 3
    assert booked[milk_id]["best_before_date"] == "2026-11-28"
    assert booked[1]["best_before_date"] == "2027-11-21"
    assert booked[1]["price"] == 1.29
    assert result.summary["booked"] == 2
    assert result.summary["new_products"] == 1


async def test_second_import_uses_barcodes():
    grocy = FakeGrocy()
    importer_opts = dict(DEFAULT_OPTIONS)
    await Importer(grocy, importer_opts).run("D1", parse_articles(DELIVERY), False, TODAY)
    count = len(grocy.prods)
    result = await Importer(grocy, importer_opts).run("D2", parse_articles(DELIVERY), False, TODAY)
    assert len(grocy.prods) == count
    assert {i.status for i in result.items} == {"booked", SKIPPED}


async def test_dry_run_changes_nothing():
    grocy = FakeGrocy()
    result = await Importer(grocy, dict(DEFAULT_OPTIONS)).run(
        "D1", parse_articles(DELIVERY), dry_run=True, today=TODAY
    )
    assert grocy.stock == []
    assert grocy.barcodes == {}
    assert len(grocy.prods) == 1
    assert result.summary["booked"] == 2


async def test_no_create_and_no_name_match():
    grocy = FakeGrocy()
    opts = {**DEFAULT_OPTIONS, "create_missing_products": False, "match_by_name": False}
    result = await Importer(grocy, opts).run("D1", parse_articles(DELIVERY), False, TODAY)
    assert {i.status for i in result.items} == {UNMATCHED, SKIPPED}
    assert grocy.stock == []


async def test_name_collision_gets_unique_name():
    grocy = FakeGrocy()
    opts = {**DEFAULT_OPTIONS, "match_by_name": False}
    await Importer(grocy, opts).run("D1", parse_articles(DELIVERY), False, TODAY)
    names = sorted(p["name"] for p in grocy.prods.values())
    assert "Spaghetti (500 g)" in names


async def test_one_failure_does_not_stop_others():
    grocy = FakeGrocy()
    grocy.fail_add_for.add(1)
    result = await Importer(grocy, dict(DEFAULT_OPTIONS)).run(
        "D1", parse_articles(DELIVERY), False, TODAY
    )
    status = {i.article_id: i.status for i in result.items}
    assert status["s200"] == FAILED
    assert status["s100"] == CREATED


async def test_keywords_match_whole_words_only():
    from custom_components.picnic_grocy.picnic_api import PicnicArticle

    arts = [
        PicnicArticle("a1", "Bürger Schwäbische Maultaschen", None, 1, 229, True),
        PicnicArticle("a2", "Picnic Tasche", None, 1, 10, False),
        PicnicArticle("a3", "Pfand Flasche 0,25", None, 1, 25, False),
    ]
    result = await Importer(FakeGrocy(), dict(DEFAULT_OPTIONS)).run("D", arts, True, TODAY)
    status = {i.article_id: i.status for i in result.items}
    assert status == {"a1": CREATED, "a2": SKIPPED, "a3": SKIPPED}


def test_placeholder_price_dropped():
    from custom_components.picnic_grocy.picnic_api import PicnicArticle

    assert PicnicArticle("x", "Joghurt", None, 3, 432199 * 3, True).price_per_unit is None
    assert PicnicArticle("y", "Milch", None, 2, 250, True).price_per_unit == 1.25


def test_debug_keeps_raw_lines():
    arts = parse_articles(DELIVERY)
    assert arts[0].raw_lines and "items" in arts[0].raw_lines[0]
