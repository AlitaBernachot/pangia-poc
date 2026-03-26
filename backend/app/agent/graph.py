from langchain_core.messages import AIMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from app.agent.state import AgentState
from app.agent.tools import TOOLS
from app.config import get_settings

SYSTEM_PROMPT = """You are Pangia, an intelligent GeoIA Agent specialising in geographic
and spatial knowledge. You have access to a Neo4j knowledge graph that stores geographic
entities, relationships, and facts.

Use the knowledge graph tools when you need factual or structured geographic information.
Always provide clear, concise answers and cite the source when information comes from the
knowledge graph.
"""


def _build_llm():
    settings = get_settings()
    return ChatOpenAI(
        model=settings.openai_model,
        temperature=settings.openai_temperature,
        api_key=settings.openai_api_key,
        streaming=True,
    ).bind_tools(TOOLS)


def _should_continue(state: AgentState) -> str:
    """Route to tools if the LLM emitted tool calls, otherwise finish."""
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return END


def _call_model(state: AgentState) -> dict:
    """Invoke the LLM with the full conversation history."""
    llm = _build_llm()
    history = list(state["messages"])
    if not history or not isinstance(history[0], SystemMessage):
        history = [SystemMessage(content=SYSTEM_PROMPT)] + history
    response: AIMessage = llm.invoke(history)
    return {"messages": [response]}


def build_graph():
    """Compile and return the LangGraph agent graph."""
    tool_node = ToolNode(TOOLS)

    workflow = StateGraph(AgentState)
    workflow.add_node("agent", _call_model)
    workflow.add_node("tools", tool_node)

    workflow.set_entry_point("agent")
    workflow.add_conditional_edges("agent", _should_continue, {"tools": "tools", END: END})
    workflow.add_edge("tools", "agent")

    return workflow.compile()


# Module-level compiled graph (reused across requests)
agent_graph = build_graph()
