"""Constants for the Ceny paliv integration (data from mBenzin.cz)."""
from __future__ import annotations

from datetime import timedelta

DOMAIN = "ceny_paliv"

CARD_URL = "/ceny_paliv_static/ceny-paliv-card.js"
CARD_VERSION = "0.4.0"

# Optional station logos (pack in the GitHub repository, downloaded on request, see logos.py)
LOGO_URL = "/ceny_paliv_static/logos"  # served from <config>/ceny_paliv_logos/
LOGO_DIR_NAME = "ceny_paliv_logos"
_PACK = "https://raw.githubusercontent.com/donthedandy/ha-ceny-paliv/main/logos"
LOGO_INDEX_URL = f"{_PACK}/index.json"
LOGO_RAW_URL = _PACK + "/{id}.png"

CONF_KEY = "key"
CONF_CITY = "city"
CONF_FUELS = "fuels"
CONF_HOMES = "homes"  # {fuel: station slug}
CONF_LANGUAGE = "language"
CONF_STATION = "station"
CONF_LOGOS = "logos"  # logo ids ticked in the setup

NONE_VALUE = "__none__"

URL = "https://www.mbenzin.cz/Mapa-cen/data?fuel={fuel}&ccs=0&klic={key}"
USER_AGENT = "HomeAssistant-ceny-paliv"

# fuel code -> (label, unit)
FUELS: dict[str, tuple[str, str]] = {
    "n95": ("Natural 95", "Kč/l"),
    "benzinplus": ("Natural 98", "Kč/l"),
    "diesel": ("Diesel", "Kč/l"),
    "dieselplus": ("Diesel Plus", "Kč/l"),
    "lpg": ("LPG", "Kč/l"),
    "cng": ("CNG", "Kč/kg"),
    "adblue": ("AdBlue", "Kč/l"),
}
DEFAULT_FUELS = ["n95"]

TOP = 5
# How old a price may be to be shown: 0 = today only, 1 = today + yesterday, ...
# LPG / CNG / AdBlue stations are updated less often, so they get a longer window.
MAX_AGE_DAYS_DEFAULT = 1
MAX_AGE_DAYS_BY_FUEL = {"lpg": 7, "cng": 3, "adblue": 7}
HISTORY_DAYS = 35
FLAT = 0.005  # |delta| below this = stable price
PERIODS = (1, 2, 7, 14, 30)  # trend windows in days

# 4 refreshes a day per fuel. mBenzin allows 20 pages per hour per key.
UPDATE_INTERVAL = timedelta(hours=6)

MAPS = "https://www.google.com/maps/search/?api=1&query={lat},{lng}"

LANGUAGES = {"en": "English", "cs": "Čeština"}
DEFAULT_LANGUAGE = "en"

# Texts used by the dashboard views (read from the `labels` attribute of sensor.ceny_paliv_<fuel>_top5).
# {placeholders} are filled in by the view.
LABELS: dict[str, dict[str, str]] = {
    "en": {
        "locale": "en-GB",
        "my_station": "My station",
        "updated_today": "Updated today",
        "updated_yesterday": "Updated yesterday",
        "price_from": "Price from {d} — may be outdated",
        "trends_start": "Trends start tomorrow (first daily record: today)",
        "since_partial": "* since {d} — history still filling",
        "not_ranked": "Not ranked — price older than yesterday",
        "cheapest_town": "Cheapest in town · #{rank} of {n} up-to-date stations",
        "vs_cheapest": "+{d} vs cheapest ({name}) · #{rank} of {n}",
        "tap_history": "Tap for full history",
        "no_recent": "No recent prices (today or yesterday)",
        "cheapest_price": "Cheapest {p} {unit}",
        "stations_same": "{n} stations at this price",
        "today": "Today",
        "yesterday": "Yesterday",
        "today_l": "today",
        "yesterday_l": "yesterday",
        "cheapest_badge": "Cheapest",
        "table_updated": "Table updated {t} · next refresh {n}",
        "refresh_failed": "Last refresh failed{at} ({err}) — showing the previous data",
        "at": " at ",
        "hidden": "{h} of {t} stations hidden — price older than {age}",
        "arrows": "Arrows: price vs yesterday",
        "down": "down",
        "stable": "stable",
        "up": "up",
        "longpress": "long-press a row for your station history",
        "e10_note": "(E10 not distinguished)",
        "tap_station": "tap a station to open Google Maps",
        "vs_yesterday": "vs yesterday",
        "name_cheapest": "cheapest",
        "name_home": "favourite station",
    },
    "cs": {
        "locale": "cs-CZ",
        "my_station": "Moje stanice",
        "updated_today": "Aktualizováno dnes",
        "updated_yesterday": "Aktualizováno včera",
        "price_from": "Cena z {d} — může být zastaralá",
        "trends_start": "Trendy se objeví zítra (první denní záznam: dnes)",
        "since_partial": "* od {d} — historie se teprve plní",
        "not_ranked": "Mimo pořadí — cena je starší než včerejšek",
        "cheapest_town": "Nejlevnější ve městě · {rank}. z {n} aktuálních stanic",
        "vs_cheapest": "+{d} oproti nejlevnější ({name}) · {rank}. z {n}",
        "tap_history": "Klepnutím zobrazíte celou historii",
        "no_recent": "Žádné aktuální ceny (dnes nebo včera)",
        "cheapest_price": "Nejlevnější {p} {unit}",
        "stations_same": "{n} stanic má tuto cenu",
        "today": "Dnes",
        "yesterday": "Včera",
        "today_l": "dnes",
        "yesterday_l": "včera",
        "cheapest_badge": "Nejlevnější",
        "table_updated": "Tabulka aktualizována {t} · další aktualizace {n}",
        "refresh_failed": "Poslední aktualizace selhala{at} ({err}) — zobrazena předchozí data",
        "at": " v ",
        "hidden": "{h} z {t} stanic skryto — cena je starší než {age}",
        "arrows": "Šipky: cena oproti včerejšku",
        "down": "klesá",
        "stable": "beze změny",
        "up": "roste",
        "longpress": "dlouhým stisknutím řádku zobrazíte historii vaší stanice",
        "e10_note": "(E10 se nerozlišuje)",
        "tap_station": "klepnutím na stanici otevřete Google Maps",
        "vs_yesterday": "oproti včerejšku",
        "name_cheapest": "nejlevnější",
        "name_home": "oblíbená stanice",
    },
}
