"""WFS (Web Feature Service) HTTP helper functions.

Provides raw async functions for interacting with OGC WFS endpoints:
- Fetching and parsing GetCapabilities XML
- Requesting vector features via GetFeature (returns GeoJSON / GML)
- Describing feature type schema via DescribeFeatureType

No LangChain, no JSON serialisation – those concerns belong in the agent tool wrappers.
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx

_TIMEOUT = 30.0
_WFS_NS = {
    "wfs": "http://www.opengis.net/wfs",
    "wfs2": "http://www.opengis.net/wfs/2.0",
    "ows": "http://www.opengis.net/ows/1.1",
    "ows11": "http://www.opengis.net/ows",
}


def _base_url(url: str) -> str:
    """Strip existing query parameters from *url* to obtain the service base URL."""
    from libs.geo_ogc.common import base_url
    return base_url(url)


async def wfs_get_capabilities(url: str) -> dict[str, Any]:
    """Fetch and parse the WFS GetCapabilities document.

    Args:
        url: WFS service endpoint URL.

    Returns:
        A dict with keys:
          - ``service_title``: Human-readable service title (str).
          - ``service_abstract``: Service description (str).
          - ``wfs_version``: WFS version string (str).
          - ``feature_types``: List of feature type dicts (name, title, abstract, bbox, crs).
          - ``raw_xml``: Raw XML string from the server.
    """
    params = {
        "SERVICE": "WFS",
        "REQUEST": "GetCapabilities",
    }
    base = _base_url(url)
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(base, params=params)
        resp.raise_for_status()
        raw_xml = resp.text

    return _parse_wfs_capabilities(raw_xml)


def _parse_wfs_capabilities(raw_xml: str) -> dict[str, Any]:
    """Parse a WFS GetCapabilities XML response."""
    root = ET.fromstring(raw_xml)
    version = root.get("version", "")

    # Service identification
    service_title = ""
    service_abstract = ""
    for si_tag in (
        "ServiceIdentification",
        "ows:ServiceIdentification",
        "Service",
        "wfs:Service",
    ):
        ns = _WFS_NS if ":" in si_tag else {}
        si_el = root.find(si_tag, ns)
        if si_el is not None:
            for t_tag in ("Title", "ows:Title"):
                t_el = si_el.find(t_tag, _WFS_NS)
                if t_el is not None and t_el.text:
                    service_title = t_el.text.strip()
                    break
            for a_tag in ("Abstract", "ows:Abstract"):
                a_el = si_el.find(a_tag, _WFS_NS)
                if a_el is not None and a_el.text:
                    service_abstract = a_el.text.strip()
                    break
            break

    # Feature type list – try all namespace variants (WFS 1.x and WFS 2.0)
    feature_types: list[dict[str, Any]] = []
    for ftl_tag in ("FeatureTypeList", "wfs:FeatureTypeList", "wfs2:FeatureTypeList"):
        ns = _WFS_NS if ":" in ftl_tag else {}
        ftl_el = root.find(ftl_tag, ns)
        if ftl_el is not None:
            for ft_tag in ("FeatureType", "wfs:FeatureType", "wfs2:FeatureType"):
                ns2 = _WFS_NS if ":" in ft_tag else {}
                for ft_el in ftl_el.findall(ft_tag, ns2):
                    ft = _parse_feature_type(ft_el)
                    if ft:
                        feature_types.append(ft)
            break

    return {
        "service_title": service_title,
        "service_abstract": service_abstract,
        "wfs_version": version,
        "feature_types": feature_types,
        "raw_xml": raw_xml,
    }


def _parse_feature_type(ft_el: ET.Element) -> dict[str, Any] | None:
    """Extract metadata from a single WFS FeatureType XML element."""
    name_el = ft_el.find("Name")
    if name_el is None:
        name_el = ft_el.find("wfs:Name", _WFS_NS)
    if name_el is None:
        name_el = ft_el.find("wfs2:Name", _WFS_NS)
    title_el = ft_el.find("Title")
    if title_el is None:
        title_el = ft_el.find("wfs:Title", _WFS_NS)
    if title_el is None:
        title_el = ft_el.find("wfs2:Title", _WFS_NS)
    abstract_el = ft_el.find("Abstract")
    if abstract_el is None:
        abstract_el = ft_el.find("wfs:Abstract", _WFS_NS)
    if abstract_el is None:
        abstract_el = ft_el.find("wfs2:Abstract", _WFS_NS)

    name = (name_el.text or "").strip() if name_el is not None else ""
    if not name:
        return None

    title = (title_el.text or "").strip() if title_el is not None else ""
    abstract = (abstract_el.text or "").strip() if abstract_el is not None else ""

    # Default CRS
    crs = ""
    for crs_tag in (
        "DefaultCRS", "DefaultSRS",
        "wfs:DefaultCRS", "wfs:DefaultSRS",
        "wfs2:DefaultCRS", "wfs2:DefaultSRS",
    ):
        ns = _WFS_NS if ":" in crs_tag else {}
        crs_el = ft_el.find(crs_tag, ns)
        if crs_el is not None and crs_el.text:
            crs = crs_el.text.strip()
            break

    # Bounding box
    bbox: dict[str, float] | None = None
    for bbox_tag in ("WGS84BoundingBox", "ows:WGS84BoundingBox"):
        ns = _WFS_NS if ":" in bbox_tag else {}
        bbox_el = ft_el.find(bbox_tag, ns)
        if bbox_el is not None:
            lc_el = bbox_el.find("LowerCorner")
            if lc_el is None:
                lc_el = bbox_el.find("ows:LowerCorner", _WFS_NS)
            uc_el = bbox_el.find("UpperCorner")
            if uc_el is None:
                uc_el = bbox_el.find("ows:UpperCorner", _WFS_NS)
            if lc_el is not None and uc_el is not None and lc_el.text and uc_el.text:
                try:
                    west, south = map(float, lc_el.text.strip().split())
                    east, north = map(float, uc_el.text.strip().split())
                    bbox = {"west": west, "south": south, "east": east, "north": north}
                except (ValueError, AttributeError):
                    pass
            break

    return {"name": name, "title": title, "abstract": abstract, "crs": crs, "bbox": bbox}


async def wfs_get_feature(
    url: str,
    type_name: str,
    bbox: str = "",
    max_features: int = 100,
    output_format: str = "application/json",
    version: str = "2.0.0",
) -> dict[str, Any]:
    """Retrieve features from a WFS layer (GetFeature operation).

    Args:
        url: WFS service endpoint URL.
        type_name: Feature type name to query (e.g. ``"my:Roads"``).
        bbox: Optional bounding box filter as ``"minx,miny,maxx,maxy"``
              or ``"minx,miny,maxx,maxy,CRS"`` for WFS 2.0.
        max_features: Maximum number of features to return.
        output_format: Requested output format.  Defaults to GeoJSON.
        version: WFS protocol version (``"1.0.0"``, ``"1.1.0"``, or ``"2.0.0"``).

    Returns:
        A dict with:
          - ``output_format``: The requested format.
          - ``content``: Raw response text.
          - ``geojson``: Parsed GeoJSON dict if the response was valid GeoJSON,
            otherwise ``None``.
          - ``feature_count``: Number of features in the GeoJSON response (or ``-1``).
    """
    count_param = "COUNT" if version == "2.0.0" else "MAXFEATURES"
    type_param = "TYPENAMES" if version == "2.0.0" else "TYPENAME"
    params: dict[str, str] = {
        "SERVICE": "WFS",
        "VERSION": version,
        "REQUEST": "GetFeature",
        type_param: type_name,
        count_param: str(max_features),
        "OUTPUTFORMAT": output_format,
    }
    if bbox:
        params["BBOX"] = bbox

    base = _base_url(url)
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(base, params=params)
        resp.raise_for_status()
        content = resp.text

    geojson: dict | None = None
    feature_count = -1
    try:
        geojson = json.loads(content)
        if isinstance(geojson, dict) and geojson.get("type") == "FeatureCollection":
            feature_count = len(geojson.get("features", []))
    except (json.JSONDecodeError, ValueError):
        pass

    return {
        "output_format": output_format,
        "content": content,
        "geojson": geojson,
        "feature_count": feature_count,
        "type_name": type_name,
    }


async def wfs_describe_feature_type(
    url: str,
    type_name: str,
    version: str = "2.0.0",
) -> dict[str, Any]:
    """Retrieve the schema for a WFS feature type (DescribeFeatureType operation).

    Args:
        url: WFS service endpoint URL.
        type_name: Feature type name to describe.
        version: WFS protocol version.

    Returns:
        A dict with:
          - ``content``: Raw XSD/XML schema text returned by the server.
          - ``type_name``: The queried feature type name.
    """
    type_param = "TYPENAMES" if version == "2.0.0" else "TYPENAME"
    params = {
        "SERVICE": "WFS",
        "VERSION": version,
        "REQUEST": "DescribeFeatureType",
        type_param: type_name,
        "OUTPUTFORMAT": "application/gml+xml; version=3.2",
    }
    base = _base_url(url)
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(base, params=params)
        resp.raise_for_status()

    return {
        "content": resp.text,
        "type_name": type_name,
    }
