"""Data update coordinator for Ceny paliv."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import MAIN_PLACE, MODE_CITY, MODE_POINT, MBenzinError, Place, async_fetch_markers, build_payload, pretty
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

    async def _async_update_data(self) -> dict[str, dict[str, dict[str, Any]]]:
        if self._history is None:
            self._history = await self._store.async_load() or {}
        session = async_get_clientsession(self.hass)
        key = self.config_entry.data[CONF_KEY]
        now = dt_util.now()
        result: dict[str, dict[str, dict[str, Any]]] = {p.key: {} for p in self.places}
        errors: list[str] = []

        for fuel in self.fuels:
            users = [p for p in self.places if fuel in p.fuels]
            try:
                markers = await async_fetch_markers(session, key, fuel)
            except MBenzinError as err:
                err_name = type(err).__name__
                errors.append(f"{fuel}: {err_name}")
                for place in users:
                    previous = ((self.data or {}).get(place.key) or {}).get(fuel)
                    if previous is None:
                        continue
                    # keep the last good data and flag the failure (the dashboard shows it)
                    result[place.key][fuel] = {
                        **previous,
                        "fetch_error": err_name,
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

        if not any(result.values()):
            raise UpdateFailed("Ceny paliv refresh failed (mBenzin.cz): " + ", ".join(errors))
        if errors:
            _LOGGER.warning("Ceny paliv partial refresh: %s", ", ".join(errors))
        logos = await self.hass.async_add_executor_job(scan_logos, logo_dir(self.hass))
        for fuels in result.values():
            for payload in fuels.values():
                payload["logos"] = logos
        await self._store.async_save(self._history)
        return result
