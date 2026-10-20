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
    city_options,
    pretty,
    station_options,
)
from .const import (
    CONF_CITY,
    CONF_FUELS,
    CONF_HOMES,
    CONF_KEY,
    CONF_STATION,
    DEFAULT_FUELS,
    DOMAIN,
    FUELS,
    NONE_VALUE,
)


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
    _queue: list[str]
    _homes: dict[str, str]
    _stations: dict[str, list[dict[str, str]]]
    _defaults_fuels: list[str] = DEFAULT_FUELS
    _defaults_homes: dict[str, str] = {}

    async def async_step_fuels(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            fuels = user_input[CONF_FUELS]
            if not fuels:
                errors[CONF_FUELS] = "no_fuel"
            else:
                session = async_get_clientsession(self.hass)
                stations: dict[str, list[dict[str, str]]] = {}
                try:
                    for fuel in fuels:
                        stations[fuel] = station_options(await async_fetch_markers(session, self._key, fuel), self._city)
                except MBenzinError as err:
                    errors["base"] = _error_key(err)
                else:
                    self._fuels, self._stations = fuels, stations
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
                )
            }
        )
        return self.async_show_form(step_id="fuels", data_schema=schema, errors=errors)

    async def async_step_station(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        fuel = self._queue[0]
        if user_input is not None:
            choice = user_input.get(CONF_STATION, NONE_VALUE)
            if choice != NONE_VALUE:
                self._homes[fuel] = choice
            self._queue.pop(0)
            if self._queue:
                return await self.async_step_station()
            return await self._async_finish()
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

    async def _async_finish(self) -> ConfigFlowResult:  # pragma: no cover - implemented by the flows
        raise NotImplementedError


class MBenzinConfigFlow(_FuelStationSteps, ConfigFlow, domain=DOMAIN):
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
            title=f"mBenzin {pretty(self._city)}",
            data={CONF_KEY: self._key, CONF_CITY: self._city},
            options={CONF_FUELS: self._fuels, CONF_HOMES: self._homes},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> MBenzinOptionsFlow:
        return MBenzinOptionsFlow()


class MBenzinOptionsFlow(_FuelStationSteps, OptionsFlow):
    """Change the fuels and the favourite stations later."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self.config_entry
        self._key = entry.data[CONF_KEY]
        self._city = entry.data[CONF_CITY]
        self._defaults_fuels = list(entry.options.get(CONF_FUELS, DEFAULT_FUELS))
        self._defaults_homes = dict(entry.options.get(CONF_HOMES, {}))
        return await self.async_step_fuels()

    async def _async_finish(self) -> ConfigFlowResult:
        return self.async_create_entry(data={CONF_FUELS: self._fuels, CONF_HOMES: self._homes})
