"""Tests of the 0.7.0 work: location sources, average prices, older prices, addresses, statistics, events, blueprints."""
import datetime as dt
import json
import pathlib

import pytest
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.ceny_paliv.api import (
    MODE_CITY,
    MODE_POINT,
    Place,
    address_of,
    build_payload,
    city_options,
    markers_in_place,
    station_options,
    station_title,
    without_house_number,
)
from custom_components.ceny_paliv.const import DOMAIN
from custom_components.ceny_paliv.regions import REGION_NAMES, region_of
from custom_components.ceny_paliv.statistics import _metadata, station_statistic_id

from test_flow import HOME, LPG, N95, calls, legacy_entry, mock_site
from test_v06 import entry_for, good, only, setup

HRADEC = (50.2099, 15.8328)
PLZEN = (49.7475, 13.3776)
MARKERS = json.loads(N95)["markers"]
HRADEC_PLACE = Place("main", "Hradec Králové", MODE_CITY, city="Hradec-Kralove")
NOW = dt.datetime(2026, 11, 20, 12, 0, tzinfo=dt.timezone.utc)


def with_prices(prices: dict[str, float] | None = None, fresh: dict[str, str] | None = None) -> str:
    """The n95 fixture with other prices (by station slug part) or other `fresh` values."""
    data = json.loads(N95)
    for m in data["markers"]:
        slug = m["url"].split("/")[3] if m["url"].count("/") >= 4 else ""
        if prices and slug in prices:
            m["price"] = prices[slug]
        if fresh and slug in fresh:
            m["fresh"] = fresh[slug]
    return json.dumps(data)


def point_entry(hass, **place):
    entry = MockConfigEntry(
        domain=DOMAIN, title="Ceny paliv Point", unique_id=DOMAIN,
        data={"key": "GOODKEY", "mode": "point", "radius": 8, "name": "Following", **place},
        options={"fuels": ["n95"], "homes": {}, "language": "en"},
    )
    entry.add_to_hass(hass)
    return entry


# ----------------------------------------------------------------------------------------------- regions
def test_region_of_known_places():
    assert REGION_NAMES[region_of(*HRADEC)] == "Královéhradecký kraj"
    assert REGION_NAMES[region_of(*PLZEN)] == "Plzeňský kraj"
    assert REGION_NAMES[region_of(50.08, 14.43)] == "Hlavní město Praha"
    assert region_of(48.0, 10.0) is None and region_of(52.5, 13.4) is None       # far outside the Czech Republic
    assert len(REGION_NAMES) == 14


# --------------------------------------------------------------------------------------------- addresses
def test_house_numbers_leave_the_town():
    assert without_house_number("Dobřany 456") == "Dobřany"
    assert without_house_number("Hradec Králové") == "Hradec Králové"
    assert without_house_number("Praha 4") == "Praha"           # a number after the town is dropped too
    assert without_house_number("Doubravice 12/3") == "Doubravice"
    assert without_house_number("Ves č.p. 5") == "Ves"


def test_accented_address_only_when_it_agrees_with_the_url():
    m = {"name": "Orlen", "url": "/Ceny-benzinu-a-nafty/Hradec-Kralove/Orlen-Bratri-Stefanu-69/1", "addr": "Bratří Štefanů 69, Hradec Králové"}
    assert address_of(m) == "Bratří Štefanů 69"
    assert station_title("Orlen", address_of(m)) == "Orlen – Bratří Štefanů 69"
    # another address in `addr` is not trusted: the slug is used
    assert address_of({**m, "addr": "Úplně jiná 1, Jinde"}) == "Orlen Bratri Stefanu 69"
    assert address_of({**m, "addr": ""}) == "Orlen Bratri Stefanu 69"
    assert address_of({k: v for k, v in m.items() if k != "addr"}) == "Orlen Bratri Stefanu 69"
    # a village: the address is the village and a number
    v = {"name": "MOL", "url": "/Ceny-benzinu-a-nafty/Dobrany/MOL-Dobrany-456/2", "addr": "Dobřany 456"}
    assert address_of(v) == "Dobřany 456"
    # no town in the URL: the `addr` text
    assert address_of({"name": "X", "url": "/stanice/9", "addr": "Hlavní 1, Plzeň"}) == "Hlavní 1, Plzeň"


def test_town_list_labels_survive_house_numbers():
    markers = [
        {"url": "/Ceny-benzinu-a-nafty/Dobrany/A/1", "addr": "Dobřany 456"},
        {"url": "/Ceny-benzinu-a-nafty/Dobrany/B/2", "addr": "tř. 1.máje 996, Dobřany"},
    ]
    assert city_options(markers) == [{"value": "Dobrany", "label": "Dobřany"}]


def test_station_labels_in_the_select_have_accents():
    labels = [o["label"] for o in station_options(MARKERS, HRADEC_PLACE)]
    assert "Orlen – Bratří Štefanů 69" in labels


# ------------------------------------------------------------------------------------------ older prices
def old(days: int) -> str:
    day = dt.date(2026, 11, 20) - dt.timedelta(days=days)
    return f"{day.day}. {day.month}. {day.year}"


def test_older_prices_option_widens_the_window_and_never_narrows_it():
    markers = json.loads(with_prices(fresh={"Orlen-Bratri-Stefanu-69": old(5), "Prim-Kutnohorska-226": old(3)}))["markers"]
    kw = dict(fuel="n95", home_slug=None, history={}, now=NOW)

    def listed(place):
        return [s["name"] for s in build_payload(markers, place=place, **kw)["stations"]]

    standard = build_payload(markers, place=HRADEC_PLACE, **kw)
    assert standard["max_age_days"] == 1 and "Orlen" not in listed(HRADEC_PLACE)
    three = Place("main", "H", MODE_CITY, city="Hradec-Kralove", max_age_days=3)
    assert "Prim" in listed(three) and "Orlen" not in listed(three)           # 3 days old yes, 5 days old no
    seven = Place("main", "H", MODE_CITY, city="Hradec-Kralove", max_age_days=7)
    assert "Orlen" in listed(seven) and build_payload(markers, place=seven, **kw)["max_age_days"] == 7
    # LPG already has a 7 day window: choosing 3 days does not shorten it
    lpg = build_payload(json.loads(LPG)["markers"], fuel="lpg", place=three, home_slug=None, history={}, now=NOW)
    assert lpg["max_age_days"] == 7
    # the date of an older price is shown with the station
    updated = {s["name"]: s["updated"] for s in build_payload(markers, place=seven, **kw)["stations"]}
    assert updated["Orlen"] == old(5)


async def test_older_prices_option_through_the_options_flow(hass, aioclient_mock):
    mock_site(aioclient_mock)
    entry = legacy_entry(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    o = await hass.config_entries.options.async_init(entry.entry_id)
    o = await hass.config_entries.options.async_configure(o["flow_id"], {"mode": "city"})
    o = await hass.config_entries.options.async_configure(o["flow_id"], {"city": "Hradec-Kralove"})
    assert [k for k in o["data_schema"].schema if k == "max_age_days"][0].default() == "standard"
    o = await hass.config_entries.options.async_configure(o["flow_id"], {"fuels": ["n95"], "language": "en", "max_age_days": "7"})
    o = await hass.config_entries.options.async_configure(o["flow_id"], {"station": HOME})
    o = await hass.config_entries.options.async_configure(o["flow_id"], {"logos": []})
    await hass.async_block_till_done()
    assert entry.options["max_age_days"] == 7
    assert hass.states.get("sensor.ceny_paliv_n95_top5").attributes["max_age_days"] == 7
    # and back to the standard window
    o = await hass.config_entries.options.async_init(entry.entry_id)
    o = await hass.config_entries.options.async_configure(o["flow_id"], {"mode": "city"})
    o = await hass.config_entries.options.async_configure(o["flow_id"], {"city": "Hradec-Kralove"})
    assert [k for k in o["data_schema"].schema if k == "max_age_days"][0].default() == "7"
    o = await hass.config_entries.options.async_configure(o["flow_id"], {"fuels": ["n95"], "language": "en", "max_age_days": "standard"})
    o = await hass.config_entries.options.async_configure(o["flow_id"], {"station": HOME})
    o = await hass.config_entries.options.async_configure(o["flow_id"], {"logos": []})
    await hass.async_block_till_done()
    assert "max_age_days" not in entry.options


# ------------------------------------------------------------------------------------------- averages
def mean(values):
    return round(sum(values) / len(values), 2)


def test_average_prices_of_country_region_and_area():
    today = NOW.date()
    payload = build_payload(MARKERS, fuel="n95", place=HRADEC_PLACE, home_slug=None, history={}, now=NOW)
    avg = payload["averages"]
    fresh = [m for m in MARKERS if m["fresh"].lower() in ("dnes", "včera", "vcera")]
    assert avg["country"]["average"] == mean([m["price"] for m in fresh]) and avg["country"]["station_count"] == len(fresh)
    in_town = [m["price"] for m in fresh if m["url"].split("/")[2] == "Hradec-Kralove"]
    assert avg["area"]["average"] == mean(in_town) and avg["area"]["station_count"] == len(in_town)
    assert avg["region"]["name"] == "Královéhradecký kraj" and avg["area"]["region"] == "Královéhradecký kraj"
    in_region = [m["price"] for m in fresh if region_of(m["lat"], m["lng"]) == "CZ052"]
    assert avg["region"]["average"] == mean(in_region)
    # the differences are consistent, and the regions are ranked cheapest first
    assert avg["area"]["vs_national"] == round(avg["area"]["average"] - avg["country"]["average"], 2)
    assert avg["area"]["vs_region"] == round(avg["area"]["average"] - avg["region"]["average"], 2)
    ranks = [r["rank"] for r in avg["country"]["regions"]]
    averages = [r["average"] for r in avg["country"]["regions"]]
    assert ranks == list(range(1, len(ranks) + 1)) and averages == sorted(averages)
    assert avg["country"]["median"] is not None and today == dt.date(2026, 11, 20)


def test_average_of_a_point_uses_the_region_of_its_centre():
    place = Place("p", "Plzeň", MODE_POINT, lat=PLZEN[0], lng=PLZEN[1], radius_km=10)
    avg = build_payload(MARKERS, fuel="n95", place=place, home_slug=None, history={}, now=NOW)["averages"]
    assert avg["region"]["name"] == "Plzeňský kraj" and avg["area"]["station_count"] > 0
    # a centre abroad has no region (and an area with no stations has no average)
    far = Place("p", "Far", MODE_POINT, lat=48.0, lng=10.0, radius_km=5)
    avg = build_payload(MARKERS, fuel="n95", place=far, home_slug=None, history={}, now=NOW)["averages"]
    assert avg["region"] is None and avg["area"]["average"] is None and avg["area"]["vs_region"] is None


async def test_average_sensors(hass, aioclient_mock):
    await setup(hass, aioclient_mock)
    national = hass.states.get("sensor.ceny_paliv_n95_national_average")
    region = hass.states.get("sensor.ceny_paliv_n95_region_average")
    area = hass.states.get("sensor.ceny_paliv_n95_area_average")
    assert float(national.state) > 0 and national.attributes["station_count"] > 100
    assert national.attributes["regions"][0]["rank"] == 1 and national.attributes["cp_role"] == "national_average"
    assert region.attributes["region"] == "Královéhradecký kraj" and region.attributes["region_code"] == "CZ052"
    assert area.attributes["vs_region"] == round(float(area.state) - float(region.state), 2)
    assert area.attributes["state_class"] == "measurement" and area.attributes["unit_of_measurement"] == "Kč/l"
    assert area.attributes["friendly_name"] == "Hradec Kralove Natural 95 · average · area"
    assert area.attributes["attribution"] == "Ceny: mbenzin.cz"


async def test_region_average_is_unavailable_outside_the_country(hass, aioclient_mock):
    hass.config.latitude, hass.config.longitude = 48.0, 10.0          # a home abroad
    mock_site(aioclient_mock)
    entry = point_entry(hass, source="home", radius=5)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.ceny_paliv_n95_region_average").state == "unavailable"
    assert hass.states.get("sensor.ceny_paliv_n95_national_average").state != "unavailable"


# ------------------------------------------------------------------------------------ location sources
async def test_home_source_uses_the_home_location(hass, aioclient_mock):
    hass.config.latitude, hass.config.longitude = HRADEC
    mock_site(aioclient_mock)
    entry = point_entry(hass, source="home", radius=5)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    stations = hass.states.get("sensor.ceny_paliv_n95_top5").attributes["stations"]
    assert stations and all(s["distance_km"] <= 5 for s in stations)
    # the home moves (the user changes it in Home Assistant): the next refresh follows
    hass.config.latitude, hass.config.longitude = PLZEN
    await entry.runtime_data.async_refresh()
    assert hass.states.get("sensor.ceny_paliv_n95_top5").attributes["stations"][0]["address"] != stations[0]["address"]


async def test_following_a_person_moves_the_area_without_a_request(hass, aioclient_mock):
    mock_site(aioclient_mock)
    hass.states.async_set("person.me", "home", {"latitude": HRADEC[0], "longitude": HRADEC[1]})
    entry = point_entry(hass, source="person", entity="person.me")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry.runtime_data
    first = [s["address"] for s in hass.states.get("sensor.ceny_paliv_n95_top5").attributes["stations"]]
    sent = len(aioclient_mock.mock_calls)

    # a few hundred metres: nothing to do
    data = coordinator.data
    hass.states.async_set("person.me", "home", {"latitude": HRADEC[0] + 0.003, "longitude": HRADEC[1]})
    await hass.async_block_till_done()
    assert coordinator.data is data

    # a trip to Plzeň: the area follows, from the prices already downloaded
    hass.states.async_set("person.me", "not_home", {"latitude": PLZEN[0], "longitude": PLZEN[1]})
    await hass.async_block_till_done()
    now = hass.states.get("sensor.ceny_paliv_n95_top5").attributes["stations"]
    assert now and [s["address"] for s in now] != first and all(s["distance_km"] <= 8 for s in now)
    assert len(aioclient_mock.mock_calls) == sent, "following someone sends no request to mBenzin"
    assert hass.states.get("sensor.ceny_paliv_n95_region_average").attributes["region"] == "Plzeňský kraj"

    # the phone loses its GPS: the area waits at home
    hass.states.async_set("person.me", "unknown", {})
    await hass.async_block_till_done()
    assert [s["address"] for s in hass.states.get("sensor.ceny_paliv_n95_top5").attributes["stations"]] != [s["address"] for s in now]


async def test_stale_downloads_are_not_reused_when_following_a_person(hass, aioclient_mock):
    mock_site(aioclient_mock)
    hass.states.async_set("person.me", "home", {"latitude": HRADEC[0], "longitude": HRADEC[1]})
    entry = point_entry(hass, source="person", entity="person.me")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry.runtime_data
    markers, when = coordinator._downloads["n95"]
    coordinator._downloads["n95"] = (markers, when - dt.timedelta(hours=7))     # older than a refresh interval
    sent = calls(aioclient_mock, "n95")
    hass.states.async_set("person.me", "not_home", {"latitude": PLZEN[0], "longitude": PLZEN[1]})
    await hass.async_block_till_done()
    assert calls(aioclient_mock, "n95") == sent + 1, "a price list that old is downloaded again"


async def test_following_a_zone(hass, aioclient_mock):
    mock_site(aioclient_mock)
    hass.states.async_set("zone.office", "0", {"latitude": HRADEC[0], "longitude": HRADEC[1], "radius": 100})
    entry = point_entry(hass, source="zone", entity="zone.office")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry.runtime_data
    first = hass.states.get("sensor.ceny_paliv_n95_top5").attributes["stations"][0]["address"]
    data = coordinator.data
    hass.states.async_set("zone.office", "2", {"latitude": HRADEC[0], "longitude": HRADEC[1], "radius": 100})    # a head count
    await hass.async_block_till_done()
    assert coordinator.data is data, "people arriving in the zone change nothing"
    hass.states.async_set("zone.office", "2", {"latitude": PLZEN[0], "longitude": PLZEN[1], "radius": 100})      # the zone moved
    await hass.async_block_till_done()
    assert hass.states.get("sensor.ceny_paliv_n95_top5").attributes["stations"][0]["address"] != first


async def test_a_missing_person_keeps_the_area_at_home_and_raises_an_issue(hass, aioclient_mock):
    hass.config.latitude, hass.config.longitude = HRADEC
    mock_site(aioclient_mock)
    entry = point_entry(hass, source="person", entity="person.ghost")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.ceny_paliv_n95_top5").attributes["stations"], "the area waits at home"
    issue_id = f"location_{entry.entry_id}_main"
    issue = ir.async_get(hass).async_get_issue(DOMAIN, issue_id)
    assert issue and issue.translation_key == "person_missing" and issue.translation_placeholders["entity"] == "person.ghost"
    hass.states.async_set("person.ghost", "home", {"latitude": HRADEC[0], "longitude": HRADEC[1]})
    await entry.runtime_data.async_refresh()
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None
    await hass.config_entries.async_remove(entry.entry_id)


async def test_a_missing_zone_raises_its_own_issue(hass, aioclient_mock):
    hass.config.latitude, hass.config.longitude = HRADEC
    mock_site(aioclient_mock)
    entry = point_entry(hass, source="zone", entity="zone.nowhere")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    issue = ir.async_get(hass).async_get_issue(DOMAIN, f"location_{entry.entry_id}_main")
    assert issue and issue.translation_key == "zone_missing"


async def test_point_without_a_usable_centre_keeps_the_last_one(hass, aioclient_mock):
    mock_site(aioclient_mock)
    entry = point_entry(hass, source="map", latitude=HRADEC[0], longitude=HRADEC[1])
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.ceny_paliv_n95_top5").attributes["stations"]
    # markers_in_place never mixes up an unknown centre with "stations without a town"
    assert markers_in_place(MARKERS, Place("x", "x", MODE_POINT)) == []


# ------------------------------------------------------------------------ config flow: the sources
async def flow_add(hass, entry, steps):
    r = await hass.config_entries.subentries.async_init((entry.entry_id, "place"), context={"source": "user"})
    for user_input in steps:
        assert r["type"].value == "form", r
        r = await hass.config_entries.subentries.async_configure(r["flow_id"], user_input)
    await hass.async_block_till_done()
    return r


@pytest.mark.parametrize(
    ("source", "entity", "step_id", "expected_entity"),
    [("home", None, "point_home", None), ("person", "person.me", "point_person", "person.me"), ("zone", "zone.office", "point_zone", "zone.office")],
)
async def test_add_a_place_around_home_a_person_or_a_zone(hass, aioclient_mock, source, entity, step_id, expected_entity):
    mock_site(aioclient_mock)
    hass.config.latitude, hass.config.longitude = HRADEC
    hass.states.async_set("person.me", "home", {"latitude": HRADEC[0], "longitude": HRADEC[1], "friendly_name": "Me"})
    hass.states.async_set("zone.office", "0", {"latitude": HRADEC[0], "longitude": HRADEC[1], "radius": 50, "friendly_name": "Office"})
    entry = legacy_entry(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    r = await hass.config_entries.subentries.async_init((entry.entry_id, "place"), context={"source": "user"})
    r = await hass.config_entries.subentries.async_configure(r["flow_id"], {"mode": "point"})
    assert r["step_id"] == "source" and [k for k in r["data_schema"].schema if k == "source"][0].default() == "map"
    r = await hass.config_entries.subentries.async_configure(r["flow_id"], {"source": source})
    assert r["step_id"] == step_id
    fields = [str(k) for k in r["data_schema"].schema]
    assert ("entity" in fields) == (entity is not None) and "radius" in fields and "name" in fields
    user = {"radius": 6, "name": ""}
    if entity:
        user["entity"] = entity
    r = await hass.config_entries.subentries.async_configure(r["flow_id"], user)
    assert r["step_id"] == "fuels" and "max_age_days" in [str(k) for k in r["data_schema"].schema]
    r = await hass.config_entries.subentries.async_configure(r["flow_id"], {"fuels": ["n95"], "max_age_days": "3"})
    assert r["step_id"] == "station" and len(r["data_schema"].schema["station"].config["options"]) > 1, "stations around the centre"
    r = await hass.config_entries.subentries.async_configure(r["flow_id"], {"station": "__none__"})
    await hass.async_block_till_done()
    sub = next(iter(entry.subentries.values()))
    expected = {"mode": "point", "source": source, "radius": 6.0, "fuels": ["n95"], "homes": {}, "max_age_days": 3}
    if expected_entity:
        expected["entity"] = expected_entity
    assert {k: v for k, v in sub.data.items() if k != "name"} == expected
    label = {"home": hass.config.location_name or "Home", "person": "Me", "zone": "Office"}[source]
    assert sub.data["name"] == f"{label} · 6 km" == sub.title
    place_sensor = next(s for s in hass.states.async_all("sensor") if s.entity_id.endswith("_n95_top5") and s.attributes["cp_place"] != "main")
    assert place_sensor.attributes["stations"] and all(x["distance_km"] <= 6 for x in place_sensor.attributes["stations"])


async def test_reconfigure_keeps_the_source_and_entity(hass, aioclient_mock):
    mock_site(aioclient_mock)
    hass.states.async_set("person.me", "home", {"latitude": HRADEC[0], "longitude": HRADEC[1]})
    entry = legacy_entry(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await flow_add(hass, entry, [
        {"mode": "point"}, {"source": "person"}, {"entity": "person.me", "radius": 7, "name": "Phone"}, {"fuels": ["n95"]}, {"station": "__none__"}
    ])
    sub_id = next(iter(entry.subentries))
    r = await hass.config_entries.subentries.async_init((entry.entry_id, "place"), context={"source": "reconfigure", "subentry_id": sub_id})
    r = await hass.config_entries.subentries.async_configure(r["flow_id"], {"mode": "point"})
    assert [k for k in r["data_schema"].schema if k == "source"][0].default() == "person"
    r = await hass.config_entries.subentries.async_configure(r["flow_id"], {"source": "person"})
    defaults = {str(k): k.default() for k in r["data_schema"].schema if k.default is not None and callable(k.default)}
    assert defaults["entity"] == "person.me" and defaults["radius"] == 7.0 and defaults["name"] == "Phone"


async def test_radius_is_limited_by_the_form(hass, aioclient_mock):
    from homeassistant.data_entry_flow import InvalidData

    mock_site(aioclient_mock)
    entry = legacy_entry(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    r = await hass.config_entries.subentries.async_init((entry.entry_id, "place"), context={"source": "user"})
    r = await hass.config_entries.subentries.async_configure(r["flow_id"], {"mode": "point"})
    r = await hass.config_entries.subentries.async_configure(r["flow_id"], {"source": "home"})
    for bad in (0, 0.5, 101, 5000):
        with pytest.raises(InvalidData):
            await hass.config_entries.subentries.async_configure(r["flow_id"], {"radius": bad})
    r = await hass.config_entries.subentries.async_configure(r["flow_id"], {"radius": 100})
    assert r["step_id"] == "fuels"


# ---------------------------------------------------------------------------------------------- statistics
def test_station_statistic_ids_are_stable_and_per_fuel():
    url = "/Ceny-benzinu-a-nafty/Hradec-Kralove/Orlen-Bratri-Stefanu-69/1"
    assert station_statistic_id("n95", url) == station_statistic_id("n95", url)
    assert station_statistic_id("n95", url) != station_statistic_id("diesel", url)
    assert station_statistic_id("n95", url).startswith("ceny_paliv:n95_")
    meta = _metadata("ceny_paliv:n95_x", "Natural 95 · Orlen", "Kč/l")
    assert meta["source"] == DOMAIN and meta["unit_of_measurement"] == "Kč/l" and meta["has_sum"] is False


async def test_favourite_history_goes_to_long_term_statistics(hass, aioclient_mock, monkeypatch):
    from custom_components.ceny_paliv import statistics

    written = []
    monkeypatch.setattr(statistics, "async_add_external_statistics", lambda h, meta, rows: written.append((meta, rows)))
    hass.config.components.add("recorder")          # the recorder is a soft dependency: it is only used when it is there
    mock_site(aioclient_mock)
    entry = entry_for(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry.runtime_data
    # yesterday's price is in the daily log: it comes along
    yesterday = (dt_util.now().date() - dt.timedelta(days=1)).isoformat()
    coordinator._history["n95"][HOME].insert(0, [yesterday, 37.5])
    written.clear()
    await coordinator.async_refresh()
    assert len(written) == 1
    meta, rows = written[0]
    home = coordinator.data["main"]["n95"]["home"]
    assert meta["statistic_id"] == station_statistic_id("n95", home["url"]) and meta["source"] == DOMAIN
    assert meta["unit_of_measurement"] == "Kč/l" and "Orlen" in meta["name"] and meta["has_sum"] is False
    means = [row["mean"] for row in rows]
    assert 37.5 in means and means[-1] == 36.9                      # the old day, and the price of this hour
    starts = [row["start"] for row in rows]
    assert starts == sorted(starts) and all(row["min"] == row["max"] == row["mean"] for row in rows)
    # a favourite that is not found (no price) writes nothing
    written.clear()
    assert statistics.async_import_station_statistics(hass, "n95", {"url": "/x"}, [], dt_util.now()) is None and not written


# -------------------------------------------------------------------------------------------------- events
async def test_price_change_events(hass, aioclient_mock):
    entry = await setup(hass, aioclient_mock)
    coordinator = entry.runtime_data
    event_id = "event.ceny_paliv_n95_price_change"
    state = hass.states.get(event_id)
    assert state and state.attributes["event_types"] == ["favourite_cheaper", "favourite_dearer", "cheapest_cheaper"]
    assert state.state == "unknown", "the prices at start-up are only the baseline"
    assert state.attributes["friendly_name"] == "Hradec Kralove Natural 95 · price change"
    unit = {"Orlen-Bratri-Stefanu-69": None}

    # the favourite gets cheaper (and so does the cheapest price of the town)
    only(aioclient_mock, text=with_prices({"Orlen-Bratri-Stefanu-69": 36.4}))
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    attrs = hass.states.get(event_id).attributes
    assert attrs["event_type"] == "cheapest_cheaper"          # the second event of that refresh is the last state
    assert attrs["station"] == "Orlen – Bratří Štefanů 69" and attrs["price"] == 36.4 and attrs["previous_price"] == 36.9
    assert attrs["change"] == -0.5 and attrs["unit"] == "Kč/l" and attrs["fuel"] == "Natural 95"
    assert attrs["place"] == "Hradec Kralove" and attrs["maps"].startswith("https://www.google.com/maps")

    # the favourite gets dearer, the cheapest price is another station's: only "dearer"
    seen = []
    hass.bus.async_listen("state_changed", lambda e: e.data["entity_id"] == event_id and seen.append(e.data["new_state"].attributes.get("event_type")))
    only(aioclient_mock, text=with_prices({"Orlen-Bratri-Stefanu-69": 37.6}))
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(event_id).attributes["event_type"] == "favourite_dearer"
    assert "cheapest_cheaper" not in seen and hass.states.get(event_id).attributes["change"] == 1.2
    del unit


async def test_both_events_of_one_refresh_are_seen(hass, aioclient_mock):
    entry = await setup(hass, aioclient_mock)
    event_id = "event.ceny_paliv_n95_price_change"
    seen = []
    hass.bus.async_listen("state_changed", lambda e: e.data["entity_id"] == event_id and seen.append(e.data["new_state"].attributes.get("event_type")))
    only(aioclient_mock, text=with_prices({"Orlen-Bratri-Stefanu-69": 36.4}))
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert [t for t in seen if t] == ["favourite_cheaper", "cheapest_cheaper"]


async def test_no_event_when_nothing_changed_or_the_data_is_old(hass, aioclient_mock):
    entry = await setup(hass, aioclient_mock)
    coordinator = entry.runtime_data
    event_id = "event.ceny_paliv_n95_price_change"
    await coordinator.async_refresh()                                  # the same prices again
    assert hass.states.get(event_id).state == "unknown"
    only(aioclient_mock, status=503)                                   # a failed refresh keeps the last data: no news
    await coordinator.async_refresh()
    assert hass.states.get(event_id).state == "unknown"
    good(aioclient_mock)
    await coordinator.async_refresh()
    assert hass.states.get(event_id).state == "unknown"


async def test_choosing_another_favourite_is_not_a_price_change(hass, aioclient_mock):
    entry = await setup(hass, aioclient_mock)
    other = "Prim-Kutnohorska-226"
    hass.config_entries.async_update_entry(entry, options={**entry.options, "homes": {"n95": other}})
    await hass.async_block_till_done()
    assert hass.states.get("event.ceny_paliv_n95_price_change").state == "unknown"


async def test_event_entities_follow_places_and_fuels(hass, aioclient_mock):
    entry = await setup(hass, aioclient_mock, fuels=("n95", "lpg"), homes={"n95": HOME})
    from homeassistant.config_entries import ConfigSubentry
    from types import MappingProxyType

    hass.config_entries.async_add_subentry(
        entry,
        ConfigSubentry(
            data=MappingProxyType({"mode": "point", "source": "map", "latitude": PLZEN[0], "longitude": PLZEN[1], "radius": 9, "fuels": ["n95"], "homes": {}, "name": "Plzeň"}),
            subentry_type="place", title="Plzeň", unique_id=None,
        ),
    )
    await hass.async_block_till_done()
    ids = sorted(s.entity_id for s in hass.states.async_all("event"))
    assert ids == ["event.ceny_paliv_lpg_price_change", "event.ceny_paliv_n95_price_change", "event.ceny_paliv_plzen_n95_price_change"]
    # removing a fuel removes its event, the sensors' registry tidy leaves the events alone
    hass.config_entries.async_update_entry(entry, options={**entry.options, "fuels": ["n95"]})
    await hass.async_block_till_done()
    assert hass.states.get("event.ceny_paliv_lpg_price_change") is None
    assert hass.states.get("event.ceny_paliv_n95_price_change") is not None


# ----------------------------------------------------------------------------------------------- blueprints
BLUEPRINTS = pathlib.Path(__file__).parents[1] / "blueprints" / "automation" / "ceny_paliv"


@pytest.mark.parametrize("name", ["favourite_price_change", "price_below_limit", "cheap_station_nearby"])
def test_blueprints_are_valid(name):
    from homeassistant.components.blueprint.models import Blueprint
    from homeassistant.components.blueprint.schemas import BLUEPRINT_SCHEMA
    from homeassistant.util.yaml import load_yaml

    blueprint = Blueprint(load_yaml(str(BLUEPRINTS / f"{name}.yaml")), expected_domain="automation", path=name, schema=BLUEPRINT_SCHEMA)
    assert blueprint.name.startswith("Ceny paliv") and blueprint.inputs
    assert blueprint.metadata["source_url"].endswith(f"{name}.yaml")


def install_blueprint(hass, name):
    target = pathlib.Path(hass.config.path("blueprints", "automation", "ceny_paliv"))
    target.mkdir(parents=True, exist_ok=True)
    (target / f"{name}.yaml").write_text((BLUEPRINTS / f"{name}.yaml").read_text(encoding="utf-8"), encoding="utf-8")


async def test_favourite_blueprint_notifies_on_a_price_change(hass, aioclient_mock):
    entry = await setup(hass, aioclient_mock)
    install_blueprint(hass, "favourite_price_change")
    notes = async_mock_service(hass, "persistent_notification", "create")
    assert await async_setup_component(hass, "automation", {"automation": {
        "use_blueprint": {"path": "ceny_paliv/favourite_price_change.yaml", "input": {
            "price_events": "event.ceny_paliv_n95_price_change", "direction": "both", "min_change": 0.1, "language": "cs"}}}})
    await hass.async_block_till_done()
    only(aioclient_mock, text=with_prices({"Orlen-Bratri-Stefanu-69": 37.6}))
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert len(notes) == 1
    assert "cena stoupla" in notes[0].data["title"] and "37.60" in notes[0].data["message"] and "dříve 36.90" in notes[0].data["message"]
    # a change smaller than the limit is ignored
    only(aioclient_mock, text=with_prices({"Orlen-Bratri-Stefanu-69": 37.65}))
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert len(notes) == 1


async def test_price_limit_blueprint(hass, aioclient_mock):
    entry = await setup(hass, aioclient_mock)
    install_blueprint(hass, "price_below_limit")
    notes = async_mock_service(hass, "persistent_notification", "create")
    assert await async_setup_component(hass, "automation", {"automation": {
        "use_blueprint": {"path": "ceny_paliv/price_below_limit.yaml", "input": {
            "cheapest_price": "sensor.ceny_paliv_n95_top5", "limit": 36.5, "language": "en"}}}})
    await hass.async_block_till_done()
    assert not notes                                                    # 36.9 is above the limit
    only(aioclient_mock, text=with_prices({"Orlen-Bratri-Stefanu-69": 36.2}))
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert len(notes) == 1 and "price under your limit" in notes[0].data["title"]
    assert "Orlen – Bratří Štefanů 69: 36.20 Kč/l" == notes[0].data["message"]


async def test_nearby_blueprint_uses_the_distance(hass, aioclient_mock):
    mock_site(aioclient_mock)
    hass.states.async_set("person.me", "home", {"latitude": HRADEC[0], "longitude": HRADEC[1]})
    entry = point_entry(hass, source="person", entity="person.me", radius=20)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    install_blueprint(hass, "cheap_station_nearby")
    notes = async_mock_service(hass, "persistent_notification", "create")
    assert await async_setup_component(hass, "automation", {"automation": {
        "use_blueprint": {"path": "ceny_paliv/cheap_station_nearby.yaml", "input": {
            "price_events": "event.ceny_paliv_n95_price_change", "max_distance": 3, "max_price": 0, "language": "en"}}}})
    await hass.async_block_till_done()
    stations = hass.states.get("sensor.ceny_paliv_n95_top5").attributes["stations"]
    far = next(s for s in stations if s["distance_km"] > 3)
    near = next(s for s in stations if s["distance_km"] <= 3)
    # a new cheapest price far away: not interesting; then one nearby: notified
    slug = lambda s: s["url"].split("/")[3]                                    # noqa: E731
    only(aioclient_mock, text=with_prices({slug(far): stations[0]["price"] - 1.0}))
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert not notes
    only(aioclient_mock, text=with_prices({slug(near): stations[0]["price"] - 2.0}))
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert len(notes) == 1 and "cheap station nearby" in notes[0].data["title"] and "from the centre" in notes[0].data["message"]
