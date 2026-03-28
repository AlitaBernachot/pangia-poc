"""WMTS (Web Map Tile Service) HTTP helper functions.

Provides raw async functions for interacting with OGC WMTS endpoints:
- Fetching and parsing GetCapabilities XML
- Requesting individual tiles via GetTile (KVP encoding)
- Listing available layers and tile matrix sets

No LangChain, no JSON serialisation – those concerns belong in the agent tool wrappers.
"""
from __future__ import annotations

import base64
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx

_TIMEOUT = 30.0
_WMTS_NS = {
    "wmts": "http://www.opengis.net/wmts/1.0",
    "ows": "http://www.opengis.net/ows/1.1",
    "xlink": "http://www.w3.org/1999/xlink",
}


def _base_url(url: str) -> str:
    """Strip existing query parameters from *url* to obtain the service base URL."""
    from libs.geo_ogc.common import base_url
    return base_url(url)


async def wmts_get_capabilities(url: str) -> dict[str, Any]:
    """Fetch and parse the WMTS GetCapabilities document.

    Args:
        url: WMTS service endpoint URL.

    Returns:
        A dict with keys:
          - ``service_title``: Human-readable service title (str).
          - ``service_abstract``: Service description (str).
          - ``layers``: List of layer dicts (identifier, title, abstract, formats,
            tile_matrix_sets, bbox).
          - ``tile_matrix_sets``: List of tile matrix set dicts (identifier, crs).
          - ``raw_xml``: Raw XML string from the server.
    """
    params = {
        "SERVICE": "WMTS",
        "REQUEST": "GetCapabilities",
        "VERSION": "1.0.0",
    }
    base = _base_url(url)
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(base, params=params)
        resp.raise_for_status()
        raw_xml = resp.text

    return _parse_wmts_capabilities(raw_xml)


def _find(element: ET.Element, tag: str) -> ET.Element | None:
    """Try to find *tag* with and without the WMTS / OWS namespace prefix."""
    result = element.find(tag)
    if result is None and ":" not in tag:
        result = element.find(f"wmts:{tag}", _WMTS_NS)
    if result is None and ":" not in tag:
        result = element.find(f"ows:{tag}", _WMTS_NS)
    return result


def _parse_wmts_capabilities(raw_xml: str) -> dict[str, Any]:
    """Parse a WMTS GetCapabilities XML response."""
    root = ET.fromstring(raw_xml)

    # Service identification
    service_title = ""
    service_abstract = ""
    si_el = root.find("ows:ServiceIdentification", _WMTS_NS)
    if si_el is None:
        si_el = root.find("ServiceIdentification")
    if si_el is not None:
        t_el = si_el.find("ows:Title", _WMTS_NS)
        if t_el is None:
            t_el = si_el.find("Title")
        a_el = si_el.find("ows:Abstract", _WMTS_NS)
        if a_el is None:
            a_el = si_el.find("Abstract")
        if t_el is not None and t_el.text:
            service_title = t_el.text.strip()
        if a_el is not None and a_el.text:
            service_abstract = a_el.text.strip()

    # Layers
    layers: list[dict[str, Any]] = []
    contents_el = root.find("wmts:Contents", _WMTS_NS)
    if contents_el is None:
        contents_el = root.find("Contents")
    if contents_el is not None:
        for layer_el in (
            list(contents_el.findall("wmts:Layer", _WMTS_NS))
            + list(contents_el.findall("Layer"))
        ):
            layer = _parse_wmts_layer(layer_el)
            if layer:
                layers.append(layer)

    # Tile matrix sets
    tile_matrix_sets: list[dict[str, Any]] = []
    if contents_el is not None:
        for tms_el in (
            list(contents_el.findall("wmts:TileMatrixSet", _WMTS_NS))
            + list(contents_el.findall("TileMatrixSet"))
        ):
            id_el = tms_el.find("ows:Identifier", _WMTS_NS)
            if id_el is None:
                id_el = tms_el.find("Identifier")
            crs_el = tms_el.find("ows:SupportedCRS", _WMTS_NS)
            if crs_el is None:
                crs_el = tms_el.find("SupportedCRS")
            identifier = (id_el.text or "").strip() if id_el is not None else ""
            crs = (crs_el.text or "").strip() if crs_el is not None else ""
            if identifier:
                tile_matrix_sets.append({"identifier": identifier, "crs": crs})

    return {
        "service_title": service_title,
        "service_abstract": service_abstract,
        "layers": layers,
        "tile_matrix_sets": tile_matrix_sets,
        "raw_xml": raw_xml,
    }


def _parse_wmts_layer(layer_el: ET.Element) -> dict[str, Any] | None:
    """Extract metadata from a single WMTS Layer XML element."""
    id_el = layer_el.find("ows:Identifier", _WMTS_NS)
    if id_el is None:
        id_el = layer_el.find("Identifier")
    title_el = layer_el.find("ows:Title", _WMTS_NS)
    if title_el is None:
        title_el = layer_el.find("Title")
    abstract_el = layer_el.find("ows:Abstract", _WMTS_NS)
    if abstract_el is None:
        abstract_el = layer_el.find("Abstract")

    identifier = (id_el.text or "").strip() if id_el is not None else ""
    if not identifier:
        return None

    title = (title_el.text or "").strip() if title_el is not None else ""
    abstract = (abstract_el.text or "").strip() if abstract_el is not None else ""

    # Supported image formats
    formats: list[str] = [
        (f_el.text or "").strip()
        for f_el in (
            list(layer_el.findall("wmts:Format", _WMTS_NS))
            + list(layer_el.findall("Format"))
        )
        if f_el.text
    ]

    # Tile matrix set links
    tile_matrix_sets: list[str] = []
    for tms_link_el in (
        list(layer_el.findall("wmts:TileMatrixSetLink", _WMTS_NS))
        + list(layer_el.findall("TileMatrixSetLink"))
    ):
        tms_el = tms_link_el.find("wmts:TileMatrixSet", _WMTS_NS)
        if tms_el is None:
            tms_el = tms_link_el.find("TileMatrixSet")
        if tms_el is not None and tms_el.text:
            tile_matrix_sets.append(tms_el.text.strip())

    # Bounding box (WGS84BoundingBox)
    bbox: dict[str, float] | None = None
    bb_el = layer_el.find("ows:WGS84BoundingBox", _WMTS_NS)
    if bb_el is None:
        bb_el = layer_el.find("WGS84BoundingBox")
    if bb_el is not None:
        lc_el = bb_el.find("ows:LowerCorner", _WMTS_NS)
        if lc_el is None:
            lc_el = bb_el.find("LowerCorner")
        uc_el = bb_el.find("ows:UpperCorner", _WMTS_NS)
        if uc_el is None:
            uc_el = bb_el.find("UpperCorner")
        if lc_el is not None and uc_el is not None and lc_el.text and uc_el.text:
            try:
                west, south = map(float, lc_el.text.strip().split())
                east, north = map(float, uc_el.text.strip().split())
                bbox = {"west": west, "south": south, "east": east, "north": north}
            except (ValueError, AttributeError):
                pass

    return {
        "identifier": identifier,
        "title": title,
        "abstract": abstract,
        "formats": formats,
        "tile_matrix_sets": tile_matrix_sets,
        "bbox": bbox,
    }


async def wmts_get_tile(
    url: str,
    layer: str,
    tile_matrix_set: str,
    tile_matrix: str,
    tile_row: int,
    tile_col: int,
    image_format: str = "image/png",
    style: str = "default",
) -> dict[str, Any]:
    """Request a single map tile from a WMTS server (GetTile operation, KVP encoding).

    Args:
        url: WMTS service endpoint URL.
        layer: Layer identifier.
        tile_matrix_set: Tile matrix set identifier (e.g. ``"EPSG:3857"``).
        tile_matrix: Tile matrix (zoom level) identifier (e.g. ``"5"``).
        tile_row: Tile row index.
        tile_col: Tile column index.
        image_format: Tile image MIME type (e.g. ``"image/png"``).
        style: Style identifier (defaults to ``"default"``).

    Returns:
        A dict with:
          - ``image_base64``: Base64-encoded tile image data (str).
          - ``content_type``: MIME type of the returned tile.
          - ``layer``, ``tile_matrix_set``, ``tile_matrix``, ``tile_row``, ``tile_col``.
    """
    params = {
        "SERVICE": "WMTS",
        "VERSION": "1.0.0",
        "REQUEST": "GetTile",
        "LAYER": layer,
        "STYLE": style,
        "TILEMATRIXSET": tile_matrix_set,
        "TILEMATRIX": tile_matrix,
        "TILEROW": str(tile_row),
        "TILECOL": str(tile_col),
        "FORMAT": image_format,
    }
    base = _base_url(url)
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(base, params=params)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", image_format)
        image_b64 = base64.b64encode(resp.content).decode("ascii")

    return {
        "image_base64": image_b64,
        "content_type": content_type,
        "layer": layer,
        "tile_matrix_set": tile_matrix_set,
        "tile_matrix": tile_matrix,
        "tile_row": tile_row,
        "tile_col": tile_col,
    }
