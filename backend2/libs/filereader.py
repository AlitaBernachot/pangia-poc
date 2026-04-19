# SPDX-FileCopyrightText: 2026 AlitaBernachot
#
# SPDX-License-Identifier: MIT

"""
libs/filereader.py
──────────────────
Async helpers to download and parse remote data files (CSV, JSON, GeoJSON).

Usage
-----
    from libs.filereader import fetch_and_parse

    result = await fetch_and_parse("https://example.com/data.csv")
    # result.format   -> "csv"
    # result.rows     -> list[dict]  (CSV records)
    # result.raw      -> None        (not returned for CSV to save memory)

    result = await fetch_and_parse("https://example.com/data.geojson")
    # result.format   -> "geojson"
    # result.rows     -> list[dict]  (feature properties, with geometry attached)
    # result.raw      -> the original parsed dict
"""

from __future__ import annotations

import csv
import io
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(60.0, connect=10.0)
_MAX_BYTES = 50 * 1024 * 1024  # 50 MB safety cap


@dataclass
class ParsedFile:
    format: str                        # "csv" | "json" | "geojson" | "unknown"
    rows: list[dict[str, Any]] = field(default_factory=list)
    raw: Any = None                    # original parsed object for JSON/GeoJSON
    total_rows: int = 0
    columns: list[str] = field(default_factory=list)
    error: str | None = None


# ─── Public API ───────────────────────────────────────────────────────────────

async def fetch_and_parse(url: str, *, max_rows: int | None = None) -> ParsedFile:
    """Download *url* and parse it as CSV, JSON, or GeoJSON.

    Parameters
    ----------
    url:
        Direct download URL of the file.
    max_rows:
        If set, truncate the result to this many rows (useful for previews).
        Pass ``None`` (default) to return all rows.
    """
    try:
        content, content_type = await _download(url)
    except Exception as exc:  # noqa: BLE001
        return ParsedFile(format="unknown", error=f"Download error: {exc}")

    fmt = _detect_format(url, content_type, content)

    try:
        if fmt == "csv":
            return _parse_csv(content, max_rows=max_rows)
        if fmt in ("json", "geojson"):
            return _parse_json(content, fmt, max_rows=max_rows)
    except Exception as exc:  # noqa: BLE001
        return ParsedFile(format=fmt, error=f"Parse error: {exc}")

    return ParsedFile(format="unknown", error="Unsupported file format")


# ─── Download ─────────────────────────────────────────────────────────────────

async def _download(url: str) -> tuple[bytes, str]:
    """Return (raw bytes, content-type header)."""
    async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            chunks: list[bytes] = []
            total = 0
            async for chunk in resp.aiter_bytes(chunk_size=65536):
                total += len(chunk)
                if total > _MAX_BYTES:
                    raise ValueError(
                        f"File exceeds the {_MAX_BYTES // (1024 * 1024)} MB limit"
                    )
                chunks.append(chunk)
    return b"".join(chunks), content_type


# ─── Format detection ─────────────────────────────────────────────────────────

def _detect_format(url: str, content_type: str, content: bytes) -> str:
    path = urlparse(url).path.lower()
    if path.endswith(".csv"):
        return "csv"
    if path.endswith(".geojson"):
        return "geojson"
    if path.endswith(".json"):
        return "json"

    ct = content_type.lower()
    if "csv" in ct or "text/plain" in ct:
        return "csv"
    if "geojson" in ct:
        return "geojson"
    if "json" in ct:
        return "json"

    # Sniff content
    snippet = content[:512].lstrip()
    if snippet.startswith(b"{") or snippet.startswith(b"["):
        try:
            obj = json.loads(content)
            if isinstance(obj, dict) and obj.get("type") in (
                "FeatureCollection", "Feature", "GeometryCollection"
            ):
                return "geojson"
            return "json"
        except json.JSONDecodeError:
            pass
    return "csv"  # default to CSV for tabular text files


# ─── CSV parser ───────────────────────────────────────────────────────────────

def _parse_csv(content: bytes, *, max_rows: int | None = None) -> ParsedFile:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            text = content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = content.decode("latin-1", errors="replace")

    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel  # type: ignore[assignment]

    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    columns = list(reader.fieldnames or [])

    rows: list[dict[str, Any]] = []
    for i, row in enumerate(reader):
        if max_rows is not None and i >= max_rows:
            break
        rows.append(dict(row))

    total = sum(1 for _ in csv.reader(io.StringIO(text), dialect=dialect)) - 1  # minus header

    return ParsedFile(format="csv", rows=rows, total_rows=max(total, 0), columns=columns)


# ─── JSON / GeoJSON parser ────────────────────────────────────────────────────

def _parse_json(content: bytes, fmt: str, *, max_rows: int | None = None) -> ParsedFile:
    obj = json.loads(content)

    if fmt == "geojson" or (
        isinstance(obj, dict) and obj.get("type") in (
            "FeatureCollection", "Feature", "GeometryCollection"
        )
    ):
        return _parse_geojson(obj, max_rows=max_rows)

    if isinstance(obj, list):
        records = obj
    elif isinstance(obj, dict):
        records = next((v for v in obj.values() if isinstance(v, list)), [obj])
    else:
        records = [{"value": obj}]

    total = len(records)
    if max_rows is not None:
        records = records[:max_rows]

    columns = list(records[0].keys()) if records and isinstance(records[0], dict) else []

    return ParsedFile(
        format="json",
        rows=[r if isinstance(r, dict) else {"value": r} for r in records],
        raw=obj,
        total_rows=total,
        columns=columns,
    )


def _parse_geojson(obj: dict, *, max_rows: int | None = None) -> ParsedFile:
    if obj.get("type") == "FeatureCollection":
        features = obj.get("features", [])
    elif obj.get("type") == "Feature":
        features = [obj]
    else:
        features = []

    total = len(features)
    if max_rows is not None:
        features = features[:max_rows]

    rows: list[dict[str, Any]] = []
    columns: set[str] = set()
    for feat in features:
        props = dict(feat.get("properties") or {})
        geom = feat.get("geometry")
        if geom:
            props["_geometry_type"] = geom.get("type")
        rows.append(props)
        columns.update(props.keys())

    return ParsedFile(
        format="geojson",
        rows=rows,
        raw=obj,
        total_rows=total,
        columns=sorted(columns),
    )


# ─── Coordinate column detection & CSV → GeoJSON conversion ──────────────────

# Candidate column name patterns for latitude / longitude
_LAT_NAMES = {
    "lat", "latitude", "y", "geo_lat", "lat_wgs84", "coordonnees_geo_lat",
    "coord_lat", "latitude_wgs84", "ycoord", "y_coord", "latitude_dd",
    "lat_dd", "wgs84_lat",
}
_LON_NAMES = {
    "lon", "long", "lng", "longitude", "x", "geo_lon", "lon_wgs84",
    "coordonnees_geo_lon", "coord_lon", "longitude_wgs84", "xcoord", "x_coord",
    "longitude_dd", "lon_dd", "wgs84_lon",
}
_LAT_SUBSTRINGS = ["latitude", "_lat", "lat_", "coord_y"]
_LON_SUBSTRINGS = ["longitude", "_lon", "lon_", "_lng", "coord_x"]
_COMBINED_COORD_NAMES = {
    "geo_point_2d", "coordonnees_gps", "coordonnees_geo", "geolocalisation",
    "geo_point", "coordinates", "coordonnees", "geoloc", "position", "localisation",
}
_COMBINED_SUBSTRINGS = ["geo_point", "coord", "geoloc", "gps"]
_LATLON_CELL_RE = re.compile(r"(-?\d{1,3}\.\d+)[,\s]+(-?\d{1,3}\.\d+)")


def _find_coord_columns(columns: list[str]) -> tuple[str | None, str | None]:
    """Return ``(lat_col, lon_col)`` by matching column names case-insensitively.

    Tries exact set matches first, then substring matching.
    """
    cols_lower = {c.lower().strip(): c for c in columns}
    lat_col = next((cols_lower[k] for k in _LAT_NAMES if k in cols_lower), None)
    lon_col = next((cols_lower[k] for k in _LON_NAMES if k in cols_lower), None)
    if lat_col and lon_col:
        return lat_col, lon_col
    if not lat_col:
        lat_col = next(
            (orig for lower, orig in cols_lower.items() if any(s in lower for s in _LAT_SUBSTRINGS)),
            None,
        )
    if not lon_col:
        lon_col = next(
            (orig for lower, orig in cols_lower.items()
             if any(s in lower for s in _LON_SUBSTRINGS) and orig != lat_col),
            None,
        )
    return lat_col, lon_col


def _find_combined_coord_column(columns: list[str]) -> str | None:
    """Find a single column that holds combined ``'lat,lon'`` values (e.g. geo_point_2d)."""
    cols_lower = {c.lower().strip(): c for c in columns}
    match = next((cols_lower[k] for k in _COMBINED_COORD_NAMES if k in cols_lower), None)
    if match:
        return match
    return next(
        (orig for lower, orig in cols_lower.items() if any(s in lower for s in _COMBINED_SUBSTRINGS)),
        None,
    )


def rows_to_geojson(
    rows: list[dict[str, Any]],
    columns: list[str],
) -> dict[str, Any] | None:
    """Convert a list of row-dicts to a GeoJSON FeatureCollection.

    Detection order:
    1. Separate lat + lon columns (heuristic name matching).
    2. Combined ``'lat,lon'`` column (e.g. ``geo_point_2d`` from French open data).

    Returns ``None`` if no coordinate data can be extracted.
    """
    features: list[dict[str, Any]] = []
    lat_col, lon_col = _find_coord_columns(columns)
    if lat_col and lon_col:
        for row in rows:
            try:
                lat = float(str(row.get(lat_col, "")).replace(",", "."))
                lon = float(str(row.get(lon_col, "")).replace(",", "."))
            except (ValueError, TypeError):
                continue
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue
            props = {k: v for k, v in row.items() if k not in (lat_col, lon_col)}
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": props,
            })
    else:
        combined_col = _find_combined_coord_column(columns)
        if combined_col:
            for row in rows:
                cell = str(row.get(combined_col, "")).strip()
                m = _LATLON_CELL_RE.search(cell)
                if not m:
                    continue
                try:
                    lat, lon = float(m.group(1)), float(m.group(2))
                except ValueError:
                    continue
                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    continue
                props = {k: v for k, v in row.items() if k != combined_col}
                features.append({
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lon, lat]},
                    "properties": props,
                })
    if not features:
        return None
    return {"type": "FeatureCollection", "features": features}
