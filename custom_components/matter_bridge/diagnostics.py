"""Diagnostics for Matter Bridge."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .coordinator import MatterBridgeConfigEntry

TO_REDACT = {
    CONF_PASSWORD,
    CONF_URL,
    CONF_USERNAME,
    "passcode",
    "discriminator",
    "manualPairingCode",
    "qrPairingCode",
    "fabricId",
    "nodeId",
    "rootNodeId",
    "peerNodeId",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: MatterBridgeConfigEntry
) -> dict[str, Any]:
    """Return diagnostics with pairing codes and fabric ids removed."""
    coordinator = entry.runtime_data
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "last_update_success": coordinator.last_update_success,
        "data": async_redact_data(asdict(coordinator.data), TO_REDACT)
        if coordinator.data
        else None,
    }
