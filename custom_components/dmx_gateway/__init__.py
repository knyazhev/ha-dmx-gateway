"""Home Assistant entry setup for the DMX Gateway Product API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval

from .api import DmxGatewayApiClient, GatewayApiCompatibilityError, GatewayAuthenticationError, GatewayConnectionError
from .const import CONFIG_REFRESH_INTERVAL, CONF_HOST, CONF_PORT, CONF_TOKEN, DOMAIN, MANUFACTURER
from .coordinator import GatewayCoordinator

PLATFORMS: list[Platform] = [Platform.LIGHT, Platform.SWITCH, Platform.SENSOR]


@dataclass(slots=True)
class GatewayRuntime:
    """Per-entry shared runtime; entities do not create their own clients."""

    client: DmxGatewayApiClient
    coordinator: GatewayCoordinator


DmxGatewayConfigEntry = ConfigEntry[GatewayRuntime]


def _remove_legacy_child_devices(hass: HomeAssistant, entry: DmxGatewayConfigEntry, gateway_id: str) -> None:
    """Remove obsolete physical-device children created by the old HA model."""
    devices = dr.async_get(hass)
    if hasattr(devices, "async_get_device_by_identifier"):
        gateway = devices.async_get_device_by_identifier((DOMAIN, gateway_id), entry.entry_id)
    else:  # Older Home Assistant compatibility.
        gateway = devices.async_get_device({(DOMAIN, gateway_id)})
    if gateway is None:
        return
    legacy_names = {"SkyDance S1-DR", "sss1"}
    legacy_ids = {
        device.id
        for device in devices.devices.values()
        if device.config_entries == {entry.entry_id}
        and device.via_device_id == gateway.id
        and device.model == "DMX runtime device"
        and device.name in legacy_names
    }
    if not legacy_ids:
        return
    entities = er.async_get(hass)
    for entity in tuple(entities.entities.values()):
        if entity.config_entry_id == entry.entry_id and entity.platform == DOMAIN and entity.device_id in legacy_ids:
            entities.async_remove(entity.entity_id)
    for device_id in legacy_ids:
        devices.async_remove_device(device_id)


async def async_setup_entry(hass: HomeAssistant, entry: DmxGatewayConfigEntry) -> bool:
    """Set up a gateway config entry."""
    client = DmxGatewayApiClient(
        async_get_clientsession(hass),
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
        entry.data[CONF_TOKEN],
    )
    try:
        info = await client.async_get_info()
    except GatewayAuthenticationError as err:
        raise ConfigEntryAuthFailed("gateway connection code rejected") from err
    except GatewayApiCompatibilityError as err:
        raise ConfigEntryNotReady(f"unsupported Product API: {err}") from err
    except GatewayConnectionError as err:
        raise ConfigEntryNotReady("gateway is unavailable") from err

    if entry.unique_id != info.gateway_id:
        # The gateway_id, never host/IP, is identity. A changed or spoofed
        # gateway must be reconfigured rather than silently adopted.
        raise ConfigEntryNotReady("gateway identity does not match this config entry")

    coordinator = GatewayCoordinator(hass, entry, client, info)
    try:
        await coordinator.async_config_entry_first_refresh()
    except GatewayAuthenticationError as err:
        raise ConfigEntryAuthFailed("gateway connection code rejected") from err
    except GatewayConnectionError as err:
        raise ConfigEntryNotReady("gateway is unavailable") from err

    entry.runtime_data = GatewayRuntime(client=client, coordinator=coordinator)
    registry = dr.async_get(hass)
    registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, info.gateway_id)},
        name="BELARD DMX Gateway",
        configuration_url="https://192.168.4.1/#channels",
        manufacturer=MANUFACTURER,
        model=info.model,
        sw_version=info.firmware_version,
    )
    _remove_legacy_child_devices(hass, entry, info.gateway_id)
    await coordinator.async_reconcile_registry()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def async_authoritative_refresh(_now) -> None:
        """Rehydrate from Gateway after normal operation or a reconnect."""
        await coordinator.async_request_refresh()

    entry.async_on_unload(
        async_track_time_interval(hass, async_authoritative_refresh, timedelta(seconds=CONFIG_REFRESH_INTERVAL))
    )
    async def async_state_refresh(_now) -> None:
        await coordinator.async_refresh_state()

    entry.async_on_unload(async_track_time_interval(hass, async_state_refresh, timedelta(seconds=5)))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: DmxGatewayConfigEntry) -> bool:
    """Unload all platforms and coordinator listeners for one gateway."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    return unloaded
