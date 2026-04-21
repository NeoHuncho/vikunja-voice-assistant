import logging

import requests

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


def test_add_label_to_task_logs_scoped_token_hint(monkeypatch, caplog):
    api = VikunjaAPI("https://example.com/api/v1", "token")

    def fake_put(*args, **kwargs):
        return FakeUnauthorizedResponse()

    monkeypatch.setattr(requests, "put", fake_put)

    with caplog.at_level(logging.ERROR):
        ok = api.add_label_to_task(4366, 44)

    assert ok is False
    assert "Scoped API tokens were tightened in Vikunja 2.3.0" in caplog.text
    assert "task-update scope in addition to label read/create permissions" in caplog.text