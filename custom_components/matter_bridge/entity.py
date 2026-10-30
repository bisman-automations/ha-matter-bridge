"""Base entities: the Matter Hub device and one device per bridge."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import MatterHubError
from .const import (
    CONF_APP_SLUG,
    CONF_CONNECTION,
    CONNECTION_APP,
    DOMAIN,
    MATTER_HUB_NAME,
)
from .coordinator import MatterBridgeConfigEntry, MatterHubCoordinator


def hub_identifier(entry: MatterBridgeConfigEntry) -> tuple[str, str]:
    """Device registry identifier of the Matter Hub device."""
    return (DOMAIN, entry.entry_id)


def bridge_identifier(
    entry: MatterBridgeConfigEntry, bridge_id: str
) -> tuple[str, str]:
    """Device registry identifier of a bridge device."""
    return (DOMAIN, f"{entry.entry_id}_{bridge_id}")


def configuration_url(entry: MatterBridgeConfigEntry) -> str | None:
    """Open the app panel for app installs, the web UI for direct ones."""
    if entry.data.get(CONF_CONNECTION) == CONNECTION_APP:
        return f"homeassistant://hassio/ingress/{entry.data[CONF_APP_SLUG]}"
    return entry.data.get("url")


async def run_action(call: Awaitable[Any]) -> None:
    """Turn Matter Hub errors into Home Assistant errors for the UI."""
    try:
        await call
    except MatterHubError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="action_failed",
            translation_placeholders={"error": str(err)},
        ) from err


def hub_device_info(
    entry: MatterBridgeConfigEntry, health: dict[str, Any]
) -> DeviceInfo:
    """The Matter Hub device; setup creates it before the bridges link to it."""
    return DeviceInfo(
        identifiers={hub_identifier(entry)},
        name="Matter Hub",
        manufacturer=MATTER_HUB_NAME,
        model="App"
        if entry.data.get(CONF_CONNECTION) == CONNECTION_APP
        else "Standalone",
        sw_version=health.get("version"),
        configuration_url=configuration_url(entry),
    )


class MatterHubEntity(CoordinatorEntity[MatterHubCoordinator]):
    """An entity on the Matter Hub device."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: MatterHubCoordinator, description: EntityDescription
    ) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        health = coordinator.data.health if coordinator.data else {}
        self._attr_device_info = hub_device_info(entry, health)


class MatterBridgeEntity(CoordinatorEntity[MatterHubCoordinator]):
    """An entity on a Matter Hub bridge device."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: MatterHubCoordinator,
        bridge_id: str,
        description: EntityDescription,
    ) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self.bridge_id = bridge_id
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{bridge_id}_{description.key}"
        bridge = self.bridge or {}
        info = bridge.get("basicInformation") or {}
        self._attr_device_info = DeviceInfo(
            identifiers={bridge_identifier(entry, bridge_id)},
            name=bridge.get("name") or bridge_id,
            manufacturer=info.get("vendorName") or MATTER_HUB_NAME,
            model=info.get("productName") or "Matter bridge",
            sw_version=info.get("softwareVersionString"),
            hw_version=info.get("hardwareVersionString"),
            serial_number=bridge_id,
            configuration_url=configuration_url(entry),
        )
        if coordinator.hub_device_id is not None:
            self._attr_device_info["via_device_id"] = coordinator.hub_device_id

    @property
    def bridge(self) -> dict[str, Any] | None:
        """This bridge's latest data, None once it is deleted in Matter Hub."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.bridges.get(self.bridge_id)

    @property
    def available(self) -> bool:
        return super().available and self.bridge is not None


def add_bridge_entities(
    coordinator: MatterHubCoordinator,
    async_add_entities: AddConfigEntryEntitiesCallback,
    factory: Callable[[str], list[MatterBridgeEntity]],
) -> None:
    """Add entities for every bridge now and for bridges created later."""
    known: set[str] = set()

    @callback
    def _add_new() -> None:
        if not coordinator.data:
            return
        new = [bid for bid in coordinator.data.bridges if bid not in known]
        if not new:
            return
        known.update(new)
        async_add_entities([ent for bid in new for ent in factory(bid)])

    _add_new()
    coordinator.config_entry.async_on_unload(coordinator.async_add_listener(_add_new))
