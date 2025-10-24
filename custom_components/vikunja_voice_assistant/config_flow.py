import logging
import voluptuous as vol
import aiohttp

from homeassistant import config_entries
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import selector  # added

from .const import (
    DOMAIN,
    CONF_OPENAI_API_KEY,
    CONF_VIKUNJA_URL,
    CONF_VIKUNJA_API_KEY,
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
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL
    _basic_input: dict | None = None

    async def _test_openai_connection(self, api_key: str) -> bool:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        # Simple test payload to validate API key
        payload = {
            "model": "gpt-5-nano",
            "messages": [{"role": "user", "content": "test"}],
            "max_tokens": 1,
            "reasoning_effort": "minimal",
        }

        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json=payload,
                ) as response:
                    # Accept both 200 (success) and 400 (bad request but valid auth)
                    # 401 would indicate invalid API key
                    return response.status != 401
        except Exception as err:
            _LOGGER.error("Failed to test OpenAI connection: %s", err)
            return False

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        # Determine language for localized labels, fallback handled by lookup
        lang = get_language(self.hass)
        # Build selector once with localized labels. We don't put these into the translation
        # json because they are dynamic options coming from our own constant structure.
        due_date_selector = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    selector.SelectOptionDict(
                        value=v,
                        label=(
                            DUE_DATE_OPTION_LABELS.get(v, {}).get(lang)
                            or DUE_DATE_OPTION_LABELS.get(v, {}).get("en", v)
                        ),
                    )
                    for v in DUE_DATE_OPTIONS
                ],
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        )

        # Base schema (no include toggles yet)
        data_schema = vol.Schema(
            {
                vol.Required(CONF_VIKUNJA_URL, default=""): str,
                vol.Required(CONF_VIKUNJA_API_KEY, default=""): str,
                vol.Required(CONF_OPENAI_API_KEY, default=""): str,
                vol.Required(CONF_VOICE_CORRECTION, default=True): cv.boolean,
                vol.Required(CONF_AUTO_VOICE_LABEL, default=True): cv.boolean,
                vol.Required(CONF_ENABLE_USER_ASSIGN, default=False): cv.boolean,
                vol.Required(CONF_DUE_DATE, default="tomorrow"): due_date_selector,
                vol.Required(CONF_DETAILED_RESPONSE, default=True): cv.boolean,
            }
        )

        if user_input is not None:
            # Strip spaces from API keys and tokens
            user_input[CONF_VIKUNJA_API_KEY] = user_input[CONF_VIKUNJA_API_KEY].strip()
            user_input[CONF_OPENAI_API_KEY] = user_input[CONF_OPENAI_API_KEY].strip()

            base_url = user_input[CONF_VIKUNJA_URL].rstrip("/")
            if not base_url.endswith("/api/v1"):
                api_url = f"{base_url}/api/v1"
            else:
                api_url = base_url

            vikunja_api = VikunjaAPI(api_url, user_input[CONF_VIKUNJA_API_KEY])

            # Test the Vikunja connection
            vikunja_success = await self.hass.async_add_executor_job(
                vikunja_api.test_connection
            )

            if not vikunja_success:
                errors["base"] = "cannot_connect"
            else:
                # Test OpenAI connection
                openai_success = await self._test_openai_connection(
                    user_input[CONF_OPENAI_API_KEY]
                )

                if not openai_success:
                    errors[CONF_OPENAI_API_KEY] = "invalid_openai_key"
                else:
                    # Save the formatted URL
                    user_input[CONF_VIKUNJA_URL] = api_url

                    # Build initial user cache if feature enabled
                    if user_input.get(CONF_ENABLE_USER_ASSIGN):
                        # Reuse shared helper to avoid duplication
                        await self.hass.async_add_executor_job(
                            build_initial_user_cache_sync,
                            self.hass.config.config_dir,
                            api_url,
                            user_input[CONF_VIKUNJA_API_KEY],
                        )

                    # Avoid duplicate entries
                    await self.async_set_unique_id(f"vikunja_{api_url}")
                    self._abort_if_unique_id_configured()

                    # Single step flow now – if detailed response selected we just store the flag.
                    return self.async_create_entry(
                        title=f"Vikunja ({api_url})", data=user_input
                    )

            # If there are errors, update the schema with the user's input as defaults
            data_schema = vol.Schema(
                {
                    vol.Required(
                        CONF_VIKUNJA_URL, default=user_input.get(CONF_VIKUNJA_URL, "")
                    ): str,
                    vol.Required(
                        CONF_VIKUNJA_API_KEY,
                        default=user_input.get(CONF_VIKUNJA_API_KEY, ""),
                    ): str,
                    vol.Required(
                        CONF_OPENAI_API_KEY,
                        default=user_input.get(CONF_OPENAI_API_KEY, ""),
                    ): str,
                    vol.Required(
                        CONF_VOICE_CORRECTION,
                        default=user_input.get(CONF_VOICE_CORRECTION, True),
                    ): cv.boolean,
                    vol.Required(
                        CONF_AUTO_VOICE_LABEL,
                        default=user_input.get(CONF_AUTO_VOICE_LABEL, True),
                    ): cv.boolean,
                    vol.Required(
                        CONF_ENABLE_USER_ASSIGN,
                        default=user_input.get(CONF_ENABLE_USER_ASSIGN, False),
                    ): cv.boolean,
                    vol.Required(
                        CONF_DUE_DATE, default=user_input.get(CONF_DUE_DATE, "tomorrow")
                    ): due_date_selector,
                    vol.Required(
                        CONF_DETAILED_RESPONSE,
                        default=user_input.get(CONF_DETAILED_RESPONSE, True),
                    ): cv.boolean,
                }
            )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_import(self, import_data):
        """Handle import from old domain during migration.

        This is called by async_migrate_old_domain to create new entries
        with the new domain from old domain entries.
        """
        _LOGGER.info("Importing config entry from old domain migration")

        # Avoid duplicate entries - check if entry with same URL already exists
        await self.async_set_unique_id(f"vikunja_{import_data[CONF_VIKUNJA_URL]}")
        self._abort_if_unique_id_configured()

        # Create the entry directly without validation
        # (validation already happened when the old entry was created)
        return self.async_create_entry(
            title=f"Vikunja ({import_data[CONF_VIKUNJA_URL]})",
            data=import_data,
        )

    # Removed second step; kept method slot intentionally deleted.
