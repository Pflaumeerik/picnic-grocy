"""Picnic → Grocy: book delivered Picnic groceries into Grocy."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .const import (
    ATTR_CONFIG_ENTRY_ID,
    ATTR_DEBUG,
    ATTR_DELIVERY_ID,
    ATTR_DRY_RUN,
    CONF_AUTH_TOKEN,
    CONF_COUNTRY,
    CONF_GROCY_API_KEY,
    CONF_GROCY_URL,
    DOMAIN,
    SERVICE_IMPORT_DELIVERY,
)
from .coordinator import PicnicGrocyCoordinator
from .grocy_api import GrocyClient
from .picnic_api import PicnicClient

PLATFORMS = [Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type PicnicGrocyConfigEntry = ConfigEntry[PicnicGrocyCoordinator]

SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(ATTR_DELIVERY_ID): cv.string,
        vol.Optional(ATTR_DRY_RUN, default=True): cv.boolean,
        vol.Optional(ATTR_DEBUG, default=False): cv.boolean,
    }
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the import action."""

    async def _import(call: ServiceCall) -> ServiceResponse:
        entries = [
            e
            for e in hass.config_entries.async_entries(DOMAIN)
            if e.state is ConfigEntryState.LOADED
        ]
        if entry_id := call.data.get(ATTR_CONFIG_ENTRY_ID):
            entries = [e for e in entries if e.entry_id == entry_id]
        if not entries:
            raise ServiceValidationError("No loaded Picnic → Grocy entry found")
        coordinator: PicnicGrocyCoordinator = entries[0].runtime_data
        result = await coordinator.async_import(
            call.data.get(ATTR_DELIVERY_ID) or None,
            dry_run=call.data[ATTR_DRY_RUN],
            debug=call.data[ATTR_DEBUG],
        )
        data = result.as_dict()
        if not call.data[ATTR_DEBUG]:
            for item in data["items"]:
                item.pop("raw", None)
        return data

    hass.services.async_register(
        DOMAIN,
        SERVICE_IMPORT_DELIVERY,
        _import,
        schema=SERVICE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: PicnicGrocyConfigEntry) -> bool:
    """Set up from a config entry."""
    session = async_get_clientsession(hass)
    picnic = PicnicClient(
        session, entry.data[CONF_COUNTRY], entry.data.get(CONF_AUTH_TOKEN)
    )
    grocy = GrocyClient(
        session, entry.data[CONF_GROCY_URL], entry.data[CONF_GROCY_API_KEY]
    )
    coordinator = PicnicGrocyCoordinator(hass, entry, picnic, grocy)
    await coordinator.async_load()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_reload_on_options))
    return True


async def _reload_on_options(hass: HomeAssistant, entry: PicnicGrocyConfigEntry) -> None:
    """Reload when options change (token refreshes also fire this listener)."""
    coordinator = entry.runtime_data
    if dict(entry.options) != coordinator.options_at_setup:
        await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: PicnicGrocyConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
