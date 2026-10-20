"""Top 5 cheapest stations of one city for one fuel, from the mBenzin.cz price-map data.

Usage: python3 mbenzin_top5.py <fuel>        fuel: n95 | benzinplus | diesel | dieselplus | lpg | cng | adblue
Your personal mBenzin key is read from the MBENZIN_KEY environment variable, or from the line
`mbenzin_key: "..."` of the secrets.yaml that sits next to this script.

- Keeps only prices updated recently (MAX_AGE_DAYS, per fuel), then sorts by price.
- Keeps a daily price log per station (HISTORY_DAYS) to compute 1/2/7/14/30-day trends.
- Always reports the "home" station (HOME_SLUG), even when it is not in the top 5.
- On any fetch error (e.g. HTTP 429 rate limit), prints the last good result from the cache.
"""
import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.request

# --- Edit these two lines for your own city / station -------------------------------------------
# City: the part of the station URL on mbenzin.cz, e.g. https://www.mbenzin.cz/Ceny-benzinu-a-nafty/<City>/<Station>/<id>
CITY = "/Hradec-Kralove/"
# Your usual station: the <Station> part of its mbenzin.cz URL (leave "" to disable the "home" feature)
HOME_SLUG = "Orlen-Example-Street-1"
# -------------------------------------------------------------------------------------------------
TOP = 5
# How old a price may be to be shown: 0 = today only, 1 = today + yesterday, ...
# LPG / CNG / AdBlue stations are updated less often, so they get a longer window.
MAX_AGE_DAYS_DEFAULT = 1
MAX_AGE_DAYS_BY_FUEL = {"lpg": 7, "cng": 3, "adblue": 7}
HISTORY_DAYS = 35
FLAT = 0.005          # |delta| below this = stable
PERIODS = (1, 2, 7, 14, 30)  # trend windows in days
FUELS = {
    "n95": ("Natural 95", "Kč/l"),
    "benzinplus": ("Natural 98", "Kč/l"),
    "diesel": ("Diesel", "Kč/l"),
    "dieselplus": ("Diesel Plus", "Kč/l"),
    "lpg": ("LPG", "Kč/l"),
    "cng": ("CNG", "Kč/kg"),
    "adblue": ("AdBlue", "Kč/l"),
}
HERE = os.path.dirname(os.path.abspath(__file__))
URL = "https://www.mbenzin.cz/Mapa-cen/data?fuel=%s&ccs=0&klic=%s"
MAPS = "https://www.google.com/maps/search/?api=1&query=%s,%s"


def get_key():
    key = os.environ.get("MBENZIN_KEY")
    if key:
        return key.strip()
    try:
        with open(os.path.join(HERE, "secrets.yaml"), encoding="utf-8") as fh:
            for line in fh:
                m = re.match(r"""^mbenzin_key:\s*["']?([^"'\s#]+)""", line)
                if m:
                    return m.group(1)
    except OSError:
        pass
    return None


def parse_fresh(value, today):
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


def slug(x):
    return x["url"].split("/")[3]


def load(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001
        return default


def save(path, data):
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, path)
    except OSError:
        pass


def trend(log, price, today, days):
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


def emit(data):
    print(json.dumps(data, ensure_ascii=False, separators=(",", ":")))


def main():
    fuel = (sys.argv[1] if len(sys.argv) > 1 else "n95").lower()
    label, unit = FUELS.get(fuel, (fuel, "Kč/l"))
    max_age = MAX_AGE_DAYS_BY_FUEL.get(fuel, MAX_AGE_DAYS_DEFAULT)
    cache_file = os.path.join(HERE, ".mbenzin_cache_%s.json" % fuel)
    history_file = os.path.join(HERE, ".mbenzin_history_%s.json" % fuel)
    meta = {
        "fuel": fuel,
        "fuel_label": label,
        "unit": unit,
        "city_name": CITY.strip("/").replace("-", " "),
        "max_age_days": max_age,
    }

    now = dt.datetime.now().astimezone()
    today = now.date()
    stamp = now.isoformat(timespec="seconds")
    try:
        url = os.environ.get("MBENZIN_URL")  # override, handy for tests
        if not url:
            key = get_key()
            if not key:
                raise RuntimeError("NoKey")
            url = URL % (fuel, key)
        req = urllib.request.Request(url, headers={"User-Agent": "HomeAssistant-mbenzin"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            markers = json.load(resp)["markers"]
    except Exception as exc:  # noqa: BLE001 — any failure falls back to the cache
        err = "HTTP %s" % exc.code if isinstance(exc, urllib.error.HTTPError) else (
            "no key" if str(exc) == "NoKey" else type(exc).__name__)
        cached = load(cache_file, {"stations": [], "home": None, "fetched_at": None, "city_total": 0, "excluded": 0})
        cached.update(meta)
        cached.update(fetch_error=err, last_attempt=stamp)
        emit(cached)
        return

    city = [x for x in markers if CITY in x.get("url", "")]

    # daily price log per station: one entry per day (latest value of the day)
    hist = load(history_file, {})
    cutoff = (today - dt.timedelta(days=HISTORY_DAYS)).isoformat()
    for x in city:
        log = [e for e in hist.get(slug(x), []) if e[0] >= cutoff and e[0] != today.isoformat()]
        log.append([today.isoformat(), x["price"]])
        hist[slug(x)] = log
    save(history_file, hist)

    def entry(x, d, rank=None):
        log = hist.get(slug(x), [])
        return {
            "rank": rank,
            "name": x["name"],
            "address": slug(x).replace("-", " "),
            "price": x["price"],
            "lat": x["lat"],
            "lng": x["lng"],
            "updated": x.get("fresh"),
            "updated_date": d.isoformat() if d else None,
            "maps": MAPS % (x["lat"], x["lng"]),
            "home": bool(HOME_SLUG) and slug(x) == HOME_SLUG,
            "trends": {str(n): trend(log, x["price"], today, n) for n in PERIODS},
        }

    kept, excluded = [], 0
    for x in city:
        d = parse_fresh(x.get("fresh"), today)
        if d is None or (today - d).days > max_age:
            excluded += 1
            continue
        kept.append((x, d))
    kept.sort(key=lambda t: t[0]["price"])
    stations = [entry(x, d, i + 1) for i, (x, d) in enumerate(kept[:TOP])]

    home = None
    for x in city:
        if HOME_SLUG and slug(x) == HOME_SLUG:
            d = parse_fresh(x.get("fresh"), today)
            pos = next((i + 1 for i, (k, _) in enumerate(kept) if slug(k) == HOME_SLUG), None)
            home = entry(x, d, pos)
            home["age_days"] = (today - d).days if d else None
            home["fresh_count"] = len(kept)
            if kept:
                home["cheapest_name"] = kept[0][0]["name"]
                home["vs_cheapest"] = round(x["price"] - kept[0][0]["price"], 2)
            break

    out = {
        "stations": stations,
        "home": home,
        "fetched_at": stamp,
        "last_attempt": stamp,
        "fetch_error": None,
        "city_total": len(city),
        "excluded": excluded,
    }
    out.update(meta)
    save(cache_file, out)
    emit(out)


if __name__ == "__main__":
    main()
