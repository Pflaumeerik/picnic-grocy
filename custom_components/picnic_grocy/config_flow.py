"""Config and options flow for Picnic → Grocy."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
    TimeSelector,
)

from .const import (
    CONF_2FA_CHANNEL,
    CONF_2FA_CODE,
    CONF_AUTH_TOKEN,
    CONF_COUNTRY,
    CONF_GROCY_API_KEY,
    CONF_GROCY_URL,
    COUNTRIES,
    DEFAULT_GROCY_URL,
    DEFAULT_OPTIONS,
    DOMAIN,
    OPT_AUTO_IMPORT,
    OPT_BBD_DURABLE,
    OPT_BBD_PERISHABLE,
    OPT_CREATE_PRODUCTS,
    OPT_DAILY_TIME,
    OPT_DELIVERY_SENSOR,
    OPT_DRY_RUN,
    OPT_FRESH_GROUP_ID,
    OPT_FRESH_KEYWORDS,
    OPT_LOCATION_CHILLED_ID,
    OPT_LOCATION_ID,
    OPT_MATCH_BY_NAME,
    OPT_QU_ID,
    OPT_SKIP_KEYWORDS,
)
from .grocy_api import GrocyAuthError, GrocyClient, GrocyError
from .picnic_api import (
    Picnic2FAError,
    Picnic2FARequired,
    PicnicAuthError,
    PicnicClient,
    PicnicError,
)

_LOGGER = logging.getLogger(__name__)

_PASSWORD = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
_CHANNEL_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_2FA_CHANNEL, default="sms"): SelectSelector(
            SelectSelectorConfig(
                options=["sms", "email"],
                translation_key="channel",
                mode=SelectSelectorMode.LIST,
            )
        )
    }
)
_CODE_SCHEMA = vol.Schema({vol.Required(CONF_2FA_CODE): str})


class PicnicGrocyConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up Picnic → Grocy."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._picnic: PicnicClient | None = None

    # --- shared Picnic login ------------------------------------------------

    async def _picnic_login(
        self, username: str, password: str
    ) -> tuple[str | None, bool]:
        """Return (error_key, needs_2fa)."""
        self._picnic = PicnicClient(
            async_get_clientsession(self.hass), self._data[CONF_COUNTRY]
        )
        try:
            await self._picnic.login(username, password)
        except Picnic2FARequired:
            return None, True
        except PicnicAuthError:
            return "invalid_auth", False
        except PicnicError:
            _LOGGER.exception("Picnic login failed")
            return "cannot_connect", False
        return None, False

    async def _finish(self) -> ConfigFlowResult:
        assert self._picnic is not None
        self._data[CONF_AUTH_TOKEN] = self._picnic.auth_token
        if self.source == "reauth":
            return self.async_update_reload_and_abort(
                self._get_reauth_entry(), data_updates=self._data
            )
        return self.async_create_entry(
            title=f"Picnic {self._data[CONF_USERNAME]}", data=self._data
        )

    # --- initial setup ------------------------------------------------------

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            country = user_input[CONF_COUNTRY]
            await self.async_set_unique_id(f"{country}_{username.lower()}")
            self._abort_if_unique_id_configured()

            grocy = GrocyClient(
                async_get_clientsession(self.hass),
                user_input[CONF_GROCY_URL],
                user_input[CONF_GROCY_API_KEY],
            )
            try:
                await grocy.system_info()
            except GrocyAuthError:
                errors["base"] = "grocy_invalid_auth"
            except GrocyError:
                _LOGGER.exception("Grocy check failed")
                errors["base"] = "grocy_cannot_connect"

            if not errors:
                self._data = {
                    CONF_COUNTRY: country,
                    CONF_USERNAME: username,
                    CONF_GROCY_URL: user_input[CONF_GROCY_URL].rstrip("/"),
                    CONF_GROCY_API_KEY: user_input[CONF_GROCY_API_KEY],
                }
                error, needs_2fa = await self._picnic_login(
                    username, user_input[CONF_PASSWORD]
                )
                if needs_2fa:
                    return await self.async_step_two_factor()
                if error:
                    errors["base"] = error
                else:
                    return await self._finish()

        defaults = user_input or {}
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_COUNTRY, default=defaults.get(CONF_COUNTRY, "DE")
                ): SelectSelector(SelectSelectorConfig(options=COUNTRIES)),
                vol.Required(
                    CONF_USERNAME, default=defaults.get(CONF_USERNAME, "")
                ): TextSelector(TextSelectorConfig(type=TextSelectorType.EMAIL)),
                vol.Required(CONF_PASSWORD): _PASSWORD,
                vol.Required(
                    CONF_GROCY_URL, default=defaults.get(CONF_GROCY_URL, DEFAULT_GROCY_URL)
                ): str,
                vol.Required(CONF_GROCY_API_KEY): _PASSWORD,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_two_factor(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose where Picnic sends the code."""
        errors: dict[str, str] = {}
        if user_input is not None:
            assert self._picnic is not None
            try:
                await self._picnic.request_2fa_code(user_input[CONF_2FA_CHANNEL].upper())
            except PicnicError:
                _LOGGER.exception("Requesting the 2FA code failed")
                errors["base"] = "cannot_send_code"
            else:
                return await self.async_step_two_factor_code()
        return self.async_show_form(
            step_id="two_factor", data_schema=_CHANNEL_SCHEMA, errors=errors
        )

    async def async_step_two_factor_code(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Enter the code."""
        errors: dict[str, str] = {}
        if user_input is not None:
            assert self._picnic is not None
            try:
                await self._picnic.verify_2fa_code(user_input[CONF_2FA_CODE])
                await self._picnic.get_user()
            except Picnic2FAError:
                errors["base"] = "invalid_code"
            except PicnicError:
                _LOGGER.exception("2FA verification failed")
                errors["base"] = "invalid_code"
            else:
                return await self._finish()
        return self.async_show_form(
            step_id="two_factor_code", data_schema=_CODE_SCHEMA, errors=errors
        )

    # --- re-authentication ----------------------------------------------------

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        self._data = dict(entry_data)
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            error, needs_2fa = await self._picnic_login(
                self._data[CONF_USERNAME], user_input[CONF_PASSWORD]
            )
            if needs_2fa:
                return await self.async_step_two_factor()
            if error:
                errors["base"] = error
            else:
                return await self._finish()
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): _PASSWORD}),
            description_placeholders={"username": self._data[CONF_USERNAME]},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return PicnicGrocyOptionsFlow()


class PicnicGrocyOptionsFlow(OptionsFlow):
    """Import behaviour."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            if not user_input.get(OPT_DELIVERY_SENSOR):
                user_input.pop(OPT_DELIVERY_SENSOR, None)
            for key in (OPT_LOCATION_ID, OPT_LOCATION_CHILLED_ID, OPT_QU_ID, OPT_FRESH_GROUP_ID):
                if user_input.get(key) in ("", "0", None):
                    user_input.pop(key, None)
            return self.async_create_entry(data=user_input)

        current = {**DEFAULT_OPTIONS, **self.config_entry.options}
        grocy = GrocyClient(
            async_get_clientsession(self.hass),
            self.config_entry.data[CONF_GROCY_URL],
            self.config_entry.data[CONF_GROCY_API_KEY],
        )
        auto = SelectOptionDict(value="0", label="Automatisch / automatic")
        try:
            locations = [auto] + [
                SelectOptionDict(value=str(loc["id"]), label=str(loc["name"]))
                for loc in await grocy.locations()
            ]
            units = [auto] + [
                SelectOptionDict(value=str(qu["id"]), label=str(qu["name"]))
                for qu in await grocy.quantity_units()
            ]
            groups = [auto] + [
                SelectOptionDict(value=str(g["id"]), label=str(g["name"]))
                for g in await grocy.product_groups()
            ]
        except GrocyError:
            locations = units = groups = [auto]

        days = NumberSelector(
            NumberSelectorConfig(min=0, max=3650, step=1, mode=NumberSelectorMode.BOX)
        )
        schema = vol.Schema(
            {
                vol.Required(OPT_AUTO_IMPORT, default=current[OPT_AUTO_IMPORT]): BooleanSelector(),
                vol.Required(
                    OPT_DAILY_TIME, default=current[OPT_DAILY_TIME]
                ): TimeSelector(),
                vol.Optional(
                    OPT_DELIVERY_SENSOR,
                    description={"suggested_value": current.get(OPT_DELIVERY_SENSOR)},
                ): EntitySelector(EntitySelectorConfig(domain="sensor")),
                vol.Required(OPT_DRY_RUN, default=current[OPT_DRY_RUN]): BooleanSelector(),
                vol.Required(
                    OPT_CREATE_PRODUCTS, default=current[OPT_CREATE_PRODUCTS]
                ): BooleanSelector(),
                vol.Required(
                    OPT_MATCH_BY_NAME, default=current[OPT_MATCH_BY_NAME]
                ): BooleanSelector(),
                vol.Optional(
                    OPT_LOCATION_ID, default=str(current.get(OPT_LOCATION_ID, "0"))
                ): SelectSelector(SelectSelectorConfig(options=locations)),
                vol.Optional(
                    OPT_LOCATION_CHILLED_ID,
                    default=str(current.get(OPT_LOCATION_CHILLED_ID, "0")),
                ): SelectSelector(SelectSelectorConfig(options=locations)),
                vol.Optional(
                    OPT_FRESH_GROUP_ID,
                    default=str(current.get(OPT_FRESH_GROUP_ID, "0")),
                ): SelectSelector(SelectSelectorConfig(options=groups)),
                vol.Optional(
                    OPT_QU_ID, default=str(current.get(OPT_QU_ID, "0"))
                ): SelectSelector(SelectSelectorConfig(options=units)),
                vol.Required(
                    OPT_BBD_PERISHABLE, default=current[OPT_BBD_PERISHABLE]
                ): days,
                vol.Required(OPT_BBD_DURABLE, default=current[OPT_BBD_DURABLE]): days,
                vol.Optional(
                    OPT_FRESH_KEYWORDS, default=current[OPT_FRESH_KEYWORDS]
                ): TextSelector(TextSelectorConfig(multiline=True)),
                vol.Optional(
                    OPT_SKIP_KEYWORDS, default=current[OPT_SKIP_KEYWORDS]
                ): str,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
