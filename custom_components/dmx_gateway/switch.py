"""Global physical-gateway blackout switch."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DmxGatewayConfigEntry
from .const import DOMAIN, MANUFACTURER
from .coordinator import GatewayCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: DmxGatewayConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    coordinator = entry.runtime_data.coordinator
    # Older releases exposed a per-channel default-fade switch.  The switch
    # duplicated the light entity in the device card and did not represent a
    # separate gateway capability (the duration number is the authoritative
    # per-channel setting). Remove only those stale registry entries while
    # retaining the global blackout switch.
    registry = er.async_get(hass)
    for device in coordinator.data.config.devices:
        for channel in device.channels:
            if channel.type != "brightness":
                continue
            stale_uid = f"{coordinator.info.gateway_id}_{channel.channel_id}_default_fade"
            entity_id = registry.async_get_entity_id("switch", DOMAIN, stale_uid)
            if entity_id:
                registry.async_remove(entity_id)
    async_add_entities([DmxBlackoutSwitch(coordinator)])


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
