"""Where a point place is centred: a fixed point, the Home Assistant home, a zone, or a person that moves."""
from __future__ import annotations

import math
from typing import Any

from homeassistant.core import HomeAssistant

from .const import SOURCE_HOME, SOURCE_MAP, SOURCE_PERSON, SOURCE_ZONE

PERSON_MISSING = "person_unavailable"
ZONE_MISSING = "zone_unavailable"
INVALID = "invalid_coordinates"


def _coordinates(latitude: Any, longitude: Any) -> tuple[float, float] | None:
    try:
        lat, lng = float(latitude), float(longitude)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(lat) and math.isfinite(lng)) or abs(lat) > 90 or abs(lng) > 180:
        return None
    return lat, lng


def centre_of(
    hass: HomeAssistant, source: str, entity: str | None, lat: float | None, lng: float | None
) -> tuple[tuple[float, float] | None, str | None]:
    """The centre of a point place and, when it cannot be found, why: (None, PERSON_MISSING | ZONE_MISSING | INVALID).

    A person or device whose location is unknown keeps the area at home. A person or zone that does not exist
    leaves the area at home too, but reports it, so a Repairs notice can say what to fix.
    """
    home = _coordinates(hass.config.latitude, hass.config.longitude)
    if source == SOURCE_HOME:
        return (home, None) if home else (None, INVALID)
    if source == SOURCE_PERSON:
        state = hass.states.get(entity or "")
        if state is None:
            return home, PERSON_MISSING
        return _coordinates(state.attributes.get("latitude"), state.attributes.get("longitude")) or home, None
    if source == SOURCE_ZONE:
        state = hass.states.get(entity or "")
        if state is None:
            return home, ZONE_MISSING
        found = _coordinates(state.attributes.get("latitude"), state.attributes.get("longitude"))
        return (found, None) if found else (home, INVALID)
    found = _coordinates(lat, lng)  # SOURCE_MAP
    return (found, None) if found else (None, INVALID)


def is_dynamic(source: str) -> bool:
    """The centre can change after the setup (it has to be looked up at every refresh)."""
    return source in (SOURCE_HOME, SOURCE_PERSON, SOURCE_ZONE)


__all__ = ["INVALID", "PERSON_MISSING", "SOURCE_MAP", "ZONE_MISSING", "centre_of", "is_dynamic"]
