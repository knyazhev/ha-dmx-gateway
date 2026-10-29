"""Brightness-only logical DMX light entities."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import ATTR_BRIGHTNESS, ATTR_TRANSITION, ColorMode, LightEntity, LightEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DmxGatewayConfigEntry
from .const import CONF_DEFAULT_FADE_DURATION, CONF_DEFAULT_FADE_ENABLED, CONF_DEFAULT_FADE_RATE, DEFAULT_FADE_DURATION, DEFAULT_FADE_ENABLED, DOMAIN
from .coordinator import GatewayCoordinator
from .models import Channel, RuntimeDevice


async def async_setup_entry(hass: HomeAssistant, entry: DmxGatewayConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    """Add one entity for every currently configured brightness channel."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        DmxBrightnessLight(coordinator, device, channel)
        for device in coordinator.data.config.devices
        for channel in device.channels
        if channel.type == "brightness"
    )


class DmxBrightnessLight(CoordinatorEntity[GatewayCoordinator], LightEntity):
    """Known state is gateway-commanded state, not DMX fixture feedback."""

    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_color_mode = ColorMode.BRIGHTNESS
    # Without this capability Home Assistant removes ``transition`` before it
    # reaches async_turn_on/off, which silently turns a requested fade into an
    # immediate gateway write.
    _attr_supported_features = LightEntityFeature.TRANSITION
    _attr_has_entity_name = True

    def __init__(self, coordinator: GatewayCoordinator, device: RuntimeDevice, channel: Channel) -> None:
        super().__init__(coordinator)
        self._device_id = device.device_id
        self._channel_id = channel.channel_id
        self._attr_unique_id = f"{coordinator.info.gateway_id}_{channel.channel_id}"

    @property
    def name(self) -> str:
        channel = self._channel()
        return channel.name if channel else self._channel_id

    @property
    def device_info(self) -> DeviceInfo:
        device = self._device()
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self.coordinator.info.gateway_id}:device:{self._device_id}")},
            via_device=(DOMAIN, self.coordinator.info.gateway_id),
            name=device.name if device else self._device_id,
            model="DMX runtime device",
        )

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self._channel() is not None

    @property
    def is_on(self) -> bool:
        return self._brightness > 0

    @property
    def brightness(self) -> int:
        return round(self._brightness * 255)

    async def async_turn_on(self, **kwargs: Any) -> None:
        brightness = kwargs.get(ATTR_BRIGHTNESS, 255) / 255
        await self.coordinator.async_set_channel(self._channel_id, brightness, self._transition_ms(kwargs, brightness))

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_channel(self._channel_id, 0.0, self._transition_ms(kwargs, 0.0))

    @property
    def _brightness(self) -> float:
        return self.coordinator.data.commanded_brightness.get(self._channel_id, 0.0) if self.coordinator.data else 0.0

    def _device(self) -> RuntimeDevice | None:
        return self.coordinator.data.config.device_for_channel(self._channel_id) if self.coordinator.data else None

    def _channel(self) -> Channel | None:
        device = self._device()
        return next((channel for channel in device.channels if channel.channel_id == self._channel_id), None) if device else None

    def _transition_ms(self, kwargs: dict[str, Any], target: float) -> int:
        # An explicit HA transition always wins, including transition=0 to
        # request an immediate change. Otherwise use the per-entry default
        # duration is the time for each 10 percentage-point change.
        if ATTR_TRANSITION in kwargs:
            return max(0, min(600000, round(float(kwargs[ATTR_TRANSITION]) * 1000)))
        if not self.coordinator.entry.options.get(CONF_DEFAULT_FADE_ENABLED, DEFAULT_FADE_ENABLED):
            return 0
        duration = float(self.coordinator.entry.options.get(CONF_DEFAULT_FADE_DURATION, self.coordinator.entry.options.get(CONF_DEFAULT_FADE_RATE, DEFAULT_FADE_DURATION)))
        if duration <= 0:
            return 0
        delta = abs(target - self._brightness)
        return max(0, min(600000, round(delta * duration * 10.0 * 1000.0)))
