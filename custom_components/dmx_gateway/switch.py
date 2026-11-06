"""Global physical-gateway blackout switch."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DmxGatewayConfigEntry
from .const import DOMAIN, MANUFACTURER
from .coordinator import GatewayCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: DmxGatewayConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities([DmxBlackoutSwitch(coordinator), *(DmxLogicalSwitch(coordinator, channel.channel_id) for channel in coordinator.data.config.published_channels if channel.type == "Switch")])


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
            name="BELARD DMX Gateway",
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


class DmxLogicalSwitch(CoordinatorEntity[GatewayCoordinator], SwitchEntity):
    """A published logical channel declared as a Home Assistant switch."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: GatewayCoordinator, channel_id: str) -> None:
        super().__init__(coordinator)
        self._channel_id = channel_id
        self._attr_unique_id = f"{coordinator.info.gateway_id}_{channel_id}"

    @property
    def device_info(self) -> DeviceInfo:
        info = self.coordinator.info
        return DeviceInfo(identifiers={(DOMAIN, info.gateway_id)}, name="BELARD DMX Gateway", manufacturer=MANUFACTURER, model=info.model, sw_version=info.firmware_version)

    @property
    def name(self) -> str:
        channel = self.coordinator.data.config.channel_for_id(self._channel_id) if self.coordinator.data else None
        return channel.name if channel else self._channel_id

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data and not self.coordinator.data.state.blackout and self.coordinator.data.commanded_brightness.get(self._channel_id, 0.0) > 0)

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.async_set_channel(self._channel_id, 1.0, 0)

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_set_channel(self._channel_id, 0.0, 0)
