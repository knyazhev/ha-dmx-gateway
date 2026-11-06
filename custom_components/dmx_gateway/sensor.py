"""Read-only native gateway diagnostics."""
from __future__ import annotations
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from . import DmxGatewayConfigEntry
from .const import DOMAIN, MANUFACTURER
from .coordinator import GatewayCoordinator

async def async_setup_entry(hass: HomeAssistant, entry: DmxGatewayConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities(DmxDiagnosticSensor(entry.runtime_data.coordinator, key, name, unit, device_class) for key, name, unit, device_class in [
        ("uptime_s", "Время работы", None, None),
        ("tx_rate_fps", "Частота DMX", "fps", None),
        ("tx_errors", "Ошибки передачи DMX", None, None),
        ("config_revision", "Версия конфигурации", None, None),
        ("runtime_devices", "Исполнительные устройства", None, None),
        ("runtime_channels", "Каналы DMX", None, None),
        ("active_transitions", "Активные переходы", None, None),
        ("free_heap", "Свободная память", "MB", SensorDeviceClass.DATA_SIZE),
        ("persistence_load_valid", "Состояние после загрузки", None, None),
        ("persistence_last_sync_ok", "Последняя запись состояния", None, None),
    ])

class DmxDiagnosticSensor(CoordinatorEntity[GatewayCoordinator], SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True
    def __init__(self, coordinator: GatewayCoordinator, key: str, name: str, unit: str | None, device_class: SensorDeviceClass | None) -> None:
        super().__init__(coordinator); self._key=key; self._attr_name=name; self._attr_unique_id=f"{coordinator.info.gateway_id}_{key}"; self._attr_native_unit_of_measurement=unit; self._attr_device_class=device_class
    @property
    def native_value(self):
        if not self.coordinator.data:
            return None
        value = getattr(self.coordinator.data.diagnostics, self._key)
        if self._key == "uptime_s" and value is not None:
            seconds = max(0, int(value))
            days, remainder = divmod(seconds, 86400)
            hours, remainder = divmod(remainder, 3600)
            minutes = remainder // 60
            if days:
                return f"{days} д {hours} ч"
            if hours:
                return f"{hours} ч {minutes} мин"
            return f"{minutes} мин"
        if self._key == "free_heap" and value is not None:
            return round(value / 1_000_000, 1)
        if self._key.startswith("persistence_") and value is not None:
            if self._key == "persistence_load_valid":
                return "OK" if value else "Нет валидного состояния"
            return "OK" if value else "Ошибка записи"
        return value
    @property
    def device_info(self) -> DeviceInfo:
        i=self.coordinator.info; return DeviceInfo(identifiers={(DOMAIN,i.gateway_id)},name="BELARD DMX Gateway",manufacturer=MANUFACTURER,model=i.model,sw_version=i.firmware_version)
