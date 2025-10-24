import logging
import os
from homeassistant.helpers import config_validation as cv
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from .const import (
    DOMAIN,
    OLD_DOMAIN,
    CONF_VIKUNJA_API_KEY,
    CONF_OPENAI_API_KEY,
    CONF_VIKUNJA_URL,
    CONF_DUE_DATE,
    CONF_VOICE_CORRECTION,
    CONF_AUTO_VOICE_LABEL,
    CONF_ENABLE_USER_ASSIGN,
    CONF_DETAILED_RESPONSE,
)
from .services import setup_services
from .user_cache import VikunjaUserCacheManager
from .intents import register_intents

_LOGGER = logging.getLogger(__name__)

# Integration uses config entries only, but hassfest expects a CONFIG_SCHEMA when async_setup exists
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


def copy_custom_sentences(hass: HomeAssistant) -> None:
    """Copy bundled custom sentences into Home Assistant's expected directory.

    Only copies when source exists and when the target file is missing or older.
    """
    source_dir = os.path.join(
        os.path.dirname(os.path.realpath(__file__)), "custom_sentences"
    )
    if not os.path.exists(source_dir):
        return
    target_root = os.path.join(hass.config.config_dir, "custom_sentences")
    os.makedirs(target_root, exist_ok=True)
    for lang in os.listdir(source_dir):
        src_lang = os.path.join(source_dir, lang)
        if not os.path.isdir(src_lang):
            continue
        dst_lang = os.path.join(target_root, lang)
        os.makedirs(dst_lang, exist_ok=True)
        for fname in os.listdir(src_lang):
            if not fname.endswith(".yaml"):
                continue
            src_file = os.path.join(src_lang, fname)
            dst_file = os.path.join(dst_lang, fname)
            if not os.path.exists(dst_file) or os.path.getmtime(
                src_file
            ) > os.path.getmtime(dst_file):
                with open(src_file, "r", encoding="utf-8") as src, open(
                    dst_file, "w", encoding="utf-8"
                ) as dst:
                    dst.write(src.read())


async def async_migrate_old_domain(hass: HomeAssistant) -> None:
    """Migrate config entries from old domain 'vikunja' to new domain 'vikunja_voice_assistant'.

    This ensures users who installed with the old domain name continue to work after update.
    We simply copy data from old domain to new domain storage and let the new domain
    take over.
    """
    # Check if there's a config entry with the old domain
    old_entries = [entry for entry in hass.config_entries.async_entries(OLD_DOMAIN)]

    if not old_entries:
        return

    _LOGGER.warning(
        "Found %d config entries with old domain '%s'. "
        "These will be migrated to '%s'. "
        "You may need to reload the integration after this update.",
        len(old_entries),
        OLD_DOMAIN,
        DOMAIN,
    )

    # Copy data from old domain to new domain in hass.data
    # This allows the integration to work with old config entries
    if OLD_DOMAIN in hass.data and DOMAIN not in hass.data:
        hass.data[DOMAIN] = hass.data[OLD_DOMAIN].copy()
        _LOGGER.info("Copied configuration data from old domain to new domain")


async def async_setup(hass: HomeAssistant, config):
    hass.data.setdefault(DOMAIN, {})

    # Migrate any old domain data
    await async_migrate_old_domain(hass)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Vikunja from a config entry."""

    # Support both old and new domain entries
    # If this is called with an old domain entry, we handle it gracefully
    actual_domain = entry.domain
    if actual_domain == OLD_DOMAIN:
        _LOGGER.warning(
            "Config entry is using old domain '%s'. "
            "Please consider removing and re-adding the integration to use the new domain '%s'.",
            OLD_DOMAIN,
            DOMAIN,
        )

    hass.data[DOMAIN] = {
        CONF_VIKUNJA_URL: entry.data[CONF_VIKUNJA_URL],
        CONF_VIKUNJA_API_KEY: entry.data[CONF_VIKUNJA_API_KEY],
        CONF_OPENAI_API_KEY: entry.data[CONF_OPENAI_API_KEY],
        CONF_DUE_DATE: entry.data[CONF_DUE_DATE],
        CONF_VOICE_CORRECTION: entry.data[CONF_VOICE_CORRECTION],
        CONF_AUTO_VOICE_LABEL: entry.data.get(CONF_AUTO_VOICE_LABEL, True),
        CONF_ENABLE_USER_ASSIGN: entry.data.get(CONF_ENABLE_USER_ASSIGN, False),
        CONF_DETAILED_RESPONSE: entry.data.get(CONF_DETAILED_RESPONSE, True),
    }

    # User cache manager (optional feature)
    user_cache_manager = VikunjaUserCacheManager(hass)
    await user_cache_manager.load()
    if hass.data[DOMAIN].get(CONF_ENABLE_USER_ASSIGN):
        user_cache_manager.schedule_periodic_refresh()
        if not user_cache_manager.data.users:
            hass.async_create_task(user_cache_manager.refresh(force=True))

    # Register intents and services
    register_intents(hass, lambda: user_cache_manager.data.users)
    setup_services(hass)

    # Manual refresh service (only if feature enabled)
    if hass.data[DOMAIN].get(CONF_ENABLE_USER_ASSIGN):

        async def _handle_refresh_users(call):  # noqa: D401
            await user_cache_manager.refresh(force=True)

        hass.services.async_register(
            DOMAIN, "refresh_user_cache", _handle_refresh_users
        )

    # Copy bundled custom sentences (all languages) into HA config dir before reload
    try:
        copy_custom_sentences(hass)
    except Exception as sentence_err:  # noqa: BLE001
        _LOGGER.error("Failed to copy custom sentences: %s", sentence_err)

    # Prompt conversation agent to reload custom sentences / intents
    await hass.services.async_call("conversation", "reload", {})
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry (placeholder for future cleanup)."""
    return True
