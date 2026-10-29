"""Gateway startup behavior selector."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DmxGatewayConfigEntry
from .const import DOMAIN, MANUFACTURER
from .coordinator import GatewayCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: DmxGatewayConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        DmxStartupBehaviorSelect(coordinator, device.device_id, channel.channel_id, channel.name)
        for device in coordinator.data.config.devices
        for channel in device.channels
        if channel.type == "brightness"
    )


class DmxStartupBehaviorSelect(CoordinatorEntity[GatewayCoordinator], SelectEntity):
    """Choose whether persisted levels are restored after a reboot."""

    _attr_has_entity_name = True
    _attr_translation_key = "startup_behavior"
    _attr_options = ["on", "off", "restore"]

    def __init__(self, coordinator: GatewayCoordinator, device_id: str, channel_id: str, channel_name: str) -> None:
        super().__init__(coordinator)
        self._channel_id = channel_id
        self._device_id = device_id
        self._attr_unique_id = f"{coordinator.info.gateway_id}_{channel_id}_startup_behavior"
        self._attr_name = "Действие после подачи электропитания"

    @property
    def device_info(self) -> DeviceInfo:
        info = self.coordinator.info
        device = self.coordinator.data.config.device_for_channel(self._channel_id)
        return DeviceInfo(identifiers={(DOMAIN, f"{info.gateway_id}:device:{self._device_id}")}, via_device=(DOMAIN, info.gateway_id), name=device.name if device else self._device_id, model="DMX runtime device")

    @property
    def current_option(self) -> str:
        if not self.coordinator.data:
            return "restore"
        return self.coordinator.data.startup_behavior.get(self._channel_id.rsplit("ch", 1)[-1], "restore")

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_startup_behavior(option, self._channel_id)
