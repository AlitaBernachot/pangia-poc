# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""data.gouv.fr MCP agent — queries the French open-data catalogue via MCP."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_mcp_adapters.client import MultiServerMCPClient

from app.config import get_settings
from app.models import AgentInput, AgentOutput, ChoiceItem
from app.pangiagent.agents.base_add_sources_agent import BaseAddSourcesAgent
from app.pangiagent.agents.base_react_agent import BaseReActAgent
from app.pangiagent.model_config import build_llm, get_agent_model_config
from libs.filereader import fetch_and_parse
from libs.datagouv import (
    apply_row_filter,
    normalize_filter_value,
    extract_dataset_candidates,
    extract_search_total,
    user_identifies_dataset,
)
from libs.similarity import rank_by_similarity
from libs.query_expander import expand_query, strip_action_prefix

logger = logging.getLogger(__name__)

# ─── System prompt ────────────────────────────────────────────────────────────

_DEFAULT_PROMPT = """You are the data.gouv.fr Open-Data Agent of the PangIA GeoIA platform.
Your job is to answer questions by querying the French government's open-data catalogue
(data.gouv.fr) through its MCP interface.

## Capabilities
You have access to:
- MCP tools from the data.gouv.fr server: search datasets, retrieve metadata, query tabular
  data via `query_resource_data`, get resource info via `get_resource_info`.
- A local tool `fetch_resource_file` that downloads and parses the **complete raw file**
  (CSV, JSON, GeoJSON) from a direct URL and returns all rows.

## Search rules
- Always call `search_datasets` with `page_size=10` (never less) to get enough results.
- If the first search returns no useful result, retry with broader or translated keywords.


- The MCP response includes the **total number of matching datasets** (e.g. "Found 2788 dataset(s)").
  If the total exceeds 50, **do not attempt to browse further pages**. Instead, stop and reply
  to the user with a message like:

  "Votre recherche a retourné **N datasets** au total — trop pour être affichés en une seule fois.
  Voici un aperçu des premiers résultats. Pour obtenir des résultats plus pertinents, veuillez
  préciser votre recherche (ex. : sujet exact, organisation, format de fichier, année)."

  Then list the datasets returned on the first page so the user can pick one directly.

## Three modes — choose based on the user's intent

### 0. Disambiguation (PRIORITY RULE — check FIRST before doing anything else)
When a search returns **2 or more datasets with different titles**, apply the following
decision logic **in order**:

**Step A — Auto-select ONLY if one of these two conditions is strictly true:**
1. The user's message contains a dataset UUID that matches a result, OR
2. The user's message contains a string delimited by quotes whose content is
   **character-for-character identical** to one of the result titles.

If condition 1 or 2 is true, silently select that dataset and proceed.

**In all other cases — including unquoted titles, partial names, or keywords —
go to Step B and ask.**

**Step B — Ask the user when no strict match was found.**
If the user's message gives no hint about which dataset to use, stop and ask:

"J'ai trouvé **N datasets** correspondant à votre recherche. Lequel souhaitez-vous utiliser ?

1. **[Titre 1]** — [description courte, max 1 phrase] *(Organisation: [org])*
2. **[Titre 2]** — [description courte, max 1 phrase] *(Organisation: [org])*
...

Veuillez me préciser le numéro ou le titre exact du dataset souhaité."

### 1. Metadata / discovery questions
*"What datasets exist about X?", "Who publishes data on Y?", "Is there open data for Z?"*
→ Search, retrieve dataset metadata, cite title + URL + licence. Stop here.

### 2. Data content questions
*"List the X for year Y", "How many Z?", "Give me the records where …", "Affiche les données"*
→ You MUST fetch the actual data. Choose the right strategy:

#### Strategy A — Preview (user asks for a sample / overview / few examples)
- Use `query_resource_data` with `page_size=20` to show structure.
- **Always state explicitly** it is a preview.

#### Strategy B — Full retrieval (user asks to "display", "show", "give me all the data")
- Use `get_resource_info` on **each resource** of the dataset to inspect available formats.
- For each resource whose URL ends in `.csv`, `.json`, or `.geojson`, call
  `fetch_resource_file` with the confirmed URL.
- **If the dataset exposes BOTH a tabular file (CSV/JSON) AND a GeoJSON file**, call
  `fetch_resource_file` **twice** — once for the tabular file, once for the GeoJSON.
  This is important: **always fetch GeoJSON resources when available** — they will be
  rendered as an interactive map in the UI.
- **Do NOT call `query_resource_data` at all** — the full file supersedes any preview.
- **Do NOT list any rows or examples** in your text response.
- **You MUST end with a short non-empty text message** containing at minimum: dataset
  title, total record count, source URL, and licence.

#### Strategy C — Filtered retrieval (user asks for records matching a condition)
Step 1 — Discover the exact column name (skip if you can guess it).
Common column names: `statut`, `etat`, `état`, `status`, `state`.

Step 2 — Mandatory: fetch the file with filter applied:
- Call `get_resource_info` to obtain the direct download URL.
- Call `fetch_resource_file` with the filter parameters:
  - `filter_column`: column name.
  - `filter_value`: the **bare keyword** — strip any leading article or preposition.
  - `filter_op`: `"contains"` / `"not_contains"` by default; `"equals"` / `"not_equals"`
    ONLY if the user explicitly quoted the exact cell value.

When the intent is ambiguous, default to **Strategy B** (full retrieval).

## Guidelines
- Use the search tools first to identify relevant datasets before fetching details.
- Always cite the dataset title, identifier, and URL in your answer.
- Prefer official government sources when multiple datasets match.
- If no relevant dataset is found, say so clearly and suggest alternative search terms.
- Answer in the same language as the user's question.
- Be concise: answer in the fewest words needed. No preambles, no repetition.
"""

# ─── Local tool ───────────────────────────────────────────────────────────────

@tool
async def fetch_resource_file(
    url: str,
    filter_column: str | None = None,
    filter_value: str | None = None,
    filter_op: str = "contains",
) -> str:
    """Download and parse a complete data file (CSV, JSON, GeoJSON) from a direct URL.

    Returns all rows as a JSON string. Use for full data retrieval instead of
    paginating through query_resource_data.

    Optional filter parameters (applied after download):
    - filter_column: column name to filter on (case-insensitive).
    - filter_value: bare keyword to match — strip leading articles/prepositions.
    - filter_op: "contains" | "not_contains" | "equals" | "not_equals" (default: "contains").
    """
    parsed = await fetch_and_parse(url)
    if parsed.error:
        return f"Error fetching file: {parsed.error}"

    rows = parsed.rows
    raw = parsed.raw

    if filter_column and filter_value is not None:
        rows = apply_row_filter(rows, parsed.columns, filter_column, filter_value, filter_op)
        if parsed.format == "geojson" and isinstance(raw, dict):
            col_actual = next((c for c in parsed.columns if c.lower() == filter_column.lower()), filter_column)
            fv = filter_value.lower()
            fv_norm = normalize_filter_value(fv)
            filtered_features = []
            for feat in raw.get("features", []):
                props = feat.get("properties") or {}
                cell = str(props.get(col_actual, props.get(filter_column, ""))).lower()
                if filter_op == "equals" and cell == fv:
                    filtered_features.append(feat)
                elif filter_op == "not_equals" and cell != fv:
                    filtered_features.append(feat)
                elif filter_op == "contains" and (fv_norm in cell or fv in cell):
                    filtered_features.append(feat)
                elif filter_op == "not_contains" and fv_norm not in cell and fv not in cell:
                    filtered_features.append(feat)
            raw = {**raw, "features": filtered_features}

    payload: dict = {
        "format": parsed.format,
        "total_rows": len(rows),
        "columns": parsed.columns,
        "rows": rows,
    }
    if parsed.format == "geojson" and raw is not None:
        payload["raw"] = raw
    return json.dumps(payload, ensure_ascii=False, default=str)


# ─── Agent class ──────────────────────────────────────────────────────────────

class DataGouvMCPAgent(BaseReActAgent, BaseAddSourcesAgent):
    name = "datagouv_mcp_agent"
    _DEFAULT_PROMPT = _DEFAULT_PROMPT

    def __init__(self, **kwargs) -> None:
        super().__init__(name=self.name, **kwargs)
        self._system_prompt = self.get_prompt(self._DEFAULT_PROMPT)

    def get_capabilities(self) -> str:
        return (
            "French open-data catalogue: searches, retrieves, and displays datasets "
            "from data.gouv.fr via MCP — including tabular data and GeoJSON layers."
        )

    async def _run(self, inp: AgentInput) -> AgentOutput:
        return await self._run_by_action(inp)

    # ── Intent-aware action handlers ──────────────────────────────────────────────

    async def _run_display(self, inp: AgentInput, intent: dict) -> AgentOutput:
        """Full data retrieval: fetch CSV/JSON and GeoJSON when available."""
        parts: list[str] = []
        if intent["filters"]:
            filter_desc = "; ".join(
                f'{f["column"]}={f["value"]} ({f.get("op", "contains")})'
                for f in intent["filters"]
            )
            parts.append(f"[INTENT] applique les filtres : {filter_desc}.")
        if intent["geo_scope"]:
            parts.append(f"[INTENT] geo_scope={intent['geo_scope']!r}")
        if intent.get("needs_map"):
            parts.append(
                "[INTENT] needs_map=true → l'utilisateur veut voir les localisations sur une carte. "
                "Récupère impérativement les ressources GeoJSON ou les colonnes de coordonnées (lat/lon) "
                "disponibles dans ce dataset en plus du fichier CSV."
            )
        return await self._do_react(inp, intent, "\n".join(parts))

    async def _run_filter(self, inp: AgentInput, intent: dict) -> AgentOutput:
        """Filtered data retrieval — applies column filters from the parsed intent."""
        parts: list[str] = []
        if intent["filters"]:
            filter_desc = "; ".join(
                f'{f["column"]}={f["value"]} ({f.get("op", "contains")})'
                for f in intent["filters"]
            )
            parts.append(f"[INTENT] action=filter → applique les filtres : {filter_desc}.")
        if intent["geo_scope"]:
            parts.append(f"[INTENT] geo_scope={intent['geo_scope']!r}")
        return await self._do_react(inp, intent, "\n".join(parts))

    async def _run_search(self, inp: AgentInput, intent: dict) -> AgentOutput:
        """Metadata-only search — does not download data files."""
        parts = [
            "[INTENT] action=search → cherche uniquement les métadonnées, "
            "ne télécharge pas les fichiers.",
        ]
        if intent["geo_scope"]:
            parts.append(f"[INTENT] geo_scope={intent['geo_scope']!r}")
        return await self._do_react(inp, intent, "\n".join(parts))

    async def _run_preview(self, inp: AgentInput, intent: dict) -> AgentOutput:
        """Preview mode — query_resource_data only, no full file download."""
        parts = [
            "[INTENT] action=preview → utilise query_resource_data avec page_size=20 "
            "pour un aperçu, ne télécharge pas le fichier complet.",
        ]
        if intent["geo_scope"]:
            parts.append(f"[INTENT] geo_scope={intent['geo_scope']!r}")
        return await self._do_react(inp, intent, "\n".join(parts))

    async def _run_compare(self, inp: AgentInput, intent: dict) -> AgentOutput:
        """Compare multiple datasets on the same topic."""
        parts = [
            "[INTENT] action=compare → récupère plusieurs datasets sur ce sujet "
            "pour permettre une comparaison.",
        ]
        if intent["geo_scope"]:
            parts.append(f"[INTENT] geo_scope={intent['geo_scope']!r}")
        return await self._do_react(inp, intent, "\n".join(parts))

    # ── Shared ReAct loop ─────────────────────────────────────────────────────

    async def _do_react(
        self,
        inp: AgentInput,
        intent: dict,
        ctx_hint: str = "",
    ) -> AgentOutput:
        settings = get_settings()

        mcp_client = MultiServerMCPClient(
            {
                "data_gouv": {
                    "url": settings.data_gouv_mcp_url,
                    "transport": "streamable_http",
                }
            }
        )
        try:
            mcp_tools = await mcp_client.get_tools()
        except Exception as exc:
            logger.warning("DataGouvMCPAgent: MCP unavailable (%s)", exc)
            return AgentOutput(
                agent_name=self.name,
                answer=(
                    "Le service data.gouv.fr MCP est actuellement inaccessible "
                    f"({settings.data_gouv_mcp_url}). Veuillez réessayer ultérieurement."
                ),
                confidence=0.0,
                error=str(exc),
            )

        all_tools = [*mcp_tools, fetch_resource_file]
        llm = build_llm(get_agent_model_config(self.name)).bind_tools(all_tools)
        tool_map = {t.name: t for t in all_tools}

        _chosen_dataset_id: str | None = inp.context.get("chosen_dataset_id")

        if _chosen_dataset_id:
            human_content = (
                f"{inp.query}\n\n"
                f"[CONTEXTE] L'utilisateur a déjà sélectionné le dataset ID : {_chosen_dataset_id}. "
                "N'appelle PAS search_datasets. Appelle directement list_dataset_resources ou "
                "get_resource_info pour récupérer les ressources de ce dataset, puis "
                "fetch_resource_file pour télécharger le fichier CSV et/ou GeoJSON disponibles."
            )
        elif ctx_hint:
            human_content = inp.query + "\n\n" + ctx_hint
        else:
            human_content = inp.query

        messages: list = [
            SystemMessage(content=self._system_prompt),
            HumanMessage(content=human_content),
        ]

        fetch_payloads: list[dict] = []
        search_call_ids: set[str] = set()
        # URLs confirmed to come from get_resource_info tool responses
        _confirmed_urls: set[str] = set()
        # URLs already processed by fetch_resource_file during the loop
        _fetched_urls: set[str] = set()
        # Map url → format for successfully fetched resources
        _fetched_url_formats: dict[str, str] = {}

        # ── Pre-search via query expansion ────────────────────────────────────
        # Build a single combined search query from:
        #   1. The dataset concept extracted by IntentParserAgent (if available),
        #      or the stripped raw query as fallback.
        #   2. The geographic scope from the intent (appended if not already in concept).
        #   3. Synonym-expanded extra terms from query_expander.
        if not _chosen_dataset_id:
            _extra_terms = expand_query(inp.query)
            search_tool = tool_map.get("search_datasets")
            if search_tool:
                import uuid as _uuid
                # Prefer the parsed concept over the raw query
                _base = intent["dataset_concept"] if intent["dataset_concept"] else strip_action_prefix(inp.query)
                # Append geo scope if not already part of the concept
                if intent["geo_scope"] and intent["geo_scope"].lower() not in _base.lower():
                    _base = f'{_base} {intent["geo_scope"]}'
                _combined_query = (_base + " " + " ".join(_extra_terms)).strip()
                logger.info(
                    "DataGouvMCPAgent: pre-search (combined) → '%s'", _combined_query
                )
                _tid = str(_uuid.uuid4())[:8]
                try:
                    _res = await search_tool.ainvoke({"query": _combined_query, "page_size": 10})
                    _content = _res if isinstance(_res, str) else json.dumps(_res, ensure_ascii=False, default=str)
                except Exception as exc:
                    _content = f"Search error: {exc}"
                _fake_ai = AIMessage(
                    content="",
                    tool_calls=[{"id": _tid, "name": "search_datasets", "args": {}}],
                )
                messages.append(_fake_ai)
                messages.append(ToolMessage(content=_content, tool_call_id=_tid))
                search_call_ids.add(_tid)
                logger.info("DataGouvMCPAgent: pre-search → %d chars", len(_content))

        try:
            for _ in range(self.max_iterations):
                response: AIMessage = await llm.ainvoke(messages)
                messages.append(response)

                if not getattr(response, "tool_calls", None):
                    break

                for tc in response.tool_calls:
                    tc_id: str = tc.get("id") or ""
                    tc_name: str = tc["name"]

                    # ── Runtime guard: block fetch before search ──────────────
                    # Skip the guard when a dataset was already chosen by the user
                    # (recursive call after inline disambiguation) — searching again
                    # would re-trigger the choice panel unnecessarily.
                    if tc_name in ("fetch_resource_file", "get_resource_info", "query_resource_data"):
                        if not search_call_ids and not _chosen_dataset_id:
                            # LLM tried to skip search — force it back on track
                            messages.append(ToolMessage(
                                content=(
                                    "[GUARD] You must call `search_datasets` first before calling "
                                    f"`{tc_name}`. Please search for relevant datasets using the "
                                    "user's query, then use the IDs/URLs returned by the search."
                                ),
                                tool_call_id=tc_id or "guard",
                            ))
                            logger.warning(
                                "DataGouvMCPAgent: blocked %s call before search_datasets",
                                tc_name,
                            )
                            continue

                    # ── Track search call IDs ────────────────────────────────
                    if tc_name == "search_datasets" and tc_id:
                        search_call_ids.add(tc_id)
                    tool_fn = tool_map.get(tc["name"])
                    if tool_fn is None:
                        result: Any = f"Unknown tool: {tc['name']}. Available: {list(tool_map)}"
                    else:
                        try:
                            result = await tool_fn.ainvoke(tc["args"])
                        except Exception as exc:
                            result = f"Tool error: {exc}"

                    tool_content: str = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)

                    # ── Extract confirmed URLs from get_resource_info responses ──
                    # Any URL appearing in a real tool response becomes trusted.
                    # Exclude backslash so JSON-encoded escape sequences (e.g. \n)
                    # don't get appended to the URL.
                    if tc_name == "get_resource_info":
                        for _url in re.findall(r'https?://[^\s\'"<>\\]+', tool_content):
                            _confirmed_urls.add(_url.rstrip(".,)"))

                    # ── Guard: fetch_resource_file must use a confirmed URL ────
                    if tc_name == "fetch_resource_file":
                        req_url: str = (tc.get("args") or {}).get("url", "")
                        if req_url and not any(req_url.startswith(cu) or cu.startswith(req_url) for cu in _confirmed_urls):
                            messages.append(ToolMessage(
                                content=(
                                    f"[GUARD] The URL '{req_url}' was not returned by any "
                                    "`get_resource_info` call in this conversation. "
                                    "Do NOT invent or guess URLs. Call `get_resource_info` "
                                    "with a dataset resource ID to obtain a real download URL first."
                                ),
                                tool_call_id=tc_id or "guard",
                            ))
                            logger.warning(
                                "DataGouvMCPAgent: blocked fetch_resource_file with unconfirmed URL %s",
                                req_url,
                            )
                            continue

                    if tc_name == "fetch_resource_file":
                        req_url_fetched: str = (tc.get("args") or {}).get("url", "")
                        if req_url_fetched:
                            _fetched_urls.add(req_url_fetched)
                        try:
                            parsed_tool = json.loads(tool_content)
                            if isinstance(parsed_tool, dict) and "rows" in parsed_tool:
                                fetch_payloads.append(parsed_tool)
                                fmt = parsed_tool.get("format", "data")
                                total = parsed_tool.get("total_rows", len(parsed_tool["rows"]))
                                cols = parsed_tool.get("columns", [])
                                if req_url_fetched and fmt:
                                    _fetched_url_formats[req_url_fetched] = fmt
                                tool_content = f"[fetch_resource_file OK] format={fmt}, total_rows={total}, columns={cols}"
                        except (json.JSONDecodeError, ValueError):
                            pass

                    messages.append(ToolMessage(content=tool_content, tool_call_id=tc_id))

                    # ── Inline disambiguation after search_datasets ───────────
                    # 1. Extract all candidates from the search response.
                    # 2. Run semantic similarity against the user query —
                    #    if one dataset clearly dominates (high cosine score +
                    #    enough margin over #2) auto-select it without asking.
                    # 3. Otherwise show the ranked list to the user via the
                    #    choice panel (same as before).
                    if tc_name == "search_datasets":
                        _inline_candidates = extract_dataset_candidates(messages, search_call_ids)
                        if (
                            len(_inline_candidates) > 1
                            and not user_identifies_dataset(inp.query, _inline_candidates)
                            and not _chosen_dataset_id
                        ):
                            _inline_total = extract_search_total(messages, search_call_ids)

                            # ── Semantic similarity ranking ───────────────────
                            logger.info(
                                "DataGouvMCPAgent: running similarity on %d candidates for query: %s",
                                len(_inline_candidates),
                                inp.query[:80],
                            )
                            _sim_result = await rank_by_similarity(
                                inp.query,
                                _inline_candidates,
                                text_fields=("title", "description", "tags"),
                            )
                            if _sim_result.auto_selected:
                                # One dataset clearly dominates → auto-select
                                _auto = _sim_result.auto_selected
                                _auto_query = (
                                    f"Je veux travailler avec le dataset : \"{_auto.get('title', '')}\""
                                    + (f" (ID: {_auto['id']})" if _auto.get("id") else "")
                                )
                                logger.info(
                                    "DataGouvMCPAgent: similarity auto-selected '%s' (score=%.3f)",
                                    _auto.get("title", _auto.get("id")),
                                    _auto.get("_score", 0),
                                )
                                return await self._run(AgentInput(
                                    query=_auto_query,
                                    session_id=inp.session_id,
                                    context={**inp.context, "chosen_dataset_id": _auto.get("id", "")},
                                ))

                            # ── Present ranked list to user ───────────────────
                            # Use the similarity-sorted order so the most
                            # relevant dataset appears first in the panel.
                            _ranked_candidates = _sim_result.ranked or _inline_candidates
                            _inline_items = [
                                ChoiceItem(
                                    id=c.get("id", ""),
                                    title=c.get("title", ""),
                                    description=c.get("description", ""),
                                    url=c.get("url", ""),
                                    organization=c.get("organization", ""),
                                )
                                for c in _ranked_candidates
                            ]
                            _inline_result = await self.request_choice(
                                session_id=inp.session_id,
                                original_query=inp.query,
                                items=_inline_items,
                                total=_inline_total,
                            )
                            if not _inline_result.resolved:
                                return AgentOutput(
                                    agent_name=self.name,
                                    answer="La sélection du dataset a expiré. Veuillez reformuler votre requête.",
                                    confidence=0.0,
                                    state={"choice_timeout": True},
                                )
                            # Re-run _run() with the chosen query and the
                            # chosen_dataset_id so the guard and disambiguation
                            # are both skipped in the recursive call.
                            return await self._run(AgentInput(
                                query=_inline_result.chosen_query,
                                session_id=inp.session_id,
                                context={**inp.context, "chosen_dataset_id": _inline_result.chosen_id},
                            ))

        except Exception as exc:
            logger.exception("DataGouvMCPAgent: ReAct loop error")
            return AgentOutput(agent_name=self.name, answer="", confidence=0.0, error=str(exc))

        # ── Auto-fetch GeoJSON URLs not fetched by the LLM ──────────────────────
        # Scan all tool responses for URLs ending in .geojson that were confirmed
        # (appeared in real tool responses) but not explicitly fetched by the LLM.
        # NOTE: tool response text may contain JSON-encoded escape sequences (e.g.
        # literal backslash-n for newlines).  Exclude backslash from the URL pattern
        # so we stop before any such sequence and don't produce malformed URLs.
        _geojson_auto_candidates: list[str] = []
        for msg in messages:
            if isinstance(msg, ToolMessage):
                for _u in re.findall(r'https?://[^\s\'"<>\\]+', msg.content):
                    _u = _u.rstrip(".,)")
                    if (
                        _u.lower().endswith(".geojson")
                        or re.search(r'[?&]format=geojson', _u, re.IGNORECASE)
                        or "/geojson" in _u.lower()
                    ) and _u not in _fetched_urls:
                        _geojson_auto_candidates.append(_u)

        for _gj_url in dict.fromkeys(_geojson_auto_candidates):  # dedupe, preserve order
            try:
                _gj_result = await fetch_resource_file.ainvoke({"url": _gj_url})
                _gj_parsed = json.loads(_gj_result)
                if isinstance(_gj_parsed, dict) and _gj_parsed.get("format") == "geojson" and "rows" in _gj_parsed:
                    fetch_payloads.append(_gj_parsed)
                    _fetched_url_formats[_gj_url] = "geojson"
                    logger.info("DataGouvMCPAgent: auto-fetched GeoJSON from %s", _gj_url)
                    break
            except Exception:
                logger.warning("DataGouvMCPAgent: auto-fetch GeoJSON failed for %s", _gj_url)

        # ── Build result text ─────────────────────────────────────────────────
        result_text = ""
        for msg in reversed(messages):
            if isinstance(msg, AIMessage):
                c = msg.content
                text = c if isinstance(c, str) else " ".join(p.get("text", "") for p in c if isinstance(p, dict))
                text = text.strip()
                if text:
                    result_text = text
                    break

        # ── Separate tabular vs GeoJSON payloads ──────────────────────────────
        tabular_data: dict | None = None
        geojson_data: dict | None = None
        for payload in fetch_payloads:
            fmt = payload.get("format", "")
            if fmt == "geojson":
                if geojson_data is None:
                    geojson_data = payload
            else:
                if tabular_data is None:
                    tabular_data = payload
        if tabular_data is None and geojson_data is not None:
            tabular_data = geojson_data

        if not result_text and tabular_data is not None:
            total = tabular_data.get("total_rows", len(tabular_data["rows"]))
            fmt_label = tabular_data.get("format", "data").upper()
            geo_note = " + GeoJSON" if geojson_data is not None else ""
            result_text = (
                f"Données récupérées depuis data.gouv.fr : {total} enregistrements "
                f"({fmt_label}{geo_note})."
            )
        elif not result_text:
            result_text = "data.gouv.fr agent returned no result."

        # ── Build AgentOutput ─────────────────────────────────────────────────
        extra_state: dict = {}

        # GeoJSON layer
        if geojson_data is not None:
            raw_gj = geojson_data.get("raw")
            if isinstance(raw_gj, dict) and raw_gj.get("type") in ("FeatureCollection", "Feature") and raw_gj.get("features"):
                extra_state["geojson"] = raw_gj

        # Tabular dataviz
        if tabular_data is not None:
            columns = tabular_data["columns"]
            all_rows = tabular_data["rows"]
            total = tabular_data.get("total_rows", len(all_rows))
            fmt_label = tabular_data.get("format", "data").upper()
            if total > 0 and columns and all_rows:
                extra_state["dataviz"] = {
                    "charts": [],
                    "kpis": [],
                    "tables": [{
                        "title": f"Données complètes ({total} enregistrements) [{fmt_label}]",
                        "columns": columns,
                        "rows": [[str(row.get(col, "")) for col in columns] for row in all_rows],
                    }],
                }

        output = AgentOutput(
            agent_name=self.name,
            answer=result_text,
            confidence=0.85,
            state=extra_state,
        )

        # ── Attach structured sources ─────────────────────────────────────────
        self._generate_sources(
            output,
            messages=messages,
            search_call_ids=search_call_ids,
            chosen_dataset_id=_chosen_dataset_id,
            fetched_url_formats=_fetched_url_formats,
        )

        return output

    def _generate_sources(
        self,
        output: AgentOutput,
        *,
        messages: list,
        search_call_ids: set,
        chosen_dataset_id: str | None,
        fetched_url_formats: dict[str, str],
        **_kwargs: Any,
    ) -> None:
        """Populate *output* with dataset and resource sources."""
        # 1. Dataset page (catalogue)
        all_candidates = extract_dataset_candidates(messages, search_call_ids)
        dataset_source: dict | None = None
        if chosen_dataset_id:
            dataset_source = next(
                (c for c in all_candidates if c.get("id") == chosen_dataset_id), None
            )
        if dataset_source is None and all_candidates:
            dataset_source = all_candidates[0]
        if dataset_source and dataset_source.get("title"):
            self.add_source(
                output,
                title=dataset_source["title"],
                url=dataset_source.get("url", ""),
                kind="dataset",
            )

        # 2. Downloaded resources
        for res_url, res_fmt in fetched_url_formats.items():
            self.add_source(
                output,
                title=res_fmt.upper(),
                url=res_url,
                kind="resource",
                fmt=res_fmt.upper(),
            )
