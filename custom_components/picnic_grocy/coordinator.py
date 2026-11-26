"""Polls Picnic for completed deliveries and imports new ones into Grocy."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_AUTH_TOKEN,
    DEFAULT_OPTIONS,
    DOMAIN,
    EVENT_IMPORTED,
    OPT_AUTO_IMPORT,
    OPT_DRY_RUN,
    STORAGE_VERSION,
)
from .grocy_api import GrocyAuthError, GrocyClient, GrocyError
from .importer import ImportResult, Importer
from .picnic_api import PicnicAuthError, PicnicClient, PicnicError, parse_articles

_LOGGER = logging.getLogger(__name__)

MAX_KNOWN = 200  # remembered delivery IDs
AUTH_FAILURES_BEFORE_REAUTH = 3  # one rejected poll is not proof the login expired


class PicnicGrocyCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Keeps track of imported deliveries."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        picnic: PicnicClient,
        grocy: GrocyClient,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=None,  # driven by time, button and delivery sensor
        )
        self.picnic = picnic
        self.grocy = grocy
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self._state: dict[str, Any] = {}
        self._updating = False
        self._auth_failures = 0
        self.new_deliveries_imported = 0
        self.options_at_setup = dict(entry.options)

    @property
    def options(self) -> dict[str, Any]:
        return {**DEFAULT_OPTIONS, **self.config_entry.options}

    async def async_load(self) -> None:
        self._state = await self._store.async_load() or {}

    async def _save(self) -> None:
        known = self._state.get("known", [])
        self._state["known"] = known[-MAX_KNOWN:]
        await self._store.async_save(self._state)

    def _persist_token(self) -> None:
        token = self.picnic.auth_token
        if token and token != self.config_entry.data.get(CONF_AUTH_TOKEN):
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data={**self.config_entry.data, CONF_AUTH_TOKEN: token},
            )

    async def _completed(self) -> list[dict[str, Any]]:
        try:
            deliveries = await self.picnic.get_deliveries(["COMPLETED"])
        except PicnicAuthError as err:
            self._auth_failures += 1
            _LOGGER.warning(
                "Picnic rejected the request (%s/%s): %s",
                self._auth_failures,
                AUTH_FAILURES_BEFORE_REAUTH,
                err,
            )
            if self._auth_failures >= AUTH_FAILURES_BEFORE_REAUTH:
                raise ConfigEntryAuthFailed(str(err)) from err
            raise PicnicError(f"Request rejected, retrying later: {err}") from err
        finally:
            self._persist_token()
        self._auth_failures = 0
        self.new_deliveries_imported = 0
        return [d for d in deliveries if d.get("delivery_id")]

    async def _async_update_data(self) -> dict[str, Any]:
        self._updating = True
        try:
            return await self._update()
        finally:
            self._updating = False

    async def _update(self) -> dict[str, Any]:
        try:
            deliveries = await self._completed()
        except PicnicError as err:
            raise UpdateFailed(f"Picnic: {err}") from err

        known: list[str] = self._state.setdefault("known", [])
        if not self._state.get("initialized"):
            # First run: everything delivered so far counts as history.
            known.extend(d["delivery_id"] for d in deliveries)
            self._state["initialized"] = True
            await self._save()
        elif self.options[OPT_AUTO_IMPORT]:
            # Picnic lists newest first; import oldest first.
            self.new_deliveries_imported = 0
            for delivery in reversed(deliveries):
                delivery_id = delivery["delivery_id"]
                if delivery_id in known:
                    continue
                try:
                    await self.async_import(
                        delivery_id, dry_run=self.options[OPT_DRY_RUN], mark_known=True
                    )
                    self.new_deliveries_imported += 1
                except HomeAssistantError as err:
                    _LOGGER.warning("Import of delivery %s failed: %s", delivery_id, err)
                    break

        return {
            "last_result": self._state.get("last_result"),
            "last_run": self._state.get("last_run"),
            "latest_delivery_id": deliveries[0]["delivery_id"] if deliveries else None,
        }

    async def async_import(
        self,
        delivery_id: str | None = None,
        dry_run: bool = True,
        mark_known: bool | None = None,
        debug: bool = False,
    ) -> ImportResult:
        """Import one delivery (default: the latest completed one)."""
        try:
            if delivery_id is None:
                deliveries = await self._completed()
                if not deliveries:
                    raise HomeAssistantError("Picnic reports no completed delivery yet")
                delivery_id = deliveries[0]["delivery_id"]
            delivery = await self.picnic.get_delivery(delivery_id)
        except ConfigEntryAuthFailed as err:
            self.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError("Picnic login expired – please re-authenticate") from err
        except PicnicAuthError as err:
            self.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError("Picnic login expired – please re-authenticate") from err
        except PicnicError as err:
            raise HomeAssistantError(f"Picnic: {err}") from err
        finally:
            self._persist_token()

        articles = parse_articles(delivery or {})
        importer = Importer(self.grocy, self.options)
        try:
            result = await importer.run(delivery_id, articles, dry_run=dry_run, debug=debug)
        except GrocyAuthError as err:
            raise HomeAssistantError("Grocy rejected the API key") from err
        except GrocyError as err:
            raise HomeAssistantError(f"Grocy: {err}") from err

        if mark_known is None:
            mark_known = not dry_run
        known: list[str] = self._state.setdefault("known", [])
        if mark_known and delivery_id not in known:
            known.append(delivery_id)
        stored = result.as_dict()
        for item in stored["items"]:
            item.pop("raw", None)
        self._state["last_result"] = stored
        self._state["last_run"] = dt_util.utcnow().isoformat()
        await self._save()

        self._announce(result)
        if not self._updating:
            self.async_set_updated_data(
                {
                    **(self.data or {}),
                    "last_result": self._state["last_result"],
                    "last_run": self._state["last_run"],
                }
            )
        return result

    def _announce(self, result: ImportResult) -> None:
        summary = result.summary
        new_names = [i.product_name for i in result.items if i.status == "created"]
        self.hass.bus.async_fire(
            EVENT_IMPORTED,
            {
                "delivery_id": result.delivery_id,
                "dry_run": result.dry_run,
                **summary,
                "new_product_names": new_names,
            },
        )
        german = (self.hass.config.language or "").startswith("de")
        if german:
            title = "Picnic → Grocy" + (" (Probelauf)" if result.dry_run else "")
            lines = [
                f"{summary['booked']} von {summary['articles']} Artikeln "
                + ("würden eingebucht." if result.dry_run else "eingebucht."),
                f"Neue Produkte: {summary['new_products']}",
                f"Per Name zugeordnet: {summary['matched_by_name']}",
                f"Übersprungen: {summary['skipped']}",
            ]
            if summary["unmatched"]:
                lines.append(f"Ohne Zuordnung: {summary['unmatched']}")
            if summary["failed"]:
                lines.append(f"Fehler: {summary['failed']} (siehe Sensor-Attribute)")
            if new_names:
                lines.append("\nBitte prüfen (MHD-Vorgabe, Lagerort): " + ", ".join(new_names[:30]))
        else:
            title = "Picnic → Grocy" + (" (dry run)" if result.dry_run else "")
            lines = [
                f"{summary['booked']} of {summary['articles']} articles "
                + ("would be booked." if result.dry_run else "booked."),
                f"New products: {summary['new_products']}",
                f"Matched by name: {summary['matched_by_name']}",
                f"Skipped: {summary['skipped']}",
            ]
            if summary["unmatched"]:
                lines.append(f"Unmatched: {summary['unmatched']}")
            if summary["failed"]:
                lines.append(f"Failed: {summary['failed']} (see sensor attributes)")
            if new_names:
                lines.append("\nPlease review (due days, location): " + ", ".join(new_names[:30]))
        persistent_notification.async_create(
            self.hass,
            "\n".join(lines),
            title=title,
            notification_id=f"{DOMAIN}_{self.config_entry.entry_id}",
        )
