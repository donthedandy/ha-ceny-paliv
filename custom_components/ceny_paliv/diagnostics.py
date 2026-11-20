"""Diagnostics download: the settings and refresh state of the places, without the key or where the user lives."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import HomeAssistant

from .const import CONF_HOMES, CONF_KEY, CONF_LOCATION
from .coordinator import CenyPalivConfigEntry

# the personal key, the centre of a point place and the favourite stations (they point to where the user lives)
TO_REDACT = {CONF_KEY, CONF_LOCATION, CONF_LATITUDE, CONF_LONGITUDE, CONF_HOMES}

# per place and fuel: how the last refresh went; the station lists themselves are left out
PAYLOAD_KEYS = ("fetched_at", "last_attempt", "fetch_error", "next_update", "max_age_days", "city_total", "excluded", "language")


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: CenyPalivConfigEntry) -> dict[str, Any]:
    coordinator = entry.runtime_data
    places: dict[str, Any] = {}
    for place_key, fuels in (coordinator.data or {}).items():
        places[place_key] = {}
        for fuel, payload in fuels.items():
            home = payload.get("home")
            places[place_key][fuel] = {
                **{key: payload.get(key) for key in PAYLOAD_KEYS if key in payload},
                "stations": len(payload.get("stations") or []),
                "home_found": home is not None,
                "home_rank": home.get("rank") if home else None,
                "logos": len(payload.get("logos") or []),
            }
    return async_redact_data(
        {
            "entry": {
                "title": entry.title,
                "data": dict(entry.data),
                "options": dict(entry.options),
                "places": {sid: {"title": sub.title, "data": dict(sub.data)} for sid, sub in entry.subentries.items()},
            },
            "coordinator": {
                "last_update_success": coordinator.last_update_success,
                # HA keeps the last exception after a recovery: only report it while the last refresh failed
                "last_exception": None if coordinator.last_update_success else repr(coordinator.last_exception),
                "update_interval": str(coordinator.update_interval),
                "failed_fuels": sorted(coordinator.failed_fuels),
                "stale_fuels": sorted(coordinator.stale_fuels),
            },
            "places": places,
        },
        TO_REDACT,
    )
