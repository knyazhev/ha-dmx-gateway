"""Manual ConfigEntry and credential reauthentication flows."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, OptionsFlowWithReload
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.const import CONF_HOST
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import DmxGatewayApiClient, GatewayApiCompatibilityError, GatewayAuthenticationError, GatewayConnectionError, GatewayTimeoutError
from .const import CONF_DEFAULT_FADE_DURATION, CONF_DEFAULT_FADE_ENABLED, CONF_DEFAULT_FADE_RATE, CONF_PORT, CONF_TOKEN, DEFAULT_FADE_DURATION, DEFAULT_FADE_ENABLED, DEFAULT_PORT, DOMAIN
from .models import GatewayInfo


def _schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema({
        vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
        vol.Required(CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
        vol.Optional(CONF_TOKEN, default=defaults.get(CONF_TOKEN, "")): str,
    })


async def async_validate_gateway(hass: HomeAssistant, data: dict[str, Any]) -> GatewayInfo:
    try:
        client = DmxGatewayApiClient(async_get_clientsession(hass), data[CONF_HOST], data[CONF_PORT], data.get(CONF_TOKEN, ""))
    except ValueError as err:
        raise GatewayConnectionError("invalid gateway address or certificate fingerprint") from err
    return await client.async_get_info()


class DmxGatewayConfigFlow(ConfigFlow, domain=DOMAIN):
    """Use the stable gateway_id, never the host/IP, as entry identity."""

    VERSION = 1
    MINOR_VERSION = 2

    @staticmethod
    def async_get_options_flow(config_entry):
        return DmxGatewayOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await async_validate_gateway(self.hass, user_input)
            except GatewayAuthenticationError:
                errors["base"] = "invalid_auth"
            except GatewayTimeoutError:
                errors["base"] = "timeout"
            except GatewayConnectionError:
                errors["base"] = "cannot_connect"
            except GatewayApiCompatibilityError:
                errors["base"] = "unsupported_api"
            else:
                await self.async_set_unique_id(info.gateway_id)
                self._abort_if_unique_id_configured(updates=user_input)
                return self.async_create_entry(title=info.model or "BELARD DMX Gateway", data=user_input)
        return self.async_show_form(step_id="user", data_schema=_schema(user_input), errors=errors)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None):
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await async_validate_gateway(self.hass, user_input)
            except GatewayAuthenticationError:
                errors["base"] = "invalid_auth"
            except GatewayTimeoutError:
                errors["base"] = "timeout"
            except GatewayConnectionError:
                errors["base"] = "cannot_connect"
            except GatewayApiCompatibilityError:
                errors["base"] = "unsupported_api"
            else:
                await self.async_set_unique_id(info.gateway_id)
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(entry, data_updates=user_input)
        return self.async_show_form(step_id="reconfigure", data_schema=_schema(dict(entry.data)), errors=errors)

    async def async_step_reauth(self, entry_data: dict[str, Any]):
        self._reauth_entry = self._get_reauth_entry()
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None):
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = dict(entry.data)
            data[CONF_TOKEN] = user_input[CONF_TOKEN]
            try:
                info = await async_validate_gateway(self.hass, data)
            except GatewayAuthenticationError:
                errors["base"] = "invalid_auth"
            except GatewayConnectionError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(info.gateway_id)
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(entry, data_updates={CONF_TOKEN: data[CONF_TOKEN]})
        return self.async_show_form(step_id="reauth_confirm", data_schema=vol.Schema({vol.Required(CONF_TOKEN): str}), errors=errors)


class DmxGatewayOptionsFlow(OptionsFlowWithReload):
    """Keep only local HA defaults; channel/device configuration is gateway Web UI state."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        return self.async_show_menu(step_id="init", menu_options=["gateway_settings"])

    async def async_step_gateway_settings(self, user_input: dict[str, Any] | None = None):
        """Channel configuration lives on the gateway, never in a second HA copy."""
        if user_input is not None:
            return await self.async_step_init()
        return self.async_show_form(
            step_id="gateway_settings", data_schema=vol.Schema({}),
            description_placeholders={"gateway_url": "https://192.168.4.1/#channels"},
        )
