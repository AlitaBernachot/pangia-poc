"""Content filtering: PII detection (regex) and toxicity classification (LLM).

PII detection uses a set of compiled regular-expression patterns to identify
personally identifiable information without any external service call.

Toxicity classification delegates to the configured LLM and is only invoked
when ``GUARDRAIL_TOXICITY_FILTER_ENABLED`` is ``true`` in configuration.
"""

import re
from dataclasses import dataclass, field

from pydantic import BaseModel

# ─── PII regex patterns ────────────────────────────────────────────────────────

_PII_PATTERNS: list[tuple[re.Pattern, str]] = [
    # E-mail addresses
    (re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"), "email"),
    # French phone numbers (local or international prefix)
    (re.compile(r"\b(?:0|\+33\s?|0033\s?)[1-9](?:[\s.\-]?\d{2}){4}\b"), "phone_number"),
    # Generic international phone numbers
    (re.compile(r"\+\d{1,3}[\s\-]?\(?\d{1,4}\)?[\s\-]?\d{3,10}"), "phone_number"),
    # French social security / NIR number (13 digits + 2-digit key)
    (re.compile(r"\b[12]\s?\d{2}\s?\d{2}\s?\d{2}\s?\d{3}\s?\d{3}\s?\d{2}\b"), "ssn"),
    # Credit / debit card numbers (groups of 4 digits)
    (re.compile(r"\b(?:\d{4}[\s\-]?){3}\d{4}\b"), "credit_card"),
    # IBAN
    (re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{4,30}\b"), "iban"),
    # IPv4 addresses – octet-range validated (0-255 per octet)
    (
        re.compile(
            r"\b(?:(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)\.){3}"
            r"(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)\b"
        ),
        "ip_address",
    ),
]


@dataclass
class ContentFilterResult:
    """Result returned by :func:`filter_content`."""

    blocked: bool
    reason: str | None = None
    detected_pii: list[str] = field(default_factory=list)


# ─── PII detection ─────────────────────────────────────────────────────────────


def detect_pii(text: str) -> list[str]:
    """Return a deduplicated list of PII type labels found in *text*."""
    found: list[str] = []
    for pattern, label in _PII_PATTERNS:
        if pattern.search(text) and label not in found:
            found.append(label)
    return found


# ─── Toxicity classification ───────────────────────────────────────────────────


class _ToxicityDecision(BaseModel):
    is_toxic: bool
    reason: str


async def classify_toxicity(text: str, llm) -> tuple[bool, str]:
    """Classify *text* as toxic or not using the provided *llm*.

    Returns a ``(is_toxic, reason)`` tuple.
    """
    structured = llm.with_structured_output(_ToxicityDecision)
    system = (
        "You are a content safety classifier.  Decide whether the following user message "
        "is toxic, hateful, harassing, abusive, or contains harmful content.\n"
        "Output is_toxic=true only for clearly harmful content; be conservative – "
        "geographic, scientific, or analytical questions are never toxic."
    )
    from langchain_core.messages import HumanMessage, SystemMessage

    result: _ToxicityDecision = await structured.ainvoke(
        [SystemMessage(content=system), HumanMessage(content=text)]
    )
    return result.is_toxic, result.reason


# ─── Orchestrator ──────────────────────────────────────────────────────────────


async def filter_content(
    text: str,
    *,
    pii_enabled: bool = True,
    toxicity_enabled: bool = True,
    llm=None,
) -> ContentFilterResult:
    """Run all content-filtering checks and return the first failure (if any).

    Parameters
    ----------
    text:
        The raw user message to inspect.
    pii_enabled:
        When *True* the message is scanned for PII patterns.
    toxicity_enabled:
        When *True* an LLM call classifies the message for toxicity.
        Requires *llm* to be provided.
    llm:
        A LangChain chat-model instance used for the toxicity check.
    """
    if pii_enabled:
        pii_found = detect_pii(text)
        if pii_found:
            types = ", ".join(pii_found)
            return ContentFilterResult(
                blocked=True,
                reason=f"Message contains personally identifiable information ({types}). Please remove sensitive data before sending.",
                detected_pii=pii_found,
            )

    if toxicity_enabled and llm is not None:
        is_toxic, reason = await classify_toxicity(text, llm)
        if is_toxic:
            return ContentFilterResult(
                blocked=True,
                reason=f"Message was flagged as harmful content: {reason}",
            )

    return ContentFilterResult(blocked=False)
