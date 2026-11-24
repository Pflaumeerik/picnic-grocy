"""Sensor showing the result of the last import."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import PicnicGrocyConfigEntry
from .const import DOMAIN
from .coordinator import PicnicGrocyCoordinator

MAX_ITEMS_IN_ATTRIBUTES = 100


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PicnicGrocyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([LastImportSensor(entry.runtime_data)])


class LastImportSensor(CoordinatorEntity[PicnicGrocyCoordinator], SensorEntity):
    """Number of articles booked by the last import; details as attributes."""

    _attr_has_entity_name = True
    _attr_translation_key = "last_import"
    _attr_icon = "mdi:cart-arrow-down"

    def __init__(self, coordinator: PicnicGrocyCoordinator) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_last_import"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Picnic → Grocy",
            manufacturer="picnic-grocy",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def _result(self) -> dict[str, Any] | None:
        return (self.coordinator.data or {}).get("last_result")

    @property
    def native_value(self) -> int | None:
        result = self._result
        return result["summary"]["booked"] if result else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        result = self._result or {}
        items = result.get("items", [])
        return {
            "delivery_id": result.get("delivery_id"),
            "dry_run": result.get("dry_run"),
            "last_run": data.get("last_run"),
            "latest_completed_delivery": data.get("latest_delivery_id"),
            **result.get("summary", {}),
            "items": [
                {
                    k: item.get(k)
                    for k in ("name", "amount", "status", "product_name", "best_before_date", "message")
                    if item.get(k) is not None
                }
                for item in items[:MAX_ITEMS_IN_ATTRIBUTES]
            ],
        }
