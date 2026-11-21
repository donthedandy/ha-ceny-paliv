/*
 * Ceny paliv card — shipped with the Ceny paliv integration, nothing to install separately.
 * Prices come from mBenzin.cz; this project is independent and not affiliated with mBenzin.
 *
 *   type: custom:ceny-paliv-card
 *   fuel: n95            # n95 | benzinplus | diesel | dieselplus | lpg | cng | adblue
 *
 * Optional (all of them are also in the visual editor: Add card > Ceny paliv; the editor saves only what you changed):
 *   place: Praha          # which place, when you follow several (name of the place; default: the first one)
 *   show: [home, list, map, graph]   # parts: home, list, map, graph, prices, regions, tank, road, places
 *   layout: auto         # auto = 2 columns when the card is wide | columns | stack
 *   stations: 5          # 1-10 stations in the list
 *   sort: price          # price | distance; chips let you switch
 *   navigation: google   # google | mapy | waze: the app of the "Navigate" button
 *   fuel_switch: false   # chips to switch the fuel without editing the card
 *   tank_size: 40        # litres of a full tank (the tank part)
 *   places: [Praha, Brno] # several places side by side (part "places")
 *   look: dark           # dark | ha (colours of your Home Assistant theme)
 *   big: false           # wall panel: one big price
 *   compact: false       # dense version: one line per station, short footer
 *   show_footer: true    # update times, legend (default: false when compact)
 *   map_height: 300      # px, default: the map card's own height
 *   logo_path: /local/   # only to use your own PNG files instead of the downloaded logo pack
 *
 * Also in this file:
 *   type: custom:ceny-paliv-badge          # a fuel price as a badge (fuel, place, show: cheapest | home)
 *   features: [{type: custom:ceny-paliv-tile-feature}]   # on a tile card whose entity is a Ceny paliv sensor
 *
 * Station logos: tick the chains in the integration's setup (Configure > Station logos); the card finds them by
 * itself. Chains without a logo get a coloured badge with their initials.
 *
 * Texts come from the language chosen in the integration setup (attribute `labels` of the top5 sensor).
 */
const CARD_VERSION = '0.8.1';

const DEFAULT_PARTS = ['home', 'list', 'map', 'graph'];
const COL_A = ['home', 'road', 'list', 'tank', 'places'];
const COL_B = ['map', 'prices', 'graph', 'regions'];
const PARTS = [...COL_A, ...COL_B];
const FUEL_ORDER = ['n95', 'benzinplus', 'diesel', 'dieselplus', 'lpg', 'cng', 'adblue'];
// mBenzin asks for the source to be shown with its prices, as a link
const SOURCE = '<a href="https://www.mbenzin.cz" target="_blank" rel="noopener noreferrer" style="color:inherit">Ceny: mbenzin.cz</a>';
const REGIONS_URL = '/ceny_paliv_static/regions.json';

const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const norm = (s) => String(s == null ? '' : s).normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/\s+/g, ' ').trim();
const num = (v) => { const n = Number(v); return v === null || v === undefined || v === '' || isNaN(n) ? null : n; };
const fp = (p) => Number(p).toFixed(2);
const km = (lat1, lng1, lat2, lng2) => {
  const r = Math.PI / 180; const dl = (lat2 - lat1) * r; const dg = (lng2 - lng1) * r;
  const a = Math.sin(dl / 2) ** 2 + Math.cos(lat1 * r) * Math.cos(lat2 * r) * Math.sin(dg / 2) ** 2;
  return 12742 * Math.asin(Math.sqrt(a));
};
// price scale: green (cheap) to red (dear)
const heat = (t) => `hsl(${Math.round(140 * (1 - Math.min(1, Math.max(0, t))))} 62% 46%)`;

// Texts of the card itself (the integration sends the others as `labels`)
const TXT = {
  en: {
    sort_price: 'Price', sort_distance: 'Distance', details: 'Station', navigate: 'Navigate', close: 'Close',
    mbenzin: 'Open on mBenzin', away: '{d} km away',
    graph_title: 'Last 30 days', g_home: 'My station', g_cheapest: 'Cheapest', g_area: 'Average', g_sum: '{n} days: town average {a} · lowest {lo} · highest {hi} Kč/l', g_none: 'No history yet: the graph fills in as prices are recorded.',
    g_loading: 'Loading the history…', tank_title: 'Full tank · {l} l', tank_fuel: 'Fuel', tank_cheapest: 'Cheapest', tank_mine: 'My station', tank_avg: 'Average',
    tank_cost: 'Full tank', tank_save: 'Saving', compare: 'Comparison', regions_title: 'Average price by region', region_cheapest: 'cheapest', region_dearest: 'dearest',
    region_info: '{n} stations · {v} against the country', rank_of: '#{r} of {t}', prices_title: 'Stations on the map', prices_empty: 'No stations to show.', prices_outside: 'farther away',
    road_title: 'On the road', road_need: 'Needs a place that follows a person (source “Person”) or a point.', places_title: 'Places', no_place: 'Place not found',
    badge_cheapest: 'Cheapest', badge_home: 'My station', tile_cheapest: 'Cheapest', tile_avg: 'Average', tile_rank: 'Rank',
  },
  cs: {
    sort_price: 'Cena', sort_distance: 'Vzdálenost', details: 'Stanice', navigate: 'Navigovat', close: 'Zavřít',
    mbenzin: 'Otevřít na mBenzin', away: '{d} km daleko',
    graph_title: 'Posledních 30 dní', g_home: 'Moje stanice', g_cheapest: 'Nejlevnější', g_area: 'Průměr', g_sum: '{n} dní: průměr ve městě {a} · nejnižší {lo} · nejvyšší {hi} Kč/l', g_none: 'Zatím žádná historie: graf se plní s ukládáním cen.',
    g_loading: 'Načítám historii…', tank_title: 'Plná nádrž · {l} l', tank_fuel: 'Palivo', tank_cheapest: 'Nejlevnější', tank_mine: 'Moje stanice', tank_avg: 'Průměr',
    tank_cost: 'Plná nádrž', tank_save: 'Úspora', compare: 'Srovnání', regions_title: 'Průměrná cena podle kraje', region_cheapest: 'nejlevnější', region_dearest: 'nejdražší',
    region_info: '{n} stanic · {v} oproti celé ČR', rank_of: '{r}. z {t}', prices_title: 'Stanice na mapě', prices_empty: 'Žádné stanice k zobrazení.', prices_outside: 'dál',
    road_title: 'Na cestě', road_need: 'Potřebuje místo, které sleduje osobu (zdroj „Osoba“), nebo bod.', places_title: 'Místa', no_place: 'Místo nenalezeno',
    badge_cheapest: 'Nejlevnější', badge_home: 'Moje stanice', tile_cheapest: 'Nejlevnější', tile_avg: 'Průměr', tile_rank: 'Pořadí',
  },
};

// Every Ceny paliv sensor of Home Assistant, by place and fuel. The sensors are found by their attributes, so the card
// does not depend on how Home Assistant names the entities (device name prefix, renamed entities, second city...).
// Older installs without the attributes are matched on the entity id suffix (..._<fuel>_top5, _home, _1 .. _5).
function scan(hass) {
  const places = {};
  for (const id of Object.keys(hass.states)) {
    if (!id.startsWith('sensor.ceny_paliv_')) continue;
    const a = hass.states[id].attributes || {};
    let fuel = null; let role = null; let idx = 0; let key = 'main'; let name = '';
    if (a.cp_fuel) {
      fuel = a.cp_fuel; role = a.cp_role; idx = a.cp_index || 0; key = a.cp_place || 'main'; name = a.cp_place_name || '';
    } else {
      const m = id.match(/_([a-z0-9]+)_(top5|home|[1-5])$/);
      if (!m) continue;
      fuel = m[1]; role = m[2] === 'top5' ? 'top5' : m[2] === 'home' ? 'home' : 'position'; idx = /^\d$/.test(m[2]) ? Number(m[2]) : 0;
    }
    const p = places[key] || (places[key] = { key, name, fuels: {} });
    if (name) p.name = name;
    const f = p.fuels[fuel] || (p.fuels[fuel] = { top5: null, home: null, pos: [], avg: {} });
    if (role === 'top5') f.top5 = id;
    else if (role === 'home') f.home = id;
    else if (role === 'position' && idx >= 1 && idx <= 5) f.pos[idx - 1] = id;
    else if (role === 'national_average') f.avg.national = id;
    else if (role === 'region_average') f.avg.region = id;
    else if (role === 'area_average') f.avg.area = id;
  }
  return places;
}

function pickPlace(places, wanted) {
  const want = norm(wanted);
  const keys = Object.keys(places);
  const key = (want && keys.find((k) => norm(places[k].name) === want || norm(k) === want)) || (places.main ? 'main' : keys[0]);
  return places[key] || null;
}

let regionsPromise = null;
function loadRegions() {
  if (!regionsPromise) {
    regionsPromise = fetch(REGIONS_URL).then((r) => (r.ok ? r.json() : null)).catch(() => null);
  }
  return regionsPromise;
}

const STYLE = `
  :host { display: block; }
  .wrap { --cp-bg: #171a20; --cp-bg2: #0e1014; --cp-border: #262a33; --cp-line: #23272f; --cp-chip: #1f232b; --cp-text: #eef0f3; --cp-text2: #d6dae1;
          --cp-sub: #9aa1ad; --cp-dim: #5b6270; --cp-good: #5fd39a; --cp-warn: #f5c26b; --cp-bad: #ff7a6b; --cp-accent: #4cc3d9; --cp-amber: #f5b14c;
          --cp-radius: 22px; }
  .wrap.ha { --cp-bg: var(--ha-card-background, var(--card-background-color, #fff)); --cp-bg2: var(--primary-background-color, #fafafa);
          --cp-border: var(--divider-color, #e0e0e0); --cp-line: var(--divider-color, #e0e0e0); --cp-chip: var(--secondary-background-color, #f2f2f2);
          --cp-text: var(--primary-text-color, #212121); --cp-text2: var(--primary-text-color, #212121); --cp-sub: var(--secondary-text-color, #727272);
          --cp-dim: var(--disabled-text-color, #9e9e9e); --cp-good: var(--success-color, #43a047); --cp-warn: var(--warning-color, #f4a100);
          --cp-bad: var(--error-color, #db4437); --cp-accent: var(--primary-color, #03a9f4); --cp-amber: var(--warning-color, #f4a100);
          --cp-radius: var(--ha-card-border-radius, 12px); }
  .grid, .col { display: flex; flex-direction: column; gap: 16px; }
  .col { min-width: 0; }
  .grid.columns { flex-direction: row; align-items: flex-start; }
  .grid.columns > .col { flex: 1 1 0; }
  .grid.auto.wide { flex-direction: row; align-items: flex-start; }
  .grid.auto.wide > .col { flex: 1 1 0; }
  .card { background: var(--cp-bg); border: 1px solid var(--cp-border); border-radius: var(--cp-radius); padding: 16px; color: var(--cp-text);
          font-family: var(--ha-font-family-body, Manrope, system-ui, sans-serif); box-sizing: border-box; text-align: left; }
  .wrap:not(.ha) .card { font-family: Manrope, system-ui, sans-serif; }
  .card.compact { padding: 12px 14px; border-radius: 18px; }
  .card.home { border-color: color-mix(in srgb, var(--cp-accent) 30%, transparent); cursor: pointer; }
  .row { display: flex; align-items: center; gap: 12px; padding: 12px 0; border-top: 1px solid var(--cp-line); cursor: pointer; user-select: none; }
  .compact .row { padding: 7px 0; gap: 10px; }
  .row:first-of-type { border-top: none; }
  .map, .graph { border-radius: var(--cp-radius); overflow: hidden; }
  .map.fixed { position: relative; min-width: 200px; }
  .map.fixed > * { position: absolute; inset: 0; display: block; }
  ha-icon { display: inline-block; }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; margin: 0 0 12px; }
  .chip { cursor: pointer; font-size: 12px; font-weight: 700; padding: 5px 11px; border-radius: 999px; background: var(--cp-chip); color: var(--cp-sub);
          border: 1px solid transparent; user-select: none; }
  .chip.on { color: var(--cp-text); border-color: var(--cp-accent); }
  .title { font-size: 15px; font-weight: 700; color: var(--cp-text); }
  .sub { font-size: 12px; color: var(--cp-sub); }
  .muted { font-size: 12px; color: var(--cp-dim); }
  table.t { width: 100%; border-collapse: collapse; font-size: 13px; }
  table.t th { text-align: right; font-weight: 600; color: var(--cp-sub); font-size: 11px; padding: 4px 4px 6px; }
  table.t td { text-align: right; padding: 8px 4px; border-top: 1px solid var(--cp-line); font-weight: 700; white-space: nowrap; }
  table.t th:first-child, table.t td:first-child { text-align: left; }
  .bar { height: 10px; border-radius: 6px; background: var(--cp-chip); overflow: hidden; }
  .bar > i { display: block; height: 100%; border-radius: 6px; }
  svg text { font-family: inherit; }
  .btn { display: flex; align-items: center; justify-content: center; gap: 8px; padding: 11px 12px; border-radius: 14px; background: var(--cp-chip); color: var(--cp-text);
         text-decoration: none; font-weight: 700; font-size: 14px; cursor: pointer; border: 1px solid var(--cp-border); }
  .btn.main { background: var(--cp-accent); color: #fff; border-color: transparent; }
  .sheet { position: fixed; inset: 0; z-index: 8; background: rgba(0,0,0,.55); display: flex; align-items: center; justify-content: center; padding: 16px; box-sizing: border-box; }
  .sheet > .card { width: 100%; max-width: 420px; max-height: 90vh; overflow: auto; display: flex; flex-direction: column; gap: 12px; }
  .big .price { font-size: 88px; font-weight: 800; letter-spacing: -0.04em; line-height: 1; }
`;

class CenyPalivCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._sig = '';
    this._children = null;
    this._timer = null;
    this._detail = null;
    this._regionSel = null;
  }

  setConfig(config) {
    if (!config || !config.fuel) throw new Error('ceny-paliv-card: set "fuel", for example "n95"');
    // show_map / show_graph: options of the first versions, still honoured when `show` is not set
    const legacy = DEFAULT_PARTS.filter((p) => !(p === 'map' && config.show_map === false) && !(p === 'graph' && config.show_graph === false));
    let show = (Array.isArray(config.show) ? config.show : config.show ? [config.show] : legacy).filter((p) => PARTS.includes(p));
    if (!config.show && Array.isArray(config.places) && config.places.length > 1) show = ['places'];
    this._config = Object.assign({ layout: 'auto', stations: 5, compact: false, logo_path: '' }, config);
    this._show = show.length ? show : DEFAULT_PARTS;
    this._layout = ['auto', 'columns', 'stack'].includes(this._config.layout) ? this._config.layout : 'auto';
    this._n = Math.min(10, Math.max(1, Math.round(Number(this._config.stations) || 5)));
    this._compact = !!this._config.compact;
    this._big = !!this._config.big;
    this._footer = this._config.show_footer != null ? !!this._config.show_footer : !this._compact;
    this._mapHeight = Number(this._config.map_height) > 0 ? Number(this._config.map_height) : 0;
    this._tank = Number(this._config.tank_size) > 0 ? Number(this._config.tank_size) : 40;
    this._nav = ['google', 'mapy', 'waze'].includes(this._config.navigation) ? this._config.navigation : 'google';
    this._sort = ['price', 'distance'].includes(this._config.sort) ? this._config.sort : 'price';
    this._look = this._config.look === 'ha' ? 'ha' : 'dark';
    this._fuel = this._config.fuel;
    this._ids = null;
    this._pf = null;
    this._scanAt = 0;
    this._sig = '';
    this._children = null;
    this._detail = null;
    this._stats = null;
    this._build();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._config) return;
    this._ids = this._resolve(hass);
    const top = hass.states[this._ids.top5];
    const home = hass.states[this._ids.home];
    const sig = [top && top.last_updated, home && home.last_updated, top && top.state, home && home.state].join('|');
    if (sig !== this._sig) {
      this._sig = sig;
      this._renderTexts();
    }
    if (this._children) this._children.forEach((c) => { c.hass = hass; });
  }

  // Sensors of the chosen place and fuel. `place` (config) is the name of the place; without it the first place is used.
  _resolve(hass) {
    const c = this._ids;
    const valid = c && c.top5 && hass.states[c.top5] && (!c.home || hass.states[c.home]) && c.pos.every((id) => !id || hass.states[id]);
    const now = Date.now();
    if (valid && (c.home || now - this._scanAt < 10000)) return c;
    this._scanAt = now;
    this._places = scan(hass);
    const chosen = pickPlace(this._places, this._config.place);
    this._pf = (chosen && chosen.fuels) || {};
    this._placeName = chosen ? chosen.name : '';
    return this._pf[this._fuel] || { top5: null, home: null, pos: [], avg: {} };
  }

  _sides() {
    const a = this._show.some((p) => COL_A.includes(p));
    const b = this._show.some((p) => COL_B.includes(p));
    return { a, b, wide: a && b && this._layout !== 'stack' };
  }

  getCardSize() {
    const h = {
      home: this._compact ? 2 : 4, road: 6, list: this._compact ? 1 + this._n : 2 + 2 * this._n, tank: 6, places: 4,
      map: this._mapHeight ? Math.ceil(this._mapHeight / 50) : 6, prices: 6, graph: 5, regions: 6,
    };
    const sd = this._sides();
    const sum = (ids) => this._show.filter((p) => ids.includes(p)).reduce((x, p) => x + h[p], 0);
    if (!sd.wide) return sum(PARTS);
    return Math.max(sum(COL_A), sum(COL_B));
  }

  getGridOptions() {
    const wide = this._config ? this._sides().wide : true;
    return { columns: wide ? 12 : 6, min_columns: wide ? 8 : 3, rows: 'auto' };
  }
  static getConfigElement() { return document.createElement('ceny-paliv-card-editor'); }
  static fuels(hass) {
    const out = [];
    for (const [id, st] of Object.entries((hass && hass.states) || {})) {
      if (!id.startsWith('sensor.ceny_paliv_')) continue;
      const a = st.attributes || {};
      const isTop = a.cp_role === 'top5' || (!a.cp_role && /_top5$/.test(id) && a.fuel);
      if (isTop && a.fuel && !out.some((o) => o.value === a.fuel)) out.push({ value: a.fuel, label: a.fuel_label || a.fuel });
    }
    return out;
  }
  // The places that have this fuel (all places when no fuel is given): [{ value: name, label: name }]
  static places(hass, fuel) {
    const out = [];
    for (const [id, st] of Object.entries((hass && hass.states) || {})) {
      if (!id.startsWith('sensor.ceny_paliv_')) continue;
      const a = st.attributes || {};
      if (a.cp_role === 'top5' && (!fuel || a.cp_fuel === fuel) && a.cp_place_name && !out.some((o) => o.value === a.cp_place_name)) {
        out.push({ value: a.cp_place_name, label: a.cp_place_name });
      }
    }
    return out;
  }
  static getStubConfig(hass) {
    const found = CenyPalivCard.fuels(hass)[0];
    return { type: 'custom:ceny-paliv-card', fuel: found ? found.value : 'n95' };
  }

  // ---------------------------------------------------------------- skeleton
  _build() {
    const root = this.shadowRoot;
    const sd = this._sides();
    const col = (id, ids) => (ids.some((p) => this._show.includes(p))
      ? `<div class="col" id="${id}">${ids.filter((p) => this._show.includes(p)).map((p) => `<div id="${p}"></div>`).join('')}</div>` : '');
    const mode = sd.wide ? this._layout : 'stack';
    root.innerHTML = `<style>${STYLE}</style><div class="wrap${this._look === 'ha' ? ' ha' : ''}${this._big ? ' big' : ''}"><div id="switch"></div><div class="grid ${mode}">${col('colA', COL_A)}${col('colB', COL_B)}</div><div id="sheet"></div></div>`;
    if (!this._listening) {
      this._listening = true;
      root.addEventListener('click', (e) => this._click(e));
      root.addEventListener('pointerdown', (e) => this._down(e));
      ['pointerup', 'pointerleave', 'pointercancel'].forEach((n) => root.addEventListener(n, () => clearTimeout(this._timer)));
    }
    this._extraReady = false;
    this._fit();
  }

  // layout "auto": two columns from 640 px (back to one below 600 px, so it never flip-flops)
  _fit() {
    const grid = this.shadowRoot.querySelector('.grid');
    if (!grid || !grid.classList.contains('auto')) return;
    const w = this.getBoundingClientRect().width;
    if (w >= 640) grid.classList.add('wide');
    else if (w < 600) grid.classList.remove('wide');
  }

  connectedCallback() {
    if (!this._ro && window.ResizeObserver) this._ro = new ResizeObserver(() => this._fit());
    if (this._ro) this._ro.observe(this);
    this._fit();
  }

  disconnectedCallback() {
    if (this._ro) this._ro.disconnect();
  }

  async _buildExtra() {
    if (this._extraReady || !this._hass || !this._show.includes('map')) return;
    this._extraReady = true;
    const helpers = window.loadCardHelpers ? await window.loadCardHelpers() : null;
    if (!helpers) return;
    const hasHome = !!this._hass.states[this._ids.home];
    // A station with a logo is drawn as its logo, the others as their price (the map shows one or the other).
    const mark = (id) => ({ entity: id, focus: true, ...(this._hass.states[id] && this._hass.states[id].attributes.entity_picture ? {} : { label_mode: 'state' }) });
    const entities = this._ids.pos.slice(0, Math.min(this._n, 5)).filter(Boolean).map(mark);
    if (hasHome) entities.push(mark(this._ids.home));
    const config = { type: 'map', theme_mode: this._look === 'ha' ? 'auto' : 'dark', auto_fit: true, default_zoom: 12, hours_to_show: 0, entities };
    const el = helpers.createCardElement(config);
    el.hass = this._hass;
    const wrap = document.createElement('div');
    wrap.className = this._mapHeight ? 'map fixed' : 'map';
    if (this._mapHeight) wrap.style.height = `${this._mapHeight}px`;
    wrap.appendChild(el);
    const slot = this.shadowRoot.getElementById('map');
    if (slot) slot.appendChild(wrap);
    this._children = [el];
  }

  // ---------------------------------------------------------------- helpers
  _labels() {
    const top = this._hass.states[this._ids.top5];
    return (top && top.attributes && top.attributes.labels) || {};
  }

  _lang() {
    const l = this._labels().language || ((this._hass && this._hass.language) || 'en').split('-')[0];
    return TXT[l] ? l : 'en';
  }

  _T(k, v) {
    const lb = this._labels();
    return String(lb[k] !== undefined ? lb[k] : k).replace(/\{(\w+)\}/g, (m, x) => (v && v[x] !== undefined ? v[x] : m));
  }

  // texts of the card itself
  _X(k, v) {
    const t = (TXT[this._lang()] || TXT.en)[k] !== undefined ? TXT[this._lang()][k] : (TXT.en[k] !== undefined ? TXT.en[k] : k);
    return String(t).replace(/\{(\w+)\}/g, (m, x) => (v && v[x] !== undefined ? v[x] : m));
  }

  _top() { return this._hass.states[this._ids.top5]; }
  _attrs() { return (this._top() && this._top().attributes) || {}; }

  _arrow(t) {
    if (!t) return { icon: 'mdi:minus', color: 'var(--cp-dim)', txt: '—' };
    if (t.dir === 'down') return { icon: 'mdi:arrow-down-bold', color: 'var(--cp-good)', txt: '−' + Math.abs(t.delta).toFixed(2) };
    if (t.dir === 'up') return { icon: 'mdi:arrow-up-bold', color: 'var(--cp-bad)', txt: '+' + Math.abs(t.delta).toFixed(2) };
    return { icon: 'mdi:minus', color: 'var(--cp-warn)', txt: '0.00' };
  }

  _age(s, today) {
    if (!s.updated_date) return s.updated === 'Dnes' ? 0 : 99;
    return Math.round((today - new Date(s.updated_date + 'T00:00:00')) / 86400000);
  }

  // URL of the logo of a station's chain, or '' when there is none. Logos come from the downloaded pack (list in the
  // `logos` attribute of the top5 sensor, matched on the chain name) or, with `logo_path`, from your own PNG files.
  _logoUrl(s) {
    const key = norm(s.chain || s.name);
    if (!key) return '';
    const path = this._config.logo_path;
    if (path) return `${path}${key.replace(/ /g, '-')}.png`;
    const list = this._attrs().logos || [];
    let best = null; let len = 0;
    for (const l of list) {
      for (const m of l.match || []) {
        if ((key === m || key.startsWith(m + ' ')) && m.length > len) { best = l.id; len = m.length; }
      }
    }
    return best ? `/ceny_paliv_static/logos/${encodeURIComponent(best)}.png` : '';
  }

  _initials(name) {
    const w = String(name || '?').trim();
    return (w.length <= 3 ? w : w.replace(/[^\p{L}\p{N}]/gu, '').slice(0, 2)).toUpperCase();
  }

  // Round badge: the chain's logo when there is one, else its initials on a colour taken from the name.
  _disc(s, size, extra) {
    const name = s.chain || s.name || '?';
    let h = 0; for (const ch of norm(name)) h = (h * 31 + ch.charCodeAt(0)) % 360;
    const url = this._logoUrl(s);
    const base = `width:${size}px;height:${size}px;border-radius:999px;position:absolute;left:0;top:0;${extra || ''}`;
    const init = `<span style="${base}display:flex;align-items:center;justify-content:center;box-sizing:border-box;font-size:${Math.round(size * 0.36)}px;font-weight:800;letter-spacing:-0.02em;background:hsl(${h} 34% 26%);color:hsl(${h} 70% 86%)">${esc(this._initials(name))}</span>`;
    if (!url) return init;
    return init + `<img src="${esc(url)}" alt="${esc(name)}" onload="this.previousElementSibling.style.visibility='hidden'" onerror="this.style.display='none'" style="${base}display:block;object-fit:cover;background:#fff">`;
  }

  _avatar(s, rank, best) {
    const size = this._compact ? 26 : 32;
    const ring = best ? 'box-shadow:0 0 0 2px var(--cp-good);' : '';
    return `<span style="position:relative;width:${size}px;height:${size}px;flex-shrink:0;display:block">${this._disc(s, size, ring)}<span style="position:absolute;right:-5px;bottom:-5px;min-width:16px;height:16px;padding:0 3px;box-sizing:border-box;border-radius:999px;background:var(--cp-bg2);border:1px solid ${best ? 'var(--cp-good)' : 'var(--cp-border)'};color:${best ? 'var(--cp-good)' : 'var(--cp-text2)'};font-size:10px;font-weight:800;display:flex;align-items:center;justify-content:center">${rank}</span></span>`;
  }

  // The stations of the place: the whole up-to-date list when the integration sends it, else the top 5.
  _pool() {
    const at = this._attrs();
    const pool = Array.isArray(at.map_stations) && at.map_stations.length ? at.map_stations : (Array.isArray(at.stations) ? at.stations : []);
    return pool;
  }

  // Where the distances are measured from: the centre the integration sends (a point or a person), else the
  // Home Assistant home when it is near the place (a town), else the middle of the stations.
  _centre(pool) {
    const c = this._attrs().centre;
    if (c && num(c.lat) !== null) return { lat: Number(c.lat), lng: Number(c.lng), real: true };
    const ok = (pool || []).filter((s) => num(s.lat) !== null);
    if (!ok.length) return null;
    const mid = { lat: ok.reduce((x, s) => x + Number(s.lat), 0) / ok.length, lng: ok.reduce((x, s) => x + Number(s.lng), 0) / ok.length };
    const h = this._hass && this._hass.config;
    if (h && num(h.latitude) !== null && num(h.longitude) !== null && km(Number(h.latitude), Number(h.longitude), mid.lat, mid.lng) <= 60) {
      return { lat: Number(h.latitude), lng: Number(h.longitude), real: true, home: true };
    }
    return { lat: mid.lat, lng: mid.lng, real: false };
  }

  _distance(s, centre) {
    if (s.distance_km != null) return Number(s.distance_km);
    if (!centre || num(s.lat) === null) return null;
    return km(centre.lat, centre.lng, Number(s.lat), Number(s.lng));
  }

  _sorted(pool, mode) {
    const centre = this._centre(pool);
    const rows = pool.map((s) => Object.assign({}, s, { _w: { d: this._distance(s, centre) } }));
    const byPrice = (a, b) => Number(a.price) - Number(b.price);
    if (mode === 'distance') rows.sort((a, b) => ((a._w.d == null ? 1e9 : a._w.d) - (b._w.d == null ? 1e9 : b._w.d)) || byPrice(a, b));
    else rows.sort(byPrice);
    return rows;
  }

  _navUrl(s, app) {
    const lat = num(s.lat); const lng = num(s.lng);
    if (lat === null || lng === null) return s.maps || '';
    if (app === 'mapy') return `https://mapy.com/fnc/v1/route?mapset=traffic&end=${lng},${lat}&routeType=car_fast`;
    if (app === 'waze') return `https://waze.com/ul?ll=${lat},${lng}&navigate=yes`;
    return `https://www.google.com/maps/dir/?api=1&destination=${lat},${lng}`;
  }

  // ---------------------------------------------------------------- rendering
  _renderTexts() {
    const hass = this._hass;
    const top = hass.states[this._ids.top5];
    const root = this.shadowRoot;
    const slot = (p, html) => { const el = root.getElementById(p); if (el) el.innerHTML = html; };
    if (!top || top.state === 'unavailable') {
      const msg = `<div class="card" style="color:var(--cp-sub);font-size:14px">Ceny paliv (${esc(this._config.fuel)}): sensor not found or unavailable — is the fuel set up in the integration?</div>`;
      const first = this._show.find((p) => COL_A.includes(p)) || this._show[0];
      this._show.forEach((p) => slot(p, p === first ? msg : ''));
      return;
    }
    this._rows = [];
    this._switchHtml();
    slot('home', this._show.includes('home') ? (this._big ? this._bigHtml() : this._homeHtml()) : '');
    slot('road', this._show.includes('road') ? this._roadHtml() : '');
    slot('list', this._show.includes('list') && !this._big ? this._listHtml() : '');
    slot('tank', this._show.includes('tank') ? this._tankHtml() : '');
    slot('places', this._show.includes('places') ? this._placesHtml() : '');
    slot('prices', this._show.includes('prices') ? this._pricesHtml() : '');
    slot('regions', this._show.includes('regions') ? this._regionsHtml() : '');
    slot('graph', this._show.includes('graph') ? this._graphHtml() : '');
    this._sheetHtml();
    this._buildExtra();
    if (this._show.includes('graph')) this._loadStats();
    if (this._show.includes('regions') || this._show.includes('prices')) this._ensureRegions();
  }

  _switchHtml() {
    const el = this.shadowRoot.getElementById('switch');
    if (!el) return;
    if (!this._config.fuel_switch || !this._pf) { el.innerHTML = ''; return; }
    const fuels = Object.keys(this._pf).sort((a, b) => FUEL_ORDER.indexOf(a) - FUEL_ORDER.indexOf(b));
    if (fuels.length < 2) { el.innerHTML = ''; return; }
    el.innerHTML = `<div class="chips">${fuels.map((f) => {
      const st = this._hass.states[this._pf[f].top5];
      const label = (st && st.attributes && st.attributes.fuel_label) || f;
      return `<span class="chip${f === this._fuel ? ' on' : ''}" data-act="fuel" data-v="${esc(f)}">${esc(label)}</span>`;
    }).join('')}</div>`;
  }

  _bigHtml() {
    const e = this._hass.states[this._ids.home];
    const at = this._attrs();
    const a = e ? e.attributes : null;
    const cheapest = (at.stations || [])[0];
    const price = e && !['unavailable', 'unknown'].includes(e.state) ? e.state : (cheapest ? cheapest.price : null);
    const name = e ? (a.station || '') : (cheapest ? cheapest.name : '');
    const tr = e ? (a.trends || {}) : (cheapest ? cheapest.trends || {} : {});
    const trend = [1, 7, 30].map((n) => { const r = this._arrow(tr[String(n)]); return `<span style="color:var(--cp-sub)">${n} d <b style="color:${r.color}">${esc(r.txt)}</b></span>`; }).join(' · ');
    const unit = at.unit_of_measurement || at.unit || 'Kč/l';
    return `<div class="card" style="text-align:center;display:flex;flex-direction:column;align-items:center;gap:10px;padding:28px 16px" data-more-info="${esc(this._ids.home || this._ids.top5)}">
      <span class="sub" style="font-size:16px;letter-spacing:.09em;text-transform:uppercase;font-weight:700">${esc(at.fuel_label || this._fuel)} · ${esc(at.city_name || '')}</span>
      <span class="price">${price == null ? '—' : fp(price)}</span>
      <span class="sub" style="font-size:18px;font-weight:700">${esc(unit)}</span>
      <span class="title" style="font-size:22px">${esc(name)}</span>
      <span style="font-size:16px;font-weight:600">${trend}</span></div>`;
  }

  _homeHtml() {
    const e = this._hass.states[this._ids.home];
    if (!e) return '';
    const T = (k, v) => this._T(k, v);
    const LOC = this._labels().locale || 'en-GB';
    const a = e.attributes;
    const stationName = a.station || T('my_station');
    const ok = !['unavailable', 'unknown'].includes(e.state);
    const price = ok ? Number(e.state).toFixed(2) : '—';
    const stale = a.age_days == null || Number(a.age_days) > 1;
    const updTxt = a.age_days == 0 ? T('updated_today') : (a.age_days == 1 ? T('updated_yesterday') : T('price_from', { d: a.updated || '—' }));
    const tr = a.trends || {};
    const today = new Date(); today.setHours(0, 0, 0, 0);
    let partial = null;
    const chip = (n) => {
      const t = tr[String(n)]; const r = this._arrow(t);
      let covered = true;
      if (t) {
        const target = new Date(today); target.setDate(target.getDate() - n);
        covered = new Date(t.ref_date + 'T00:00:00') <= target; if (!covered) partial = t.ref_date;
      }
      return `<div style="display:flex;flex-direction:column;align-items:center;gap:2px;background:var(--cp-chip);border-radius:12px;padding:8px 2px;min-width:0">
        <span style="font-size:11px;font-weight:700;color:var(--cp-sub)">${n} d${t && !covered ? '*' : ''}</span>
        <ha-icon icon="${r.icon}" style="--mdc-icon-size:18px;color:${r.color}"></ha-icon>
        <span style="font-size:13px;font-weight:800;color:${r.color};white-space:nowrap">${r.txt}</span></div>`;
    };
    const chips = [1, 2, 7, 14, 30].map(chip).join('');
    const anyTrend = Object.values(tr).some(Boolean);
    const note = !anyTrend ? T('trends_start')
      : (partial ? T('since_partial', { d: new Date(partial + 'T00:00:00').toLocaleDateString(LOC, { day: 'numeric', month: 'short' }) }) : '');
    let pos;
    if (a.rank == null) pos = `<span style="color:var(--cp-warn)">${esc(T('not_ranked'))}</span>`;
    else if (Number(a.vs_cheapest) <= 0) pos = `<span style="color:var(--cp-good)">${esc(T('cheapest_town', { rank: a.rank, n: a.fresh_count }))}</span>`;
    else pos = `<span style="color:var(--cp-warn)">${esc(T('vs_cheapest', { d: Number(a.vs_cheapest).toFixed(2), name: a.cheapest_name, rank: a.rank, n: a.fresh_count }))}</span>`;
    const topHome = this._attrs().home || { name: stationName };
    const hasLogo = !!this._logoUrl(topHome);
    const size = this._compact ? 36 : 44;
    const iconBox = `<div style="position:absolute;left:0;top:0;width:${size}px;height:${size}px;border-radius:14px;display:flex;align-items:center;justify-content:center;background:color-mix(in srgb, var(--cp-accent) 16%, transparent)"><ha-icon icon="mdi:gas-station-in-use" style="--mdc-icon-size:22px;color:var(--cp-accent)"></ha-icon></div>`;
    const logo = `<div style="position:relative;width:${size}px;height:${size}px;flex-shrink:0">${hasLogo ? this._disc(topHome, size) : iconBox}</div>`;
    const cp = this._compact;
    const mini = [1, 7, 30].map((n) => { const r = this._arrow(tr[String(n)]); return `<span style="color:var(--cp-sub)">${n} d <span style="color:${r.color};font-weight:800">${esc(r.txt)}</span></span>`; }).join(' · ');
    return `<div class="card home${cp ? ' compact' : ''}" data-more-info="${esc(this._ids.home)}">
      <div style="display:flex;flex-direction:column;gap:${cp ? 8 : 12}px;width:100%;text-align:left">
        <div style="display:flex;align-items:center;gap:12px">${logo}
          <div style="flex:1 1 auto;display:flex;flex-direction:column;gap:2px;min-width:0">
            <span style="font-size:12px;letter-spacing:.09em;text-transform:uppercase;font-weight:700;color:var(--cp-sub)">${esc(T('my_station'))}</span>
            <span class="title">${esc(stationName)}</span>
            <span style="font-size:12px;color:${stale ? 'var(--cp-warn)' : 'var(--cp-sub)'}">${esc(updTxt)}</span></div>
          <div style="display:flex;flex-direction:column;align-items:flex-end;flex-shrink:0">
            <span style="font-size:${cp ? 30 : 40}px;font-weight:800;letter-spacing:-0.03em;line-height:1;color:${stale ? 'var(--cp-sub)' : 'var(--cp-text)'}">${price}</span>
            <span style="font-size:11px;color:var(--cp-sub);font-weight:600">${esc(a.unit_of_measurement || 'Kč/l')}</span></div>
        </div>
        ${cp ? `<div style="display:flex;flex-wrap:wrap;gap:4px 8px;font-size:12px;font-weight:600">${mini}</div>`
    : `<div style="display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:6px">${chips}</div>
        ${note ? `<span style="font-size:11px;color:var(--cp-dim);margin-top:-4px">${esc(note)}</span>` : ''}`}
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;font-size:12px;font-weight:600">${pos}
          ${cp ? '' : `<span style="color:var(--cp-dim);font-weight:500;white-space:nowrap">${esc(T('tap_history'))}</span>`}</div>
      </div></div>`;
  }

  // One row of a list: a station, tap = details.
  _rowHtml(s, i, min, mode, today) {
    const T = (k, v) => this._T(k, v);
    const cp = this._compact;
    const best = Number(s.price) === min;
    const diff = Number(s.price) - min;
    const name = s.name || '—';
    const a0 = s.address || '';
    const addr = a0.startsWith(name) ? a0.slice(name.length).trim() : a0;
    const tr = this._arrow((s.trends || {})['1']);
    const age = this._age(s, today);
    const when = age <= 0 ? T('today') : `<span style="color:var(--cp-warn)">${esc(age === 1 ? T('yesterday') : (s.updated || '—'))}</span>`;
    const d = s._w ? s._w.d : null;
    const dist = d != null ? ` · ${d.toFixed(1)} km` : '';
    const home = s.home ? `<ha-icon icon="mdi:home" title="${esc(T('my_station'))}" style="--mdc-icon-size:14px;color:var(--cp-accent);margin-left:6px"></ha-icon>` : '';
    const idx = this._rows.push(s) - 1;
    return `<div class="row" data-i="${idx}">
      ${this._avatar(s, i + 1, best)}
      <div style="flex:1 1 auto;display:flex;flex-direction:column;gap:2px;text-align:left;min-width:0">
        <span class="title" style="${cp ? 'white-space:nowrap;overflow:hidden;text-overflow:ellipsis' : ''}">${esc(name)}${cp ? ` <span style="font-size:11px;font-weight:500;color:var(--cp-sub)">${esc(addr)}${dist}</span>` : ''}${home}</span>
        ${cp ? '' : `<span class="sub" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(addr)}${dist} · ${when}</span>`}</div>
      <div style="display:flex;flex-direction:column;align-items:center;flex-shrink:0;width:40px" title="${esc(T('vs_yesterday'))}">
        <ha-icon icon="${tr.icon}" style="--mdc-icon-size:18px;color:${tr.color}"></ha-icon>
        <span style="font-size:10px;font-weight:700;color:${tr.color}">${tr.txt}</span></div>
      <div style="display:flex;flex-direction:column;align-items:flex-end;flex-shrink:0;gap:1px">
        <span style="font-size:18px;font-weight:800;color:${best ? 'var(--cp-good)' : 'var(--cp-text)'}">${fp(s.price)}</span>
        <span style="font-size:11px;font-weight:600;color:${best ? 'var(--cp-good)' : 'var(--cp-sub)'}">${esc(best ? T('cheapest_badge') : '+' + fp(diff))}</span></div>
      <ha-icon icon="mdi:chevron-right" style="--mdc-icon-size:18px;color:var(--cp-dim);flex-shrink:0"></ha-icon></div>`;
  }

  _listHtml() {
    const at = this._attrs();
    const T = (k, v) => this._T(k, v);
    const LOC = this._labels().locale || 'en-GB';
    const mode = this._sort;
    const pool = this._pool();
    const all = Array.isArray(at.stations) ? at.stations : [];
    const maxAge = at.max_age_days != null ? Number(at.max_age_days) : 1;
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const fresh = pool.filter((s) => this._age(s, today) <= maxAge);
    const sorted = this._sorted(fresh, mode);
    const list = sorted.slice(0, this._n);
    const cp = this._compact;
    const allPrices = fresh.map((s) => Number(s.price)).filter((p) => !isNaN(p));
    const min = allPrices.length ? Math.min(...allPrices) : null;
    const unit = at.unit_of_measurement || 'Kč/l';
    const n = min === null ? 0 : fresh.filter((s) => Number(s.price) === min).length;
    const sub = min === null ? T('no_recent') : T('cheapest_price', { p: fp(min), unit }) + (n > 1 ? ' · ' + T('stations_same', { n }) : '');
    const head = `<div style="display:flex;align-items:center;gap:12px;width:100%;padding-bottom:${cp ? 6 : 12}px">
      <div style="width:${cp ? 36 : 44}px;height:${cp ? 36 : 44}px;border-radius:14px;display:flex;align-items:center;justify-content:center;background:color-mix(in srgb, var(--cp-amber) 16%, transparent);flex-shrink:0">
        <ha-icon icon="mdi:gas-station" style="--mdc-icon-size:22px;color:var(--cp-amber)"></ha-icon></div>
      <div style="flex:1 1 auto;display:flex;flex-direction:column;gap:2px;text-align:left;min-width:0">
        <span class="title">${esc(at.fuel_label || this._fuel)} · ${esc(at.city_name || '')}</span>
        <span style="font-size:13px;color:var(--cp-sub)">${esc(sub)}</span></div>
      <div style="display:flex;flex-direction:column;align-items:flex-end;flex-shrink:0">
        <span style="font-size:${cp ? 22 : 28}px;font-weight:800;letter-spacing:-0.02em;line-height:1;color:${min === null ? 'var(--cp-dim)' : 'var(--cp-good)'}">${min === null ? '—' : fp(min)}</span>
        <span style="font-size:11px;color:var(--cp-sub);font-weight:600">${esc(unit)}</span></div></div>`;
    const sorts = cp ? '' : `<div class="chips">${['price', 'distance'].map((m) => `<span class="chip${m === mode ? ' on' : ''}" data-act="sort" data-v="${m}">${esc(this._X('sort_' + m))}</span>`).join('')}</div>`;
    const rows = list.map((s, i) => this._rowHtml(s, i, min, mode, today)).join('');
    // footer
    const now = new Date();
    const hm = (d) => d.toLocaleTimeString(LOC, { hour: '2-digit', minute: '2-digit' });
    const when = (d) => (d.toDateString() === now.toDateString() ? hm(d) : d.toLocaleString(LOC, { weekday: 'short', hour: '2-digit', minute: '2-digit' }));
    const fa = at.fetched_at ? new Date(at.fetched_at) : null;
    const la = at.last_attempt ? new Date(at.last_attempt) : null;
    const nu = at.next_update ? new Date(at.next_update) : null;
    const hidden = (at.excluded || 0) + Math.max(0, all.length - fresh.length);
    const lines = [`<span style="font-size:13px;color:var(--cp-text2);font-weight:600">${esc(T('table_updated', { t: fa ? when(fa) : '—', n: nu ? when(nu) : '—' }))}</span>`];
    if (at.fetch_error) lines.push(`<span style="font-size:12px;color:var(--cp-warn)">${esc(T('refresh_failed', { at: la ? T('at') + when(la) : '', err: at.fetch_error }))}</span>`);
    if (at.city_total) lines.push(`<span style="font-size:12px;color:var(--cp-sub)">${esc(T('hidden', { h: hidden, t: at.city_total, age: maxAge >= 1 ? T('yesterday_l') : T('today_l') }))}</span>`);
    lines.push(`<span style="font-size:11px;color:var(--cp-sub)">${esc(T('arrows'))} · <span style="color:var(--cp-good)">▼ ${esc(T('down'))}</span> · <span style="color:var(--cp-warn)">— ${esc(T('stable'))}</span> · <span style="color:var(--cp-bad)">▲ ${esc(T('up'))}</span> · ${esc(T('longpress'))}</span>`);
    lines.push(`<span style="font-size:11px;color:var(--cp-dim)">${SOURCE} · ${esc(at.fuel_label || '')}${at.fuel === 'n95' ? ' ' + esc(T('e10_note')) : ''} · ${esc(T('tap_station'))}</span>`);
    const foot = !this._footer ? `<div style="padding-top:6px;font-size:11px;color:var(--cp-dim);text-align:left">${SOURCE}${at.fetch_error ? ' · ' + esc(T('refresh_failed', { at: '', err: at.fetch_error })) : ''}</div>` : `<div style="display:flex;flex-direction:column;gap:3px;text-align:left;border-top:1px solid var(--cp-line);padding-top:12px">${lines.join('')}</div>`;
    return `<div class="card${cp ? ' compact' : ''}">${head}${sorts}${rows}${foot}</div>`;
  }

  // On the road: the nearest stations, one tap to navigate.
  _roadHtml() {
    const at = this._attrs();
    const pool = this._pool();
    const centre = this._centre(pool);
    const head = `<div class="title" style="display:flex;align-items:center;gap:8px;margin-bottom:10px"><ha-icon icon="mdi:road-variant" style="--mdc-icon-size:22px;color:var(--cp-accent)"></ha-icon>${esc(this._X('road_title'))} · ${esc(at.fuel_label || this._fuel)}</div>`;
    if (!centre || !centre.real) return `<div class="card">${head}<span class="sub">${esc(this._X('road_need'))}</span></div>`;
    const rows = this._sorted(pool, 'distance').slice(0, Math.min(this._n, 3));
    const unit = at.unit_of_measurement || 'Kč/l';
    const body = rows.map((s) => {
      const idx = this._rows.push(s) - 1;
      const w = s._w;
      return `<div style="display:flex;align-items:center;gap:12px;padding:10px 0;border-top:1px solid var(--cp-line)">
        <div style="flex:1;min-width:0;display:flex;flex-direction:column;gap:2px;cursor:pointer" data-i="${idx}">
          <span class="title" style="font-size:17px">${esc(s.name)}</span>
          <span class="sub">${w.d != null ? w.d.toFixed(1) + ' km' : ''}</span></div>
        <div style="text-align:right"><div style="font-size:26px;font-weight:800;letter-spacing:-0.02em">${fp(s.price)}</div><div class="sub">${esc(unit)}</div></div>
        <a class="btn main" style="padding:12px 14px" href="${esc(this._navUrl(s, this._nav))}" target="_blank" rel="noopener noreferrer" title="${esc(this._X('navigate'))}"><ha-icon icon="mdi:navigation-variant" style="--mdc-icon-size:22px"></ha-icon></a></div>`;
    }).join('');
    return `<div class="card">${head}${body}</div>`;
  }

  // Every fuel of the place, what a full tank costs, and the favourite against the cheapest and the average.
  _tankHtml() {
    const hass = this._hass;
    const fuels = Object.keys(this._pf || {}).sort((a, b) => FUEL_ORDER.indexOf(a) - FUEL_ORDER.indexOf(b));
    const price = (id) => { const st = id && hass.states[id]; return st && !['unavailable', 'unknown'].includes(st.state) ? Number(st.state) : null; };
    const rows = fuels.map((f) => {
      const ids = this._pf[f];
      const st = hass.states[ids.top5];
      return {
        fuel: f, label: (st && st.attributes && st.attributes.fuel_label) || f, cheapest: price(ids.top5), mine: price(ids.home), avg: price(ids.avg.area),
      };
    });
    const money = (p) => (p == null ? '—' : `${Math.round(p * this._tank)} Kč`);
    const body = rows.map((r) => {
      const save = r.cheapest != null && r.avg != null ? (r.avg - r.cheapest) * this._tank : null;
      const on = r.fuel === this._fuel;
      return `<tr data-act="fuel" data-v="${esc(r.fuel)}" style="cursor:pointer;${on ? 'background:var(--cp-chip)' : ''}"><td>${esc(r.label)}</td><td>${r.cheapest == null ? '—' : fp(r.cheapest)}</td><td>${r.mine == null ? '—' : fp(r.mine)}</td><td>${r.avg == null ? '—' : fp(r.avg)}</td>
        <td>${money(r.cheapest)}</td><td style="color:${save != null && save > 0 ? 'var(--cp-good)' : 'var(--cp-sub)'}">${save == null ? '—' : (save >= 0 ? '+' : '−') + Math.abs(Math.round(save)) + ' Kč'}</td></tr>`;
    }).join('');
    const cur = rows.find((r) => r.fuel === this._fuel);
    let bars = '';
    if (cur) {
      const items = [[this._X('tank_cheapest'), cur.cheapest, 'var(--cp-good)'], [this._X('tank_mine'), cur.mine, 'var(--cp-accent)'], [this._X('tank_avg'), cur.avg, 'var(--cp-amber)']].filter((x) => x[1] != null);
      const hi = Math.max(...items.map((x) => x[1])); const lo = Math.min(...items.map((x) => x[1]));
      const span = Math.max(hi - lo, 0.5);
      bars = `<div class="title" style="margin:14px 0 8px">${esc(this._X('compare'))} · ${esc(cur.label)}</div>${items.map(([label, v, color]) => {
        const w = 35 + 65 * ((v - lo) / span);
        return `<div style="display:flex;align-items:center;gap:10px;margin:6px 0"><span class="sub" style="width:92px;flex-shrink:0">${esc(label)}</span>
          <div class="bar" style="flex:1"><i style="width:${w.toFixed(0)}%;background:${color}"></i></div>
          <span style="min-width:112px;text-align:right;font-weight:800;font-size:13px;white-space:nowrap">${fp(v)} · ${Math.round(v * this._tank)} Kč</span></div>`;
      }).join('')}`;
    }
    return `<div class="card"><div class="title" style="margin-bottom:8px">${esc(this._X('tank_title', { l: this._tank }))}</div>
      <table class="t"><tr><th>${esc(this._X('tank_fuel'))}</th><th>${esc(this._X('tank_cheapest'))}</th><th>${esc(this._X('tank_mine'))}</th><th>${esc(this._X('tank_avg'))}</th><th>${esc(this._X('tank_cost'))}</th><th>${esc(this._X('tank_save'))}</th></tr>${body}</table>${bars}</div>`;
  }

  // Several places side by side: the cheapest price and the favourite station of each.
  _placesHtml() {
    const hass = this._hass;
    const places = this._places || scan(hass);
    const wanted = Array.isArray(this._config.places) && this._config.places.length ? this._config.places : Object.values(places).map((p) => p.name);
    const cards = wanted.map((w) => {
      const p = Object.values(places).find((x) => norm(x.name) === norm(w) || norm(x.key) === norm(w));
      const f = p && p.fuels[this._fuel];
      if (!f) return `<div class="card" style="flex:1 1 180px"><span class="title">${esc(w)}</span><div class="sub">${esc(this._X('no_place'))}</div></div>`;
      const st = hass.states[f.top5];
      const at = (st && st.attributes) || {};
      const cheapest = (at.stations || [])[0];
      const home = f.home && hass.states[f.home];
      const unit = at.unit_of_measurement || 'Kč/l';
      const avg = f.avg.area && hass.states[f.avg.area];
      return `<div class="card" style="flex:1 1 180px;cursor:pointer" data-more-info="${esc(f.top5)}">
        <div class="sub" style="font-weight:700;letter-spacing:.06em;text-transform:uppercase">${esc(p.name)} · ${esc(at.fuel_label || this._fuel)}</div>
        <div style="font-size:34px;font-weight:800;letter-spacing:-0.03em;line-height:1.1;color:var(--cp-good);margin-top:6px">${cheapest ? fp(cheapest.price) : '—'}<span class="sub" style="font-size:12px;font-weight:600"> ${esc(unit)}</span></div>
        <div class="title" style="margin-top:2px">${esc(cheapest ? cheapest.name : '')}</div>
        ${home && !['unavailable', 'unknown'].includes(home.state) ? `<div class="sub" style="margin-top:8px">${esc(this._T('my_station'))}: <b style="color:var(--cp-text)">${fp(home.state)}</b></div>` : ''}
        ${avg && !['unavailable', 'unknown'].includes(avg.state) ? `<div class="sub">${esc(this._X('tank_avg'))}: <b style="color:var(--cp-text)">${fp(avg.state)}</b></div>` : ''}</div>`;
    }).join('');
    return `<div style="display:flex;flex-wrap:wrap;gap:12px">${cards}</div>`;
  }

  // Region (kraj) map coloured by average price. Needs the outlines (regions.json served by the integration).
  _regionsHtml() {
    const avgs = (((this._attrs().averages || {}).country || {}).regions) || [];
    const own = ((this._attrs().averages || {}).region || {}).code;
    const data = this._regionData;
    const title = `<div class="title" style="margin-bottom:8px">${esc(this._X('regions_title'))} · ${esc(this._attrs().fuel_label || this._fuel)}</div>`;
    if (!data) return `<div class="card">${title}<span class="sub">…</span></div>`;
    if (!avgs.length) return `<div class="card">${title}<span class="sub">—</span></div>`;
    const byCode = {}; avgs.forEach((r) => { byCode[r.code] = r; });
    const vals = avgs.map((r) => r.average).filter((v) => v != null);
    const lo = Math.min(...vals); const hi = Math.max(...vals); const span = Math.max(hi - lo, 0.05);
    const proj = this._projection(data.regions.flatMap((r) => r.polygons.flat(2)));
    const paths = data.regions.map((r) => {
      const d = r.polygons.map((poly) => poly.map((ring) => 'M' + ring.map((p) => proj(p[0], p[1]).join(',')).join('L') + 'Z').join('')).join('');
      const a = byCode[r.code];
      const fill = a && a.average != null ? heat((a.average - lo) / span) : 'var(--cp-chip)';
      const sel = this._regionSel === r.code;
      return `<path d="${d}" fill-rule="evenodd" data-act="region" data-v="${esc(r.code)}" style="fill:${fill};stroke:${sel ? 'var(--cp-text)' : r.code === own ? 'var(--cp-accent)' : 'var(--cp-bg)'};stroke-width:${sel || r.code === own ? 2.2 : 1};cursor:pointer"><title>${esc(r.name)}${a ? ' · ' + fp(a.average) : ''}</title></path>`;
    }).join('');
    const labels = data.regions.map((r) => {
      const a = byCode[r.code]; if (!a || a.average == null) return '';
      const c = this._centroid(r, proj);
      return `<text x="${c[0].toFixed(1)}" y="${c[1].toFixed(1)}" text-anchor="middle" dominant-baseline="middle" style="font-size:11px;font-weight:800;fill:#fff;paint-order:stroke;stroke:rgba(0,0,0,.55);stroke-width:2.5px;pointer-events:none">${a.average.toFixed(1)}</text>`;
    }).join('');
    const sel = this._regionSel && byCode[this._regionSel];
    const national = (((this._attrs().averages || {}).country || {}).average);
    let info = `<span class="sub">${esc(this._X('region_cheapest'))}: <b style="color:var(--cp-good)">${lo.toFixed(2)}</b> · ${esc(this._X('region_dearest'))}: <b style="color:var(--cp-bad)">${hi.toFixed(2)}</b>${national != null ? ` · ČR: <b style="color:var(--cp-text)">${Number(national).toFixed(2)}</b>` : ''}</span>`;
    if (sel) {
      const v = sel.vs_national;
      info = `<span class="title" style="font-size:14px">${esc(sel.name)}: ${fp(sel.average)}</span> <span class="sub">${esc(this._X('region_info', { n: sel.station_count, v: v == null ? '—' : (v >= 0 ? '+' : '−') + Math.abs(v).toFixed(2) }))} · ${esc(this._X('rank_of', { r: sel.rank, t: avgs.length }))}</span>`;
    }
    return `<div class="card">${title}<svg viewBox="0 0 ${proj.w.toFixed(0)} ${proj.h.toFixed(0)}" style="width:100%;height:auto;display:block">${paths}${labels}</svg>
      <div style="height:8px;border-radius:6px;margin:8px 0 6px;background:linear-gradient(90deg,${heat(0)},${heat(0.5)},${heat(1)})"></div>${info}</div>`;
  }

  // equirectangular projection fitted to the points; returns f(lat, lng) -> [x, y] with .w and .h
  _projection(points, width = 600, pad = 10) {
    let a = 90; let b = -90; let c = 180; let d = -180;
    points.forEach((p) => { a = Math.min(a, p[0]); b = Math.max(b, p[0]); c = Math.min(c, p[1]); d = Math.max(d, p[1]); });
    const k = Math.cos(((a + b) / 2) * Math.PI / 180);
    const spanX = Math.max((d - c) * k, 1e-6); const spanY = Math.max(b - a, 1e-6);
    const sc = (width - 2 * pad) / spanX;
    const f = (lat, lng) => [pad + (lng - c) * k * sc, pad + (b - lat) * sc];
    f.w = width; f.h = spanY * sc + 2 * pad;
    return f;
  }

  _centroid(region, proj) {
    let best = null;
    region.polygons.forEach((poly) => { const ring = poly[0]; if (!best || ring.length > best.length) best = ring; });
    let x = 0; let y = 0;
    best.forEach((p) => { const q = proj(p[0], p[1]); x += q[0]; y += q[1]; });
    return [x / best.length, y / best.length];
  }

  _ensureRegions() {
    if (this._regionData || this._regionsAsked) return;
    this._regionsAsked = true;
    loadRegions().then((d) => {
      if (d && Array.isArray(d.regions)) {
        this._regionData = d;
        if (this._ids && this._hass) { this._sig = ''; this._renderTexts(); }
      }
    });
  }

  // Stations on a map: a marker per station, coloured by how cheap it is, with the price on it.
  _pricesHtml() {
    const at = this._attrs();
    const pool = this._pool().filter((s) => num(s.lat) !== null);
    const title = `<div class="title" style="margin-bottom:8px">${esc(this._X('prices_title'))} · ${esc(at.fuel_label || this._fuel)}</div>`;
    if (!pool.length) return `<div class="card">${title}<span class="sub">${esc(this._X('prices_empty'))}</span></div>`;
    const centre = this._centre(pool);
    // fit the map to where most stations are: a few far-away ones would squeeze the rest into a corner
    const q = (arr, f) => { const a = [...arr].sort((x, y) => x - y); return a[Math.min(a.length - 1, Math.max(0, Math.round((a.length - 1) * f)))]; };
    const lats = pool.map((s) => Number(s.lat)); const lngs = pool.map((s) => Number(s.lng));
    const padLat = (q(lats, 0.95) - q(lats, 0.05)) * 0.15 + 0.004; const padLng = (q(lngs, 0.95) - q(lngs, 0.05)) * 0.15 + 0.006;
    const box = { a: q(lats, 0.05) - padLat, b: q(lats, 0.95) + padLat, c: q(lngs, 0.05) - padLng, d: q(lngs, 0.95) + padLng };
    if (centre && centre.real) { box.a = Math.min(box.a, centre.lat); box.b = Math.max(box.b, centre.lat); box.c = Math.min(box.c, centre.lng); box.d = Math.max(box.d, centre.lng); }
    const inside = (s) => Number(s.lat) >= box.a && Number(s.lat) <= box.b && Number(s.lng) >= box.c && Number(s.lng) <= box.d;
    const shown = pool.filter(inside);
    const proj = this._projection([[box.a, box.c], [box.b, box.d]], 600, 30);
    const prices = pool.map((s) => Number(s.price)); const lo = Math.min(...prices); const hi = Math.max(...prices); const span = Math.max(hi - lo, 0.05);
    let bg = '';
    if (this._regionData) {
      bg = this._regionData.regions.map((r) => `<path d="${r.polygons.map((poly) => poly.map((ring) => 'M' + ring.map((p) => proj(p[0], p[1]).join(',')).join('L') + 'Z').join('')).join('')}" fill-rule="evenodd" style="fill:var(--cp-chip);stroke:var(--cp-line);stroke-width:1"/>`).join('');
    }
    const order = shown.map((s, i) => ({ s, i })).sort((a, b) => Number(b.s.price) - Number(a.s.price));
    const markers = order.map(({ s }) => {
      const [x, y] = proj(Number(s.lat), Number(s.lng));
      const idx = this._rows.push(s) - 1;
      const t = (Number(s.price) - lo) / span;
      const w = 36; const h = 17;
      return `<g data-i="${idx}" style="cursor:pointer"><rect x="${(x - w / 2).toFixed(1)}" y="${(y - h / 2).toFixed(1)}" width="${w}" height="${h}" rx="8" style="fill:${heat(t)};stroke:${s.home ? '#fff' : 'rgba(0,0,0,.35)'};stroke-width:${s.home ? 2.5 : 1}"/>
        <text x="${x.toFixed(1)}" y="${(y + 0.5).toFixed(1)}" text-anchor="middle" dominant-baseline="middle" style="font-size:10px;font-weight:800;fill:#fff;pointer-events:none">${Number(s.price).toFixed(1)}</text></g>`;
    }).join('');
    const me = centre && centre.real ? (() => { const [x, y] = proj(centre.lat, centre.lng); return `<g style="pointer-events:none"><circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="7" style="fill:var(--cp-accent);stroke:#fff;stroke-width:2.5"/></g>`; })() : '';
    return `<div class="card">${title}<svg viewBox="0 0 ${proj.w.toFixed(0)} ${proj.h.toFixed(0)}" style="width:100%;height:auto;display:block;border-radius:12px;background:var(--cp-bg2)${this._mapHeight ? `;max-height:${this._mapHeight}px` : ''}">${bg}${me}${markers}</svg>
      <div style="height:8px;border-radius:6px;margin:8px 0 4px;background:linear-gradient(90deg,${heat(0)},${heat(0.5)},${heat(1)})"></div>
      <div class="sub" style="display:flex;justify-content:space-between"><span>${lo.toFixed(2)}</span>${pool.length > shown.length ? `<span>+${pool.length - shown.length} ${esc(this._X('prices_outside'))}</span>` : ''}<span>${hi.toFixed(2)}</span></div></div>`;
  }

  // ---------------------------------------------------------------- 30-day graph (long-term statistics)
  async _loadStats() {
    const ids = [this._ids.home, this._ids.top5, this._ids.avg && this._ids.avg.area].filter(Boolean);
    if (!ids.length || !this._hass) return;
    const key = ids.join(',');
    if (this._stats && this._stats.key === key && Date.now() - this._stats.at < 1800000) return;
    this._stats = { key, at: Date.now(), data: null };
    try {
      const r = await this._hass.callWS({
        type: 'recorder/statistics_during_period', start_time: new Date(Date.now() - 31 * 86400000).toISOString(),
        statistic_ids: ids, period: 'day', types: ['mean'],
      });
      this._stats.data = r || {};
    } catch (err) {
      this._stats.data = {};
    }
    const slot = this.shadowRoot.getElementById('graph');
    if (slot && this._ids) slot.innerHTML = this._graphHtml();
  }

  _graphHtml() {
    const title = `<div class="title" style="margin-bottom:8px">${esc(this._X('graph_title'))} · ${esc(this._attrs().fuel_label || this._fuel)}</div>`;
    const st = this._stats;
    if (!st || !st.data) return `<div class="card">${title}<span class="sub">${esc(this._X('g_loading'))}</span></div>`;
    const series = [
      { id: this._ids.home, label: this._X('g_home'), color: 'var(--cp-accent)', w: 2.6 },
      { id: this._ids.top5, label: this._X('g_cheapest'), color: 'var(--cp-good)', w: 2.2 },
      { id: this._ids.avg && this._ids.avg.area, label: this._X('g_area'), color: 'var(--cp-amber)', w: 2, dash: '5 4' },
    ].map((s) => {
      const rows = (st.data[s.id] || []).map((p) => {
        const t = typeof p.start === 'number' ? p.start : Date.parse(p.start);
        return [t, p.mean];
      }).filter((p) => p[1] != null && !isNaN(p[0]));
      return Object.assign({}, s, { rows });
    }).filter((s) => s.id && s.rows.length);
    if (!series.length || series.every((s) => s.rows.length < 2)) return `<div class="card">${title}<span class="sub">${esc(this._X('g_none'))}</span></div>`;
    const all = series.flatMap((s) => s.rows);
    const t0 = Math.min(...all.map((p) => p[0])); const t1 = Math.max(...all.map((p) => p[0]));
    const vmin = Math.min(...all.map((p) => p[1])); const vmax = Math.max(...all.map((p) => p[1]));
    const pad = Math.max((vmax - vmin) * 0.15, 0.1);
    const lo = vmin - pad; const hi = vmax + pad;
    const W = 600; const H = 220; const L = 44; const R = 10; const Tp = 10; const B = 26;
    const x = (t) => L + (t1 === t0 ? 0 : (t - t0) / (t1 - t0)) * (W - L - R);
    const y = (v) => Tp + (1 - (v - lo) / (hi - lo)) * (H - Tp - B);
    const grid = [0, 0.5, 1].map((f) => { const v = lo + (hi - lo) * f; return `<line x1="${L}" x2="${W - R}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}" style="stroke:var(--cp-line);stroke-width:1"/><text x="${L - 6}" y="${y(v).toFixed(1)}" text-anchor="end" dominant-baseline="middle" style="font-size:11px;fill:var(--cp-sub)">${v.toFixed(1)}</text>`; }).join('');
    const LOC = this._labels().locale || 'en-GB';
    const ticks = [0, 0.5, 1].map((f) => { const t = t0 + (t1 - t0) * f; return `<text x="${x(t).toFixed(1)}" y="${H - 6}" text-anchor="${f === 0 ? 'start' : f === 1 ? 'end' : 'middle'}" style="font-size:11px;fill:var(--cp-sub)">${esc(new Date(t).toLocaleDateString(LOC, { day: 'numeric', month: 'short' }))}</text>`; }).join('');
    const lines = series.map((s) => `<polyline fill="none" points="${s.rows.map((p) => x(p[0]).toFixed(1) + ',' + y(p[1]).toFixed(1)).join(' ')}" style="stroke:${s.color};stroke-width:${s.w};stroke-linejoin:round;stroke-linecap:round${s.dash ? `;stroke-dasharray:${s.dash}` : ''}"/>`).join('');
    const legend = series.map((s) => { const last = s.rows[s.rows.length - 1][1]; return `<span style="display:inline-flex;align-items:center;gap:6px;font-size:12px;color:var(--cp-text2);font-weight:600"><i style="display:inline-block;width:14px;height:3px;border-radius:2px;background:${s.color}"></i>${esc(s.label)} <b>${Number(last).toFixed(2)}</b></span>`; }).join('');
    // The average of the town over the period, from the long-term statistics of the area-average sensor.
    const area = series.find((s) => this._ids.avg && s.id === this._ids.avg.area);
    let summary = '';
    if (area && area.rows.length >= 3) {
      const v = area.rows.map((p) => p[1]);
      const days = Math.round((area.rows[area.rows.length - 1][0] - area.rows[0][0]) / 86400000) + 1;
      const avg = v.reduce((a, b) => a + b, 0) / v.length;
      summary = `<div class="muted" style="margin-top:6px">${esc(this._X('g_sum', { n: days, a: avg.toFixed(2), lo: Math.min(...v).toFixed(2), hi: Math.max(...v).toFixed(2) }))}</div>`;
    }
    return `<div class="card">${title}<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:auto;display:block">${grid}${ticks}${lines}</svg><div style="display:flex;flex-wrap:wrap;gap:6px 16px;margin-top:6px">${legend}</div>${summary}</div>`;
  }

  // ---------------------------------------------------------------- station details
  _sheetHtml() {
    const el = this.shadowRoot.getElementById('sheet');
    if (!el) return;
    const s = this._detail;
    if (!s) { el.innerHTML = ''; return; }
    const at = this._attrs();
    const pool = this._pool();
    const w = s._w || { d: this._distance(s, this._centre(pool)) };
    const unit = at.unit_of_measurement || 'Kč/l';
    const apps = [['mapy', 'Mapy.com', 'mdi:map-marker-radius'], ['google', 'Google Maps', 'mdi:google-maps'], ['waze', 'Waze', 'mdi:waze']];
    const main = this._nav;
    const buttons = apps.sort((a, b) => (b[0] === main) - (a[0] === main)).map(([k, label, icon]) => `<a class="btn${k === main ? ' main' : ''}" href="${esc(this._navUrl(s, k))}" target="_blank" rel="noopener noreferrer"><ha-icon icon="${icon}" style="--mdc-icon-size:20px"></ha-icon>${esc(this._X('navigate'))}: ${esc(label)}</a>`).join('');
    const lines = [];
    if (s.address) lines.push(`<span class="sub">${esc(s.address)}</span>`);
    {
      const today = new Date(); today.setHours(0, 0, 0, 0);
      const age = this._age(s, today);
      const when = age <= 0 ? this._T('updated_today') : (age === 1 ? this._T('updated_yesterday') : this._T('price_from', { d: s.updated || '—' }));
      lines.push(`<span class="sub">${esc(when)}</span>`);
    }
    if (w.d != null) lines.push(`<span class="sub">${esc(this._X('away', { d: w.d.toFixed(1) }))}</span>`);
    el.innerHTML = `<div class="sheet" data-act="close"><div class="card" data-act="keep">
      <div style="display:flex;align-items:center;gap:12px"><span style="position:relative;width:44px;height:44px;flex-shrink:0;display:block">${this._disc(s, 44)}</span>
        <div style="flex:1;min-width:0"><div class="title" style="font-size:17px">${esc(s.name || '')}</div></div>
        <div style="text-align:right"><div style="font-size:32px;font-weight:800;letter-spacing:-0.03em;line-height:1">${fp(s.price)}</div><div class="sub">${esc(unit)}</div></div></div>
      ${lines.join('')}
      <div style="display:flex;flex-direction:column;gap:8px">${buttons}
        ${s.url ? `<a class="btn" href="${esc(/^\//.test(s.url) ? 'https://www.mbenzin.cz' + s.url : s.url)}" target="_blank" rel="noopener noreferrer"><ha-icon icon="mdi:open-in-new" style="--mdc-icon-size:20px"></ha-icon>${esc(this._X('mbenzin'))}</a>` : ''}
        <span class="btn" data-act="close">${esc(this._X('close'))}</span></div></div></div>`;
  }

  // ---------------------------------------------------------------- interaction
  _target(e) {
    const path = e.composedPath ? e.composedPath() : [];
    return {
      path,
      anchor: path.find((n) => n.tagName === 'A' && n.getAttribute && n.getAttribute('href')),
      act: path.find((n) => n.dataset && n.dataset.act),
      row: path.find((n) => n.dataset && n.dataset.i !== undefined),
      more: path.find((n) => n.dataset && n.dataset.moreInfo),
    };
  }

  _down(e) {
    const t = this._target(e);
    this._long = false;
    clearTimeout(this._timer);
    if (t.row) {
      this._timer = setTimeout(() => {
        this._long = true;
        this._moreInfo(this._ids.home || this._ids.top5);
      }, 550);
    }
  }

  _click(e) {
    const t = this._target(e);
    if (this._long) { this._long = false; return; }
    if (t.anchor) return;
    if (t.act) {
      const a = t.act.dataset.act; const v = t.act.dataset.v;
      if (a === 'keep') return;
      if (a === 'close') { this._detail = null; this._sheetHtml(); return; }
      if (a === 'sort') { this._sort = v; this._sig = ''; this._renderTexts(); return; }
      if (a === 'fuel') { this._switchFuel(v); return; }
      if (a === 'region') { this._regionSel = this._regionSel === v ? null : v; const slot = this.shadowRoot.getElementById('regions'); if (slot) slot.innerHTML = this._regionsHtml(); return; }
    }
    if (t.row) {
      const s = (this._rows || [])[Number(t.row.dataset.i)];
      if (s) { this._detail = s; this._sheetHtml(); }
      return;
    }
    if (t.more) this._moreInfo(t.more.dataset.moreInfo);
  }

  _switchFuel(fuel) {
    if (!fuel || fuel === this._fuel) return;
    this._fuel = fuel;
    this._ids = null;
    this._sig = '';
    this._stats = null;
    this._detail = null;
    this._children = null;
    this._build();
    this.hass = this._hass;
  }

  _moreInfo(entityId) {
    this.dispatchEvent(new CustomEvent('hass-more-info', { bubbles: true, composed: true, detail: { entityId } }));
  }
}


// ------------------------------------------------------------------ badge
class CenyPalivBadge extends HTMLElement {
  setConfig(config) {
    this._config = config || {};
    if (!this._config.fuel && !this._config.entity) throw new Error('ceny-paliv-badge: set "fuel" (for example "n95") or "entity"');
    if (!this.shadowRoot) this.attachShadow({ mode: 'open' });
    this._sig = '';
  }
  set hass(hass) {
    this._hass = hass;
    if (!this._config) return;
    let id = this._config.entity;
    let st; let label = '';
    if (!id) {
      const p = pickPlace(scan(hass), this._config.place);
      const f = p && p.fuels[this._config.fuel];
      id = f && (this._config.show === 'home' && f.home ? f.home : f.top5);
    }
    st = id && hass.states[id];
    const at = (st && st.attributes) || {};
    const home = this._config.show === 'home' || (st && at.cp_role === 'home');
    label = this._config.name || (at.fuel_label ? `${at.fuel_label}` : (st && at.friendly_name) || '');
    const value = st && !['unavailable', 'unknown'].includes(st.state) ? Number(st.state).toFixed(2) : '—';
    const unit = at.unit_of_measurement || 'Kč/l';
    const lang = ((hass.language || 'en').split('-')[0]);
    const tag = (TXT[lang] || TXT.en)[home ? 'badge_home' : 'badge_cheapest'];
    const sig = [id, value, label].join('|');
    if (sig === this._sig) return;
    this._sig = sig;
    this._id = id;
    this.shadowRoot.innerHTML = `<style>
      :host { display: inline-block; }
      .b { display: inline-flex; align-items: center; gap: 8px; height: var(--ha-badge-size, 36px); padding: 0 14px 0 10px; box-sizing: border-box; border-radius: var(--ha-badge-border-radius, calc(var(--ha-badge-size, 36px) / 2));
           background: var(--ha-card-background, var(--card-background-color, #fff)); border: 1px solid var(--divider-color, #e0e0e0); color: var(--primary-text-color); cursor: pointer;
           font-family: var(--ha-font-family-body, system-ui, sans-serif); }
      .v { font-weight: 800; font-size: 14px; } .u { font-size: 11px; color: var(--secondary-text-color); } .l { font-size: 11px; color: var(--secondary-text-color); line-height: 1.1; }
      .c { display: flex; flex-direction: column; } ha-icon { --mdc-icon-size: 18px; color: var(--primary-color); }
    </style><div class="b"><ha-icon icon="${home ? 'mdi:gas-station-in-use' : 'mdi:gas-station'}"></ha-icon><div class="c"><span class="l">${esc(label)}${label ? ' · ' : ''}${esc(tag)}</span><span><span class="v">${value}</span> <span class="u">${esc(unit)}</span></span></div></div>`;
    const b = this.shadowRoot.querySelector('.b');
    b.onclick = () => this.dispatchEvent(new CustomEvent('hass-more-info', { bubbles: true, composed: true, detail: { entityId: this._id } }));
  }
  static getStubConfig(hass) { const f = CenyPalivCard.fuels(hass)[0]; return { type: 'custom:ceny-paliv-badge', fuel: f ? f.value : 'n95' }; }
}

// ------------------------------------------------------------------ tile card feature
class CenyPalivTileFeature extends HTMLElement {
  setConfig(config) { this._config = config || {}; if (!this.shadowRoot) this.attachShadow({ mode: 'open' }); }
  // recent Home Assistant sets `context` ({ entity_id }), older versions `stateObj`
  set context(c) { this._context = c; this._draw(); }
  set stateObj(o) { this._stateObj = o; this._draw(); }
  set hass(h) { this._hass = h; this._draw(); }
  _draw() {
    const entityId = (this._context && this._context.entity_id) || (this._stateObj && this._stateObj.entity_id);
    if (!this._hass || !entityId) return;
    const hass = this._hass;
    const st = hass.states[entityId];
    if (!st) return;
    const at = st.attributes || {};
    const lang = ((hass.language || 'en').split('-')[0]);
    const X = (k) => (TXT[lang] || TXT.en)[k] || TXT.en[k];
    const places = scan(hass);
    const p = pickPlace(places, at.cp_place_name);
    const f = p && p.fuels[at.cp_fuel];
    const val = (id) => { const s = id && hass.states[id]; return s && !['unavailable', 'unknown'].includes(s.state) ? Number(s.state) : null; };
    const cheapest = f ? val(f.top5) : null;
    const avg = f ? val(f.avg.area) : null;
    const mine = Number(st.state);
    const cell = (label, v, color) => `<div class="c"><span class="l">${esc(label)}</span><span class="v" style="color:${color || 'inherit'}">${v == null || isNaN(v) ? '—' : Number(v).toFixed(2)}</span></div>`;
    const diff = avg != null && !isNaN(mine) ? mine - avg : null;
    const rank = at.rank != null ? `<div class="c"><span class="l">${esc(X('tile_rank'))}</span><span class="v">${esc(String(at.rank))}${at.fresh_count ? '/' + esc(String(at.fresh_count)) : ''}</span></div>` : '';
    const sig = JSON.stringify([cheapest, avg, mine, at.rank, lang]);
    if (sig === this._sig) return;
    this._sig = sig;
    this.shadowRoot.innerHTML = `<style>
      :host { display: block; } .r { display: flex; gap: 8px; justify-content: space-around; padding: 4px 12px 10px; font-family: var(--ha-font-family-body, system-ui, sans-serif); }
      .c { display: flex; flex-direction: column; align-items: center; min-width: 0; } .l { font-size: 11px; color: var(--secondary-text-color); } .v { font-size: 15px; font-weight: 800; color: var(--primary-text-color); }
    </style><div class="r">${cell(X('tile_cheapest'), cheapest, 'var(--success-color, #43a047)')}${cell(X('tile_avg'), avg)}${diff == null ? '' : `<div class="c"><span class="l">Δ</span><span class="v" style="color:${diff <= 0 ? 'var(--success-color, #43a047)' : 'var(--error-color, #db4437)'}">${diff >= 0 ? '+' : '−'}${Math.abs(diff).toFixed(2)}</span></div>`}${rank}</div>`;
  }
  static getStubConfig() { return { type: 'custom:ceny-paliv-tile-feature' }; }
}


// ------------------------------------------------------------------ visual editor
const EDITOR_TEXT = {
  en: {
    fuel: 'Fuel', place: 'Place', show: 'Parts to show', layout: 'Layout', stations: 'Stations in the list', compact: 'Compact', show_footer: 'Show update times and legend',
    map_height: 'Map height in px (0 = automatic)', logo_path: 'Folder of your own logos (leave empty for the logo pack)',
    home: 'My station', list: 'Cheapest stations', map: 'Map', graph: '30-day graph', prices: 'Station map with prices', regions: 'Region map', tank: 'Fuels and full tank',
    road: 'On the road', places: 'Places side by side',
    auto: 'Automatic: 2 columns when the card is wide', columns: 'Always 2 columns', stack: 'Always 1 column',
    sort: 'Sort the list by', price: 'Price', distance: 'Distance',
    navigation: 'Navigation app', google: 'Google Maps', mapy: 'Mapy.com', waze: 'Waze', fuel_switch: 'Chips to switch the fuel', tank_size: 'Full tank in litres',
    look: 'Look', dark: 'Ceny paliv (dark)', ha: 'Home Assistant theme', big: 'Big price for wall panels',
    place_list: 'Places to show side by side',
  },
  cs: {
    fuel: 'Palivo', place: 'Místo', show: 'Zobrazené části', layout: 'Rozvržení', stations: 'Počet stanic v seznamu', compact: 'Kompaktní', show_footer: 'Zobrazit časy aktualizace a legendu',
    map_height: 'Výška mapy v px (0 = automaticky)', logo_path: 'Složka s vlastními logy (prázdné = balíček log)',
    home: 'Moje stanice', list: 'Nejlevnější stanice', map: 'Mapa', graph: 'Graf za 30 dní', prices: 'Mapa stanic s cenami', regions: 'Mapa krajů', tank: 'Paliva a plná nádrž',
    road: 'Na cestě', places: 'Místa vedle sebe',
    auto: 'Automaticky: 2 sloupce, je-li karta široká', columns: 'Vždy 2 sloupce', stack: 'Vždy 1 sloupec',
    sort: 'Řadit seznam podle', price: 'Ceny', distance: 'Vzdálenosti',
    navigation: 'Navigační aplikace', google: 'Google Maps', mapy: 'Mapy.com', waze: 'Waze', fuel_switch: 'Tlačítka pro přepnutí paliva', tank_size: 'Plná nádrž v litrech',
    look: 'Vzhled', dark: 'Ceny paliv (tmavý)', ha: 'Motiv Home Assistantu', big: 'Velká cena pro nástěnné panely',
    place_list: 'Místa zobrazená vedle sebe',
  },
};

// What a config means when a key is missing: the editor saves only what differs from this.
const EDITOR_DEFAULTS = {
  show: DEFAULT_PARTS, layout: 'auto', stations: 5, compact: false, map_height: 0, sort: 'price', navigation: 'google', fuel_switch: false,
  tank_size: 40, look: 'dark', big: false,
};

class CenyPalivCardEditor extends HTMLElement {
  setConfig(config) { this._config = config; this._render(); }
  set hass(hass) { this._hass = hass; this._render(); }

  _render() {
    if (!this._hass || !this._config) return;
    if (!this._form) {
      this._form = document.createElement('ha-form');
      this._form.addEventListener('value-changed', (e) => {
        // keep what the config already has; add what the user changed; drop what is empty or back to its default
        const value = e.detail.value || {};
        const config = Object.assign({}, this._config);
        for (const k of Object.keys(value)) {
          const v = value[k];
          const def = k === 'show_footer' ? !value.compact : EDITOR_DEFAULTS[k];
          const empty = v === undefined || v === null || v === '' || (Array.isArray(v) && !v.length);
          const isDefault = def !== undefined && (Array.isArray(v) ? JSON.stringify(v) === JSON.stringify(def) : v === def);
          if (empty || isDefault) delete config[k];
          else config[k] = v;
        }
        this.dispatchEvent(new CustomEvent('config-changed', { detail: { config }, bubbles: true, composed: true }));
      });
      this.appendChild(this._form);
    }
    const lang = ((this._hass.language || 'en').split('-')[0] in EDITOR_TEXT) ? this._hass.language.split('-')[0] : 'en';
    const L = EDITOR_TEXT[lang];
    const options = CenyPalivCard.fuels(this._hass);
    this._form.hass = this._hass;
    this._form.data = Object.assign({ show: DEFAULT_PARTS, layout: 'auto', stations: 5, compact: false, show_footer: !this._config.compact, map_height: 0, sort: 'price', navigation: 'google', fuel_switch: false, tank_size: 40, look: 'dark', big: false }, this._config);
    const places = CenyPalivCard.places(this._hass, this._config.fuel);
    const allPlaces = CenyPalivCard.places(this._hass);
    const sel = (name, list, mode = 'dropdown') => ({ name, selector: { select: { mode, options: list.map((p) => ({ value: p, label: L[p] })) } } });
    this._form.schema = [
      { name: 'fuel', required: true, selector: { select: { options, mode: 'dropdown' } } },
      ...(places.length > 1 ? [{ name: 'place', selector: { select: { options: places, mode: 'dropdown' } } }] : []),
      { name: 'show', selector: { select: { multiple: true, mode: 'list', options: PARTS.map((p) => ({ value: p, label: L[p] })) } } },
      ...(allPlaces.length > 1 ? [{ name: 'places', selector: { select: { multiple: true, mode: 'list', options: allPlaces } } }] : []),
      sel('layout', ['auto', 'columns', 'stack']),
      { name: 'stations', selector: { number: { min: 1, max: 10, step: 1, mode: 'slider' } } },
      sel('sort', ['price', 'distance']),
      sel('navigation', ['google', 'mapy', 'waze']),
      { name: 'fuel_switch', selector: { boolean: {} } },
      { name: 'tank_size', selector: { number: { min: 10, max: 150, step: 1, mode: 'box', unit_of_measurement: 'l' } } },
      sel('look', ['dark', 'ha']),
      { name: 'big', selector: { boolean: {} } },
      { name: 'compact', selector: { boolean: {} } },
      { name: 'show_footer', selector: { boolean: {} } },
      { name: 'map_height', selector: { number: { min: 0, max: 800, step: 10, mode: 'box', unit_of_measurement: 'px' } } },
      { name: 'logo_path', selector: { text: {} } },
    ];
    this._form.computeLabel = (schema) => (schema.name === 'places' ? L.place_list : (L[schema.name] || schema.name));
  }
}

if (!customElements.get('ceny-paliv-card-editor')) customElements.define('ceny-paliv-card-editor', CenyPalivCardEditor);
if (!customElements.get('ceny-paliv-card')) customElements.define('ceny-paliv-card', CenyPalivCard);
if (!customElements.get('ceny-paliv-badge')) customElements.define('ceny-paliv-badge', CenyPalivBadge);
if (!customElements.get('ceny-paliv-tile-feature')) customElements.define('ceny-paliv-tile-feature', CenyPalivTileFeature);

window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === 'ceny-paliv-card')) {
  window.customCards.push({
    type: 'ceny-paliv-card',
    name: 'Ceny paliv',
    description: 'Czech fuel prices: cheapest stations of your city, your favourite station, map, price map, region map and 30-day graph (data from mBenzin.cz).',
  });
}
window.customBadges = window.customBadges || [];
if (!window.customBadges.some((c) => c.type === 'ceny-paliv-badge')) {
  window.customBadges.push({ type: 'ceny-paliv-badge', name: 'Ceny paliv', description: 'A fuel price (cheapest or your favourite station) as a badge.' });
}
window.customCardFeatures = window.customCardFeatures || [];
if (!window.customCardFeatures.some((c) => c.type === 'ceny-paliv-tile-feature')) {
  window.customCardFeatures.push({
    type: 'ceny-paliv-tile-feature',
    name: 'Ceny paliv',
    supported: (a, b) => {
      const c = [a, b].find((x) => x && x.entity_id);
      return !c || String(c.entity_id).startsWith('sensor.ceny_paliv_');
    },
    configurable: false,
  });
}
console.info(`%c Ceny paliv card %c ${CARD_VERSION} `, 'color:#fff;background:#f5b14c;font-weight:700', 'color:#f5b14c;background:#171a20');
