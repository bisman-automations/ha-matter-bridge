"""Tests for the Matter Hub transports."""

from __future__ import annotations

from http import HTTPStatus

import pytest

from homeassistant.auth.models import User
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.matter_bridge.api import (
    DirectTransport,
    MatterHubAppError,
    MatterHubAuthError,
    MatterHubClient,
    MatterHubCommandError,
    MatterHubConnectionError,
    SupervisorTransport,
    async_find_apps,
    is_matter_hub_app,
)

from .conftest import INGRESS, SLUG, SUPERVISOR, URL, mock_supervisor


@pytest.mark.parametrize(
    ("app", "expected"),
    [
        ({"slug": "3fd9e6b0_hamh"}, True),
        ({"slug": "3fd9e6b0_hamh-alpha"}, True),
        ({"slug": "local_hamh_testing"}, True),
        ({"slug": "abcd_other", "url": "https://github.com/riddix/home-assistant-matter-hub"}, True),
        ({"slug": "core_matter_server"}, False),
        ({"slug": "abcd_hamhx"}, False),
    ],
)
def test_is_matter_hub_app(app, expected) -> None:
    assert is_matter_hub_app(app) is expected


async def test_find_apps(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, supervisor_env, health, bridges
) -> None:
    mock_supervisor(aioclient_mock, health, bridges)
    apps = await async_find_apps(hass)
    assert [a.slug for a in apps] == [SLUG]
    _, _, _, headers = aioclient_mock.mock_calls[0]
    assert headers["Authorization"] == "Bearer core-token"


async def test_supervisor_ingress_request(
    hass: HomeAssistant,
    hass_owner_user: User,
    aioclient_mock: AiohttpClientMocker,
    supervisor_env,
    health,
    bridges,
) -> None:
    mock_supervisor(aioclient_mock, health, bridges)
    transport = SupervisorTransport(hass, async_get_clientsession(hass), SLUG)
    client = MatterHubClient(transport)

    assert (await client.async_get_health())["version"] == "2.0.59"
    assert len(await client.async_get_bridges()) == 2

    calls = [(m, str(u)) for m, u, *_ in aioclient_mock.mock_calls]
    assert calls[:3] == [
        ("GET", f"{SUPERVISOR}/addons/{SLUG}/info"),
        ("POST", f"{SUPERVISOR}/ingress/session"),
        ("GET", f"{INGRESS}/api/health"),
    ]
    # The ingress session is created for the owner and reused.
    assert aioclient_mock.mock_calls[1][2] == {"user_id": hass_owner_user.id}
    assert calls[3] == ("GET", f"{INGRESS}/api/matter/bridges")
    ingress_headers = aioclient_mock.mock_calls[2][3]
    assert ingress_headers["Cookie"] == "ingress_session=sess1"
    assert "Authorization" not in ingress_headers


async def test_supervisor_renews_expired_session(
    hass: HomeAssistant,
    hass_owner_user: User,
    aioclient_mock: AiohttpClientMocker,
    supervisor_env,
    health,
    bridges,
) -> None:
    mock_supervisor(aioclient_mock, health, bridges)
    transport = SupervisorTransport(hass, async_get_clientsession(hass), SLUG)
    client = MatterHubClient(transport)
    await client.async_get_health()

    aioclient_mock.clear_requests()
    mock_supervisor(aioclient_mock, health, bridges)
    aioclient_mock._mocks = [  # noqa: SLF001 - make the ingress call answer 401
        m for m in aioclient_mock._mocks if not str(m._url).endswith("/api/health")  # noqa: SLF001
    ]
    aioclient_mock.get(f"{INGRESS}/api/health", status=HTTPStatus.UNAUTHORIZED)
    with pytest.raises(MatterHubAppError):
        # Still 401 after renewing: reported as an ingress problem, not bad credentials.
        await client.async_get_health()
    methods = [(m, str(u)) for m, u, *_ in aioclient_mock.mock_calls]
    assert methods == [
        ("GET", f"{INGRESS}/api/health"),
        ("GET", f"{SUPERVISOR}/addons/{SLUG}/info"),
        ("POST", f"{SUPERVISOR}/ingress/session"),
        ("GET", f"{INGRESS}/api/health"),
    ]


async def test_supervisor_app_stopped(
    hass: HomeAssistant,
    hass_owner_user: User,
    aioclient_mock: AiohttpClientMocker,
    supervisor_env,
    health,
    bridges,
) -> None:
    mock_supervisor(aioclient_mock, health, bridges, state="stopped")
    client = MatterHubClient(SupervisorTransport(hass, async_get_clientsession(hass), SLUG))
    with pytest.raises(MatterHubAppError, match="stopped"):
        await client.async_get_health()


async def test_direct_unhealthy_503_returns_body(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, health
) -> None:
    health["status"] = "unhealthy"
    aioclient_mock.get(f"{URL}/api/health", json=health, status=HTTPStatus.SERVICE_UNAVAILABLE)
    client = MatterHubClient(DirectTransport(async_get_clientsession(hass), URL))
    assert (await client.async_get_health())["status"] == "unhealthy"


async def test_direct_basic_auth(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
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


async def test_direct_command_error(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.post(
        f"{URL}/api/matter/bridges/b1/actions/open-commissioning-window",
        status=HTTPStatus.BAD_REQUEST,
        json={"error": "Bridge is not running"},
    )
    client = MatterHubClient(DirectTransport(async_get_clientsession(hass), URL))
    with pytest.raises(MatterHubCommandError, match="not running"):
        await client.async_bridge_action("b1", "open-commissioning-window")


async def test_direct_unreachable(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(f"{URL}/api/health", exc=TimeoutError)
    client = MatterHubClient(DirectTransport(async_get_clientsession(hass), URL))
    with pytest.raises(MatterHubConnectionError):
        await client.async_get_health()
