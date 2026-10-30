"""Global physical-gateway blackout switch."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DmxGatewayConfigEntry
from .const import CONF_DEFAULT_FADE_DURATION, CONF_DEFAULT_FADE_ENABLED, DEFAULT_FADE_DURATION, DEFAULT_FADE_ENABLED, DOMAIN, MANUFACTURER, fade_enabled_key
from .coordinator import GatewayCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: DmxGatewayConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        [DmxBlackoutSwitch(coordinator)]
        + [
            DmxDefaultFadeSwitch(coordinator, device.device_id, channel.channel_id, channel.name)
            for device in coordinator.data.config.devices
            for channel in device.channels
            if channel.type == "brightness"
        ]
    )


class DmxBlackoutSwitch(CoordinatorEntity[GatewayCoordinator], SwitchEntity):
    """Blackout only changes physical transmission, never logical light levels."""

    _attr_has_entity_name = True
    _attr_translation_key = "blackout"

    def __init__(self, coordinator: GatewayCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.info.gateway_id}_blackout"

    @property
    def device_info(self) -> DeviceInfo:
        info = self.coordinator.info
        return DeviceInfo(
            identifiers={(DOMAIN, info.gateway_id)},
            name=info.model,
            manufacturer=MANUFACTURER,
            model=info.model,
            sw_version=info.firmware_version,
        )

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.diagnostics.blackout if self.coordinator.data else False

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.async_set_blackout(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_set_blackout(False)


class DmxDefaultFadeSwitch(CoordinatorEntity[GatewayCoordinator], SwitchEntity):
    """Enable automatic fades when HA does not provide transition explicitly."""

    _attr_has_entity_name = True
    _attr_translation_key = "default_fade"

    def __init__(self, coordinator: GatewayCoordinator, device_id: str, channel_id: str, channel_name: str) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._channel_id = channel_id
        self._attr_unique_id = f"{coordinator.info.gateway_id}_{channel_id}_default_fade"
        self._attr_name = f"{channel_name} — включение"

    @property
    def device_info(self) -> DeviceInfo:
        info = self.coordinator.info
        device = self.coordinator.data.config.device_for_channel(self._channel_id)
        return DeviceInfo(identifiers={(DOMAIN, f"{info.gateway_id}:device:{self._device_id}")}, via_device=(DOMAIN, info.gateway_id), name=device.name if device else self._device_id, model="DMX runtime device")

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.entry.options.get(fade_enabled_key(self._channel_id), self.coordinator.entry.options.get(CONF_DEFAULT_FADE_ENABLED, DEFAULT_FADE_ENABLED)))

    async def async_turn_on(self, **kwargs) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._set(False)

    async def _set(self, value: bool) -> None:
        options = dict(self.coordinator.entry.options)
        options[fade_enabled_key(self._channel_id)] = value
        options.setdefault(CONF_DEFAULT_FADE_DURATION, DEFAULT_FADE_DURATION)
        self.hass.config_entries.async_update_entry(self.coordinator.entry, options=options)
        self.async_write_ha_state()
