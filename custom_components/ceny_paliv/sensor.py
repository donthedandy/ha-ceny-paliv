"""Sensors: top-5 summary, favourite station and 5 map positions, per fuel.

Entity ids are predictable (used by the dashboard views):
  sensor.ceny_paliv_<fuel>_top5   cheapest price, all details in attributes
  sensor.ceny_paliv_<fuel>_home   price at your favourite station (if one is chosen)
  sensor.ceny_paliv_<fuel>_1 .. 5 the 5 cheapest stations, with latitude/longitude for the map card

The entity ids never change, but the displayed names do: the position and favourite sensors are named after the
station they currently describe ("1 · Orlen – Bratri Stefanu 69"), so standard cards show it without any template.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import station_title
from .const import FUELS, TOP
from .coordinator import CenyPalivConfigEntry, CenyPalivCoordinator

TOP_ATTRIBUTES = (
    "stations",
    "home",
    "fetched_at",
    "last_attempt",
    "fetch_error",
    "city_total",
    "excluded",
    "max_age_days",
    "fuel",
    "fuel_label",
    "unit",
    "city_name",
    "language",
    "labels",
    "next_update",
)
HOME_ATTRIBUTES = ("updated", "updated_date", "age_days", "rank", "fresh_count", "vs_cheapest", "cheapest_name", "trends", "maps")


async def async_setup_entry(hass: HomeAssistant, entry: CenyPalivConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    entities: list[CenyPalivEntity] = []
    for fuel in coordinator.fuels:
        entities.append(CenyPalivTop5Sensor(coordinator, entry, fuel))
        if coordinator.homes.get(fuel):
            entities.append(CenyPalivHomeSensor(coordinator, entry, fuel))
        entities.extend(CenyPalivPositionSensor(coordinator, entry, fuel, i) for i in range(TOP))
    async_add_entities(entities)


class CenyPalivEntity(CoordinatorEntity[CenyPalivCoordinator], SensorEntity):
    """Base: one fuel of one city."""

    _attr_has_entity_name = False  # keeps the entity ids predictable: sensor.ceny_paliv_<fuel>_...

    def __init__(self, coordinator: CenyPalivCoordinator, entry: CenyPalivConfigEntry, fuel: str, suffix: str) -> None:
        super().__init__(coordinator)
        self._fuel = fuel
        self._attr_unique_id = f"{entry.entry_id}_{fuel}_{suffix}"
        self._attr_name = f"Ceny paliv {fuel} {suffix}"
        self.entity_id = f"sensor.ceny_paliv_{fuel}_{suffix}"  # suggestion for new installs
        self._attr_native_unit_of_measurement = FUELS.get(fuel, (fuel, "Kč/l"))[1]
        # No device on purpose: with a device, Home Assistant puts the device name in front of every entity name
        # ("Ceny paliv Hradec Kralove 1 · Orlen – ..."), which hides the station in narrow cards.

    @property
    def _payload(self) -> dict[str, Any]:
        return (self.coordinator.data or {}).get(self._fuel) or {}

    @property
    def _label(self) -> str:
        return self._payload.get("fuel_label") or FUELS.get(self._fuel, (self._fuel,))[0]

    def _word(self, key: str, default: str) -> str:
        return (self._payload.get("labels") or {}).get(key, default)


class CenyPalivTop5Sensor(CenyPalivEntity):
    _attr_icon = "mdi:gas-station"

    def __init__(self, coordinator, entry, fuel) -> None:
        super().__init__(coordinator, entry, fuel, "top5")

    @property
    def name(self) -> str:
        return f"{self._label} · {self._word('name_cheapest', 'cheapest')}"

    @property
    def native_value(self) -> float | None:
        stations = self._payload.get("stations") or []
        return stations[0]["price"] if stations else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = {k: self._payload.get(k) for k in TOP_ATTRIBUTES}
        attrs.update(cp_fuel=self._fuel, cp_role="top5")
        return attrs


class CenyPalivHomeSensor(CenyPalivEntity):
    """Favourite station. state_class=measurement -> long-term statistics (the 30-day graph)."""

    _attr_icon = "mdi:gas-station-in-use"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry, fuel) -> None:
        super().__init__(coordinator, entry, fuel, "home")

    @property
    def name(self) -> str:
        home = self._payload.get("home")
        if home:
            return station_title(home["name"], home["address"])
        return f"{self._label} · {self._word('name_home', 'favourite station')}"

    @property
    def _home(self) -> dict[str, Any] | None:
        return self._payload.get("home")

    @property
    def available(self) -> bool:
        return super().available and self._home is not None

    @property
    def native_value(self) -> float | None:
        return self._home["price"] if self._home else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        home = self._home or {}
        attrs = {"station": home.get("address"), "latitude": home.get("lat"), "longitude": home.get("lng")}
        attrs.update({k: home.get(k) for k in HOME_ATTRIBUTES})
        attrs.update(cp_fuel=self._fuel, cp_role="home")
        return attrs


class CenyPalivPositionSensor(CenyPalivEntity):
    """The n-th cheapest station. Has latitude/longitude so the map card can show it."""

    _attr_icon = "mdi:gas-station"

    def __init__(self, coordinator, entry, fuel, index: int) -> None:
        super().__init__(coordinator, entry, fuel, str(index + 1))
        self._index = index

    @property
    def name(self) -> str:
        s = self._station
        if s:
            return f"{self._index + 1} · {station_title(s['name'], s['address'])}"
        return f"{self._label} · {self._index + 1}"

    @property
    def _station(self) -> dict[str, Any] | None:
        stations = self._payload.get("stations") or []
        return stations[self._index] if len(stations) > self._index else None

    @property
    def available(self) -> bool:
        return super().available and self._station is not None

    @property
    def native_value(self) -> float | None:
        return self._station["price"] if self._station else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        s = self._station
        attrs: dict[str, Any] = {"cp_fuel": self._fuel, "cp_role": "position", "cp_index": self._index + 1}
        if s:
            # the favourite station is drawn by its own sensor on the map: no coordinates here
            attrs.update(
                station=s["address"],
                latitude=None if s["home"] else s["lat"],
                longitude=None if s["home"] else s["lng"],
            )
        return attrs
