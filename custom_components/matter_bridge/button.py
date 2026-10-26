"""Buttons for Matter Hub bridge actions."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import MatterBridgeConfigEntry
from .entity import MatterBridgeEntity, MatterHubEntity, add_bridge_entities, run_action

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class ActionButtonDescription(ButtonEntityDescription):
    """A button that posts a Matter Hub action."""

    action: str


RESTART_ALL = ActionButtonDescription(
    key="restart_all",
    translation_key="restart_all",
    device_class=ButtonDeviceClass.RESTART,
    entity_category=EntityCategory.CONFIG,
    action="restart-all",
)

BRIDGE_BUTTONS: tuple[ActionButtonDescription, ...] = (
    ActionButtonDescription(
        key="restart",
        translation_key="restart",
        device_class=ButtonDeviceClass.RESTART,
        entity_category=EntityCategory.CONFIG,
        action="restart",
    ),
    ActionButtonDescription(
        key="refresh_devices",
        translation_key="refresh_devices",
        entity_category=EntityCategory.CONFIG,
        action="refresh",
    ),
    ActionButtonDescription(
        key="force_sync",
        translation_key="force_sync",
        entity_category=EntityCategory.CONFIG,
        action="force-sync",
    ),
    ActionButtonDescription(
        key="open_commissioning_window",
        translation_key="open_commissioning_window",
        entity_category=EntityCategory.CONFIG,
        action="open-commissioning-window",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MatterBridgeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up buttons."""
    coordinator = entry.runtime_data
    async_add_entities([HubButton(coordinator, RESTART_ALL)])
    add_bridge_entities(
        coordinator,
        async_add_entities,
        lambda bid: [BridgeButton(coordinator, bid, d) for d in BRIDGE_BUTTONS],
    )


class HubButton(MatterHubEntity, ButtonEntity):
    """Action on all bridges."""

    entity_description: ActionButtonDescription

    async def async_press(self) -> None:
        await run_action(
            self.coordinator.client.async_all_bridges_action(
                self.entity_description.action
            )
        )
        await self.coordinator.async_request_refresh()


class BridgeButton(MatterBridgeEntity, ButtonEntity):
    """Action on one bridge."""

    entity_description: ActionButtonDescription

    async def async_press(self) -> None:
        await run_action(
            self.coordinator.async_bridge_action(
                self.bridge_id, self.entity_description.action
            )
        )
