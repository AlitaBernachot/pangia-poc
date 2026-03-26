import operator
from typing import Annotated, Sequence, TypedDict

from langchain_core.messages import BaseMessage


def _merge_dicts(a: dict, b: dict) -> dict:
    """Reducer that merges two dicts – used to accumulate sub-agent results."""
    return {**a, **b}


class AgentState(TypedDict):
    """Shared state threaded through the entire multi-agent graph."""

    # Full conversation history; new messages are *appended* (not replaced)
    messages: Annotated[Sequence[BaseMessage], operator.add]
    session_id: str

    # Set by the router node: which sub-agents should be invoked
    agents_to_call: list[str]

    # Keyed by agent name ("neo4j" | "rdf" | "vector" | "postgis").
    # Results from parallel sub-agent branches are merged via _merge_dicts.
    sub_results: Annotated[dict[str, str], _merge_dicts]
