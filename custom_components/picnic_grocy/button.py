"""Button: check Picnic for new deliveries right now."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import PicnicGrocyConfigEntry
from .const import DOMAIN
from .coordinator import PicnicGrocyCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PicnicGrocyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([CheckNowButton(entry.runtime_data)])


class CheckNowButton(CoordinatorEntity[PicnicGrocyCoordinator], ButtonEntity):
    """Imports any new completed delivery, like the daily check."""

    _attr_has_entity_name = True
    _attr_translation_key = "check_now"
    _attr_icon = "mdi:cart-arrow-down"

    def __init__(self, coordinator: PicnicGrocyCoordinator) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_check_now"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Picnic → Grocy",
            manufacturer="picnic-grocy",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def available(self) -> bool:
        return True

    async def async_press(self) -> None:
        await self.coordinator.async_refresh()
