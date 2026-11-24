"""Config flow tests."""

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.picnic_grocy.const import (
    CONF_AUTH_TOKEN,
    CONF_COUNTRY,
    CONF_GROCY_API_KEY,
    CONF_GROCY_URL,
    DOMAIN,
)
from custom_components.picnic_grocy.grocy_api import GrocyAuthError
from custom_components.picnic_grocy.picnic_api import (
    Picnic2FAError,
    Picnic2FARequired,
)

USER_INPUT = {
    CONF_COUNTRY: "DE",
    CONF_USERNAME: "erik@example.com",
    CONF_PASSWORD: "secret",
    CONF_GROCY_URL: "http://a0d7b954-grocy/",
    CONF_GROCY_API_KEY: "key",
}
FLOW = "custom_components.picnic_grocy.config_flow"


async def _start(hass):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )


async def test_flow_with_2fa(hass: HomeAssistant) -> None:
    result = await _start(hass)
    assert result["type"] is FlowResultType.FORM

    async def login(self, user, pw):
        self.auth_token = "pre-2fa"
        raise Picnic2FARequired

    async def verify(self, code):
        if code != "123456":
            raise Picnic2FAError("bad")
        self.auth_token = "final-token"

    with (
        patch(f"{FLOW}.GrocyClient.system_info", AsyncMock(return_value={})),
        patch(f"{FLOW}.PicnicClient.login", login),
        patch(f"{FLOW}.PicnicClient.request_2fa_code", AsyncMock()) as req,
        patch(f"{FLOW}.PicnicClient.verify_2fa_code", verify),
        patch(f"{FLOW}.PicnicClient.get_user", AsyncMock(return_value={})),
        patch("custom_components.picnic_grocy.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
        assert result["step_id"] == "two_factor"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"channel": "email"}
        )
        req.assert_awaited_once_with("EMAIL")
        assert result["step_id"] == "two_factor_code"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"code": "000000"}
        )
        assert result["errors"] == {"base": "invalid_code"}
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"code": "123456"}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data[CONF_AUTH_TOKEN] == "final-token"
    assert data[CONF_GROCY_URL] == "http://a0d7b954-grocy"
    assert CONF_PASSWORD not in data


async def test_flow_bad_grocy_key(hass: HomeAssistant) -> None:
    result = await _start(hass)
    with patch(f"{FLOW}.GrocyClient.system_info", AsyncMock(side_effect=GrocyAuthError)):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["errors"] == {"base": "grocy_invalid_auth"}
