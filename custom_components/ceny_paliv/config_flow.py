"""Config flow: key -> place (a town, or a point and a radius) -> fuels -> favourite station per fuel -> logos.

More places can be added later with the "Add place" button of the integration (config sub-entries): they share the key
and the language, and each one has its own fuels and favourite stations. The first place lives in the entry itself,
exactly as in the versions before places existed.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    LocationSelector,
    LocationSelectorConfig,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    MODE_CITY,
    MODE_POINT,
    InvalidAuth,
    MBenzinError,
    Place,
    RateLimited,
    async_fetch_markers,
    city_options,
    markers_in_place,
    pretty,
    station_options,
)
from .const import (
    CONF_CITY,
    CONF_FUELS,
    CONF_HOMES,
    CONF_KEY,
    CONF_LANGUAGE,
    CONF_LATITUDE,
    CONF_LOCATION,
    CONF_LOGOS,
    CONF_LONGITUDE,
    CONF_MODE,
    CONF_NAME,
    CONF_RADIUS,
    CONF_STATION,
    DEFAULT_FUELS,
    DEFAULT_LANGUAGE,
    DEFAULT_RADIUS_KM,
    DOMAIN,
    FUELS,
    LANGUAGES,
    NONE_VALUE,
    SUBENTRY_PLACE,
)
from .logos import async_fetch_index, async_sync, chains_in, installed_ids, logo_dir

MIN_RADIUS_KM = 1
MAX_RADIUS_KM = 100


def _error_key(err: MBenzinError) -> str:
    if isinstance(err, InvalidAuth):
        return "invalid_auth"
    if isinstance(err, RateLimited):
        return "rate_limited"
    return "cannot_connect"


class _PlaceSteps:
    """Shared by the config flow, the options flow and the "add place" flow:
    place (town or point) -> fuels -> favourite station per fuel -> (logos, first place only)."""

    hass: Any
    _ask_language = False
    _ask_logos = False

    # --- hooks -------------------------------------------------------------------------------------------------
    def _api_key(self) -> str:  # pragma: no cover - implemented by the flows
        raise NotImplementedError

    def _initial(self) -> dict[str, Any]:
        """Defaults shown in the forms: mode, city, latitude, longitude, radius, name, fuels, homes, language, logos."""
        return {}

    async def _async_finish(self) -> Any:  # pragma: no cover - implemented by the flows
        raise NotImplementedError

    # --- state -------------------------------------------------------------------------------------------------
    def _state(self) -> dict[str, Any]:
        if not hasattr(self, "_st"):
            self._st: dict[str, Any] = {"markers": {}, "initial": self._initial()}
        return self._st

    async def _markers(self, fuel: str) -> list[dict[str, Any]]:
        cache = self._state()["markers"]
        if fuel not in cache:
            cache[fuel] = await async_fetch_markers(async_get_clientsession(self.hass), self._api_key(), fuel)
        return cache[fuel]

    def _place(self) -> Place:
        st = self._state()
        return Place(
            key="tmp",
            title=st.get("title", ""),
            mode=st["mode"],
            city=st.get("city"),
            lat=st.get("latitude"),
            lng=st.get("longitude"),
            radius_km=st.get("radius", DEFAULT_RADIUS_KM),
        )

    def _place_data(self) -> dict[str, Any]:
        """What is stored for the place."""
        st = self._state()
        if st["mode"] == MODE_POINT:
            return {
                CONF_MODE: MODE_POINT,
                CONF_LATITUDE: st["latitude"],
                CONF_LONGITUDE: st["longitude"],
                CONF_RADIUS: st["radius"],
                CONF_NAME: st["title"],
            }
        return {CONF_MODE: MODE_CITY, CONF_CITY: st["city"], CONF_NAME: st["title"]}

    # --- place -------------------------------------------------------------------------------------------------
    async def async_step_mode(self, user_input: dict[str, Any] | None = None) -> Any:
        st = self._state()
        if user_input is not None:
            st["mode"] = user_input[CONF_MODE]
            return await (self.async_step_city() if st["mode"] == MODE_CITY else self.async_step_point())
        schema = vol.Schema(
            {
                vol.Required(CONF_MODE, default=st["initial"].get(CONF_MODE, MODE_CITY)): SelectSelector(
                    SelectSelectorConfig(
                        options=[MODE_CITY, MODE_POINT], mode=SelectSelectorMode.LIST, translation_key="mode"
                    )
                )
            }
        )
        return self.async_show_form(step_id="mode", data_schema=schema)

    async def async_step_city(self, user_input: dict[str, Any] | None = None) -> Any:
        st = self._state()
        errors: dict[str, str] = {}
        try:
            options = city_options(await self._markers("n95"))
        except MBenzinError as err:
            options, errors["base"] = [], _error_key(err)
        if user_input is not None and not errors:
            st["city"] = user_input[CONF_CITY]
            st["title"] = next((o["label"] for o in options if o["value"] == st["city"]), pretty(st["city"]))
            return await self.async_step_fuels()
        default = st["initial"].get(CONF_CITY)
        key = vol.Required(CONF_CITY, default=default) if any(o["value"] == default for o in options) else vol.Required(CONF_CITY)
        schema = vol.Schema(
            {key: SelectSelector(SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN))}
        )
        return self.async_show_form(step_id="city", data_schema=schema, errors=errors)

    async def async_step_point(self, user_input: dict[str, Any] | None = None) -> Any:
        st = self._state()
        if user_input is not None:
            loc = user_input[CONF_LOCATION]
            st["latitude"] = round(float(loc["latitude"]), 5)
            st["longitude"] = round(float(loc["longitude"]), 5)
            km = float(loc.get("radius", DEFAULT_RADIUS_KM * 1000)) / 1000
            st["radius"] = round(min(max(km, MIN_RADIUS_KM), MAX_RADIUS_KM), 1)
            name = (user_input.get(CONF_NAME) or "").strip()
            st["title"] = name or f"{st['latitude']:.2f}, {st['longitude']:.2f} · {st['radius']:g} km"
            return await self.async_step_fuels()
        ini = st["initial"]
        was_point = ini.get(CONF_MODE) == MODE_POINT
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_LOCATION,
                    default={
                        "latitude": ini.get(CONF_LATITUDE, self.hass.config.latitude),
                        "longitude": ini.get(CONF_LONGITUDE, self.hass.config.longitude),
                        "radius": float(ini.get(CONF_RADIUS, DEFAULT_RADIUS_KM)) * 1000,
                    },
                ): LocationSelector(LocationSelectorConfig(radius=True)),
                vol.Optional(CONF_NAME, default=(ini.get(CONF_NAME) or "") if was_point else ""): TextSelector(),
            }
        )
        return self.async_show_form(step_id="point", data_schema=schema)

    # --- fuels -------------------------------------------------------------------------------------------------
    async def async_step_fuels(self, user_input: dict[str, Any] | None = None) -> Any:
        st = self._state()
        errors: dict[str, str] = {}
        if user_input is not None:
            fuels = user_input[CONF_FUELS]
            if not fuels:
                errors[CONF_FUELS] = "no_fuel"
            else:
                stations: dict[str, list[dict[str, str]]] = {}
                chains: set[str] = set()
                try:
                    place = self._place()
                    for fuel in fuels:
                        markers = await self._markers(fuel)
                        stations[fuel] = station_options(markers, place)
                        chains |= {m.get("chain") or m["name"] for m in markers_in_place(markers, place)}
                except MBenzinError as err:
                    errors["base"] = _error_key(err)
                else:
                    st.update(fuels=fuels, stations=stations, chains=chains, queue=list(fuels), homes={})
                    if self._ask_language:
                        st["language"] = user_input[CONF_LANGUAGE]
                    return await self.async_step_station()
        fields: dict[Any, Any] = {
            vol.Required(CONF_FUELS, default=st["initial"].get(CONF_FUELS, DEFAULT_FUELS)): SelectSelector(
                SelectSelectorConfig(
                    options=[{"value": k, "label": v[0]} for k, v in FUELS.items()],
                    multiple=True,
                    mode=SelectSelectorMode.LIST,
                )
            )
        }
        if self._ask_language:
            fields[vol.Required(CONF_LANGUAGE, default=self._default_language())] = SelectSelector(
                SelectSelectorConfig(
                    options=[{"value": k, "label": v} for k, v in LANGUAGES.items()],
                    mode=SelectSelectorMode.DROPDOWN,
                )
            )
        return self.async_show_form(step_id="fuels", data_schema=vol.Schema(fields), errors=errors)

    def _default_language(self) -> str:
        """Language of the dashboard texts: the saved one, else Home Assistant's own language."""
        saved = self._state()["initial"].get(CONF_LANGUAGE)
        if saved in LANGUAGES:
            return saved
        ha_language = (self.hass.config.language or DEFAULT_LANGUAGE).split("-")[0]
        return ha_language if ha_language in LANGUAGES else DEFAULT_LANGUAGE

    async def async_step_station(self, user_input: dict[str, Any] | None = None) -> Any:
        st = self._state()
        fuel = st["queue"][0]
        if user_input is not None:
            choice = user_input.get(CONF_STATION, NONE_VALUE)
            if choice != NONE_VALUE:
                st["homes"][fuel] = choice
            st["queue"].pop(0)
            if st["queue"]:
                return await self.async_step_station()
            return await self.async_step_logos()
        options = [{"value": NONE_VALUE, "label": "—"}] + st["stations"][fuel]
        valid = {o["value"] for o in options}
        default = (st["initial"].get(CONF_HOMES) or {}).get(fuel, NONE_VALUE)
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
            description_placeholders={"fuel": FUELS[fuel][0], "city": st["title"]},
        )

    # --- logos (first place only) ------------------------------------------------------------------------------
    async def async_step_logos(self, user_input: dict[str, Any] | None = None) -> Any:
        """Optional: tick the chains whose logos should be downloaded from the pack on GitHub."""
        st = self._state()
        if not self._ask_logos:
            return await self._async_finish()
        session = async_get_clientsession(self.hass)
        if user_input is None:
            index = await async_fetch_index(session)
            if not index:  # offline or pack not published: carry on without logos
                st["logos"] = None
                return await self._async_finish()
            st["index"] = index
            in_city = chains_in(sorted(st["chains"]), index)
            default = st["initial"].get(CONF_LOGOS)
            if default is None:
                default = await self.hass.async_add_executor_job(installed_ids, logo_dir(self.hass)) or sorted(in_city)
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
        st["logos"] = list(user_input.get(CONF_LOGOS, []))
        others: set[str] = set()
        for other in self.hass.config_entries.async_entries(DOMAIN):
            if other.entry_id != self._own_entry_id():
                others |= set(other.options.get(CONF_LOGOS, []))
        await async_sync(self.hass, session, st["index"], others | set(st["logos"]))
        return await self._async_finish()

    def _own_entry_id(self) -> str | None:
        return None

    def _options(self, previous: dict[str, Any] | None = None) -> dict[str, Any]:
        """Entry options of the first place: fuels, favourite stations, language, logos."""
        st = self._state()
        options = {CONF_FUELS: st["fuels"], CONF_HOMES: st["homes"], CONF_LANGUAGE: st["language"]}
        logos = st.get("logos")
        if logos is None:
            logos = (previous or {}).get(CONF_LOGOS)
        if logos is not None:
            options[CONF_LOGOS] = logos
        return options


class CenyPalivConfigFlow(_PlaceSteps, ConfigFlow, domain=DOMAIN):
    VERSION = 1
    _ask_language = True
    _ask_logos = True

    def _api_key(self) -> str:
        return self._key

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if self._async_current_entries():
            # one entry holds the key; more towns or points are added with "Add place" on it
            return self.async_abort(reason="single_instance_allowed")
        errors: dict[str, str] = {}
        if user_input is not None:
            key = user_input[CONF_KEY].strip()
            try:
                markers = await async_fetch_markers(async_get_clientsession(self.hass), key, "n95")
            except MBenzinError as err:
                errors["base"] = _error_key(err)
            else:
                self._key = key
                self._state()["markers"]["n95"] = markers
                return await self.async_step_mode()
        schema = vol.Schema(
            {vol.Required(CONF_KEY): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))}
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """mBenzin refused the key: ask for a new one instead of failing forever."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            key = user_input[CONF_KEY].strip()
            try:
                await async_fetch_markers(async_get_clientsession(self.hass), key, "n95")
            except MBenzinError as err:
                errors["base"] = _error_key(err)
            else:
                return self.async_update_reload_and_abort(entry, data_updates={CONF_KEY: key})
        schema = vol.Schema(
            {vol.Required(CONF_KEY): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))}
        )
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=schema, errors=errors, description_placeholders={"title": entry.title}
        )

    async def _async_finish(self) -> ConfigFlowResult:
        st = self._state()
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=f"Ceny paliv {st['title']}",
            data={CONF_KEY: self._key, **self._place_data()},
            options=self._options(),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> CenyPalivOptionsFlow:
        return CenyPalivOptionsFlow()

    @classmethod
    @callback
    def async_get_supported_subentry_types(cls, config_entry: ConfigEntry) -> dict[str, type[ConfigSubentryFlow]]:
        return {SUBENTRY_PLACE: CenyPalivPlaceFlow}


class CenyPalivOptionsFlow(_PlaceSteps, OptionsFlow):
    """Change the first place (town or point), its fuels and favourite stations, the language and the logos."""

    _ask_language = True
    _ask_logos = True

    def _api_key(self) -> str:
        return self.config_entry.data[CONF_KEY]

    def _own_entry_id(self) -> str | None:
        return self.config_entry.entry_id

    def _initial(self) -> dict[str, Any]:
        initial = dict(self.config_entry.data)
        initial.update(self.config_entry.options)
        return initial

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self.async_step_mode()

    async def _async_finish(self) -> ConfigFlowResult:
        st = self._state()
        entry = self.config_entry
        data = {CONF_KEY: entry.data[CONF_KEY], **self._place_data()}
        options = self._options(entry.options)
        # one single update (data, options, title): two updates in a row would trigger two reloads, and the second
        # one is lost when the first one is already unloading the entry
        self.hass.config_entries.async_update_entry(
            entry, data=data, options=options, title=f"Ceny paliv {st['title']}"
        )
        return self.async_create_entry(data=options)


class CenyPalivPlaceFlow(_PlaceSteps, ConfigSubentryFlow):
    """Add (or change) another place: a town or a point with a radius, with its own fuels and favourite stations."""

    def _api_key(self) -> str:
        return self._get_entry().data[CONF_KEY]

    def _initial(self) -> dict[str, Any]:
        if self.source == "reconfigure":
            return dict(self._get_reconfigure_subentry().data)
        return {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        return await self.async_step_mode()

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        return await self.async_step_mode()

    async def _async_finish(self) -> SubentryFlowResult:
        st = self._state()
        data = {**self._place_data(), CONF_FUELS: st["fuels"], CONF_HOMES: st["homes"]}
        if self.source == "reconfigure":
            return self.async_update_and_abort(
                self._get_entry(), self._get_reconfigure_subentry(), title=st["title"], data=data
            )
        return self.async_create_entry(title=st["title"], data=data)
