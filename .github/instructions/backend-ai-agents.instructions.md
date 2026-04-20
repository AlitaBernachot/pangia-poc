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

## Inheritance

Every new sub-agent that participates in the orchestrator fan-out **must** inherit from `BaseAgent`:

```python
from app.pangiagent.agents.base_agent import BaseAgent
```

`BaseAgent` provides:
- Pre- and post-guardrail hook execution (via `run()`)
- Timing (`duration_ms` written to `output.state`)
- Uniform error handling and logging
- System prompt loading from `config/prompts/<agent_name>.yaml` (via `get_prompt(default)`)

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
