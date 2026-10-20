"""mBenzin.cz price-map client and data processing."""
from __future__ import annotations

import datetime as dt
import re
from typing import Any

import aiohttp

from .const import (
    DEFAULT_LANGUAGE,
    FLAT,
    FUELS,
    HISTORY_DAYS,
    LABELS,
    MAPS,
    MAX_AGE_DAYS_BY_FUEL,
    MAX_AGE_DAYS_DEFAULT,
    PERIODS,
    TOP,
    UPDATE_INTERVAL,
    URL,
    USER_AGENT,
)


class MBenzinError(Exception):
    """Base error."""


class CannotConnect(MBenzinError):
    """The site cannot be reached."""


class InvalidAuth(MBenzinError):
    """The access key is missing, wrong or not accepted."""


class RateLimited(MBenzinError):
    """HTTP 429: more than 20 pages per hour."""


async def async_fetch_markers(session: aiohttp.ClientSession, key: str, fuel: str) -> list[dict[str, Any]]:
    """Download the price-map markers of one fuel (all of the Czech Republic)."""
    url = URL.format(fuel=fuel, key=key)
    try:
        async with session.get(
            url, headers={"User-Agent": USER_AGENT}, timeout=aiohttp.ClientTimeout(total=60)
        ) as resp:
            if resp.status == 429:
                raise RateLimited
            if resp.status in (401, 403):
                raise InvalidAuth
            if resp.status != 200:
                raise CannotConnect(f"HTTP {resp.status}")
            try:
                data = await resp.json(content_type=None)
            except ValueError as err:  # an HTML "browser check" page = key not accepted
                raise InvalidAuth from err
    except (aiohttp.ClientError, TimeoutError) as err:
        raise CannotConnect(type(err).__name__) from err
    markers = data.get("markers") if isinstance(data, dict) else None
    if not isinstance(markers, list):
        raise InvalidAuth
    return markers


def city_of(marker: dict[str, Any]) -> str | None:
    """City slug of a marker: /Ceny-benzinu-a-nafty/<City>/<Station>/<id>."""
    parts = marker.get("url", "").split("/")
    return parts[2] if len(parts) >= 5 else None


def station_slug(marker: dict[str, Any]) -> str:
    return marker["url"].split("/")[3]


def pretty(slug: str) -> str:
    return slug.replace("-", " ")


def city_options(markers: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Cities that have at least one station, for a select box."""
    slugs = {c for m in markers if (c := city_of(m))}
    return [{"value": s, "label": pretty(s)} for s in sorted(slugs, key=str.casefold)]


def station_options(markers: list[dict[str, Any]], city: str) -> list[dict[str, str]]:
    """Stations of one city selling the fuel, for a select box."""
    out = []
    for m in markers:
        if city_of(m) != city:
            continue
        slug = station_slug(m)
        address = pretty(slug)
        if address.lower().startswith(m["name"].lower()):
            address = address[len(m["name"]):].strip()
        out.append({"value": slug, "label": f"{m['name']} – {address}" if address else m["name"]})
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


def build_payload(
    markers: list[dict[str, Any]],
    *,
    fuel: str,
    city: str,
    home_slug: str | None,
    history: dict[str, list[list]],
    now: dt.datetime,
    language: str = DEFAULT_LANGUAGE,
) -> dict[str, Any]:
    """Top stations of the city + the favourite station, with trends.

    `history` ({station slug: [[date, price], ...]}) is updated in place with today's prices.
    """
    today = now.date()
    label, unit = FUELS.get(fuel, (fuel, "Kč/l"))
    max_age = MAX_AGE_DAYS_BY_FUEL.get(fuel, MAX_AGE_DAYS_DEFAULT)
    in_city = [m for m in markers if city_of(m) == city]

    cutoff = (today - dt.timedelta(days=HISTORY_DAYS)).isoformat()
    for m in in_city:
        slug = station_slug(m)
        log = [e for e in history.get(slug, []) if e[0] >= cutoff and e[0] != today.isoformat()]
        log.append([today.isoformat(), m["price"]])
        history[slug] = log

    def entry(m: dict[str, Any], d: dt.date | None, rank: int | None) -> dict[str, Any]:
        slug = station_slug(m)
        log = history.get(slug, [])
        return {
            "rank": rank,
            "name": m["name"],
            "address": pretty(slug),
            "price": m["price"],
            "lat": m["lat"],
            "lng": m["lng"],
            "updated": m.get("fresh"),
            "updated_date": d.isoformat() if d else None,
            "maps": MAPS.format(lat=m["lat"], lng=m["lng"]),
            "home": bool(home_slug) and slug == home_slug,
            "trends": {str(n): _trend(log, m["price"], today, n) for n in PERIODS},
        }

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

    stamp = now.isoformat(timespec="seconds")
    return {
        "stations": stations,
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
        "city_name": pretty(city),
        "language": language,
        "labels": LABELS.get(language, LABELS[DEFAULT_LANGUAGE]),
        "next_update": (now + UPDATE_INTERVAL).isoformat(timespec="seconds"),
    }
