"""Typed errors for Gnani API failures.

Each error carries whether it is retryable and the Gnani request id when one is known,
so callers can log and support issues can be traced without logging payloads.
"""


class GnaniError(Exception):
    code = "gnani_error"
    retryable = False

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        gnani_code: str | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.gnani_code = gnani_code
        self.request_id = request_id

    def __str__(self) -> str:
        parts = [self.message]
        if self.status_code:
            parts.append(f"status={self.status_code}")
        if self.gnani_code:
            parts.append(f"gnani_code={self.gnani_code}")
        if self.request_id:
            parts.append(f"request_id={self.request_id}")
        return " | ".join(parts)


class GnaniNotConfigured(GnaniError):
    code = "speech_not_configured"


class GnaniAuthError(GnaniError):
    """401 missing/invalid key or 403 scope not allowed. Operator must fix configuration."""

    code = "speech_auth_failed"


class GnaniCreditError(GnaniError):
    """402 insufficient credit."""

    code = "speech_credit_exhausted"


class GnaniRateLimited(GnaniError):
    code = "speech_rate_limited"
    retryable = True


class GnaniBadRequest(GnaniError):
    """400/422: the request (audio, text, language, voice) was rejected. Not retryable."""

    code = "speech_request_rejected"


class GnaniUnavailable(GnaniError):
    """5xx, timeouts and connection failures."""

    code = "speech_unavailable"
    retryable = True


class GnaniResponseError(GnaniError):
    """A 2xx response that does not match the documented contract."""

    code = "speech_bad_response"
