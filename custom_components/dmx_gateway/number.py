"""Gateway configuration number entities."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DmxGatewayConfigEntry
from .const import CONF_DEFAULT_FADE_ENABLED, CONF_DEFAULT_FADE_RATE, DEFAULT_FADE_ENABLED, DEFAULT_FADE_RATE, DOMAIN, MANUFACTURER
from .coordinator import GatewayCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: DmxGatewayConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities([DmxDefaultFadeRateNumber(entry.runtime_data.coordinator)])


class DmxDefaultFadeRateNumber(CoordinatorEntity[GatewayCoordinator], NumberEntity):
    """Default automatic fade speed in percentage points per second."""

    _attr_has_entity_name = True
    _attr_translation_key = "default_fade_rate"
    _attr_native_min_value = 0
    _attr_native_max_value = 1000
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER
    _attr_native_unit_of_measurement = "%/s"

    def __init__(self, coordinator: GatewayCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.info.gateway_id}_default_fade_rate"

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
    def native_value(self) -> float:
        return float(self.coordinator.entry.options.get(CONF_DEFAULT_FADE_RATE, DEFAULT_FADE_RATE))

    async def async_set_native_value(self, value: float) -> None:
        options = dict(self.coordinator.entry.options)
        options[CONF_DEFAULT_FADE_RATE] = float(value)
        options.setdefault(CONF_DEFAULT_FADE_ENABLED, DEFAULT_FADE_ENABLED)
        self.hass.config_entries.async_update_entry(self.coordinator.entry, options=options)
        self.async_write_ha_state()
