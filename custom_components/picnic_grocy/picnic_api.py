"""Minimal async client for the (unofficial) Picnic storefront API.

Only what the importer needs: login incl. two-factor authentication, the list
of deliveries and the details of a single delivery. Endpoints and headers follow
python-picnic-api2, but this client is async and has no extra dependencies, so
it never conflicts with the version Home Assistant's own Picnic integration pins.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import md5
from typing import Any

import aiohttp

BASE_URL = "https://storefront-prod.{country}.picnicinternational.com/api/15"
AUTH_HEADER = "x-picnic-auth"
CLIENT_ID = 30100
_HEADERS = {
    "User-Agent": "okhttp/4.9.0",
    "Content-Type": "application/json; charset=UTF-8",
    "x-picnic-agent": "30100;1.206.1-#15408",
    "x-picnic-did": "598F770380CA54B6",
}
_TIMEOUT = aiohttp.ClientTimeout(total=30)
MAX_PLAUSIBLE_PRICE = 500.0


class PicnicError(Exception):
    """Generic Picnic API error."""


class PicnicAuthError(PicnicError):
    """Credentials or token invalid."""


class Picnic2FARequired(PicnicError):
    """Login succeeded, but a second factor is needed."""


class Picnic2FAError(PicnicError):
    """The second factor was rejected."""


@dataclass
class PicnicArticle:
    """One delivered article, flattened from the order tree."""

    article_id: str
    name: str
    unit_quantity: str | None
    amount: int
    line_price_cents: int | None
    perishable: bool | None
    decorators: list[dict[str, Any]] = field(default_factory=list)
    raw_lines: list[dict[str, Any]] = field(default_factory=list)

    @property
    def price_per_unit(self) -> float | None:
        """Price of one piece in currency units, if Picnic sent a plausible one."""
        if self.line_price_cents is None or self.amount <= 0:
            return None
        price = round(self.line_price_cents / self.amount / 100, 2)
        # Picnic marks some promotion lines with placeholder prices; drop those.
        return price if 0 < price <= MAX_PLAUSIBLE_PRICE else None


class PicnicClient:
    """Async Picnic API client bound to one account."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        country: str,
        auth_token: str | None = None,
    ) -> None:
        self._session = session
        self._base = BASE_URL.format(country=country.lower())
        self.auth_token = auth_token

    # --- low level ---------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        headers = dict(_HEADERS)
        if self.auth_token:
            headers[AUTH_HEADER] = self.auth_token
        return headers

    async def _request(
        self, method: str, path: str, payload: Any = None
    ) -> Any:
        try:
            async with self._session.request(
                method,
                self._base + path,
                json=payload,
                headers=self._headers(),
                timeout=_TIMEOUT,
            ) as resp:
                if token := resp.headers.get(AUTH_HEADER):
                    self.auth_token = token
                if resp.status == 204:
                    return None
                body = await resp.text()
                if resp.status in (401, 403):
                    raise PicnicAuthError(f"HTTP {resp.status}: {body[:300]}")
                data: Any = None
                if body:
                    try:
                        data = await resp.json(content_type=None)
                    except ValueError as err:
                        raise PicnicError(
                            f"Unexpected answer (HTTP {resp.status})"
                        ) from err
        except aiohttp.ClientError as err:
            raise PicnicError(f"Connection error: {err}") from err

        if isinstance(data, dict):
            code = (data.get("error") or {}).get("code")
            if code in ("AUTH_ERROR", "AUTH_INVALID_CRED"):
                raise PicnicAuthError(code)
        if resp.status >= 400:
            raise PicnicError(f"HTTP {resp.status}: {str(data)[:200]}")
        return data

    # --- authentication ----------------------------------------------------

    async def login(self, username: str, password: str) -> None:
        """Log in. Raises Picnic2FARequired if a code must be requested next."""
        self.auth_token = None
        secret = md5(password.encode("utf-8")).hexdigest()  # noqa: S324 - Picnic's scheme
        data = await self._request(
            "POST",
            "/user/login",
            {"key": username, "secret": secret, "client_id": CLIENT_ID},
        )
        if isinstance(data, dict) and data.get(
            "second_factor_authentication_required"
        ):
            raise Picnic2FARequired
        if not self.auth_token:
            raise PicnicAuthError("No token received")

    async def request_2fa_code(self, channel: str) -> None:
        """Ask Picnic to send a code via SMS or EMAIL."""
        await self._post_2fa("/user/2fa/generate", {"channel": channel})

    async def verify_2fa_code(self, code: str) -> None:
        """Confirm the received code; the token is valid afterwards."""
        await self._post_2fa("/user/2fa/verify", {"otp": code.strip()})

    async def _post_2fa(self, path: str, payload: dict[str, Any]) -> None:
        try:
            data = await self._request("POST", path, payload)
        except PicnicAuthError:
            raise
        except PicnicError as err:
            raise Picnic2FAError(str(err)) from err
        if isinstance(data, dict) and (data.get("error") or {}).get("code"):
            raise Picnic2FAError(data["error"].get("message") or data["error"]["code"])

    # --- data ----------------------------------------------------------------

    async def get_user(self) -> dict[str, Any]:
        """Cheap call to check that the token works."""
        return await self._request("GET", "/user")

    async def get_deliveries(
        self, statuses: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """Delivery summaries, newest first (as Picnic returns them)."""
        data = await self._request("POST", "/deliveries/summary", statuses or [])
        return data if isinstance(data, list) else []

    async def get_delivery(self, delivery_id: str) -> dict[str, Any]:
        """Full delivery with orders → lines → articles."""
        return await self._request("GET", f"/deliveries/{delivery_id}")


def _line_total(line: dict[str, Any]) -> int | None:
    """Price actually paid for a line: promotion price if present, else line price."""
    for deco in line.get("decorators") or []:
        if deco.get("type") == "PRICE" and deco.get("display_price") is not None:
            return int(deco["display_price"])
    for key in ("price", "display_price"):
        if line.get(key) is not None:
            return int(line[key])
    return None


def _quantity(article: dict[str, Any]) -> int:
    for deco in article.get("decorators") or []:
        if deco.get("type") == "QUANTITY" and deco.get("quantity"):
            return int(deco["quantity"])
    return 1


def parse_articles(delivery: dict[str, Any]) -> list[PicnicArticle]:
    """Flatten a delivery into articles, merging identical article IDs.

    Picnic puts a placeholder into the article price; the real price is on the
    order line. Promotion lines ("3 for 2.59") can bundle different articles,
    so the line total is split across them by quantity.
    """
    merged: dict[str, PicnicArticle] = {}
    for order in delivery.get("orders") or []:
        for line in order.get("items") or []:
            articles = [a for a in line.get("items") or [] if a.get("id")]
            if not articles:
                continue
            total = _line_total(line)
            pieces = sum(_quantity(a) for a in articles) or 1
            for art in articles:
                art_id = art["id"]
                decorators = art.get("decorators") or []
                amount = _quantity(art)
                price = round(total * amount / pieces) if total is not None else None
                if art_id in merged:
                    existing = merged[art_id]
                    existing.amount += amount
                    if existing.line_price_cents is not None and price is not None:
                        existing.line_price_cents += price
                    else:
                        existing.line_price_cents = None
                    existing.decorators.extend(decorators)
                    existing.raw_lines.append(_slim(line))
                    continue
                merged[art_id] = PicnicArticle(
                    article_id=art_id,
                    name=(art.get("name") or art_id).strip(),
                    unit_quantity=art.get("unit_quantity"),
                    amount=amount,
                    line_price_cents=price,
                    perishable=art.get("perishable"),
                    decorators=list(decorators),
                    raw_lines=[_slim(line)],
                )
    return list(merged.values())


def _slim(line: dict[str, Any]) -> dict[str, Any]:
    """Order line without images, for diagnostics."""
    def strip(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {
                k: strip(v)
                for k, v in obj.items()
                if "image" not in k and k not in ("max_count",)
            }
        if isinstance(obj, list):
            return [strip(v) for v in obj]
        return obj

    return strip(line)
