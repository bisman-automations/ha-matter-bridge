"""Matter Bridge: Home Assistant Matter Hub as an integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import (
    device_registry as dr,
    entity_registry as er,
    issue_registry as ir,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import DirectTransport, MatterHubClient, MatterHubError
from .app import find_app
from .const import (
    CONF_ADDON,
    CONF_CONNECTION,
    CONNECTION_APP,
    DOMAIN,
    app_unavailable_issue_id,
    ingress_removed_issue_id,
)
from .coordinator import MatterBridgeConfigEntry, MatterHubCoordinator
from .entity import bridge_id_of, bridge_identifier, hub_device_fields, hub_identifier

# A bridge must be missing from this many successful polls in a row before
# its device is removed. Matter Hub lists its bridges one by one while it
# starts, so a single poll during a restart can leave some (or all) out.
MISSING_POLLS_BEFORE_REMOVAL = 3

# Suffix of the Pairing code sensor removed in 2.0.0. Unique ids are
# ``<entry_id>_<bridge_id>_pairing_code``.
_PAIRING_CODE_SUFFIX = "_pairing_code"

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SENSOR,
    Platform.SWITCH,
]


def create_transport(hass: HomeAssistant, data: Mapping[str, Any]) -> DirectTransport:
    """Build the URL client a config entry or a flow input describes.

    App entries are rejected in ``async_setup_entry`` before this runs. A
    caller that still passes one gets an error instead of a Supervisor
    session.
    """
    if data.get(CONF_CONNECTION) == CONNECTION_APP or CONF_URL not in data:
        raise MatterHubError(
            "This Matter Bridge entry still uses the removed app connection"
        )
    session = async_get_clientsession(hass)
    return DirectTransport(
        session,
        str(data[CONF_URL]),
        data.get(CONF_USERNAME) or None,
        data.get(CONF_PASSWORD) or None,
    )


@callback
def _async_remove_pairing_code_entities(
    hass: HomeAssistant, entry: MatterBridgeConfigEntry
) -> None:
    """Remove Pairing code entities this entry created in 1.x.

    They stay in the entity registry after the sensor is deleted, and the
    restored state would still be the manual pairing code. Only entities
    owned by this entry, with this integration's unique id, are removed.
    """
    registry = er.async_get(hass)
    prefix = f"{entry.entry_id}_"
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        unique_id = entity.unique_id or ""
        if not (
            unique_id.startswith(prefix) and unique_id.endswith(_PAIRING_CODE_SUFFIX)
        ):
            continue
        entity_id = entity.entity_id
        registry.async_remove(entity_id)
        # A restored state can outlive the registry entry. Drop it too, so
        # the pairing code is not left in the state machine.
        if hass.states.get(entity_id) is not None:
            hass.states.async_remove(entity_id)


def _async_clear_stale_issues(hass: HomeAssistant, entry_id: str) -> None:
    """Drop the pre-2.0.0 "app unavailable" repair if a previous version left it."""
    ir.async_delete_issue(hass, DOMAIN, app_unavailable_issue_id(entry_id))


@callback
def _async_follow_app_port(hass: HomeAssistant, entry: MatterBridgeConfigEntry) -> None:
    """Point an app entry at the app's current port.

    The Supervisor assigns the Matter Hub app's port. It normally keeps it,
    but a reinstall gets a new one. When the app isn't found (no Supervisor
    info yet, or the app was removed) the saved address is kept.
    """
    slug = entry.data.get(CONF_ADDON)
    if not slug or (app := find_app(hass, str(slug))) is None:
        return
    if entry.data.get(CONF_URL) != app.url:
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_URL: app.url}
        )


async def async_setup_entry(
    hass: HomeAssistant, entry: MatterBridgeConfigEntry
) -> bool:
    """Set up Matter Bridge from a config entry."""
    _async_clear_stale_issues(hass, entry.entry_id)
    # Do this even when the entry cannot load, so the pairing code leaves
    # the entity registry on the upgrade that removes the sensor.
    _async_remove_pairing_code_entities(hass, entry)

    if entry.data.get(CONF_CONNECTION) == CONNECTION_APP:
        # Not loaded, on purpose. The repair (or Reconfigure) writes a URL
        # onto this same entry and reloads it.
        ir.async_create_issue(
            hass,
            DOMAIN,
            ingress_removed_issue_id(entry.entry_id),
            is_fixable=True,
            severity=ir.IssueSeverity.ERROR,
            translation_key="ingress_removed",
            translation_placeholders={"title": entry.title},
            data={"entry_id": entry.entry_id},
        )
        raise ConfigEntryError(
            translation_domain=DOMAIN,
            translation_key="ingress_removed",
            translation_placeholders={"title": entry.title},
        )

    ir.async_delete_issue(hass, DOMAIN, ingress_removed_issue_id(entry.entry_id))
    _async_follow_app_port(hass, entry)

    client = MatterHubClient(create_transport(hass, dict(entry.data)))
    coordinator = MatterHubCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    hub = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        **hub_device_fields(entry, coordinator.data.health),
    )
    coordinator.hub_device_id = hub.id

    # Registered before the platforms add their listeners, so on a poll that
    # removes a device the platforms see it gone and can forget that bridge.
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
    """Drop this entry's repair issues when it is deleted."""
    ir.async_delete_issue(hass, DOMAIN, ingress_removed_issue_id(entry.entry_id))
    _async_clear_stale_issues(hass, entry.entry_id)


@callback
def _remove_deleted_bridges(
    hass: HomeAssistant,
    entry: MatterBridgeConfigEntry,
    coordinator: MatterHubCoordinator,
) -> None:
    """Drop devices for bridges that were deleted in Matter Hub.

    The coordinator calls its listeners after a failed poll too, and ``data``
    is still the previous successful list. Counting that poll would treat the
    bridge as back (it is in the stale list) and reset the absence streak, so
    a bridge that is really gone would never reach the removal threshold
    while Matter Hub is flapping. Only a successful poll changes the streak.

    Nothing is removed while Matter Hub lists no bridges at all (it is
    starting or restarting). A bridge is removed once it has been missing
    from ``MISSING_POLLS_BEFORE_REMOVAL`` successful polls in a row.
    """
    if not coordinator.last_update_success or not coordinator.data:
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
        bridge_id = bridge_id_of(entry, device)
        if bridge_id is None or bridge_id in current:
            continue
        missing[bridge_id] = missing.get(bridge_id, 0) + 1
        if missing[bridge_id] >= MISSING_POLLS_BEFORE_REMOVAL:
            del missing[bridge_id]
            registry.async_remove_device(device.id)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: MatterBridgeConfigEntry, device: dr.DeviceEntry
) -> bool:
    """Allow removing a bridge device only once the bridge is gone."""
    coordinator = entry.runtime_data
    if hub_identifier(entry) in device.identifiers:
        return False
    return not any(
        bridge_identifier(entry, bridge_id) in device.identifiers
        for bridge_id in coordinator.data.bridges
    )
