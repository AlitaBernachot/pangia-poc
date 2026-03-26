"""
Backward-compatibility shim.
The agent graph has been reorganised into master.py (multi-agent architecture).
All imports of `agent_graph` should use `app.agent.master` directly.
"""
from app.agent.master import agent_graph  # noqa: F401
