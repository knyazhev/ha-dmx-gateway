"""Gateway configuration number entities."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DmxGatewayConfigEntry
from .const import CONF_DEFAULT_FADE_DURATION, CONF_DEFAULT_FADE_ENABLED, CONF_DEFAULT_FADE_RATE, DEFAULT_FADE_DURATION, DEFAULT_FADE_ENABLED, DOMAIN, MANUFACTURER
from .coordinator import GatewayCoordinator


def _duration_key(channel_id: str) -> str:
    return f"default_fade_duration_{channel_id}"


async def async_setup_entry(hass: HomeAssistant, entry: DmxGatewayConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        DmxDefaultFadeRateNumber(coordinator, device.device_id, channel.channel_id, channel.name)
        for device in coordinator.data.config.devices
        for channel in device.channels
        if channel.type == "brightness"
    )


class DmxDefaultFadeRateNumber(CoordinatorEntity[GatewayCoordinator], NumberEntity):
    """Default automatic fade speed in percentage points per second."""

    _attr_has_entity_name = True
    _attr_translation_key = "default_fade_duration"
    _attr_native_min_value = 1
    _attr_native_max_value = 10
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER
    _attr_native_unit_of_measurement = "s/10%"

    def __init__(self, coordinator: GatewayCoordinator, device_id: str, channel_id: str, channel_name: str) -> None:
        super().__init__(coordinator)
        self._channel_id = channel_id
        self._device_id = device_id
        self._attr_unique_id = f"{coordinator.info.gateway_id}_{channel_id}_default_fade_duration"
        self._attr_name = f"{channel_name} — время увеличения яркости с 0 до 100 %"

    @property
    def device_info(self) -> DeviceInfo:
        info = self.coordinator.info
        device = self.coordinator.data.config.device_for_channel(self._channel_id)
        return DeviceInfo(identifiers={(DOMAIN, f"{info.gateway_id}:device:{self._device_id}")}, via_device=(DOMAIN, info.gateway_id), name=device.name if device else self._device_id, model="DMX runtime device")

    @property
    def native_value(self) -> float:
        return float(self.coordinator.entry.options.get(_duration_key(self._channel_id), self.coordinator.entry.options.get(CONF_DEFAULT_FADE_DURATION, self.coordinator.entry.options.get(CONF_DEFAULT_FADE_RATE, DEFAULT_FADE_DURATION))))

    async def async_set_native_value(self, value: float) -> None:
        options = dict(self.coordinator.entry.options)
        options[_duration_key(self._channel_id)] = float(value)
        options.setdefault(CONF_DEFAULT_FADE_ENABLED, DEFAULT_FADE_ENABLED)
        self.hass.config_entries.async_update_entry(self.coordinator.entry, options=options)
        self.async_write_ha_state()
