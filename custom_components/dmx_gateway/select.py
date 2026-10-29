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
    async_add_entities([DmxStartupBehaviorSelect(entry.runtime_data.coordinator)])


class DmxStartupBehaviorSelect(CoordinatorEntity[GatewayCoordinator], SelectEntity):
    """Choose whether persisted levels are restored after a reboot."""

    _attr_has_entity_name = True
    _attr_translation_key = "startup_behavior"
    _attr_entity_category = "config"
    _attr_options = ["restore", "off"]

    def __init__(self, coordinator: GatewayCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.info.gateway_id}_startup_behavior"

    @property
    def device_info(self) -> DeviceInfo:
        info = self.coordinator.info
        return DeviceInfo(identifiers={(DOMAIN, info.gateway_id)}, name=info.model, manufacturer=MANUFACTURER, model=info.model, sw_version=info.firmware_version)

    @property
    def current_option(self) -> str:
        return self.coordinator.data.startup_behavior if self.coordinator.data else "restore"

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_startup_behavior(option)
