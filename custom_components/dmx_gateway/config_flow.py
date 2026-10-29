"""Manual ConfigEntry, reconfigure, and development-token reauth flows."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, OptionsFlowWithReload
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import DmxGatewayApiClient, GatewayApiCompatibilityError, GatewayApiError, GatewayAuthenticationError, GatewayConnectionError, GatewayRevisionConflictError, GatewayTimeoutError
from .const import CONF_DEFAULT_FADE_ENABLED, CONF_DEFAULT_FADE_RATE, CONF_PORT, CONF_TOKEN, DEFAULT_FADE_ENABLED, DEFAULT_FADE_RATE, DEFAULT_PORT, DOMAIN
from .models import GatewayConfig, GatewayInfo


def _schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
            vol.Required(CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
            # Do not prefill a stored credential into a UI form.
            vol.Required(CONF_TOKEN, default=""): str,
        }
    )


async def async_validate_gateway(hass: HomeAssistant, data: dict[str, Any]) -> GatewayInfo:
    """Validate credentials and Product API before persisting a ConfigEntry."""
    client = DmxGatewayApiClient(async_get_clientsession(hass), data[CONF_HOST], data[CONF_PORT], data[CONF_TOKEN])
    return await client.async_get_info()


class DmxGatewayConfigFlow(ConfigFlow, domain=DOMAIN):
    """Use API gateway_id, not host/IP, as the ConfigEntry unique ID."""

    VERSION = 1
    MINOR_VERSION = 1

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
                # A gateway may receive a different DHCP address. Preserve the
                # ConfigEntry/registry identity and refresh its connection data.
                self._abort_if_unique_id_configured(updates=user_input)
                return self.async_create_entry(title=info.model, data=user_input)
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


def _api_config(config: GatewayConfig) -> dict[str, Any]:
    return {
        "schema_version": config.schema_version,
        "devices": [
            {
                "device_id": device.device_id,
                "name": device.name,
                "start_address": device.start_address,
                "channels": [
                    {"channel_id": channel.channel_id, "name": channel.name, "type": channel.type, "offset": channel.offset}
                    for channel in device.channels
                ],
            }
            for device in config.devices
        ],
    }


def _valid_dmx_range(start_address: int, channel_count: int) -> bool:
    """Return whether a device fits entirely in the 512-slot DMX universe."""
    return 1 <= start_address <= 512 and 1 <= channel_count <= 512 and start_address + channel_count - 1 <= 512


class DmxGatewayOptionsFlow(OptionsFlowWithReload):
    """Thin standard-UI editor over authoritative Gateway runtime config."""

    def __init__(self) -> None:
        self._config: GatewayConfig | None = None
        self._selected_device_id: str | None = None
        self._pending_device: dict[str, Any] | None = None

    def _client(self) -> DmxGatewayApiClient:
        data = self.config_entry.data
        return DmxGatewayApiClient(async_get_clientsession(self.hass), data[CONF_HOST], data[CONF_PORT], data[CONF_TOKEN])

    async def _load(self) -> GatewayConfig:
        self._config = await self._client().async_get_config()
        return self._config

    async def _apply(self, candidate: dict[str, Any]) -> dict[str, str]:
        """CAS write followed by authoritative reread; never retry a conflict."""
        assert self._config is not None
        try:
            await self._client().async_put_config(candidate, self._config.config_revision)
        except GatewayRevisionConflictError:
            await self._load()
            return {"base": "revision_conflict"}
        except GatewayConnectionError:
            return {"base": "cannot_connect"}
        except GatewayApiError:
            return {"base": "invalid_config"}
        await self._load()
        runtime = self.config_entry.runtime_data
        await runtime.coordinator.async_request_refresh()
        return {}

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        try:
            config = await self._load()
        except GatewayConnectionError:
            return self.async_abort(reason="cannot_connect")
        menu_options = ["fade_settings"]
        if not config.devices:
            menu_options.append("add_device")
        else:
            menu_options.extend(["add_device", "edit_device", "delete_device"])
        return self.async_show_menu(step_id="init", menu_options=menu_options)

    async def async_step_fade_settings(self, user_input: dict[str, Any] | None = None):
        """Configure the default fade rate used when HA omits transition."""
        if user_input is not None:
            return self.async_create_entry(data={CONF_DEFAULT_FADE_ENABLED: bool(user_input[CONF_DEFAULT_FADE_ENABLED]), CONF_DEFAULT_FADE_RATE: float(user_input[CONF_DEFAULT_FADE_RATE])})
        current = self.config_entry.options.get(CONF_DEFAULT_FADE_RATE, DEFAULT_FADE_RATE)
        enabled = self.config_entry.options.get(CONF_DEFAULT_FADE_ENABLED, DEFAULT_FADE_ENABLED)
        schema = vol.Schema({vol.Required(CONF_DEFAULT_FADE_ENABLED, default=enabled): bool, vol.Required(CONF_DEFAULT_FADE_RATE, default=current): vol.All(vol.Coerce(float), vol.Range(min=0, max=1000))})
        return self.async_show_form(step_id="fade_settings", data_schema=schema)

    async def async_step_add_device(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            self._pending_device = {"device_id": f"device-{uuid4().hex}", "name": user_input["name"].strip(), "start_address": user_input["start_address"], "channel_count": user_input["channel_count"]}
            if not self._pending_device["name"]:
                errors["name"] = "required"
            elif not _valid_dmx_range(self._pending_device["start_address"], self._pending_device["channel_count"]):
                errors["base"] = "dmx_range"
            else:
                return await self.async_step_edit_channels()
        schema = vol.Schema({vol.Required("name"): str, vol.Required("start_address", default=1): vol.All(vol.Coerce(int), vol.Range(min=1, max=512)), vol.Required("channel_count", default=1): vol.All(vol.Coerce(int), vol.Range(min=1, max=512))})
        return self.async_show_form(step_id="add_device", data_schema=schema, errors=errors)

    async def async_step_edit_device(self, user_input: dict[str, Any] | None = None):
        config = self._config or await self._load()
        if self._selected_device_id is None:
            if user_input is not None:
                self._selected_device_id = user_input["device_id"]
            else:
                return self.async_show_form(step_id="edit_device", data_schema=vol.Schema({vol.Required("device_id"): vol.In({d.device_id: d.name for d in config.devices})}))
        device = next(d for d in config.devices if d.device_id == self._selected_device_id)
        if user_input is not None and "name" in user_input:
            self._pending_device = {"device_id": device.device_id, "name": user_input["name"].strip(), "start_address": user_input["start_address"], "channel_count": user_input["channel_count"]}
            if not self._pending_device["name"]:
                errors["name"] = "required"
            elif not _valid_dmx_range(self._pending_device["start_address"], self._pending_device["channel_count"]):
                errors["base"] = "dmx_range"
            else:
                return await self.async_step_edit_channels()
            return self.async_show_form(step_id="edit_device_details", data_schema=vol.Schema({vol.Required("name", default=device.name): str, vol.Required("start_address", default=device.start_address): vol.All(vol.Coerce(int), vol.Range(min=1, max=512)), vol.Required("channel_count", default=len(device.channels)): vol.All(vol.Coerce(int), vol.Range(min=1, max=512))}), errors=errors)
        return self.async_show_form(step_id="edit_device_details", data_schema=vol.Schema({vol.Required("name", default=device.name): str, vol.Required("start_address", default=device.start_address): vol.All(vol.Coerce(int), vol.Range(min=1, max=512)), vol.Required("channel_count", default=len(device.channels)): vol.All(vol.Coerce(int), vol.Range(min=1, max=512))}))

    async_step_edit_device_details = async_step_edit_device

    async def async_step_edit_channels(self, user_input: dict[str, Any] | None = None):
        assert self._pending_device is not None
        config = self._config or await self._load()
        existing = next((d for d in config.devices if d.device_id == self._pending_device["device_id"]), None)
        count = self._pending_device["channel_count"]
        schema_fields: dict[Any, Any] = {}
        for index in range(count):
            default = existing.channels[index].name if existing and index < len(existing.channels) else f"Channel {index + 1}"
            schema_fields[vol.Required(f"channel_{index}_name", default=default)] = str
        if user_input is not None:
            names = [user_input[f"channel_{index}_name"].strip() for index in range(count)]
            if not all(names):
                return self.async_show_form(step_id="edit_channels", data_schema=vol.Schema(schema_fields), errors={"base": "required"})
            channels = []
            for index, name in enumerate(names):
                channel_id = existing.channels[index].channel_id if existing and index < len(existing.channels) else f"{self._pending_device['device_id']}-ch{index + 1}"
                channels.append({"channel_id": channel_id, "name": name, "type": "brightness", "offset": index})
            candidate = _api_config(config)
            item = {"device_id": self._pending_device["device_id"], "name": self._pending_device["name"], "start_address": self._pending_device["start_address"], "channels": channels}
            candidate["devices"] = [item if d["device_id"] == item["device_id"] else d for d in candidate["devices"]]
            if existing is None:
                candidate["devices"].append(item)
            errors = await self._apply(candidate)
            if errors:
                return self.async_show_form(step_id="edit_channels", data_schema=vol.Schema(schema_fields), errors=errors)
            return self.async_create_entry(data={})
        return self.async_show_form(step_id="edit_channels", data_schema=vol.Schema(schema_fields))

    async def async_step_delete_device(self, user_input: dict[str, Any] | None = None):
        config = self._config or await self._load()
        if self._selected_device_id is None:
            if user_input is None:
                return self.async_show_form(step_id="delete_device", data_schema=vol.Schema({vol.Required("device_id"): vol.In({d.device_id: d.name for d in config.devices})}))
            self._selected_device_id = user_input["device_id"]
            return self.async_show_form(step_id="confirm_delete", data_schema=vol.Schema({vol.Required("confirm", default=False): bool}))
        if user_input is not None:
            if not user_input["confirm"]:
                return self.async_abort(reason="delete_cancelled")
            candidate = _api_config(config)
            candidate["devices"] = [d for d in candidate["devices"] if d["device_id"] != self._selected_device_id]
            errors = await self._apply(candidate)
            if errors:
                return self.async_show_form(step_id="confirm_delete", data_schema=vol.Schema({vol.Required("confirm", default=False): bool}), errors=errors)
            return self.async_create_entry(data={})
        return self.async_show_form(step_id="confirm_delete", data_schema=vol.Schema({vol.Required("confirm", default=False): bool}))

    async_step_confirm_delete = async_step_delete_device
