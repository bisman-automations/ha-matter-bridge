"""Fixtures for Matter Bridge tests.

The commissioning block uses the Matter SDK's published example values
(passcode 20202021, discriminator 3840). They are not a real bridge. Tests
assert they never reach state, attributes, events or this integration's logs,
and that diagnostics redact them.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.matter_bridge.const import (
    CONF_APP_SLUG,
    CONF_CONNECTION,
    CONNECTION_APP,
    CONNECTION_DIRECT,
    DOMAIN,
)
from homeassistant.const import CONF_URL

URL = "http://192.0.2.20:8482"
SLUG = "3fd9e6b0_hamh"

# Matter SDK example values. Not a secret from a real bridge.
EXAMPLE_MANUAL_CODE = "34970112332"
EXAMPLE_QR_CODE = "MT:Y.K9042C00KA0648G00"
EXAMPLE_PASSCODE = 20202021

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
            "passcode": EXAMPLE_PASSCODE,
            "discriminator": 3840,
            "manualPairingCode": EXAMPLE_MANUAL_CODE,
            "qrPairingCode": EXAMPLE_QR_CODE,
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


def mock_direct(aioclient_mock, health, bridges) -> None:
    aioclient_mock.get(f"{URL}/api/health", json=health)
    aioclient_mock.get(f"{URL}/api/matter/bridges", json=bridges)


def direct_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Matter Hub (192.0.2.20)",
        unique_id="direct_192.0.2.20:8482",
        data={CONF_CONNECTION: CONNECTION_DIRECT, CONF_URL: URL},
    )


def app_entry(**extra: Any) -> MockConfigEntry:
    """A 1.x entry that reached Matter Hub through Supervisor ingress."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Home-Assistant-Matter-Hub",
        unique_id=f"app_{SLUG}",
        data={CONF_CONNECTION: CONNECTION_APP, CONF_APP_SLUG: SLUG, **extra},
    )
