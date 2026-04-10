"""
Backward-compatibility shim.
The agent graph has been reorganised into orchestrator.py (multi-agent architecture).
All imports of `agent_graph` should use `app.agent.orchestrator` directly.
"""
from app.agent.orchestrator import agent_graph  # noqa: F401
