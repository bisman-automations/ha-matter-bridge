"""Matter Bridge: Home Assistant Matter Hub as an integration."""

from __future__ import annotations

from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import DirectTransport, MatterHubClient, SupervisorTransport, Transport
from .const import CONF_APP_SLUG, CONF_CONNECTION, CONNECTION_APP
from .coordinator import MatterBridgeConfigEntry, MatterHubCoordinator
from .entity import bridge_identifier, hub_identifier

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SENSOR,
    Platform.SWITCH,
]


def create_transport(hass: HomeAssistant, data: dict) -> Transport:
    """Build the transport a config entry (or flow input) describes."""
    session = async_get_clientsession(hass)
    username = data.get(CONF_USERNAME) or None
    password = data.get(CONF_PASSWORD) or None
    if data.get(CONF_CONNECTION) == CONNECTION_APP:
        return SupervisorTransport(hass, session, data[CONF_APP_SLUG], username, password)
    return DirectTransport(session, data[CONF_URL], username, password)


async def async_setup_entry(hass: HomeAssistant, entry: MatterBridgeConfigEntry) -> bool:
    """Set up Matter Bridge from a config entry."""
    client = MatterHubClient(create_transport(hass, dict(entry.data)))
    coordinator = MatterHubCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    _remove_deleted_bridges(hass, entry, coordinator)
    entry.async_on_unload(
        coordinator.async_add_listener(
            lambda: _remove_deleted_bridges(hass, entry, coordinator)
        )
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MatterBridgeConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


@callback
def _remove_deleted_bridges(
    hass: HomeAssistant, entry: MatterBridgeConfigEntry, coordinator: MatterHubCoordinator
) -> None:
    """Drop devices for bridges that were deleted in Matter Hub."""
    if not coordinator.data or not coordinator.last_update_success:
        return
    registry = dr.async_get(hass)
    keep = {hub_identifier(entry)} | {
        bridge_identifier(entry, bid) for bid in coordinator.data.bridges
    }
    for device in dr.async_entries_for_config_entry(registry, entry.entry_id):
        if not device.identifiers & keep:
            registry.async_update_device(device.id, remove_config_entry_id=entry.entry_id)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: MatterBridgeConfigEntry, device: dr.DeviceEntry
) -> bool:
    """Allow removing a bridge device only once the bridge is gone."""
    coordinator = entry.runtime_data
    if hub_identifier(entry) in device.identifiers:
        return False
    return not any(
        bridge_identifier(entry, bid) in device.identifiers
        for bid in coordinator.data.bridges
    )
