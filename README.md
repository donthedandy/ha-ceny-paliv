<p align="center"><img src="https://raw.githubusercontent.com/donthedandy/ha-ceny-paliv/main/docs/logo.png" alt="Ceny paliv" width="420"></p>

# ⛽ Ceny paliv – Czech fuel prices for Home Assistant

**English** · [Česky](README.cs.md)

A HACS integration that shows the cheapest stations of **your city** for the fuel(s) you use — **Natural 95, Diesel, LPG, CNG** and more — plus **your favourite station** with price history and trends. Everything is configured from the Home Assistant UI.

![Dashboard](docs/screenshot.webp)

> **Ceny paliv** (Czech for “fuel prices”) is an independent project. The prices come from [mBenzin.cz](https://www.mbenzin.cz); this project is not made, endorsed or supported by mBenzin.cz.

## Features

- Pick your **city**, one or **several fuels** (e.g. Natural 95 + LPG for a dual-fuel car) and a **favourite station per fuel**
- Per fuel: the **top 5 cheapest** stations in the city (only that city, not the region), with a Google Maps link, and a **map**
- Favourite station: price, **trends vs 1/2/7/14/30 days ago**, rank in town, long-term statistics (the 30-day graph)
- A ready-made **dashboard card** (`ceny-paliv-card`) shipped with the integration — add it from the card picker, no YAML to copy — in **English or Czech** (your choice during setup). It is **flexible**: two columns on a wide dashboard, one on a phone, a compact version, and every part (favourite station, list, map, graph) can be placed as its own card
- Optional **station logos** (Orlen, MOL, Shell, Tesco…): tick the chains you want in the setup and they are downloaded for you. Chains without a logo get a colour badge with their initials
- Stale prices are hidden (older than yesterday for petrol/diesel, 3 days for CNG, 7 days for LPG/AdBlue)

## 1. Get your access key (free)

mBenzin blocks plain scraping with a browser check, but they give a **personal access key** to Home Assistant users. E-mail **reklama@mbenzin.cz** and tell them what the prices are for, which city/stations, and how often you load them. (For me the answer came quickly and the key worked immediately.)

- The key is **personal — never share it or publish it**. Everyone requests their own.
- Limit: **20 pages per hour** per key. This integration makes 4 calls a day per fuel.
- It uses mBenzin's price-map data, which is not a documented public API: be gentle and respect their conditions.

## 2. Install with HACS

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/donthedandy/ha-ceny-paliv`, category **Integration**.
2. Search for **Ceny paliv**, download it, **restart** Home Assistant.
3. Settings → Devices & services → **Add integration** → **Ceny paliv**, then:
   1. paste your **access key**
   2. choose your **city**
   3. choose your **fuel(s)** and the **language** of the dashboard texts (English / Čeština)
   4. for each fuel, choose your **favourite station** from the list of stations of your city (or "—" for none)
   5. optionally tick the **logos** of the chains to show (the chains of your city are preselected; see [Station logos](#4-station-logos-optional))

You can change the fuels, the language, the favourite stations and the logos later: the integration's **Configure** button.

> The setup screens follow Home Assistant's own language (English and Czech are provided). The language chosen in step 3 only sets the labels of the dashboard card.

## Entities

For each fuel `<fuel>` (`n95`, `benzinplus`, `diesel`, `dieselplus`, `lpg`, `cng`, `adblue`):

| Entity | What |
|---|---|
| `sensor.ceny_paliv_<fuel>_top5` | price of the cheapest station; attributes: the 5 stations (name, address, price, coordinates, Google Maps link, trends…) |
| `sensor.ceny_paliv_<fuel>_home` | price at your favourite station (only if you chose one); trends, rank, statistics |
| `sensor.ceny_paliv_<fuel>_1` … `_5` | the 5 cheapest stations, with latitude/longitude for the map card |

The sensors are named after the station they currently show (for example `1 · Orlen – Bratri Stefanu 69`); the entity ids never change. Prices refresh every 6 hours. If a refresh fails (for example HTTP 429) the last data is kept and the attribute `fetch_error` says why.

## 3. The dashboard card (included, nothing else to install)

The integration ships its own card, **`ceny-paliv-card`**. After installing (and restarting) just:

1. Open a dashboard → **Edit** → **Add card** → search **Ceny paliv**.
2. Pick the **fuel** (the visual editor lists the fuels you set up). Done.

Or in YAML:

```yaml
type: custom:ceny-paliv-card
fuel: n95            # n95 | benzinplus | diesel | dieselplus | lpg | cng | adblue
```

One card per fuel: for a dual-fuel car add a second card with `fuel: lpg`. The card has four parts: your favourite station (price, trends, rank), the top 5 with a Google Maps link on tap, a map and the 30-day graph. Everything below is also in the card's visual editor.

| Option | Default | |
|---|---|---|
| `fuel` | – | required |
| `show` | `[home, list, map, graph]` | the parts to draw: `home` (favourite station), `list` (cheapest stations), `map`, `graph` (30 days) |
| `layout` | `auto` | `auto`: two columns (station and list on the left, map and graph on the right) when the card is wide, one column when it is narrow, as on a phone; `columns`: always two; `stack`: always one |
| `stations` | `5` | how many stations in the list (1–5, also on the map) |
| `compact` | `false` | dense version: one line per station, trends on one line, no legend |
| `show_footer` | `true` (`false` if `compact`) | update times and legend below the list |
| `map_height` | automatic | height of the map in pixels |
| `logo_path` | – | only to use your own PNG files instead of the logo pack (see below) |

Texts follow the language chosen in the setup. If the card does not show up after an update, reload the browser page (Ctrl+F5).

### Place the parts where you want

Use several cards with `show` to put each part anywhere in a dashboard, with other cards in between:

```yaml
type: custom:ceny-paliv-card
fuel: n95
show: [home]          # only my station
---
type: custom:ceny-paliv-card
fuel: n95
show: [list]
stations: 3
compact: true         # small tile with the 3 cheapest stations
---
type: custom:ceny-paliv-card
fuel: n95
show: [map, graph]
map_height: 260
```

(The three cards are separate; `---` only separates them here.) In a *sections* dashboard the card also resizes itself to its content.

For a notification when your station's price changes, see `examples/price_alert.yaml`.

## 4. Station logos (optional)

The card shows a round logo for the chain of each station. Without a logo it draws a coloured badge with the initials of the chain (`OR`, `PR`…), so nothing has to be set up.

To have the real logos, open **Settings → Devices & services → Ceny paliv → Configure** and go to the **Station logos** step: tick the chains you want. They are downloaded (a few KB each) from the [logo pack](logos/) in this repository into the folder `ceny_paliv_logos` of your Home Assistant configuration and the card finds them by itself. Untick a chain to remove its logo. The chains of your city are preselected the first time. Nothing is downloaded unless you tick it, and the pack is not installed with the integration.

The pack is also published as **`ceny-paliv-logos.zip`** in each [release](https://github.com/donthedandy/ha-ceny-paliv/releases): unzip it into `<config>/ceny_paliv_logos/` if you prefer to do it by hand (restart or reload the integration to pick up new files). You can drop your own square PNG there too, named after the chain in lower case, without accents, with dashes for spaces (`eurobit.png`, `robin-oil.png`): such files are used and never deleted. To use files from another folder, set `logo_path: /local/logos/` on the card (files named like the chain, for example `/local/logos/orlen.png`).

The logos are trademarks of their owners, used only to identify the stations; this project is not affiliated with them. The sources and the removal policy are in [logos/SOURCES.md](logos/SOURCES.md).

## 5. Without the card: standard cards

Every sensor is named after what it currently shows (for example `1 · Orlen – Bratri Stefanu 69`), so any standard card displays the station without a template. The names follow the ranking and update at each refresh; the entity ids never change.

An **Entities** card with the 5 cheapest stations (the sensor state is the price):

```yaml
type: entities
title: Natural 95
entities:
  - sensor.ceny_paliv_n95_1
  - sensor.ceny_paliv_n95_2
  - sensor.ceny_paliv_n95_3
  - sensor.ceny_paliv_n95_4
  - sensor.ceny_paliv_n95_5
```

A **Markdown** card with the address and a Google Maps link:

```yaml
type: markdown
title: Natural 95 – top 5
content: |-
  {% for s in (state_attr('sensor.ceny_paliv_n95_top5', 'stations') or []) %}
  {{ s.rank }}. **{{ s.name }}** – {{ s.street }}: **{{ '%.2f' | format(s.price) }} Kč/l** · [Maps]({{ s.maps }})
  {% endfor %}
```

Each station in the `stations` attribute of `sensor.ceny_paliv_<fuel>_top5` has: `rank`, `name`, `street`, `address`, `price`, `lat`, `lng`, `updated`, `maps`, `home` and `trends`. Use the `_home` sensor for your favourite station (its attributes include `rank`, `vs_cheapest` and `trends`).

## Notes

- **E10** is not distinguished by mBenzin: "Natural 95" is the price shown for 95-octane petrol.
- Entity ids are `sensor.ceny_paliv_<fuel>_…`. A second city would get a `_2` suffix.
- The daily price log used for the trends is stored by Home Assistant and fills up over time (a `*` next to a trend in the card marks a trend computed from a shorter history).

## 🇨🇿 Česky

Úplný český popis (získání klíče, instalace přes HACS, senzory, dashboard) najdete v **[README.cs.md](README.cs.md)**. Stručně: klíč zdarma na reklama@mbenzin.cz, HACS → Vlastní repozitáře → `https://github.com/donthedandy/ha-ceny-paliv` (Integrace) → restart → Přidat integraci **Ceny paliv**.

## License

MIT — see [LICENSE](LICENSE).
