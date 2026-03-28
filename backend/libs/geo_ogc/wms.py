"""WMS (Web Map Service) HTTP helper functions.

Provides raw async functions for interacting with OGC WMS endpoints:
- Fetching and parsing GetCapabilities XML
- Requesting map images via GetMap
- Requesting feature information via GetFeatureInfo

No LangChain, no JSON serialisation – those concerns belong in the agent tool wrappers.
"""
from __future__ import annotations

import base64
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx

_TIMEOUT = 30.0
_WMS_NAMESPACES = {
    "wms": "http://www.opengis.net/wms",
    "ows": "http://www.opengis.net/ows/1.1",
    "xlink": "http://www.w3.org/1999/xlink",
}


def _base_url(url: str) -> str:
    """Strip existing query parameters from *url* to obtain the service base URL."""
    from libs.geo_ogc.common import base_url
    return base_url(url)


async def wms_get_capabilities(url: str) -> dict[str, Any]:
    """Fetch and parse the WMS GetCapabilities document.

    Args:
        url: WMS service endpoint URL (with or without existing query params).

    Returns:
        A dict with keys:
          - ``service_title``: Human-readable service title (str).
          - ``service_abstract``: Service description (str).
          - ``wms_version``: WMS version string (str).
          - ``layers``: List of layer dicts (name, title, abstract, bbox, crs).
          - ``raw_xml``: Raw XML string from the server.
    """
    params = {
        "SERVICE": "WMS",
        "REQUEST": "GetCapabilities",
    }
    base = _base_url(url)
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(base, params=params)
        resp.raise_for_status()
        raw_xml = resp.text

    return _parse_wms_capabilities(raw_xml)


def _parse_wms_capabilities(raw_xml: str) -> dict[str, Any]:
    """Parse a WMS GetCapabilities XML response."""
    root = ET.fromstring(raw_xml)
    version = root.get("version", "")

    # Service metadata
    service_title = ""
    service_abstract = ""
    service_el = root.find("Service")
    if service_el is None:
        service_el = root.find("wms:Service", _WMS_NAMESPACES)
    if service_el is not None:
        title_el = service_el.find("Title")
        if title_el is None:
            title_el = service_el.find("wms:Title", _WMS_NAMESPACES)
        abstract_el = service_el.find("Abstract")
        if abstract_el is None:
            abstract_el = service_el.find("wms:Abstract", _WMS_NAMESPACES)
        if title_el is not None:
            service_title = (title_el.text or "").strip()
        if abstract_el is not None:
            service_abstract = (abstract_el.text or "").strip()

    # Layer extraction
    layers: list[dict[str, Any]] = []
    capability_el = root.find("Capability")
    if capability_el is None:
        capability_el = root.find("wms:Capability", _WMS_NAMESPACES)
    if capability_el is not None:
        _extract_wms_layers(capability_el, layers, _WMS_NAMESPACES)

    return {
        "service_title": service_title,
        "service_abstract": service_abstract,
        "wms_version": version,
        "layers": layers,
        "raw_xml": raw_xml,
    }


def _extract_wms_layers(
    element: ET.Element,
    layers: list[dict[str, Any]],
    ns: dict[str, str],
    parent_crs: list[str] | None = None,
) -> None:
    """Recursively extract Layer elements from a WMS Capability XML node."""
    for layer_el in element.findall("Layer") + element.findall("wms:Layer", ns):
        name_el = layer_el.find("Name")
        if name_el is None:
            name_el = layer_el.find("wms:Name", ns)
        title_el = layer_el.find("Title")
        if title_el is None:
            title_el = layer_el.find("wms:Title", ns)
        abstract_el = layer_el.find("Abstract")
        if abstract_el is None:
            abstract_el = layer_el.find("wms:Abstract", ns)

        name = (name_el.text or "").strip() if name_el is not None else ""
        title = (title_el.text or "").strip() if title_el is not None else ""
        abstract = (abstract_el.text or "").strip() if abstract_el is not None else ""

        # CRS / SRS
        crs_list: list[str] = list(parent_crs or [])
        for crs_tag in ("CRS", "SRS", "wms:CRS", "wms:SRS"):
            crs_ns = ns if ":" in crs_tag else {}
            for crs_el in layer_el.findall(crs_tag, crs_ns):
                if crs_el.text:
                    crs_list.append(crs_el.text.strip())
        crs_list = list(dict.fromkeys(crs_list))  # deduplicate, preserve order

        # Bounding box (EX_GeographicBoundingBox or LatLonBoundingBox)
        bbox: dict[str, float] | None = None
        geo_bbox_el = layer_el.find("EX_GeographicBoundingBox")
        if geo_bbox_el is None:
            geo_bbox_el = layer_el.find("wms:EX_GeographicBoundingBox", ns)
        if geo_bbox_el is not None:
            try:
                w_el = geo_bbox_el.find("westBoundLongitude") or geo_bbox_el.find("wms:westBoundLongitude", ns)
                e_el = geo_bbox_el.find("eastBoundLongitude") or geo_bbox_el.find("wms:eastBoundLongitude", ns)
                s_el = geo_bbox_el.find("southBoundLatitude") or geo_bbox_el.find("wms:southBoundLatitude", ns)
                n_el = geo_bbox_el.find("northBoundLatitude") or geo_bbox_el.find("wms:northBoundLatitude", ns)
                if w_el is not None and e_el is not None and s_el is not None and n_el is not None:
                    bbox = {
                        "west": float(w_el.text),  # type: ignore[arg-type]
                        "east": float(e_el.text),  # type: ignore[arg-type]
                        "south": float(s_el.text),  # type: ignore[arg-type]
                        "north": float(n_el.text),  # type: ignore[arg-type]
                    }
            except (TypeError, ValueError, AttributeError):
                pass

        if not bbox:
            latlon_el = layer_el.find("LatLonBoundingBox")
            if latlon_el is None:
                latlon_el = layer_el.find("wms:LatLonBoundingBox", ns)
            if latlon_el is not None:
                try:
                    bbox = {
                        "west": float(latlon_el.get("minx", 0)),
                        "east": float(latlon_el.get("maxx", 0)),
                        "south": float(latlon_el.get("miny", 0)),
                        "north": float(latlon_el.get("maxy", 0)),
                    }
                except (TypeError, ValueError):
                    pass

        if name:
            layers.append(
                {
                    "name": name,
                    "title": title,
                    "abstract": abstract,
                    "crs": crs_list,
                    "bbox": bbox,
                }
            )

        # Recurse into nested layers
        _extract_wms_layers(layer_el, layers, ns, crs_list)


async def wms_get_map(
    url: str,
    layers: str,
    bbox: str,
    width: int = 512,
    height: int = 512,
    srs: str = "EPSG:4326",
    image_format: str = "image/png",
    version: str = "1.3.0",
) -> dict[str, Any]:
    """Request a map image from a WMS server (GetMap operation).

    Args:
        url: WMS service endpoint URL.
        layers: Comma-separated list of layer names to render.
        bbox: Bounding box as ``"minx,miny,maxx,maxy"`` in the given SRS.
        width: Image width in pixels.
        height: Image height in pixels.
        srs: Coordinate reference system (e.g. ``"EPSG:4326"``).
              For WMS 1.3.0, this is the CRS parameter.
        image_format: Requested image MIME type (e.g. ``"image/png"``).
        version: WMS protocol version (``"1.1.1"`` or ``"1.3.0"``).

    Returns:
        A dict with:
          - ``image_base64``: Base64-encoded image data (str).
          - ``content_type``: MIME type of the returned image.
          - ``width`` / ``height``: Requested dimensions.
    """
    crs_param = "CRS" if version == "1.3.0" else "SRS"
    params = {
        "SERVICE": "WMS",
        "VERSION": version,
        "REQUEST": "GetMap",
        "LAYERS": layers,
        "BBOX": bbox,
        "WIDTH": str(width),
        "HEIGHT": str(height),
        crs_param: srs,
        "FORMAT": image_format,
        "TRANSPARENT": "TRUE",
        "STYLES": "",
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
        "width": width,
        "height": height,
        "layers": layers,
        "bbox": bbox,
        "srs": srs,
    }


async def wms_get_feature_info(
    url: str,
    layers: str,
    bbox: str,
    width: int,
    height: int,
    x: int,
    y: int,
    srs: str = "EPSG:4326",
    info_format: str = "application/json",
    version: str = "1.3.0",
) -> dict[str, Any]:
    """Request feature information at a pixel coordinate (GetFeatureInfo operation).

    Args:
        url: WMS service endpoint URL.
        layers: Comma-separated layer names to query.
        bbox: Bounding box of the map request as ``"minx,miny,maxx,maxy"``.
        width: Width of the map image in pixels.
        height: Height of the map image in pixels.
        x: Pixel column of the query point.
        y: Pixel row of the query point.
        srs: Coordinate reference system.
        info_format: Response MIME type (``"application/json"`` or ``"text/xml"``).
        version: WMS protocol version.

    Returns:
        A dict with:
          - ``info_format``: The requested/returned MIME type.
          - ``content``: Raw response text from the server.
          - ``x`` / ``y``: The queried pixel coordinates.
    """
    crs_param = "CRS" if version == "1.3.0" else "SRS"
    xy_i_param = "I" if version == "1.3.0" else "X"
    xy_j_param = "J" if version == "1.3.0" else "Y"
    params = {
        "SERVICE": "WMS",
        "VERSION": version,
        "REQUEST": "GetFeatureInfo",
        "QUERY_LAYERS": layers,
        "LAYERS": layers,
        "BBOX": bbox,
        "WIDTH": str(width),
        "HEIGHT": str(height),
        crs_param: srs,
        xy_i_param: str(x),
        xy_j_param: str(y),
        "INFO_FORMAT": info_format,
        "FEATURE_COUNT": "10",
        "STYLES": "",
    }
    base = _base_url(url)
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(base, params=params)
        resp.raise_for_status()

    return {
        "info_format": info_format,
        "content": resp.text,
        "x": x,
        "y": y,
        "layers": layers,
    }
