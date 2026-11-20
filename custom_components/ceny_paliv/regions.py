"""The Czech region (kraj) of a point, from the simplified boundaries in regions.json.

The boundaries are open data of ČÚZK (RÚIAN, CC BY 4.0), simplified by script/build_regions.py: a point within about
200 m of a border may land in the neighbouring region.
"""
from __future__ import annotations

import json
import math
import pathlib
from functools import lru_cache
from typing import Any

# a point outside every simplified region still belongs to the nearest one when it is this close
NEAR_BORDER_KM = 2.0

Ring = list[tuple[float, float]]  # (lat, lng) points


def _in_ring(ring: Ring, lat: float, lng: float) -> bool:
    """Ray casting."""
    inside = False
    y1, x1 = ring[-1]
    for y2, x2 in ring:
        if (y1 > lat) != (y2 > lat) and lng < x1 + (lat - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
        y1, x1 = y2, x2
    return inside


class _Region:
    def __init__(self, data: dict[str, Any]) -> None:
        self.code: str = data["code"]
        self.name: str = data["name"]
        # a polygon is [outer ring, hole, hole...]
        self.polygons: list[list[Ring]] = [
            [[(float(lat), float(lng)) for lat, lng in ring] for ring in polygon] for polygon in data["polygons"]
        ]
        points = [p for polygon in self.polygons for p in polygon[0]]
        self.bbox = (
            min(p[0] for p in points), max(p[0] for p in points), min(p[1] for p in points), max(p[1] for p in points)
        )

    def contains(self, lat: float, lng: float) -> bool:
        south, north, west, east = self.bbox
        if not (south <= lat <= north and west <= lng <= east):
            return False
        return any(
            _in_ring(polygon[0], lat, lng) and not any(_in_ring(hole, lat, lng) for hole in polygon[1:])
            for polygon in self.polygons
        )

    def distance_km(self, lat: float, lng: float) -> float:
        """Distance to the nearest vertex of the boundary (good enough for a point just outside)."""
        scale = math.cos(math.radians(lat))
        return 111.2 * min(
            math.hypot(lat - y, (lng - x) * scale) for polygon in self.polygons for ring in polygon for y, x in ring
        )


def _load() -> list[_Region]:
    data = json.loads((pathlib.Path(__file__).parent / "regions.json").read_text(encoding="utf-8"))
    return [_Region(region) for region in data["regions"]]


_REGIONS = _load()  # read once, when the module is imported (Home Assistant imports it outside the event loop)
REGION_NAMES = {region.code: region.name for region in _REGIONS}


@lru_cache(maxsize=8192)
def region_of(lat: float, lng: float) -> str | None:
    """The NUTS 3 code of the region (for example CZ010 for Prague), or None outside the Czech Republic."""
    for region in _REGIONS:
        if region.contains(lat, lng):
            return region.code
    margin = NEAR_BORDER_KM / 70  # degrees, generous for latitude and longitude
    near = [
        (region.distance_km(lat, lng), region.code)
        for region in _REGIONS
        if region.bbox[0] - margin <= lat <= region.bbox[1] + margin
        and region.bbox[2] - margin <= lng <= region.bbox[3] + margin
    ]
    distance, code = min(near, default=(math.inf, None))
    return code if distance <= NEAR_BORDER_KM else None
