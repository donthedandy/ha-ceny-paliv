import json
import os
import re

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

HERE = os.path.dirname(__file__)
N95 = open(os.path.join(HERE, "fixtures", "n95.json"), encoding="utf-8").read()
LPG = open(os.path.join(HERE, "fixtures", "lpg.json"), encoding="utf-8").read()
REPO = os.path.join(os.path.dirname(HERE), "logos") + os.sep   # the logo pack of this repository
INDEX = open(REPO + "index.json").read()
RAW = "https://raw.githubusercontent.com/donthedandy/ha-ceny-paliv/main/logos/"

HOME = "Orlen-Bratri-Stefanu-69"  # favourite station used by the tests (Hradec Kralove)


def mock_logos(aioclient_mock):
    aioclient_mock.get(RAW + "index.json", text=INDEX)
    for name in ("orlen", "makro", "tesco"):
        aioclient_mock.get(RAW + f"{name}.png", content=open(REPO + name + ".png", "rb").read())


def mock_site(aioclient_mock, good=True):
    if good:
        mock_logos(aioclient_mock)
        aioclient_mock.get(re.compile(r".*fuel=n95.*"), text=N95)
        aioclient_mock.get(re.compile(r".*fuel=lpg.*"), text=LPG)
    else:
        aioclient_mock.get(re.compile(r".*"), text="<!doctype html><title>Ověřuji prohlížeč</title>", headers={"Content-Type": "text/html"})


def calls(aioclient_mock, fuel):
    return sum(1 for c in aioclient_mock.mock_calls if f"fuel={fuel}" in str(c[1]))


async def step(hass, r, **user_input):
    return await hass.config_entries.flow.async_configure(r["flow_id"], user_input)


async def start(hass):
    r = await hass.config_entries.flow.async_init("ceny_paliv", context={"source": config_entries.SOURCE_USER})
    return await step(hass, r, key="GOODKEY")


async def setup_city(hass, fuels=("n95",), language="en", homes=None, logos=()):
    """Complete setup of a town. homes: {fuel: station slug}; the station steps follow the order of `fuels`."""
    homes = homes or {}
    r = await start(hass)
    assert r["step_id"] == "mode"
    r = await step(hass, r, mode="city")
    r = await step(hass, r, city="Hradec-Kralove")
    r = await step(hass, r, fuels=list(fuels), language=language)
    for fuel in fuels:
        assert r["step_id"] == "station"
        r = await step(hass, r, station=homes.get(fuel, "__none__"))
    if r.get("step_id") == "logos":
        r = await step(hass, r, logos=list(logos))
    await hass.async_block_till_done()
    return r


def legacy_entry(hass):
    """An installation made by version 0.4.x and older: no `mode`, no `name`, no sub-entries."""
    entry = MockConfigEntry(
        domain="ceny_paliv",
        title="Ceny paliv Hradec Kralove",
        unique_id="Hradec-Kralove",
        data={"key": "GOODKEY", "city": "Hradec-Kralove"},
        options={"fuels": ["n95"], "homes": {"n95": HOME}, "language": "en"},
    )
    entry.add_to_hass(hass)
    return entry


# ------------------------------------------------------------------------------------------ setup flow
async def test_bad_key(hass, aioclient_mock):
    mock_site(aioclient_mock, good=False)
    r = await hass.config_entries.flow.async_init("ceny_paliv", context={"source": config_entries.SOURCE_USER})
    assert r["type"] == FlowResultType.FORM and r["step_id"] == "user"
    r = await step(hass, r, key="WRONG")
    assert r["type"] == FlowResultType.FORM and r["errors"] == {"base": "invalid_auth"}


async def test_full_city_flow_and_sensors(hass, aioclient_mock):
    mock_site(aioclient_mock)
    r = await start(hass)
    assert r["step_id"] == "mode"
    r = await step(hass, r, mode="city")
    assert r["step_id"] == "city"
    options = r["data_schema"].schema["city"].config["options"]
    assert {"value": "Hradec-Kralove", "label": "Hradec Králové"} in options     # the real spelling, from `addr`
    assert {"value": "Dobrany", "label": "Dobřany"} in options
    r = await step(hass, r, city="Hradec-Kralove")
    assert r["step_id"] == "fuels"
    r = await step(hass, r, fuels=["n95", "lpg"], language="cs")
    assert r["step_id"] == "station" and r["description_placeholders"]["fuel"] == "Natural 95"
    r = await step(hass, r, station=HOME)
    assert r["step_id"] == "station" and r["description_placeholders"]["fuel"] == "LPG"
    r = await step(hass, r, station="__none__")
    assert r["step_id"] == "logos"
    default = [k for k in r["data_schema"].schema if k == "logos"][0].default()
    assert {"orlen", "makro", "tesco"} <= set(default), default      # chains present in the town are preselected
    r = await step(hass, r, logos=["orlen", "makro"])
    assert r["type"] == FlowResultType.CREATE_ENTRY, r
    assert r["title"] == "Ceny paliv Hradec Králové"
    assert r["data"] == {"key": "GOODKEY", "mode": "city", "city": "Hradec-Kralove", "name": "Hradec Králové"}
    assert r["options"] == {"fuels": ["n95", "lpg"], "homes": {"n95": HOME}, "language": "cs", "logos": ["orlen", "makro"]}
    await hass.async_block_till_done()

    top = hass.states.get("sensor.ceny_paliv_n95_top5")
    assert top and float(top.state) == 36.9 and len(top.attributes["stations"]) == 5
    assert top.attributes["fuel_label"] == "Natural 95" and top.attributes["city_name"] == "Hradec Králové"
    assert top.attributes["language"] == "cs" and top.attributes["labels"]["my_station"] == "Moje stanice"
    assert top.attributes["cp_place"] == "main" and top.attributes["cp_place_name"] == "Hradec Králové"
    assert top.attributes["friendly_name"] == "Hradec Králové Natural 95 · nejlevnější"
    home = hass.states.get("sensor.ceny_paliv_n95_home")
    assert home and float(home.state) == 36.9 and home.attributes["rank"] == 1
    assert home.attributes["friendly_name"] == "Hradec Králové Orlen – Bratří Štefanů 69"
    assert hass.states.get("sensor.ceny_paliv_n95_1").attributes.get("latitude") is None   # favourite: own sensor
    p2 = hass.states.get("sensor.ceny_paliv_n95_2")
    assert p2.attributes["latitude"] and p2.attributes["friendly_name"].startswith("Hradec Králové 2 · ")
    assert p2.attributes["cp_role"] == "position" and p2.attributes["cp_index"] == 2
    assert hass.states.get("sensor.ceny_paliv_lpg_top5").attributes["friendly_name"] == "Hradec Králové LPG · nejlevnější"
    assert hass.states.get("sensor.ceny_paliv_lpg_home") is None            # none chosen -> no home sensor
    assert calls(aioclient_mock, "n95") >= 1


async def test_only_one_entry_via_flow(hass, aioclient_mock):
    mock_site(aioclient_mock)
    legacy_entry(hass)
    r = await hass.config_entries.flow.async_init("ceny_paliv", context={"source": config_entries.SOURCE_USER})
    assert r["type"] == FlowResultType.ABORT and r["reason"] == "single_instance_allowed"


async def test_language_default_follows_ha(hass, aioclient_mock):
    mock_site(aioclient_mock)
    hass.config.language = "cs"
    r = await start(hass)
    r = await step(hass, r, mode="city")
    r = await step(hass, r, city="Hradec-Kralove")
    assert r["step_id"] == "fuels"
    assert [k for k in r["data_schema"].schema if k == "language"][0].default() == "cs"


# ---------------------------------------------------------------------- existing installation untouched
async def test_legacy_entry_keeps_ids_names_and_data(hass, aioclient_mock):
    """An entry of 0.4.x (no mode, no name) must behave exactly as before: same entity ids, unique ids, names."""
    from homeassistant.helpers import entity_registry as er
    mock_site(aioclient_mock)
    entry = legacy_entry(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    top = hass.states.get("sensor.ceny_paliv_n95_top5")
    assert top and float(top.state) == 36.9 and top.attributes["city_name"] == "Hradec Kralove"   # unchanged title
    assert top.attributes["friendly_name"] == "Hradec Kralove Natural 95 · cheapest"
    assert top.attributes["cp_place"] == "main"
    assert hass.states.get("sensor.ceny_paliv_n95_home").attributes["friendly_name"] == "Hradec Kralove Orlen – Bratří Štefanů 69"
    assert hass.states.get("sensor.ceny_paliv_n95_3").attributes["friendly_name"].startswith("Hradec Kralove 3 · ")
    reg = er.async_get(hass)
    assert reg.async_get("sensor.ceny_paliv_n95_top5").unique_id == f"{entry.entry_id}_n95_top5"
    assert reg.async_get("sensor.ceny_paliv_n95_home").unique_id == f"{entry.entry_id}_n95_home"
    assert reg.async_get("sensor.ceny_paliv_n95_5").unique_id == f"{entry.entry_id}_n95_5"
    assert dict(entry.data) == {"key": "GOODKEY", "city": "Hradec-Kralove"}


async def test_legacy_options_flow_keeps_the_town(hass, aioclient_mock):
    mock_site(aioclient_mock)
    entry = legacy_entry(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    o = await hass.config_entries.options.async_init(entry.entry_id)
    assert o["step_id"] == "mode"
    assert [k for k in o["data_schema"].schema if k == "mode"][0].default() == "city"
    o = await hass.config_entries.options.async_configure(o["flow_id"], {"mode": "city"})
    assert o["step_id"] == "city"
    assert [k for k in o["data_schema"].schema if k == "city"][0].default() == "Hradec-Kralove"
    o = await hass.config_entries.options.async_configure(o["flow_id"], {"city": "Hradec-Kralove"})
    o = await hass.config_entries.options.async_configure(o["flow_id"], {"fuels": ["n95", "lpg"], "language": "cs"})
    o = await hass.config_entries.options.async_configure(o["flow_id"], {"station": HOME})      # n95 default is kept
    o = await hass.config_entries.options.async_configure(o["flow_id"], {"station": "__none__"})
    o = await hass.config_entries.options.async_configure(o["flow_id"], {"logos": []})
    assert o["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert hass.states.get("sensor.ceny_paliv_lpg_top5") is not None
    assert hass.states.get("sensor.ceny_paliv_n95_top5").attributes["labels"]["my_station"] == "Moje stanice"
    assert entry.data["city"] == "Hradec-Kralove" and entry.data["mode"] == "city"


async def test_switch_first_place_to_a_point_keeps_entities(hass, aioclient_mock):
    """Configure -> Around a point: same entity ids (so the history and the dashboards stay), new stations."""
    mock_site(aioclient_mock)
    entry = legacy_entry(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    o = await hass.config_entries.options.async_init(entry.entry_id)
    o = await hass.config_entries.options.async_configure(o["flow_id"], {"mode": "point"})
    assert o["step_id"] == "source"
    o = await hass.config_entries.options.async_configure(o["flow_id"], {"source": "map"})
    assert o["step_id"] == "point"
    o = await hass.config_entries.options.async_configure(
        o["flow_id"], {"location": {"latitude": 50.2104, "longitude": 15.8252, "radius": 4000}, "name": "Around HK"}
    )
    o = await hass.config_entries.options.async_configure(o["flow_id"], {"fuels": ["n95"], "language": "en"})
    assert o["step_id"] == "station"
    o = await hass.config_entries.options.async_configure(o["flow_id"], {"station": HOME})
    o = await hass.config_entries.options.async_configure(o["flow_id"], {"logos": []})
    assert o["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.data == {
        "key": "GOODKEY", "mode": "point", "source": "map", "latitude": 50.2104, "longitude": 15.8252, "radius": 4.0, "name": "Around HK",
    }
    top = hass.states.get("sensor.ceny_paliv_n95_top5")
    assert top.attributes["city_name"] == "Around HK" and top.attributes["stations"][0]["distance_km"] <= 4.0
    assert hass.states.get("sensor.ceny_paliv_n95_home") is not None


# ----------------------------------------------------------------------------------------- point mode
async def test_point_mode_setup(hass, aioclient_mock):
    mock_site(aioclient_mock)
    r = await start(hass)
    r = await step(hass, r, mode="point")
    assert r["step_id"] == "source"
    assert [k for k in r["data_schema"].schema if k == "source"][0].default() == "map"
    r = await step(hass, r, source="map")
    assert r["step_id"] == "point"
    default = [k for k in r["data_schema"].schema if k == "location"][0].default()
    assert default["radius"] == 10000.0 and default["latitude"] == hass.config.latitude   # Home Assistant's location
    r = await step(hass, r, location={"latitude": 50.2104, "longitude": 15.8252, "radius": 6000}, name="")
    assert r["step_id"] == "fuels"
    r = await step(hass, r, fuels=["n95"], language="en")
    r = await step(hass, r, station="__none__")
    r = await step(hass, r, logos=[])
    assert r["type"] == FlowResultType.CREATE_ENTRY
    assert r["title"] == "Ceny paliv 50.21, 15.83 · 6 km"
    assert r["data"]["mode"] == "point" and r["data"]["radius"] == 6.0
    await hass.async_block_till_done()
    top = hass.states.get("sensor.ceny_paliv_n95_top5")
    assert top and all(s["distance_km"] <= 6.0 for s in top.attributes["stations"])


async def test_plzen_the_issue(hass, aioclient_mock):
    """Issue 2: a town split in districts and a station of another village filed under the town."""
    from custom_components.ceny_paliv.api import MODE_CITY, MODE_POINT, Place, markers_in_place
    markers = json.loads(N95)["markers"]
    town = markers_in_place(markers, Place("t", "Plzeň", MODE_CITY, city="Plzen"))
    urls = " ".join(m["url"] for m in town)
    assert "Terminal-Oil-Tlustice-253" in urls and "Eurooil-Jasminova" not in urls and "Tesco-U-letiste" not in urls
    zone = markers_in_place(markers, Place("z", "Plzeň", MODE_POINT, lat=49.7475, lng=13.3776, radius_km=10))
    urls = " ".join(m["url"] for m in zone)
    assert "Eurooil-Jasminova" in urls and "Tesco-U-letiste" in urls and "AVIA-Rokycanska" in urls
    assert "Terminal-Oil-Tlustice-253" not in urls                      # 37 km away
    assert len(zone) > len(town) - 1


# ------------------------------------------------------------------------------------ several places
async def add_place(hass, entry, **place):
    r = await hass.config_entries.subentries.async_init((entry.entry_id, "place"), context={"source": "user"})
    assert r["type"] == FlowResultType.FORM and r["step_id"] == "mode"
    r = await hass.config_entries.subentries.async_configure(r["flow_id"], {"mode": place["mode"]})
    if place["mode"] == "city":
        r = await hass.config_entries.subentries.async_configure(r["flow_id"], {"city": place["city"]})
    else:
        assert r["step_id"] == "source"
        r = await hass.config_entries.subentries.async_configure(r["flow_id"], {"source": "map"})
        r = await hass.config_entries.subentries.async_configure(r["flow_id"], {"location": place["location"], "name": place.get("name", "")})
    assert r["step_id"] == "fuels" and "language" not in r["data_schema"].schema    # language is the entry's
    r = await hass.config_entries.subentries.async_configure(r["flow_id"], {"fuels": place["fuels"]})
    for fuel in place["fuels"]:
        assert r["step_id"] == "station"
        r = await hass.config_entries.subentries.async_configure(r["flow_id"], {"station": place.get("homes", {}).get(fuel, "__none__")})
    assert r["type"] == FlowResultType.CREATE_ENTRY, r
    await hass.async_block_till_done()
    return r


async def test_add_a_second_place_shares_the_download(hass, aioclient_mock):
    mock_site(aioclient_mock)
    entry = legacy_entry(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    before = dict(hass.states.get("sensor.ceny_paliv_n95_top5").attributes)
    ids_before = {s.entity_id for s in hass.states.async_all() if s.entity_id.startswith("sensor.ceny_paliv")}
    n95_calls = calls(aioclient_mock, "n95")

    brno_home = next(m["url"].split("/")[3] for m in json.loads(N95)["markers"] if m["url"].split("/")[2:3] == ["Brno"])
    r = await add_place(hass, entry, mode="city", city="Brno", fuels=["n95"], homes={"n95": brno_home})
    assert r["title"] == "Brno" and r["data"]["homes"] == {"n95": brno_home} and r["data"]["city"] == "Brno"

    # the first place is untouched: same ids, same names, same data
    assert ids_before <= {s.entity_id for s in hass.states.async_all()}
    first = hass.states.get("sensor.ceny_paliv_n95_top5")
    assert first.attributes["friendly_name"] == "Hradec Kralove Natural 95 · cheapest" == before["friendly_name"]
    assert first.state == hass.states.get("sensor.ceny_paliv_n95_top5").state and first.attributes["cp_place"] == "main"
    # the second place has its own sensors, names and place attributes
    second = hass.states.get("sensor.ceny_paliv_brno_n95_top5")
    assert second and second.attributes["friendly_name"] == "Brno Natural 95 · cheapest"
    sub_id = [s for s in entry.subentries][0]
    assert second.attributes["cp_place"] == sub_id and second.attributes["cp_place_name"] == "Brno"
    assert second.attributes["cp_fuel"] == "n95"
    assert hass.states.get("sensor.ceny_paliv_brno_n95_home") is not None
    assert hass.states.get("sensor.ceny_paliv_brno_n95_1").attributes["friendly_name"].startswith("Brno 1 · ")
    # two downloads of n95 in all: one by the "add place" form (town list) and one refresh shared by BOTH places
    assert calls(aioclient_mock, "n95") - n95_calls == 2


async def test_a_point_as_second_place_and_removal(hass, aioclient_mock):
    mock_site(aioclient_mock)
    entry = legacy_entry(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await add_place(
        hass, entry, mode="point", location={"latitude": 49.7475, "longitude": 13.3776, "radius": 10000}, name="Plzeň zone", fuels=["n95"]
    )
    top = hass.states.get("sensor.ceny_paliv_plzen_zone_n95_top5")
    assert top and top.attributes["cp_place_name"] == "Plzeň zone"
    assert "Terminal Oil" not in str([s["address"] for s in top.attributes["stations"]])
    assert all(s["distance_km"] <= 10 for s in top.attributes["stations"])
    # removing the place removes its sensors, the first place stays
    sub_id = next(iter(entry.subentries))
    assert hass.config_entries.async_remove_subentry(entry, sub_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.ceny_paliv_plzen_zone_n95_top5") is None
    assert hass.states.get("sensor.ceny_paliv_n95_top5") is not None


async def test_place_can_be_reconfigured(hass, aioclient_mock):
    mock_site(aioclient_mock)
    entry = legacy_entry(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await add_place(hass, entry, mode="city", city="Brno", fuels=["n95"])
    sub_id = next(iter(entry.subentries))
    r = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "place"), context={"source": "reconfigure", "subentry_id": sub_id}
    )
    assert r["step_id"] == "mode"
    r = await hass.config_entries.subentries.async_configure(r["flow_id"], {"mode": "city"})
    assert [k for k in r["data_schema"].schema if k == "city"][0].default() == "Brno"
    r = await hass.config_entries.subentries.async_configure(r["flow_id"], {"city": "Olomouc"})
    r = await hass.config_entries.subentries.async_configure(r["flow_id"], {"fuels": ["n95", "lpg"]})
    r = await hass.config_entries.subentries.async_configure(r["flow_id"], {"station": "__none__"})
    r = await hass.config_entries.subentries.async_configure(r["flow_id"], {"station": "__none__"})
    assert r["type"] == FlowResultType.ABORT and r["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert entry.subentries[sub_id].data["city"] == "Olomouc" and entry.subentries[sub_id].title == "Olomouc"


async def test_failed_refresh_keeps_the_data_of_every_place(hass, aioclient_mock):
    mock_site(aioclient_mock)
    entry = legacy_entry(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await add_place(hass, entry, mode="city", city="Brno", fuels=["n95"])
    aioclient_mock.clear_requests()
    aioclient_mock.get(re.compile(r".*"), status=429)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    for eid in ("sensor.ceny_paliv_n95_top5", "sensor.ceny_paliv_brno_n95_top5"):
        st = hass.states.get(eid)
        assert st.attributes["fetch_error"] == "RateLimited" and st.attributes["stations"], eid


# --------------------------------------------------------------------------------------------------- card
async def test_card_is_served(hass, hass_client_no_auth, aioclient_mock):
    """The integration serves custom:ceny-paliv-card and registers it as an extra frontend module."""
    from homeassistant.components.frontend import DATA_EXTRA_MODULE_URL
    mock_site(aioclient_mock)
    await setup_city(hass)
    urls = hass.data[DATA_EXTRA_MODULE_URL].urls
    assert any(u.startswith("/ceny_paliv_static/ceny-paliv-card.js") for u in urls), urls
    client = await hass_client_no_auth()
    resp = await client.get("/ceny_paliv_static/ceny-paliv-card.js")
    assert resp.status == 200 and resp.headers.get("Cache-Control") == "no-cache"
    assert (await client.get("/ceny_paliv_static/ceny-paliv-card.js?v=0.0.1")).status == 200
    body = await resp.text()
    assert "customElements.define('ceny-paliv-card'" in body and "ceny-paliv-card-editor" in body
    assert "cp_place" in body


MARKDOWN_TEMPLATE = """{% for s in (state_attr('sensor.ceny_paliv_n95_top5', 'stations') or []) %}
{{ s.rank }}. **{{ s.name }}** – {{ s.street }}: **{{ '%.2f' | format(s.price) }} Kč/l** · [Maps]({{ s.maps }})
{% endfor %}"""


async def test_readme_markdown_example(hass, aioclient_mock):
    """The Markdown card template of the README renders with the real sensor attributes."""
    from homeassistant.helpers.template import Template
    mock_site(aioclient_mock)
    await setup_city(hass)
    out = Template(MARKDOWN_TEMPLATE, hass).async_render()
    lines = [line for line in out.splitlines() if line.strip()]
    assert len(lines) == 5 and lines[0].startswith("1. **Orlen** – Bratří Štefanů 69:") and "google.com/maps" in lines[0]
    assert Template("{% for s in (state_attr('sensor.nope', 'stations') or []) %}x{% endfor %}", hass).async_render() == ""


# -------------------------------------------------------------------------------------------------- logos
async def test_logos_download_serve_and_remove(hass, hass_client_no_auth, aioclient_mock):
    mock_site(aioclient_mock)
    folder = hass.config.path("ceny_paliv_logos")
    os.makedirs(folder, exist_ok=True)
    open(os.path.join(folder, "mine.png"), "wb").write(open(REPO + "tesco.png", "rb").read())   # a file dropped by hand
    await setup_city(hass, logos=["orlen", "makro"])
    entry = hass.config_entries.async_entries("ceny_paliv")[0]
    assert sorted(f for f in os.listdir(folder) if f.endswith(".png")) == ["makro.png", "mine.png", "orlen.png"]
    top = hass.states.get("sensor.ceny_paliv_n95_top5")
    logos = {item["id"]: item["match"] for item in top.attributes["logos"]}
    assert logos == {"makro": ["makro"], "mine": ["mine"], "orlen": ["orlen"]}, logos
    assert top.attributes["stations"][0]["chain"] == "Orlen"
    client = await hass_client_no_auth()
    resp = await client.get("/ceny_paliv_static/logos/orlen.png")
    assert resp.status == 200 and (await resp.read()).startswith(b"\x89PNG")
    assert (await client.get("/ceny_paliv_static/logos/nope.png")).status == 404
    assert (await client.get("/ceny_paliv_static/logos/..%2Fconfiguration.png")).status in (400, 404)
    # options: untick makro, tick tesco
    o = await hass.config_entries.options.async_init(entry.entry_id)
    o = await hass.config_entries.options.async_configure(o["flow_id"], {"mode": "city"})
    o = await hass.config_entries.options.async_configure(o["flow_id"], {"city": "Hradec-Kralove"})
    o = await hass.config_entries.options.async_configure(o["flow_id"], {"fuels": ["n95"], "language": "en"})
    o = await hass.config_entries.options.async_configure(o["flow_id"], {"station": "__none__"})
    assert o["step_id"] == "logos"
    default = [k for k in o["data_schema"].schema if k == "logos"][0].default()
    assert sorted(default) == ["makro", "orlen"]
    o = await hass.config_entries.options.async_configure(o["flow_id"], {"logos": ["orlen", "tesco"]})
    assert o["type"] == FlowResultType.CREATE_ENTRY and o["data"]["logos"] == ["orlen", "tesco"]
    await hass.async_block_till_done()
    assert sorted(f for f in os.listdir(folder) if f.endswith(".png")) == ["mine.png", "orlen.png", "tesco.png"]   # mine.png is kept
    ids = [item["id"] for item in hass.states.get("sensor.ceny_paliv_n95_top5").attributes["logos"]]
    assert ids == ["mine", "orlen", "tesco"], ids


async def test_logos_step_skipped_when_pack_unreachable(hass, aioclient_mock):
    aioclient_mock.get(re.compile(r".*fuel=n95.*"), text=N95)
    aioclient_mock.get(re.compile(r".*raw.githubusercontent.*"), status=404)
    r = await start(hass)
    r = await step(hass, r, mode="city")
    r = await step(hass, r, city="Hradec-Kralove")
    r = await step(hass, r, fuels=["n95"], language="en")
    r = await step(hass, r, station="__none__")
    assert r["type"] == FlowResultType.CREATE_ENTRY and "logos" not in r["options"], r


async def test_refused_logo_is_not_stored(hass, aioclient_mock):
    aioclient_mock.get(RAW + "tesco.png", content=b"<html>not a png</html>")
    mock_site(aioclient_mock)
    await setup_city(hass, logos=["tesco"])
    assert not os.path.exists(os.path.join(hass.config.path("ceny_paliv_logos"), "tesco.png"))
