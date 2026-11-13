"""Config flow for Matter Bridge.

Every connection is a URL. The Matter Hub app does not publish Supervisor
discovery (its add-on config has no ``discovery:`` key; checked in
RiDDiX/home-assistant-addons for hamh, hamh-alpha and hamh-testing), so there
is no ``async_step_hassio``. The app also only lets the Supervisor connect
(see ``api.py``), so the forms say it can't be added yet; a 403 shows the
``forbidden`` error.

Entries saved by 1.x with ``connection: app`` are not a step in this flow.
Setup raises, and the repair in ``repairs.py`` (or Reconfigure) turns them
into a URL entry without changing the entry id.
"""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any
from urllib.parse import urlsplit

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from . import create_transport
from .api import (
    MatterHubAuthError,
    MatterHubClient,
    MatterHubError,
    MatterHubForbiddenError,
)
from .const import (
    CONF_CONNECTION,
    CONNECTION_APP,
    CONNECTION_DIRECT,
    DOMAIN,
    EXAMPLE_URL,
    MATTER_HUB_URL,
    ingress_removed_issue_id,
)

_LOGGER = logging.getLogger(__name__)

_CREDENTIALS = {
    vol.Optional(CONF_USERNAME): TextSelector(
        TextSelectorConfig(type=TextSelectorType.TEXT, autocomplete="username")
    ),
    vol.Optional(CONF_PASSWORD): TextSelector(
        TextSelectorConfig(
            type=TextSelectorType.PASSWORD, autocomplete="current-password"
        )
    ),
}


def normalize_url(url: str) -> str:
    """Turn ``host:8482`` into ``http://host:8482`` and drop a trailing slash."""
    url = url.strip().rstrip("/")
    if "://" not in url:
        url = f"http://{url}"
    return url


def url_unique_id(url: str) -> str:
    """Unique id for a URL entry. The host and port identify the hub."""
    parts = urlsplit(url)
    return f"{CONNECTION_DIRECT}_{parts.hostname}:{parts.port or 80}{parts.path}"


def entry_title(url: str) -> str:
    """Title shown on the integration card."""
    return f"Matter Hub ({urlsplit(url).hostname})"


def is_legacy_app_entry(data: Mapping[str, Any]) -> bool:
    """True for a 1.x entry that used Supervisor ingress."""
    return data.get(CONF_CONNECTION) == CONNECTION_APP


def other_entry_has_unique_id(
    hass: HomeAssistant, unique_id: str, entry_id: str
) -> bool:
    """True when a different Matter Bridge entry already uses ``unique_id``."""
    return any(
        entry.unique_id == unique_id and entry.entry_id != entry_id
        for entry in hass.config_entries.async_entries(DOMAIN)
    )


def build_connection_data(
    user_input: Mapping[str, Any],
    *,
    previous: Mapping[str, Any] | None = None,
    keep_blank_credentials: bool = False,
) -> dict[str, Any]:
    """The config-entry data for a URL connection.

    ``keep_blank_credentials`` keeps a username or password already stored
    when the form leaves that field blank. The repair uses it so an app
    entry that had authentication survives the move to a URL. Reconfigure of
    a URL entry does not: a blank field there clears the saved value.
    """
    data: dict[str, Any] = {
        CONF_CONNECTION: CONNECTION_DIRECT,
        CONF_URL: normalize_url(user_input[CONF_URL]),
    }
    for key in (CONF_USERNAME, CONF_PASSWORD):
        value = user_input.get(key) or ""
        if value:
            data[key] = value
        elif keep_blank_credentials and previous and previous.get(key):
            data[key] = previous[key]
    return data


def connection_schema(*, default_url: str | None = None) -> vol.Schema:
    """URL plus optional username and password."""
    url_field = (
        vol.Required(CONF_URL, default=default_url)
        if default_url is not None
        else vol.Required(CONF_URL)
    )
    return vol.Schema(
        {
            url_field: TextSelector(TextSelectorConfig(type=TextSelectorType.URL)),
            **_CREDENTIALS,
        }
    )


async def async_validate_connection(
    hass: HomeAssistant, data: Mapping[str, Any]
) -> dict[str, str]:
    """Try the URL. Return form errors, or an empty dict when it works."""
    client = MatterHubClient(create_transport(hass, data))
    try:
        await client.async_get_health()
        await client.async_get_bridges()
    except MatterHubAuthError:
        return {"base": "invalid_auth"}
    except MatterHubForbiddenError:
        return {"base": "forbidden"}
    except MatterHubError:
        return {"base": "cannot_connect"}
    except Exception:
        _LOGGER.exception("Unexpected error validating Matter Hub")
        return {"base": "unknown"}
    return {}


class MatterBridgeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Connect to Home Assistant Matter Hub at a URL."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the Matter Hub URL."""
        errors: dict[str, str] = {}
        if user_input is not None:
            data = build_connection_data(user_input)
            await self.async_set_unique_id(url_unique_id(data[CONF_URL]))
            self._abort_if_unique_id_configured()
            errors = await async_validate_connection(self.hass, data)
            if not errors:
                return self.async_create_entry(
                    title=entry_title(data[CONF_URL]), data=data
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                connection_schema(), user_input
            ),
            errors=errors,
            description_placeholders={
                "example_url": EXAMPLE_URL,
                "project_url": MATTER_HUB_URL,
            },
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the URL or credentials.

        A 1.x app entry has no URL yet. Submitting one converts it in place
        (same entry id, so devices and entities stay) and clears the repair.
        """
        entry = self._get_reconfigure_entry()
        legacy = is_legacy_app_entry(entry.data)
        errors: dict[str, str] = {}
        if user_input is not None:
            data = build_connection_data(
                user_input,
                previous=entry.data,
                keep_blank_credentials=legacy,
            )
            unique_id = url_unique_id(data[CONF_URL])
            if legacy:
                if other_entry_has_unique_id(self.hass, unique_id, entry.entry_id):
                    return self.async_abort(reason="already_configured")
            else:
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_mismatch(reason="different_hub")
            errors = await async_validate_connection(self.hass, data)
            if not errors:
                updates: dict[str, Any] = {}
                if legacy:
                    ir.async_delete_issue(
                        self.hass, DOMAIN, ingress_removed_issue_id(entry.entry_id)
                    )
                    # Same entry id, new unique id: devices are keyed by the
                    # entry id, so they stay while the URL takes over.
                    updates["unique_id"] = unique_id
                    updates["title"] = entry_title(data[CONF_URL])
                return self.async_update_reload_and_abort(entry, data=data, **updates)

        suggested = user_input or {
            key: value
            for key, value in entry.data.items()
            if key in (CONF_URL, CONF_USERNAME)
        }
        credential_hint = (
            "Leave the username and password blank to keep ones already saved."
            if legacy
            else "Leave the username and password blank to clear any saved ones."
        )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                connection_schema(), suggested
            ),
            errors=errors,
            description_placeholders={
                "credential_hint": credential_hint,
                "example_url": EXAMPLE_URL,
                "project_url": MATTER_HUB_URL,
            },
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Matter Hub started asking for a password."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the Matter Hub username and password."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**entry.data, **user_input}
            errors = await async_validate_connection(self.hass, data)
            if not errors:
                return self.async_update_reload_and_abort(entry, data=data)
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(CONF_USERNAME): TextSelector(
                            TextSelectorConfig(
                                type=TextSelectorType.TEXT, autocomplete="username"
                            )
                        ),
                        vol.Required(CONF_PASSWORD): TextSelector(
                            TextSelectorConfig(
                                type=TextSelectorType.PASSWORD,
                                autocomplete="current-password",
                            )
                        ),
                    }
                ),
                {CONF_USERNAME: entry.data.get(CONF_USERNAME)},
            ),
            errors=errors,
        )
