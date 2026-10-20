"""Config flow: key -> city -> fuels -> favourite station for each fuel."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    CannotConnect,
    InvalidAuth,
    MBenzinError,
    RateLimited,
    async_fetch_markers,
    city_of,
    city_options,
    pretty,
    station_options,
)
from .const import (
    CONF_CITY,
    CONF_FUELS,
    CONF_HOMES,
    CONF_KEY,
    CONF_LANGUAGE,
    CONF_LOGOS,
    CONF_STATION,
    DEFAULT_FUELS,
    DEFAULT_LANGUAGE,
    DOMAIN,
    FUELS,
    LANGUAGES,
    NONE_VALUE,
)
from .logos import async_fetch_index, async_sync, chains_in, installed_ids, logo_dir


def _error_key(err: MBenzinError) -> str:
    if isinstance(err, InvalidAuth):
        return "invalid_auth"
    if isinstance(err, RateLimited):
        return "rate_limited"
    return "cannot_connect"


class _FuelStationSteps:
    """Shared by the config flow and the options flow: choose fuels, then a favourite station per fuel."""

    _key: str
    _city: str
    _fuels: list[str]
    _language: str
    _queue: list[str]
    _homes: dict[str, str]
    _stations: dict[str, list[dict[str, str]]]
    _defaults_fuels: list[str] = DEFAULT_FUELS
    _defaults_language: str | None = None
    _defaults_homes: dict[str, str] = {}
    _defaults_logos: list[str] | None = None
    _chains: set[str]
    _logos: list[str] | None = None

    async def async_step_fuels(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            fuels = user_input[CONF_FUELS]
            if not fuels:
                errors[CONF_FUELS] = "no_fuel"
            else:
                session = async_get_clientsession(self.hass)
                stations: dict[str, list[dict[str, str]]] = {}
                chains: set[str] = set()
                try:
                    for fuel in fuels:
                        markers = await async_fetch_markers(session, self._key, fuel)
                        stations[fuel] = station_options(markers, self._city)
                        chains |= {m.get("chain") or m["name"] for m in markers if city_of(m) == self._city}
                except MBenzinError as err:
                    errors["base"] = _error_key(err)
                else:
                    self._fuels, self._stations, self._chains = fuels, stations, chains
                    self._language = user_input[CONF_LANGUAGE]
                    self._queue, self._homes = list(fuels), {}
                    return await self.async_step_station()
        schema = vol.Schema(
            {
                vol.Required(CONF_FUELS, default=self._defaults_fuels): SelectSelector(
                    SelectSelectorConfig(
                        options=[{"value": k, "label": v[0]} for k, v in FUELS.items()],
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
                vol.Required(CONF_LANGUAGE, default=self._default_language()): SelectSelector(
                    SelectSelectorConfig(
                        options=[{"value": k, "label": v} for k, v in LANGUAGES.items()],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="fuels", data_schema=schema, errors=errors)

    def _default_language(self) -> str:
        """Language of the dashboard texts: the saved one, else Home Assistant's own language."""
        if self._defaults_language in LANGUAGES:
            return self._defaults_language
        ha_language = (self.hass.config.language or DEFAULT_LANGUAGE).split("-")[0]
        return ha_language if ha_language in LANGUAGES else DEFAULT_LANGUAGE

    async def async_step_station(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        fuel = self._queue[0]
        if user_input is not None:
            choice = user_input.get(CONF_STATION, NONE_VALUE)
            if choice != NONE_VALUE:
                self._homes[fuel] = choice
            self._queue.pop(0)
            if self._queue:
                return await self.async_step_station()
            return await self.async_step_logos()
        options = [{"value": NONE_VALUE, "label": "—"}] + self._stations[fuel]
        valid = {o["value"] for o in options}
        default = self._defaults_homes.get(fuel, NONE_VALUE)
        schema = vol.Schema(
            {
                vol.Optional(CONF_STATION, default=default if default in valid else NONE_VALUE): SelectSelector(
                    SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN)
                )
            }
        )
        return self.async_show_form(
            step_id="station",
            data_schema=schema,
            description_placeholders={"fuel": FUELS[fuel][0], "city": pretty(self._city)},
        )

    async def async_step_logos(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Optional: tick the chains whose logos should be downloaded from the pack on GitHub."""
        session = async_get_clientsession(self.hass)
        if user_input is None:
            index = await async_fetch_index(session)
            if not index:  # offline or pack not published: carry on without logos
                self._logos = None
                return await self._async_finish()
            self._index = index
            in_city = chains_in(sorted(self._chains), index)
            folder = logo_dir(self.hass)
            default = self._defaults_logos
            if default is None:
                default = await self.hass.async_add_executor_job(installed_ids, folder) or sorted(in_city)
            options = sorted(index, key=lambda i: (i["id"] not in in_city, i["label"].casefold()))
            known = {i["id"] for i in index}
            schema = vol.Schema(
                {
                    vol.Optional(CONF_LOGOS, default=[d for d in default if d in known]): SelectSelector(
                        SelectSelectorConfig(
                            options=[{"value": i["id"], "label": i["label"]} for i in options],
                            multiple=True,
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            )
            return self.async_show_form(step_id="logos", data_schema=schema)
        self._logos = list(user_input.get(CONF_LOGOS, []))
        others: set[str] = set()
        for other in self.hass.config_entries.async_entries(DOMAIN):
            if other.entry_id != self._own_entry_id():
                others |= set(other.options.get(CONF_LOGOS, []))
        await async_sync(self.hass, session, self._index, others | set(self._logos))
        return await self._async_finish()

    def _own_entry_id(self) -> str | None:
        return None

    async def _async_finish(self) -> ConfigFlowResult:  # pragma: no cover - implemented by the flows
        raise NotImplementedError

    def _options(self, previous: dict[str, Any] | None = None) -> dict[str, Any]:
        options = {CONF_FUELS: self._fuels, CONF_HOMES: self._homes, CONF_LANGUAGE: self._language}
        logos = self._logos if self._logos is not None else (previous or {}).get(CONF_LOGOS)
        if logos is not None:
            options[CONF_LOGOS] = logos
        return options


class CenyPalivConfigFlow(_FuelStationSteps, ConfigFlow, domain=DOMAIN):
    VERSION = 1

    _cities: list[dict[str, str]]

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            key = user_input[CONF_KEY].strip()
            try:
                markers = await async_fetch_markers(async_get_clientsession(self.hass), key, "n95")
            except MBenzinError as err:
                errors["base"] = _error_key(err)
            else:
                self._key = key
                self._cities = city_options(markers)
                return await self.async_step_city()
        schema = vol.Schema(
            {vol.Required(CONF_KEY): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))}
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_city(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._city = user_input[CONF_CITY]
            await self.async_set_unique_id(self._city)
            self._abort_if_unique_id_configured()
            return await self.async_step_fuels()
        schema = vol.Schema(
            {
                vol.Required(CONF_CITY): SelectSelector(
                    SelectSelectorConfig(options=self._cities, mode=SelectSelectorMode.DROPDOWN)
                )
            }
        )
        return self.async_show_form(step_id="city", data_schema=schema)

    async def _async_finish(self) -> ConfigFlowResult:
        return self.async_create_entry(
            title=f"Ceny paliv {pretty(self._city)}",
            data={CONF_KEY: self._key, CONF_CITY: self._city},
            options=self._options(),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> CenyPalivOptionsFlow:
        return CenyPalivOptionsFlow()


class CenyPalivOptionsFlow(_FuelStationSteps, OptionsFlow):
    """Change the fuels and the favourite stations later."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self.config_entry
        self._key = entry.data[CONF_KEY]
        self._city = entry.data[CONF_CITY]
        self._defaults_fuels = list(entry.options.get(CONF_FUELS, DEFAULT_FUELS))
        self._defaults_homes = dict(entry.options.get(CONF_HOMES, {}))
        self._defaults_language = entry.options.get(CONF_LANGUAGE)
        self._defaults_logos = entry.options.get(CONF_LOGOS)
        return await self.async_step_fuels()

    def _own_entry_id(self) -> str | None:
        return self.config_entry.entry_id

    async def _async_finish(self) -> ConfigFlowResult:
        return self.async_create_entry(data=self._options(self.config_entry.options))
