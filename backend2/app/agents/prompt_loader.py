# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""Prompt loader for backend2 agents.

System prompts are stored in ``agents/prompts.yml`` so that they can be
edited without modifying Python source or rebuilding the Docker image.

Usage
-----
    from app.agents.prompt_loader import get_prompt

    class MyAgent(BaseAgent):
        _DEFAULT_PROMPT = "Fallback prompt used when prompts.yml has no entry."

        def __init__(self, **kwargs) -> None:
            super().__init__(name="my_agent", **kwargs)
            self._system_prompt = get_prompt("my_agent", self._DEFAULT_PROMPT)

``get_prompt`` returns the value from ``prompts.yml`` when the key is present,
otherwise it returns *default*.

``load_prompts`` is ``@lru_cache``'d so the YAML file is read exactly once per
process.  Call ``load_prompts.cache_clear()`` in tests that need to inject a
different prompt file.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_PROMPTS_FILE = Path(__file__).parent / "prompts.yml"


@lru_cache(maxsize=1)
def load_prompts() -> dict[str, str]:
    """Load and cache all prompts from ``prompts.yml``.

    Returns an empty dict (and logs a warning) if the file is missing or
    malformed so that agents can fall back to their hardcoded defaults
    without crashing.
    """
    if not _PROMPTS_FILE.exists():
        logger.warning(
            "prompt_loader: %s not found — all agents will use default prompts",
            _PROMPTS_FILE,
        )
        return {}
    try:
        with _PROMPTS_FILE.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        if not isinstance(data, dict):
            raise TypeError(f"Expected a YAML mapping, got {type(data)}")
        logger.debug("prompt_loader: loaded %d prompt(s) from %s", len(data), _PROMPTS_FILE)
        return {k: str(v).strip() for k, v in data.items()}
    except Exception:
        logger.exception("prompt_loader: failed to load %s — using defaults", _PROMPTS_FILE)
        return {}


def get_prompt(agent_name: str, default: str) -> str:
    """Return the system prompt for *agent_name*.

    Parameters
    ----------
    agent_name:
        The agent's ``name`` attribute (e.g. ``"rag_agent"``).
    default:
        Fallback string used when *agent_name* has no entry in ``prompts.yml``.
    """
    return load_prompts().get(agent_name, default)
