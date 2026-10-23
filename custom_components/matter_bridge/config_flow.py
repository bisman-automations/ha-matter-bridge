"""Config flow for Matter Bridge."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any
from urllib.parse import urlsplit

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from . import create_transport
from .api import (
    MatterHubApp,
    MatterHubAppError,
    MatterHubAuthError,
    MatterHubClient,
    MatterHubError,
    async_find_apps,
    supervisor_available,
)
from .const import (
    CONF_APP_SLUG,
    CONF_CONNECTION,
    CONNECTION_APP,
    CONNECTION_DIRECT,
    DEFAULT_URL,
    DOMAIN,
    MATTER_HUB_URL,
)

_LOGGER = logging.getLogger(__name__)

CREDENTIALS = {
    vol.Optional(CONF_USERNAME): TextSelector(
        TextSelectorConfig(type=TextSelectorType.TEXT, autocomplete="username")
    ),
    vol.Optional(CONF_PASSWORD): TextSelector(
        TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="current-password")
    ),
}


def _normalize_url(url: str) -> str:
    url = url.strip().rstrip("/")
    if "://" not in url:
        url = f"http://{url}"
    return url


def _url_unique_id(url: str) -> str:
    parts = urlsplit(url)
    return f"{CONNECTION_DIRECT}_{parts.hostname}:{parts.port or 80}{parts.path}"


class MatterBridgeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Connect to Home Assistant Matter Hub."""

    VERSION = 1

    def __init__(self) -> None:
        self._apps: list[MatterHubApp] = []

    async def _async_validate(self, data: dict[str, Any]) -> tuple[dict[str, str], str | None]:
        """Try the connection; return form errors and Matter Hub's version."""
        client = MatterHubClient(create_transport(self.hass, data))
        try:
            health = await client.async_get_health()
            await client.async_get_bridges()
        except MatterHubAuthError:
            return {"base": "invalid_auth"}, None
        except MatterHubAppError:
            return {"base": "app_not_running"}, None
        except MatterHubError:
            return {"base": "cannot_connect"}, None
        except Exception:
            _LOGGER.exception("Unexpected error validating Matter Hub")
            return {"base": "unknown"}, None
        return {}, health.get("version")

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Offer the installed app when there is one, otherwise ask for a URL."""
        if supervisor_available():
            try:
                self._apps = await async_find_apps(self.hass)
            except MatterHubError as err:
                _LOGGER.debug("Could not list Supervisor apps: %s", err)
                self._apps = []
        if self._apps:
            return self.async_show_menu(step_id="user", menu_options=["app", "direct"])
        return await self.async_step_direct()

    async def async_step_app(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Connect to the Matter Hub app through Supervisor ingress."""
        errors: dict[str, str] = {}
        if user_input is not None:
            slug = user_input[CONF_APP_SLUG]
            await self.async_set_unique_id(f"{CONNECTION_APP}_{slug}")
            self._abort_if_unique_id_configured()
            data = {CONF_CONNECTION: CONNECTION_APP, **user_input}
            errors, _ = await self._async_validate(data)
            if not errors:
                app = next((a for a in self._apps if a.slug == slug), None)
                return self.async_create_entry(
                    title=app.name if app else "Matter Hub", data=data
                )

        options = [
            SelectOptionDict(value=a.slug, label=f"{a.name} ({a.state})") for a in self._apps
        ]
        schema = vol.Schema(
            {
                vol.Required(CONF_APP_SLUG, default=self._apps[0].slug): SelectSelector(
                    SelectSelectorConfig(options=options)
                ),
                **CREDENTIALS,
            }
        )
        return self.async_show_form(
            step_id="app",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
        )

    async def async_step_direct(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Connect to Matter Hub at a URL (Docker / standalone)."""
        errors: dict[str, str] = {}
        if user_input is not None:
            url = _normalize_url(user_input[CONF_URL])
            await self.async_set_unique_id(_url_unique_id(url))
            self._abort_if_unique_id_configured()
            data = {CONF_CONNECTION: CONNECTION_DIRECT, **user_input, CONF_URL: url}
            errors, _ = await self._async_validate(data)
            if not errors:
                return self.async_create_entry(
                    title=f"Matter Hub ({urlsplit(url).hostname})", data=data
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_URL, default=DEFAULT_URL): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.URL)
                ),
                **CREDENTIALS,
            }
        )
        return self.async_show_form(
            step_id="direct",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
            description_placeholders={"project_url": MATTER_HUB_URL},
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the URL or credentials."""
        entry = self._get_reconfigure_entry()
        is_app = entry.data.get(CONF_CONNECTION) == CONNECTION_APP
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**entry.data, **user_input}
            for key in (CONF_USERNAME, CONF_PASSWORD):
                if not user_input.get(key):
                    data.pop(key, None)
            if not is_app:
                data[CONF_URL] = _normalize_url(user_input[CONF_URL])
                await self.async_set_unique_id(_url_unique_id(data[CONF_URL]))
                self._abort_if_unique_id_mismatch(reason="different_hub")
            errors, _ = await self._async_validate(data)
            if not errors:
                return self.async_update_reload_and_abort(entry, data=data)

        fields: dict[Any, Any] = {}
        if not is_app:
            fields[vol.Required(CONF_URL)] = TextSelector(
                TextSelectorConfig(type=TextSelectorType.URL)
            )
        schema = vol.Schema({**fields, **CREDENTIALS})
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                schema, user_input or {k: v for k, v in entry.data.items() if k != CONF_PASSWORD}
            ),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
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
            errors, _ = await self._async_validate(data)
            if not errors:
                return self.async_update_reload_and_abort(entry, data=data)
        schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.TEXT, autocomplete="username")
                ),
                vol.Required(CONF_PASSWORD): TextSelector(
                    TextSelectorConfig(
                        type=TextSelectorType.PASSWORD, autocomplete="current-password"
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=self.add_suggested_values_to_schema(
                schema, {CONF_USERNAME: entry.data.get(CONF_USERNAME)}
            ),
            errors=errors,
        )
