"""The Matter Hub app on this host: a blank URL uses it."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import AsyncMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.matter_bridge.app import find_apps
from custom_components.matter_bridge.const import (
    CONF_ADDON,
    CONF_CONNECTION,
    CONNECTION_DIRECT,
    DOMAIN,
)
from homeassistant import config_entries
from homeassistant.components.repairs import repairs_flow_manager
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.setup import async_setup_component

from .conftest import SLUG, app_entry, direct_entry, mock_direct

PORT = 62345
APP_URL = f"http://127.0.0.1:{PORT}"
ALPHA = "3fd9e6b0_hamh-alpha"


def _info(name: str, port: int | None, state: str = "started") -> dict[str, Any]:
    return {"name": name, "ingress_port": port, "state": state}


@contextmanager
def apps(infos: dict[str, dict[str, Any] | None], *, hassio: bool = True) -> Iterator:
    with (
        patch("custom_components.matter_bridge.app.is_hassio", return_value=hassio),
        patch("homeassistant.components.hassio.get_addons_info", return_value=infos),
    ):
        yield


def mock_app(aioclient_mock: AiohttpClientMocker, health, bridges, url=APP_URL):
    aioclient_mock.get(f"{url}/api/health", json=health)
    aioclient_mock.get(f"{url}/api/matter/bridges", json=bridges)


def test_find_apps(hass: HomeAssistant) -> None:
    infos = {
        SLUG: _info("Home Assistant Matter Hub", PORT, "stopped"),
        ALPHA: _info("Home Assistant Matter Hub (Alpha)", 62346),
        "core_mosquitto": _info("Mosquitto broker", 1883),
        "3fd9e6b0_hamh-testing": _info("No port", None),
        "a0d7b954_other": None,
    }
    with apps(infos):
        found = find_apps(hass)
    # Started first; other apps and ones without a port are left out.
    assert [app.slug for app in found] == [ALPHA, SLUG]
    assert found[1].url == APP_URL
    with apps(infos, hassio=False):
        assert find_apps(hass) == []
    with (
        patch("custom_components.matter_bridge.app.is_hassio", return_value=True),
        patch(
            "homeassistant.components.hassio.get_addons_info",
            side_effect=RuntimeError,
        ),
    ):
        assert find_apps(hass) == []


async def _user_flow(hass: HomeAssistant, user_input: dict[str, Any]) -> Any:
    with patch(
        "custom_components.matter_bridge.async_setup_entry",
        AsyncMock(return_value=True),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        return await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input
        )


async def test_blank_url_uses_the_app(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, health, bridges
) -> None:
    mock_app(aioclient_mock, health, bridges)
    with apps({SLUG: _info("Home Assistant Matter Hub", PORT)}):
        result = await _user_flow(hass, {CONF_PASSWORD: "local-secret"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Home Assistant Matter Hub"
    assert result["data"] == {
        CONF_CONNECTION: CONNECTION_DIRECT,
        CONF_URL: APP_URL,
        CONF_ADDON: SLUG,
        CONF_USERNAME: "hamh",
        CONF_PASSWORD: "local-secret",
    }
    assert result["result"].unique_id == f"app_{SLUG}"
    request = aioclient_mock.mock_calls[0]
    assert str(request[1]) == f"{APP_URL}/api/health"


async def test_blank_url_without_app(hass: HomeAssistant) -> None:
    with apps({}):
        result = await _user_flow(hass, {CONF_PASSWORD: "x"})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_URL: "no_app"}


async def test_typed_url_ignores_the_app(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, health, bridges
) -> None:
    mock_direct(aioclient_mock, health, bridges)
    with apps({SLUG: _info("Home Assistant Matter Hub", PORT)}):
        result = await _user_flow(hass, {CONF_URL: "192.0.2.20:8482"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert CONF_ADDON not in result["data"]
    assert CONF_USERNAME not in result["data"]


async def test_choose_between_apps(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, health, bridges
) -> None:
    mock_app(aioclient_mock, health, bridges)
    infos = {
        SLUG: _info("Home Assistant Matter Hub", PORT),
        ALPHA: _info("Home Assistant Matter Hub (Alpha)", 62346),
    }
    with apps(infos):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert "app" in result["data_schema"].schema
        with patch(
            "custom_components.matter_bridge.async_setup_entry",
            AsyncMock(return_value=True),
        ):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], {"app": SLUG, CONF_PASSWORD: "p"}
            )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_ADDON] == SLUG
    assert result["data"][CONF_URL] == APP_URL


async def test_one_app_has_no_choice(hass: HomeAssistant) -> None:
    with apps({SLUG: _info("Home Assistant Matter Hub", PORT)}):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
    assert "app" not in result["data_schema"].schema


async def test_setup_follows_a_new_port(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, health, bridges
) -> None:
    new_url = "http://127.0.0.1:62999"
    mock_app(aioclient_mock, health, bridges, url=new_url)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Home Assistant Matter Hub",
        unique_id=f"app_{SLUG}",
        data={
            CONF_CONNECTION: CONNECTION_DIRECT,
            CONF_URL: APP_URL,
            CONF_ADDON: SLUG,
            CONF_USERNAME: "hamh",
            CONF_PASSWORD: "p",
        },
    )
    entry.add_to_hass(hass)
    with apps({SLUG: _info("Home Assistant Matter Hub", 62999)}):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert entry.data[CONF_URL] == new_url


async def test_setup_keeps_url_when_app_not_found(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, health, bridges
) -> None:
    mock_app(aioclient_mock, health, bridges)
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=f"app_{SLUG}",
        data={CONF_CONNECTION: CONNECTION_DIRECT, CONF_URL: APP_URL, CONF_ADDON: SLUG},
    )
    entry.add_to_hass(hass)
    with apps({}):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert entry.data[CONF_URL] == APP_URL


async def test_reconfigure_url_entry_to_app(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, health, bridges
) -> None:
    mock_app(aioclient_mock, health, bridges)
    entry = direct_entry()
    entry.add_to_hass(hass)
    with (
        apps({SLUG: _info("Home Assistant Matter Hub", PORT)}),
        patch(
            "custom_components.matter_bridge.async_setup_entry",
            AsyncMock(return_value=True),
        ),
    ):
        result = await entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_URL: "", CONF_PASSWORD: "p"}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_URL] == APP_URL
    assert entry.data[CONF_ADDON] == SLUG
    assert entry.unique_id == f"app_{SLUG}"


async def test_repair_with_blank_url_uses_the_same_app(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, health, bridges
) -> None:
    """A 1.x app entry is repaired onto the app it was set up with."""
    assert await async_setup_component(hass, "repairs", {})
    mock_app(aioclient_mock, health, bridges)
    entry = app_entry()
    entry.add_to_hass(hass)
    infos = {
        ALPHA: _info("Home Assistant Matter Hub (Alpha)", 62346),
        SLUG: _info("Home Assistant Matter Hub", PORT, "stopped"),
    }
    with apps(infos):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        issue_id = f"ingress_removed_{entry.entry_id}"
        manager = repairs_flow_manager(hass)
        assert manager is not None
        result = await manager.async_init(
            DOMAIN, context={"issue_id": issue_id}, data={"issue_id": issue_id}
        )
        assert result["step_id"] == "init"
        result = await manager.async_configure(result["flow_id"], {CONF_PASSWORD: "p"})
        assert result["type"] is FlowResultType.CREATE_ENTRY
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert entry.data[CONF_URL] == APP_URL
    assert entry.data[CONF_ADDON] == SLUG
    assert entry.data[CONF_USERNAME] == "hamh"
    assert entry.unique_id == f"app_{SLUG}"
