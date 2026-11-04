"""Tests for the Matter Hub URL client."""

from __future__ import annotations

from http import HTTPStatus

import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.matter_bridge.api import (
    DirectTransport,
    MatterHubAuthError,
    MatterHubClient,
    MatterHubCommandError,
    MatterHubConnectionError,
    MatterHubError,
)
from custom_components.matter_bridge.const import CONF_CONNECTION, CONNECTION_APP
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .conftest import URL


def test_supervisor_transport_is_gone() -> None:
    """Ingress sessions are not something this integration can create."""
    import custom_components.matter_bridge.api as api

    assert not hasattr(api, "SupervisorTransport")
    assert not hasattr(api, "async_find_apps")
    assert not hasattr(api, "supervisor_available")


def test_create_transport_rejects_app_entries(hass: HomeAssistant) -> None:
    from custom_components.matter_bridge import create_transport

    with pytest.raises(MatterHubError, match="removed app connection"):
        create_transport(hass, {CONF_CONNECTION: CONNECTION_APP, "app_slug": "hamh"})


async def test_direct_unhealthy_503_returns_body(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, health
) -> None:
    health["status"] = "unhealthy"
    aioclient_mock.get(
        f"{URL}/api/health", json=health, status=HTTPStatus.SERVICE_UNAVAILABLE
    )
    client = MatterHubClient(DirectTransport(async_get_clientsession(hass), URL))
    assert (await client.async_get_health())["status"] == "unhealthy"


async def test_direct_basic_auth(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(
        f"{URL}/api/health",
        status=HTTPStatus.UNAUTHORIZED,
        headers={"WWW-Authenticate": 'Basic realm="Home Assistant Matter Hub"'},
    )
    client = MatterHubClient(
        DirectTransport(async_get_clientsession(hass), URL, "admin", "wrong")
    )
    with pytest.raises(MatterHubAuthError):
        await client.async_get_health()
    # admin:wrong
    assert aioclient_mock.mock_calls[0][3]["Authorization"] == "Basic YWRtaW46d3Jvbmc="


async def test_direct_command_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(
        f"{URL}/api/matter/bridges/b1/actions/open-commissioning-window",
        status=HTTPStatus.BAD_REQUEST,
        json={"error": "Bridge is not running"},
    )
    client = MatterHubClient(DirectTransport(async_get_clientsession(hass), URL))
    with pytest.raises(MatterHubCommandError, match="not running"):
        await client.async_bridge_action("b1", "open-commissioning-window")


async def test_direct_unreachable(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{URL}/api/health", exc=TimeoutError)
    client = MatterHubClient(DirectTransport(async_get_clientsession(hass), URL))
    with pytest.raises(MatterHubConnectionError):
        await client.async_get_health()


async def test_unexpected_body(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{URL}/api/health", text="nope")
    client = MatterHubClient(DirectTransport(async_get_clientsession(hass), URL))
    with pytest.raises(MatterHubConnectionError, match="Unexpected health"):
        await client.async_get_health()
