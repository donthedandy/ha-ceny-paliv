"""Tests of the 0.6.0 work: reliability (429, key refused, malformed data), diagnostics, Repairs, refresh action."""
import datetime as dt
import json
import re

import pytest
from homeassistant.components.diagnostics import REDACTED
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr, entity_registry as er, issue_registry as ir
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.diagnostics import get_diagnostics_for_config_entry

from custom_components.ceny_paliv import api
from custom_components.ceny_paliv.api import retry_after_seconds, usable_marker
from custom_components.ceny_paliv.const import DOMAIN

from test_flow import HOME, N95, calls, mock_site


def entry_for(hass, fuels=("n95",), homes=None):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Ceny paliv Hradec Kralove",
        unique_id=DOMAIN,
        data={"key": "GOODKEY", "mode": "city", "city": "Hradec-Kralove"},
        options={"fuels": list(fuels), "homes": homes if homes is not None else {"n95": HOME}, "language": "en"},
    )
    entry.add_to_hass(hass)
    return entry


async def setup(hass, aioclient_mock, **kw):
    mock_site(aioclient_mock)
    entry = entry_for(hass, **kw)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def good(aioclient_mock):
    """Back to a working site (the earlier fake answers are forgotten)."""
    aioclient_mock.clear_requests()
    mock_site(aioclient_mock)


def only(aioclient_mock, **response):
    """Every download from now on gets this answer."""
    aioclient_mock.clear_requests()
    aioclient_mock.get(re.compile(r".*mbenzin.*"), **response)


# ---------------------------------------------------------------------------------------------- unit
def test_retry_after_seconds_and_dates():
    now = dt.datetime(2026, 11, 20, 12, 0, tzinfo=dt.timezone.utc)
    assert retry_after_seconds("120") == 120
    assert retry_after_seconds(" 30 ") == 30
    assert retry_after_seconds("Fri, 20 Nov 2026 12:05:00 GMT", now) == 300
    assert retry_after_seconds("Fri, 20 Nov 2026 11:00:00 GMT", now) == 0          # a date in the past
    assert retry_after_seconds("999999999", now) == 24 * 3600                      # capped at 24 hours
    for bad in (None, "", "soon", "-5", "1e3", "Fri, 99 Nov 2026"):
        assert retry_after_seconds(bad, now) is None, bad


def test_usable_marker_rejects_malformed_data():
    good = {"url": "/Ceny-benzinu-a-nafty/Praha/Orlen-Foo-1/1", "name": "Orlen", "price": 36.9, "lat": 50.0, "lng": 14.0}
    assert usable_marker(good)
    for bad in (
        None, "x", [], {},
        {**good, "price": "36.9"}, {**good, "price": True}, {**good, "price": float("nan")},
        {**good, "lat": None}, {**good, "lng": float("inf")}, {**good, "name": 5}, {**good, "url": None}, {**good, "url": "x"},
    ):
        assert not usable_marker(bad), bad


async def test_malformed_markers_are_skipped_not_fatal(hass, aioclient_mock):
    data = json.loads(N95)
    data["markers"] = [None, "junk", {"url": "/x"}, {**data["markers"][0], "price": "free"}] + data["markers"]
    good(aioclient_mock)
    aioclient_mock.clear_requests()
    aioclient_mock.get(re.compile(r".*fuel=n95.*"), text=json.dumps(data))
    entry = entry_for(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.ceny_paliv_n95_top5").state == "36.9"


async def test_station_without_a_town_in_its_url_does_not_crash_point_mode(hass, aioclient_mock):
    data = json.loads(N95)
    ref = next(m for m in data["markers"] if "Hradec-Kralove" in m["url"])
    data["markers"].append({**ref, "id": 4242, "url": "/stanice/4242", "name": "Neznama", "addr": "Hlavni 1, Hradec Kralove", "price": 30.1})
    good(aioclient_mock)
    aioclient_mock.clear_requests()
    aioclient_mock.get(re.compile(r".*fuel=n95.*"), text=json.dumps(data))
    entry = MockConfigEntry(
        domain=DOMAIN, title="Point", unique_id=DOMAIN,
        data={"key": "GOODKEY", "mode": "point", "latitude": ref["lat"], "longitude": ref["lng"], "radius": 5},
        options={"fuels": ["n95"], "homes": {}, "language": "en"},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    top = hass.states.get("sensor.ceny_paliv_n95_top5")
    assert top.state == "30.1"
    station = top.attributes["stations"][0]
    assert station["name"] == "Neznama" and station["address"] == "Hlavni 1, Hradec Kralove"
    assert api.station_slug({"url": "/stanice/4242"}) == "4242"


# ------------------------------------------------------------------------------------------ the key
async def test_key_goes_in_the_query_by_default_and_never_in_errors(hass, aioclient_mock):
    await setup(hass, aioclient_mock)
    url = str(aioclient_mock.mock_calls[-1][1])
    assert "klic=GOODKEY" in url and "fuel=" in url


async def test_key_in_a_header_when_enabled(hass, aioclient_mock, monkeypatch):
    monkeypatch.setattr(api, "KEY_IN_HEADER", True)
    await setup(hass, aioclient_mock)
    call = aioclient_mock.mock_calls[-1]
    assert "GOODKEY" not in str(call[1]) and call[3]["X-Mbenzin-Klic"] == "GOODKEY"


async def test_connection_error_text_never_holds_the_key(hass, aioclient_mock):
    import aiohttp
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    aioclient_mock.get(re.compile(r".*"), exc=aiohttp.ClientConnectionError("cannot reach https://x/?klic=SECRETKEY"))
    with pytest.raises(api.CannotConnect) as err:
        await api.async_fetch_markers(async_get_clientsession(hass), "SECRETKEY", "n95")
    assert "SECRETKEY" not in repr(err.value) and err.value.__cause__ is None


# -------------------------------------------------------------------------------------------- 429
async def test_rate_limit_keeps_data_and_waits(hass, aioclient_mock):
    entry = await setup(hass, aioclient_mock)
    coordinator = entry.runtime_data
    only(aioclient_mock, status=429, headers={"Retry-After": "120"})
    await coordinator.async_refresh()
    payload = coordinator.data["main"]["n95"]
    assert payload["fetch_error"] == "RateLimited" and payload["stations"], "the last data stays"
    assert coordinator.failed_fuels == {"n95": "RateLimited"}
    assert hass.states.get("sensor.ceny_paliv_n95_top5").state == "36.9"      # still available: it is only a short wait
    before = len(aioclient_mock.mock_calls)
    await coordinator.async_refresh()
    await coordinator.async_refresh()
    assert len(aioclient_mock.mock_calls) == before, "no request while mBenzin asked us to wait"
    # the wait is over: the next refresh downloads again and the error is cleared
    coordinator._cooldown_until = hass.loop.time() - 1
    good(aioclient_mock)
    await coordinator.async_refresh()
    assert coordinator.failed_fuels == {} and coordinator.data["main"]["n95"]["fetch_error"] is None


async def test_rate_limit_without_retry_after_waits_almost_one_interval(hass, aioclient_mock):
    entry = await setup(hass, aioclient_mock)
    coordinator = entry.runtime_data
    only(aioclient_mock, status=429)
    await coordinator.async_refresh()
    assert 5.5 * 3600 < coordinator._cooldown_until - hass.loop.time() < 6 * 3600


# ---------------------------------------------------------------------------------------- key refused
async def test_refused_key_asks_for_a_new_one(hass, aioclient_mock):
    entry = await setup(hass, aioclient_mock)
    coordinator = entry.runtime_data
    only(aioclient_mock, status=403)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    flows = [f for f in hass.config_entries.flow.async_progress() if f["context"]["source"] == "reauth"]
    assert len(flows) == 1 and flows[0]["step_id"] == "reauth_confirm"
    # a wrong new key is refused, a good one is saved and the entry reloads
    r = await hass.config_entries.flow.async_configure(flows[0]["flow_id"], {"key": "STILLWRONG"})
    assert r["errors"] == {"base": "cannot_connect"} or r["errors"] == {"base": "invalid_auth"}
    good(aioclient_mock)
    r = await hass.config_entries.flow.async_configure(flows[0]["flow_id"], {"key": " NEWKEY "})
    assert r["type"].value == "abort" and r["reason"] == "reauth_successful"
    await hass.async_block_till_done()
    assert entry.data["key"] == "NEWKEY" and entry.state is ConfigEntryState.LOADED


async def test_html_answer_asks_for_a_new_key_only_when_it_repeats(hass, aioclient_mock):
    entry = await setup(hass, aioclient_mock)
    coordinator = entry.runtime_data
    only(aioclient_mock, text="<!doctype html><title>Ověřuji prohlížeč</title>", headers={"Content-Type": "text/html"})
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert not [f for f in hass.config_entries.flow.async_progress() if f["context"]["source"] == "reauth"], "one outage page is not a refused key"
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert [f for f in hass.config_entries.flow.async_progress() if f["context"]["source"] == "reauth"]


async def test_an_outage_resets_the_rejection_count(hass, aioclient_mock):
    entry = await setup(hass, aioclient_mock)
    coordinator = entry.runtime_data
    html = dict(text="<!doctype html>", headers={"Content-Type": "text/html"})
    only(aioclient_mock, **html)
    await coordinator.async_refresh()
    good(aioclient_mock)
    await coordinator.async_refresh()           # a good answer in between
    only(aioclient_mock, **html)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert not [f for f in hass.config_entries.flow.async_progress() if f["context"]["source"] == "reauth"]


# ------------------------------------------------------------------------- unavailable + Repairs issue
async def test_no_fresh_prices_for_a_day_makes_sensors_unavailable_and_raises_an_issue(hass, aioclient_mock):
    entry = await setup(hass, aioclient_mock)
    coordinator = entry.runtime_data
    issues = ir.async_get(hass)
    assert not issues.issues
    # the last good download is 25 hours old
    old = (dt_util.now() - dt.timedelta(hours=25)).isoformat(timespec="seconds")
    for place in coordinator.data.values():
        for payload in place.values():
            payload["fetched_at"] = old
    only(aioclient_mock, status=503)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.stale_fuels == {"n95"}
    assert hass.states.get("sensor.ceny_paliv_n95_top5").state == "unavailable"
    assert hass.states.get("sensor.ceny_paliv_n95_1").state == "unavailable"
    issue = issues.async_get_issue(DOMAIN, f"no_data_{entry.entry_id}")
    assert issue and issue.translation_key == "no_data" and "Natural 95" in issue.translation_placeholders["fuels"]
    # mBenzin answers again: the sensors come back and the issue goes away by itself
    good(aioclient_mock)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.stale_fuels == set()
    assert hass.states.get("sensor.ceny_paliv_n95_top5").state == "36.9"
    assert issues.async_get_issue(DOMAIN, f"no_data_{entry.entry_id}") is None


async def test_removing_the_entry_removes_the_issue(hass, aioclient_mock):
    entry = await setup(hass, aioclient_mock)
    coordinator = entry.runtime_data
    for place in coordinator.data.values():
        for payload in place.values():
            payload["fetched_at"] = (dt_util.now() - dt.timedelta(hours=30)).isoformat()
    only(aioclient_mock, status=503)
    await coordinator.async_refresh()
    assert ir.async_get(hass).issues
    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert not ir.async_get(hass).issues


async def test_first_refresh_failing_with_no_data_is_retried_by_home_assistant(hass, aioclient_mock):
    only(aioclient_mock, status=503)
    entry = entry_for(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY


# --------------------------------------------------------------------------------------- the action
async def test_refresh_action_downloads_old_data_but_not_recent_data(hass, aioclient_mock):
    entry = await setup(hass, aioclient_mock)
    start = calls(aioclient_mock, "n95")
    await hass.services.async_call(DOMAIN, "refresh", {}, blocking=True)
    assert calls(aioclient_mock, "n95") == start, "the data was downloaded a moment ago: it is not downloaded again"
    coordinator = entry.runtime_data
    markers, when = coordinator._downloads["n95"]
    coordinator._downloads["n95"] = (markers, when - dt.timedelta(minutes=31))
    await hass.services.async_call(DOMAIN, "refresh", {"config_entry_id": entry.entry_id}, blocking=True)
    assert calls(aioclient_mock, "n95") == start + 1


async def test_refresh_action_reports_failures_and_bad_targets(hass, aioclient_mock):
    entry = await setup(hass, aioclient_mock)
    coordinator = entry.runtime_data
    markers, when = coordinator._downloads["n95"]
    coordinator._downloads["n95"] = (markers, when - dt.timedelta(hours=1))
    only(aioclient_mock, status=503)
    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(DOMAIN, "refresh", {}, blocking=True)
    assert err.value.translation_key == "refresh_failed" and "n95" in err.value.translation_placeholders["failed"]
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(DOMAIN, "refresh", {"config_entry_id": "nope"}, blocking=True)
    assert err.value.translation_key == "entry_not_found"
    await hass.config_entries.async_unload(entry.entry_id)
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(DOMAIN, "refresh", {}, blocking=True)
    assert err.value.translation_key == "no_loaded_entries"
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(DOMAIN, "refresh", {"config_entry_id": entry.entry_id}, blocking=True)
    assert err.value.translation_key == "entry_not_loaded"


# ------------------------------------------------------------------------------------------ diagnostics
async def test_diagnostics_hold_no_key_and_no_favourite(hass, hass_client, aioclient_mock):
    entry = await setup(hass, aioclient_mock)
    diag = await get_diagnostics_for_config_entry(hass, hass_client, entry)
    text = json.dumps(diag)
    assert "GOODKEY" not in text and HOME not in text
    assert diag["entry"]["data"]["key"] == REDACTED and diag["entry"]["options"]["homes"] == REDACTED
    assert diag["entry"]["title"] == REDACTED
    assert all(sub["title"] == REDACTED for sub in diag["entry"]["places"].values())
    assert "hradec" not in text.lower()  # the town (entry title and city) stays out of the file
    assert diag["coordinator"]["last_update_success"] is True and diag["coordinator"]["last_exception"] is None
    fuel = diag["places"]["main"]["n95"]
    assert fuel["stations"] == 5 and fuel["home_found"] is True and fuel["fetch_error"] is None


# ------------------------------------------------------------------------------- registry and devices
async def test_one_device_per_place_and_ids_do_not_change(hass, aioclient_mock):
    entry = await setup(hass, aioclient_mock)
    registry = er.async_get(hass)
    top = registry.async_get("sensor.ceny_paliv_n95_top5")
    assert top.unique_id == f"{entry.entry_id}_n95_top5"
    device = dr.async_get(hass).async_get(top.device_id)
    assert device.name == "Hradec Kralove" and device.manufacturer == "mBenzin.cz"
    assert {registry.async_get(f"sensor.ceny_paliv_n95_{i}").device_id for i in range(1, 6)} == {top.device_id}
    state = hass.states.get("sensor.ceny_paliv_n95_top5")
    assert state.attributes["attribution"] == "Ceny: mbenzin.cz"
    assert state.name == "Hradec Kralove Natural 95 · cheapest"      # the device (the place) comes first


async def test_removing_a_fuel_removes_its_sensors(hass, aioclient_mock):
    entry = await setup(hass, aioclient_mock, fuels=("n95", "lpg"), homes={"n95": HOME})
    registry = er.async_get(hass)
    assert registry.async_get("sensor.ceny_paliv_lpg_top5") and registry.async_get("sensor.ceny_paliv_lpg_3")
    hass.config_entries.async_update_entry(entry, options={**entry.options, "fuels": ["n95"]})
    await hass.async_block_till_done()
    assert registry.async_get("sensor.ceny_paliv_lpg_top5") is None and registry.async_get("sensor.ceny_paliv_lpg_3") is None
    assert registry.async_get("sensor.ceny_paliv_n95_top5") and registry.async_get("sensor.ceny_paliv_n95_home")


async def test_removing_the_favourite_archives_its_sensor_and_choosing_it_again_restores_it(hass, aioclient_mock):
    entry = await setup(hass, aioclient_mock)
    registry = er.async_get(hass)
    assert registry.async_get("sensor.ceny_paliv_n95_home").disabled_by is None
    hass.config_entries.async_update_entry(entry, options={**entry.options, "homes": {}})
    await hass.async_block_till_done()
    home = registry.async_get("sensor.ceny_paliv_n95_home")
    assert home is not None, "kept for its history"
    assert home.disabled_by is er.RegistryEntryDisabler.INTEGRATION and home.entity_category.value == "diagnostic"
    hass.config_entries.async_update_entry(entry, options={**entry.options, "homes": {"n95": HOME}})
    await hass.async_block_till_done()
    home = registry.async_get("sensor.ceny_paliv_n95_home")
    assert home.disabled_by is None and home.entity_category is None
    assert hass.states.get("sensor.ceny_paliv_n95_home").state == "36.9"


async def test_a_second_place_gets_its_own_device(hass, aioclient_mock):
    entry = await setup(hass, aioclient_mock)
    from types import MappingProxyType

    from homeassistant.config_entries import ConfigSubentry

    hass.config_entries.async_add_subentry(
        entry,
        ConfigSubentry(
            data=MappingProxyType({"mode": "point", "latitude": 50.2, "longitude": 15.8, "radius": 5, "fuels": ["n95"], "homes": {}}),
            subentry_type="place", title="Near home", unique_id=None,
        ),
    )
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    main = registry.async_get("sensor.ceny_paliv_n95_top5").device_id
    other = next(e for e in registry.entities.values() if e.platform == DOMAIN and "near_home" in e.entity_id and e.entity_id.endswith("top5"))
    assert other.device_id and other.device_id != main
    assert dr.async_get(hass).async_get(other.device_id).name == "Near home"


async def test_diagnostics_forget_an_old_exception_after_recovery(hass, hass_client, aioclient_mock):
    entry = await setup(hass, aioclient_mock)
    entry.runtime_data.last_exception = RuntimeError("old")      # what Home Assistant keeps after a recovery
    diag = await get_diagnostics_for_config_entry(hass, hass_client, entry)
    assert diag["coordinator"]["last_exception"] is None
