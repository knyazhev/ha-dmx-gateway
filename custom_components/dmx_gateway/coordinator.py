"""Shared state refresh and optimistic commanded-state cache."""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from typing import Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import DmxGatewayApiClient, GatewayApiError, GatewayAuthenticationError
from .const import DOMAIN
from .models import Diagnostics, GatewayConfig, GatewayInfo, GatewayState, LogicalChannelState


@dataclass(frozen=True, slots=True)
class GatewaySnapshot:
    info: GatewayInfo
    config: GatewayConfig
    diagnostics: Diagnostics
    state: GatewayState
    # Product API currently exposes commanded writes, not fixture feedback.
    commanded_brightness: dict[str, float]


class GatewayCoordinator(DataUpdateCoordinator[GatewaySnapshot]):
    """Refresh topology/diagnostics slowly; commands update logical state now."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: DmxGatewayApiClient, info: GatewayInfo) -> None:
        super().__init__(
            hass,
            logger=logging.getLogger(__name__),
            name=DOMAIN,
            # ``__init__`` owns the explicit HA lifecycle refresh. Keeping
            # this unset avoids a second scheduler whose recovery after a
            # transport-loss event was not reliable on the deployed Core.
            update_interval=None,
            config_entry=entry,
        )
        self.entry = entry
        self.client = client
        self.info = info
        self._reload_scheduled = False

    async def _async_update_data(self) -> GatewaySnapshot:
        try:
            # The product API runs on a deliberately small ESP-IDF HTTP
            # server.  Fetch sequentially through the one shared HA session:
            # it reuses one connection rather than opening four simultaneous
            # keep-alive sessions at every refresh.  ``/v1/state`` remains
            # the authoritative source for logical brightness and blackout.
            info = await self.client.async_get_info()
            config = await self.client.async_get_config()
            state = await self.client.async_get_state()
            # A configuration PUT may race the two reads. Re-read the
            # topology once so entities are never hydrated from a mismatched
            # config/state pair.
            if state.config_revision != config.config_revision:
                config = await self.client.async_get_config()
                if state.config_revision != config.config_revision:
                    state = await self.client.async_get_state()
            diagnostics = await self.client.async_get_diagnostics()
        except GatewayAuthenticationError:
            raise
        except GatewayApiError as err:
            raise UpdateFailed(str(err)) from err

        old = self.data
        valid_channels = {channel.channel_id for device in config.devices for channel in device.channels}
        # Gateway /state is authoritative across HA restart/reconnect. If a
        # topology update raced the two GETs, retain only channels from config.
        commanded = {channel_id: logical.brightness for channel_id, logical in state.channels.items() if channel_id in valid_channels}
        diagnostics = replace(diagnostics, blackout=state.blackout)
        snapshot = GatewaySnapshot(info=info, config=config, diagnostics=diagnostics, state=state, commanded_brightness=commanded)
        self._sync_runtime_device_names(config)
        if old and self._topology(old.config) != self._topology(config):
            self._schedule_reload(old.config, config)
        return snapshot

    async def async_set_channel(self, channel_id: str, brightness: float, transition_ms: int) -> None:
        """Send one gateway-side command; do not emulate a transition in HA."""
        await self.client.async_set_channel_state(channel_id, brightness, transition_ms)
        if self.data:
            states = dict(self.data.commanded_brightness)
            states[channel_id] = brightness
            state_channels = dict(self.data.state.channels)
            state_channels[channel_id] = LogicalChannelState(brightness=brightness, transitioning=transition_ms > 0)
            self.async_set_updated_data(
                replace(self.data, state=replace(self.data.state, channels=state_channels), commanded_brightness=states)
            )

    async def async_set_blackout(self, state: bool) -> None:
        returned = await self.client.async_set_blackout(state)
        if self.data:
            self.async_set_updated_data(
                replace(self.data, diagnostics=replace(self.data.diagnostics, blackout=returned), state=replace(self.data.state, blackout=returned))
            )

    @staticmethod
    def _topology(config: GatewayConfig) -> frozenset[tuple[str, str]]:
        return frozenset((device.device_id, channel.channel_id) for device in config.devices for channel in device.channels)

    def _sync_runtime_device_names(self, config: GatewayConfig) -> None:
        """Reflect Gateway display-name changes without replacing device identity."""
        device_registry = dr.async_get(self.hass)
        for runtime_device in config.devices:
            device = device_registry.async_get_device(
                identifiers={(DOMAIN, f"{self.info.gateway_id}:device:{runtime_device.device_id}")}
            )
            if device is not None and device.name_by_user is None and device.name != runtime_device.name:
                device_registry.async_update_device(device.id, name=runtime_device.name)

    @callback
    def _schedule_reload(self, previous: GatewayConfig, current: GatewayConfig) -> None:
        """Remove only vanished runtime identities before a topology reload."""
        if self._reload_scheduled:
            return
        self._reload_scheduled = True
        previous_channels = {channel.channel_id for device in previous.devices for channel in device.channels}
        current_channels = {channel.channel_id for device in current.devices for channel in device.channels}
        removed_channels = previous_channels - current_channels
        previous_devices = {device.device_id for device in previous.devices}
        current_devices = {device.device_id for device in current.devices}
        removed_devices = previous_devices - current_devices
        self.hass.async_create_task(self._async_reconcile_removed_topology(removed_channels, removed_devices))

    async def _async_reconcile_removed_topology(self, removed_channels: set[str], removed_devices: set[str]) -> None:
        """Remove stale HA registry records owned by deleted Gateway topology."""
        entity_registry = er.async_get(self.hass)
        expected_unique_ids = {f"{self.info.gateway_id}_{channel_id}" for channel_id in removed_channels}
        for entity in er.async_entries_for_config_entry(entity_registry, self.entry.entry_id):
            if entity.platform == DOMAIN and entity.unique_id in expected_unique_ids:
                entity_registry.async_remove(entity.entity_id)

        device_registry = dr.async_get(self.hass)
        for device_id in removed_devices:
            device = device_registry.async_get_device(
                identifiers={(DOMAIN, f"{self.info.gateway_id}:device:{device_id}")}
            )
            if device is not None:
                device_registry.async_remove_device(device.id)

        await self.hass.config_entries.async_reload(self.entry.entry_id)

    async def async_reconcile_registry(self) -> None:
        """Remove prior runtime entities that no longer exist on the Gateway."""
        if self.data is None:
            return
        active_channel_ids = {
            channel.channel_id for device in self.data.config.devices for channel in device.channels
        }
        expected_unique_ids = {
            f"{self.info.gateway_id}_{channel_id}" for channel_id in active_channel_ids
        }
        entity_registry = er.async_get(self.hass)
        stale_device_ids: set[str] = set()
        for entity in er.async_entries_for_config_entry(entity_registry, self.entry.entry_id):
            if (
                entity.platform == DOMAIN
                and entity.unique_id != f"{self.info.gateway_id}_blackout"
                and entity.unique_id not in expected_unique_ids
            ):
                if entity.device_id is not None:
                    stale_device_ids.add(entity.device_id)
                entity_registry.async_remove(entity.entity_id)

        device_registry = dr.async_get(self.hass)
        for device_id in stale_device_ids:
            device_registry.async_remove_device(device_id)
