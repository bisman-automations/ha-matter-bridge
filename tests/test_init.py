"""Setup, entity and action tests."""

from __future__ import annotations

from datetime import timedelta
import logging

import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.matter_bridge.const import (
    CONF_CONNECTION,
    CONNECTION_DIRECT,
    DOMAIN,
)
from custom_components.matter_bridge.diagnostics import (
    async_get_config_entry_diagnostics,
)
from homeassistant.components.repairs import repairs_flow_manager
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_PASSWORD,
    CONF_URL,
    CONF_USERNAME,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import (
    device_registry as dr,
    entity_registry as er,
    issue_registry as ir,
)
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util

from .conftest import (
    EXAMPLE_MANUAL_CODE,
    EXAMPLE_PASSCODE,
    EXAMPLE_QR_CODE,
    URL,
    app_entry,
    direct_entry,
    mock_direct,
)

SECRETS = (EXAMPLE_MANUAL_CODE, EXAMPLE_QR_CODE, str(EXAMPLE_PASSCODE))


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


async def _poll(hass: HomeAssistant) -> None:
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=31))
    await hass.async_block_till_done()


def _integration_logs(caplog: pytest.LogCaptureFixture) -> str:
    return "\n".join(
        f"{record.getMessage()}\n{record.exc_text or ''}"
        for record in caplog.records
        if record.name.startswith("custom_components.matter_bridge")
    )


def _assert_secrets_absent(blob: str) -> None:
    for secret in SECRETS:
        assert secret not in blob


async def test_entities(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    health,
    bridges,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger="custom_components.matter_bridge")
    seen: list[str] = []
    hass.bus.async_listen("state_changed", lambda event: seen.append(str(event.data)))
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
    assert hass.states.get("binary_sensor.living_room_commissioned").state == STATE_ON
    assert hass.states.get("switch.living_room_running").state == STATE_ON

    assert hass.states.get("switch.garage_running").state == STATE_OFF
    assert hass.states.get("binary_sensor.garage_commissioned").state == "unknown"
    # The pairing code is not an entity, and no attribute carries the QR payload.
    assert hass.states.get("sensor.living_room_pairing_code") is None
    assert hass.states.get("sensor.garage_pairing_code") is None
    for state in hass.states.async_all():
        assert "qr_code" not in state.attributes
        _assert_secrets_absent(f"{state.state} {state.attributes}")
    for event_data in seen:
        _assert_secrets_absent(event_data)
    _assert_secrets_absent(_integration_logs(caplog))

    bridge = _device(hass, entry, ("matter_bridge", f"{entry.entry_id}_b1"))
    hub = _device(hass, entry, ("matter_bridge", entry.entry_id))
    assert bridge.via_device_id == hub.id
    assert hub.sw_version == "2.0.59"
    assert hub.configuration_url == URL
    assert bridge.configuration_url == URL
    # Matter Hub and its bridges are software, so they're services.
    assert hub.entry_type is dr.DeviceEntryType.SERVICE
    assert bridge.entry_type is dr.DeviceEntryType.SERVICE


async def test_button_and_switch_actions(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
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
    health,
    bridges,
) -> None:
    await _setup_direct(hass, aioclient_mock, health, bridges)
    aioclient_mock.post(
        f"{URL}/api/matter/bridges/b2/actions/open-commissioning-window",
        status=400,
        json={"error": "Bridge is not running"},
    )
    with pytest.raises(HomeAssistantError, match="not running"):
        await hass.services.async_call(
            "button",
            "press",
            {ATTR_ENTITY_ID: "button.garage_open_pairing_window"},
            blocking=True,
        )


async def test_bridges_added_removed_and_readded(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    health,
    bridges,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Removing a bridge drops its device; creating it again restores entities."""
    caplog.set_level(logging.ERROR, logger="homeassistant.helpers.entity_platform")
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
    assert hass.states.get("switch.garage_running") is None

    # The known set shrank with the device, so the same bridge id gets entities.
    aioclient_mock.clear_requests()
    mock_direct(aioclient_mock, health, bridges)
    await _poll(hass)
    assert _device(hass, entry, b2) is not None
    garage = hass.states.get("switch.garage_running")
    assert garage is not None
    assert garage.state == STATE_OFF
    assert "already exists" not in caplog.text


async def test_restart_keeps_bridges(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    health,
    bridges,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A Matter Hub restart (no bridges, then some) never deletes devices."""
    caplog.set_level(logging.ERROR, logger="homeassistant.helpers.entity_platform")
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
    assert "already exists" not in caplog.text


async def test_failed_update_does_not_prune(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    health,
    bridges,
) -> None:
    """A failed poll neither removes a bridge nor resets its absence streak.

    Listeners run after a failure too, and ``data`` is still the previous
    successful list. Counting that poll would see the bridge and clear the
    streak, so three real absences split by errors would never remove it.
    """
    entry = await _setup_direct(hass, aioclient_mock, health, bridges)
    b2 = ("matter_bridge", f"{entry.entry_id}_b2")

    aioclient_mock.clear_requests()
    mock_direct(aioclient_mock, health, [bridges[0]])
    await _poll(hass)
    assert entry.runtime_data.missing_polls.get("b2") == 1

    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{URL}/api/health", exc=TimeoutError)
    await _poll(hass)
    await _poll(hass)
    assert entry.runtime_data.missing_polls.get("b2") == 1
    assert _device(hass, entry, b2) is not None

    aioclient_mock.clear_requests()
    mock_direct(aioclient_mock, health, [bridges[0]])
    await _poll(hass)
    assert entry.runtime_data.missing_polls.get("b2") == 2
    assert _device(hass, entry, b2) is not None
    await _poll(hass)
    assert _device(hass, entry, b2) is None


async def test_auth_failure_starts_reauth(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(
        f"{URL}/api/health",
        status=401,
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
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(f"{URL}/api/health", exc=TimeoutError)
    entry = direct_entry()
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_diagnostics_redacted(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    health,
    bridges,
) -> None:
    entry = await _setup_direct(hass, aioclient_mock, health, bridges)
    # A QR payload under a name this integration does not know about yet.
    entry.runtime_data.data.bridges["b1"]["note"] = "MT:NOT-A-REAL-PAYLOAD"
    diag = await async_get_config_entry_diagnostics(hass, entry)
    rendered = str(diag)
    assert diag["entry"]["url"] == "**REDACTED**"
    commissioning = diag["data"]["bridges"]["b1"]["commissioning"]
    assert commissioning["manualPairingCode"] == "**REDACTED**"
    assert commissioning["qrPairingCode"] == "**REDACTED**"
    assert commissioning["passcode"] == "**REDACTED**"
    assert commissioning["discriminator"] == "**REDACTED**"
    assert commissioning["fabrics"][0]["label"] == "Apple Home"
    assert commissioning["fabrics"][0]["fabricId"] == "**REDACTED**"
    assert diag["data"]["bridges"]["b1"]["note"] == "**REDACTED**"
    _assert_secrets_absent(rendered)
    assert "MT:NOT-A-REAL-PAYLOAD" not in rendered


async def test_unload(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    health,
    bridges,
) -> None:
    entry = await _setup_direct(hass, aioclient_mock, health, bridges)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert er.async_get(hass).async_get("sensor.living_room_status") is not None


async def test_devices_from_before_1_2_0_become_services(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    health,
    bridges,
) -> None:
    """Devices registered as ordinary devices switch to services on setup."""
    mock_direct(aioclient_mock, health, bridges)
    entry = direct_entry()
    entry.add_to_hass(hass)
    registry = dr.async_get(hass)
    old = registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("matter_bridge", entry.entry_id)},
        name="Matter Hub",
    )
    assert old.entry_type is None
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    hub = _device(hass, entry, ("matter_bridge", entry.entry_id))
    assert hub.id == old.id
    assert hub.entry_type is dr.DeviceEntryType.SERVICE
    bridge = _device(hass, entry, ("matter_bridge", f"{entry.entry_id}_b1"))
    assert bridge.entry_type is dr.DeviceEntryType.SERVICE


async def test_app_entry_is_not_loaded(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A 1.x app entry does not load, and its pairing-code entity is removed."""
    caplog.set_level(logging.DEBUG, logger="custom_components.matter_bridge")
    entry = app_entry()
    entry.add_to_hass(hass)
    ent_reg = er.async_get(hass)
    pairing = ent_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{entry.entry_id}_b1_pairing_code",
        suggested_object_id="living_room_pairing_code",
        config_entry=entry,
    )
    status = ent_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{entry.entry_id}_b1_status",
        suggested_object_id="living_room_status",
        config_entry=entry,
    )
    hass.states.async_set(
        pairing.entity_id,
        EXAMPLE_MANUAL_CODE,
        {"qr_code": EXAMPLE_QR_CODE},
    )

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert entry.error_reason_translation_key == "ingress_removed"
    assert entry.error_reason_translation_placeholders == {"title": entry.title}
    assert ent_reg.async_get(pairing.entity_id) is None
    assert hass.states.get(pairing.entity_id) is None
    assert ent_reg.async_get(status.entity_id) is not None
    issue = ir.async_get(hass).async_get_issue(
        DOMAIN, f"ingress_removed_{entry.entry_id}"
    )
    assert issue is not None
    assert issue.is_fixable
    assert issue.severity is ir.IssueSeverity.ERROR
    assert issue.translation_key == "ingress_removed"
    assert issue.data == {"entry_id": entry.entry_id}
    # Nothing talked to the Supervisor, and the code was not logged.
    assert aioclient_mock.mock_calls == []
    _assert_secrets_absent(_integration_logs(caplog))

    await hass.config_entries.async_remove(entry.entry_id)
    assert (
        ir.async_get(hass).async_get_issue(DOMAIN, f"ingress_removed_{entry.entry_id}")
        is None
    )


async def test_app_entry_repair_converts_to_url(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    health,
    bridges,
) -> None:
    """The repair writes a URL onto the same entry and keeps its devices."""
    assert await async_setup_component(hass, "repairs", {})
    mock_direct(aioclient_mock, health, bridges)
    entry = app_entry(**{CONF_USERNAME: "admin", CONF_PASSWORD: "secret"})
    entry_id = entry.entry_id
    entry.add_to_hass(hass)
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    hub = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("matter_bridge", entry.entry_id)},
        name="Matter Hub",
        configuration_url="homeassistant://hassio/ingress/3fd9e6b0_hamh",
    )
    bridge = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("matter_bridge", f"{entry.entry_id}_b1")},
        name="Living Room",
    )
    status = ent_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{entry.entry_id}_b1_status",
        suggested_object_id="living_room_status",
        config_entry=entry,
        device_id=bridge.id,
    )
    ent_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{entry.entry_id}_b1_pairing_code",
        suggested_object_id="living_room_pairing_code",
        config_entry=entry,
        device_id=bridge.id,
    )

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    issue_id = f"ingress_removed_{entry.entry_id}"

    manager = repairs_flow_manager(hass)
    assert manager is not None
    result = await manager.async_init(
        DOMAIN, context={"issue_id": issue_id}, data={"issue_id": issue_id}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    assert result["description_placeholders"]["title"] == entry.title
    assert (
        "home-assistant-matter-hub" in result["description_placeholders"]["project_url"]
    )

    result = await manager.async_configure(
        result["flow_id"], {CONF_URL: "192.0.2.20:8482"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    assert entry.entry_id == entry_id
    assert entry.state is ConfigEntryState.LOADED
    assert entry.data[CONF_CONNECTION] == CONNECTION_DIRECT
    assert entry.data[CONF_URL] == URL
    assert entry.data[CONF_USERNAME] == "admin"
    assert entry.data[CONF_PASSWORD] == "secret"
    assert "app_slug" not in entry.data
    assert entry.unique_id == "direct_192.0.2.20:8482"
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None

    assert _device(hass, entry, ("matter_bridge", entry.entry_id)).id == hub.id
    assert (
        _device(hass, entry, ("matter_bridge", f"{entry.entry_id}_b1")).id == bridge.id
    )
    kept = ent_reg.async_get(status.entity_id)
    assert kept is not None
    assert kept.unique_id == f"{entry.entry_id}_b1_status"
    assert hass.states.get(status.entity_id).state == "running"
    assert ent_reg.async_get("sensor.living_room_pairing_code") is None
    assert hass.states.get("sensor.living_room_pairing_code") is None
    hub_device = _device(hass, entry, ("matter_bridge", entry.entry_id))
    assert hub_device.configuration_url == URL
    for state in hass.states.async_all():
        _assert_secrets_absent(f"{state.state} {state.attributes}")


async def test_app_entry_repair_cannot_connect(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    assert await async_setup_component(hass, "repairs", {})
    entry = app_entry()
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    issue_id = f"ingress_removed_{entry.entry_id}"
    manager = repairs_flow_manager(hass)
    result = await manager.async_init(
        DOMAIN, context={"issue_id": issue_id}, data={"issue_id": issue_id}
    )
    aioclient_mock.get(f"{URL}/api/health", exc=TimeoutError)
    result = await manager.async_configure(result["flow_id"], {CONF_URL: URL})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert entry.data[CONF_CONNECTION] != CONNECTION_DIRECT
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is not None


async def test_upgrade_removes_pairing_entity_on_url_entry(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    health,
    bridges,
) -> None:
    """A URL entry from 1.x drops the Pairing code entity it already had."""
    mock_direct(aioclient_mock, health, bridges)
    entry = direct_entry()
    entry.add_to_hass(hass)
    ent_reg = er.async_get(hass)
    pairing = ent_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{entry.entry_id}_b1_pairing_code",
        suggested_object_id="living_room_pairing_code",
        config_entry=entry,
        disabled_by=er.RegistryEntryDisabler.USER,
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert ent_reg.async_get(pairing.entity_id) is None
    assert hass.states.get("sensor.living_room_status") is not None
