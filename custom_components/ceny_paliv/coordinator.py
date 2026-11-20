"""Data update coordinator for Ceny paliv."""
from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    MAIN_PLACE,
    MODE_CITY,
    InvalidAuth,
    MBenzinError,
    Place,
    RateLimited,
    async_fetch_markers,
    build_payload,
    pretty,
)
from .const import (
    CONF_CITY,
    CONF_FUELS,
    CONF_HOMES,
    CONF_KEY,
    CONF_LANGUAGE,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_MODE,
    CONF_NAME,
    CONF_RADIUS,
    DEFAULT_FUELS,
    DEFAULT_LANGUAGE,
    DEFAULT_RADIUS_KM,
    DOMAIN,
    FORCED_REFRESH_MIN_AGE,
    FUELS,
    SOURCE_URL,
    STALE_DATA_AFTER,
    SUBENTRY_PLACE,
    UPDATE_INTERVAL,
)
from .logos import logo_dir, scan_logos

_LOGGER = logging.getLogger(__name__)

type CenyPalivConfigEntry = ConfigEntry[CenyPalivCoordinator]


def _place(key: str, title: str, data: Any, fuels: Any, homes: Any) -> Place:
    mode = data.get(CONF_MODE, MODE_CITY)
    return Place(
        key=key,
        title=title,
        mode=mode,
        city=data.get(CONF_CITY),
        lat=data.get(CONF_LATITUDE),
        lng=data.get(CONF_LONGITUDE),
        radius_km=float(data.get(CONF_RADIUS, DEFAULT_RADIUS_KM)),
        fuels=tuple(fuels),
        homes=dict(homes),
    )


def places_of(entry: ConfigEntry) -> list[Place]:
    """The places of an entry: the first one lives in the entry itself (as in the versions before places existed,
    so existing installations keep their sensors and history), the others are sub-entries."""
    data = entry.data
    if data.get(CONF_MODE, MODE_CITY) == MODE_CITY and data.get(CONF_CITY):
        title = data.get(CONF_NAME) or pretty(data[CONF_CITY])
    else:
        title = data.get(CONF_NAME) or "Point"
    places = [
        _place(
            MAIN_PLACE,
            title,
            data,
            entry.options.get(CONF_FUELS, DEFAULT_FUELS),
            entry.options.get(CONF_HOMES, {}),
        )
    ]
    for sub in entry.subentries.values():
        if sub.subentry_type == SUBENTRY_PLACE:
            places.append(
                _place(sub.subentry_id, sub.title, sub.data, sub.data.get(CONF_FUELS, DEFAULT_FUELS), sub.data.get(CONF_HOMES, {}))
            )
    return places


def no_data_issue_id(entry_id: str) -> str:
    return f"no_data_{entry_id}"


class CenyPalivCoordinator(DataUpdateCoordinator[dict[str, dict[str, dict[str, Any]]]]):
    """Fetch the prices of every fuel used by any place (one download per fuel) and keep the daily price history.

    `data` is {place key: {fuel: payload}}.
    """

    config_entry: CenyPalivConfigEntry

    def __init__(self, hass: HomeAssistant, entry: CenyPalivConfigEntry) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, config_entry=entry, update_interval=UPDATE_INTERVAL)
        self._store: Store[dict[str, dict]] = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
        self._history: dict[str, dict[str, list[list]]] | None = None
        self.places: list[Place] = places_of(entry)
        # the last download of each fuel (nationwide markers + when), kept in memory for the refresh action
        self._downloads: dict[str, tuple[list[dict[str, Any]], datetime]] = {}
        self._cooldown_until: float | None = None  # loop time until which mBenzin asked us to wait (HTTP 429)
        self._key_rejections = 0  # consecutive refreshes in which every fuel was refused for the key
        self._force = False  # set while the refresh action runs
        # fuels whose last refresh failed (with the error), and the ones without fresh data for STALE_DATA_AFTER
        self.failed_fuels: dict[str, str] = {}
        self.stale_fuels: set[str] = set()

    @property
    def language(self) -> str:
        return self.config_entry.options.get(CONF_LANGUAGE, DEFAULT_LANGUAGE)

    @property
    def fuels(self) -> list[str]:
        """Every fuel needed by at least one place."""
        out: list[str] = []
        for place in self.places:
            out.extend(f for f in place.fuels if f not in out)
        return out

    async def async_refresh_now(self) -> None:
        """The refresh action: download again every fuel whose data is older than FORCED_REFRESH_MIN_AGE."""
        self._force = True
        try:
            await self.async_refresh()
        finally:
            self._force = False

    async def _async_markers(self, session: Any, key: str, fuel: str, now: datetime) -> list[dict[str, Any]]:
        """The nationwide markers of a fuel: downloaded, or the recent download when the action runs too often."""
        cached = self._downloads.get(fuel)
        if self._force and cached is not None and now - cached[1] < FORCED_REFRESH_MIN_AGE:
            return cached[0]
        loop_time = self.hass.loop.time()
        if self._cooldown_until is not None and self._cooldown_until > loop_time:
            raise RateLimited(self._cooldown_until - loop_time)
        try:
            markers = await async_fetch_markers(session, key, fuel)
        except RateLimited as err:
            # mBenzin asks us to wait: no request for any fuel until then (it counts per key, not per fuel)
            delay = err.retry_after if err.retry_after is not None else UPDATE_INTERVAL.total_seconds() - 600
            self._cooldown_until = loop_time + delay
            raise
        self._cooldown_until = None
        self._downloads[fuel] = (markers, now)
        return markers

    async def _async_update_data(self) -> dict[str, dict[str, dict[str, Any]]]:
        if self._history is None:
            self._history = await self._store.async_load() or {}
        session = async_get_clientsession(self.hass)
        key = self.config_entry.data[CONF_KEY]
        now = dt_util.now()
        result: dict[str, dict[str, dict[str, Any]]] = {p.key: {} for p in self.places}
        errors: dict[str, str] = {}
        auth_errors: list[InvalidAuth] = []

        for fuel in self.fuels:
            users = [p for p in self.places if fuel in p.fuels]
            try:
                markers = await self._async_markers(session, key, fuel, now)
            except MBenzinError as err:
                errors[fuel] = type(err).__name__
                if isinstance(err, InvalidAuth):
                    auth_errors.append(err)
                for place in users:
                    previous = ((self.data or {}).get(place.key) or {}).get(fuel)
                    if previous is None:
                        continue
                    # keep the last good data and flag the failure (the dashboard shows it)
                    result[place.key][fuel] = {
                        **previous,
                        "fetch_error": errors[fuel],
                        "last_attempt": now.isoformat(timespec="seconds"),
                        "next_update": (now + UPDATE_INTERVAL).isoformat(timespec="seconds"),
                    }
                continue
            for place in users:
                result[place.key][fuel] = build_payload(
                    markers,
                    fuel=fuel,
                    place=place,
                    home_slug=place.homes.get(fuel),
                    history=self._history.setdefault(fuel, {}),
                    now=now,
                    language=self.language,
                )

        if self.fuels and len(auth_errors) == len(self.fuels):
            self._key_rejections += 1
            # 401/403 is certain; an HTML answer only after it repeats (6 h later), so an outage page cannot ask for
            # a new key. Home Assistant then shows the "Reauthenticate" prompt.
            if any(err.definite for err in auth_errors) or self._key_rejections >= 2:
                raise ConfigEntryAuthFailed(translation_domain=DOMAIN, translation_key="invalid_auth")
        else:
            self._key_rejections = 0

        self._update_stale(result, now)
        if not any(result.values()):
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"errors": ", ".join(f"{f}: {e}" for f, e in errors.items()) or "-"},
            )
        # log each change once, not on every refresh
        for fuel in sorted(errors.keys() - self.failed_fuels.keys()):
            _LOGGER.warning("Ceny paliv: %s prices cannot be refreshed from mBenzin.cz (%s)", fuel, errors[fuel])
        for fuel in sorted(self.failed_fuels.keys() - errors.keys()):
            _LOGGER.info("Ceny paliv: %s prices are refreshed again", fuel)
        self.failed_fuels = errors
        logos = await self.hass.async_add_executor_job(scan_logos, logo_dir(self.hass))
        for fuels in result.values():
            for payload in fuels.values():
                payload["logos"] = logos
        await self._store.async_save(self._history)
        return result

    def _update_stale(self, result: dict[str, dict[str, dict[str, Any]]], now: datetime) -> None:
        """Fuels whose newest data is older than STALE_DATA_AFTER: unavailable sensors + a Repairs issue."""
        newest: dict[str, datetime] = {}
        for fuels in result.values():
            for fuel, payload in fuels.items():
                fetched = dt_util.parse_datetime(payload.get("fetched_at") or "")
                if fetched is not None and (fuel not in newest or fetched > newest[fuel]):
                    newest[fuel] = fetched
        self.stale_fuels = {fuel for fuel, fetched in newest.items() if now - fetched > STALE_DATA_AFTER}
        entry = self.config_entry
        if self.stale_fuels:
            oldest = min(newest[fuel] for fuel in self.stale_fuels)
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                no_data_issue_id(entry.entry_id),
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="no_data",
                translation_placeholders={
                    "title": entry.title,
                    "fuels": ", ".join(FUELS.get(f, (f,))[0] for f in sorted(self.stale_fuels)),
                    "since": dt_util.as_local(oldest).strftime("%Y-%m-%d %H:%M"),
                    "url": SOURCE_URL,
                },
            )
        else:
            ir.async_delete_issue(self.hass, DOMAIN, no_data_issue_id(entry.entry_id))
