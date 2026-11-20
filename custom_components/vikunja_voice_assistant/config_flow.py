import logging
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import selector  # added

from .const import (
    DOMAIN,
    CONF_VIKUNJA_URL,
    CONF_VIKUNJA_API_KEY,
    CONF_AI_TASK_ENTITY,
    CONF_DUE_DATE,
    DUE_DATE_OPTIONS,
    CONF_VOICE_CORRECTION,
    CONF_AUTO_VOICE_LABEL,
    CONF_ENABLE_USER_ASSIGN,
    DUE_DATE_OPTION_LABELS,
    CONF_DETAILED_RESPONSE,
)
from .helpers.localization import get_language
from .api.vikunja_api import VikunjaAPI
from .user_cache import build_initial_user_cache_sync

_LOGGER = logging.getLogger(__name__)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):  # type: ignore[call-arg]
    """Handle a config flow for the Vikunja integration."""

    VERSION = 1
    _basic_input: dict | None = None


    def _build_data_schema(self, defaults):
        lang = get_language(self.hass)
        due_date_selector = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    selector.SelectOptionDict(
                        value=value,
                        label=(
                            DUE_DATE_OPTION_LABELS.get(value, {}).get(lang)
                            or DUE_DATE_OPTION_LABELS.get(value, {}).get("en", value)
                        ),
                    )
                    for value in DUE_DATE_OPTIONS
                ],
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        )
        ai_task_selector = selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain=["ai_task"],
            )
        )
        token_selector = selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
        )

        return vol.Schema(
            {
                vol.Required(CONF_VIKUNJA_URL, default=defaults.get(CONF_VIKUNJA_URL, "")): str,
                vol.Required(
                    CONF_VIKUNJA_API_KEY,
                    default=defaults.get(CONF_VIKUNJA_API_KEY, ""),
                ): token_selector,
                vol.Required(
                    CONF_AI_TASK_ENTITY,
                    default=defaults.get(CONF_AI_TASK_ENTITY, ""),
                ): ai_task_selector,
                vol.Required(
                    CONF_VOICE_CORRECTION,
                    default=defaults.get(CONF_VOICE_CORRECTION, True),
                ): cv.boolean,
                vol.Required(
                    CONF_AUTO_VOICE_LABEL,
                    default=defaults.get(CONF_AUTO_VOICE_LABEL, True),
                ): cv.boolean,
                vol.Required(
                    CONF_ENABLE_USER_ASSIGN,
                    default=defaults.get(CONF_ENABLE_USER_ASSIGN, False),
                ): cv.boolean,
                vol.Required(
                    CONF_DUE_DATE, default=defaults.get(CONF_DUE_DATE, "tomorrow")
                ): due_date_selector,
                vol.Required(
                    CONF_DETAILED_RESPONSE,
                    default=defaults.get(CONF_DETAILED_RESPONSE, True),
                ): cv.boolean,
            }
        )

    def _sanitize_user_input(self, user_input):
        sanitized = dict(user_input)
        sanitized[CONF_VIKUNJA_API_KEY] = sanitized.get(CONF_VIKUNJA_API_KEY, "").strip()
        sanitized[CONF_AI_TASK_ENTITY] = sanitized.get(CONF_AI_TASK_ENTITY, "").strip()

        base_url = sanitized.get(CONF_VIKUNJA_URL, "").strip()
        if base_url:
            base_url = base_url.rstrip("/")
            if not base_url.endswith("/api/v1"):
                sanitized[CONF_VIKUNJA_URL] = f"{base_url}/api/v1"
            else:
                sanitized[CONF_VIKUNJA_URL] = base_url
        else:
            sanitized[CONF_VIKUNJA_URL] = ""

        return sanitized

    async def _test_connection(self, vikunja_url, api_key):
        if not vikunja_url or not api_key:
            return False

        vikunja_api = VikunjaAPI(vikunja_url, api_key)
        return await self.hass.async_add_executor_job(vikunja_api.test_connection)

    async def _ensure_user_cache(self, data):
        if not data.get(CONF_ENABLE_USER_ASSIGN):
            return

        await self.hass.async_add_executor_job(
            build_initial_user_cache_sync,
            self.hass.config.config_dir,
            data[CONF_VIKUNJA_URL],
            data[CONF_VIKUNJA_API_KEY],
        )

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors: dict[str, str] = {}
        defaults = user_input or {}

        if user_input is not None:
            sanitized = self._sanitize_user_input(user_input)
            defaults = sanitized

            connection_ok = await self._test_connection(
                sanitized[CONF_VIKUNJA_URL], sanitized[CONF_VIKUNJA_API_KEY]
            )

            if connection_ok:
                await self._ensure_user_cache(sanitized)

                await self.async_set_unique_id(f"vikunja_{sanitized[CONF_VIKUNJA_URL]}")
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"Vikunja ({sanitized[CONF_VIKUNJA_URL]})", data=sanitized
                )

            errors["base"] = "cannot_connect"

        data_schema = self._build_data_schema(defaults)
        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input=None):
        """Handle reconfiguration initiated from an existing entry."""
        entry_id = self.context.get("entry_id")
        if not entry_id:
            return self.async_abort(reason="reconfigure_entry_not_found")

        entry = self.hass.config_entries.async_get_entry(entry_id)
        if entry is None:
            return self.async_abort(reason="reconfigure_entry_not_found")

        errors: dict[str, str] = {}
        defaults = dict(entry.data)

        if user_input is not None:
            sanitized = self._sanitize_user_input(user_input)
            defaults = sanitized

            connection_ok = await self._test_connection(
                sanitized[CONF_VIKUNJA_URL], sanitized[CONF_VIKUNJA_API_KEY]
            )

            if connection_ok:
                await self._ensure_user_cache(sanitized)

                self.hass.config_entries.async_update_entry(entry, data=sanitized)
                await self.hass.config_entries.async_reload(entry.entry_id)

                return self.async_abort(reason="reconfigure_successful")

            errors["base"] = "cannot_connect"

        data_schema = self._build_data_schema(defaults)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=data_schema,
            errors=errors,
        )
