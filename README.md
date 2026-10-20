# ⛽ mBenzin – Czech fuel prices for Home Assistant

**English** · [Česky](README.cs.md)

A HACS integration that shows the cheapest stations of **your city** for the fuel(s) you use — **Natural 95, Diesel, LPG, CNG** and more — plus **your favourite station** with price history and trends. Everything is configured from the Home Assistant UI.

![Dashboard](docs/screenshot.webp)

> Unofficial project, not affiliated with mBenzin.cz. Data: [mBenzin.cz](https://www.mbenzin.cz).

## Features

- Pick your **city**, one or **several fuels** (e.g. Natural 95 + LPG for a dual-fuel car) and a **favourite station per fuel**
- Per fuel: the **top 5 cheapest** stations in the city (only that city, not the region), with a Google Maps link, and a **map**
- Favourite station: price, **trends vs 1/2/7/14/30 days ago**, rank in town, long-term statistics (the 30-day graph)
- Ready-made **dashboard views** (one per fuel), optional, in **English or Czech** (your choice during setup)
- Stale prices are hidden (older than yesterday for petrol/diesel, 3 days for CNG, 7 days for LPG/AdBlue)

## 1. Get your access key (free)

mBenzin blocks plain scraping with a browser check, but they give a **personal access key** to Home Assistant users. E-mail **reklama@mbenzin.cz** and tell them what the prices are for, which city/stations, and how often you load them. (For me the answer came quickly and the key worked immediately.)

- The key is **personal — never share it or publish it**. Everyone requests their own.
- Limit: **20 pages per hour** per key. This integration makes 4 calls a day per fuel.
- It uses mBenzin's price-map data, which is not a documented public API: be gentle and respect their conditions.

## 2. Install with HACS

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/donthedandy/ha-mbenzin-ceny-paliv`, category **Integration**.
2. Search for **mBenzin**, download it, **restart** Home Assistant.
3. Settings → Devices & services → **Add integration** → **mBenzin**, then:
   1. paste your **access key**
   2. choose your **city**
   3. choose your **fuel(s)** and the **language** of the dashboard texts (English / Čeština)
   4. for each fuel, choose your **favourite station** from the list of stations of your city (or "—" for none)

You can change the fuels, the language and the favourite stations later: the integration's **Configure** button.

> The setup screens follow Home Assistant's own language (English and Czech are provided). The language chosen in step 3 only sets the labels of the ready-made dashboard views.

## Entities

For each fuel `<fuel>` (`n95`, `benzinplus`, `diesel`, `dieselplus`, `lpg`, `cng`, `adblue`):

| Entity | What |
|---|---|
| `sensor.mbenzin_<fuel>_top5` | price of the cheapest station; attributes: the 5 stations (name, address, price, coordinates, Google Maps link, trends…) |
| `sensor.mbenzin_<fuel>_home` | price at your favourite station (only if you chose one); trends, rank, statistics |
| `sensor.mbenzin_<fuel>_1` … `_5` | the 5 cheapest stations, with latitude/longitude for the map card |

Prices refresh every 6 hours. If a refresh fails (for example HTTP 429) the last data is kept and the attribute `fetch_error` says why.

## 3. Dashboard (optional)

1. Install [`button-card`](https://github.com/custom-cards/button-card) from HACS.
2. Dashboard → Edit → add a view → ⋮ → *Edit in YAML* → paste `dashboard/fuel_view_<fuel>.yaml` (n95, diesel, lpg, cng) → Save. One view per fuel.
3. Round chain logos are shown if you put `orlen.png`, `makro.png`, … (128 px) in `config/www/`. They are trademarks, so none are included; missing ones are just hidden. Adjust the `LOGOS` map in the view for your chains.
4. No favourite station for that fuel? Remove the first card (and the `…_home` line in the map card) from the view.

For a notification when your station's price changes, see `examples/price_alert.yaml`.

## Notes

- **E10** is not distinguished by mBenzin: "Natural 95" is the price shown for 95-octane petrol.
- Entity ids are `sensor.mbenzin_<fuel>_…`. A second city would get a `_2` suffix.
- The daily price log used for the trends is stored by Home Assistant and fills up over time (a `*` in the view marks a trend computed from a shorter history).

## 🇨🇿 Česky

Úplný český popis (získání klíče, instalace přes HACS, senzory, dashboard) najdete v **[README.cs.md](README.cs.md)**. Stručně: klíč zdarma na reklama@mbenzin.cz, HACS → Vlastní repozitáře → `https://github.com/donthedandy/ha-mbenzin-ceny-paliv` (Integrace) → restart → Přidat integraci **mBenzin**.

## License

MIT — see [LICENSE](LICENSE).
