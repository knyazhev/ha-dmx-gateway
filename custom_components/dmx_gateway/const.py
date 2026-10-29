"""Constants for the DMX Gateway integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "dmx_gateway"
PLATFORMS: Final = ["light", "switch"]

CONF_HOST: Final = "host"
CONF_PORT: Final = "port"
CONF_TOKEN: Final = "token"
DEFAULT_PORT: Final = 8080
CONF_DEFAULT_FADE_RATE: Final = "default_fade_rate"
DEFAULT_FADE_RATE: Final = 10.0

API_VERSION: Final = "v1"
CONFIG_REFRESH_INTERVAL: Final = 60
DIAGNOSTICS_REFRESH_INTERVAL: Final = 60
REQUEST_TIMEOUT: Final = 10

MANUFACTURER: Final = "DMX Gateway"
