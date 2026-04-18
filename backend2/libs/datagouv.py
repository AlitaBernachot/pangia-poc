# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""
libs/datagouv.py
────────────────
Non-LLM utilities for the data.gouv.fr MCP agent.

Provides:
- Row-level filtering helpers (``apply_row_filter``, ``normalize_filter_value``)
- MCP search-result parsing (``parse_text_search_results``)
- Dataset candidate extraction from a ReAct message history
  (``extract_dataset_candidates``, ``extract_search_total``)
- Disambiguation helper (``user_identifies_dataset``)
"""
from __future__ import annotations

import ast
import json
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_core.messages import ToolMessage

# ─── Row filtering ────────────────────────────────────────────────────────────

# Common French/English prepositions that prefix status phrases in natural language
# (e.g. "en maintenance" → "maintenance", "en service" → "service").
_FILTER_PREP_RE = re.compile(
    r"^(?:en |de |du |le |la |les |l\u2019|en cours de |hors |sous |avec |dans |au |aux )\s*",
    re.IGNORECASE,
)


def normalize_filter_value(value: str) -> str:
    """Strip leading French/English prepositions from *value*.

    E.g. ``"en maintenance"`` → ``"maintenance"``, ``"hors service"`` → ``"service"``.
    Applied for ``contains``/``not_contains`` so that dataset cell values like
    ``"MAINTENANCE"`` are matched by a user phrase like ``"en maintenance"``.
    """
    return _FILTER_PREP_RE.sub("", value).strip()


def apply_row_filter(
    rows: list[dict],
    columns: list[str],
    filter_column: str,
    filter_value: str,
    filter_op: str,
) -> list[dict]:
    """Filter *rows* by comparing *filter_column* against *filter_value*.

    Column name matching is case-insensitive. Comparison is always done on
    lowercased strings. For ``contains``/``not_contains``, *filter_value* is
    normalised by stripping leading prepositions.

    Supported *filter_op* values: ``"equals"``, ``"not_equals"``,
    ``"contains"``, ``"not_contains"``.
    """
    col_actual = next(
        (c for c in columns if c.lower() == filter_column.lower()),
        filter_column,
    )
    fv = filter_value.lower()
    fv_norm = normalize_filter_value(fv)

    def _match(row: dict) -> bool:
        cell = str(row.get(col_actual, row.get(filter_column, ""))).lower()
        if filter_op == "equals":
            return cell == fv
        if filter_op == "not_equals":
            return cell != fv
        if filter_op == "contains":
            return fv_norm in cell or fv in cell
        if filter_op == "not_contains":
            return fv_norm not in cell and fv not in cell
        return True

    return [r for r in rows if _match(r)]


# ─── Search result parsing ────────────────────────────────────────────────────

_MAX_DESC_LEN = 250
_NUMBERED_RE = re.compile(r"^\s*\d+\.\s+(.+)")
_SEARCH_TOTAL_RE = re.compile(r"Found\s+(\d+)\s+dataset", re.IGNORECASE)
_UUID_RE = re.compile(
    r"\b[0-9a-f]{24}\b"
    r"|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)
_QUOTED_RE = re.compile(r'["\u00ab\u201c\u2018](.*?)["\u00bb\u201d\u2019]')


def parse_text_search_results(text: str) -> list[dict]:
    """Parse the plain-text MCP search result format into candidate dicts.

    Handles blocks like::

        1. Dataset Title
           ID: <uuid>
           Organization: Org Name
           Tags: tag1, tag2
           URL: https://...
    """
    results: list[dict] = []
    current: dict | None = None

    for line in text.splitlines():
        m = _NUMBERED_RE.match(line)
        if m:
            if current is not None:
                results.append(current)
            current = {
                "title": m.group(1).strip(),
                "id": "",
                "organization": "",
                "description": "",
                "url": "",
            }
            continue
        if current is None:
            continue
        s = line.strip()
        if not s:
            continue
        if s.startswith("ID:"):
            current["id"] = s[3:].strip()
        elif s.startswith("Organization:"):
            current["organization"] = s[13:].strip()
        elif s.startswith("URL:"):
            current["url"] = s[4:].strip()
        elif s.startswith("Tags:") and not current["description"]:
            current["description"] = s[5:].strip()

    if current is not None:
        results.append(current)
    return results


def extract_search_total(messages: list, search_ids: set[str]) -> int | None:
    """Extract the total dataset count from MCP ``search_datasets`` responses.

    Looks for the pattern ``"Found N dataset(s)"`` in ``ToolMessage`` content.
    Returns the highest total found (multiple searches), or ``None``.
    """
    total: int | None = None
    for msg in messages:
        # Import here to avoid circular imports at module level
        from langchain_core.messages import ToolMessage as TM
        if not isinstance(msg, TM) or msg.tool_call_id not in search_ids:
            continue
        raw = msg.content
        if isinstance(raw, list):
            texts = [b.get("text", "") for b in raw if isinstance(b, dict) and b.get("type") == "text"]
        elif isinstance(raw, str):
            texts = [raw]
        else:
            continue
        for text in texts:
            for m in _SEARCH_TOTAL_RE.finditer(text):
                n = int(m.group(1))
                if total is None or n > total:
                    total = n
    return total


def extract_dataset_candidates(messages: list, search_ids: set[str]) -> list[dict]:
    """Parse search tool results from a ReAct message history.

    Only inspects ``ToolMessage`` whose ``tool_call_id`` is in *search_ids*
    (i.e. responses to ``search_datasets`` calls).

    Handles three response formats:
    - MCP wrapped text: ``[{"type": "text", "text": "..."}]``
    - data.gouv.fr JSON API: ``{"data": [...], "total": N}`` or bare list
    - Plain text (fallback via :func:`parse_text_search_results`)

    Returns a deduplicated list of dicts with keys:
    ``id``, ``title``, ``description``, ``url``, ``organization``.
    """
    from langchain_core.messages import ToolMessage as TM

    candidates: list[dict] = []
    seen_ids: set[str] = set()

    def _add(ds_id: str, title: str, description: str, url: str, org: str) -> None:
        if not ds_id and not title:
            return
        if ds_id and ds_id in seen_ids:
            return
        if ds_id:
            seen_ids.add(ds_id)
        candidates.append({
            "id": ds_id,
            "title": title or "Untitled Dataset",
            "description": " ".join(description.split())[:_MAX_DESC_LEN],
            "url": url,
            "organization": org,
        })

    for msg in messages:
        if not isinstance(msg, TM) or msg.tool_call_id not in search_ids:
            continue
        raw = msg.content
        if isinstance(raw, list):
            data = raw
        elif not isinstance(raw, str) or not raw.strip():
            continue
        else:
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                try:
                    data = ast.literal_eval(raw)
                except Exception:
                    for ds in parse_text_search_results(raw):
                        _add(ds["id"], ds["title"], ds["description"], ds["url"], ds["organization"])
                    continue

        # MCP text wrapper: [{"type": "text", "text": "..."}]
        if (
            isinstance(data, list)
            and data
            and isinstance(data[0], dict)
            and data[0].get("type") == "text"
        ):
            for block in data:
                text_content = block.get("text", "") if isinstance(block, dict) else ""
                for ds in parse_text_search_results(text_content):
                    _add(ds["id"], ds["title"], ds["description"], ds["url"], ds["organization"])
            continue

        # Standard data.gouv.fr JSON: {"data": [...]} or plain list
        dataset_list: list | None = None
        if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
            dataset_list = data["data"]
        elif isinstance(data, list):
            dataset_list = data

        if not dataset_list:
            continue
        for ds in dataset_list:
            if not isinstance(ds, dict):
                continue
            org = ds.get("organization") or {}
            org_name = org.get("name", "") if isinstance(org, dict) else str(org)
            _add(
                str(ds.get("id", "")),
                str(ds.get("title", "")),
                ds.get("description") or "",
                ds.get("page", ds.get("url", "")),
                org_name,
            )

    return candidates


def user_identifies_dataset(user_query: str, candidates: list[dict]) -> bool:
    """Return ``True`` only if *user_query* unambiguously identifies one candidate.

    Accepted signals:
    - A UUID present in the query that matches the ``id`` of a candidate.
    - A quoted string whose content is character-for-character identical to the
      ``title`` of a candidate.
    """
    candidate_ids = {c.get("id", "").lower() for c in candidates if c.get("id")}
    for uuid in _UUID_RE.findall(user_query):
        if uuid.lower() in candidate_ids:
            return True

    candidate_titles = {c.get("title", "") for c in candidates if c.get("title")}
    for quoted in _QUOTED_RE.findall(user_query):
        if quoted in candidate_titles:
            return True

    return False
