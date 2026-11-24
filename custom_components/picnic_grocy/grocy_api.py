"""Minimal async client for the Grocy REST API."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import aiohttp

_TIMEOUT = aiohttp.ClientTimeout(total=30)


class GrocyError(Exception):
    """Grocy API error."""


class GrocyAuthError(GrocyError):
    """API key rejected."""


class GrocyClient:
    """Async Grocy client."""

    def __init__(self, session: aiohttp.ClientSession, url: str, api_key: str) -> None:
        self._session = session
        self._base = url.rstrip("/")
        if self._base.endswith("/api"):
            self._base = self._base[: -len("/api")]
        self._headers = {"GROCY-API-KEY": api_key, "Accept": "application/json"}

    async def _request(
        self, method: str, path: str, payload: Any = None, ok_404: bool = False
    ) -> Any:
        try:
            async with self._session.request(
                method,
                f"{self._base}/api{path}",
                json=payload,
                headers=self._headers,
                timeout=_TIMEOUT,
            ) as resp:
                if resp.status in (401, 403):
                    raise GrocyAuthError(f"HTTP {resp.status}")
                if resp.status == 204:
                    return None
                text = await resp.text()
                try:
                    data = await resp.json(content_type=None) if text else None
                except ValueError as err:
                    raise GrocyError(
                        f"No JSON from Grocy (HTTP {resp.status}) – wrong URL or port?"
                    ) from err
                if resp.status == 400 and ok_404:
                    return None
                if resp.status >= 400:
                    msg = data.get("error_message") if isinstance(data, dict) else text
                    raise GrocyError(f"HTTP {resp.status}: {msg}")
                return data
        except aiohttp.ClientError as err:
            raise GrocyError(f"Connection error: {err}") from err

    async def system_info(self) -> dict[str, Any]:
        """Check connection and key."""
        data = await self._request("GET", "/system/info")
        if not isinstance(data, dict) or "grocy_version" not in data:
            raise GrocyError("Unexpected answer – is this really Grocy?")
        return data

    async def locations(self) -> list[dict[str, Any]]:
        return await self._request("GET", "/objects/locations") or []

    async def quantity_units(self) -> list[dict[str, Any]]:
        return await self._request("GET", "/objects/quantity_units") or []

    async def products(self) -> list[dict[str, Any]]:
        return await self._request("GET", "/objects/products") or []

    async def product_by_barcode(self, barcode: str) -> dict[str, Any] | None:
        """Product details for a barcode, or None if unknown."""
        data = await self._request(
            "GET", f"/stock/products/by-barcode/{quote(barcode, safe='')}", ok_404=True
        )
        if isinstance(data, dict) and data.get("product"):
            return data["product"]
        return None

    async def create_product(self, fields: dict[str, Any]) -> int:
        data = await self._request("POST", "/objects/products", fields)
        return int(data["created_object_id"])

    async def add_barcode(self, product_id: int, barcode: str, note: str) -> None:
        await self._request(
            "POST",
            "/objects/product_barcodes",
            {"product_id": product_id, "barcode": barcode, "note": note},
        )

    async def add_stock(self, product_id: int, fields: dict[str, Any]) -> None:
        await self._request("POST", f"/stock/products/{product_id}/add", fields)
