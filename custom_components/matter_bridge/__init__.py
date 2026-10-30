"""Matter Bridge: Home Assistant Matter Hub as an integration."""

from __future__ import annotations

from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import DirectTransport, MatterHubClient, SupervisorTransport, Transport
from .const import CONF_APP_SLUG, CONF_CONNECTION, CONNECTION_APP, DOMAIN
from .coordinator import MatterBridgeConfigEntry, MatterHubCoordinator
from .entity import bridge_identifier, hub_device_info, hub_identifier

# A bridge must be missing from this many successful polls in a row before
# its device is removed. Matter Hub lists its bridges one by one while it
# starts, so a single poll during a restart can leave some (or all) out.
MISSING_POLLS_BEFORE_REMOVAL = 3

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
        return SupervisorTransport(
            hass, session, data[CONF_APP_SLUG], username, password
        )
    return DirectTransport(session, data[CONF_URL], username, password)


async def async_setup_entry(
    hass: HomeAssistant, entry: MatterBridgeConfigEntry
) -> bool:
    """Set up Matter Bridge from a config entry."""
    client = MatterHubClient(create_transport(hass, dict(entry.data)))
    coordinator = MatterHubCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    hub = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        **hub_device_info(entry, coordinator.data.health),
    )
    coordinator.hub_device_id = hub.id

    _remove_deleted_bridges(hass, entry, coordinator)
    entry.async_on_unload(
        coordinator.async_add_listener(
            lambda: _remove_deleted_bridges(hass, entry, coordinator)
        )
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: MatterBridgeConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(
    hass: HomeAssistant, entry: MatterBridgeConfigEntry
) -> None:
    """Drop the entry's repair issue when it is deleted."""
    ir.async_delete_issue(hass, DOMAIN, f"app_unavailable_{entry.entry_id}")


@callback
def _remove_deleted_bridges(
    hass: HomeAssistant,
    entry: MatterBridgeConfigEntry,
    coordinator: MatterHubCoordinator,
) -> None:
    """Drop devices for bridges that were deleted in Matter Hub.

    Nothing is removed while Matter Hub lists no bridges at all (it is
    starting or restarting), and a bridge is only removed once it has been
    missing from several successful polls in a row.
    """
    if not coordinator.data or not coordinator.last_update_success:
        return
    current = set(coordinator.data.bridges)
    if not current:
        return
    missing = coordinator.missing_polls
    for bridge_id in list(missing):
        if bridge_id in current:
            del missing[bridge_id]
    registry = dr.async_get(hass)
    hub = hub_identifier(entry)
    for device in dr.async_entries_for_config_entry(registry, entry.entry_id):
        if hub in device.identifiers:
            continue
        bridge_id = _bridge_id_of(entry, device)
        if bridge_id is None or bridge_id in current:
            continue
        missing[bridge_id] = missing.get(bridge_id, 0) + 1
        if missing[bridge_id] >= MISSING_POLLS_BEFORE_REMOVAL:
            del missing[bridge_id]
            registry.async_remove_device(device.id)


def _bridge_id_of(entry: MatterBridgeConfigEntry, device: dr.DeviceEntry) -> str | None:
    """The Matter Hub bridge id a device stands for, if it is one of ours."""
    prefix = f"{entry.entry_id}_"
    for domain, value in device.identifiers:
        if domain == hub_identifier(entry)[0] and value.startswith(prefix):
            return value.removeprefix(prefix)
    return None


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
