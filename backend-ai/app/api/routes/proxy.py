# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""Proxy route for OGC/WFS requests.

Fetches external OGC service responses on behalf of the frontend to avoid
browser CORS restrictions.  Handles:

- Servers that only support GML2 output (converted to GeoJSON server-side)
- Invalid TYPENAME parameters (auto-discovered via GetCapabilities)
- SSRF prevention (private/internal addresses blocked)
"""
from __future__ import annotations

import ipaddress
import logging
import socket
import xml.etree.ElementTree as ET
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

router = APIRouter()
logger = logging.getLogger(__name__)

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]

_MAX_RESPONSE_BYTES = 10 * 1024 * 1024  # 10 MB
_GML_NS = "http://www.opengis.net/gml"
_WFS_NS = "http://www.opengis.net/wfs"


# ─── SSRF validation ──────────────────────────────────────────────────────────


def _validate_url(url: str) -> None:
    """Raise HTTPException if the URL targets a private/internal address."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="Only http/https URLs are allowed.")
    host = parsed.hostname
    if not host:
        raise HTTPException(status_code=400, detail="Invalid URL: missing host.")
    try:
        addr = ipaddress.ip_address(host)
        for net in _BLOCKED_NETWORKS:
            if addr in net:
                raise HTTPException(
                    status_code=400,
                    detail="Requests to private/internal addresses are not allowed.",
                )
    except ValueError:
        try:
            resolved = socket.getaddrinfo(host, None)
        except OSError:
            raise HTTPException(status_code=502, detail=f"Could not resolve host: {host}")
        for info in resolved:
            addr_str = info[4][0]
            try:
                addr = ipaddress.ip_address(addr_str)
                for net in _BLOCKED_NETWORKS:
                    if addr in net:
                        raise HTTPException(
                            status_code=400,
                            detail="Requests to private/internal addresses are not allowed.",
                        )
            except ValueError:
                continue


# ─── GML2 → GeoJSON conversion ────────────────────────────────────────────────


def _looks_projected(coords: list[list[float]]) -> bool:
    """Return True if any coordinate value is clearly outside WGS84 [-180, 180] / [-90, 90] range.

    Values like 700000 (Lambert 93 easting) or 6000000 (northing) are dead giveaways
    that the server returned a projected CRS instead of WGS84 lon/lat.
    """
    for xy in coords:
        if not xy:
            continue
        if abs(xy[0]) > 180 or abs(xy[1]) > 90:
            return True
    return False


def _parse_gml_coords(text: str) -> list[list[float]]:
    """Parse a GML2 ``<gml:coordinates>`` text (``x,y x,y …``) into ``[[lon, lat], …]``."""
    points: list[list[float]] = []
    for pair in text.strip().split():
        parts = pair.split(",")
        if len(parts) >= 2:
            try:
                points.append([float(parts[0]), float(parts[1])])
            except ValueError:
                continue
    return points


def _parse_gml_pos_list(text: str) -> list[list[float]]:
    """Parse a GML3 ``<gml:posList>`` text (``x y x y …``) into ``[[lon, lat], …]``."""
    nums = [float(v) for v in text.strip().split() if v]
    return [[nums[i], nums[i + 1]] for i in range(0, len(nums) - 1, 2)]


def _coords_from_element(elem: ET.Element) -> list[list[float]]:
    """Extract coordinates from a GML geometry child, supporting GML2 and GML3."""
    # GML2 style
    c = elem.find(f"{{{_GML_NS}}}coordinates")
    if c is not None and c.text:
        return _parse_gml_coords(c.text)
    # GML3 style
    pl = elem.find(f"{{{_GML_NS}}}posList")
    if pl is not None and pl.text:
        return _parse_gml_pos_list(pl.text)
    return []


def _parse_gml_geometry(elem: ET.Element) -> dict | None:
    """Recursively convert a GML geometry element to a GeoJSON geometry dict."""
    local = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag

    if local == "Point":
        pts = _coords_from_element(elem)
        return {"type": "Point", "coordinates": pts[0]} if pts else None

    if local == "LineString":
        pts = _coords_from_element(elem)
        return {"type": "LineString", "coordinates": pts} if pts else None

    if local == "Polygon":
        rings: list[list[list[float]]] = []
        outer = elem.find(f".//{{{_GML_NS}}}outerBoundaryIs")
        if outer is None:
            outer = elem.find(f".//{{{_GML_NS}}}exterior")
        if outer is not None:
            for ring_elem in outer.iter():
                pts = _coords_from_element(ring_elem)
                if pts:
                    rings.append(pts)
                    break
        for inner_tag in (f"{{{_GML_NS}}}innerBoundaryIs", f"{{{_GML_NS}}}interior"):
            for inner in elem.findall(f".//{inner_tag}"):
                for ring_elem in inner.iter():
                    pts = _coords_from_element(ring_elem)
                    if pts:
                        rings.append(pts)
                        break
        return {"type": "Polygon", "coordinates": rings} if rings else None

    if local == "MultiPolygon":
        polys = []
        for poly in elem.findall(f".//{{{_GML_NS}}}Polygon"):
            g = _parse_gml_geometry(poly)
            if g:
                polys.append(g["coordinates"])
        return {"type": "MultiPolygon", "coordinates": polys} if polys else None

    if local == "MultiLineString":
        lines = []
        for line in elem.findall(f".//{{{_GML_NS}}}LineString"):
            g = _parse_gml_geometry(line)
            if g:
                lines.append(g["coordinates"])
        return {"type": "MultiLineString", "coordinates": lines} if lines else None

    if local == "MultiPoint":
        pts = []
        for pt in elem.findall(f".//{{{_GML_NS}}}Point"):
            g = _parse_gml_geometry(pt)
            if g:
                pts.append(g["coordinates"])
        return {"type": "MultiPoint", "coordinates": pts} if pts else None

    return None


_GML_GEOM_TAGS = frozenset({
    "Point", "LineString", "Polygon",
    "MultiPolygon", "MultiLineString", "MultiPoint", "GeometryCollection",
})


_KNOWN_PROJECTED_CRS = {
    # Lambert 93 (France métropolitaine)
    "EPSG:2154", "urn:ogc:def:crs:EPSG::2154",
    # Lambert CC (zones)
    "EPSG:3942", "EPSG:3943", "EPSG:3944", "EPSG:3945", "EPSG:3946",
    "EPSG:3947", "EPSG:3948", "EPSG:3949", "EPSG:3950",
    # UTM zones (common)
    "EPSG:32630", "EPSG:32631", "EPSG:32632",
    "EPSG:2972",  # RGFG95 UTM 22N (Guyane)
    "EPSG:2975",  # RGR92 UTM 40S (Réunion)
}


def _reproject_lambert93_to_wgs84(x: float, y: float) -> tuple[float, float]:
    """Approximate reprojection from Lambert 93 (EPSG:2154) to WGS84.

    Uses a simplified iterative Transverse Mercator inverse to avoid a pyproj
    dependency.  Accuracy is ~1 m, sufficient for map display.
    """
    import math

    # Lambert 93 parameters
    a = 6378137.0          # GRS80 semi-major axis
    e2 = 0.00669437999014  # GRS80 first eccentricity squared
    e = math.sqrt(e2)
    n = 0.7256077650532670
    F = 11754255.4261
    rho0 = 6289062.9678
    lam0 = math.radians(3.0)  # central meridian 3°E

    rho = math.sqrt(x ** 2 + (rho0 - y) ** 2)
    if rho == 0:
        return 3.0, 90.0
    theta = math.atan2(x, rho0 - y)
    lam = theta / n + lam0

    t = (F / (abs(rho))) ** (1.0 / n)
    phi = math.pi / 2 - 2 * math.atan(t)
    for _ in range(10):
        sin_phi = math.sin(phi)
        phi = (math.pi / 2
               - 2 * math.atan(t * ((1 - e * sin_phi) / (1 + e * sin_phi)) ** (e / 2)))

    return math.degrees(lam), math.degrees(phi)


def _reproject_geojson(geojson: dict, srs_name: str) -> dict:
    """Reproject all coordinates in a GeoJSON FeatureCollection to WGS84.

    Currently handles Lambert 93 (EPSG:2154) only; other projected CRS fall
    back to a coordinate swap heuristic (tries lat/lon → lon/lat if values
    look like WGS84 after swapping).
    """
    lambert93 = srs_name in ("EPSG:2154", "urn:ogc:def:crs:EPSG::2154")

    def _reproj_coords(coords):
        if not coords:
            return coords
        if isinstance(coords[0], (int, float)):
            if lambert93:
                return list(_reproject_lambert93_to_wgs84(coords[0], coords[1]))
            return [coords[1], coords[0]]  # swap lat/lon → lon/lat for other CRS
        return [_reproj_coords(c) for c in coords]

    def _reproj_geom(geom):
        if not geom:
            return geom
        return {**geom, "coordinates": _reproj_coords(geom["coordinates"])}

    return {
        **geojson,
        "features": [
            {**f, "geometry": _reproj_geom(f.get("geometry"))}
            for f in geojson.get("features", [])
        ],
    }


def _gml_to_geojson(xml_bytes: bytes) -> dict:
    """Convert a GML2/GML3 WFS FeatureCollection to GeoJSON."""
    root = ET.fromstring(xml_bytes)
    features: list[dict] = []

    # Detect CRS from the FeatureCollection srsName attribute
    srs_name: str = ""
    for attr in ("srsName", "SRS"):
        srs_name = root.get(attr, "")
        if srs_name:
            break

    for member in root.findall(f"{{{_WFS_NS}}}member") or root.findall(f"{{{_GML_NS}}}featureMember"):
        for feat_elem in member:
            geometry: dict | None = None
            props: dict = {}

            for child in feat_elem:
                local = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if local == "boundedBy":
                    continue

                # Geometry property: look for a GML geometry child
                found_geom = False
                for geom_child in child:
                    g_local = geom_child.tag.split("}")[-1] if "}" in geom_child.tag else geom_child.tag
                    if g_local in _GML_GEOM_TAGS:
                        # Also capture srsName from the geometry element if not set
                        if not srs_name:
                            srs_name = geom_child.get("srsName", "")
                        g = _parse_gml_geometry(geom_child)
                        if g:
                            geometry = g
                        found_geom = True
                        break

                if not found_geom and child.text and child.text.strip():
                    props[local] = child.text.strip()

            if geometry:
                features.append({"type": "Feature", "geometry": geometry, "properties": props})

    geojson: dict = {"type": "FeatureCollection", "features": features}

    # Reproject if server returned a known projected CRS (e.g. Lambert 93)
    # or if coordinate values are clearly outside WGS84 range
    needs_reproject = srs_name in _KNOWN_PROJECTED_CRS
    if not needs_reproject and features:
        # Heuristic: sample the first feature's first coordinate
        first_geom = features[0].get("geometry") or {}
        coords = first_geom.get("coordinates") or []
        flat: list[list[float]] = []
        if coords and isinstance(coords[0], (int, float)):
            flat = [coords[:2]]
        elif coords and isinstance(coords[0], list):
            flat = [c[:2] for c in (coords[0] if isinstance(coords[0][0], list) else coords)[:3]]
        if _looks_projected(flat):
            logger.debug("GML response appears to be in a projected CRS (srsName=%r); reprojecting to WGS84", srs_name)
            # Assume Lambert 93 for French WFS services with no explicit srsName
            if not srs_name:
                srs_name = "EPSG:2154"
            needs_reproject = True

    if needs_reproject:
        geojson = _reproject_geojson(geojson, srs_name)

    return geojson


def _is_service_exception(data: bytes) -> bool:
    return b"ServiceException" in data or b"ExceptionReport" in data


# ─── WFS helpers ──────────────────────────────────────────────────────────────


async def _discover_first_typename(client: httpx.AsyncClient, service_base: str) -> str | None:
    """Call WFS GetCapabilities and return the first declared FeatureType name."""
    caps_url = f"{service_base}?SERVICE=WFS&REQUEST=GetCapabilities"
    try:
        resp = await client.get(caps_url, timeout=15.0)
        if resp.status_code >= 400:
            return None
        root = ET.fromstring(resp.content)
        # WFS 1.x: <Name> inside <FeatureType>; we skip the top-level service Name
        for ft in root.iter(f"{{{_WFS_NS}}}FeatureType"):
            name_elem = ft.find(f"{{{_WFS_NS}}}Name")
            if name_elem is not None and name_elem.text:
                return name_elem.text.strip()
        # Fallback: un-namespaced
        for elem in root.iter("Name"):
            text = (elem.text or "").strip()
            if text and "WFS" not in text:
                return text
    except Exception:
        logger.debug("GetCapabilities discovery failed for %s", service_base, exc_info=True)
    return None


# ─── Endpoint ─────────────────────────────────────────────────────────────────


@router.get("/api/proxy/wfs")
async def proxy_wfs(
    url: str = Query(..., description="Full WFS GetFeature URL to proxy"),
):
    """Proxy a WFS GetFeature request and return a GeoJSON response.

    Handles servers that only expose GML2 output by converting it server-side.
    Automatically discovers the correct TYPENAME via GetCapabilities when the
    requested one does not exist.
    """
    _validate_url(url)

    req_headers = {
        "User-Agent": "PangIA-GeoIA/2.0 (contact@pangia.io)",
        "Accept": "application/json, application/geo+json, application/xml, text/xml, */*",
    }

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        # ── First attempt ─────────────────────────────────────────────────────
        try:
            resp = await client.get(url, headers=req_headers)
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Upstream WFS service timed out.")
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Could not reach upstream service: {exc}")

        if resp.status_code >= 400:
            raise HTTPException(
                status_code=resp.status_code,
                detail=f"Upstream WFS returned HTTP {resp.status_code}.",
            )

        if len(resp.content) > _MAX_RESPONSE_BYTES:
            raise HTTPException(status_code=413, detail="Upstream response exceeds 10 MB limit.")

        content_type = resp.headers.get("content-type", "")
        data = resp.content

        # ── If JSON → check for projected CRS and reproject if needed ──────────
        if "json" in content_type:
            try:
                geojson_data = resp.json()
                # GeoJSON CRS (legacy, but some WFS servers still emit it)
                crs_obj = geojson_data.get("crs") or {}
                crs_name: str = ""
                if isinstance(crs_obj, dict):
                    props_obj = crs_obj.get("properties") or {}
                    crs_name = props_obj.get("name", "")
                if crs_name in _KNOWN_PROJECTED_CRS:
                    geojson_data = _reproject_geojson(geojson_data, crs_name)
                else:
                    # Heuristic check on first feature
                    first_feats = (geojson_data.get("features") or [])[:1]
                    if first_feats:
                        first_geom = (first_feats[0].get("geometry") or {})
                        coords = first_geom.get("coordinates") or []
                        flat: list[list[float]] = []
                        if coords and isinstance(coords[0], (int, float)):
                            flat = [coords[:2]]
                        elif coords and isinstance(coords[0], list):
                            flat = [c[:2] for c in (coords[0] if isinstance(coords[0][0], list) else coords)[:3]]
                        if _looks_projected(flat):
                            logger.debug("JSON GeoJSON has projected coords; reprojecting Lambert93→WGS84")
                            geojson_data = _reproject_geojson(geojson_data, "EPSG:2154")
                return JSONResponse(content=geojson_data)
            except Exception:
                pass  # fall through to GML parser

        # ── XML/GML response ──────────────────────────────────────────────────
        if _is_service_exception(data):
            # Likely a bad TYPENAME — discover the correct one via GetCapabilities
            parsed = urlparse(url)
            orig_params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            service_base = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

            typename = await _discover_first_typename(client, service_base)
            if not typename:
                raise HTTPException(
                    status_code=502,
                    detail="WFS ServiceException: TYPENAME not found and GetCapabilities discovery failed.",
                )

            max_features = orig_params.get("maxFeatures", orig_params.get("count", "200"))
            retry_params = {
                "SERVICE": "WFS",
                "REQUEST": "GetFeature",
                "VERSION": "1.0.0",
                "TYPENAME": typename,
                "SRSNAME": orig_params.get("SRSNAME", orig_params.get("srsname", "EPSG:4326")),
                "maxFeatures": max_features,
            }
            retry_url = f"{service_base}?{urlencode(retry_params)}"
            logger.debug("WFS typename fallback: %s → TYPENAME=%s", service_base, typename)

            try:
                resp2 = await client.get(retry_url, headers=req_headers, timeout=30.0)
            except httpx.RequestError as exc:
                raise HTTPException(status_code=502, detail=f"WFS retry failed: {exc}")

            if resp2.status_code >= 400 or _is_service_exception(resp2.content):
                raise HTTPException(
                    status_code=502,
                    detail=f"WFS service returned an error even with discovered TYPENAME '{typename}'.",
                )
            data = resp2.content

        # ── Convert GML → GeoJSON ─────────────────────────────────────────────
        try:
            geojson = _gml_to_geojson(data)
        except ET.ParseError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Could not parse WFS response as GML: {exc}",
            )

        return JSONResponse(content=geojson)
