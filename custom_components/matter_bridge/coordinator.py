"""Polls Matter Hub for health and bridge state."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MatterHubAuthError, MatterHubClient, MatterHubError
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

type MatterBridgeConfigEntry = ConfigEntry[MatterHubCoordinator]


@dataclass(slots=True)
class MatterHubData:
    """One poll of Matter Hub."""

    health: dict[str, Any]
    bridges: dict[str, dict[str, Any]] = field(default_factory=dict)


class MatterHubCoordinator(DataUpdateCoordinator[MatterHubData]):
    """Fetch health and the bridge list on an interval."""

    config_entry: MatterBridgeConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: MatterBridgeConfigEntry, client: MatterHubClient
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self.client = client

    async def _async_update_data(self) -> MatterHubData:
        try:
            health = await self.client.async_get_health()
            bridges = await self.client.async_get_bridges()
        except MatterHubAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except MatterHubError as err:
            raise UpdateFailed(str(err)) from err
        return MatterHubData(
            health=health,
            bridges={b["id"]: b for b in bridges if isinstance(b, dict) and "id" in b},
        )

    async def async_bridge_action(self, bridge_id: str, action: str) -> None:
        """Run a bridge action, then refresh so entities update right away."""
        await self.client.async_bridge_action(bridge_id, action)
        await self.async_request_refresh()
