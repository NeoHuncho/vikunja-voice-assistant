from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List

from .const import (
    DOMAIN,
    CONF_VIKUNJA_URL,
    CONF_VIKUNJA_API_KEY,
    CONF_AI_TASK_ENTITY,
    CONF_DUE_DATE,
    CONF_VOICE_CORRECTION,
    CONF_AUTO_VOICE_LABEL,
    CONF_ENABLE_USER_ASSIGN,
    CONF_DETAILED_RESPONSE,
)
from .api.vikunja_api import VikunjaAPI
from .api.homeassistant_llm_api import HomeAssistantLLMAPI
from .helpers.detailed_response_formatter import build_detailed_response
from .helpers.localization import (
    get_language,
    L,
)

_LOGGER = logging.getLogger(__name__)

## NOTE: `_friendly_due_phrase` removed; using `friendly_due_phrase` from response_formatter.


def _append_label_if_missing(labels, label):
    if not isinstance(labels, list) or not isinstance(label, dict):
        return
    label_id = label.get("id")
    if label_id is not None and any(
        isinstance(existing, dict) and existing.get("id") == label_id
        for existing in labels
    ):
        return
    labels.append(label)


def _find_label_by_title(labels, label_name):
    normalized_name = str(label_name or "").strip().casefold()
    for label in labels or []:
        if not isinstance(label, dict):
            continue
        if str(label.get("title") or "").strip().casefold() == normalized_name:
            return label
    return None


async def process_task(
    hass, task_description: str, user_cache_users: List[Dict[str, Any]]
):
    """Create a Vikunja task from natural language description.

    Returns (success, message, task_title)
    """
    domain_config = hass.data.get(DOMAIN, {})
    vikunja_url = domain_config.get(CONF_VIKUNJA_URL)
    vikunja_api_key = domain_config.get(CONF_VIKUNJA_API_KEY)
    ai_task_entity = domain_config.get(CONF_AI_TASK_ENTITY, "")
    default_due_date = domain_config.get(CONF_DUE_DATE, "none")
    voice_correction = domain_config.get(CONF_VOICE_CORRECTION, True)
    auto_voice_label = domain_config.get(CONF_AUTO_VOICE_LABEL, True)
    enable_user_assignment = domain_config.get(CONF_ENABLE_USER_ASSIGN, False)
    detailed_response = domain_config.get(CONF_DETAILED_RESPONSE, True)
    # Granular include flags removed; when detailed_response is true we include all available metadata.
    lang = get_language(hass)
    if not all([vikunja_url, vikunja_api_key, ai_task_entity]):
        _LOGGER.error("Missing configuration for Vikunja voice assistant")
        return False, L("config_error", lang), ""

    vikunja_api = VikunjaAPI(vikunja_url, vikunja_api_key)
    projects, labels = await asyncio.gather(
        hass.async_add_executor_job(vikunja_api.get_projects),
        hass.async_add_executor_job(vikunja_api.get_labels),
    )

    voice_label_id = None
    if auto_voice_label:
        try:
            voice_label = _find_label_by_title(labels, "voice")
            if voice_label is None:
                voice_label = await hass.async_add_executor_job(
                    vikunja_api.get_label_by_title, "voice"
                )
                _append_label_if_missing(labels, voice_label)
            if voice_label:
                voice_label_id = voice_label.get("id")
            if voice_label_id is None:
                voice_label = await hass.async_add_executor_job(
                    vikunja_api.create_label, "voice"
                )
                if voice_label:
                    voice_label_id = voice_label.get("id")
                    _append_label_if_missing(labels, voice_label)
        except Exception as label_err:  # noqa: BLE001
            _LOGGER.error("Could not ensure 'voice' label exists: %s", label_err)

    llm_client = HomeAssistantLLMAPI(hass, ai_task_entity)
    users_for_prompt = user_cache_users if enable_user_assignment else []
    llm_response = await llm_client.create_task_from_description(
        task_description,
        projects,
        labels,
        default_due_date,
        voice_correction,
        users=users_for_prompt,
        enable_user_assignment=enable_user_assignment,
    )
    if not llm_response:
        _LOGGER.error("Failed to process task with Home Assistant LLM")
        return False, L("llm_conn_error", lang), ""
    try:
        task_data = llm_response.get("task_data", {})
        # Some upstream responses in tests wrap the task payload under "task_data" but may
        # produce None instead of an object. Treat that as an LLM processing failure
        # rather than throwing an AttributeError.
        if task_data is None:
            _LOGGER.error("LLM response task_data was None")
            return False, L("llm_process_error", lang), ""
        if not isinstance(task_data, dict):
            _LOGGER.error("LLM response task_data not a dict: %r", type(task_data))
            return False, L("llm_process_error", lang), ""
        if not task_data.get("title"):
            _LOGGER.error("Missing required 'title' field in task data")
            return False, L("llm_missing_title", lang), ""

        extracted_label_ids = []
        if isinstance(task_data, dict) and task_data.get("label_ids"):
            existing_label_ids = {
                label_obj.get("id")
                for label_obj in (labels or [])
                if isinstance(label_obj, dict)
            }
            for lid in task_data.get("label_ids", []):
                if lid in existing_label_ids:
                    extracted_label_ids.append(lid)
            task_data.pop("label_ids", None)

        assignee_username_or_name = task_data.pop("assignee", None)
        result = await hass.async_add_executor_job(
            lambda: vikunja_api.add_task(task_data)
        )
        if result:
            try:
                task_id = result.get("id") if isinstance(result, dict) else None
                if task_id:
                    label_ids_to_attach = list(dict.fromkeys(extracted_label_ids))
                    if (
                        auto_voice_label
                        and voice_label_id
                        and voice_label_id not in label_ids_to_attach
                    ):
                        label_ids_to_attach.append(voice_label_id)
                    for lid in label_ids_to_attach:
                        attach_success = await hass.async_add_executor_job(
                            vikunja_api.add_label_to_task, task_id, lid
                        )
                        if not attach_success:
                            _LOGGER.error(
                                "Failed to attach label %s to task %s", lid, task_id
                            )
                    if enable_user_assignment and assignee_username_or_name:
                        # Late import to avoid circulars
                        lookup = assignee_username_or_name.strip().lower()
                        # user_cache_users already prepared list
                        uid = None
                        for u in user_cache_users:
                            uname = str(u.get("username", "")).lower()
                            name = str(u.get("name", "")).lower()
                            if lookup == uname or lookup == name:
                                uid = u.get("id")
                                break
                        if uid is not None:
                            assign_ok = await hass.async_add_executor_job(
                                vikunja_api.assign_user_to_task, task_id, uid
                            )
                            if not assign_ok:
                                _LOGGER.error(
                                    "Failed to assign user %s to task %s",
                                    lookup,
                                    task_id,
                                )
                        else:
                            _LOGGER.warning(
                                "Assignee '%s' not found in cached users",
                                assignee_username_or_name,
                            )
            except Exception as attach_err:  # noqa: BLE001
                _LOGGER.error("Error attaching labels/assignee to task: %s", attach_err)

        if result:
            task_title = task_data.get("title")
            _LOGGER.info("Created Vikunja task '%s'", task_title)
            # Build response message
            # detailed_response flag determines whether to include metadata in response
            if not detailed_response:
                return True, L("success_added", lang, title=task_title), task_title

            # Build detailed response via helper module
            safe_task_title = task_title or ""
            try:
                detailed_message = build_detailed_response(
                    task_title=safe_task_title,
                    task_data=task_data,
                    projects=projects,
                    labels=labels,
                    extracted_label_ids=extracted_label_ids,
                    assignee_username_or_name=assignee_username_or_name,
                    enable_user_assignment=enable_user_assignment,
                    lang=lang,
                )
            except Exception as format_err:  # noqa: BLE001
                _LOGGER.error("Error building detailed response: %s", format_err)
                return (
                    True,
                    L("success_added", lang, title=safe_task_title),
                    safe_task_title,
                )
            return True, detailed_message, safe_task_title
        _LOGGER.error("Failed to create task in Vikunja")
        return False, L("vikunja_add_error", lang), ""
    except Exception as err:  # noqa: BLE001
        _LOGGER.error("Unexpected error creating task: %s", err)
        return False, L("unexpected_error", lang), ""
