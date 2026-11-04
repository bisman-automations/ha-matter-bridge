"""Repair that moves a 1.x app entry onto a URL.

The entry id does not change, so the devices and entities already registered
for it stay (their unique ids are ``<entry_id>_...``). The repair replaces
``connection: app`` with the URL transport and reloads.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.repairs import RepairsFlow
from homeassistant.const import CONF_URL, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import issue_registry as ir

from .config_flow import (
    async_validate_connection,
    build_connection_data,
    connection_schema,
    entry_title,
    other_entry_has_unique_id,
    url_unique_id,
)
from .const import DEFAULT_URL, DOMAIN, MATTER_HUB_URL, ingress_removed_issue_id


class IngressRemovedRepairFlow(RepairsFlow):
    """Ask for the Matter Hub URL and convert the entry."""

    def __init__(self, entry_id: str) -> None:
        self._entry_id = entry_id

    async def async_step_init(
        self, user_input: dict[str, str] | None = None
    ) -> FlowResult:
        """Collect the URL and reload the same config entry."""
        entry = self.hass.config_entries.async_get_entry(self._entry_id)
        if entry is None:
            return self.async_abort(reason="entry_gone")

        # The repairs flow calls this step first with {"issue_id": ...}.
        # That is not the form. A submission always includes the URL.
        if user_input is not None and CONF_URL not in user_input:
            user_input = None

        errors: dict[str, str] = {}
        if user_input is not None:
            data = build_connection_data(
                user_input, previous=entry.data, keep_blank_credentials=True
            )
            unique_id = url_unique_id(data[CONF_URL])
            if other_entry_has_unique_id(self.hass, unique_id, entry.entry_id):
                errors = {"base": "already_configured"}
            else:
                errors = await async_validate_connection(self.hass, data)
            if not errors:
                # Drop the repair before reload. Setup of the URL entry
                # deletes it too; doing it here covers a reload that is still
                # in progress when the flow finishes.
                ir.async_delete_issue(
                    self.hass, DOMAIN, ingress_removed_issue_id(entry.entry_id)
                )
                self.hass.config_entries.async_update_entry(
                    entry,
                    data=data,
                    unique_id=unique_id,
                    title=entry_title(data[CONF_URL]),
                )
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_create_entry(data={})

        suggested: dict[str, Any] = {CONF_URL: DEFAULT_URL}
        if username := entry.data.get(CONF_USERNAME):
            suggested[CONF_USERNAME] = username
        if user_input:
            suggested.update(user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                connection_schema(), suggested
            ),
            errors=errors,
            description_placeholders={
                "example_url": DEFAULT_URL,
                "project_url": MATTER_HUB_URL,
                "title": entry.title,
            },
        )


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, str | int | float | None] | None,
) -> RepairsFlow:
    """Create the fix flow for an ``ingress_removed`` issue."""
    entry_id = str((data or {}).get("entry_id") or "")
    if not entry_id and issue_id.startswith("ingress_removed_"):
        entry_id = issue_id.removeprefix("ingress_removed_")
    return IngressRemovedRepairFlow(entry_id)
