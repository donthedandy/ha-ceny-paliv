# ⛽ Fuel prices from mBenzin.cz in Home Assistant

Cheapest stations of **your city** for the fuel you use — **Natural 95, Diesel, LPG, CNG** (and others) — plus tracking of **your usual station**: price history, 1/2/7/14/30-day trends, rank in town, optional price-change notification. All in a Home Assistant dashboard view.

![Dashboard](docs/screenshot.webp)

> Built for Hradec Králové, but it works for any Czech city: change two lines in the script.
> Unofficial project, not affiliated with mBenzin.cz.

## What you get

- **My station** card: price, trends vs 1/2/7/14/30 days ago, "cheapest in town" status, long-term statistics
- **Top 5** cheapest stations in the city (only that city, not the whole region) with day-over-day arrows and a tap-to-open Google Maps link
- **Map** with the prices on the stations
- **30-day graph** of your station (min / mean / max)
- **One view per fuel**: install only the fuels you need (petrol car, diesel van, LPG…)
- Optional phone notification when your station's price changes

## How it works

1. A tiny Python script (`mbenzin_top5.py <fuel>`) downloads the price-map data of mBenzin for that fuel (one JSON, ~450 KB), keeps the stations of your city whose price is recent, sorts them and prints a compact JSON.
2. A `command_line` sensor runs it **5 times a day** (05:00, 11:00, 14:00, 17:00, 21:00) and exposes the result as attributes.
3. Template sensors feed the map and your station card; the script also keeps a small daily price log next to itself (`.mbenzin_history_<fuel>.json`) to compute trends.
4. If a refresh fails (for example HTTP 429), the last good data is shown and the card tells you so.

Supported fuels (the name is the argument of the script):

| Fuel | Argument | Package / view in this repo |
|---|---|---|
| Natural 95 | `n95` | `mbenzin_n95.yaml` / `fuel_view_n95.yaml` |
| Diesel | `diesel` | `mbenzin_diesel.yaml` / `fuel_view_diesel.yaml` |
| LPG | `lpg` | `mbenzin_lpg.yaml` / `fuel_view_lpg.yaml` |
| CNG (Kč/kg) | `cng` | `mbenzin_cng.yaml` / `fuel_view_cng.yaml` |
| Natural 98, Diesel Plus, AdBlue | `benzinplus`, `dieselplus`, `adblue` | copy a package and a view, then replace `n95` with the argument |

## Get your access key (free, easy)

mBenzin blocks plain scraping with a browser check, so the usual `scrape` integration does not work. But they offer a **personal access key** for Home Assistant users. Just e-mail **reklama@mbenzin.cz** and tell them what the prices are for, which stations/city, and how often you load them. (For me it was answered quickly and the key worked immediately.)

- The key is **personal — never share it or commit it**. Everyone requests their own.
- Limit: **20 pages per hour** per key. Each fuel uses 5 calls a day, spread over the day.
- It uses mBenzin's price-map data, which is not a documented public API: be gentle, keep the refresh rate low, and respect their conditions.

## Install

1. **Script** — copy `mbenzin_top5.py` to your HA config folder (next to `configuration.yaml`) and edit the two lines at the top:
   - `CITY` — the city part of any station URL on mbenzin.cz, e.g. `/Hradec-Kralove/`
   - `HOME_SLUG` — your usual station, the station part of its URL (`.../Ceny-benzinu-a-nafty/<City>/<STATION-SLUG>/<id>`), or `""` to disable the home feature
2. **Key** — add `mbenzin_key: "YOUR_KEY"` to your `secrets.yaml` (see `secrets.example.yaml`). The script reads that line from the `secrets.yaml` next to it (or from the `MBENZIN_KEY` environment variable); the key never appears in your other YAML files.
3. **Packages** — make sure packages are enabled in `configuration.yaml`:
   ```yaml
   homeassistant:
     packages: !include_dir_named packages
   ```
   then copy the package of each fuel you want from `packages/` into your `packages/` folder.
4. **Restart** Home Assistant (a `command_line` sensor needs a restart the first time). You get `sensor.mbenzin_<fuel>_top5`, `…_home` and `…_1` to `…_5`.
5. **Dashboard** — install [`button-card`](https://github.com/custom-cards/button-card) from HACS. Then Dashboard → Edit → add a view → ⋮ → *Edit in YAML* → paste a file from `dashboard/` → Save. Repeat for each fuel.
6. **Logos (optional)** — the cards show round chain logos if you place `orlen.png`, `makro.png`, … (128 px) in `config/www/`. Logos are trademarks, so none are included; missing ones are simply hidden. Adjust the `LOGOS` map in the dashboard for your chains.
7. **Notification (optional)** — see `examples/price_alert.yaml`.

## Notes

- **E10** is not distinguished by mBenzin: "Natural 95" is the price shown for 95-octane petrol.
- If your usual station does not sell a fuel (typically LPG or CNG), the "My station" card of that view stays empty — just remove that first card from the view.
- Prices older than a few days are hidden, because stale prices are misleading: 1 day for petrol/diesel (today + yesterday), 3 days for CNG, 7 days for LPG and AdBlue (`MAX_AGE_DAYS_BY_FUEL` in the script).
- Trends start empty and fill up as the daily log grows; a `*` marks a trend computed from a shorter history.
- The home sensor has `state_class: measurement`, so Home Assistant keeps its long-term statistics (the 30-day graph).
- Entity names are `sensor.mbenzin_<fuel>_…`; rename them in the UI if you like (the `unique_id` is kept).

## 🇨🇿 Stručně česky

Ceny **benzínu, nafty, LPG a CNG** v jednom městě z [mBenzin.cz](https://www.mbenzin.cz) v Home Assistantu: žebříček 5 nejlevnějších stanic ve městě, sledování „své“ stanice (trendy 1/2/7/14/30 dní, pořadí ve městě, notifikace při změně ceny) a mapa s cenami. Pro každé palivo je samostatný pohled — nainstalujte jen ty, které potřebujete.

- Klasický `scrape` nefunguje (ověření prohlížeče), ale mBenzin zdarma vystavuje **osobní přístupový klíč** — napište na **reklama@mbenzin.cz**, k čemu ceny používáte, o které stanice jde a jak často je načítáte.
- Klíč je osobní, nesdílejte ho; každý si žádá vlastní. Limit je 20 stránek za hodinu; skript volá web jen 5× denně pro každé palivo.
- Instalace: viz kroky výše (skript → klíč v `secrets.yaml` → balíček (package) → restart → dashboard). V skriptu stačí upravit `CITY` a `HOME_SLUG`.

## License

MIT — see [LICENSE](LICENSE).
