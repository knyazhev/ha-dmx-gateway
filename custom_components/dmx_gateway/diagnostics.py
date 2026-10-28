"""Diagnostics deliberately omit all credentials."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import DmxGatewayConfigEntry
from .const import CONF_TOKEN


TO_REDACT = {CONF_TOKEN, "password", "ssid", "api_key", "pairing_credential"}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: DmxGatewayConfigEntry) -> dict[str, Any]:
    """Return only known logical gateway state and redacted entry settings."""
    snapshot = entry.runtime_data.coordinator.data
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "gateway": asdict(snapshot.info),
        "config": asdict(snapshot.config),
        "diagnostics": asdict(snapshot.diagnostics),
        "integration": {
            "last_update_success": entry.runtime_data.coordinator.last_update_success,
            "state_model": "commanded_logical_state_only_no_fixture_feedback",
        },
    }
