# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field


class AgentInput(BaseModel):
    query: str
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    context: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentOutput(BaseModel):
    agent_name: str
    answer: str
    confidence: float = 1.0
    state: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class ExecutionStep(BaseModel):
    agent_name: str
    parallel_group: int = 0  # steps with same group run in parallel


class ExecutionPlan(BaseModel):
    steps: list[ExecutionStep]
    reasoning: str = ""


class HITLRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    original_query: str
    context: dict[str, Any] = Field(default_factory=dict)
    clarifying_questions: list[str]
    status: str = "pending"  # pending | answered | timeout
    clarified_query: str | None = None


class HITLResponse(BaseModel):
    request_id: str
    clarified_query: str


class ChoiceItem(BaseModel):
    """A single selectable option surfaced by an agent that needs user disambiguation."""
    id: str
    title: str
    description: str = ""
    url: str = ""
    organization: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChoiceRequest(BaseModel):
    """Issued by an agent when it needs the user to pick one item from a list."""
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    agent_name: str
    original_query: str
    items: list[ChoiceItem]
    total: int | None = None  # total matching items if list was truncated
    status: str = "pending"   # pending | answered | timeout
    chosen_id: str | None = None
    chosen_query: str | None = None  # query rewritten to target the chosen item


class ChoiceResponse(BaseModel):
    request_id: str
    chosen_id: str
    chosen_query: str


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    selected_sources: list[str] | None = None


class StreamEvent(BaseModel):
    type: str
    data: dict[str, Any] = Field(default_factory=dict)
