"""In-memory fakes for Picnic and Grocy."""

from __future__ import annotations

from typing import Any

from custom_components.picnic_grocy.grocy_api import GrocyError

DELIVERY = {
    "delivery_id": "D1",
    "status": "COMPLETED",
    "orders": [
        {
            "items": [
                {
                    "price": 358,
                    "items": [
                        {
                            "id": "s100",
                            "name": "Milch 3,5%",
                            "unit_quantity": "1 Liter",
                            "perishable": True,
                            "decorators": [{"type": "QUANTITY", "quantity": 2}],
                        }
                    ],
                },
                {
                    "price": 129,
                    "items": [
                        {
                            "id": "s200",
                            "name": "Spaghetti",
                            "unit_quantity": "500 g",
                            "perishable": False,
                            "decorators": [],
                        }
                    ],
                },
                {
                    "price": 25,
                    "items": [{"id": "s300", "name": "Pfand Flasche", "decorators": []}],
                },
            ]
        },
        {
            "items": [
                {
                    "price": 179,
                    "items": [
                        {"id": "s100", "name": "Milch 3,5%", "perishable": True, "decorators": []}
                    ],
                }
            ]
        },
    ],
}


class FakeGrocy:
    """Grocy with products, barcodes and stock in memory."""

    def __init__(self) -> None:
        self.prods: dict[int, dict[str, Any]] = {
            1: {"id": 1, "name": "Spaghetti", "default_best_before_days": 365},
        }
        self.barcodes: dict[str, int] = {}
        self.stock: list[tuple[int, dict[str, Any]]] = []
        self.fail_add_for: set[int] = set()

    async def system_info(self):
        return {"grocy_version": {"Version": "4.7.1"}}

    async def locations(self):
        return [{"id": 2, "name": "Kühlschrank"}, {"id": 3, "name": "Vorrat"}]

    async def quantity_units(self):
        return [{"id": 3, "name": "Pack"}, {"id": 2, "name": "Stück"}]

    async def product_groups(self):
        return [{"id": 1, "name": "Frischware"}]

    async def products(self):
        return list(self.prods.values())

    async def product_by_barcode(self, barcode):
        pid = self.barcodes.get(barcode)
        return dict(self.prods[pid]) if pid else None

    async def create_product(self, fields):
        pid = max(self.prods) + 1
        self.prods[pid] = {"id": pid, **fields}
        return pid

    async def add_barcode(self, product_id, barcode, note):
        self.barcodes[barcode] = product_id

    async def add_stock(self, product_id, fields):
        if product_id in self.fail_add_for:
            raise GrocyError("boom")
        self.stock.append((product_id, fields))


class FakePicnic:
    """Picnic account with one completed delivery."""

    def __init__(self, *args, **kwargs) -> None:
        self.auth_token = "token-1"
        self.deliveries = [{"delivery_id": "D1", "status": "COMPLETED"}]

    async def get_deliveries(self, statuses=None):
        return list(self.deliveries)

    async def get_delivery(self, delivery_id):
        return {**DELIVERY, "delivery_id": delivery_id}

    async def get_user(self):
        return {"user_id": "u"}
