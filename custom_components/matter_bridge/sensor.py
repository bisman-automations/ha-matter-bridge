"""Sensors for Matter Hub and its bridges."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import BRIDGE_STATUSES, HEALTH_STATUSES
from .coordinator import MatterBridgeConfigEntry
from .entity import MatterBridgeEntity, MatterHubEntity, add_bridge_entities

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class HubSensorDescription(SensorEntityDescription):
    """A sensor computed from the health response."""

    value_fn: Callable[[dict[str, Any]], StateType]
    attrs_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


@dataclass(frozen=True, kw_only=True)
class BridgeSensorDescription(SensorEntityDescription):
    """A sensor computed from one bridge."""

    value_fn: Callable[[dict[str, Any]], StateType]
    attrs_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


def _commissioning(bridge: dict[str, Any]) -> dict[str, Any]:
    return bridge.get("commissioning") or {}


HUB_SENSORS: tuple[HubSensorDescription, ...] = (
    HubSensorDescription(
        key="status",
        translation_key="hub_status",
        device_class=SensorDeviceClass.ENUM,
        options=HEALTH_STATUSES,
        value_fn=lambda h: h.get("status"),
    ),
    HubSensorDescription(
        key="running_bridges",
        translation_key="running_bridges",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda h: h.get("services", {}).get("bridges", {}).get("running"),
        attrs_fn=lambda h: dict(h.get("services", {}).get("bridges", {})),
    ),
    HubSensorDescription(
        key="uptime",
        translation_key="uptime",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement="s",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda h: h.get("uptime"),
    ),
)

BRIDGE_SENSORS: tuple[BridgeSensorDescription, ...] = (
    BridgeSensorDescription(
        key="status",
        translation_key="bridge_status",
        device_class=SensorDeviceClass.ENUM,
        options=BRIDGE_STATUSES,
        value_fn=lambda b: b.get("status"),
        attrs_fn=lambda b: {"status_reason": b.get("statusReason"), "port": b.get("port")},
    ),
    BridgeSensorDescription(
        key="devices",
        translation_key="devices",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda b: b.get("deviceCount"),
    ),
    BridgeSensorDescription(
        key="fabrics",
        translation_key="fabrics",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda b: len(_commissioning(b).get("fabrics") or []),
        attrs_fn=lambda b: {
            "controllers": [
                f.get("label") or f"Vendor {f.get('rootVendorId')}"
                for f in _commissioning(b).get("fabrics") or []
            ]
        },
    ),
    BridgeSensorDescription(
        key="failed_entities",
        translation_key="failed_entities",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda b: len(b.get("failedEntities") or []),
        attrs_fn=lambda b: {
            "entities": {
                f.get("entityId"): f.get("reason") for f in b.get("failedEntities") or []
            }
        },
    ),
    BridgeSensorDescription(
        key="pairing_code",
        translation_key="pairing_code",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda b: _commissioning(b).get("manualPairingCode"),
        attrs_fn=lambda b: {"qr_code": _commissioning(b).get("qrPairingCode")},
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MatterBridgeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors."""
    coordinator = entry.runtime_data
    async_add_entities(HubSensor(coordinator, d) for d in HUB_SENSORS)
    add_bridge_entities(
        coordinator,
        async_add_entities,
        lambda bid: [BridgeSensor(coordinator, bid, d) for d in BRIDGE_SENSORS],
    )


class HubSensor(MatterHubEntity, SensorEntity):
    """Matter Hub sensor."""

    entity_description: HubSensorDescription

    @property
    def native_value(self) -> StateType:
        return self.entity_description.value_fn(self.coordinator.data.health)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if fn := self.entity_description.attrs_fn:
            return fn(self.coordinator.data.health)
        return None


class BridgeSensor(MatterBridgeEntity, SensorEntity):
    """Bridge sensor."""

    entity_description: BridgeSensorDescription

    @property
    def native_value(self) -> StateType:
        bridge = self.bridge
        return self.entity_description.value_fn(bridge) if bridge else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        bridge = self.bridge
        if bridge and (fn := self.entity_description.attrs_fn):
            return fn(bridge)
        return None
