"""Tests of the 0.8.0 work: the data the card needs (all stations, centre, averages, statistics), the region outlines, versions."""
import json
import pathlib
import re
import shutil
import subprocess

import pytest

from custom_components.ceny_paliv.const import CARD_VERSION, MAP_STATIONS, REGIONS_URL
from custom_components.ceny_paliv.sensor import CenyPalivTop5Sensor

from test_flow import mock_site
from test_v06 import setup
from test_v07 import point_entry

ROOT = pathlib.Path(__file__).parent.parent / "custom_components" / "ceny_paliv"


async def test_top5_carries_everything_the_card_draws(hass, aioclient_mock):
    await setup(hass, aioclient_mock)
    top = hass.states.get("sensor.ceny_paliv_n95_top5")
    pool = top.attributes["map_stations"]
    prices = [s["price"] for s in pool]
    assert len(pool) > 5 and len(pool) <= MAP_STATIONS and prices == sorted(prices)
    assert pool[0]["price"] == top.attributes["stations"][0]["price"] == float(top.state)
    first = pool[0]
    assert {"name", "address", "chain", "price", "lat", "lng", "maps", "url", "home", "updated_date"} <= set(first)
    assert set(first["trends"]) == {"1"}                         # the day's change only: the list stays small
    assert top.attributes["centre"] is None                      # a whole city has no single centre
    assert top.attributes["averages"]["area"]["average"] > 0 and top.attributes["averages"]["country"]["regions"]
    assert top.attributes["state_class"] == "measurement"        # long-term statistics: the 30-day graph of the cheapest price


def test_the_big_attributes_stay_out_of_the_database():
    assert {"map_stations", "averages", "labels", "logos", "stations"} <= CenyPalivTop5Sensor._unrecorded_attributes


async def test_a_point_has_a_centre_and_distances(hass, aioclient_mock):
    mock_site(aioclient_mock)
    entry = point_entry(hass, source="home", radius=8)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    top = hass.states.get("sensor.ceny_paliv_n95_top5")
    assert top.attributes["centre"] == {"lat": hass.config.latitude, "lng": hass.config.longitude}
    assert all("distance_km" in s for s in top.attributes["map_stations"])


async def test_region_outlines_are_served(hass, aioclient_mock, hass_client_no_auth):
    await setup(hass, aioclient_mock)
    client = await hass_client_no_auth()
    resp = await client.get(REGIONS_URL)
    assert resp.status == 200
    data = await resp.json()
    assert len(data["regions"]) == 14 and data["regions"][0]["polygons"]


def test_versions_agree():
    js = (ROOT / "frontend" / "ceny-paliv-card.js").read_text()
    assert re.search(r"const CARD_VERSION = '([^']+)'", js).group(1) == CARD_VERSION
    assert json.loads((ROOT / "manifest.json").read_text())["version"] == CARD_VERSION


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_card_is_valid_javascript():
    result = subprocess.run(["node", "--check", str(ROOT / "frontend" / "ceny-paliv-card.js")], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
