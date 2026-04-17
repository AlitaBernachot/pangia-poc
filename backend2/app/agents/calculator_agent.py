# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

import ast
import logging
import operator

from app.base_agent import BaseAgent
from app.models import AgentInput, AgentOutput

logger = logging.getLogger(__name__)

_SAFE_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
}


def _safe_eval(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in _SAFE_OPS:
        return _SAFE_OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _SAFE_OPS:
        return _SAFE_OPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError(f"Unsupported expression node: {type(node)}")


class CalculatorAgent(BaseAgent):
    def __init__(self, **kwargs) -> None:
        super().__init__(name="calculator_agent", **kwargs)

    def get_capabilities(self) -> str:
        return "Evaluates arithmetic expressions (addition, subtraction, multiplication, division, powers)."

    async def _run(self, inp: AgentInput) -> AgentOutput:
        query = inp.query.strip()
        # Extract expression: look for math-like substring
        expr = query
        try:
            tree = ast.parse(expr, mode="eval")
            result = _safe_eval(tree.body)
            return AgentOutput(
                agent_name=self.name,
                answer=f"Result: {result}",
                confidence=1.0,
            )
        except Exception as exc:
            return AgentOutput(
                agent_name=self.name,
                answer=f"Could not evaluate expression: {exc}",
                confidence=0.3,
                error=str(exc),
            )
