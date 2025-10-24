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
    Since Home Assistant doesn't support changing a config entry's domain directly,
    we create new entries and remove old ones.
    """
    # Check if there's a config entry with the old domain
    old_entries = [entry for entry in hass.config_entries.async_entries(OLD_DOMAIN)]

    if not old_entries:
        return

    _LOGGER.warning(
        "Found %d config entries with old domain '%s'. " "Migrating to '%s'.",
        len(old_entries),
        OLD_DOMAIN,
        DOMAIN,
    )

    # Migrate each old entry to the new domain
    for old_entry in old_entries:
        # Check if an entry with the new domain already exists with the same URL
        existing_new = [
            entry
            for entry in hass.config_entries.async_entries(DOMAIN)
            if entry.data.get(CONF_VIKUNJA_URL) == old_entry.data.get(CONF_VIKUNJA_URL)
        ]

        if existing_new:
            # New domain entry already exists, just remove the old one
            _LOGGER.info(
                "Entry for '%s' already exists in new domain, removing old entry",
                old_entry.data.get(CONF_VIKUNJA_URL),
            )
            await hass.config_entries.async_remove(old_entry.entry_id)
        else:
            # Create new entry with new domain
            _LOGGER.info(
                "Migrating entry for '%s' from domain '%s' to '%s'",
                old_entry.data.get(CONF_VIKUNJA_URL),
                OLD_DOMAIN,
                DOMAIN,
            )

            # Create the new config entry with the same data but new domain
            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": "import"},
                data=old_entry.data,
            )

            # If successful, remove the old entry
            if result.get("type") == "create_entry":
                await hass.config_entries.async_remove(old_entry.entry_id)
                _LOGGER.info("Successfully migrated entry to new domain")
            else:
                _LOGGER.error(
                    "Failed to migrate entry for '%s': %s",
                    old_entry.data.get(CONF_VIKUNJA_URL),
                    result,
                )

    # Copy runtime data if it exists
    if OLD_DOMAIN in hass.data:
        if DOMAIN not in hass.data:
            hass.data[DOMAIN] = hass.data[OLD_DOMAIN].copy()
            _LOGGER.info(
                "Copied runtime configuration data from old domain to new domain"
            )
        # Clean up old domain data
        hass.data.pop(OLD_DOMAIN, None)


async def async_setup(hass: HomeAssistant, config):
    # Migrate any old domain entries BEFORE initializing new domain
    await async_migrate_old_domain(hass)

    # Now initialize the new domain
    hass.data.setdefault(DOMAIN, {})

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Vikunja from a config entry."""

    # After migration in async_setup, all entries should have the new domain
    # This is just a safety check in case migration didn't run
    if entry.domain == OLD_DOMAIN:
        _LOGGER.error(
            "Config entry is still using old domain '%s'. "
            "Migration should have updated this. Please reload Home Assistant.",
            OLD_DOMAIN,
        )
        # Don't proceed with setup for old domain entries - they should have been migrated
        return False

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
