"""Config flow tests."""

from __future__ import annotations

from http import HTTPStatus
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.matter_bridge.config_flow import MatterBridgeConfigFlow
from custom_components.matter_bridge.const import (
    CONF_CONNECTION,
    CONNECTION_DIRECT,
    DOMAIN,
)
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .conftest import SLUG, URL, app_entry, direct_entry, mock_direct


@pytest.fixture(autouse=True)
def no_setup():
    with patch(
        "custom_components.matter_bridge.async_setup_entry",
        AsyncMock(return_value=True),
    ):
        yield


def test_no_hassio_discovery_step() -> None:
    """The Matter Hub app does not publish Supervisor discovery.

    ConfigFlow has a generic hassio step. This integration does not define
    its own, because the add-on never sends discovery.
    """
    assert "async_step_hassio" not in MatterBridgeConfigFlow.__dict__
    assert "async_step_app" not in MatterBridgeConfigFlow.__dict__


async def test_user_flow(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    health,
    bridges,
) -> None:
    mock_direct(aioclient_mock, health, bridges)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert (
        result["description_placeholders"]["project_url"]
        == "https://github.com/RiDDiX/home-assistant-matter-hub"
    )
    assert (
        result["description_placeholders"]["example_url"] == "http://192.168.1.20:8482"
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: "192.0.2.20:8482/"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Matter Hub (192.0.2.20)"
    assert result["data"] == {CONF_CONNECTION: CONNECTION_DIRECT, CONF_URL: URL}
    assert result["result"].unique_id == "direct_192.0.2.20:8482"


async def test_user_flow_ignores_supervisor_token(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, monkeypatch
) -> None:
    """A Supervisor token does not start an app lookup or an ingress session."""
    monkeypatch.setenv("SUPERVISOR_TOKEN", "core-token")
    monkeypatch.setenv("SUPERVISOR", "supervisor")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["step_id"] == "user"
    assert aioclient_mock.mock_calls == []


@pytest.mark.parametrize(
    ("mock_kwargs", "error"),
    [
        ({"exc": TimeoutError}, "cannot_connect"),
        (
            {
                "status": HTTPStatus.UNAUTHORIZED,
                "headers": {"WWW-Authenticate": "Basic realm=x"},
            },
            "invalid_auth",
        ),
        # The Matter Hub app only lets the Supervisor in: a password won't help.
        ({"status": HTTPStatus.FORBIDDEN}, "forbidden"),
    ],
)
async def test_user_flow_errors(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    health,
    bridges,
    mock_kwargs,
    error,
) -> None:
    aioclient_mock.get(f"{URL}/api/health", **mock_kwargs)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: URL}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    aioclient_mock.clear_requests()
    mock_direct(aioclient_mock, health, bridges)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: URL, CONF_USERNAME: "admin", CONF_PASSWORD: "pw"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_USERNAME] == "admin"


async def test_user_already_configured(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    direct_entry().add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: URL}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    health,
    bridges,
) -> None:
    entry = direct_entry()
    entry.add_to_hass(hass)
    mock_direct(aioclient_mock, health, bridges)
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_USERNAME: "admin", CONF_PASSWORD: "secret"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_PASSWORD] == "secret"
    # Reauth reloads the entry. Unload it so its poll timer doesn't outlive the
    # test (older Home Assistant versions finish that reload after the flow).
    await hass.async_block_till_done()
    await hass.config_entries.async_unload(entry.entry_id)


async def test_reconfigure(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    health,
    bridges,
) -> None:
    entry = direct_entry()
    entry.add_to_hass(hass)
    mock_direct(aioclient_mock, health, bridges)
    result = await entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"
    assert "clear" in result["description_placeholders"]["credential_hint"]
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: URL, CONF_USERNAME: "admin", CONF_PASSWORD: "pw"}
    )
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_USERNAME] == "admin"

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: "http://192.0.2.99:8482"}
    )
    assert result["reason"] == "different_hub"


async def test_reconfigure_converts_app_entry(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    health,
    bridges,
) -> None:
    """Reconfigure turns a 1.x app entry into a URL entry, same entry id."""
    entry = app_entry(username="admin", password="secret")
    entry_id = entry.entry_id
    entry.add_to_hass(hass)
    mock_direct(aioclient_mock, health, bridges)
    result = await entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"
    assert "keep" in result["description_placeholders"]["credential_hint"]
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: URL}
    )
    assert result["reason"] == "reconfigure_successful"
    assert entry.entry_id == entry_id
    assert entry.unique_id == "direct_192.0.2.20:8482"
    assert entry.data[CONF_CONNECTION] == CONNECTION_DIRECT
    assert entry.data[CONF_URL] == URL
    assert entry.data[CONF_USERNAME] == "admin"
    assert entry.data[CONF_PASSWORD] == "secret"
    assert "app_slug" not in entry.data
    assert entry.title == "Matter Hub (192.0.2.20)"
    assert SLUG not in entry.unique_id
