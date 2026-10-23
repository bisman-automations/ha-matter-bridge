"""Binary sensors for Matter Hub and its bridges."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import MatterBridgeConfigEntry
from .entity import MatterBridgeEntity, MatterHubEntity, add_bridge_entities

PARALLEL_UPDATES = 0

HA_CONNECTED = BinarySensorEntityDescription(
    key="home_assistant_connected",
    translation_key="home_assistant_connected",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
    entity_category=EntityCategory.DIAGNOSTIC,
)
COMMISSIONED = BinarySensorEntityDescription(
    key="commissioned",
    translation_key="commissioned",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MatterBridgeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up binary sensors."""
    coordinator = entry.runtime_data
    async_add_entities([HomeAssistantConnected(coordinator, HA_CONNECTED)])
    add_bridge_entities(
        coordinator,
        async_add_entities,
        lambda bid: [BridgeCommissioned(coordinator, bid, COMMISSIONED)],
    )


class HomeAssistantConnected(MatterHubEntity, BinarySensorEntity):
    """Whether Matter Hub's own connection to Home Assistant is up."""

    @property
    def is_on(self) -> bool | None:
        services = self.coordinator.data.health.get("services", {})
        return services.get("homeAssistant", {}).get("connected")


class BridgeCommissioned(MatterBridgeEntity, BinarySensorEntity):
    """Whether at least one controller has paired with the bridge."""

    @property
    def is_on(self) -> bool | None:
        bridge = self.bridge
        if not bridge or not bridge.get("commissioning"):
            return None
        return bool(bridge["commissioning"].get("isCommissioned"))
