"""Async client for the gateway Product HTTP API /v1."""

from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import quote

try:  # HA provides aiohttp; fallback keeps dependency-free model tests runnable.
    from aiohttp import ClientError
except ImportError:  # pragma: no cover - only used outside Home Assistant.
    ClientError = OSError

from .const import API_VERSION, REQUEST_TIMEOUT
from .models import Diagnostics, GatewayConfig, GatewayInfo, GatewayResponseError, GatewayState


class GatewayApiError(Exception):
    """Base Product API error."""


class GatewayConnectionError(GatewayApiError):
    """The gateway could not be reached."""


class GatewayTimeoutError(GatewayConnectionError):
    """The gateway did not answer in time."""


class GatewayAuthenticationError(GatewayApiError):
    """The development bearer token was rejected."""


class GatewayInvalidResponseError(GatewayApiError):
    """The API answer was invalid or incompatible."""


class GatewayRevisionConflictError(GatewayApiError):
    """A configuration PUT lost its compare-and-swap race."""


class GatewayUnsupportedOperationError(GatewayApiError):
    """The requested operation is not supported by the gateway."""


class GatewayApiCompatibilityError(GatewayApiError):
    """The gateway exposes an unsupported API version."""


class DmxGatewayApiClient:
    """One shared, non-blocking API client per configured gateway."""

    def __init__(self, session: Any, host: str, port: int, token: str) -> None:
        self._session = session
        self._base_url = f"http://{host}:{port}/v1"
        self._token = token

    def update_connection(self, host: str, port: int, token: str) -> None:
        """Update entry connection data without changing gateway identity."""
        self._base_url = f"http://{host}:{port}/v1"
        self._token = token

    async def async_get_info(self) -> GatewayInfo:
        payload = await self._async_request("GET", "/info")
        try:
            return GatewayInfo.from_api(payload)
        except GatewayResponseError as err:
            if "API version" in str(err):
                raise GatewayApiCompatibilityError(str(err)) from err
            raise GatewayInvalidResponseError(str(err)) from err

    async def async_get_config(self) -> GatewayConfig:
        return self._parse_config(await self._async_request("GET", "/config"))

    async def async_put_config(self, config: dict[str, Any], expected_revision: int) -> GatewayConfig:
        return self._parse_config(await self._async_request("PUT", "/config", {"expected_revision": expected_revision, "config": config}))

    async def async_set_channel_state(self, channel_id: str, brightness: float, transition_ms: int = 0) -> None:
        if not 0.0 <= brightness <= 1.0 or not 0 <= transition_ms <= 600000:
            raise GatewayUnsupportedOperationError("brightness or transition_ms outside Product API range")
        await self._async_request("POST", f"/channels/{quote(channel_id, safe='')}/state", {"brightness": brightness, "transition_ms": transition_ms})

    async def async_set_blackout(self, state: bool) -> bool:
        payload = await self._async_request("POST", "/blackout", {"state": state})
        returned = payload.get("state")
        if not isinstance(returned, bool):
            raise GatewayInvalidResponseError("invalid blackout response")
        return returned

    async def async_get_diagnostics(self) -> Diagnostics:
        try:
            return Diagnostics.from_api(await self._async_request("GET", "/diagnostics"))
        except GatewayResponseError as err:
            raise GatewayInvalidResponseError(str(err)) from err

    async def async_get_state(self) -> GatewayState:
        try:
            return GatewayState.from_api(await self._async_request("GET", "/state"))
        except GatewayResponseError as err:
            raise GatewayInvalidResponseError(str(err)) from err

    def _parse_config(self, payload: dict[str, Any]) -> GatewayConfig:
        try:
            return GatewayConfig.from_api(payload)
        except GatewayResponseError as err:
            raise GatewayInvalidResponseError(str(err)) from err

    async def _async_request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self._token}", "Accept": "application/json"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        try:
            async with self._session.request(method, self._base_url + path, headers=headers, json=payload, timeout=REQUEST_TIMEOUT) as response:
                # Authentication is determined by the HTTP status. Some
                # intermediaries return a non-JSON 401 page, so classify it
                # before attempting to decode a structured API response.
                if response.status == 401:
                    raise GatewayAuthenticationError("gateway rejected credential")
                try:
                    body = await response.json(content_type=None)
                except (ValueError, TypeError) as err:
                    raise GatewayInvalidResponseError("gateway did not return JSON") from err
        except asyncio.TimeoutError as err:
            raise GatewayTimeoutError("gateway request timed out") from err
        except (OSError, ClientError) as err:
            raise GatewayConnectionError("gateway connection failed") from err
        if not isinstance(body, dict):
            raise GatewayInvalidResponseError("gateway JSON root is not an object")
        if response.status == 409 and body.get("error") == "revision_conflict":
            raise GatewayRevisionConflictError("gateway configuration changed")
        if response.status in (404, 422) and body.get("error") in {"unsupported_operation", "unknown_channel"}:
            raise GatewayUnsupportedOperationError(str(body.get("message", body["error"])))
        if response.status < 200 or response.status >= 300:
            raise GatewayApiError(f"gateway returned HTTP {response.status}: {body.get('error', 'unknown_error')}")
        return body
