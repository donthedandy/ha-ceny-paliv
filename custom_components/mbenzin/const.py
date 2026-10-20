"""Constants for the mBenzin integration."""
from __future__ import annotations

from datetime import timedelta

DOMAIN = "mbenzin"

CONF_KEY = "key"
CONF_CITY = "city"
CONF_FUELS = "fuels"
CONF_HOMES = "homes"  # {fuel: station slug}
CONF_STATION = "station"

NONE_VALUE = "__none__"

URL = "https://www.mbenzin.cz/Mapa-cen/data?fuel={fuel}&ccs=0&klic={key}"
USER_AGENT = "HomeAssistant-mbenzin"

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
