"""Constants for Matter Bridge."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "matter_bridge"

CONF_CONNECTION: Final = "connection"
# Stored on entries created before 2.0.0, which reached the Matter Hub app
# through a Supervisor ingress session. New entries never set this. Setup
# refuses it and a repair asks for a URL instead.
CONF_APP_SLUG: Final = "app_slug"

CONNECTION_APP: Final = "app"
CONNECTION_DIRECT: Final = "direct"

DEFAULT_URL: Final = "http://homeassistant.local:8482"
DEFAULT_SCAN_INTERVAL: Final = timedelta(seconds=30)
REQUEST_TIMEOUT: Final = 15

MATTER_HUB_NAME: Final = "Home Assistant Matter Hub"
MATTER_HUB_URL: Final = "https://github.com/RiDDiX/home-assistant-matter-hub"

BRIDGE_STATUSES: Final = ["starting", "running", "stopped", "failed"]
HEALTH_STATUSES: Final = ["healthy", "degraded", "unhealthy"]

# The manual and QR pairing codes, and the passcode and discriminator they
# are built from. Matter Hub's bridge payload uses these names
# (packages/common/src/bridge-data.ts, BridgeCommissioning). Diagnostics
# redact them. They are never copied onto an entity.
PAIRING_CODE_KEYS: Final = frozenset(
    {
        "passcode",
        "discriminator",
        "manualPairingCode",
        "qrPairingCode",
        "manual_pairing_code",
        "qr_pairing_code",
        "pairingCode",
        "pairing_code",
        "qrCode",
        "qr_code",
        "setupPayload",
        "setupPinCode",
        "setup_pin_code",
        "pinCode",
        "pincode",
    }
)


def ingress_removed_issue_id(entry_id: str) -> str:
    """Repair issue for a 1.x entry that still uses the app connection."""
    return f"ingress_removed_{entry_id}"


def app_unavailable_issue_id(entry_id: str) -> str:
    """Issue id used before 2.0.0 when the app looked stopped.

    Setup deletes any leftover issue with this id. Nothing creates it now.
    """
    return f"app_unavailable_{entry_id}"
