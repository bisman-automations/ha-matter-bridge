"""Constants for Matter Bridge."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "matter_bridge"

CONF_CONNECTION: Final = "connection"
CONF_APP_SLUG: Final = "app_slug"

CONNECTION_APP: Final = "app"
CONNECTION_DIRECT: Final = "direct"

DEFAULT_URL: Final = "http://homeassistant.local:8482"
DEFAULT_SCAN_INTERVAL: Final = timedelta(seconds=30)
REQUEST_TIMEOUT: Final = 15

# Slugs the Home Assistant Matter Hub app is published under. Supervisor
# prefixes them with the repository hash ("3fd9e6b0_hamh") or "local_".
APP_SLUGS: Final = ("hamh", "hamh-alpha", "hamh-testing", "hamh_alpha", "hamh_testing")
APP_PROJECT_URL_MARKER: Final = "home-assistant-matter-hub"

MATTER_HUB_NAME: Final = "Home Assistant Matter Hub"
MATTER_HUB_URL: Final = "https://github.com/RiDDiX/home-assistant-matter-hub"

BRIDGE_STATUSES: Final = ["starting", "running", "stopped", "failed"]
HEALTH_STATUSES: Final = ["healthy", "degraded", "unhealthy"]
