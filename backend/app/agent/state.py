import operator
from typing import Annotated, Any, Sequence, TypedDict

from langchain_core.messages import BaseMessage


def _merge_dicts(a: dict, b: dict) -> dict:
    """Reducer that merges two dicts – used to accumulate sub-agent results."""
    return {**a, **b}


class AgentState(TypedDict):
    """Shared state threaded through the entire multi-agent graph."""

    # Full conversation history; new messages are *appended* (not replaced)
    messages: Annotated[Sequence[BaseMessage], operator.add]
    session_id: str

    # Agents explicitly requested by the user.  An empty list means
    # "no preference – let the router decide among all active agents".
    selected_agents: list[str]

    # Set by the router node: which sub-agents should be invoked
    agents_to_call: list[str]

    # Keyed by agent name ("neo4j" | "rdf" | "vector" | "postgis" | "map").
    # Results from parallel sub-agent branches are merged via _merge_dicts.
    sub_results: Annotated[dict[str, str], _merge_dicts]

    # GeoJSON FeatureCollection produced by the map agent (None if not invoked).
    geojson: dict[str, Any] | None

    # Structured visualisation data produced by the dataviz agent (None if not invoked).
    # Contains charts, KPI cards, and/or tables ready for the frontend to render.
    dataviz: dict[str, Any] | None

    # Decision produced by the humanoutput_agent about which visualisation
    # components to render.  Keys: "needs_map" (bool), "needs_dataviz" (bool).
    # None when the humanoutput_agent is disabled or has not run yet.
    output_decision: dict[str, Any] | None
