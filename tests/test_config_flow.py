"""Config flow tests."""

from __future__ import annotations

from http import HTTPStatus
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.matter_bridge.const import (
    CONF_APP_SLUG,
    CONF_CONNECTION,
    CONNECTION_APP,
    CONNECTION_DIRECT,
    DOMAIN,
)
from homeassistant import config_entries
from homeassistant.auth.models import User
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .conftest import SLUG, URL, direct_entry, mock_direct, mock_supervisor


@pytest.fixture(autouse=True)
def no_setup():
    with patch(
        "custom_components.matter_bridge.async_setup_entry",
        AsyncMock(return_value=True),
    ):
        yield


async def test_direct_flow(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    no_supervisor,
    health,
    bridges,
) -> None:
    mock_direct(aioclient_mock, health, bridges)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "direct"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: "192.0.2.20:8482/"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Matter Hub (192.0.2.20)"
    assert result["data"] == {CONF_CONNECTION: CONNECTION_DIRECT, CONF_URL: URL}
    assert result["result"].unique_id == "direct_192.0.2.20:8482"


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
    ],
)
async def test_direct_flow_errors(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    no_supervisor,
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


async def test_direct_already_configured(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, no_supervisor
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


async def test_app_flow(
    hass: HomeAssistant,
    hass_owner_user: User,
    aioclient_mock: AiohttpClientMocker,
    supervisor_env,
    health,
    bridges,
) -> None:
    mock_supervisor(aioclient_mock, health, bridges)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["app", "direct"]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "app"}
    )
    assert result["step_id"] == "app"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_APP_SLUG: SLUG}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Home-Assistant-Matter-Hub"
    assert result["data"] == {CONF_CONNECTION: CONNECTION_APP, CONF_APP_SLUG: SLUG}
    assert result["result"].unique_id == f"app_{SLUG}"


async def test_app_flow_not_running(
    hass: HomeAssistant,
    hass_owner_user: User,
    aioclient_mock: AiohttpClientMocker,
    supervisor_env,
    health,
    bridges,
) -> None:
    mock_supervisor(aioclient_mock, health, bridges, state="stopped")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "app"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_APP_SLUG: SLUG}
    )
    assert result["errors"] == {"base": "app_not_running"}


async def test_supervisor_without_app_goes_direct(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, supervisor_env
) -> None:
    aioclient_mock.get(
        "http://supervisor/addons", json={"result": "ok", "data": {"addons": []}}
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["step_id"] == "direct"


async def test_reauth(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    no_supervisor,
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
    no_supervisor,
    health,
    bridges,
) -> None:
    entry = direct_entry()
    entry.add_to_hass(hass)
    mock_direct(aioclient_mock, health, bridges)
    result = await entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"
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
