import asyncio
import pytest

from custom_components.vikunja_voice_assistant.task_handler import process_task
from custom_components.vikunja_voice_assistant.const import (
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
import custom_components.vikunja_voice_assistant.task_handler as th_mod


class FakeHass:
    def __init__(self, domain_config):
        self.data = {DOMAIN: domain_config}

    async def async_add_executor_job(self, func, *args, **kwargs):
        if asyncio.iscoroutinefunction(func):
            return await func(*args, **kwargs)
        return func(*args, **kwargs)


class FakeVikunjaAPI:
    def __init__(self, url, key):  # noqa: D401
        self._projects = []
        self._labels = []
        self._label_search_results = {}
        self._tasks_created = []
        self._assignments = []
        self._created_labels = []
        self._attached_labels = []

    def _set_projects(self, projects):
        self._projects = projects

    def _set_labels(self, labels):
        self._labels = labels

    def _set_label_search_result(self, label_name, label):
        self._label_search_results[label_name] = label

    def get_projects(self):
        return self._projects

    def get_labels(self):
        return self._labels

    def get_label_by_title(self, name):
        return self._label_search_results.get(name)

    def create_label(self, name):
        self._created_labels.append(name)
        return {"id": 999, "title": name}

    def add_task(self, task_data):
        task = {"id": 123, **task_data}
        self._tasks_created.append(task)
        return task

    def add_label_to_task(self, task_id, label_id):
        self._attached_labels.append((task_id, label_id))
        return True

    def assign_user_to_task(self, task_id, user_id):
        self._assignments.append((task_id, user_id))
        return True


class FakeLLMAPI:
    """Fake wrapper for the HomeAssistantLLMAPI (or similar) used by task_handler."""

    def __init__(self, *_, **__):
        self._next_response = None

    def set_response(self, task_data):
        # task_handler expects {"task_data": {...}} or None
        self._next_response = {"task_data": task_data} if task_data is not None else None

    async def create_task_from_description(self, *_, **__):
        return self._next_response


@pytest.fixture(autouse=True)
def patch_apis(monkeypatch):
    fake_vikunja = FakeVikunjaAPI("url", "key")
    fake_llm = FakeLLMAPI()
    monkeypatch.setattr(th_mod, "VikunjaAPI", lambda *a, **k: fake_vikunja)
    # Adjust this attribute name to match the actual LLM wrapper used in task_handler
    monkeypatch.setattr(th_mod, "HomeAssistantLLMAPI", lambda *a, **k: fake_llm)
    return fake_vikunja, fake_llm


def base_config(**overrides):
    cfg = {
        CONF_VIKUNJA_URL: "https://example.com/api/v1",
        CONF_VIKUNJA_API_KEY: "vikkey",
        CONF_AI_TASK_ENTITY: "ai_task.vikunja_llm",
        CONF_DUE_DATE: "none",
        CONF_VOICE_CORRECTION: True,
        CONF_AUTO_VOICE_LABEL: False,
        CONF_ENABLE_USER_ASSIGN: False,
        CONF_DETAILED_RESPONSE: True,
    }
    normalized = {}
    for k, v in overrides.items():
        if k.startswith("CONF_") and k in globals():
            const_value = globals()[k]
            normalized[const_value] = v
        else:
            normalized[k] = v
    cfg.update(normalized)
    return cfg


def test_process_task_minimal(patch_apis):
    fake_vikunja, fake_llm = patch_apis
    fake_vikunja._set_projects([])
    fake_vikunja._set_labels([])
    fake_llm.set_response({"title": "Buy milk", "project_id": 1})
    hass = FakeHass(base_config(CONF_DETAILED_RESPONSE=False))
    ok, msg, title = asyncio.run(process_task(hass, "Buy milk", []))
    assert ok is True
    assert title == "Buy milk"
    assert msg == "Successfully added task: Buy milk"


def test_process_task_detailed_with_metadata(patch_apis):
    fake_vikunja, fake_llm = patch_apis
    fake_vikunja._set_projects([{"id": 2, "title": "Home"}])
    fake_vikunja._set_labels([{"id": 9, "title": "errand"}])
    fake_llm.set_response(
        {
            "title": "Buy milk",
            "project_id": 2,
            "due_date": "2099-01-01",
            "priority": 3,
            "repeat_after": 86400,
            "label_ids": [9],
        }
    )
    hass = FakeHass(base_config())
    ok, msg, title = asyncio.run(process_task(hass, "Buy milk for home", []))
    assert ok is True
    assert title == "Buy milk"
    assert "project 'Home'" in msg
    assert "labels:" in msg
    assert "due" in msg
    assert "priority" in msg
    assert "repeats" in msg


def test_process_task_with_assignee(patch_apis):
    fake_vikunja, fake_llm = patch_apis
    fake_vikunja._set_projects([])
    fake_vikunja._set_labels([])
    fake_llm.set_response(
        {"title": "Prepare slides", "project_id": 1, "assignee": "alice"}
    )
    users = [{"id": 7, "username": "alice", "name": "Alice"}]
    hass = FakeHass(base_config(CONF_ENABLE_USER_ASSIGN=True))
    ok, msg, title = asyncio.run(
        process_task(hass, "prepare slides assign to alice", users)
    )
    assert ok is True
    assert "assigned to alice" in msg
    assert fake_vikunja._assignments == [(123, 7)]


def test_process_task_reuses_voice_label_found_by_search(patch_apis):
    fake_vikunja, fake_llm = patch_apis
    fake_vikunja._set_projects([])
    fake_vikunja._set_labels([{"id": 7, "title": "other"}])
    fake_vikunja._set_label_search_result("voice", {"id": 42, "title": "voice"})
    fake_llm.set_response({"title": "Buy milk", "project_id": 1})
    hass = FakeHass(
        base_config(CONF_AUTO_VOICE_LABEL=True, CONF_DETAILED_RESPONSE=False)
    )

    ok, msg, title = asyncio.run(process_task(hass, "Buy milk", []))

    assert ok is True
    assert title == "Buy milk"
    assert msg == "Successfully added task: Buy milk"
    assert fake_vikunja._created_labels == []
    assert fake_vikunja._attached_labels == [(123, 42)]


def test_process_task_llm_failure(patch_apis, monkeypatch):
    fake_vikunja, fake_llm = patch_apis
    # Force LLM pipeline to return None
    fake_llm.set_response(None)
    hass = FakeHass(base_config())
    ok, msg, title = asyncio.run(process_task(hass, "some description", []))
    assert ok is False
    assert "couldn't process" in msg.lower()
    assert title == ""


def test_process_task_missing_title(patch_apis):
    fake_vikunja, fake_llm = patch_apis
    # Provide response missing title (malformed task_data)
    fake_llm.set_response({"project_id": 1})
    hass = FakeHass(base_config())
    ok, msg, title = asyncio.run(process_task(hass, "whatever", []))
    assert ok is False
    assert "couldn't understand" in msg.lower()
    assert title == ""
