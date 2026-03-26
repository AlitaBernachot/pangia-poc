import operator
from typing import Annotated, Sequence, TypedDict

from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    """State passed through every node in the LangGraph agent."""

    # `operator.add` means new messages are appended, not replaced
    messages: Annotated[Sequence[BaseMessage], operator.add]
    session_id: str
