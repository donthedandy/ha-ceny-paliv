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
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from homeassistant.util import slugify

from .api import MAIN_PLACE, Place, station_title
from .const import ATTRIBUTION, DOMAIN, FUELS, SOURCE_URL, TOP
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
        if reg.platform != DOMAIN or not reg.unique_id:
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


class CenyPalivEntity(CoordinatorEntity[CenyPalivCoordinator], SensorEntity):
    """Base: one fuel of one city."""

    _attr_has_entity_name = False  # keeps the entity ids predictable: sensor.ceny_paliv_<fuel>_...
    _attr_attribution = ATTRIBUTION  # mBenzin asks for the source to be shown with its prices

    def __init__(
        self, coordinator: CenyPalivCoordinator, entry: CenyPalivConfigEntry, place: Place, fuel: str, suffix: str
    ) -> None:
        super().__init__(coordinator)
        self._place = place
        self._fuel = fuel
        if place.key == MAIN_PLACE:
            # the first place keeps the ids it had before places existed
            self._attr_unique_id = f"{entry.entry_id}_{fuel}_{suffix}"
            self.entity_id = f"sensor.ceny_paliv_{fuel}_{suffix}"  # suggestion for new installs
        else:
            self._attr_unique_id = f"{entry.entry_id}_{place.key}_{fuel}_{suffix}"
            self.entity_id = f"sensor.ceny_paliv_{slugify(place.title)}_{fuel}_{suffix}"
        self._attr_name = f"Ceny paliv {fuel} {suffix}"
        self._attr_native_unit_of_measurement = FUELS.get(fuel, (fuel, "Kč/l"))[1]
        # One device per place. Entity names do not use the device name (has_entity_name is False), so the station
        # stays visible in narrow cards.
        device_id = entry.entry_id if place.key == MAIN_PLACE else f"{entry.entry_id}_{place.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=f"Ceny paliv {place.title}",
            entry_type=DeviceEntryType.SERVICE,
            manufacturer="mBenzin.cz",
            configuration_url=SOURCE_URL,
        )

    @property
    def available(self) -> bool:
        """Unavailable when the fuel has had no fresh prices for a day (a short outage keeps the last prices)."""
        return super().available and self._fuel not in self.coordinator.stale_fuels

    @property
    def _payload(self) -> dict[str, Any]:
        return ((self.coordinator.data or {}).get(self._place.key) or {}).get(self._fuel) or {}

    @property
    def _where(self) -> str:
        """' · <place>' once there are several places, so the names stay distinct (the first place keeps its names)."""
        if self._place.key == MAIN_PLACE or len(self.coordinator.places) < 2:
            return ""
        return f" · {self._place.title}"

    @property
    def _label(self) -> str:
        return self._payload.get("fuel_label") or FUELS.get(self._fuel, (self._fuel,))[0]

    def _word(self, key: str, default: str) -> str:
        return (self._payload.get("labels") or {}).get(key, default)


class CenyPalivTop5Sensor(CenyPalivEntity):
    _attr_icon = "mdi:gas-station"

    def __init__(self, coordinator, entry, place, fuel) -> None:
        super().__init__(coordinator, entry, place, fuel, "top5")

    @property
    def name(self) -> str:
        return f"{self._label} · {self._word('name_cheapest', 'cheapest')}{self._where}"

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
            return station_title(home["name"], home["address"]) + self._where
        return f"{self._label} · {self._word('name_home', 'favourite station')}{self._where}"

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
            return f"{self._index + 1} · {station_title(s['name'], s['address'])}{self._where}"
        return f"{self._label} · {self._index + 1}{self._where}"

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
