"""Shared HTTP plumbing for Gnani APIs (https://api.vachana.ai).

Responsibilities:
  * one httpx client with the X-API-Key-ID header and timeouts,
  * a process-wide concurrency guard (the docs give "Only 1 active request is allowed at a time"
    as an example rate limit, so the default is 1 in-flight request),
  * retry with exponential backoff on 429/500/502/503/504, timeouts and connection errors only,
  * mapping HTTP failures to typed GnaniError subclasses,
  * logging of status, latency and request id only (never keys, audio, text or transcripts).
"""

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

import httpx

from app.config import Settings, get_settings
from app.gnani.errors import (
    GnaniAuthError,
    GnaniBadRequest,
    GnaniCreditError,
    GnaniError,
    GnaniNotConfigured,
    GnaniRateLimited,
    GnaniUnavailable,
)

logger = logging.getLogger("kaamsetu.gnani")

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _extract_error(response: httpx.Response) -> tuple[str | None, str]:
    """Return (gnani_code, message) from any of the three documented error envelopes."""
    try:
        body: Any = response.json()
    except ValueError:
        return None, (response.text[:200] or response.reason_phrase)
    if isinstance(body, dict):
        detail = body.get("detail")
        if isinstance(detail, dict):  # auth / credit / rate-limit envelope
            return detail.get("error_code"), str(detail.get("message", ""))
        if isinstance(detail, list):  # FastAPI-style 422
            return "VALIDATION_ERROR", "; ".join(str(d.get("msg", d)) for d in detail if isinstance(d, dict))
        error = body.get("error")
        if isinstance(error, dict):  # STT envelope
            return error.get("type"), str(error.get("message", ""))
        if "message" in body:  # TTS envelope
            return None, str(body["message"])
    return None, response.reason_phrase


def map_http_error(response: httpx.Response, request_id: str | None) -> GnaniError:
    status = response.status_code
    gnani_code, message = _extract_error(response)
    kw = {"status_code": status, "gnani_code": gnani_code, "request_id": request_id}
    if status in (401, 403):
        return GnaniAuthError(message or "Gnani rejected the API key", **kw)
    if status == 402:
        return GnaniCreditError(message or "Gnani credit exhausted", **kw)
    if status == 429:
        return GnaniRateLimited(message or "Gnani rate limit reached", **kw)
    if 400 <= status < 500:
        return GnaniBadRequest(message or "Gnani rejected the request", **kw)
    return GnaniUnavailable(message or "Gnani service error", **kw)


class GnaniHttp:
    """Thin, retrying, concurrency-limited wrapper around httpx.Client."""

    _shared_semaphores: dict[int, threading.BoundedSemaphore] = {}
    _sem_lock = threading.Lock()

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.settings = settings or get_settings()
        self._transport = transport
        self._sleep = sleep
        self._client: httpx.Client | None = None
        with GnaniHttp._sem_lock:
            size = max(1, self.settings.gnani_max_concurrency)
            # Shared across Prisma and Timbre: the limit is per API key, not per product.
            self._semaphore = GnaniHttp._shared_semaphores.setdefault(size, threading.BoundedSemaphore(size))

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            key = self.settings.gnani_api_key.get_secret_value().strip()
            if not key:
                raise GnaniNotConfigured("GNANI_API_KEY is not set in backend/.env")
            self._client = httpx.Client(
                base_url=self.settings.gnani_api_base_url,
                headers={"X-API-Key-ID": key, "User-Agent": f"KAAMSETU/{self.settings.app_version}"},
                timeout=httpx.Timeout(self.settings.gnani_timeout_seconds, connect=10.0),
                transport=self._transport,
            )
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def request(self, method: str, path: str, *, operation: str, **kwargs: Any) -> httpx.Response:
        """Send a request with retries. Returns a 2xx response or raises GnaniError."""
        client = self.client  # raises GnaniNotConfigured before any network work
        attempts = 1 + max(0, self.settings.gnani_max_retries)
        last_error: GnaniError | None = None

        for attempt in range(1, attempts + 1):
            if not self._semaphore.acquire(timeout=self.settings.gnani_timeout_seconds):
                raise GnaniRateLimited("Speech service is busy with another request; try again")
            started = time.perf_counter()
            try:
                response = client.request(method, path, **kwargs)
            except httpx.TimeoutException:
                last_error = GnaniUnavailable(f"Gnani {operation} timed out")
                status, request_id = None, None
            except httpx.TransportError as exc:
                last_error = GnaniUnavailable(f"Could not reach Gnani ({type(exc).__name__})")
                status, request_id = None, None
            else:
                status = response.status_code
                request_id = response.headers.get("x-api-request-id")
                last_error = None if response.is_success else map_http_error(response, request_id)
            finally:
                self._semaphore.release()

            elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
            logger.info(
                "gnani call",
                extra={"ctx": {"operation": operation, "status": status, "attempt": attempt,
                               "latency_ms": elapsed_ms, "gnani_request_id": request_id,
                               "error": last_error.code if last_error else None}},
            )
            if last_error is None:
                return response
            # Retry only what the docs call retryable: 429/500/502/503/504, plus timeouts and connection failures.
            retryable = status is None or status in RETRYABLE_STATUS
            if not retryable or attempt == attempts:
                raise last_error
            self._sleep(min(4.0, 0.5 * (2 ** (attempt - 1))))  # 0.5s, 1s, 2s ...

        raise last_error or GnaniUnavailable("Gnani request failed")  # pragma: no cover
