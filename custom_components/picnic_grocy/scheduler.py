"""When to ask Picnic for new deliveries.

No fixed polling: once a day at a chosen time, on demand (button/action),
and in a few follow-up checks after Home Assistant's own Picnic integration
reports a new delivery.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import logging

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_change,
)

from .const import (
    DEFAULT_DAILY_TIME,
    FOLLOW_UP_DELAYS,
    OPT_DAILY_TIME,
    OPT_DELIVERY_SENSOR,
    PICNIC_DELIVERY_UNIQUE_SUFFIX,
)
from .coordinator import PicnicGrocyCoordinator

_LOGGER = logging.getLogger(__name__)


def find_delivery_sensor(hass: HomeAssistant) -> str | None:
    """The 'last order delivery time' sensor of the core Picnic integration."""
    registry = er.async_get(hass)
    for entry in registry.entities.values():
        if entry.platform == "picnic" and str(entry.unique_id).endswith(
            PICNIC_DELIVERY_UNIQUE_SUFFIX
        ):
            return entry.entity_id
    return None


def _parse_time(value: str | None) -> tuple[int, int, int]:
    parts = [int(p) for p in str(value or DEFAULT_DAILY_TIME).split(":")]
    while len(parts) < 3:
        parts.append(0)
    return parts[0], parts[1], parts[2]


class ImportScheduler:
    """Owns the time and state listeners of one config entry."""

    def __init__(self, hass: HomeAssistant, coordinator: PicnicGrocyCoordinator) -> None:
        self.hass = hass
        self.coordinator = coordinator
        self._unsubs: list[Callable[[], None]] = []
        self._follow_ups: list[Callable[[], None]] = []
        self.delivery_sensor: str | None = None

    @callback
    def start(self) -> None:
        options = self.coordinator.options
        hour, minute, second = _parse_time(options.get(OPT_DAILY_TIME))
        self._unsubs.append(
            async_track_time_change(
                self.hass, self._on_daily, hour=hour, minute=minute, second=second
            )
        )
        self.delivery_sensor = options.get(OPT_DELIVERY_SENSOR) or find_delivery_sensor(
            self.hass
        )
        if self.delivery_sensor:
            self._unsubs.append(
                async_track_state_change_event(
                    self.hass, [self.delivery_sensor], self._on_delivery
                )
            )
        else:
            _LOGGER.info("No Picnic delivery sensor found; only daily/manual checks")

    @callback
    def stop(self) -> None:
        for unsub in self._unsubs + self._follow_ups:
            unsub()
        self._unsubs.clear()
        self._follow_ups.clear()

    async def _on_daily(self, _now: datetime) -> None:
        await self.coordinator.async_refresh()

    @callback
    def _on_delivery(self, event: Event[EventStateChangedData]) -> None:
        new = event.data["new_state"]
        old = event.data["old_state"]
        if new is None or new.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return
        if old is not None and old.state == new.state:
            return
        if old is None or old.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            # Restart or reconnect, not a new delivery.
            return
        _LOGGER.debug("Picnic reported a delivery (%s); scheduling checks", new.state)
        self._cancel_follow_ups()
        for delay in FOLLOW_UP_DELAYS:
            self._follow_ups.append(
                async_call_later(self.hass, delay, self._follow_up)
            )

    async def _follow_up(self, _now: datetime) -> None:
        await self.coordinator.async_refresh()
        if self.coordinator.new_deliveries_imported:
            self._cancel_follow_ups()

    @callback
    def _cancel_follow_ups(self) -> None:
        for unsub in self._follow_ups:
            unsub()
        self._follow_ups.clear()
