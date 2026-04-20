# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""
libs/similarity.py
──────────────────
Lightweight semantic-similarity helper for inline dataset disambiguation.

Usage
-----
    from libs.similarity import rank_by_similarity

    result = await rank_by_similarity(
        query="prix des carburants en France",
        candidates=[
            {"id": "abc", "title": "Prix des carburants", "description": "…"},
            {"id": "xyz", "title": "Stations-service", "description": "…"},
        ],
    )
    if result.auto_selected:
        # One candidate clearly dominates — use it without asking the user
        best = result.auto_selected
    else:
        # Present result.ranked to the user so they can pick
        ranked = result.ranked

Model
-----
``paraphrase-multilingual-MiniLM-L12-v2`` (~120 MB) — fast, multilingual,
works well for French queries. Loaded lazily on first call and cached for the
lifetime of the process.

Auto-selection heuristic
------------------------
A candidate is auto-selected when ALL of the following hold:

1. Its cosine similarity score exceeds ``AUTO_SELECT_THRESHOLD`` (default 0.65).
2. Its score is at least ``AUTO_SELECT_MARGIN`` (default 0.15) above the second-best.

If the model fails to load (missing package, network error) the function
returns a ``SimilarityResult`` with ``ranked = candidates`` (unchanged order)
and ``auto_selected = None``, so callers fall back to the regular choice panel.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

# ── Thresholds ────────────────────────────────────────────────────────────────
# Tune these if auto-selection is too aggressive or too conservative.
AUTO_SELECT_THRESHOLD: float = 0.50   # min score for the top candidate
AUTO_SELECT_MARGIN: float = 0.10       # min gap between top and second best
AUTO_SELECT_HIGH_CONFIDENCE: float = 0.75  # score above which margin is ignored

# ── Lazy singleton ────────────────────────────────────────────────────────────
_model = None
_model_load_attempted = False


def _load_model():
    """Return a SentenceTransformer instance, or None if unavailable."""
    global _model, _model_load_attempted  # noqa: PLW0603
    if _model_load_attempted:
        return _model
    _model_load_attempted = True
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore[import]
        _model = SentenceTransformer(_MODEL_NAME)
        logger.info("similarity: model '%s' loaded", _MODEL_NAME)
    except Exception as exc:  # noqa: BLE001
        logger.warning("similarity: could not load model — %s", exc)
        _model = None
    return _model


# ── Public API ─────────────────────────────────────────────────────────────────

@dataclass
class SimilarityResult:
    """Outcome of :func:`rank_by_similarity`."""

    ranked: list[dict] = field(default_factory=list)
    """Candidate dicts sorted by cosine score (descending), each with a
    ``"_score"`` key added.  Equals the original list (unsorted) when the
    model is unavailable."""

    auto_selected: dict | None = None
    """The best candidate when it clearly dominates; ``None`` otherwise."""


async def rank_by_similarity(
    query: str,
    candidates: list[dict],
    *,
    text_fields: tuple[str, ...] = ("title", "description"),
    top_k: int | None = None,
    threshold: float = AUTO_SELECT_THRESHOLD,
    margin: float = AUTO_SELECT_MARGIN,
    high_confidence: float = AUTO_SELECT_HIGH_CONFIDENCE,
) -> SimilarityResult:
    """Rank *candidates* by semantic similarity to *query*.

    Parameters
    ----------
    query:
        The user's natural-language query.
    candidates:
        List of dicts, each representing a dataset.  Each dict must have at
        least a ``"title"`` key; ``"description"`` is also used when present.
    text_fields:
        Keys from each candidate dict to concatenate as the document text.
    top_k:
        If set, return only the *top_k* best candidates.
    threshold:
        Minimum cosine score for the top candidate to be considered for
        auto-selection.
    margin:
        Minimum score gap between the top and second-best candidate required
        for auto-selection.

    Returns
    -------
    SimilarityResult
        ``ranked`` is always populated (may equal the original list when the
        model is unavailable).  ``auto_selected`` is set only when one
        candidate clearly dominates.
    """
    if not candidates:
        return SimilarityResult(ranked=[])

    if len(candidates) == 1:
        return SimilarityResult(ranked=candidates, auto_selected=candidates[0])

    loop = asyncio.get_running_loop()
    try:
        ranked, auto = await loop.run_in_executor(
            None,
            _compute_similarity,
            query,
            candidates,
            text_fields,
            top_k,
            threshold,
            margin,
            high_confidence,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("similarity: ranking failed — %s", exc)
        return SimilarityResult(ranked=candidates, auto_selected=None)

    return SimilarityResult(ranked=ranked, auto_selected=auto)


# ── Internal computation (runs in thread pool) ─────────────────────────────────

def _compute_similarity(
    query: str,
    candidates: list[dict],
    text_fields: tuple[str, ...],
    top_k: int | None,
    threshold: float,
    margin: float,
    high_confidence: float = AUTO_SELECT_HIGH_CONFIDENCE,
) -> tuple[list[dict], dict | None]:
    """Blocking computation — called via run_in_executor."""
    model = _load_model()
    if model is None:
        return candidates, None

    from sentence_transformers import util  # type: ignore[import]

    # Build document strings: concatenate chosen fields for each candidate
    docs = [
        " ".join(str(c.get(f, "")) for f in text_fields if c.get(f))
        for c in candidates
    ]

    q_emb = model.encode(query, convert_to_tensor=True)
    d_embs = model.encode(docs, convert_to_tensor=True)
    scores = util.cos_sim(q_emb, d_embs)[0]  # shape: (n_candidates,)

    ranked_indices = scores.argsort(descending=True).tolist()
    if top_k is not None:
        ranked_indices = ranked_indices[:top_k]

    ranked: list[dict] = []
    for idx in ranked_indices:
        entry = dict(candidates[idx])
        entry["_score"] = round(float(scores[idx]), 4)
        ranked.append(entry)

    # Log scores for all top candidates to help with threshold tuning
    top_n = min(5, len(ranked))
    score_summary = ", ".join(
        f"'{r.get('title', r.get('id', '?'))[:30]}'={r['_score']:.3f}"
        for r in ranked[:top_n]
    )
    logger.info("similarity: top-%d scores: %s", top_n, score_summary)

    # Auto-select heuristic
    auto: dict | None = None
    if len(ranked) >= 2:
        top_score = ranked[0]["_score"]
        second_score = ranked[1]["_score"]
        if top_score >= high_confidence:
            # Very high confidence: auto-select regardless of margin
            auto = ranked[0]
            logger.info(
                "similarity: AUTO-SELECTED '%s' (high-confidence score=%.3f, margin=%.3f)",
                auto.get("title", auto.get("id")),
                top_score,
                top_score - second_score,
            )
        elif top_score >= threshold and (top_score - second_score) >= margin:
            auto = ranked[0]
            logger.info(
                "similarity: AUTO-SELECTED '%s' (score=%.3f, margin=%.3f)",
                auto.get("title", auto.get("id")),
                top_score,
                top_score - second_score,
            )
        else:
            logger.info(
                "similarity: no auto-select (top=%.3f, margin=%.3f, threshold=%.2f, required_margin=%.2f, high_confidence=%.2f)",
                top_score,
                top_score - second_score,
                threshold,
                margin,
                high_confidence,
            )
    elif ranked:
        # Only one candidate after top_k truncation
        if ranked[0]["_score"] >= threshold:
            auto = ranked[0]

    return ranked, auto
