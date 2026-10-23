"""Client for the Home Assistant Matter Hub REST API.

Matter Hub can be reached two ways:

* As a Home Assistant app (add-on). The app runs on the host network but only
  accepts requests from the Supervisor's ingress proxy, so requests go through
  ``http://supervisor/ingress/<token>/...`` with an ingress session that Home
  Assistant Core creates with its Supervisor token.
* Directly, for Docker / standalone installs, at ``http://host:8482``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
import base64
from dataclasses import dataclass
import json as json_lib
import logging
import os
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import APP_PROJECT_URL_MARKER, APP_SLUGS, REQUEST_TIMEOUT

_LOGGER = logging.getLogger(__name__)

INGRESS_COOKIE = "ingress_session"


class MatterHubError(Exception):
    """Base error talking to Matter Hub."""


class MatterHubConnectionError(MatterHubError):
    """Matter Hub could not be reached."""


class MatterHubAuthError(MatterHubError):
    """Matter Hub rejected the credentials."""


class MatterHubCommandError(MatterHubError):
    """Matter Hub answered a command with an error."""


class MatterHubAppError(MatterHubConnectionError):
    """The Matter Hub app is missing, stopped or has no ingress."""


@dataclass(slots=True, frozen=True)
class MatterHubApp:
    """An installed Matter Hub app as reported by the Supervisor."""

    slug: str
    name: str
    state: str
    version: str | None


def supervisor_available() -> bool:
    """Return True when Home Assistant runs under the Supervisor."""
    return bool(os.environ.get("SUPERVISOR_TOKEN"))


def _supervisor_base() -> str:
    return f"http://{os.environ.get('SUPERVISOR', 'supervisor')}"


def _supervisor_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {os.environ.get('SUPERVISOR_TOKEN', '')}"}


def is_matter_hub_app(app: dict[str, Any]) -> bool:
    """Return True when a Supervisor app entry is Matter Hub."""
    slug = str(app.get("slug", ""))
    suffix = slug.split("_", 1)[1] if "_" in slug else slug
    if suffix in APP_SLUGS:
        return True
    return APP_PROJECT_URL_MARKER in str(app.get("url") or "").lower()


async def _supervisor_call(
    session: aiohttp.ClientSession,
    method: str,
    path: str,
    json: dict[str, Any] | None = None,
) -> Any:
    """Call the Supervisor API and unwrap its ``data`` envelope."""
    try:
        async with asyncio.timeout(REQUEST_TIMEOUT):
            resp = await session.request(
                method,
                f"{_supervisor_base()}{path}",
                headers=_supervisor_headers(),
                json=json,
            )
            body = await resp.json(content_type=None)
    except (TimeoutError, aiohttp.ClientError, ValueError) as err:
        raise MatterHubConnectionError(f"Supervisor request failed: {err}") from err
    if not isinstance(body, dict) or body.get("result") != "ok":
        message = body.get("message") if isinstance(body, dict) else None
        raise MatterHubAppError(message or f"Supervisor returned HTTP {resp.status}")
    return body.get("data", {})


async def async_find_apps(hass: HomeAssistant) -> list[MatterHubApp]:
    """List installed Matter Hub apps."""
    session = async_get_clientsession(hass)
    data = await _supervisor_call(session, "GET", "/addons")
    return [
        MatterHubApp(
            slug=app["slug"],
            name=app.get("name") or app["slug"],
            state=app.get("state", "unknown"),
            version=app.get("version"),
        )
        for app in data.get("addons", [])
        if is_matter_hub_app(app)
    ]


class Transport(ABC):
    """Sends a request to the Matter Hub web API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        self._session = session
        # Built by hand: aiohttp.BasicAuth is deprecated in newer aiohttp.
        self._auth_header: dict[str, str] = {}
        if username:
            token = base64.b64encode(f"{username}:{password or ''}".encode()).decode()
            self._auth_header = {"Authorization": f"Basic {token}"}

    @abstractmethod
    async def request(
        self, method: str, path: str, json: Any = None, ok_statuses: tuple[int, ...] = ()
    ) -> Any:
        """Send a request to ``/api/...`` and return the decoded body."""

    async def _send(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None,
        json: Any,
    ) -> tuple[int, Any, aiohttp.ClientResponse]:
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                resp = await self._session.request(
                    method, url, headers={**(headers or {}), **self._auth_header}, json=json
                )
                text = await resp.text()
        except (TimeoutError, aiohttp.ClientError) as err:
            raise MatterHubConnectionError(f"Cannot reach Matter Hub: {err}") from err
        body: Any = text or None
        if text and text.lstrip()[:1] in ("{", "["):
            try:
                body = json_lib.loads(text)
            except ValueError:
                body = text
        return resp.status, body, resp

    @staticmethod
    def _raise_for(status: int, body: Any, resp: aiohttp.ClientResponse) -> None:
        if status == 401 and "basic" in resp.headers.get("WWW-Authenticate", "").lower():
            raise MatterHubAuthError("Matter Hub rejected the username or password")
        if status == 403:
            raise MatterHubAuthError("Matter Hub refused access (IP allow list)")
        message = body.get("error") if isinstance(body, dict) else body
        if status == 404:
            raise MatterHubCommandError(message or "Not found")
        if status >= 500 and not message:
            raise MatterHubConnectionError(f"Matter Hub returned HTTP {status}")
        raise MatterHubCommandError(message or f"Matter Hub returned HTTP {status}")


class DirectTransport(Transport):
    """Talks to Matter Hub at a URL (Docker / standalone)."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        url: str,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        super().__init__(session, username, password)
        self._base = url.rstrip("/")

    async def request(
        self, method: str, path: str, json: Any = None, ok_statuses: tuple[int, ...] = ()
    ) -> Any:
        status, body, resp = await self._send(
            method, f"{self._base}{path}", headers=None, json=json
        )
        if status < 400 or status in ok_statuses:
            return body
        self._raise_for(status, body, resp)
        return None  # pragma: no cover


class SupervisorTransport(Transport):
    """Talks to the Matter Hub app through Supervisor ingress."""

    def __init__(
        self,
        hass: HomeAssistant,
        session: aiohttp.ClientSession,
        slug: str,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        super().__init__(session, username, password)
        self._hass = hass
        self.slug = slug
        self._ingress_token: str | None = None
        self._ingress_session: str | None = None
        self._lock = asyncio.Lock()
        self.app_info: dict[str, Any] = {}

    async def async_app_info(self) -> dict[str, Any]:
        """Fetch the app's Supervisor info (state, version, ingress entry)."""
        self.app_info = await _supervisor_call(
            self._session, "GET", f"/addons/{self.slug}/info"
        )
        return self.app_info

    async def _ensure_ingress(self, *, renew: bool = False) -> tuple[str, str]:
        async with self._lock:
            if renew:
                self._ingress_session = None
            if self._ingress_token is None or self._ingress_session is None:
                info = await self.async_app_info()
                if info.get("state") != "started":
                    raise MatterHubAppError(
                        f"The Matter Hub app is {info.get('state', 'not running')}"
                    )
                entry = info.get("ingress_entry") or ""
                token = entry.rstrip("/").rsplit("/", 1)[-1] if entry else ""
                if not token:
                    raise MatterHubAppError("The Matter Hub app has no ingress entry")
                self._ingress_token = token
            if self._ingress_session is None:
                user_id = await self._session_user_id()
                data = await _supervisor_call(
                    self._session, "POST", "/ingress/session", {"user_id": user_id}
                )
                self._ingress_session = data["session"]
            return self._ingress_token, self._ingress_session

    async def _session_user_id(self) -> str:
        """Ingress sessions belong to a user; Matter Hub's panel needs an admin."""
        owner = await self._hass.auth.async_get_owner()
        if owner and owner.is_active:
            return owner.id
        for user in await self._hass.auth.async_get_users():
            if user.is_active and user.is_admin and not user.system_generated:
                return user.id
        raise MatterHubAppError("No active administrator to open an ingress session")

    async def request(
        self, method: str, path: str, json: Any = None, ok_statuses: tuple[int, ...] = ()
    ) -> Any:
        for attempt in range(2):
            token, ingress_session = await self._ensure_ingress(renew=attempt > 0)
            headers = {"Cookie": f"{INGRESS_COOKIE}={ingress_session}"}
            status, body, resp = await self._send(
                method,
                f"{_supervisor_base()}/ingress/{token}{path}",
                headers=headers,
                json=json,
            )
            if status < 400 or status in ok_statuses:
                return body
            # A 401 without a Basic challenge is the Supervisor rejecting an
            # expired ingress session (sessions live 15 minutes): renew once.
            # A 502 means the app restarted and may have a new ingress port.
            basic = "basic" in resp.headers.get("WWW-Authenticate", "").lower()
            if attempt == 0 and ((status == 401 and not basic) or status == 502):
                if status == 502:
                    self._ingress_token = None
                continue
            if status == 401 and not basic:
                raise MatterHubAppError("Supervisor rejected the ingress session")
            self._raise_for(status, body, resp)
        return None  # pragma: no cover


class MatterHubClient:
    """High level Matter Hub API."""

    def __init__(self, transport: Transport) -> None:
        self.transport = transport

    async def async_get_health(self) -> dict[str, Any]:
        """Overall health. HTTP 503 still carries the body when unhealthy."""
        data = await self.transport.request("GET", "/api/health", ok_statuses=(503,))
        if not isinstance(data, dict) or "status" not in data:
            raise MatterHubConnectionError("Unexpected health response from Matter Hub")
        return data

    async def async_get_bridges(self) -> list[dict[str, Any]]:
        """All bridges with status, commissioning and device counts."""
        data = await self.transport.request("GET", "/api/matter/bridges")
        if not isinstance(data, list):
            raise MatterHubConnectionError("Unexpected bridge list from Matter Hub")
        return data

    async def async_bridge_action(self, bridge_id: str, action: str) -> Any:
        """Run a bridge action: start, stop, restart, refresh, force-sync,
        open-commissioning-window."""
        return await self.transport.request(
            "POST", f"/api/matter/bridges/{bridge_id}/actions/{action}"
        )

    async def async_all_bridges_action(self, action: str) -> Any:
        """start-all, stop-all or restart-all."""
        return await self.transport.request(
            "POST", f"/api/matter/bridges/actions/{action}"
        )
