"""Config flow for Matter Bridge.

Every connection is a URL. The Matter Hub app does not publish Supervisor
discovery (its add-on config has no ``discovery:`` key; checked in
RiDDiX/home-assistant-addons for hamh, hamh-alpha and hamh-testing), so there
is no ``async_step_hassio``. The URL field is optional: left blank, the flow
uses the Matter Hub app on this host (``app.py``) at ``127.0.0.1`` and its
port, with user name ``hamh`` unless one is entered. A 403 shows the
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
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
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
from .app import APP_USERNAME, MatterHubApp, find_app, find_apps
from .const import (
    CONF_ADDON,
    CONF_APP_SLUG,
    CONF_CONNECTION,
    CONNECTION_APP,
    CONNECTION_DIRECT,
    DOMAIN,
    EXAMPLE_URL,
    MATTER_HUB_URL,
    ingress_removed_issue_id,
)

_LOGGER = logging.getLogger(__name__)

CONF_APP = "app"

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


def entry_title(url: str, app: MatterHubApp | None = None) -> str:
    """Title shown on the integration card."""
    if app is not None:
        return app.name
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
    app: MatterHubApp | None = None,
) -> dict[str, Any]:
    """The config-entry data for a URL connection.

    ``keep_blank_credentials`` keeps a username or password already stored
    when the form leaves that field blank. The repair uses it so an app
    entry that had authentication survives the move to a URL. Reconfigure of
    a URL entry does not: a blank field there clears the saved value.
    """
    data: dict[str, Any] = {CONF_CONNECTION: CONNECTION_DIRECT}
    if app is not None:
        data[CONF_URL] = app.url
        data[CONF_ADDON] = app.slug
    else:
        data[CONF_URL] = normalize_url(user_input[CONF_URL])
    for key in (CONF_USERNAME, CONF_PASSWORD):
        value = user_input.get(key) or ""
        if value:
            data[key] = value
        elif keep_blank_credentials and previous and previous.get(key):
            data[key] = previous[key]
    # The app's local password is for user hamh. Without a password the app
    # may be open to the host, so no username is sent either.
    if app is not None and data.get(CONF_PASSWORD) and not data.get(CONF_USERNAME):
        data[CONF_USERNAME] = APP_USERNAME
    return data


def entry_unique_id(data: Mapping[str, Any]) -> str:
    """Unique id: the app's slug for the app on this host, else the URL."""
    if data.get(CONF_ADDON):
        return f"{CONF_APP}_{data[CONF_ADDON]}"
    return url_unique_id(data[CONF_URL])


def pick_app(
    hass: HomeAssistant,
    user_input: Mapping[str, Any],
    previous: Mapping[str, Any] | None = None,
) -> tuple[MatterHubApp | None, dict[str, str]]:
    """The app to use when the URL is blank, or the form error.

    A URL means no app. Otherwise the app picked in the form, then the one
    this entry already used, then the first installed (started ones first).
    """
    if (user_input.get(CONF_URL) or "").strip():
        return None, {}
    apps = find_apps(hass)
    if not apps:
        return None, {CONF_URL: "no_app"}
    wanted = user_input.get(CONF_APP) or (
        previous and (previous.get(CONF_ADDON) or previous.get(CONF_APP_SLUG))
    )
    if wanted and (match := find_app(hass, str(wanted))):
        return match, {}
    return apps[0], {}


def connection_schema(apps: list[MatterHubApp] | None = None) -> vol.Schema:
    """Optional URL, a choice of app when more than one is installed, and
    optional username and password."""
    fields: dict[Any, Any] = {
        vol.Optional(CONF_URL): TextSelector(
            TextSelectorConfig(type=TextSelectorType.URL)
        ),
    }
    if apps and len(apps) > 1:
        fields[vol.Optional(CONF_APP)] = SelectSelector(
            SelectSelectorConfig(
                options=[
                    SelectOptionDict(value=app.slug, label=app.name) for app in apps
                ],
                mode=SelectSelectorMode.DROPDOWN,
            )
        )
    return vol.Schema({**fields, **_CREDENTIALS})


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
        apps = find_apps(self.hass)
        if user_input is not None:
            app, errors = pick_app(self.hass, user_input)
            if not errors:
                data = build_connection_data(user_input, app=app)
                await self.async_set_unique_id(entry_unique_id(data))
                self._abort_if_unique_id_configured()
                errors = await async_validate_connection(self.hass, data)
                if not errors:
                    return self.async_create_entry(
                        title=entry_title(data[CONF_URL], app), data=data
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                connection_schema(apps), user_input
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
        apps = find_apps(self.hass)
        if user_input is not None:
            app, errors = pick_app(self.hass, user_input, entry.data)
        if user_input is not None and not errors:
            data = build_connection_data(
                user_input,
                previous=entry.data,
                keep_blank_credentials=legacy,
                app=app,
            )
            unique_id = entry_unique_id(data)
            if legacy:
                if other_entry_has_unique_id(self.hass, unique_id, entry.entry_id):
                    return self.async_abort(reason="already_configured")
            elif not (entry.data.get(CONF_ADDON) or data.get(CONF_ADDON)):
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_mismatch(reason="different_hub")
            elif entry.unique_id != unique_id and other_entry_has_unique_id(
                self.hass, unique_id, entry.entry_id
            ):
                # Moving between a typed URL and the app on this host is
                # allowed, unless another entry already has that hub.
                return self.async_abort(reason="already_configured")
            errors = await async_validate_connection(self.hass, data)
            if not errors:
                updates: dict[str, Any] = {}
                if legacy:
                    ir.async_delete_issue(
                        self.hass, DOMAIN, ingress_removed_issue_id(entry.entry_id)
                    )
                # Same entry id, new unique id: devices are keyed by the
                # entry id, so they stay while the new address takes over.
                if entry.unique_id != unique_id:
                    updates["unique_id"] = unique_id
                    updates["title"] = entry_title(data[CONF_URL], app)
                return self.async_update_reload_and_abort(entry, data=data, **updates)

        suggested = user_input or {
            key: value
            for key, value in entry.data.items()
            if key in (CONF_URL, CONF_USERNAME) and not entry.data.get(CONF_ADDON)
        }
        credential_hint = (
            "Leave the username and password blank to keep ones already saved."
            if legacy
            else "Leave the username and password blank to clear any saved ones."
        )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                connection_schema(apps), suggested
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
