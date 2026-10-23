"""Start / stop switch per bridge."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import MatterBridgeConfigEntry
from .entity import MatterBridgeEntity, add_bridge_entities, run_action

PARALLEL_UPDATES = 1

RUNNING = SwitchEntityDescription(key="running", translation_key="running")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MatterBridgeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up switches."""
    coordinator = entry.runtime_data
    add_bridge_entities(
        coordinator,
        async_add_entities,
        lambda bid: [BridgeRunningSwitch(coordinator, bid, RUNNING)],
    )


class BridgeRunningSwitch(MatterBridgeEntity, SwitchEntity):
    """On while the bridge is running (or starting)."""

    @property
    def is_on(self) -> bool | None:
        bridge = self.bridge
        return bridge.get("status") in ("running", "starting") if bridge else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await run_action(self.coordinator.async_bridge_action(self.bridge_id, "start"))

    async def async_turn_off(self, **kwargs: Any) -> None:
        await run_action(self.coordinator.async_bridge_action(self.bridge_id, "stop"))
