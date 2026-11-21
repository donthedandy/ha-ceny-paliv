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
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import MAIN_PLACE, Place, station_title
from .const import DOMAIN, TOP
from .coordinator import CenyPalivConfigEntry, CenyPalivCoordinator
from .entity import CenyPalivBaseEntity

TOP_ATTRIBUTES = (
    "stations",
    "map_stations",
    "centre",
    "averages",
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
    "logos",
)
HOME_ATTRIBUTES = ("updated", "updated_date", "age_days", "rank", "fresh_count", "vs_cheapest", "cheapest_name", "trends", "maps")


async def async_setup_entry(hass: HomeAssistant, entry: CenyPalivConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    per_place: list[tuple[Place, list[CenyPalivEntity]]] = []
    for place in coordinator.places:
        entities: list[CenyPalivEntity] = []
        for fuel in place.fuels:
            entities.append(CenyPalivTop5Sensor(coordinator, entry, place, fuel))
            if place.homes.get(fuel):
                entities.append(CenyPalivHomeSensor(coordinator, entry, place, fuel))
            entities.extend(CenyPalivPositionSensor(coordinator, entry, place, fuel, i) for i in range(TOP))
            entities.extend(CenyPalivAverageSensor(coordinator, entry, place, fuel, kind) for kind in AVERAGE_KINDS)
        per_place.append((place, entities))
    # before the entities are added: a favourite sensor that comes back must not be added while still disabled
    _tidy_registry(hass, entry, {e.unique_id for _, entities in per_place for e in entities if e.unique_id})
    for place, entities in per_place:
        if place.key == MAIN_PLACE:
            async_add_entities(entities)
        else:
            async_add_entities(entities, config_subentry_id=place.key)


def _tidy_registry(hass: HomeAssistant, entry: CenyPalivConfigEntry, wanted: set[str]) -> None:
    """Keep the entity registry in line with the settings.

    The sensors of a fuel that was removed are deleted. The favourite sensor of a fuel that is still followed but no
    longer has a favourite is kept for its history, as a disabled diagnostic entity; it comes back when a favourite
    is chosen again.
    """
    registry = er.async_get(hass)
    for reg in er.async_entries_for_config_entry(registry, entry.entry_id):
        if reg.platform != DOMAIN or reg.domain != "sensor" or not reg.unique_id:
            continue
        if reg.unique_id in wanted:
            if reg.unique_id.endswith("_home") and reg.disabled_by is er.RegistryEntryDisabler.INTEGRATION:
                registry.async_update_entity(reg.entity_id, disabled_by=None, entity_category=None)
            continue
        if reg.unique_id.endswith("_home") and reg.unique_id[: -len("_home")] + "_top5" in wanted:
            registry.async_update_entity(
                reg.entity_id, disabled_by=er.RegistryEntryDisabler.INTEGRATION, entity_category=EntityCategory.DIAGNOSTIC
            )
        else:
            registry.async_remove(reg.entity_id)


class CenyPalivEntity(CenyPalivBaseEntity, SensorEntity):
    """Base of the sensors: one fuel of one place."""

    def __init__(
        self, coordinator: CenyPalivCoordinator, entry: CenyPalivConfigEntry, place: Place, fuel: str, suffix: str
    ) -> None:
        super().__init__(coordinator, entry, place, fuel, suffix)
        self._attr_name = f"Ceny paliv {fuel} {suffix}"


class CenyPalivTop5Sensor(CenyPalivEntity):
    _attr_icon = "mdi:gas-station"
    _attr_state_class = SensorStateClass.MEASUREMENT  # long-term statistics: the card draws the cheapest price over 30 days
    # big and only useful to the card: not worth filling the database with them
    _unrecorded_attributes = frozenset({"map_stations", "averages", "labels", "logos", "stations"})

    def __init__(self, coordinator, entry, place, fuel) -> None:
        super().__init__(coordinator, entry, place, fuel, "top5")

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
        attrs.update(cp_fuel=self._fuel, cp_role="top5", cp_place=self._place.key, cp_place_name=self._place.title)
        return attrs


class CenyPalivHomeSensor(CenyPalivEntity):
    """Favourite station. state_class=measurement -> long-term statistics (the 30-day graph)."""

    _attr_icon = "mdi:gas-station-in-use"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry, place, fuel) -> None:
        super().__init__(coordinator, entry, place, fuel, "home")

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
        attrs.update(cp_fuel=self._fuel, cp_role="home", cp_place=self._place.key, cp_place_name=self._place.title)
        return attrs


class CenyPalivPositionSensor(CenyPalivEntity):
    """The n-th cheapest station. Has latitude/longitude so the map card can show it."""

    _attr_icon = "mdi:gas-station"

    def __init__(self, coordinator, entry, place, fuel, index: int) -> None:
        super().__init__(coordinator, entry, place, fuel, str(index + 1))
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
        attrs: dict[str, Any] = {
            "cp_fuel": self._fuel,
            "cp_role": "position",
            "cp_index": self._index + 1,
            "cp_place": self._place.key,
            "cp_place_name": self._place.title,
        }
        if s:
            # the favourite station is drawn by its own sensor on the map: no coordinates here
            attrs.update(
                station=s["address"],
                latitude=None if s["home"] else s["lat"],
                longitude=None if s["home"] else s["lng"],
            )
        return attrs


AVERAGE_KINDS = ("national_average", "region_average", "area_average")


class CenyPalivAverageSensor(CenyPalivEntity):
    """Average price of the up-to-date stations: the country, the region of the place, or the place itself.

    state_class=measurement gives long-term statistics. Computed from the same download as everything else.
    """

    _attr_icon = "mdi:chart-line"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry, place, fuel, kind: str) -> None:
        super().__init__(coordinator, entry, place, fuel, kind)
        self._kind = kind

    @property
    def _data(self) -> dict[str, Any] | None:
        averages = self._payload.get("averages") or {}
        return averages.get({"national_average": "country", "region_average": "region", "area_average": "area"}[self._kind])

    @property
    def name(self) -> str:
        word = {
            "national_average": self._word("avg_national", "average · Czech Republic"),
            "region_average": self._word("avg_region", "average · region"),
            "area_average": self._word("avg_area", "average · area"),
        }[self._kind]
        return f"{self._label} · {word}"

    @property
    def available(self) -> bool:
        return super().available and bool(self._data) and self._data.get("average") is not None

    @property
    def native_value(self) -> float | None:
        return self._data.get("average") if self._data else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self._data or {}
        attrs: dict[str, Any] = {"station_count": data.get("station_count")}
        if self._kind == "national_average":
            attrs.update(median=data.get("median"), regions=data.get("regions"))
        elif self._kind == "region_average":
            attrs.update(
                region=data.get("name"), region_code=data.get("code"), rank=data.get("rank"), vs_national=data.get("vs_national")
            )
        else:
            attrs.update(
                region=data.get("region"),
                region_rank=data.get("region_rank"),
                vs_national=data.get("vs_national"),
                vs_region=data.get("vs_region"),
            )
        attrs.update(cp_fuel=self._fuel, cp_role=self._kind, cp_place=self._place.key, cp_place_name=self._place.title)
        return attrs
