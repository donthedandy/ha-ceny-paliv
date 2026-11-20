"""Price-change events: the favourite station got cheaper or dearer, the cheapest price of the place dropped.

One event entity per place and fuel (`event.ceny_paliv_<fuel>_price_change` for the first place). Each refresh is
compared with the one before; the entity id stays the same when another favourite station is chosen, so automations
and blueprints keep working. A restart or a reload never reports a change by itself: the first prices are the baseline.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import MAIN_PLACE, Place
from .const import DOMAIN
from .coordinator import CenyPalivConfigEntry, CenyPalivCoordinator
from .entity import CenyPalivBaseEntity

PARALLEL_UPDATES = 0  # the coordinator does the fetching; entities only read its data

FAVOURITE_CHEAPER = "favourite_cheaper"
FAVOURITE_DEARER = "favourite_dearer"
CHEAPEST_CHEAPER = "cheapest_cheaper"
EVENT_TYPES = [FAVOURITE_CHEAPER, FAVOURITE_DEARER, CHEAPEST_CHEAPER]


async def async_setup_entry(hass: HomeAssistant, entry: CenyPalivConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    wanted: set[str] = set()
    per_place: list[tuple[Place, list[CenyPalivPriceChangeEvent]]] = []
    for place in coordinator.places:
        events = [CenyPalivPriceChangeEvent(coordinator, entry, place, fuel) for fuel in place.fuels]
        wanted |= {e.unique_id for e in events if e.unique_id}
        per_place.append((place, events))
    # the events of a fuel that was removed go with it
    registry = er.async_get(hass)
    for reg in er.async_entries_for_config_entry(registry, entry.entry_id):
        if reg.platform == DOMAIN and reg.domain == "event" and reg.unique_id not in wanted:
            registry.async_remove(reg.entity_id)
    for place, events in per_place:
        if place.key == MAIN_PLACE:
            async_add_entities(events)
        else:
            async_add_entities(events, config_subentry_id=place.key)


def _station(data: dict[str, Any] | None) -> tuple[str, float] | None:
    """Who and how much, to compare two refreshes: the station URL and its price."""
    if not data or data.get("price") is None or not data.get("url"):
        return None
    return str(data["url"]), float(data["price"])


class CenyPalivPriceChangeEvent(CenyPalivBaseEntity, EventEntity):
    _entity_domain = "event"
    _attr_event_types = EVENT_TYPES
    _attr_icon = "mdi:gas-station"

    def __init__(self, coordinator: CenyPalivCoordinator, entry: CenyPalivConfigEntry, place: Place, fuel: str) -> None:
        super().__init__(coordinator, entry, place, fuel, "price_change")
        self._favourite: tuple[str, float] | None = None
        self._cheapest: float | None = None

    @property
    def name(self) -> str:
        return f"{self._label} · {self._word('name_events', 'price change')}{self._where}"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._remember(self._payload)

    def _remember(self, payload: dict[str, Any]) -> None:
        self._favourite = _station(payload.get("home"))
        stations = payload.get("stations") or []
        self._cheapest = float(stations[0]["price"]) if stations else None

    @callback
    def _handle_coordinator_update(self) -> None:
        payload = self._payload
        if not payload or payload.get("fetch_error"):
            super()._handle_coordinator_update()  # the last known prices: nothing new to compare
            return
        favourite, cheapest = self._favourite, self._cheapest
        self._remember(payload)
        common = {
            "fuel": payload.get("fuel_label"),
            "unit": payload.get("unit"),
            "place": self._place.title,
        }
        home = payload.get("home")
        now = _station(home)
        # the same station as before (another favourite chosen in the meantime is not a price change)
        if home and now and favourite and now[0] == favourite[0] and now[1] != favourite[1]:
            self._fire(FAVOURITE_CHEAPER if now[1] < favourite[1] else FAVOURITE_DEARER, home, favourite[1], common)
        stations = payload.get("stations") or []
        if stations and cheapest is not None and float(stations[0]["price"]) < cheapest:
            self._fire(CHEAPEST_CHEAPER, stations[0], cheapest, common)
        super()._handle_coordinator_update()

    def _fire(self, event_type: str, station: dict[str, Any], previous: float, common: dict[str, Any]) -> None:
        price = float(station["price"])
        self._trigger_event(
            event_type,
            {
                **common,
                "station": station.get("title"),
                "address": station.get("address"),
                "price": price,
                "previous_price": previous,
                "change": round(price - previous, 2),
                "distance_km": station.get("distance_km"),
                "maps": station.get("maps"),
            },
        )
        self.async_write_ha_state()  # one state per event: two events in one refresh are both seen
