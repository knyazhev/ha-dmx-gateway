"""Typed Product API models. These deliberately contain no HA entity logic."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any

from .const import API_VERSION


class GatewayResponseError(ValueError):
    """The gateway returned malformed or incompatible JSON."""


def _string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise GatewayResponseError(f"invalid {field}")
    return value


def _integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise GatewayResponseError(f"invalid {field}")
    return value


@dataclass(frozen=True, slots=True)
class GatewayInfo:
    gateway_id: str
    model: str
    firmware_version: str
    api_version: str

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "GatewayInfo":
        api_version = _string(payload.get("api_version"), "api_version")
        if api_version != API_VERSION:
            raise GatewayResponseError(f"unsupported API version: {api_version}")
        return cls(
            gateway_id=_string(payload.get("gateway_id"), "gateway_id"),
            model=_string(payload.get("model"), "model"),
            firmware_version=_string(payload.get("firmware_version"), "firmware_version"),
            api_version=api_version,
        )


@dataclass(frozen=True, slots=True)
class Channel:
    channel_id: str
    name: str
    type: str
    offset: int

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "Channel":
        channel_type = _string(payload.get("type"), "channel.type")
        if channel_type != "brightness":
            raise GatewayResponseError(f"unsupported channel type: {channel_type}")
        return cls(
            channel_id=_string(payload.get("channel_id"), "channel_id"),
            name=_string(payload.get("name"), "channel.name"),
            type=channel_type,
            offset=_integer(payload.get("offset"), "channel.offset"),
        )


@dataclass(frozen=True, slots=True)
class RuntimeDevice:
    device_id: str
    name: str
    start_address: int
    channels: tuple[Channel, ...]

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "RuntimeDevice":
        channels = payload.get("channels")
        if not isinstance(channels, list):
            raise GatewayResponseError("invalid device.channels")
        if not all(isinstance(channel, dict) for channel in channels):
            raise GatewayResponseError("invalid channel entry")
        return cls(
            device_id=_string(payload.get("device_id"), "device_id"),
            name=_string(payload.get("name"), "device.name"),
            start_address=_integer(payload.get("start_address"), "device.start_address"),
            channels=tuple(Channel.from_api(channel) for channel in channels),
        )


@dataclass(frozen=True, slots=True)
class GatewayConfig:
    schema_version: int
    config_revision: int
    devices: tuple[RuntimeDevice, ...]

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "GatewayConfig":
        devices = payload.get("devices")
        if not isinstance(devices, list):
            raise GatewayResponseError("invalid devices")
        parsed = tuple(RuntimeDevice.from_api(device) for device in devices if isinstance(device, dict))
        if len(parsed) != len(devices):
            raise GatewayResponseError("invalid device entry")
        return cls(
            schema_version=_integer(payload.get("schema_version"), "schema_version"),
            config_revision=_integer(payload.get("config_revision"), "config_revision"),
            devices=parsed,
        )

    def device_for_channel(self, channel_id: str) -> RuntimeDevice | None:
        return next((device for device in self.devices if any(channel.channel_id == channel_id for channel in device.channels)), None)


@dataclass(frozen=True, slots=True)
class Diagnostics:
    uptime_s: int
    tx_rate_fps: float
    tx_errors: int
    config_revision: int
    runtime_devices: int
    runtime_channels: int
    active_transitions: int
    blackout: bool

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "Diagnostics":
        required_ints = ("uptime_s", "tx_errors", "config_revision", "runtime_devices", "runtime_channels", "active_transitions")
        values = {name: _integer(payload.get(name), name) for name in required_ints}
        fps = payload.get("tx_rate_fps")
        if isinstance(fps, bool) or not isinstance(fps, (int, float)):
            raise GatewayResponseError("invalid tx_rate_fps")
        blackout = payload.get("blackout")
        if not isinstance(blackout, bool):
            raise GatewayResponseError("invalid blackout")
        return cls(tx_rate_fps=float(fps), blackout=blackout, **values)


@dataclass(frozen=True, slots=True)
class LogicalChannelState:
    brightness: float
    transitioning: bool


@dataclass(frozen=True, slots=True)
class GatewayState:
    config_revision: int
    blackout: bool
    channels: dict[str, LogicalChannelState]

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "GatewayState":
        revision = _integer(payload.get("config_revision"), "config_revision")
        blackout = payload.get("blackout")
        channels = payload.get("channels")
        if not isinstance(blackout, bool) or not isinstance(channels, dict):
            raise GatewayResponseError("invalid state snapshot")
        parsed: dict[str, LogicalChannelState] = {}
        for channel_id, channel in channels.items():
            if not isinstance(channel_id, str) or not isinstance(channel, dict):
                raise GatewayResponseError("invalid state channel")
            brightness = channel.get("brightness")
            transitioning = channel.get("transitioning")
            if isinstance(brightness, bool) or not isinstance(brightness, (int, float)) or not isfinite(brightness) or not 0.0 <= brightness <= 1.0:
                raise GatewayResponseError("invalid state brightness")
            if not isinstance(transitioning, bool):
                raise GatewayResponseError("invalid transitioning")
            parsed[channel_id] = LogicalChannelState(float(brightness), transitioning)
        return cls(config_revision=revision, blackout=blackout, channels=parsed)
