"""Logical channel and RGB/RGBW group light entities."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import ATTR_BRIGHTNESS, ATTR_RGB_COLOR, ATTR_TRANSITION, ColorMode, LightEntity, LightEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DmxGatewayConfigEntry
from .const import DOMAIN, MANUFACTURER
from .coordinator import GatewayCoordinator
from .models import LogicalChannel, LogicalGroup


async def async_setup_entry(hass: HomeAssistant, entry: DmxGatewayConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    """Expose only published logical lights and logical RGB/RGBW groups."""
    coordinator = entry.runtime_data.coordinator
    entities: list[LightEntity] = []
    for channel in coordinator.data.config.published_channels:
        if channel.type in {"Light", "brightness", "RGB Light", "RGBW Light"}:
            entities.append(DmxLogicalLight(coordinator, channel.channel_id))
    entities.extend(DmxLogicalGroupLight(coordinator, group.group_id) for group in coordinator.data.config.groups if group.published)
    async_add_entities(entities)


class _GatewayEntity(CoordinatorEntity[GatewayCoordinator]):
    _attr_has_entity_name = True

    @property
    def device_info(self) -> DeviceInfo:
        info = self.coordinator.info
        return DeviceInfo(identifiers={(DOMAIN, info.gateway_id)}, name="BELARD DMX Gateway", manufacturer=MANUFACTURER, model=info.model, sw_version=info.firmware_version)


class DmxLogicalLight(_GatewayEntity, LightEntity):
    """One published DMX logical channel, attached directly to the gateway."""

    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_features = LightEntityFeature.TRANSITION

    def __init__(self, coordinator: GatewayCoordinator, channel_id: str) -> None:
        super().__init__(coordinator)
        self._channel_id = channel_id
        self._attr_unique_id = f"{coordinator.info.gateway_id}_{channel_id}"

    def _channel(self) -> LogicalChannel | None:
        return self.coordinator.data.config.channel_for_id(self._channel_id) if self.coordinator.data else None

    @property
    def name(self) -> str:
        channel = self._channel()
        return channel.name if channel else self._channel_id

    @property
    def available(self) -> bool:
        channel = self._channel()
        return bool(self.coordinator.last_update_success and channel and channel.published)

    @property
    def is_on(self) -> bool:
        return self._brightness > 0

    @property
    def brightness(self) -> int:
        return round(self._brightness * 255)

    @property
    def _brightness(self) -> float:
        return self.coordinator.data.commanded_brightness.get(self._channel_id, 0.0) if self.coordinator.data and not self.coordinator.data.state.blackout else 0.0

    async def async_turn_on(self, **kwargs: Any) -> None:
        brightness = kwargs.get(ATTR_BRIGHTNESS, 255) / 255
        await self.coordinator.async_set_channel(self._channel_id, brightness, self._transition_ms(kwargs, brightness), ATTR_TRANSITION not in kwargs)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_channel(self._channel_id, 0.0, self._transition_ms(kwargs, 0.0), ATTR_TRANSITION not in kwargs)

    def _transition_ms(self, kwargs: dict[str, Any], target: float) -> int:
        if ATTR_TRANSITION in kwargs:
            return max(0, min(600000, round(float(kwargs[ATTR_TRANSITION]) * 1000)))
        # Fade policy belongs to the gateway. HA supplies only explicit
        # per-call transitions; an omitted transition delegates to gateway settings.
        return 0


class DmxLogicalGroupLight(_GatewayEntity, LightEntity):
    """A single Home Assistant light backed by RGB or RGBW DMX members."""

    _attr_supported_features = LightEntityFeature.TRANSITION

    def __init__(self, coordinator: GatewayCoordinator, group_id: str) -> None:
        super().__init__(coordinator)
        self._group_id = group_id
        self._last_nonzero: tuple[int, ...] = ()
        self._attr_unique_id = f"{coordinator.info.gateway_id}_{group_id}"

    def _group(self) -> LogicalGroup | None:
        if not self.coordinator.data:
            return None
        return next((group for group in self.coordinator.data.config.groups if group.group_id == self._group_id), None)

    def _values(self) -> tuple[int, ...]:
        values = self.coordinator.data.state.groups.get(self._group_id, ()) if self.coordinator.data else ()
        if any(values):
            self._last_nonzero = values
        return (0,) * len(values) if self.coordinator.data and self.coordinator.data.state.blackout else values

    def _normalized_color(self) -> tuple[int, ...]:
        values = self._values() or self._last_nonzero
        peak = max(values, default=0)
        return tuple(round(value * 255 / peak) for value in values) if peak else values

    @property
    def name(self) -> str:
        group = self._group()
        return group.name if group else self._group_id

    @property
    def available(self) -> bool:
        group = self._group()
        return bool(self.coordinator.last_update_success and group and group.published)

    @property
    def color_mode(self) -> ColorMode:
        return ColorMode.RGBW if self._group() and self._group().type == "RGBW" else ColorMode.RGB

    @property
    def supported_color_modes(self) -> set[ColorMode]:
        return {self.color_mode}

    @property
    def is_on(self) -> bool:
        return any(self._values())

    @property
    def brightness(self) -> int:
        return max(self._values(), default=0)

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        values = self._normalized_color()
        return tuple(values[:3]) if len(values) >= 3 else None

    @property
    def rgbw_color(self) -> tuple[int, int, int, int] | None:
        values = self._normalized_color()
        return tuple(values[:4]) if len(values) >= 4 else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_refresh_state()
        if not self.coordinator.last_update_success:
            raise HomeAssistantError("Cannot read current gateway color")
        group = self._group()
        if group is None:
            return
        current = self._values()
        values = current if any(current) else self._last_nonzero
        if not any(values):
            values = (255,) * len(group.members)
        requested = kwargs.get("rgbw_color") if group.type == "RGBW" else kwargs.get(ATTR_RGB_COLOR)
        if requested is not None:
            values = tuple(max(0, min(255, int(value))) for value in requested)
        brightness = max(0, min(255, int(kwargs.get(ATTR_BRIGHTNESS, max(current, default=0) or max(self._last_nonzero, default=0) or 255))))
        peak = max(values, default=0)
        values = [round(value * brightness / peak) for value in values] if peak else [0] * len(group.members)
        await self.coordinator.async_set_group(self._group_id, values, self._transition_ms(kwargs, values), ATTR_TRANSITION not in kwargs)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_refresh_state()
        if not self.coordinator.last_update_success:
            raise HomeAssistantError("Cannot read current gateway color")
        group = self._group()
        if group:
            self._values()  # Remember color/level for a subsequent plain turn_on.
            await self.coordinator.async_set_group(self._group_id, [0] * len(group.members), self._transition_ms(kwargs, [0] * len(group.members)), ATTR_TRANSITION not in kwargs)

    def _transition_ms(self, kwargs: dict[str, Any], target: list[int]) -> int:
        if ATTR_TRANSITION in kwargs:
            return max(0, min(600000, round(float(kwargs[ATTR_TRANSITION]) * 1000)))
        # Fade policy belongs to the gateway. HA supplies only explicit
        # per-call transitions; an omitted transition delegates to gateway settings.
        return 0
