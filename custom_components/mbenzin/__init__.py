"""mBenzin.cz fuel prices."""
from __future__ import annotations

from homeassistant.core import HomeAssistant

from .coordinator import MBenzinConfigEntry, MBenzinCoordinator

PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: MBenzinConfigEntry) -> bool:
    coordinator = MBenzinCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_reload(hass: HomeAssistant, entry: MBenzinConfigEntry) -> None:
    """Options changed (fuels / favourite stations): reload."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: MBenzinConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
