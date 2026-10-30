"""ESPHome-style read-only gateway diagnostics."""
from __future__ import annotations
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from . import DmxGatewayConfigEntry
from .const import DOMAIN, MANUFACTURER
from .coordinator import GatewayCoordinator

async def async_setup_entry(hass: HomeAssistant, entry: DmxGatewayConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities(DmxDiagnosticSensor(entry.runtime_data.coordinator, key, name, unit, device_class) for key, name, unit, device_class in [
        ("uptime_s", "Время работы", UnitOfTime.SECONDS, SensorDeviceClass.DURATION),
        ("tx_rate_fps", "Частота DMX", "fps", None),
        ("tx_errors", "Ошибки передачи DMX", None, None),
        ("config_revision", "Версия конфигурации", None, None),
        ("runtime_devices", "Исполнительные устройства", None, None),
        ("runtime_channels", "Каналы DMX", None, None),
        ("active_transitions", "Активные переходы", None, None),
    ])

class DmxDiagnosticSensor(CoordinatorEntity[GatewayCoordinator], SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True
    def __init__(self, coordinator: GatewayCoordinator, key: str, name: str, unit: str | None, device_class: SensorDeviceClass | None) -> None:
        super().__init__(coordinator); self._key=key; self._attr_name=name; self._attr_unique_id=f"{coordinator.info.gateway_id}_{key}"; self._attr_native_unit_of_measurement=unit; self._attr_device_class=device_class
    @property
    def native_value(self): return getattr(self.coordinator.data.diagnostics, self._key) if self.coordinator.data else None
    @property
    def device_info(self) -> DeviceInfo:
        i=self.coordinator.info; return DeviceInfo(identifiers={(DOMAIN,i.gateway_id)},name=i.model,manufacturer=MANUFACTURER,model=i.model,sw_version=i.firmware_version)
