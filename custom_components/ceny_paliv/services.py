"""The ceny_paliv.refresh action: load the prices now, without flooding mBenzin.cz."""
from __future__ import annotations

try:  # Home Assistant 2026.x validates with probatio (it maps voluptuous onto it)
    import probatio as vol
except ImportError:  # pragma: no cover - Home Assistant 2025.x
    import voluptuous as vol  # type: ignore[no-redef]

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .coordinator import CenyPalivConfigEntry

SERVICE_REFRESH = "refresh"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"
REFRESH_SCHEMA = vol.Schema({vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string})


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the action once, when the integration is set up (not per entry)."""

    async def async_refresh(call: ServiceCall) -> None:
        failed: list[str] = []
        for entry in _loaded_entries(hass, call.data.get(ATTR_CONFIG_ENTRY_ID)):
            coordinator = entry.runtime_data
            await coordinator.async_refresh_now()
            if not coordinator.last_update_success:
                failed.append(f"{entry.title} ({coordinator.last_exception})")
            failed.extend(f"{entry.title} · {fuel} ({err})" for fuel, err in coordinator.failed_fuels.items())
        if failed:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="refresh_failed",
                translation_placeholders={"failed": ", ".join(failed)},
            )

    hass.services.async_register(DOMAIN, SERVICE_REFRESH, async_refresh, schema=REFRESH_SCHEMA)


def _loaded_entries(hass: HomeAssistant, entry_id: str | None) -> list[CenyPalivConfigEntry]:
    if entry_id is None:
        entries = [e for e in hass.config_entries.async_entries(DOMAIN) if e.state is ConfigEntryState.LOADED]
        if not entries:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="no_loaded_entries")
        return entries
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="entry_not_found", translation_placeholders={"entry_id": entry_id}
        )
    if entry.state is not ConfigEntryState.LOADED:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="entry_not_loaded", translation_placeholders={"title": entry.title}
        )
    return [entry]
