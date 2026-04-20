# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""
libs/query_expander.py
──────────────────────
Deterministic query expansion for the data.gouv.fr MCP agent.

Instead of embedding a huge synonym table inside the LLM system prompt, this
module performs a lightweight keyword scan on the user query and returns a list
of additional search terms to inject into the HumanMessage.  The LLM then runs
``search_datasets`` for each suggested term (it is already instructed to do so).

Keeping synonyms here (Python dict) rather than in the prompt means:

- The prompt stays short and focused on *behaviour*, not *vocabulary*.
- The synonym table can grow arbitrarily without inflating the token budget.
- Each row is easy to review, test, and extend without touching prompts.
- Other agents can reuse ``expand_query`` by importing this module.

Usage
-----
    from libs.query_expander import expand_query, strip_action_prefix

    extra = expand_query("quelle station essence est la moins chère ?")
    # → ["prix des carburants"]

    clean = strip_action_prefix("Affiche moi le prix des carburants en France")
    # → "prix des carburants en France"
"""
from __future__ import annotations

import re

# ─── Action prefix stripping ──────────────────────────────────────────────────
# Strips common French conversational action verbs from the start of a query
# so that the remainder can be used directly as a search keyword string.
# e.g. "Affiche moi le prix des carburants en France" → "prix des carburants en France"

_ACTION_PREFIX_RE = re.compile(
    r'^(?:'
    r'(?:affich|montr|donn|list|trouv|cherch)e(?:-moi)?'
    r'|peux.tu|voudr(?:ais|ait)|je\s+veux|je\s+voudrais'
    r'|peut.on|comment\s+(?:trouver|voir|savoir)'
    r'|quelle?s?\s+(?:sont|est)'
    r')'
    r'\s+(?:moi\s+)?(?:les?\s+|la\s+|le\s+|des?\s+|du\s+)?',
    re.IGNORECASE,
)


def strip_action_prefix(query: str) -> str:
    """Strip common French conversational prefixes for use as a search keyword.

    Examples
    --------
    >>> strip_action_prefix("Affiche moi le prix des carburants en France")
    'prix des carburants en France'
    >>> strip_action_prefix("quels sont les accidents de la route ?")
    'accidents de la route ?'
    """
    return _ACTION_PREFIX_RE.sub('', query).strip()

# ─── Synonym table ─────────────────────────────────────────────────────────────
# Format:
#   trigger_patterns  →  extra search terms
#
# Keys: tuple of regex patterns (case-insensitive, word-boundary aware).
#   A group fires when ANY of its patterns matches the user query.
# Values: list of additional search terms to suggest.
#
# Guidelines:
#   - Keep trigger patterns short and distinctive.
#   - Add new groups for each thematic domain.
#   - Avoid over-matching (e.g. "eau" would match "bureau") — prefer \bword\b.

_SYNONYM_GROUPS: list[tuple[tuple[str, ...], list[str]]] = [
    # ── Fuel / gas stations ────────────────────────────────────────────────────
    # "prix des carburants" = exact canonical dataset name on data.gouv.fr
    (
        (r"\bcarburant", r"\bessence\b", r"\bgazole\b", r"\bdiesel\b",
         r"\bstation.service\b", r"\bstation\s+essence\b"),
        ["prix des carburants"],
    ),
    # ── Cameras / surveillance ────────────────────────────────────────────────
    # Different angles: equipment name vs. usage concept
    (
        (r"\bcam[eé]ra", r"\bwebcam\b", r"\bvidéosurveillance\b", r"\bCCTV\b"),
        ["vidéosurveillance", "caméra voie publique"],
    ),
    # ── Sensors / monitoring ──────────────────────────────────────────────────
    (
        (r"\bcapteur\b", r"\bsonde\b", r"\bmonitoring\b"),
        ["capteurs IoT", "mesure environnementale"],
    ),
    # ── Waste / recycling ─────────────────────────────────────────────────────
    (
        (r"\bdéchett?erie\b", r"\bcollecte\s+déchet", r"\btri\s+sélectif\b"),
        ["déchetterie", "collecte déchets ménagers"],
    ),
    # ── Schools / education ───────────────────────────────────────────────────
    (
        (r"\bécole\b", r"\bcollège\b", r"\blycée\b", r"\bétablissement\s+scolaire\b"),
        ["établissements scolaires", "annuaire éducation nationale"],
    ),
    # ── Parking ───────────────────────────────────────────────────────────────
    (
        (r"\bparking\b", r"\bstationnement\b"),
        ["stationnement", "places de parking"],
    ),
    # ── Cycling ───────────────────────────────────────────────────────────────
    (
        (r"\bvélo\b", r"\bcycliste\b", r"\bpiste\s+cyclable\b", r"\bvoie\s+verte\b"),
        ["pistes cyclables", "aménagements cyclables"],
    ),
    # ── Public transport ──────────────────────────────────────────────────────
    (
        (r"\bbus\b", r"\btransport\s+en\s+commun\b", r"\bligne\s+de\s+bus\b"),
        ["transport en commun", "GTFS horaires"],
    ),
    # ── Flooding / flood risk ─────────────────────────────────────────────────
    (
        (r"\binondation\b", r"\bcrue\b", r"\bPPRi\b", r"\bzone\s+inondable\b"),
        ["zones inondables", "PPRi risque inondation"],
    ),
    # ── Air quality / pollution ───────────────────────────────────────────────
    (
        (r"\bpollution\b", r"\bqualité\s+de\s+l.air\b", r"\bémissions?\b", r"\bpolluant"),
        ["qualité de l'air", "émissions polluants atmosphériques"],
    ),
    # ── Road accidents ────────────────────────────────────────────────────────
    (
        (r"\baccident\b", r"\bcollision\b", r"\baccidentologie\b", r"\bsécurité\s+routière\b"),
        ["accidentologie routière", "base accidents corporels"],
    ),
    # ── Housing / real estate ────────────────────────────────────────────────
    (
        (r"\blogement\b", r"\bhabitation\b", r"\bimmobilier\b", r"\bDVF\b",
         r"\bmutation\s+foncière\b"),
        ["DVF mutations foncières", "parc logements INSEE"],
    ),
    # ── Employment ───────────────────────────────────────────────────────────
    (
        (r"\bemploi\b", r"\bchômage\b", r"\bdemandeur\s+d.emploi\b"),
        ["demandeurs emploi Pôle emploi", "marché du travail INSEE"],
    ),
    # ── Population / demographics ────────────────────────────────────────────
    (
        (r"\bpopulation\b", r"\bhabitant\b", r"\brecensement\b", r"\bdémographie\b"),
        ["recensement INSEE population communale"],
    ),
    # ── Crime / delinquency ──────────────────────────────────────────────────
    (
        (r"\bcrime\b", r"\bdélinquance\b", r"\bviolence\b", r"\binfraction\b"),
        ["statistiques criminalité état 4001"],
    ),
    # ── Forests / green spaces ───────────────────────────────────────────────
    (
        (r"\bforêt\b", r"\barbre\b", r"\bespace\s+vert\b", r"\bcouvert\s+forestier\b"),
        ["patrimoine arboré espaces verts", "forêt ONF"],
    ),
    # ── Water / rivers ───────────────────────────────────────────────────────
    (
        (r"\beau\s+potable\b", r"\brivière\b", r"\bcours\s+d.eau\b", r"\bhydrologie\b",
         r"\bnappe\s+phréatique\b"),
        ["hydrologie cours d'eau", "qualité eau potable"],
    ),
    # ── Health / hospitals ───────────────────────────────────────────────────
    (
        (r"\bhôpital\b", r"\bclinique\b", r"\bsanté\b", r"\bARS\b", r"\bEHPAD\b"),
        ["établissements de santé FINESS", "capacité hospitalière"],
    ),
    # ── Energy / electricity ─────────────────────────────────────────────────
    (
        (r"\bélectricité\b", r"\bénerg(ie|étique)\b", r"\bpanneau\s+solaire\b",
         r"\brenouvelable\b", r"\bEnedis\b"),
        ["consommation énergie Enedis", "production électricité renouvelable"],
    ),
    # ── Agriculture / land use ───────────────────────────────────────────────
    (
        (r"\bagriculture\b", r"\bexploitation\s+agricole\b", r"\bRPG\b", r"\bparcelle\b"),
        ["RPG registre parcellaire graphique", "exploitations agricoles recensement"],
    ),
    # ── Tourism ──────────────────────────────────────────────────────────────
    (
        (r"\btourisme\b", r"\bhébergement\s+touristique\b", r"\bcamping\b", r"\bgîte\b"),
        ["hébergements touristiques capacité", "fréquentation touristique INSEE"],
    ),
]

# Pre-compile all patterns once at import time
_COMPILED: list[tuple[list[re.Pattern], list[str]]] = [
    ([re.compile(p, re.IGNORECASE) for p in patterns], terms)
    for patterns, terms in _SYNONYM_GROUPS
]


def expand_query(query: str) -> list[str]:
    """Return a deduplicated list of additional search terms for *query*.

    Scans the user query against all synonym groups.  For each group whose
    trigger patterns match, the associated search terms are added.

    Returns an empty list when no synonyms apply (query is already specific
    or covers no known domain).

    Parameters
    ----------
    query:
        The raw user message / question.

    Returns
    -------
    list[str]
        Additional search terms to pass to ``search_datasets``.
        May be empty.
    """
    seen: set[str] = set()
    result: list[str] = []
    for patterns, terms in _COMPILED:
        if any(p.search(query) for p in patterns):
            for t in terms:
                if t.lower() not in seen:
                    seen.add(t.lower())
                    result.append(t)
    return result
