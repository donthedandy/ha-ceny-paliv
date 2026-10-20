"""Sensors: top-5 summary, favourite station and 5 map positions, per fuel.

Entity ids are predictable (used by the dashboard views):
  sensor.mbenzin_<fuel>_top5   cheapest price, all details in attributes
  sensor.mbenzin_<fuel>_home   price at your favourite station (if one is chosen)
  sensor.mbenzin_<fuel>_1 .. 5 the 5 cheapest stations, with latitude/longitude for the map card
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import pretty
from .const import CONF_CITY, DOMAIN, FUELS, TOP
from .coordinator import MBenzinConfigEntry, MBenzinCoordinator

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


async def async_setup_entry(hass: HomeAssistant, entry: MBenzinConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    entities: list[MBenzinEntity] = []
    for fuel in coordinator.fuels:
        entities.append(MBenzinTop5Sensor(coordinator, entry, fuel))
        if coordinator.homes.get(fuel):
            entities.append(MBenzinHomeSensor(coordinator, entry, fuel))
        entities.extend(MBenzinPositionSensor(coordinator, entry, fuel, i) for i in range(TOP))
    async_add_entities(entities)


class MBenzinEntity(CoordinatorEntity[MBenzinCoordinator], SensorEntity):
    """Base: one fuel of one city."""

    _attr_has_entity_name = False  # keeps the entity ids predictable: sensor.mbenzin_<fuel>_...

    def __init__(self, coordinator: MBenzinCoordinator, entry: MBenzinConfigEntry, fuel: str, suffix: str) -> None:
        super().__init__(coordinator)
        self._fuel = fuel
        self._attr_unique_id = f"{entry.entry_id}_{fuel}_{suffix}"
        self._attr_name = f"mBenzin {fuel} {suffix}"
        self._attr_native_unit_of_measurement = FUELS.get(fuel, (fuel, "Kč/l"))[1]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"mBenzin {pretty(entry.data[CONF_CITY])}",
            manufacturer="mBenzin.cz",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def _payload(self) -> dict[str, Any]:
        return (self.coordinator.data or {}).get(self._fuel) or {}


class MBenzinTop5Sensor(MBenzinEntity):
    _attr_icon = "mdi:gas-station"

    def __init__(self, coordinator, entry, fuel) -> None:
        super().__init__(coordinator, entry, fuel, "top5")

    @property
    def native_value(self) -> float | None:
        stations = self._payload.get("stations") or []
        return stations[0]["price"] if stations else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {k: self._payload.get(k) for k in TOP_ATTRIBUTES}


class MBenzinHomeSensor(MBenzinEntity):
    """Favourite station. state_class=measurement -> long-term statistics (the 30-day graph)."""

    _attr_icon = "mdi:gas-station-in-use"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry, fuel) -> None:
        super().__init__(coordinator, entry, fuel, "home")

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
        return attrs


class MBenzinPositionSensor(MBenzinEntity):
    """The n-th cheapest station. Has latitude/longitude so the map card can show it."""

    _attr_icon = "mdi:gas-station"

    def __init__(self, coordinator, entry, fuel, index: int) -> None:
        super().__init__(coordinator, entry, fuel, str(index + 1))
        self._index = index

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
        if not s:
            return {}
        # the favourite station is drawn by its own sensor on the map: no coordinates here
        return {
            "station": s["address"],
            "latitude": None if s["home"] else s["lat"],
            "longitude": None if s["home"] else s["lng"],
        }
