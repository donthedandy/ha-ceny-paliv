"""Data update coordinator for mBenzin."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import MBenzinError, async_fetch_markers, build_payload
from .const import (
    CONF_CITY,
    CONF_FUELS,
    CONF_HOMES,
    CONF_KEY,
    CONF_LANGUAGE,
    DEFAULT_FUELS,
    DEFAULT_LANGUAGE,
    DOMAIN,
    UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

type MBenzinConfigEntry = ConfigEntry[MBenzinCoordinator]


class MBenzinCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Fetch the prices of every selected fuel and keep the daily price history."""

    config_entry: MBenzinConfigEntry

    def __init__(self, hass: HomeAssistant, entry: MBenzinConfigEntry) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, config_entry=entry, update_interval=UPDATE_INTERVAL)
        self._store: Store[dict[str, dict]] = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
        self._history: dict[str, dict[str, list[list]]] | None = None

    @property
    def fuels(self) -> list[str]:
        return list(self.config_entry.options.get(CONF_FUELS, DEFAULT_FUELS))

    @property
    def homes(self) -> dict[str, str]:
        return dict(self.config_entry.options.get(CONF_HOMES, {}))

    @property
    def language(self) -> str:
        return self.config_entry.options.get(CONF_LANGUAGE, DEFAULT_LANGUAGE)

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        if self._history is None:
            self._history = await self._store.async_load() or {}
        session = async_get_clientsession(self.hass)
        key = self.config_entry.data[CONF_KEY]
        city = self.config_entry.data[CONF_CITY]
        homes = self.homes
        now = dt_util.now()
        result: dict[str, dict[str, Any]] = {}
        errors: list[str] = []

        for fuel in self.fuels:
            try:
                markers = await async_fetch_markers(session, key, fuel)
            except MBenzinError as err:
                err_name = type(err).__name__
                errors.append(f"{fuel}: {err_name}")
                previous = (self.data or {}).get(fuel)
                if previous is None:
                    continue
                # keep the last good data and flag the failure (the dashboard shows it)
                result[fuel] = {
                    **previous,
                    "fetch_error": err_name,
                    "last_attempt": now.isoformat(timespec="seconds"),
                    "next_update": (now + UPDATE_INTERVAL).isoformat(timespec="seconds"),
                }
                continue
            result[fuel] = build_payload(
                markers,
                fuel=fuel,
                city=city,
                home_slug=homes.get(fuel),
                history=self._history.setdefault(fuel, {}),
                now=now,
                language=self.language,
            )

        if not result:
            raise UpdateFailed("mBenzin refresh failed: " + ", ".join(errors))
        if errors:
            _LOGGER.warning("mBenzin partial refresh: %s", ", ".join(errors))
        await self._store.async_save(self._history)
        return result
