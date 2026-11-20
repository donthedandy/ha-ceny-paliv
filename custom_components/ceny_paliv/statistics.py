"""Long-term statistics per station and fuel, independent of entities, places and config entries.

The favourite sensor's own statistics belong to its entity: a new favourite or a new setup starts them again. These
external statistics are keyed by the station itself (its mBenzin URL), so the price history of a station goes on when
it is chosen again, in another place, or after the integration was removed and added again.
"""
from __future__ import annotations

from datetime import date, datetime, time
import hashlib
from typing import Any

from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import async_add_external_statistics
from homeassistant.core import HomeAssistant, callback
from homeassistant.util import dt as dt_util

from .const import DOMAIN, FUELS

try:  # newer Home Assistant versions describe the mean by its type
    from homeassistant.components.recorder.models import StatisticMeanType
except ImportError:  # pragma: no cover - older versions only know has_mean
    StatisticMeanType = None  # type: ignore[assignment,misc]

_METADATA_FIELDS = StatisticMetaData.__annotations__


def station_statistic_id(fuel: str, url: str) -> str:
    """'ceny_paliv:n95_3fa2b1c4d5e6': one statistic per fuel and station, the same in every place and setup."""
    return f"{DOMAIN}:{fuel}_{hashlib.sha256(url.encode()).hexdigest()[:12]}"


def _metadata(statistic_id: str, name: str, unit: str) -> StatisticMetaData:
    metadata: dict[str, Any] = {
        "has_sum": False,
        "name": name,
        "source": DOMAIN,
        "statistic_id": statistic_id,
        "unit_of_measurement": unit,
    }
    # the recorder builds its database row from these keys: give exactly the ones this version knows
    if "mean_type" in _METADATA_FIELDS and StatisticMeanType is not None:
        metadata["mean_type"] = StatisticMeanType.ARITHMETIC
    else:  # pragma: no cover
        metadata["has_mean"] = True
    if "unit_class" in _METADATA_FIELDS:
        metadata["unit_class"] = None
    return metadata  # type: ignore[return-value]


@callback
def async_import_station_statistics(
    hass: HomeAssistant, fuel: str, home: dict[str, Any], log: list[list[Any]], now: datetime
) -> str | None:
    """Write the favourite station's price of this hour and its daily log (idempotent); return the statistic id.

    The daily log (one price a day, kept 35 days) goes in at noon of each day, so a station chosen as favourite brings
    along the history the integration already has.
    """
    url, price = home.get("url"), home.get("price")
    if not isinstance(url, str) or not isinstance(price, (int, float)) or isinstance(price, bool):
        return None
    statistic_id = station_statistic_id(fuel, url)
    if "recorder" not in hass.config.components:
        return statistic_id
    label, unit = FUELS.get(fuel, (fuel, "Kč/l"))
    hour = dt_util.as_utc(now).replace(minute=0, second=0, microsecond=0)
    rows: dict[datetime, float] = {}
    for item in log:
        try:
            day, value = date.fromisoformat(item[0]), float(item[1])
        except (TypeError, ValueError, IndexError):
            continue
        start = dt_util.as_utc(datetime.combine(day, time(12), tzinfo=dt_util.get_default_time_zone()))
        if start <= hour:
            rows[start] = value
    rows[hour] = float(price)
    async_add_external_statistics(
        hass,
        _metadata(statistic_id, f"{label} · {home.get('title') or home.get('name') or url}", unit),
        [StatisticData(start=start, mean=value, min=value, max=value) for start, value in sorted(rows.items())],
    )
    return statistic_id
