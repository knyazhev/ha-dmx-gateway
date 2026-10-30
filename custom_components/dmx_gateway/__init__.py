"""Home Assistant entry setup for the DMX Gateway Product API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval

from .api import DmxGatewayApiClient, GatewayApiCompatibilityError, GatewayAuthenticationError, GatewayConnectionError
from .const import CONFIG_REFRESH_INTERVAL, CONF_HOST, CONF_PORT, CONF_TOKEN, DOMAIN, MANUFACTURER
from .coordinator import GatewayCoordinator

PLATFORMS: list[Platform] = [Platform.LIGHT, Platform.SWITCH, Platform.NUMBER, Platform.SELECT, Platform.SENSOR]


@dataclass(slots=True)
class GatewayRuntime:
    """Per-entry shared runtime; entities do not create their own clients."""

    client: DmxGatewayApiClient
    coordinator: GatewayCoordinator


DmxGatewayConfigEntry = ConfigEntry[GatewayRuntime]


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
    await coordinator.async_reconcile_registry()
    registry = dr.async_get(hass)
    registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, info.gateway_id)},
        name=info.model,
        manufacturer=MANUFACTURER,
        model=info.model,
        sw_version=info.firmware_version,
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def async_authoritative_refresh(_now) -> None:
        """Rehydrate from Gateway after normal operation or a reconnect."""
        await coordinator.async_request_refresh()

    entry.async_on_unload(
        async_track_time_interval(hass, async_authoritative_refresh, timedelta(seconds=CONFIG_REFRESH_INTERVAL))
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: DmxGatewayConfigEntry) -> bool:
    """Unload all platforms and coordinator listeners for one gateway."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    return unloaded
