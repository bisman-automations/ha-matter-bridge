"""Diagnostics for Matter Bridge.

Pairing codes and QR payloads are removed before the download is built.
``async_redact_data`` matches dictionary keys. A second pass redacts any
string that looks like a Matter QR payload (``MT:...``), so a future field
name cannot leak the QR code into a diagnostics download.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .const import PAIRING_CODE_KEYS
from .coordinator import MatterBridgeConfigEntry

# Fabric and node ids identify a commissioned fabric. Treat them like the
# pairing material: useful to Matter Hub, not to a diagnostics download.
TO_REDACT = PAIRING_CODE_KEYS | {
    CONF_PASSWORD,
    CONF_URL,
    CONF_USERNAME,
    "fabricId",
    "nodeId",
    "rootNodeId",
    "peerNodeId",
}

# Matter QR payloads always start with this. The example in the Matter SDK
# does too, so tests can tell a redacted payload from a real one.
_QR_PREFIX = "MT:"
_REDACTED = "**REDACTED**"


def _redact_qr_payloads(value: Any) -> Any:
    """Replace Matter QR payload strings wherever they sit in the tree."""
    if isinstance(value, dict):
        return {key: _redact_qr_payloads(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_qr_payloads(item) for item in value]
    if isinstance(value, str) and value.startswith(_QR_PREFIX):
        return _REDACTED
    return value


def redact(data: Any) -> Any:
    """Remove secrets by key, then any remaining QR payload strings."""
    return _redact_qr_payloads(async_redact_data(data, TO_REDACT))


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: MatterBridgeConfigEntry
) -> dict[str, Any]:
    """Return diagnostics with pairing codes and fabric ids removed."""
    coordinator = entry.runtime_data
    return {
        "entry": redact(dict(entry.data)),
        "last_update_success": coordinator.last_update_success,
        "data": redact(asdict(coordinator.data)) if coordinator.data else None,
    }
