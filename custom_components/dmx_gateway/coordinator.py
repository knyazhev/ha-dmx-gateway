"""Shared state refresh and optimistic commanded-state cache."""

from __future__ import annotations

import asyncio
import logging
from functools import wraps
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
    startup_behavior: dict[str, str]


def serialized_io(method):
    """A late poll must finish before a new command can update the HA cache."""
    @wraps(method)
    async def wrapped(self,*args,**kwargs):
        async with self._io_lock:
            return await method(self,*args,**kwargs)
    return wrapped


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
        self._io_lock = asyncio.Lock()
        self._pending_channel_targets: dict[str, float] = {}

    @serialized_io
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
            # Startup behavior and fade defaults are configured in the
            # gateway Web UI in the gateway-centric model. They are not
            # required for entity hydration and are absent from native v1.
            startup_behavior = {}
        except GatewayAuthenticationError:
            raise
        except GatewayApiError as err:
            raise UpdateFailed(str(err)) from err

        old = self.data
        valid_channels = {channel.channel_id for channel in config.channels}
        # Gateway /state is authoritative across HA restart/reconnect. If a
        # topology update raced the two GETs, retain only channels from config.
        commanded = {channel_id: logical.brightness for channel_id, logical in state.channels.items() if channel_id in valid_channels}
        for channel_id, target in tuple(self._pending_channel_targets.items()):
            actual = state.channels.get(channel_id)
            if actual is None or actual.target_authoritative or not actual.transitioning:
                self._pending_channel_targets.pop(channel_id, None)
            else:
                commanded[channel_id] = target
        diagnostics = replace(diagnostics, blackout=state.blackout)
        snapshot = GatewaySnapshot(info=info, config=config, diagnostics=diagnostics, state=state, commanded_brightness=commanded, startup_behavior=startup_behavior)
        if old and self._topology(old.config) != self._topology(config):
            self._schedule_reload(old.config, config)
        return snapshot

    @serialized_io
    async def async_set_channel(self, channel_id: str, brightness: float, transition_ms: int, use_default_fade: bool = False) -> None:
        """Let the gateway's measured transition drive the HA entity state."""
        await self.client.async_set_channel_state(channel_id, brightness, transition_ms, use_default_fade)
        self._pending_channel_targets[channel_id] = brightness
        if self.data:
            commanded = dict(self.data.commanded_brightness)
            commanded[channel_id] = brightness
            self.async_set_updated_data(replace(self.data, commanded_brightness=commanded))

    @serialized_io
    async def async_set_blackout(self, state: bool) -> None:
        returned = await self.client.async_set_blackout(state)
        if self.data:
            self.async_set_updated_data(
                replace(self.data, diagnostics=replace(self.data.diagnostics, blackout=returned), state=replace(self.data.state, blackout=returned))
            )

    @serialized_io
    async def async_set_group(self, group_id: str, values: list[int], transition_ms: int, use_default_fade: bool = False) -> None:
        await self.client.async_set_group_state(group_id, values, transition_ms, use_default_fade)
        if self.data:
            groups = dict(self.data.state.groups)
            groups[group_id] = tuple(values)
            channels = dict(self.data.state.channels)
            commanded = dict(self.data.commanded_brightness)
            group = next((item for item in self.data.config.groups if item.group_id == group_id), None)
            if group is not None:
                for channel_id, value in zip(group.members, values, strict=True):
                    channels[channel_id] = LogicalChannelState(value / 255, transition_ms > 0)
                    commanded[channel_id] = value / 255
            self.async_set_updated_data(replace(
                self.data, state=replace(self.data.state, groups=groups, channels=channels),
                commanded_brightness=commanded,
            ))

    @serialized_io
    async def async_set_startup_behavior(self, behavior: str, channel_id: str) -> None:
        channel = int(channel_id.rsplit("ch", 1)[-1]) if "ch" in channel_id else 1
        returned = await self.client.async_set_startup_behavior(behavior, channel)
        if self.data:
            values = dict(self.data.startup_behavior); values[str(channel)] = returned
            self.async_set_updated_data(replace(self.data, startup_behavior=values))

    async def async_refresh_state(self) -> None:
        """Read actual levels quickly; never send cached values to the gateway."""
        # Skip busy ticks rather than queueing reads behind a slow request or
        # a command. This also bounds work while the gateway reconnects.
        if self._io_lock.locked():
            return
        full_refresh = False
        async with self._io_lock:
            if self.data is None:
                return
            try:
                state = await self.client.async_get_state()
            except GatewayApiError as err:
                self.async_set_update_error(UpdateFailed(str(err)))
                return
            if set(state.channels) != set(self.data.state.channels) or set(state.groups) != set(self.data.state.groups):
                full_refresh = True
            else:
                commanded = {key: value.brightness for key, value in state.channels.items()}
                for channel_id, target in tuple(self._pending_channel_targets.items()):
                    actual = state.channels.get(channel_id)
                    if actual is None or actual.target_authoritative or not actual.transitioning:
                        self._pending_channel_targets.pop(channel_id, None)
                    else:
                        commanded[channel_id] = target
                self.async_set_updated_data(replace(self.data,state=state,commanded_brightness=commanded,diagnostics=replace(self.data.diagnostics,blackout=state.blackout)))
        if full_refresh:
            await self.async_request_refresh()

    @staticmethod
    def _topology(config: GatewayConfig) -> frozenset[tuple[str, str, str, str]]:
        return frozenset(
            [("channel", channel.channel_id, channel.type, str(channel.published)) for channel in config.channels]
            + [("group", group.group_id, group.type, str(group.published)) for group in config.groups]
        )

    @callback
    def _schedule_reload(self, previous: GatewayConfig, current: GatewayConfig) -> None:
        """Reload platforms when published topology changes, retaining registry IDs."""
        if self._reload_scheduled:
            return
        self._reload_scheduled = True
        self.hass.async_create_task(self.hass.config_entries.async_reload(self.entry.entry_id))

    async def async_reconcile_registry(self) -> None:
        """Move entities to the gateway and retain IDs of hidden/deleted controls.

        Registry removal destroys entity_id/customizations used by automations.
        Integration-disabled records can instead be reused on ungroup/restore;
        an owner's explicit disabled_by setting is never overwritten.
        """
        if self.data is None:
            return
        expected = {
            ("switch" if channel.type == "Switch" else "light", f"{self.info.gateway_id}_{channel.channel_id}")
            for channel in self.data.config.published_channels
        }
        expected.update(("light", f"{self.info.gateway_id}_{group.group_id}")
                        for group in self.data.config.groups if group.published)
        expected.add(("switch", f"{self.info.gateway_id}_blackout"))
        registry = er.async_get(self.hass)
        devices = dr.async_get(self.hass)
        if hasattr(devices, "async_get_device_by_identifier"):
            gateway = devices.async_get_device_by_identifier((DOMAIN, self.info.gateway_id), self.entry.entry_id)
        else:  # Supported older Home Assistant releases.
            gateway = devices.async_get_device(identifiers={(DOMAIN, self.info.gateway_id)})
        for entity in er.async_entries_for_config_entry(registry, self.entry.entry_id):
            if entity.platform != DOMAIN:
                continue
            changes = {}
            if gateway is not None and entity.device_id != gateway.id:
                changes["device_id"] = gateway.id
            # Diagnostics remain registered independently of control topology.
            active = entity.domain == "sensor" or (entity.domain, entity.unique_id) in expected
            if not active and entity.disabled_by is None:
                changes["disabled_by"] = er.RegistryEntryDisabler.INTEGRATION
            elif active and entity.disabled_by == er.RegistryEntryDisabler.INTEGRATION:
                changes["disabled_by"] = None
            if changes:
                registry.async_update_entity(entity.entity_id, **changes)
