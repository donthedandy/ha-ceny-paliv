"""mBenzin.cz price-map client and data processing."""
from __future__ import annotations

import datetime as dt
import email.utils
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

import aiohttp

from .regions import REGION_NAMES, region_of
from .const import (
    DEFAULT_LANGUAGE,
    FLAT,
    FUELS,
    HISTORY_DAYS,
    KEY_HEADER,
    KEY_IN_HEADER,
    LABELS,
    MAP_STATIONS,
    MAPS,
    MAX_RETRY_AFTER,
    MAX_AGE_DAYS_BY_FUEL,
    MAX_AGE_DAYS_DEFAULT,
    PERIODS,
    TOP,
    UPDATE_INTERVAL,
    URL_BASE,
    USER_AGENT,
)


class MBenzinError(Exception):
    """Base error."""


class CannotConnect(MBenzinError):
    """The site cannot be reached."""


class InvalidAuth(MBenzinError):
    """The access key is missing, wrong or not accepted.

    `definite` is True for an explicit 401/403. An HTML "browser check" page or an answer without markers also
    means "key not accepted", but it can be an outage page too, so it only counts once it repeats.
    """

    def __init__(self, *args: object, definite: bool = False) -> None:
        super().__init__(*args)
        self.definite = definite


class RateLimited(MBenzinError):
    """HTTP 429: more than 20 pages per hour. `retry_after` is the delay mBenzin asked for, in seconds, if any."""

    def __init__(self, retry_after: float | None = None) -> None:
        super().__init__(retry_after)
        self.retry_after = retry_after


def retry_after_seconds(value: str | None, now: dt.datetime | None = None) -> float | None:
    """The delay of a `Retry-After` header in seconds (0 to 24 hours), or None when it is missing or invalid.

    Both forms are read: a number of seconds, and an HTTP date.
    """
    if not value:
        return None
    value = value.strip()
    limit = MAX_RETRY_AFTER.total_seconds()
    if value.isdecimal():
        return min(float(int(value)), limit)
    try:
        at = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    if at.tzinfo is None:
        at = at.replace(tzinfo=dt.timezone.utc)
    current = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    return min(max(0.0, (at - current).total_seconds()), limit)


def usable_marker(marker: Any) -> bool:
    """A marker with everything the integration reads. A malformed one is skipped, it must not stop the refresh."""
    if not isinstance(marker, dict):
        return False
    url, name = marker.get("url"), marker.get("name")
    if not isinstance(url, str) or not url.startswith("/") or not isinstance(name, str):
        return False
    for name_ in ("price", "lat", "lng"):
        value = marker.get(name_)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            return False
    return True


async def async_fetch_markers(session: aiohttp.ClientSession, key: str, fuel: str) -> list[dict[str, Any]]:
    """Download the price-map markers of one fuel (all of the Czech Republic).

    Raises RateLimited (429), InvalidAuth (401/403, or an answer that is not a price map) and CannotConnect.
    """
    params = {"fuel": fuel, "ccs": "0"}
    headers = {"User-Agent": USER_AGENT}
    if KEY_IN_HEADER:
        headers[KEY_HEADER] = key
    else:
        params["klic"] = key
    try:
        async with session.get(
            URL_BASE, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=60)
        ) as resp:
            if resp.status == 429:
                raise RateLimited(retry_after_seconds(resp.headers.get("Retry-After")))
            if resp.status in (401, 403):
                raise InvalidAuth(definite=True)
            if resp.status != 200:
                raise CannotConnect(f"HTTP {resp.status}")
            try:
                data = await resp.json(content_type=None)
            except ValueError as err:  # an HTML "browser check" page = key not accepted
                raise InvalidAuth from err
    except (aiohttp.ClientError, TimeoutError) as err:
        raise CannotConnect(type(err).__name__) from None  # never chain: the exception text can hold the URL
    except ValueError:  # aiohttp refuses a header value with control characters: not a usable key
        raise InvalidAuth(definite=True) from None
    markers = data.get("markers") if isinstance(data, dict) else None
    if not isinstance(markers, list):
        raise InvalidAuth
    return [m for m in markers if usable_marker(m)]


MODE_CITY = "city"
MODE_POINT = "point"
MAIN_PLACE = "main"


@dataclass(frozen=True)
class Place:
    """One place to follow: a town of the mBenzin list, or a point with a radius."""

    key: str  # MAIN_PLACE for the first place of the entry, else the sub-entry id
    title: str
    mode: str = MODE_CITY
    city: str | None = None
    lat: float | None = None
    lng: float | None = None
    radius_km: float = 10.0
    fuels: tuple[str, ...] = ()
    homes: dict[str, str] = field(default_factory=dict)
    source: str = "map"  # where a point is centred: map, home, person or zone (see const.SOURCES)
    entity: str | None = None  # the person / device tracker / zone, for the sources that have one
    max_age_days: int | None = None  # show prices up to this old (3 or 7); None = the standard window


def distance_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance (haversine)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(a))


def markers_in_place(markers: list[dict[str, Any]], place: Place) -> list[dict[str, Any]]:
    """The markers that belong to the place (same town slug, or within the radius of the point)."""
    if place.mode == MODE_POINT:
        if place.lat is None or place.lng is None:
            return []  # the centre is not known (yet)
        return [m for m in markers if distance_km(place.lat, place.lng, m["lat"], m["lng"]) <= place.radius_km]
    return [m for m in markers if city_of(m) == place.city]


def city_of(marker: dict[str, Any]) -> str | None:
    """City slug of a marker: /Ceny-benzinu-a-nafty/<City>/<Station>/<id>."""
    parts = marker.get("url", "").split("/")
    return parts[2] if len(parts) >= 5 else None


def station_slug(marker: dict[str, Any]) -> str:
    """The station part of the URL (/Ceny-benzinu-a-nafty/<City>/<Station>/<id>). A few stations have no town in
    mBenzin's URL (/stanice/<id>): they are identified by that id instead of crashing."""
    parts = marker["url"].split("/")
    return parts[3] if len(parts) > 3 and parts[3] else parts[-1] or str(marker.get("id", ""))


_HOUSE_NUMBER = re.compile(r"\s+(?:č\.?\s*p\.?\s*)?\d+[A-Za-z]?(?:/\d+[A-Za-z]?)?$", re.IGNORECASE)


def without_house_number(town: str) -> str:
    """'Dobřany 456' -> 'Dobřany' (a village address is the village and a number)."""
    return _HOUSE_NUMBER.sub("", town).strip()


def _addr_street(marker: dict[str, Any]) -> str | None:
    """The street part of mBenzin's `addr` ('Bratří Štefanů 69, Hradec Králové' -> 'Bratří Štefanů 69'), but only
    when it is the same address as the station's URL slug with its accents: a different text is not trusted."""
    parts = marker["url"].split("/")
    addr = str(marker.get("addr") or "").strip()
    if not addr or len(parts) <= 3 or not parts[3]:
        return None
    street = addr.rsplit(",", 1)[0].strip() if "," in addr else addr
    key = _alnum(street)
    return _bounded(street) if key and _alnum(parts[3]).endswith(key) else None


def address_of(marker: dict[str, Any]) -> str:
    """The readable address, with the Czech accents when mBenzin's `addr` text agrees with the URL; else the slug."""
    parts = marker["url"].split("/")
    if len(parts) > 3 and parts[3]:
        return _addr_street(marker) or pretty(parts[3])
    return _bounded(marker.get("addr") or marker["name"])


def _bounded(value: Any, limit: int = 120) -> str:
    """Text from mBenzin with a length limit, so an odd value cannot bloat the entity attributes."""
    return str(value)[:limit]


def pretty(slug: str) -> str:
    return slug.replace("-", " ")


def street_of(name: str, address: str) -> str:
    """The address text without the leading station name ('Bratri Stefanu 69')."""
    if address.lower().startswith(name.lower()):
        return address[len(name):].strip()
    return address


def station_title(name: str, address: str) -> str:
    """'Orlen – Bratri Stefanu 69' from the station name and its address text."""
    street = street_of(name, address)
    return f"{name} – {street}" if street else name


def _alnum(text: str) -> str:
    """Lower case letters and digits only, no diacritics: 'Plzeň - Koterov' -> 'plzenkoterov'."""
    plain = "".join(c for c in unicodedata.normalize("NFD", text.lower()) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", plain)


def city_options(markers: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Towns that have at least one station, for a select box.

    The value is the mBenzin slug ('Dobrany'); the label is the real spelling ('Dobřany'), taken from the
    `addr` field of the stations ('tř. 1.máje 996, Dobřany') when it matches the slug.
    """
    spelling: dict[str, Counter] = {}
    for m in markers:
        slug = city_of(m)
        if not slug:
            continue
        counter = spelling.setdefault(slug, Counter())
        town = without_house_number(str(m.get("addr") or "").rsplit(",", 1)[-1].strip())
        if town and _alnum(town) == _alnum(slug):
            counter[town] += 1
    options = [
        {"value": slug, "label": counter.most_common(1)[0][0] if counter else pretty(slug)}
        for slug, counter in spelling.items()
    ]
    return sorted(options, key=lambda o: (_alnum(o["label"]), o["label"]))


def station_options(markers: list[dict[str, Any]], place: Place) -> list[dict[str, str]]:
    """Stations of one place selling the fuel, for a select box."""
    out = []
    for m in markers_in_place(markers, place):
        slug = station_slug(m)
        out.append({"value": slug, "label": station_title(_bounded(m["name"]), address_of(m))})
    return sorted(out, key=lambda o: o["label"].casefold())


def parse_fresh(value: str | None, today: dt.date) -> dt.date | None:
    """mBenzin 'fresh' field -> date. Returns None when the format is unknown."""
    raw = (value or "").strip()
    low = raw.lower()
    if low == "dnes":
        return today
    if low in ("včera", "vcera"):
        return today - dt.timedelta(days=1)
    m = re.match(r"^(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})$", raw)
    if m:
        try:
            return dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    m = re.search(r"(\d+)\s*d", low)  # e.g. "před 3 dny"
    if m:
        return today - dt.timedelta(days=int(m.group(1)))
    return None


def _trend(log: list[list], price: float, today: dt.date, days: int) -> dict[str, Any] | None:
    """Compare with the price `days` ago (or the oldest earlier record). None when no earlier record."""
    earlier = [(d, p) for d, p in log if d < today.isoformat()]
    if not earlier:
        return None
    target = (today - dt.timedelta(days=days)).isoformat()
    older = [e for e in earlier if e[0] <= target]
    ref_date, ref_price = older[-1] if older else earlier[0]
    delta = round(price - ref_price, 2)
    return {
        "dir": "flat" if abs(delta) < FLAT else ("up" if delta > 0 else "down"),
        "delta": delta,
        "ref_date": ref_date,
        "ref_price": ref_price,
    }


def _fresh_enough(marker: dict[str, Any], today: dt.date, max_age: int) -> bool:
    d = parse_fresh(marker.get("fresh"), today)
    return d is not None and (today - d).days <= max_age


def _average(prices: list[float]) -> float | None:
    return round(sum(prices) / len(prices), 2) if prices else None


def _median(prices: list[float]) -> float | None:
    if not prices:
        return None
    ordered = sorted(prices)
    mid = len(ordered) // 2
    return round(ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2, 2)


def _diff(value: float | None, reference: float | None) -> float | None:
    return None if value is None or reference is None else round(value - reference, 2)


def price_overview(
    markers: list[dict[str, Any]], today: dt.date, max_age: int, place_markers: list[dict[str, Any]], centre: tuple[float, float] | None
) -> dict[str, Any]:
    """Average prices of the up-to-date stations: the whole country (with the 14 regions), the region of the place and
    the place itself, and how the place stands against the other two. Only data already downloaded is used."""
    by_region: dict[str, list[float]] = {}
    country: list[float] = []
    for m in markers:
        if not _fresh_enough(m, today, max_age):
            continue
        country.append(m["price"])
        code = region_of(m["lat"], m["lng"])
        if code:
            by_region.setdefault(code, []).append(m["price"])
    national = _average(country)
    ranked = sorted(by_region.items(), key=lambda item: sum(item[1]) / len(item[1]))
    regions = [
        {
            "code": code,
            "name": REGION_NAMES.get(code, code),
            "average": _average(prices),
            "station_count": len(prices),
            "vs_national": _diff(_average(prices), national),
            "rank": rank,
        }
        for rank, (code, prices) in enumerate(ranked, 1)
    ]
    # the region of the place: its centre for a point, else where most of its stations are
    own = [m for m in place_markers if _fresh_enough(m, today, max_age)]
    code = region_of(*centre) if centre else None
    if code is None and own:
        found = Counter(c for c in (region_of(m["lat"], m["lng"]) for m in own) if c)
        code = found.most_common(1)[0][0] if found else None
    region = next((r for r in regions if r["code"] == code), None)
    area_avg = _average([m["price"] for m in own])
    return {
        "country": {"average": national, "median": _median(country), "station_count": len(country), "regions": regions},
        "region": region,
        "area": {
            "average": area_avg,
            "station_count": len(own),
            "region": region["name"] if region else None,
            "region_rank": region["rank"] if region else None,
            "vs_national": _diff(area_avg, national),
            "vs_region": _diff(area_avg, region["average"] if region else None),
        },
    }


def build_payload(
    markers: list[dict[str, Any]],
    *,
    fuel: str,
    place: Place,
    home_slug: str | None,
    history: dict[str, list[list]],
    now: dt.datetime,
    language: str = DEFAULT_LANGUAGE,
) -> dict[str, Any]:
    """Top stations of the place + the favourite station, with trends.

    `history` ({station slug: [[date, price], ...]}) is updated in place with today's prices.
    """
    today = now.date()
    label, unit = FUELS.get(fuel, (fuel, "Kč/l"))
    max_age = MAX_AGE_DAYS_BY_FUEL.get(fuel, MAX_AGE_DAYS_DEFAULT)
    if place.max_age_days:
        max_age = max(max_age, place.max_age_days)  # "show older prices too" only ever widens the window
    in_city = markers_in_place(markers, place)

    cutoff = (today - dt.timedelta(days=HISTORY_DAYS)).isoformat()
    for m in in_city:
        slug = station_slug(m)
        log = [e for e in history.get(slug, []) if e[0] >= cutoff and e[0] != today.isoformat()]
        log.append([today.isoformat(), m["price"]])
        history[slug] = log

    def entry(m: dict[str, Any], d: dt.date | None, rank: int | None) -> dict[str, Any]:
        slug = station_slug(m)
        log = history.get(slug, [])
        out = {
            "rank": rank,
            "name": _bounded(m["name"]),
            "title": station_title(_bounded(m["name"]), address_of(m)),
            "url": m["url"],
            "chain": _bounded(m.get("chain") or m["name"]),
            "address": address_of(m),
            "street": street_of(_bounded(m["name"]), address_of(m)),
            "price": m["price"],
            "lat": m["lat"],
            "lng": m["lng"],
            "updated": m.get("fresh"),
            "updated_date": d.isoformat() if d else None,
            "maps": MAPS.format(lat=m["lat"], lng=m["lng"]),
            "home": bool(home_slug) and slug == home_slug,
            "trends": {str(n): _trend(log, m["price"], today, n) for n in PERIODS},
        }
        if place.mode == MODE_POINT and place.lat is not None:
            out["distance_km"] = round(distance_km(place.lat, place.lng, m["lat"], m["lng"]), 1)
        return out

    kept: list[tuple[dict[str, Any], dt.date]] = []
    excluded = 0
    for m in in_city:
        d = parse_fresh(m.get("fresh"), today)
        if d is None or (today - d).days > max_age:
            excluded += 1
            continue
        kept.append((m, d))
    kept.sort(key=lambda t: t[0]["price"])
    stations = [entry(m, d, i + 1) for i, (m, d) in enumerate(kept[:TOP])]
    # every up-to-date station of the place (the card sorts them and draws the price map): lighter than `stations`
    pool = []
    for m, d in kept[:MAP_STATIONS]:
        item = {k: v for k, v in entry(m, d, None).items() if k not in ("rank", "street", "title")}
        item["trends"] = {"1": item["trends"]["1"]}  # the card only shows the day's change here
        pool.append(item)

    home = None
    if home_slug:
        for m in in_city:
            if station_slug(m) != home_slug:
                continue
            d = parse_fresh(m.get("fresh"), today)
            pos = next((i + 1 for i, (k, _) in enumerate(kept) if station_slug(k) == home_slug), None)
            home = entry(m, d, pos)
            home["age_days"] = (today - d).days if d else None
            home["fresh_count"] = len(kept)
            if kept:
                home["cheapest_name"] = kept[0][0]["name"]
                home["vs_cheapest"] = round(m["price"] - kept[0][0]["price"], 2)
            break

    centre = (place.lat, place.lng) if place.mode == MODE_POINT and place.lat is not None and place.lng is not None else None
    stamp = now.isoformat(timespec="seconds")
    return {
        "averages": price_overview(markers, today, max_age, in_city, centre),
        "stations": stations,
        "map_stations": pool,
        "centre": {"lat": place.lat, "lng": place.lng} if centre else None,
        "home": home,
        "fetched_at": stamp,
        "last_attempt": stamp,
        "fetch_error": None,
        "city_total": len(in_city),
        "excluded": excluded,
        "max_age_days": max_age,
        "fuel": fuel,
        "fuel_label": label,
        "unit": unit,
        "city_name": place.title,
        "language": language,
        "labels": LABELS.get(language, LABELS[DEFAULT_LANGUAGE]),
        "next_update": (now + UPDATE_INTERVAL).isoformat(timespec="seconds"),
    }
