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
    dmx_address: int | None = None
    value: int | None = None
    published: bool = True

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "Channel":
        channel_type = _string(payload.get("type"), "channel.type")
        if channel_type not in {"brightness", "Light", "Switch", "RGB Light", "RGBW Light"}:
            raise GatewayResponseError(f"unsupported channel type: {channel_type}")
        return cls(
            channel_id=_string(payload.get("channel_id"), "channel_id"),
            name=_string(payload.get("name"), "channel.name"),
            type=channel_type,
            offset=_integer(payload.get("offset"), "channel.offset"),
            dmx_address=payload.get("dmx_address") if isinstance(payload.get("dmx_address"), int) else None,
            value=payload.get("value") if isinstance(payload.get("value"), int) else None,
            published=payload.get("published", True) if isinstance(payload.get("published", True), bool) else True,
        )


@dataclass(frozen=True, slots=True)
class LogicalChannel:
    channel_id: str
    name: str
    type: str
    dmx_address: int
    value: int
    published: bool

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "LogicalChannel":
        channel_type = _string(payload.get("type"), "logical_channel.type")
        if channel_type not in {"Light", "Switch", "RGB Light", "RGBW Light", "brightness"}:
            raise GatewayResponseError(f"unsupported logical channel type: {channel_type}")
        address = _integer(payload.get("dmx_address"), "logical_channel.dmx_address")
        value = _integer(payload.get("value", 0), "logical_channel.value")
        if not 1 <= address <= 512 or not 0 <= value <= 255:
            raise GatewayResponseError("logical channel value outside range")
        return cls(
            channel_id=_string(payload.get("channel_id"), "logical_channel.channel_id"),
            name=_string(payload.get("name"), "logical_channel.name"),
            type=channel_type,
            dmx_address=address,
            value=value,
            published=payload.get("published", True) if isinstance(payload.get("published", True), bool) else True,
        )


@dataclass(frozen=True, slots=True)
class LogicalGroup:
    group_id: str
    name: str
    type: str
    members: tuple[str, ...]
    published: bool = True

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "LogicalGroup":
        group_type = _string(payload.get("type"), "group.type")
        members = payload.get("members")
        if group_type not in {"RGB", "RGBW"} or not isinstance(members, list) or not all(isinstance(member, str) for member in members):
            raise GatewayResponseError("invalid logical group")
        return cls(
            group_id=_string(payload.get("group_id"), "group.group_id"),
            name=_string(payload.get("name"), "group.name"),
            type=group_type,
            members=tuple(members),
            published=payload.get("published", True) if isinstance(payload.get("published", True), bool) else True,
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
    gateway_id: str | None
    gateway_name: str
    logical_channels: tuple[LogicalChannel, ...]
    groups: tuple[LogicalGroup, ...]
    devices: tuple[RuntimeDevice, ...]

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "GatewayConfig":
        devices = payload.get("devices", [])
        if not isinstance(devices, list):
            raise GatewayResponseError("invalid devices")
        parsed = tuple(RuntimeDevice.from_api(device) for device in devices if isinstance(device, dict))
        if len(parsed) != len(devices):
            raise GatewayResponseError("invalid device entry")
        logical_payload = payload.get("logical_channels", [])
        if not isinstance(logical_payload, list):
            raise GatewayResponseError("invalid logical_channels")
        logical = tuple(LogicalChannel.from_api(channel) for channel in logical_payload if isinstance(channel, dict))
        if len(logical) != len(logical_payload):
            raise GatewayResponseError("invalid logical channel entry")
        groups_payload = payload.get("groups", [])
        if not isinstance(groups_payload, list):
            raise GatewayResponseError("invalid groups")
        groups = tuple(LogicalGroup.from_api(group) for group in groups_payload if isinstance(group, dict))
        if len(groups) != len(groups_payload):
            raise GatewayResponseError("invalid group entry")
        gateway = payload.get("gateway")
        if gateway is not None and not isinstance(gateway, dict):
            raise GatewayResponseError("invalid gateway")
        return cls(
            schema_version=_integer(payload.get("schema_version"), "schema_version"),
            config_revision=_integer(payload.get("config_revision"), "config_revision"),
            gateway_id=gateway.get("id") if isinstance(gateway, dict) and isinstance(gateway.get("id"), str) else None,
            gateway_name=gateway.get("name", "BELARD DMX Gateway") if isinstance(gateway, dict) and isinstance(gateway.get("name", "BELARD DMX Gateway"), str) else "BELARD DMX Gateway",
            logical_channels=logical,
            groups=groups,
            devices=parsed,
        )

    @property
    def channels(self) -> tuple[LogicalChannel, ...]:
        if self.logical_channels:
            return self.logical_channels
        return tuple(
            LogicalChannel(channel.channel_id, channel.name, channel.type, channel.dmx_address or device.start_address + channel.offset, channel.value or 0, channel.published)
            for device in self.devices for channel in device.channels
        )

    @property
    def published_channels(self) -> tuple[LogicalChannel, ...]:
        return tuple(channel for channel in self.channels if channel.published)

    def channel_for_id(self, channel_id: str) -> LogicalChannel | None:
        return next((channel for channel in self.channels if channel.channel_id == channel_id), None)

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
    free_heap: int | None = None
    persistence_load_valid: bool | None = None
    persistence_last_sync_ok: bool | None = None
    logical_channels: int | None = None
    groups: int | None = None

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
        free_heap = payload.get("free_heap")
        if isinstance(free_heap, bool) or (free_heap is not None and not isinstance(free_heap, int)):
            raise GatewayResponseError("invalid free_heap")
        persistence = payload.get("persistence")
        if persistence is not None and not isinstance(persistence, dict):
            raise GatewayResponseError("invalid persistence")
        load_valid = persistence.get("load_valid") if persistence else None
        last_sync_ok = persistence.get("last_sync_ok", persistence.get("last_save_ok")) if persistence else None
        if persistence and persistence.get("save_attempted") is False:
            last_sync_ok = None
        if load_valid is not None and not isinstance(load_valid, bool):
            raise GatewayResponseError("invalid persistence.load_valid")
        if last_sync_ok is not None and not isinstance(last_sync_ok, bool):
            raise GatewayResponseError("invalid persistence.last_sync_ok")
        return cls(
            tx_rate_fps=float(fps), blackout=blackout, free_heap=free_heap,
            persistence_load_valid=load_valid, persistence_last_sync_ok=last_sync_ok, **values,
            logical_channels=payload.get("logical_channels") if isinstance(payload.get("logical_channels"), int) else None,
            groups=payload.get("groups") if isinstance(payload.get("groups"), int) else None,
        )


@dataclass(frozen=True, slots=True)
class LogicalChannelState:
    brightness: float
    transitioning: bool
    target_authoritative: bool = False


@dataclass(frozen=True, slots=True)
class GatewayState:
    config_revision: int
    blackout: bool
    channels: dict[str, LogicalChannelState]
    groups: dict[str, tuple[int, ...]]

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "GatewayState":
        revision = _integer(payload.get("config_revision"), "config_revision")
        blackout = payload.get("blackout")
        channels = payload.get("channels")
        groups = payload.get("groups", {})
        if not isinstance(blackout, bool) or not isinstance(channels, dict) or not isinstance(groups, dict):
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
            parsed[channel_id] = LogicalChannelState(float(brightness), transitioning, "actual_brightness" in channel)
        parsed_groups: dict[str, tuple[int, ...]] = {}
        for group_id, group in groups.items():
            if not isinstance(group_id, str) or not isinstance(group, dict) or not isinstance(group.get("values", []), list) or not all(isinstance(value, int) and 0 <= value <= 255 for value in group.get("values", [])):
                raise GatewayResponseError("invalid state group")
            parsed_groups[group_id] = tuple(group["values"])
        return cls(config_revision=revision, blackout=blackout, channels=parsed, groups=parsed_groups)
