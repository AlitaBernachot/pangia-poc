"""Authentication / authorisation: API-key header check.

When ``GUARDRAIL_AUTH_ENABLED`` is ``true`` the backend requires every request
to carry the header ``X-API-Key`` with a value that matches the configured
``GUARDRAIL_API_KEY`` secret.

The check is intentionally lightweight (constant-time string comparison via
:func:`hmac.compare_digest`) so it cannot leak key length through timing.
"""

import hmac
from dataclasses import dataclass


@dataclass
class AuthResult:
    """Result returned by :func:`check_auth`."""

    blocked: bool
    reason: str | None = None


def check_auth(provided_key: str | None, expected_key: str) -> AuthResult:
    """Verify that *provided_key* matches *expected_key*.

    Uses :func:`hmac.compare_digest` to prevent timing-based side-channel
    attacks.

    Parameters
    ----------
    provided_key:
        The value extracted from the ``X-API-Key`` request header, or
        ``None`` when the header is absent.
    expected_key:
        The secret value configured via ``GUARDRAIL_API_KEY``.
    """
    if not provided_key:
        return AuthResult(
            blocked=True,
            reason="Missing API key. Please provide a valid X-API-Key header.",
        )

    if not hmac.compare_digest(provided_key, expected_key):
        return AuthResult(
            blocked=True,
            reason="Invalid API key. Access denied.",
        )

    return AuthResult(blocked=False)
