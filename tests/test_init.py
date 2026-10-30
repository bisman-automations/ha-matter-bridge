"""Setup, entity and action tests."""

from __future__ import annotations

from datetime import timedelta
from http import HTTPStatus

import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.matter_bridge.diagnostics import (
    async_get_config_entry_diagnostics,
)
from homeassistant.auth.models import User
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util

from .conftest import (
    INGRESS,
    URL,
    app_entry,
    direct_entry,
    mock_direct,
    mock_supervisor,
)


def _device(hass, entry, identifier):
    """Find one of the entry's devices by identifier (works on every HA version)."""
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    return next((d for d in devices if identifier in d.identifiers), None)


async def _setup_direct(hass, aioclient_mock, health, bridges):
    mock_direct(aioclient_mock, health, bridges)
    entry = direct_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_entities(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    no_supervisor,
    health,
    bridges,
) -> None:
    entry = await _setup_direct(hass, aioclient_mock, health, bridges)
    assert entry.state is ConfigEntryState.LOADED

    assert hass.states.get("sensor.matter_hub_status").state == "healthy"
    assert hass.states.get("sensor.matter_hub_running_bridges").state == "1"
    assert (
        hass.states.get("binary_sensor.matter_hub_home_assistant_connection").state
        == STATE_ON
    )

    assert hass.states.get("sensor.living_room_status").state == "running"
    assert hass.states.get("sensor.living_room_devices").state == "12"
    controllers = hass.states.get("sensor.living_room_controllers")
    assert controllers.state == "1"
    assert controllers.attributes["controllers"] == ["Apple Home"]
    assert hass.states.get("sensor.living_room_failed_entities").state == "1"
    assert hass.states.get("sensor.living_room_pairing_code").state == "34970112332"
    assert hass.states.get("binary_sensor.living_room_commissioned").state == STATE_ON
    assert hass.states.get("switch.living_room_running").state == STATE_ON

    assert hass.states.get("switch.garage_running").state == STATE_OFF
    assert hass.states.get("binary_sensor.garage_commissioned").state == "unknown"
    assert hass.states.get("sensor.garage_pairing_code").state == "unknown"

    bridge = _device(hass, entry, ("matter_bridge", f"{entry.entry_id}_b1"))
    hub = _device(hass, entry, ("matter_bridge", entry.entry_id))
    assert bridge.via_device_id == hub.id
    assert hub.sw_version == "2.0.59"


async def test_button_and_switch_actions(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    no_supervisor,
    health,
    bridges,
) -> None:
    await _setup_direct(hass, aioclient_mock, health, bridges)
    for action in ("restart", "force-sync", "stop", "start"):
        aioclient_mock.post(f"{URL}/api/matter/bridges/b1/actions/{action}", json={})
    aioclient_mock.post(f"{URL}/api/matter/bridges/actions/restart-all", json={})

    await hass.services.async_call(
        "button", "press", {ATTR_ENTITY_ID: "button.living_room_restart"}, blocking=True
    )
    await hass.services.async_call(
        "button",
        "press",
        {ATTR_ENTITY_ID: "button.living_room_force_sync"},
        blocking=True,
    )
    await hass.services.async_call(
        "switch",
        "turn_off",
        {ATTR_ENTITY_ID: "switch.living_room_running"},
        blocking=True,
    )
    await hass.services.async_call(
        "button",
        "press",
        {ATTR_ENTITY_ID: "button.matter_hub_restart_all_bridges"},
        blocking=True,
    )
    posted = [str(u) for m, u, *_ in aioclient_mock.mock_calls if m == "POST"]
    assert posted == [
        f"{URL}/api/matter/bridges/b1/actions/restart",
        f"{URL}/api/matter/bridges/b1/actions/force-sync",
        f"{URL}/api/matter/bridges/b1/actions/stop",
        f"{URL}/api/matter/bridges/actions/restart-all",
    ]


async def test_action_error(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    no_supervisor,
    health,
    bridges,
) -> None:
    await _setup_direct(hass, aioclient_mock, health, bridges)
    aioclient_mock.post(
        f"{URL}/api/matter/bridges/b2/actions/open-commissioning-window",
        status=HTTPStatus.BAD_REQUEST,
        json={"error": "Bridge is not running"},
    )
    with pytest.raises(HomeAssistantError, match="not running"):
        await hass.services.async_call(
            "button",
            "press",
            {ATTR_ENTITY_ID: "button.garage_open_pairing_window"},
            blocking=True,
        )


async def test_bridges_added_and_removed(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    no_supervisor,
    health,
    bridges,
) -> None:
    entry = await _setup_direct(hass, aioclient_mock, health, bridges)

    new = {**bridges[1], "id": "b3", "name": "Office"}
    aioclient_mock.clear_requests()
    mock_direct(aioclient_mock, health, [bridges[0], new])
    await _poll(hass)

    assert hass.states.get("switch.office_running") is not None
    assert _device(hass, entry, ("matter_bridge", f"{entry.entry_id}_b3")) is not None
    # A bridge is only removed once it has been gone for three polls in a row.
    b2 = ("matter_bridge", f"{entry.entry_id}_b2")
    await _poll(hass)
    assert _device(hass, entry, b2) is not None
    await _poll(hass)
    assert _device(hass, entry, b2) is None


async def _poll(hass: HomeAssistant) -> None:
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=31))
    await hass.async_block_till_done()


async def test_restart_keeps_bridges(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    no_supervisor,
    health,
    bridges,
) -> None:
    """A Matter Hub restart (no bridges, then some) never deletes devices."""
    entry = await _setup_direct(hass, aioclient_mock, health, bridges)
    b1 = ("matter_bridge", f"{entry.entry_id}_b1")
    b2 = ("matter_bridge", f"{entry.entry_id}_b2")

    aioclient_mock.clear_requests()
    mock_direct(aioclient_mock, health, [])
    for _ in range(5):
        await _poll(hass)
    assert _device(hass, entry, b1) is not None
    assert _device(hass, entry, b2) is not None

    # Starting up: only the first bridge is listed for two polls, then both.
    aioclient_mock.clear_requests()
    mock_direct(aioclient_mock, health, [bridges[0]])
    await _poll(hass)
    await _poll(hass)
    aioclient_mock.clear_requests()
    mock_direct(aioclient_mock, health, bridges)
    await _poll(hass)
    aioclient_mock.clear_requests()
    mock_direct(aioclient_mock, health, [bridges[0]])
    await _poll(hass)
    await _poll(hass)
    assert _device(hass, entry, b2) is not None


async def test_auth_failure_starts_reauth(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, no_supervisor
) -> None:
    aioclient_mock.get(
        f"{URL}/api/health",
        status=HTTPStatus.UNAUTHORIZED,
        headers={"WWW-Authenticate": "Basic realm=x"},
    )
    entry = direct_entry()
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flows] == ["reauth"]


async def test_unreachable_retries(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, no_supervisor
) -> None:
    aioclient_mock.get(f"{URL}/api/health", exc=TimeoutError)
    entry = direct_entry()
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_app_entry_setup(
    hass: HomeAssistant,
    hass_owner_user: User,
    aioclient_mock: AiohttpClientMocker,
    supervisor_env,
    health,
    bridges,
) -> None:
    mock_supervisor(aioclient_mock, health, bridges)
    entry = app_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.living_room_status").state == "running"
    assert any(
        str(u) == f"{INGRESS}/api/matter/bridges"
        for _, u, *_ in aioclient_mock.mock_calls
    )
    hub = _device(hass, entry, ("matter_bridge", entry.entry_id))
    assert hub.configuration_url == "homeassistant://hassio/ingress/3fd9e6b0_hamh"


async def test_diagnostics_redacted(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    no_supervisor,
    health,
    bridges,
) -> None:
    entry = await _setup_direct(hass, aioclient_mock, health, bridges)
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["entry"]["url"] == "**REDACTED**"
    commissioning = diag["data"]["bridges"]["b1"]["commissioning"]
    assert commissioning["manualPairingCode"] == "**REDACTED**"
    assert commissioning["passcode"] == "**REDACTED**"
    assert commissioning["fabrics"][0]["label"] == "Apple Home"


async def test_unload(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    no_supervisor,
    health,
    bridges,
) -> None:
    entry = await _setup_direct(hass, aioclient_mock, health, bridges)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert er.async_get(hass).async_get("sensor.living_room_status") is not None


async def test_app_unavailable_repair(
    hass: HomeAssistant,
    hass_owner_user: User,
    aioclient_mock: AiohttpClientMocker,
    supervisor_env,
    health,
    bridges,
) -> None:
    """A stopped app raises a repair, which goes once Matter Hub answers."""
    from homeassistant.helpers import issue_registry as ir

    mock_supervisor(aioclient_mock, health, bridges)
    entry = app_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    issue_id = f"app_unavailable_{entry.entry_id}"
    issues = ir.async_get(hass)
    assert issues.async_get_issue("matter_bridge", issue_id) is None

    coordinator = entry.runtime_data
    coordinator.client.transport._ingress_session = None
    aioclient_mock.clear_requests()
    mock_supervisor(aioclient_mock, health, bridges, state="stopped")
    await _poll(hass)
    issue = issues.async_get_issue("matter_bridge", issue_id)
    assert issue is not None
    assert issue.translation_key == "app_unavailable"
    assert hass.states.get("sensor.living_room_status").state == "unavailable"

    aioclient_mock.clear_requests()
    mock_supervisor(aioclient_mock, health, bridges)
    await _poll(hass)
    assert issues.async_get_issue("matter_bridge", issue_id) is None

    await hass.config_entries.async_remove(entry.entry_id)
