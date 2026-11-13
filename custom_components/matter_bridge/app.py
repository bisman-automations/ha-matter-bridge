"""Find the Matter Hub app on this Home Assistant.

The app's ``allow_local_access`` option (Alpha, after 2.1.0-alpha.990, which
used ``local_api_password`` alone) lets processes on the host reach its API at
``http://127.0.0.1:<ingress port>``; with ``local_api_password`` set they use
Basic auth as user ``hamh`` (RiDDiX/home-assistant-matter-hub#551). The ingress
port is assigned by the Supervisor (``ingress_port: 0``), so it differs per
install. Home Assistant's own Supervisor integration already keeps every
app's info, including that port; this module only reads it through
``hassio.get_addons_info``. It never calls the Supervisor itself and never
creates an ingress session.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.hassio import is_hassio

_LOGGER = logging.getLogger(__name__)

# Slugs in RiDDiX/home-assistant-addons (Stable, Alpha, Testing). Installed
# apps from a third-party repository are named ``<repository hash>_<slug>``.
APP_SLUGS = ("hamh", "hamh-alpha", "hamh-testing")
APP_USERNAME = "hamh"
APP_HOST = "127.0.0.1"


@dataclass(frozen=True, slots=True)
class MatterHubApp:
    """One installed Matter Hub app."""

    slug: str
    name: str
    port: int
    started: bool

    @property
    def url(self) -> str:
        """The local API address."""
        return app_url(self.port)


def app_url(port: int) -> str:
    """Local API address for an ingress port."""
    return f"http://{APP_HOST}:{port}"


def _is_matter_hub(slug: str) -> bool:
    short = slug.split("_", 1)[-1].replace("_", "-")
    return short in APP_SLUGS


def find_apps(hass: HomeAssistant) -> list[MatterHubApp]:
    """Installed Matter Hub apps with a known port, started ones first.

    Empty when Home Assistant has no Supervisor, or its app info isn't
    loaded yet.
    """
    if not is_hassio(hass):
        return []
    try:
        from homeassistant.components.hassio import get_addons_info  # noqa: PLC0415

        infos = get_addons_info(hass) or {}
    except Exception:  # noqa: BLE001 - no Supervisor or not ready yet
        _LOGGER.debug("Matter Hub app lookup unavailable", exc_info=True)
        return []
    apps: list[MatterHubApp] = []
    for slug, info in infos.items():
        if not info or not _is_matter_hub(slug):
            continue
        port = info.get("ingress_port")
        if not isinstance(port, int) or port <= 0:
            continue
        apps.append(
            MatterHubApp(
                slug=slug,
                name=str(info.get("name") or slug),
                port=port,
                started=info.get("state") == "started",
            )
        )
    apps.sort(key=lambda app: (not app.started, app.name))
    return apps


def find_app(hass: HomeAssistant, slug: str) -> MatterHubApp | None:
    """The installed app with this slug, if any."""
    return next((app for app in find_apps(hass) if app.slug == slug), None)
