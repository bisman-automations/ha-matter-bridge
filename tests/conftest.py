"""Fixtures for Matter Bridge tests."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from homeassistant.const import CONF_URL

from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.matter_bridge.const import (
    CONF_APP_SLUG,
    CONF_CONNECTION,
    CONNECTION_APP,
    CONNECTION_DIRECT,
    DOMAIN,
)

URL = "http://192.0.2.20:8482"
SUPERVISOR = "http://supervisor"
SLUG = "3fd9e6b0_hamh"
INGRESS_TOKEN = "abc123TOKEN"
INGRESS = f"{SUPERVISOR}/ingress/{INGRESS_TOKEN}"

HEALTH: dict[str, Any] = {
    "status": "healthy",
    "version": "2.0.59",
    "uptime": 3600,
    "timestamp": "2026-10-23T12:00:00.000Z",
    "services": {
        "homeAssistant": {"connected": True},
        "bridges": {"total": 2, "running": 1, "stopped": 1, "failed": 0},
    },
}

BRIDGES: list[dict[str, Any]] = [
    {
        "id": "b1",
        "name": "Living Room",
        "port": 5540,
        "status": "running",
        "deviceCount": 12,
        "basicInformation": {
            "vendorId": 65521,
            "vendorName": "riddix",
            "productId": 32768,
            "productName": "MatterHub",
            "productLabel": "Home Assistant Matter Hub",
            "hardwareVersion": 1,
            "softwareVersion": 1,
            "softwareVersionString": "2.0.59",
        },
        "commissioning": {
            "isCommissioned": True,
            "passcode": 20202021,
            "discriminator": 3840,
            "manualPairingCode": "34970112332",
            "qrPairingCode": "MT:Y.K9042C00KA0648G00",
            "fabrics": [
                {
                    "fabricIndex": 1,
                    "fabricId": 1,
                    "nodeId": 9,
                    "rootNodeId": 1,
                    "rootVendorId": 4937,
                    "label": "Apple Home",
                }
            ],
        },
        "failedEntities": [{"entityId": "light.broken", "reason": "unsupported"}],
    },
    {
        "id": "b2",
        "name": "Garage",
        "port": 5541,
        "status": "stopped",
        "deviceCount": 0,
        "basicInformation": {"vendorName": "riddix", "productName": "MatterHub"},
        "commissioning": None,
    },
]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations."""
    return


@pytest.fixture
def health() -> dict[str, Any]:
    return copy.deepcopy(HEALTH)


@pytest.fixture
def bridges() -> list[dict[str, Any]]:
    return copy.deepcopy(BRIDGES)


@pytest.fixture
def supervisor_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPERVISOR", "supervisor")
    monkeypatch.setenv("SUPERVISOR_TOKEN", "core-token")


@pytest.fixture
def no_supervisor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)


def mock_direct(aioclient_mock: AiohttpClientMocker, health, bridges) -> None:
    aioclient_mock.get(f"{URL}/api/health", json=health)
    aioclient_mock.get(f"{URL}/api/matter/bridges", json=bridges)


def mock_supervisor(
    aioclient_mock: AiohttpClientMocker, health, bridges, *, state: str = "started"
) -> None:
    aioclient_mock.get(
        f"{SUPERVISOR}/addons",
        json={
            "result": "ok",
            "data": {
                "addons": [
                    {"slug": "core_mosquitto", "name": "Mosquitto broker", "state": "started"},
                    {"slug": SLUG, "name": "Home-Assistant-Matter-Hub", "state": state, "version": "2.0.59"},
                ]
            },
        },
    )
    aioclient_mock.get(
        f"{SUPERVISOR}/addons/{SLUG}/info",
        json={
            "result": "ok",
            "data": {"state": state, "ingress_entry": f"/api/hassio_ingress/{INGRESS_TOKEN}"},
        },
    )
    aioclient_mock.post(
        f"{SUPERVISOR}/ingress/session", json={"result": "ok", "data": {"session": "sess1"}}
    )
    aioclient_mock.get(f"{INGRESS}/api/health", json=health)
    aioclient_mock.get(f"{INGRESS}/api/matter/bridges", json=bridges)


def direct_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Matter Hub (192.0.2.20)",
        unique_id="direct_192.0.2.20:8482",
        data={CONF_CONNECTION: CONNECTION_DIRECT, CONF_URL: URL},
    )


def app_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Home-Assistant-Matter-Hub",
        unique_id=f"app_{SLUG}",
        data={CONF_CONNECTION: CONNECTION_APP, CONF_APP_SLUG: SLUG},
    )
