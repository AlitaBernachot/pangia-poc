# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""Follow-up data analysis agent for PangIA V2.

Handles follow-up questions about data already fetched during a previous turn
("combien y en a-t-il à Ingré ?", "parmi ces caméras, lesquelles sont en vue directe ?").

The agent is a normal ``BaseAgent`` registered in the fan-out like any other.
The orchestrator's ``router_node`` routes to it when:
  - ``context["intent"]["is_followup"]`` is True, AND
  - ``context["previous_sub_results"]`` is non-empty.

This is the **only** place in the codebase that inspects ``tabular_data``
inside ``previous_sub_results``.  The orchestrator itself is agnostic of
sub_result internals.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.models import AgentInput, AgentOutput
from app.pangiagent.agents.base_agents.base_agent import BaseAgent
from app.pangiagent.model_config import build_llm, get_agent_model_config

logger = logging.getLogger(__name__)

_MAX_ROWS_FOR_LLM = 500

_SYSTEM_PROMPT = (
    "Tu es un analyste de données expert. "
    "L'utilisateur a posé une question de suivi sur des données déjà récupérées. "
    "Tu reçois les données brutes sous forme de liste d'objets JSON et la question. "
    "Analyse les données, filtre, compte ou agrège selon la demande. "
    "Réponds UNIQUEMENT en JSON valide avec ce schéma exactement :\n"
    "{\n"
    '  "answer": "<réponse naturelle en français>",\n'
    '  "columns": ["col1", "col2", ...],\n'
    '  "rows": [[val1, val2, ...], ...],\n'
    '  "total_rows": <int>\n'
    "}\n"
    "Règles STRICTES :\n"
    "- Dans 'rows', inclus UNIQUEMENT les lignes qui correspondent au filtre demandé. "
    "Ne retourne PAS toutes les lignes si un filtre est appliqué.\n"
    "- Si aucune ligne ne correspond au filtre, retourne rows=[] et total_rows=0.\n"
    "- total_rows doit être égal au nombre de lignes dans 'rows'.\n"
    "- answer doit être une phrase complète en français décrivant le résultat filtré.\n"
    "- Ne retourne rien d'autre que ce JSON."
)


class FollowupFilterAgent(BaseAgent):
    """Answers follow-up questions by analysing previously fetched sub_results."""

    name = "followup_filter_agent"

    def __init__(self, **kwargs) -> None:
        super().__init__(name=self.name, **kwargs)

    def get_capabilities(self) -> str:
        return (
            "Analyses previously fetched data to answer follow-up questions: "
            "filter, count, aggregate or search within data already retrieved "
            "in a previous turn. Use ONLY when is_followup=True and previous "
            "data is available in context."
        )

    @staticmethod
    def _extract_tabular_data(sub_results: dict[str, Any]) -> dict[str, Any] | None:
        """Return the first ``tabular_data`` found in any sub_result value."""
        for result in sub_results.values():
            if isinstance(result, dict):
                td = result.get("tabular_data")
                if td and isinstance(td, dict) and (td.get("columns") or td.get("rows")):
                    return td
        return None

    @staticmethod
    def _extract_geojson(sub_results: dict[str, Any]) -> dict[str, Any] | None:
        """Return the first GeoJSON FeatureCollection found in any sub_result value."""
        for result in sub_results.values():
            if isinstance(result, dict):
                gj = result.get("geojson")
                if isinstance(gj, dict) and gj.get("type") == "FeatureCollection":
                    return gj
        return None

    @staticmethod
    def _filter_geojson(
        original_geojson: dict[str, Any],
        filtered_rows: list[list],
        cols: list[str],
    ) -> dict[str, Any] | None:
        """Keep only GeoJSON features whose properties match at least one filtered row.

        Matching strategy: build a set of (col, value) pairs from the filtered rows
        and keep features where ANY unique-looking property value appears in that set.
        """
        if not filtered_rows or not original_geojson.get("features"):
            return None

        # Build a lookup: set of (column_name, str_value) from the filtered rows
        filtered_props: set[tuple[str, str]] = set()
        for row in filtered_rows:
            for col, val in zip(cols, row):
                if val and str(val) not in ("", "None", "null"):
                    filtered_props.add((col.lower(), str(val).strip()))

        kept: list[dict] = []
        for feature in original_geojson["features"]:
            props = feature.get("properties") or {}
            for prop_key, prop_val in props.items():
                if prop_val is None:
                    continue
                if (prop_key.lower(), str(prop_val).strip()) in filtered_props:
                    kept.append(feature)
                    break

        if not kept:
            return None
        return {"type": "FeatureCollection", "features": kept}

    async def _run(self, inp: AgentInput) -> AgentOutput:
        previous_sub_results: dict[str, Any] = inp.context.get("previous_sub_results") or {}
        tabular_data = self._extract_tabular_data(previous_sub_results)

        if not tabular_data:
            logger.info(
                "FollowupFilterAgent: no tabular_data in previous_sub_results %s",
                list(previous_sub_results.keys()),
            )
            return AgentOutput(
                agent_name=self.name,
                answer="Je n'ai pas trouvé de données précédemment récupérées à analyser.",
                confidence=0.0,
                state={},
            )

        cols: list[str] = tabular_data.get("columns") or []
        all_rows: list[list] = tabular_data.get("rows") or []
        total_before = len(all_rows)
        fmt_label = tabular_data.get("format", "data").upper()

        rows_sample = all_rows[:_MAX_ROWS_FOR_LLM]
        data_records = [dict(zip(cols, r)) for r in rows_sample]
        data_json = json.dumps(data_records, ensure_ascii=False, default=str)

        user_prompt = (
            f"Données disponibles ({total_before} enregistrements, format {fmt_label}) :\n"
            f"{data_json}\n\n"
            f"Question de l'utilisateur : {inp.query}"
        )

        cfg = get_agent_model_config(self.name)
        llm = build_llm(cfg)
        response = await llm.ainvoke([
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ])
        raw = response.content if hasattr(response, "content") else str(response)
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
        parsed: dict[str, Any] = json.loads(cleaned)

        answer: str = parsed.get("answer", "")
        result_cols: list[str] = parsed.get("columns") or cols
        result_rows: list[list] = parsed.get("rows") or []
        total_after: int = int(parsed.get("total_rows", len(result_rows)))

        logger.info(
            "FollowupFilterAgent: LLM returned %d/%d rows for %r",
            total_after, total_before, inp.query,
        )

        result_tabular: dict[str, Any] = {
            "columns": result_cols,
            "rows": result_rows,
            "total_rows": total_after,
            "format": fmt_label,
        }

        # Filter the original GeoJSON to only keep features matching the filtered rows
        original_geojson = self._extract_geojson(previous_sub_results)
        filtered_geojson: dict[str, Any] | None = None
        if original_geojson and result_rows:
            filtered_geojson = self._filter_geojson(original_geojson, result_rows, result_cols)
            logger.info(
                "FollowupFilterAgent: filtered GeoJSON %d → %d features",
                len(original_geojson.get("features") or []),
                len((filtered_geojson or {}).get("features") or []),
            )

        extra_state: dict[str, Any] = {
            "tabular_data": result_tabular,
            "output_decision": {
                "needs_map": bool(filtered_geojson),
                "needs_dataviz": bool(result_rows),
            },
        }
        if filtered_geojson:
            extra_state["geojson"] = filtered_geojson

        return AgentOutput(
            agent_name=self.name,
            answer=answer,
            confidence=0.95,
            state=extra_state,
        )
