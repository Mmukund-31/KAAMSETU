"""Helpers for unit-testing the Gnani adapters with httpx.MockTransport (no network, no credits)."""

from collections.abc import Callable

import httpx
from pydantic import SecretStr

from app.config import Settings, get_settings
from app.gnani.base import GnaniHttp

TEST_KEY = "test-gnani-key-0123456789"

# Captured from a real Prisma v3.0 response on 2026-11-10 (Hinglish demo sentence, language en-IN).
REAL_PRISMA_BODY = {
    "success": True,
    "request_id": "01a1c554-0000-7000-8000-000000000001",
    "transcript": "motor ka pressure abnormal hai, bearing mein vibration aa raha hai, machine number M204 hai, "
                  "production abhi chal raha hai.",
    "model": "prisma-v3.0",
    "processing_time": 0.406,
    "end_to_end_latency": 0.41,
    "detected_language_code": "en-IN",
}


def fake_settings(**overrides) -> Settings:
    base = {"gnani_api_key": SecretStr(TEST_KEY), "gnani_max_retries": 3, "gnani_timeout_seconds": 5.0}
    base.update(overrides)
    return get_settings().model_copy(update=base)


class Recorder:
    """A MockTransport handler that replays queued responses and records requests."""

    def __init__(self, *responses: httpx.Response | Callable[[httpx.Request], httpx.Response] | Exception):
        self.queue = list(responses)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        request.read()
        self.requests.append(request)
        item = self.queue.pop(0) if len(self.queue) > 1 else self.queue[0]
        if isinstance(item, Exception):
            raise item
        return item(request) if callable(item) else item


def make_http(recorder: Recorder, sleeps: list[float] | None = None, **settings_overrides) -> GnaniHttp:
    sleeps = sleeps if sleeps is not None else []
    return GnaniHttp(fake_settings(**settings_overrides), transport=httpx.MockTransport(recorder),
                     sleep=sleeps.append)


def json_response(status: int, body: object, headers: dict | None = None) -> httpx.Response:
    return httpx.Response(status, json=body, headers=headers)
