"""Ceny paliv: Czech fuel prices (data from mBenzin.cz)."""
from __future__ import annotations

from pathlib import Path

from aiohttp import web

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .const import CARD_URL, CARD_VERSION, LOGO_URL
from .coordinator import CenyPalivConfigEntry, CenyPalivCoordinator
from .logos import ID_RE, logo_dir

PLATFORMS = ["sensor"]


class CenyPalivCardView(HomeAssistantView):
    """Serves the card with `Cache-Control: no-cache`: the browser always revalidates, so it never keeps a stale
    copy (Home Assistant's own pages carry no cache headers, so an old page may still point to an old URL)."""

    url = CARD_URL
    name = "ceny_paliv:card"
    requires_auth = False

    def __init__(self, path: Path) -> None:
        self._path = path

    async def get(self, request: web.Request) -> web.StreamResponse:
        return web.FileResponse(self._path, headers={"Cache-Control": "no-cache"})


class CenyPalivLogoView(HomeAssistantView):
    """Serves the downloaded chain logos (<config>/ceny_paliv_logos/<id>.png). No auth: the browser loads them in <img>."""

    url = LOGO_URL + "/{logo_id}.png"
    name = "ceny_paliv:logo"
    requires_auth = False

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass

    async def get(self, request: web.Request, logo_id: str) -> web.StreamResponse:
        path = logo_dir(self._hass) / f"{logo_id}.png"
        if not ID_RE.match(logo_id) or not await self._hass.async_add_executor_job(path.is_file):
            return web.Response(status=404)
        return web.FileResponse(path, headers={"Cache-Control": "no-cache"})


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Serve the dashboard card (custom:ceny-paliv-card) and load it in the frontend."""
    card = Path(__file__).parent / "frontend" / "ceny-paliv-card.js"
    hass.http.register_view(CenyPalivCardView(card))
    hass.http.register_view(CenyPalivLogoView(hass))
    add_extra_js_url(hass, f"{CARD_URL}?v={CARD_VERSION}")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: CenyPalivConfigEntry) -> bool:
    coordinator = CenyPalivCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_reload(hass: HomeAssistant, entry: CenyPalivConfigEntry) -> None:
    """Options changed (fuels / favourite stations): reload."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: CenyPalivConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
