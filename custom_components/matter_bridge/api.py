"""Client for the Home Assistant Matter Hub REST API.

Matter Hub is reached at a URL (``http://host:8482`` by default). That covers
Docker and standalone installs. The Matter Hub app by default only lets the
Supervisor in (``--http-ip-whitelist=172.30.32.2``, everything else gets 403).
Its ``allow_local_access`` option also allows loopback at
``http://127.0.0.1:<ingress port>``, with Basic auth as user ``hamh`` when
``local_api_password`` is set (``app.py`` finds the port). A 403 is ``MatterHubForbiddenError``.

There is no Supervisor transport. Ingress sessions belong to a logged-in
user's frontend; an integration must not mint one with the Supervisor token.

Responses can carry a bridge's pairing code, QR payload, passcode and
discriminator. Those values stay inside this client. Nothing here logs a
response body, copies one into an exception, or returns one except to the
coordinator, which keeps it off entities and diagnostics.
"""

from __future__ import annotations

import asyncio
import base64
import json as json_lib
import logging
from typing import Any

import aiohttp

from .const import REQUEST_TIMEOUT

_LOGGER = logging.getLogger(__name__)


class MatterHubError(Exception):
    """Base error talking to Matter Hub."""


class MatterHubConnectionError(MatterHubError):
    """Matter Hub could not be reached."""


class MatterHubAuthError(MatterHubError):
    """Matter Hub rejected the credentials."""


class MatterHubForbiddenError(MatterHubError):
    """Matter Hub refused this address (its IP allow list).

    The Matter Hub app without a local API password only lets the Supervisor
    in, so a password can't fix this; it isn't an authentication error.
    """


class MatterHubCommandError(MatterHubError):
    """Matter Hub answered a command with an error."""


class DirectTransport:
    """Talks to Matter Hub at a URL."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        url: str,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        self._session = session
        self._base = url.rstrip("/")
        # Built by hand: aiohttp.BasicAuth is deprecated in newer aiohttp.
        self._auth_header: dict[str, str] = {}
        if username:
            token = base64.b64encode(f"{username}:{password or ''}".encode()).decode()
            self._auth_header = {"Authorization": f"Basic {token}"}

    async def request(
        self,
        method: str,
        path: str,
        json: Any = None,
        ok_statuses: tuple[int, ...] = (),
    ) -> Any:
        """Send a request to ``/api/...`` and return the decoded body."""
        status, body, resp = await self._send(method, path, json)
        if status < 400 or status in ok_statuses:
            return body
        self._raise_for(status, body, resp)
        return None  # pragma: no cover

    async def _send(
        self, method: str, path: str, json: Any
    ) -> tuple[int, Any, aiohttp.ClientResponse]:
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                resp = await self._session.request(
                    method,
                    f"{self._base}{path}",
                    headers=self._auth_header or None,
                    json=json,
                )
                text = await resp.text()
        except (TimeoutError, aiohttp.ClientError) as err:
            # The exception text is the client error, not the response body.
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
        # Command errors use Matter Hub's short ``error`` string. Pairing
        # material is not part of that string; don't attach the raw body.
        if (
            status == 401
            and "basic" in resp.headers.get("WWW-Authenticate", "").lower()
        ):
            raise MatterHubAuthError("Matter Hub rejected the username or password")
        if status == 403:
            raise MatterHubForbiddenError(
                "Matter Hub refused this connection (its IP allow list)"
            )
        message = body.get("error") if isinstance(body, dict) else None
        if status == 404:
            raise MatterHubCommandError(message or "Not found")
        if status >= 500 and not message:
            raise MatterHubConnectionError(f"Matter Hub returned HTTP {status}")
        raise MatterHubCommandError(message or f"Matter Hub returned HTTP {status}")


class MatterHubClient:
    """High level Matter Hub API."""

    def __init__(self, transport: DirectTransport) -> None:
        self.transport = transport

    async def async_get_health(self) -> dict[str, Any]:
        """Overall health. HTTP 503 still carries the body when unhealthy."""
        data = await self.transport.request("GET", "/api/health", ok_statuses=(503,))
        if not isinstance(data, dict) or "status" not in data:
            raise MatterHubConnectionError("Unexpected health response from Matter Hub")
        return data

    async def async_get_bridges(self) -> list[dict[str, Any]]:
        """All bridges with status, commissioning and device counts.

        Commissioning includes the pairing code and QR payload. Callers must
        not copy those fields onto entities, events or log records.
        """
        data = await self.transport.request("GET", "/api/matter/bridges")
        if not isinstance(data, list):
            raise MatterHubConnectionError("Unexpected bridge list from Matter Hub")
        return data

    async def async_bridge_action(self, bridge_id: str, action: str) -> Any:
        """Run a bridge action: start, stop, restart, refresh, force-sync,
        open-commissioning-window.

        The return value is Matter Hub's reply. It is not logged and is not
        written to entity state. Opening a pairing window does not reveal the
        code; the code stays in the Matter Hub web interface.
        """
        return await self.transport.request(
            "POST", f"/api/matter/bridges/{bridge_id}/actions/{action}"
        )

    async def async_all_bridges_action(self, action: str) -> Any:
        """start-all, stop-all or restart-all."""
        return await self.transport.request(
            "POST", f"/api/matter/bridges/actions/{action}"
        )
