"""Book a Picnic delivery into Grocy.

Kept free of Home Assistant imports so it can be unit-tested on its own.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
import re
from typing import Any

from .const import (
    BARCODE_PREFIX,
    OPT_BBD_DURABLE,
    OPT_BBD_PERISHABLE,
    OPT_CREATE_PRODUCTS,
    OPT_FRESH_KEYWORDS,
    OPT_LOCATION_CHILLED_ID,
    OPT_LOCATION_ID,
    OPT_MATCH_BY_NAME,
    OPT_QU_ID,
    OPT_SKIP_KEYWORDS,
)
from .grocy_api import GrocyClient, GrocyError
from .picnic_api import PicnicArticle

NEVER_EXPIRES = "2999-12-31"
_PIECE_NAMES = ("stück", "stk", "piece", "pieces", "stuk", "pièce")
_FRIDGE_NAMES = ("kühlschrank", "fridge", "koelkast", "réfrigérateur", "frigo")

# Item results
BOOKED = "booked"  # existing product, stock added
CREATED = "created"  # new product created, stock added
MATCHED_BY_NAME = "matched_by_name"  # existing product found by name, barcode added
SKIPPED = "skipped"  # filtered by keyword
UNMATCHED = "unmatched"  # no product and auto-create is off
FAILED = "failed"


@dataclass
class ItemResult:
    """What happened (or would happen) to one article."""

    article_id: str
    name: str
    amount: int
    status: str
    product_id: int | None = None
    product_name: str | None = None
    best_before_date: str | None = None
    price: float | None = None
    message: str | None = None
    decorators: list[str] = field(default_factory=list)
    raw: list[dict[str, Any]] | None = None


@dataclass
class ImportResult:
    """Summary of one import run."""

    delivery_id: str
    dry_run: bool
    items: list[ItemResult] = field(default_factory=list)

    def count(self, *statuses: str) -> int:
        return sum(1 for item in self.items if item.status in statuses)

    @property
    def summary(self) -> dict[str, int]:
        return {
            "articles": len(self.items),
            "booked": self.count(BOOKED, CREATED, MATCHED_BY_NAME),
            "new_products": self.count(CREATED),
            "matched_by_name": self.count(MATCHED_BY_NAME),
            "skipped": self.count(SKIPPED),
            "unmatched": self.count(UNMATCHED),
            "failed": self.count(FAILED),
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "delivery_id": self.delivery_id,
            "dry_run": self.dry_run,
            "summary": self.summary,
            "items": [asdict(item) for item in self.items],
        }


def _keyword_pattern(raw: str | None) -> re.Pattern[str] | None:
    """Whole-word match, so 'Tasche' skips 'Tasche' but not 'Maultaschen'."""
    words = [re.escape(k.strip()) for k in (raw or "").split(",") if k.strip()]
    if not words:
        return None
    return re.compile(r"(?<!\w)(?:" + "|".join(words) + r")(?!\w)", re.IGNORECASE)


def best_before(days: int | None, today: date) -> str:
    """Grocy convention: 0 days means 'never expires'."""
    if not days or days <= 0:
        return NEVER_EXPIRES
    return (today + timedelta(days=int(days))).isoformat()


class Importer:
    """Runs one import against Grocy."""

    def __init__(self, grocy: GrocyClient, options: dict[str, Any]) -> None:
        self._grocy = grocy
        self._opt = options
        self._products_by_name: dict[str, dict[str, Any]] | None = None
        self._location_id: int | None = None
        self._chilled_location_id: int | None = None
        self._qu_id: int | None = None

    def is_fresh(self, art: PicnicArticle) -> bool:
        """Chilled goods (Picnic flag) or produce/bread (keyword, part of a word)."""
        if art.perishable:
            return True
        name = art.name.lower()
        words = [k.strip().lower() for k in str(self._opt.get(OPT_FRESH_KEYWORDS) or "").split(",")]
        if any(w[1:].strip() in name for w in words if w.startswith("-") and w[1:].strip()):
            return False
        return any(w in name for w in words if w and not w.startswith("-"))

    async def _defaults(self) -> None:
        if self._location_id is not None:
            return
        locations = await self._grocy.locations()
        units = await self._grocy.quantity_units()
        if not locations:
            raise GrocyError("Grocy has no storage location – please create one")
        if not units:
            raise GrocyError("Grocy has no quantity unit – please create one")
        wanted_loc = self._opt.get(OPT_LOCATION_ID)
        loc_ids = {int(loc["id"]) for loc in locations}
        self._location_id = (
            int(wanted_loc) if wanted_loc and int(wanted_loc) in loc_ids
            else int(locations[0]["id"])
        )
        wanted_chilled = self._opt.get(OPT_LOCATION_CHILLED_ID)
        if wanted_chilled and int(wanted_chilled) in loc_ids:
            self._chilled_location_id = int(wanted_chilled)
        else:
            fridge = next(
                (
                    loc for loc in locations
                    if any(n in str(loc.get("name", "")).lower() for n in _FRIDGE_NAMES)
                ),
                None,
            )
            self._chilled_location_id = int(fridge["id"]) if fridge else self._location_id
        wanted_qu = self._opt.get(OPT_QU_ID)
        qu_ids = {int(qu["id"]) for qu in units}
        if wanted_qu and int(wanted_qu) in qu_ids:
            self._qu_id = int(wanted_qu)
        else:
            piece = next(
                (qu for qu in units if str(qu.get("name", "")).lower() in _PIECE_NAMES),
                units[0],
            )
            self._qu_id = int(piece["id"])

    async def _by_name(self) -> dict[str, dict[str, Any]]:
        if self._products_by_name is None:
            self._products_by_name = {
                str(p["name"]).strip().lower(): p for p in await self._grocy.products()
            }
        return self._products_by_name

    async def run(
        self,
        delivery_id: str,
        articles: list[PicnicArticle],
        dry_run: bool,
        today: date | None = None,
        debug: bool = False,
    ) -> ImportResult:
        today = today or date.today()
        result = ImportResult(delivery_id=delivery_id, dry_run=dry_run)
        skip = _keyword_pattern(self._opt.get(OPT_SKIP_KEYWORDS))
        for art in articles:
            item = ItemResult(
                article_id=art.article_id,
                name=art.name,
                amount=art.amount,
                status=FAILED,
                price=art.price_per_unit,
                decorators=sorted({str(d.get("type")) for d in art.decorators}),
                raw=art.raw_lines if debug else None,
            )
            result.items.append(item)
            if skip and skip.search(art.name):
                item.status = SKIPPED
                continue
            try:
                await self._import_article(art, item, delivery_id, dry_run, today)
            except GrocyError as err:
                item.status = FAILED
                item.message = str(err)
        return result

    async def _import_article(
        self,
        art: PicnicArticle,
        item: ItemResult,
        delivery_id: str,
        dry_run: bool,
        today: date,
    ) -> None:
        barcode = f"{BARCODE_PREFIX}{art.article_id}"
        product = await self._grocy.product_by_barcode(barcode)
        status = BOOKED

        if product is None and self._opt.get(OPT_MATCH_BY_NAME, True):
            by_name = await self._by_name()
            product = by_name.get(art.name.lower())
            if product is not None:
                status = MATCHED_BY_NAME
                if not dry_run:
                    await self._grocy.add_barcode(
                        int(product["id"]), barcode, f"Picnic: {art.name}"
                    )

        if product is None:
            if not self._opt.get(OPT_CREATE_PRODUCTS, True):
                item.status = UNMATCHED
                return
            product = await self._create_product(art, barcode, dry_run)
            status = CREATED

        bbd_days = product.get("default_best_before_days")
        item.product_id = product.get("id")
        item.product_name = product.get("name")
        item.best_before_date = best_before(
            int(bbd_days) if bbd_days not in (None, "") else 0, today
        )

        if not dry_run:
            fields: dict[str, Any] = {
                "amount": art.amount,
                "transaction_type": "purchase",
                "best_before_date": item.best_before_date,
                "note": f"Picnic {delivery_id}",
            }
            if art.price_per_unit is not None:
                fields["price"] = art.price_per_unit
            await self._grocy.add_stock(int(product["id"]), fields)
        item.status = status

    async def _create_product(
        self, art: PicnicArticle, barcode: str, dry_run: bool
    ) -> dict[str, Any]:
        await self._defaults()
        by_name = await self._by_name()
        name = art.name
        if name.lower() in by_name and art.unit_quantity:
            name = f"{art.name} ({art.unit_quantity})"
        if name.lower() in by_name:
            name = f"{art.name} [{art.article_id}]"
        days = (
            self._opt.get(OPT_BBD_PERISHABLE, 7)
            if self.is_fresh(art)
            else self._opt.get(OPT_BBD_DURABLE, 180)
        )
        fields = {
            "name": name,
            "description": " · ".join(
                part for part in (art.unit_quantity, f"Picnic-Artikel {art.article_id}") if part
            ),
            "location_id": (
                self._chilled_location_id if art.perishable else self._location_id
            ),
            "qu_id_purchase": self._qu_id,
            "qu_id_stock": self._qu_id,
            "default_best_before_days": int(days),
        }
        product: dict[str, Any] = {**fields, "id": None}
        if not dry_run:
            product["id"] = await self._grocy.create_product(fields)
            await self._grocy.add_barcode(product["id"], barcode, f"Picnic: {art.name}")
        by_name[name.lower()] = product
        return product
