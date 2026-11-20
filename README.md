<p align="center"><img src="https://raw.githubusercontent.com/donthedandy/ha-ceny-paliv/main/docs/logo.png" alt="Ceny paliv" width="420"></p>

# ⛽ Ceny paliv – Czech fuel prices for Home Assistant

**English** · [Česky](README.cs.md)

A HACS integration that shows the cheapest stations of **your city** for the fuel(s) you use — **Natural 95, Diesel, LPG, CNG** and more — plus **your favourite station** with price history and trends. Everything is configured from the Home Assistant UI.

<p align="center">
  <img src="https://raw.githubusercontent.com/donthedandy/ha-ceny-paliv/main/docs/card.png" alt="The card: favourite station with trends and the 5 cheapest stations, with logos" width="330">
  &nbsp;
  <img src="https://raw.githubusercontent.com/donthedandy/ha-ceny-paliv/main/docs/map-graph.png" alt="The map of the cheapest stations and the 30-day graph" width="330">
</p>

> **Ceny paliv** (Czech for “fuel prices”) is an independent project. The prices come from [mBenzin.cz](https://www.mbenzin.cz); this project is not made, endorsed or supported by mBenzin.cz.

## Features

- Pick your **city** (or **a point on the map with a radius**), one or **several fuels** (e.g. Natural 95 + LPG for a dual-fuel car) and a **favourite station per fuel**
- Follow **as many places as you like** (home, the city you drive to, a holiday area…): one key, an **Add place** button, one card per place
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
   2. choose the **kind of place**: *a town from the list*, or *around a point* (a marker on the map and a radius, 10 km by default, centred on your Home Assistant location)
   3. choose the town (or move the marker and set the radius)
   4. choose your **fuel(s)** and the **language** of the dashboard texts (English / Čeština)
   5. for each fuel, choose your **favourite station** from the stations of the place (or "—" for none)
   6. optionally tick the **logos** of the chains to show (the chains of your place are preselected; see [Station logos](#4-station-logos-optional))

You can change the place, the fuels, the language, the favourite stations and the logos later: the integration's **Configure** button.

> The setup screens follow Home Assistant's own language (English and Czech are provided). The language chosen in step 3 only sets the labels of the dashboard card.

## Entities

For each fuel `<fuel>` (`n95`, `benzinplus`, `diesel`, `dieselplus`, `lpg`, `cng`, `adblue`):

| Entity | What |
|---|---|
| `sensor.ceny_paliv_<fuel>_top5` | price of the cheapest station; attributes: the 5 stations (name, address, price, coordinates, Google Maps link, trends…) |
| `sensor.ceny_paliv_<fuel>_home` | price at your favourite station (only if you chose one); trends, rank, statistics |
| `sensor.ceny_paliv_<fuel>_1` … `_5` | the 5 cheapest stations, with latitude/longitude for the map card |

The sensors are named after the station they currently show (for example `1 · Orlen – Bratri Stefanu 69`); the entity ids never change. Prices refresh every 6 hours. If a refresh fails (for example HTTP 429) the last data is kept and the attribute `fetch_error` says why.

## More places (optional)

On the integration page, the **Add place** button adds another town or point with its own fuels and favourite stations: for example your home town and the city you often drive to. The places share the key and the language. Each place has its own sensors and its own card; remove a place from its ⋮ menu.

<p align="center"><img src="https://raw.githubusercontent.com/donthedandy/ha-ceny-paliv/main/docs/add-place-button.png" alt="The Add place button on the integration page" width="640"></p>

1. Click **Add place** and choose the **kind of place**: a town from the list, or a point on the map with a radius.
2. For a point, move the marker (or type the coordinates), set the radius in metres and, if you like, give the place a name. Here: Plzeň, 10 km.
3. Choose the fuels and your favourite stations, as for the first place.

<p align="center">
  <img src="https://raw.githubusercontent.com/donthedandy/ha-ceny-paliv/main/docs/add-place-kind.png" alt="Kind of place: a town from the list or around a point" width="300">
  &nbsp;
  <img src="https://raw.githubusercontent.com/donthedandy/ha-ceny-paliv/main/docs/add-place-point.png" alt="Point and radius: a marker on the map and a radius of 10 km" width="300">
</p>

- **Which kind of place?** A *town* follows the stations that mBenzin files under that town name. Some towns are split by mBenzin into districts (Plzeň has `Plzen`, `Plzen---Koterov`, …), and a few stations are filed under the wrong town. If the list of a town looks incomplete, use *Around a point* instead: every station inside the circle is included, whatever the town name.
- **Already installed?** Nothing changes by itself: your current place keeps its sensors, its names and its price history. To follow your current place as a point, open **Configure** and choose *Around a point*: the sensors keep their ids and the history stays, you only pick your favourite station again.
- Sensors of the first place keep the ids `sensor.ceny_paliv_<fuel>_…`; the ones of the other places are `sensor.ceny_paliv_<place>_<fuel>_…` and their names end with the name of the place.

## When something goes wrong

- **mBenzin answers "too many requests" (HTTP 429):** the integration keeps the last prices, flags the problem in the attribute `fetch_error` and sends **no request at all** until the time mBenzin asked for (`Retry-After`, at most 24 hours; without it, almost one refresh interval). It does not hammer the server.
- **mBenzin refuses your key:** after a clear refusal (or an unreadable answer twice in a row) Home Assistant shows **Reauthenticate** on the integration: enter the new key and everything continues, no need to delete anything.
- **No fresh prices for 24 hours:** the sensors become **unavailable** and a **Repairs** notice explains which fuels, since when and where to look. They come back by themselves. Shorter outages keep the last prices.
- **Refresh now:** the action `ceny_paliv.refresh` loads the prices immediately (optionally for one entry: `config_entry_id`). Data downloaded less than 30 minutes ago is not downloaded again, so it cannot flood mBenzin.
- **Diagnostics:** *Download diagnostics* on the integration gives the settings and the state of the last refresh, without your key and without the places or favourite stations that point to where you live.
- Each place has its own **device** (the sensors are grouped under it); removing a fuel removes its sensors, and a favourite you remove is kept as a disabled diagnostic sensor so its history is not lost. Malformed entries in mBenzin's data are skipped instead of stopping the refresh.

## 3. The dashboard card (included, nothing else to install)

The integration ships its own card, **`ceny-paliv-card`**. After installing (and restarting) just:

1. Open a dashboard → **Edit** → **Add card** → search **Ceny paliv**.
2. Pick the **fuel** (the visual editor lists the fuels you set up). Done.

<p align="center"><img src="https://raw.githubusercontent.com/donthedandy/ha-ceny-paliv/main/docs/card-editor.png" alt="The visual editor of the card: parts to show, layout, number of stations" width="360"></p>

Or in YAML:

```yaml
type: custom:ceny-paliv-card
fuel: n95            # n95 | benzinplus | diesel | dieselplus | lpg | cng | adblue
```

One card per fuel: for a dual-fuel car add a second card with `fuel: lpg`. The card has four parts: your favourite station (price, trends, rank), the top 5 with a Google Maps link on tap, a map and the 30-day graph. Everything below is also in the card's visual editor.

| Option | Default | |
|---|---|---|
| `fuel` | – | required |
| `place` | first place | the name of the place, when you follow several (the visual editor offers a list) |
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
- Entity ids are `sensor.ceny_paliv_<fuel>_…` for the first place and `sensor.ceny_paliv_<place>_<fuel>_…` for the others. Town names are shown with their Czech spelling (Dobřany) when mBenzin gives it.
- The daily price log used for the trends is stored by Home Assistant and fills up over time (a `*` next to a trend in the card marks a trend computed from a shorter history).

## 🇨🇿 Česky

Úplný český popis (získání klíče, instalace přes HACS, senzory, dashboard) najdete v **[README.cs.md](README.cs.md)**. Stručně: klíč zdarma na reklama@mbenzin.cz, HACS → Vlastní repozitáře → `https://github.com/donthedandy/ha-ceny-paliv` (Integrace) → restart → Přidat integraci **Ceny paliv**.

## Roadmap

What is planned is tracked in the open, one issue per feature:

- **[v0.7.0](https://github.com/donthedandy/ha-ceny-paliv/milestone/1)** – smarter data: follow a person or device, more location sources, average prices, older prices, cleaner addresses, price-change events and blueprints.
- **[v0.8.0](https://github.com/donthedandy/ha-ceny-paliv/milestone/2)** – a richer card: station details with navigation, sorting, a comparison graph, tank cost, more maps, badge and tile.

Ideas and votes are welcome: open an issue or add a 👍 to the one you want.

## Credits

The reliability work of 0.6 (waiting after HTTP 429, asking for a new key, diagnostics, Repairs, the refresh action) was inspired by [Vituhlos's fork](https://github.com/Vituhlos/ha-ceny-paliv) of this project, also MIT licensed. Thank you!

## License

MIT — see [LICENSE](LICENSE).
