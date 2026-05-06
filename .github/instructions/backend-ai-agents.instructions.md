---
# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

description: "Use when creating or modifying agent files in backend-ai/app/pangiagent/agents/. Covers file location, BaseAgent inheritance, naming conventions, registration, and documentation requirements."
applyTo: "backend-ai/app/pangiagent/agents/*.py"
---

# Backend2 Agent Guidelines

## File location

Every agent file **must** be placed in `backend-ai/app/pangiagent/agents/`.
Do not add agent files directly under `backend-ai/app/` or any other directory.

Base classes and mixins live in the `base_agents/` sub-package:
`backend-ai/app/pangiagent/agents/base_agents/`.
Do **not** add new base classes directly in `agents/`.

## Inheritance

### Base class hierarchy

```
object
├── BaseAgent (ABC)              base_agent.py — guardrails, prompt, HITL, intent
│   └── BaseReActAgent           base_react_agent.py — generic ReAct loop
│       ├── DataVizAgent
│       ├── MapVizAgent
│       └── DataGouvMCPAgent ───┐
└── BaseAddSourcesAgent (mixin) ┘ base_add_sources_agent.py
```

### Choosing the right base class

| Your agent does… | Inherit from |
|---|---|
| Simple LLM call, no tools | `BaseAgent` |
| Calls external tools in a ReAct loop | `BaseReActAgent` |
| Exposes structured data sources to the user | add `BaseAddSourcesAgent` as a second base |

**`BaseAgent`** — mandatory base for all fanned-out agents:

```python
from app.pangiagent.agents.base_agents.base_agent import BaseAgent
```

Provides:
- Pre- and post-guardrail hook execution (via `run()`)
- Timing (`duration_ms` written to `output.state`)
- Uniform error handling and logging
- System prompt loading from `config/prompts/<agent_name>.yaml` (via `get_prompt(default)`)

**`BaseReActAgent`** — use instead of `BaseAgent` when your agent needs a tool-calling loop:

```python
from app.pangiagent.agents.base_agents.base_react_agent import BaseReActAgent

class MyAgent(BaseReActAgent):
    ...
```

Provides in addition to `BaseAgent`:
- `_react_loop(messages, llm, tool_map)` — iterates up to `max_iterations`, dispatches tool calls, appends `ToolMessage` results.
- `_invoke_tool(tc, tool_map)` — single-call hook; override for caching, guards, or disambiguation.

**`BaseAddSourcesAgent`** — pure mixin for agents that expose structured sources (`AgentSource`) to the synthesis layer. No `BaseAgent` dependency; combine via multiple inheritance:

```python
from app.pangiagent.agents.base_agents.base_react_agent import BaseReActAgent
from app.pangiagent.agents.base_agents.base_add_sources_agent import BaseAddSourcesAgent

class MyAgent(BaseReActAgent, BaseAddSourcesAgent):
    ...
```

Provides:
- `add_source(output, title, url, kind, fmt)` — deduplicated append.
- `merge_sources(outputs)` — static; orders datasets → resources → other.
- `_generate_sources(output, **context)` — no-op hook; override to populate sources after `_run()`.

**Exception:** Utility agents that are called directly inside a LangGraph node rather than fanned out as independent sub-agents (e.g. `AmbiguityAgent`) do **not** need to inherit from `BaseAgent`. Document this clearly in the module docstring.

## Abstract methods to implement

```python
def get_capabilities(self) -> str:
    """Return a one-sentence description of what this agent can do."""

async def _run(self, inp: AgentInput) -> AgentOutput:
    """Core agent logic — called by BaseAgent.run() after pre-guardrails pass."""
```

Never override `run()` directly — put all logic in `_run()`.

## Naming conventions

| Artifact | Convention | Example |
|---|---|---|
| Class name | `{Name}Agent` (PascalCase) | `SearchAgent` |
| File name | `{name}_agent.py` (snake_case) | `search_agent.py` |
| `name` kwarg passed to `super().__init__()` | `"{name}_agent"` (snake_case string) | `"search_agent"` |
| Registry key in `app/api/routes/chat.py` `_AGENTS` dict | `"{name}_agent"` | `"search_agent"` |

## Constructor pattern

```python
class SearchAgent(BaseAgent):
    _DEFAULT_PROMPT = "You are a helpful search assistant."

    def __init__(self, **kwargs) -> None:
        super().__init__(name="search_agent", **kwargs)
        self._system_prompt = self.get_prompt(self._DEFAULT_PROMPT)
        # other agent-specific initialisation here
```

Pass `**kwargs` through to `super().__init__()` so that `pre_guardrails` and `post_guardrails` can be injected by the caller.

Always define `_DEFAULT_PROMPT` as a class attribute so the hardcoded fallback is visible in source.  `get_prompt()` loads `config/prompts/<agent_name>.yaml` (key `prompt:`) and returns `_DEFAULT_PROMPT` when the file is absent. Create a new `config/prompts/<agent_name>.yaml` file whenever you add a new agent.

## Shared functionality belongs in BaseAgent

If you add a capability that is useful to **every** agent (e.g. LLM client construction helpers, audit logging, retry logic), put it in `BaseAgent` rather than duplicating it across agent files or creating a separate utility module.  `base_agent.py` is the single place where cross-cutting agent concerns live.

Non-`BaseAgent` utility classes (e.g. `AmbiguityAgent`) that need the same helpers may import module-level functions from `base_agent.py` directly.

## Registering the agent

Add the new agent to the `_AGENTS` dict in `backend-ai/app/api/routes/chat.py`:

```python
from app.pangiagent.agents.search_agent import SearchAgent

_AGENTS = {
    ...
    "search_agent": SearchAgent(
        pre_guardrails=[check_toxic_input, check_ambiguous_intent],
        post_guardrails=[check_output_length],
    ),
}
```

The dict key **must** match the `name` attribute passed to `BaseAgent.__init__()`.

## Guardrails

- **Pre-guardrails** receive an `AgentInput` and return `Optional[str]` (a violation message, or `None`).
- **Post-guardrails** receive an `AgentOutput` and return `Optional[str]`.
- Available guardrails live in `backend-ai/app/pangiagent/guardrails.py`.
- A pre-guardrail violation short-circuits execution and returns an `AgentOutput` with `error` set.
- A post-guardrail violation lowers `confidence` by 0.2 and records the violation in `output.state["post_guardrail_violations"]`.

## Documentation

Whenever a new agent is added to `backend-ai/app/pangiagent/agents/`, **always** update `README.md`:
- Add the file to the architecture tree under `agents/`.
- Add a row to the relevant table (Mermaid diagram list, capability descriptions, etc.) if applicable.
- Describe the agent's purpose and any configuration or environment variables it requires.

---

## Architectural rules — separation of concerns

### No hardcoding

Never hardcode agent names, data keys, or routing logic outside of the module that owns them.

- Agent names are defined once as `name = "..."` on the class and nowhere else.
- Routing decisions belong in `router_node` or `_hitl_decision` — not scattered across nodes.
- Data keys like `"tabular_data"`, `"dataviz"`, `"geojson"` are only referenced in the agents that produce or consume them, never in orchestration code.

### Never use regex or keyword lists for linguistic understanding

Any detection that depends on the meaning of natural language — intent classification,
back-reference resolution, follow-up detection, entity extraction — **must** use an LLM.

**Forbidden patterns:**

```python
# BAD — fragile, language-specific, unmaintainable
if re.search(r"\b(parmi|ces|ceux|among)\b", query):
    ...

FOLLOWUP_WORDS = ["parmi", "ces", "ceux", "lesquelles"]
if any(w in query.lower() for w in FOLLOWUP_WORDS):
    ...
```

**Correct approach:** extend or improve the relevant LLM prompt (e.g. `intent_parser_agent.yaml`)
with better instructions, examples, and rules. The system must work in all languages without
hardcoded vocabulary.

This applies everywhere: orchestrator nodes, router, agents, guardrails, utility functions.

### The orchestrator is a traffic controller, not a data inspector

`orchestrator_agent.py` must remain agnostic of what is inside `sub_results`.

**Allowed in the orchestrator:**
- Knowing that `sub_results` is a `dict[str, Any]` and whether it is empty or not.
- Knowing that `context["previous_sub_results"]` exists and is non-empty.
- Knowing that `intent["is_followup"]` is `True` or `False`.

**Forbidden in the orchestrator:**
- Reading or checking any key inside a sub_result value (`tabular_data`, `dataviz`, `geojson`, `ogc_layers`, `rows`, `columns`, …).
- Making routing decisions based on the content of sub_result values.
- Building, transforming, or merging data structures (tables, charts, GeoJSON) directly in a node function.

### Every data domain has a single owner

| Data key | Owner (only this file may read/write it) |
|---|---|
| `tabular_data` | `followup_filter_agent.py`, `datagouv_mcp_agent.py`, `dataviz_agent.py` |
| `dataviz` | `dataviz_agent.py`, `humanoutput_agent.py` (decides), `dataviz_node` (reads for final output) |
| `geojson` / `ogc_layers` | `mapviz_agent.py`, agents that produce geographic output |
| `output_decision` | `humanoutput_agent.py` (writes), `_after_humanoutput` edge (reads) |
| `previous_sub_results` | `memory_node` (writes), `followup_filter_agent.py` (reads) |

### Routing is the router's job

`router_node` is the single place that decides which agents to call. If a special condition requires a different agent (e.g. follow-up queries), implement it as a short-circuit **inside `router_node`**, not as an extra conditional edge from another node.

```python
# CORRECT — short-circuit inside router_node
if intent.get("is_followup") and ctx.get("previous_sub_results"):
    return {"agents_to_call": ["followup_filter_agent"], ...}

# WRONG — adding a new branch in _hitl_decision or build_graph
if previous_turns and has_something:
    return "some_special_node"
```

### Agents communicate through sub_results, not through state keys

An agent must not read another agent's internal state keys directly.
All inter-agent data flows through `sub_results[agent_name][key]`.
The only exceptions are the final output fields (`dataviz`, `geojson`, `ogc_layers`) that the post-processing agents write to top-level state.

