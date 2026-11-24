"""Setup, polling and the import action."""

from unittest.mock import patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_USERNAME
from homeassistant.core import HomeAssistant

from custom_components.picnic_grocy.const import (
    CONF_AUTH_TOKEN,
    CONF_COUNTRY,
    CONF_GROCY_API_KEY,
    CONF_GROCY_URL,
    DOMAIN,
    EVENT_IMPORTED,
)

from .fakes import FakeGrocy, FakePicnic

DATA = {
    CONF_COUNTRY: "DE",
    CONF_USERNAME: "erik@example.com",
    CONF_AUTH_TOKEN: "token-0",
    CONF_GROCY_URL: "http://grocy",
    CONF_GROCY_API_KEY: "key",
}


async def _setup(hass, options=None):
    grocy = FakeGrocy()
    picnic = FakePicnic()
    entry = MockConfigEntry(domain=DOMAIN, data=DATA, options=options or {}, unique_id="x")
    entry.add_to_hass(hass)
    with (
        patch("custom_components.picnic_grocy.PicnicClient", return_value=picnic),
        patch("custom_components.picnic_grocy.GrocyClient", return_value=grocy),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry, picnic, grocy


async def test_existing_deliveries_are_history(hass: HomeAssistant) -> None:
    entry, picnic, grocy = await _setup(hass)
    assert entry.state is ConfigEntryState.LOADED
    assert grocy.stock == []
    # Token refreshed by Picnic is persisted, without reloading the entry.
    assert entry.data[CONF_AUTH_TOKEN] == "token-1"
    assert entry.state is ConfigEntryState.LOADED


async def test_new_delivery_imported_automatically(hass: HomeAssistant) -> None:
    entry, picnic, grocy = await _setup(hass, {"dry_run": False})
    events = []
    hass.bus.async_listen(EVENT_IMPORTED, events.append)
    picnic.deliveries.insert(0, {"delivery_id": "D2", "status": "COMPLETED"})
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert len(grocy.stock) == 2
    assert events and events[0].data["delivery_id"] == "D2"
    state = hass.states.get("sensor.picnic_grocy_last_import")
    assert state is not None and state.state == "2"

    # Not imported twice
    await entry.runtime_data.async_refresh()
    assert len(grocy.stock) == 2


async def test_dry_run_default(hass: HomeAssistant) -> None:
    entry, picnic, grocy = await _setup(hass)
    picnic.deliveries.insert(0, {"delivery_id": "D2", "status": "COMPLETED"})
    await entry.runtime_data.async_refresh()
    assert grocy.stock == []
    assert entry.runtime_data.data["last_result"]["dry_run"] is True


async def test_import_action(hass: HomeAssistant) -> None:
    entry, picnic, grocy = await _setup(hass)
    response = await hass.services.async_call(
        DOMAIN, "import_delivery", {"dry_run": True}, blocking=True, return_response=True
    )
    assert response["delivery_id"] == "D1"
    assert response["summary"]["booked"] == 2
    assert grocy.stock == []

    await hass.services.async_call(
        DOMAIN, "import_delivery", {"dry_run": False}, blocking=True, return_response=True
    )
    assert len(grocy.stock) == 2


async def test_unload(hass: HomeAssistant) -> None:
    entry, _, _ = await _setup(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
