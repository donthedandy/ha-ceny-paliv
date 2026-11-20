# Provenance: this script and the regions.json it writes come from https://github.com/Vituhlos/ha-ceny-paliv (MIT).
# The boundaries themselves are open data of ČÚZK (RÚIAN), CC BY 4.0, simplified.
"""Build custom_components/ceny_paliv/regions.json: the boundaries of the 14 Czech regions (kraje), simplified.

Source: ČÚZK, RÚIAN, the INSPIRE Administrative Units download service (WFS), licence CC BY 4.0. The script asks it
for the units of the 2nd national level (kraje) in WGS 84 and simplifies every ring with Douglas-Peucker, so the
file stays small; a station lies on the wrong side of a simplified border only within about TOLERANCE of it.

    python script/build_regions.py            # download and write the file
    python script/build_regions.py units.xml  # from a GetFeature answer saved before
"""
from __future__ import annotations

import json
import pathlib
import sys
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any

URL = (
    "https://services.cuzk.gov.cz/wfs/inspire-au-wfs.asp?service=WFS&version=2.0.0&request=GetFeature"
    "&STOREDQUERY_ID=GetUnitByNationalLevel&NAT_LEVEL=2ndOrder"
    "&XMIN=-910000&YMIN=-1240000&XMAX=-420000&YMAX=-930000&srsName=urn:ogc:def:crs:EPSG::4326"
)
OUT = pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "ceny_paliv" / "regions.json"
TOLERANCE = 0.002  # degrees, about 200 m north-south and 150 m east-west
NS = {
    "gml": "http://www.opengis.net/gml/3.2",
    "au": "http://inspire.ec.europa.eu/schemas/au/4.0",
    "elf-au": "http://www.locationframework.eu/schemas/AdministrativeUnits/1.0",
    "gn": "http://inspire.ec.europa.eu/schemas/gn/4.0",
    "base2": "http://inspire.ec.europa.eu/schemas/base2/2.0",
}

Point = tuple[float, float]


def _simplify(points: list[Point], tolerance: float) -> list[Point]:
    """Douglas-Peucker, iterative (a ring has tens of thousands of points)."""
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        first, last = stack.pop()
        (y1, x1), (y2, x2) = points[first], points[last]
        dy, dx = y2 - y1, x2 - x1
        length = (dx * dx + dy * dy) ** 0.5
        farthest, index = 0.0, 0
        for i in range(first + 1, last):
            y, x = points[i]
            if length:
                distance = abs(dx * (y1 - y) - dy * (x1 - x)) / length
            else:
                distance = ((y - y1) ** 2 + (x - x1) ** 2) ** 0.5
            if distance > farthest:
                farthest, index = distance, i
        if farthest > tolerance:
            keep[index] = True
            stack += [(first, index), (index, last)]
    return [point for point, kept in zip(points, keep, strict=True) if kept]


def _ring(element: ET.Element) -> list[list[float]]:
    pos_list = element.find(".//gml:posList", NS)
    assert pos_list is not None and pos_list.text
    numbers = [float(value) for value in pos_list.text.split()]
    points = list(zip(numbers[::2], numbers[1::2], strict=True))  # EPSG:4326 in GML: latitude first
    # the closed ring is split in two so its first and last points are not the same (Douglas-Peucker needs a chord)
    half = len(points) // 2
    simplified = _simplify(points[: half + 1], TOLERANCE)[:-1] + _simplify(points[half:], TOLERANCE)
    return [[round(lat, 4), round(lng, 4)] for lat, lng in simplified]


def build(xml: bytes) -> dict[str, Any]:
    regions: list[dict[str, Any]] = []
    for unit in ET.fromstring(xml).iter(f"{{{NS['elf-au']}}}AdministrativeUnit"):
        code = unit.find(".//base2:identifier", NS)
        name = unit.find(".//gn:text", NS)
        assert code is not None and code.text and name is not None and name.text
        polygons = [
            [_ring(polygon.find("gml:exterior", NS))]  # type: ignore[arg-type]
            + [_ring(hole) for hole in polygon.findall("gml:interior", NS)]
            for polygon in unit.iter(f"{{{NS['gml']}}}Polygon")
        ]
        regions.append({"code": code.text[:5], "name": name.text, "polygons": polygons})
    assert len(regions) == 14, f"expected the 14 regions, got {len(regions)}"
    return {
        "source": "ČÚZK, RÚIAN (INSPIRE Administrative Units), CC BY 4.0; simplified",
        "regions": sorted(regions, key=lambda region: region["code"]),
    }


def main() -> None:
    if len(sys.argv) > 1:
        xml = pathlib.Path(sys.argv[1]).read_bytes()
    else:
        with urllib.request.urlopen(URL, timeout=300) as response:  # noqa: S310 - a fixed https URL
            xml = response.read()
    data = build(xml)
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    points = sum(len(ring) for region in data["regions"] for polygon in region["polygons"] for ring in polygon)
    print(f"{OUT.name}: 14 regions, {points} points, {OUT.stat().st_size // 1024} kB")


if __name__ == "__main__":
    main()
