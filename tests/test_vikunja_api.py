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


class FakeLabelResponse:
    def __init__(self, data, total_pages=1):
        self._data = data
        self.headers = {"x-pagination-total-pages": str(total_pages)}
        self.text = ""

    def json(self):
        return self._data

    def raise_for_status(self):
        return None


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


def test_get_labels_fetches_all_pages(monkeypatch):
    api = VikunjaAPI("https://example.com/api/v1", "token")
    calls = []

    def fake_get(*args, **kwargs):
        params = kwargs["params"]
        calls.append(params.copy())
        if params["page"] == 1:
            return FakeLabelResponse([{"id": 1, "title": "first"}], total_pages=2)
        return FakeLabelResponse([{"id": 2, "title": "voice"}], total_pages=2)

    monkeypatch.setattr(vikunja_api_module.requests, "get", fake_get)

    assert api.get_labels() == [
        {"id": 1, "title": "first"},
        {"id": 2, "title": "voice"},
    ]
    assert calls == [
        {"page": 1, "per_page": 100},
        {"page": 2, "per_page": 100},
    ]


def test_get_label_by_title_searches_and_uses_exact_match(monkeypatch):
    api = VikunjaAPI("https://example.com/api/v1", "token")

    def fake_get(*args, **kwargs):
        assert kwargs["params"]["s"] == "voice"
        return FakeLabelResponse(
            [{"id": 1, "title": "voicemail"}, {"id": 2, "title": " Voice "}],
        )

    monkeypatch.setattr(vikunja_api_module.requests, "get", fake_get)

    assert api.get_label_by_title("voice") == {"id": 2, "title": " Voice "}
