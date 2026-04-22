import logging

import requests

from custom_components.vikunja_voice_assistant.api import vikunja_api as vikunja_api_module
from custom_components.vikunja_voice_assistant.api.vikunja_api import VikunjaAPI


class FakeUnauthorizedResponse:
    status_code = 401
    text = (
        '{"code":11,"message":"missing, malformed, expired or otherwise invalid '
        'token provided"}'
    )

    def json(self):
        return {
            "code": 11,
            "message": "missing, malformed, expired or otherwise invalid token provided",
        }

    def raise_for_status(self):
        raise requests.exceptions.HTTPError(response=self)


def _patch_unauthorized_put(monkeypatch):
    def fake_put(*args, **kwargs):
        return FakeUnauthorizedResponse()

    monkeypatch.setattr(vikunja_api_module.requests, "put", fake_put)


def test_add_label_to_task_logs_scoped_token_hint(monkeypatch, caplog):
    api = VikunjaAPI("https://example.com/api/v1", "token")
    _patch_unauthorized_put(monkeypatch)

    with caplog.at_level(logging.ERROR):
        ok = api.add_label_to_task(4366, 44)

    assert ok is False
    assert "If you're using a scoped API token" in caplog.text
    assert "task-update scope in addition to label read/create permissions" in caplog.text


def test_assign_user_to_task_logs_scoped_token_hint(monkeypatch, caplog):
    api = VikunjaAPI("https://example.com/api/v1", "token")
    _patch_unauthorized_put(monkeypatch)

    with caplog.at_level(logging.ERROR):
        ok = api.assign_user_to_task(4366, 44)

    assert ok is False
    assert "If you're using a scoped API token" in caplog.text
    assert "assignee updates may require their own scoped permission" in caplog.text