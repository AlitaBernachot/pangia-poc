# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""Mixin that adds structured source tracking to an agent.

Usage — combine with any BaseAgent subclass via multiple inheritance::

    class MyAgent(BaseReActAgent, BaseAddSourcesAgent):
        ...

``BaseAddSourcesAgent`` is a pure mixin: it does not inherit from
``BaseAgent`` and carries no ``__init__``.  It relies on ``self.name``
being provided by the other base class in the MRO.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.models import AgentOutput, AgentSource

if TYPE_CHECKING:
    pass


class BaseAddSourcesAgent:
    """Mixin providing source tracking helpers for agents that expose data sources.

    Methods
    -------
    add_source(output, title, url, kind, fmt)
        Append a deduplicated :class:`AgentSource` to *output*.
    merge_sources(outputs) → list[AgentSource]
        Deduplicate and order sources across multiple ``AgentOutput`` objects.
    _generate_sources(output, **context)
        No-op hook — override to populate sources after the core logic.
    """

    # ── Instance helpers ──────────────────────────────────────────────────────

    def add_source(
        self,
        output: AgentOutput,
        title: str,
        url: str = "",
        kind: str = "dataset",
        fmt: str = "",
    ) -> None:
        """Append an :class:`~app.models.AgentSource` to *output*.

        ``agent_name`` is filled automatically from ``self.name``.
        Deduplicates by URL (if non-empty) so the same resource is never
        added twice.

        Parameters
        ----------
        output:
            The :class:`AgentOutput` to attach the source to.
        title:
            Human-readable label (dataset title, resource format label, etc.)
        url:
            Page or download URL.  Leave empty when not applicable.
        kind:
            ``"dataset"`` for a catalogue page link,
            ``"resource"`` for a downloadable file,
            ``"other"`` for anything else.
        fmt:
            File format string (e.g. ``"CSV"``, ``"GeoJSON"``).
            Only relevant when ``kind="resource"``.
        """
        if url and any(s.url == url for s in output.sources):
            return  # deduplicate by URL
        output.sources.append(AgentSource(
            title=title,
            url=url,
            kind=kind,
            format=fmt,
            agent_name=self.name,  # type: ignore[attr-defined]
        ))

    # ── Class-level / static helpers ──────────────────────────────────────────

    @staticmethod
    def merge_sources(outputs: list[AgentOutput]) -> list[AgentSource]:
        """Return a deduplicated, ordered list of all sources across *outputs*.

        Deduplicates by URL (for sourced items) then by title.
        Datasets come before resources in the final list.

        Parameters
        ----------
        outputs:
            Collection of :class:`AgentOutput` objects whose ``.sources``
            fields are merged.
        """
        seen_urls: set[str] = set()
        seen_titles: set[str] = set()
        merged: list[AgentSource] = []
        for kind_filter in ("dataset", "resource", "other"):
            for out in outputs:
                for src in out.sources:
                    if src.kind != kind_filter:
                        continue
                    if src.url and src.url in seen_urls:
                        continue
                    if not src.url and src.title in seen_titles:
                        continue
                    if src.url:
                        seen_urls.add(src.url)
                    seen_titles.add(src.title)
                    merged.append(src)
        return merged

    def _generate_sources(self, output: AgentOutput, **context: Any) -> None:
        """Attach structured sources to *output* after the agent's core logic.

        Override this method to populate ``output.sources`` with
        :class:`~app.models.AgentSource` entries using :meth:`add_source`.
        The default implementation is a no-op.

        Parameters
        ----------
        output:
            The :class:`AgentOutput` being built — mutate it in-place via
            :meth:`add_source`.
        **context:
            Subclass-specific keyword arguments (e.g. ``messages``,
            ``search_call_ids``, ``fetched_url_formats`` for MCP agents).
        """
