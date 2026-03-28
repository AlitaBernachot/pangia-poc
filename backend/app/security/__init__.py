"""Security module – input guardrails for PangIA GeoIA.

Sub-modules
-----------
content_filter      PII detection (regex) and toxicity classification (LLM).
intent_validator    Malicious-intent detection (LLM).
rate_limiter        Per-session sliding-window rate limiting (Redis).
auth                API-key authentication.
input_guardrail     Orchestrator that wires all checks; exposes the LangGraph node.
"""

from app.security.input_guardrail import GuardrailResult, guardrail_node, blocked_output_node

__all__ = ["GuardrailResult", "guardrail_node", "blocked_output_node"]
