"""Tests of 0.8.1: the logo of the station that holds a rank follows the station; "Worth it" is gone from the card."""
import pathlib

from test_flow import mock_site, setup_city

ROOT = pathlib.Path(__file__).parent.parent / "custom_components" / "ceny_paliv"
CARD = (ROOT / "frontend" / "ceny-paliv-card.js").read_text()


async def test_a_rank_sensor_shows_the_logo_of_its_station(hass, aioclient_mock):
    mock_site(aioclient_mock)
    await setup_city(hass, logos=["orlen", "makro"])
    pictures = {}
    for rank in range(1, 6):
        state = hass.states.get(f"sensor.ceny_paliv_n95_{rank}")
        station = state.attributes["station"]
        pictures[rank] = (station, state.attributes.get("entity_picture"))
    chains = {"orlen": "Orlen", "makro": "Makro"}
    known = [p for _, p in pictures.values() if p]
    assert known, pictures                                            # at least one station has a logo
    for _, picture in pictures.values():
        assert picture is None or picture in {f"/ceny_paliv_static/logos/{c}.png" for c in chains}


async def test_without_logos_no_picture(hass, aioclient_mock):
    mock_site(aioclient_mock)
    await setup_city(hass)
    for rank in range(1, 6):
        assert hass.states.get(f"sensor.ceny_paliv_n95_{rank}").attributes.get("entity_picture") is None


def test_worth_it_is_gone_from_the_card():
    for word in ("worth", "Worth", "consumption", "detour", "vyplat"):
        assert word not in CARD, word


def test_the_distance_can_start_from_the_home_of_home_assistant():
    assert "this._hass.config" in CARD and "home: true" in CARD
