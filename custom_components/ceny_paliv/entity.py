"""Base entity of Ceny paliv: one fuel of one place, grouped under the place's device."""
from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .api import MAIN_PLACE, Place
from .const import ATTRIBUTION, DOMAIN, FUELS, SOURCE_URL
from .coordinator import CenyPalivConfigEntry, CenyPalivCoordinator


class CenyPalivBaseEntity(CoordinatorEntity[CenyPalivCoordinator]):
    """Shared by the sensors and the event entities."""

    _attr_has_entity_name = True  # the friendly name is "<place> <entity name>" (recent HA versions always add the device)
    _attr_attribution = ATTRIBUTION  # mBenzin asks for the source to be shown with its prices
    _entity_domain = "sensor"

    def __init__(
        self, coordinator: CenyPalivCoordinator, entry: CenyPalivConfigEntry, place: Place, fuel: str, suffix: str
    ) -> None:
        super().__init__(coordinator)
        self._place = place
        self._fuel = fuel
        if place.key == MAIN_PLACE:
            # the first place keeps the ids it had before places existed
            self._attr_unique_id = f"{entry.entry_id}_{fuel}_{suffix}"
            self.entity_id = f"{self._entity_domain}.ceny_paliv_{fuel}_{suffix}"  # suggestion for new installs
        else:
            self._attr_unique_id = f"{entry.entry_id}_{place.key}_{fuel}_{suffix}"
            self.entity_id = f"{self._entity_domain}.ceny_paliv_{slugify(place.title)}_{fuel}_{suffix}"
        self._attr_native_unit_of_measurement = FUELS.get(fuel, (fuel, "Kč/l"))[1]
        # One device per place, named after the place; the friendly names read "<place> <entity name>".
        device_id = entry.entry_id if place.key == MAIN_PLACE else f"{entry.entry_id}_{place.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=place.title,
            model="Ceny paliv",
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
    def _label(self) -> str:
        return self._payload.get("fuel_label") or FUELS.get(self._fuel, (self._fuel,))[0]

    def _word(self, key: str, default: str) -> str:
        return (self._payload.get("labels") or {}).get(key, default)
