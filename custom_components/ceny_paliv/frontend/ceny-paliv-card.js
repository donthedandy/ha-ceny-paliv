/*
 * Ceny paliv card — shipped with the Ceny paliv integration, nothing to install separately.
 * Prices come from mBenzin.cz; this project is independent and not affiliated with mBenzin.
 *
 *   type: custom:ceny-paliv-card
 *   fuel: n95            # n95 | benzinplus | diesel | dieselplus | lpg | cng | adblue
 *
 * Optional (all of them are also in the visual editor: Add card > Ceny paliv):
 *   show: [home, list, map, graph]   # which parts to draw; use several cards to place them freely
 *   layout: auto         # auto = 2 columns when the card is wide | columns | stack
 *   stations: 5          # 1-5 stations in the list
 *   compact: false       # dense version: one line per station, short footer
 *   show_footer: true    # update times, legend (default: false when compact)
 *   map_height: 300      # px, default: the map card's own height
 *   logo_path: /local/   # only to use your own PNG files instead of the downloaded logo pack
 *
 * Station logos: tick the chains in the integration's setup (Configure > Station logos); the card finds them by
 * itself. Chains without a logo get a coloured badge with their initials.
 *
 * Texts come from the language chosen in the integration setup (attribute `labels` of the top5 sensor).
 */
const CARD_VERSION = '0.4.1';

const PARTS = ['home', 'list', 'map', 'graph'];

const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const norm = (s) => String(s == null ? '' : s).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/\s+/g, ' ').trim();

const STYLE = `
  :host { display: block; }
  .grid, .col { display: flex; flex-direction: column; gap: 16px; }
  .col { min-width: 0; }
  .grid.columns { flex-direction: row; align-items: flex-start; }
  .grid.columns > .col { flex: 1 1 0; }
  .grid.auto.wide { flex-direction: row; align-items: flex-start; }
  .grid.auto.wide > .col { flex: 1 1 0; }
  .card { background: #171a20; border: 1px solid #262a33; border-radius: 22px; padding: 16px; color: #eef0f3;
          font-family: Manrope, system-ui, sans-serif; box-sizing: border-box; }
  .card.compact { padding: 12px 14px; border-radius: 18px; }
  .card.home { border-color: rgba(76,195,217,0.30); cursor: pointer; }
  .row { display: flex; align-items: center; gap: 12px; padding: 12px 0; border-top: 1px solid #23272f; cursor: pointer; user-select: none; }
  .compact .row { padding: 7px 0; gap: 10px; }
  .row:first-of-type { border-top: none; }
  .map, .graph { border-radius: 22px; overflow: hidden; }
  .map.fixed { position: relative; min-width: 200px; }
  .map.fixed > * { position: absolute; inset: 0; display: block; }
  ha-icon { display: inline-block; }
`;

class CenyPalivCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._sig = '';
    this._children = null;
    this._timer = null;
  }

  setConfig(config) {
    if (!config || !config.fuel) throw new Error('ceny-paliv-card: set "fuel", for example "n95"');
    // show_map / show_graph: options of the first versions, still honoured when `show` is not set
    const legacy = PARTS.filter((p) => !(p === 'map' && config.show_map === false) && !(p === 'graph' && config.show_graph === false));
    const show = (Array.isArray(config.show) ? config.show : config.show ? [config.show] : legacy).filter((p) => PARTS.includes(p));
    this._config = Object.assign({ layout: 'auto', stations: 5, compact: false, logo_path: '' }, config);
    this._show = show.length ? show : PARTS;
    this._layout = ['auto', 'columns', 'stack'].includes(this._config.layout) ? this._config.layout : 'auto';
    this._n = Math.min(5, Math.max(1, Math.round(Number(this._config.stations) || 5)));
    this._compact = !!this._config.compact;
    this._footer = this._config.show_footer != null ? !!this._config.show_footer : !this._compact;
    this._mapHeight = Number(this._config.map_height) > 0 ? Number(this._config.map_height) : 0;
    this._ids = null;
    this._scanAt = 0;
    this._sig = '';
    this._children = null;
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

  // Find this fuel's sensors by their attributes, so the card does not depend on how Home Assistant names the
  // entities (device name prefix, renamed entities, second city...). Older installs without the attributes are
  // matched on the entity id suffix (..._<fuel>_top5, _home, _1 .. _5).
  _resolve(hass) {
    const c = this._ids;
    const valid = c && c.top5 && hass.states[c.top5] && (!c.home || hass.states[c.home]) && c.pos.every((id) => !id || hass.states[id]);
    const now = Date.now();
    if (valid && (c.home || now - this._scanAt < 10000)) return c;
    this._scanAt = now;
    const fuel = this._config.fuel;
    const ids = { top5: null, home: null, pos: [] };
    for (const id of Object.keys(hass.states)) {
      if (!id.startsWith('sensor.ceny_paliv_')) continue;
      const a = hass.states[id].attributes || {};
      let role = null; let idx = 0;
      if (a.cp_fuel) {
        if (a.cp_fuel !== fuel) continue;
        role = a.cp_role; idx = a.cp_index || 0;
      } else {
        const m = id.match(/_([a-z0-9]+)_(top5|home|[1-5])$/);
        if (!m || m[1] !== fuel) continue;
        role = m[2] === 'top5' ? 'top5' : m[2] === 'home' ? 'home' : 'position'; idx = /^\d$/.test(m[2]) ? Number(m[2]) : 0;
      }
      if (role === 'top5') ids.top5 = id;
      else if (role === 'home') ids.home = id;
      else if (role === 'position' && idx >= 1 && idx <= 5) ids.pos[idx - 1] = id;
    }
    return ids;
  }

  _sides() {
    const a = this._show.some((p) => p === 'home' || p === 'list');
    const b = this._show.some((p) => p === 'map' || p === 'graph');
    return { a, b, wide: a && b && this._layout !== 'stack' };
  }

  getCardSize() {
    const h = { home: this._compact ? 2 : 4, list: this._compact ? 1 + this._n : 2 + 2 * this._n, map: this._mapHeight ? Math.ceil(this._mapHeight / 50) : 6, graph: 4 };
    const sizes = this._show.map((p) => h[p]);
    const sd = this._sides();
    if (!sd.wide) return sizes.reduce((x, y) => x + y, 0);
    const left = ['home', 'list'].filter((p) => this._show.includes(p)).reduce((x, p) => x + h[p], 0);
    const right = ['map', 'graph'].filter((p) => this._show.includes(p)).reduce((x, p) => x + h[p], 0);
    return Math.max(left, right);
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
    root.innerHTML = `<style>${STYLE}</style><div class="wrap"><div class="grid ${mode}">${col('colA', ['home', 'list'])}${col('colB', ['map', 'graph'])}</div></div>`;
    root.addEventListener('click', (e) => this._click(e));
    root.addEventListener('pointerdown', (e) => this._down(e));
    ['pointerup', 'pointerleave', 'pointercancel'].forEach((n) => root.addEventListener(n, () => clearTimeout(this._timer)));
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
    if (this._extraReady || !this._hass) return;
    this._extraReady = true;
    const helpers = window.loadCardHelpers ? await window.loadCardHelpers() : null;
    if (!helpers) return;
    const hasHome = !!this._hass.states[this._ids.home];
    const kids = [];
    if (this._show.includes('map')) {
      const entities = this._ids.pos.slice(0, this._n).filter(Boolean).map((id) => ({ entity: id, label_mode: 'state', focus: true }));
      if (hasHome) entities.push({ entity: this._ids.home, label_mode: 'state', focus: true });
      kids.push({ id: 'map', cls: this._mapHeight ? 'map fixed' : 'map', config: { type: 'map', theme_mode: 'dark', auto_fit: true, default_zoom: 12, hours_to_show: 0, entities } });
    }
    if (this._show.includes('graph') && hasHome) {
      kids.push({
        id: 'graph',
        cls: 'graph',
        config: {
          type: 'statistics-graph', title: '30 d', entities: [this._ids.home], days_to_show: 30, period: 'day',
          chart_type: 'line', stat_types: ['mean', 'min', 'max'],
        },
      });
    }
    this._children = [];
    for (const k of kids) {
      const el = helpers.createCardElement(k.config);
      el.hass = this._hass;
      const wrap = document.createElement('div');
      wrap.className = k.cls;
      if (k.id === 'map' && this._mapHeight) wrap.style.height = `${this._mapHeight}px`;
      wrap.appendChild(el);
      this.shadowRoot.getElementById(k.id).appendChild(wrap);
      this._children.push(el);
    }
  }

  // ---------------------------------------------------------------- helpers
  _labels() {
    const top = this._hass.states[this._ids.top5];
    return (top && top.attributes && top.attributes.labels) || {};
  }

  _T(k, v) {
    const lb = this._labels();
    return String(lb[k] !== undefined ? lb[k] : k).replace(/\{(\w+)\}/g, (m, x) => (v && v[x] !== undefined ? v[x] : m));
  }

  _arrow(t) {
    if (!t) return { icon: 'mdi:minus', color: '#5b6270', txt: '—' };
    if (t.dir === 'down') return { icon: 'mdi:arrow-down-bold', color: '#5fd39a', txt: '−' + Math.abs(t.delta).toFixed(2) };
    if (t.dir === 'up') return { icon: 'mdi:arrow-up-bold', color: '#ff7a6b', txt: '+' + Math.abs(t.delta).toFixed(2) };
    return { icon: 'mdi:minus', color: '#f5c26b', txt: '0.00' };
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
    const top = this._hass.states[this._ids.top5];
    const list = (top && top.attributes && top.attributes.logos) || [];
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
    const ring = best ? 'box-shadow:0 0 0 2px #5fd39a;' : '';
    return `<span style="position:relative;width:${size}px;height:${size}px;flex-shrink:0;display:block">${this._disc(s, size, ring)}<span style="position:absolute;right:-5px;bottom:-5px;min-width:16px;height:16px;padding:0 3px;box-sizing:border-box;border-radius:999px;background:#0e1014;border:1px solid ${best ? '#5fd39a' : '#2a2f39'};color:${best ? '#5fd39a' : '#d6dae1'};font-size:10px;font-weight:800;display:flex;align-items:center;justify-content:center">${rank}</span></span>`;
  }

  // ---------------------------------------------------------------- rendering
  _renderTexts() {
    const hass = this._hass;
    const top = hass.states[this._ids.top5];
    const root = this.shadowRoot;
    const slot = (p, html) => { const el = root.getElementById(p); if (el) el.innerHTML = html; };
    if (!top || top.state === 'unavailable') {
      const msg = `<div class="card" style="color:#9aa1ad;font-size:14px">Ceny paliv (${esc(this._config.fuel)}): sensor not found or unavailable — is the fuel set up in the integration?</div>`;
      const first = this._show.find((p) => p === 'home' || p === 'list') || this._show[0];
      this._show.forEach((p) => slot(p, p === first ? msg : ''));
      return;
    }
    slot('home', this._show.includes('home') ? this._homeHtml() : '');
    slot('list', this._show.includes('list') ? this._listHtml() : '');
    this._buildExtra();
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
      return `<div style="display:flex;flex-direction:column;align-items:center;gap:2px;background:#1f232b;border-radius:12px;padding:8px 2px;min-width:0">
        <span style="font-size:11px;font-weight:700;color:#9aa1ad">${n} d${t && !covered ? '*' : ''}</span>
        <ha-icon icon="${r.icon}" style="--mdc-icon-size:18px;color:${r.color}"></ha-icon>
        <span style="font-size:13px;font-weight:800;color:${r.color};white-space:nowrap">${r.txt}</span></div>`;
    };
    const chips = [1, 2, 7, 14, 30].map(chip).join('');
    const anyTrend = Object.values(tr).some(Boolean);
    const note = !anyTrend ? T('trends_start')
      : (partial ? T('since_partial', { d: new Date(partial + 'T00:00:00').toLocaleDateString(LOC, { day: 'numeric', month: 'short' }) }) : '');
    let pos;
    if (a.rank == null) pos = `<span style="color:#f5c26b">${esc(T('not_ranked'))}</span>`;
    else if (Number(a.vs_cheapest) <= 0) pos = `<span style="color:#5fd39a">${esc(T('cheapest_town', { rank: a.rank, n: a.fresh_count }))}</span>`;
    else pos = `<span style="color:#f5c26b">${esc(T('vs_cheapest', { d: Number(a.vs_cheapest).toFixed(2), name: a.cheapest_name, rank: a.rank, n: a.fresh_count }))}</span>`;
    const topHome = (this._hass.states[this._ids.top5].attributes || {}).home || { name: stationName };
    const hasLogo = !!this._logoUrl(topHome);
    const size = this._compact ? 36 : 44;
    const iconBox = `<div style="position:absolute;left:0;top:0;width:${size}px;height:${size}px;border-radius:14px;display:flex;align-items:center;justify-content:center;background:rgba(76,195,217,0.16)"><ha-icon icon="mdi:gas-station-in-use" style="--mdc-icon-size:22px;color:#4cc3d9"></ha-icon></div>`;
    const logo = `<div style="position:relative;width:${size}px;height:${size}px;flex-shrink:0">${hasLogo ? this._disc(topHome, size) : iconBox}</div>`;
    const cp = this._compact;
    const mini = [1, 7, 30].map((n) => { const r = this._arrow(tr[String(n)]); return `<span style="color:#9aa1ad">${n} d <span style="color:${r.color};font-weight:800">${esc(r.txt)}</span></span>`; }).join(' · ');
    return `<div class="card home${cp ? ' compact' : ''}" data-more-info="${esc(this._ids.home)}">
      <div style="display:flex;flex-direction:column;gap:${cp ? 8 : 12}px;width:100%;text-align:left">
        <div style="display:flex;align-items:center;gap:12px">${logo}
          <div style="flex:1 1 auto;display:flex;flex-direction:column;gap:2px;min-width:0">
            <span style="font-size:12px;letter-spacing:.09em;text-transform:uppercase;font-weight:700;color:#9aa1ad">${esc(T('my_station'))}</span>
            <span style="font-size:15px;font-weight:700;color:#eef0f3">${esc(stationName)}</span>
            <span style="font-size:12px;color:${stale ? '#f5c26b' : '#9aa1ad'}">${esc(updTxt)}</span></div>
          <div style="display:flex;flex-direction:column;align-items:flex-end;flex-shrink:0">
            <span style="font-size:${cp ? 30 : 40}px;font-weight:800;letter-spacing:-0.03em;line-height:1;color:${stale ? '#9aa1ad' : '#eef0f3'}">${price}</span>
            <span style="font-size:11px;color:#9aa1ad;font-weight:600">${esc(a.unit_of_measurement || 'Kč/l')}</span></div>
        </div>
        ${cp ? `<div style="display:flex;flex-wrap:wrap;gap:4px 8px;font-size:12px;font-weight:600">${mini}</div>`
    : `<div style="display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:6px">${chips}</div>
        ${note ? `<span style="font-size:11px;color:#5b6270;margin-top:-4px">${esc(note)}</span>` : ''}`}
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;font-size:12px;font-weight:600">${pos}
          ${cp ? '' : `<span style="color:#5b6270;font-weight:500;white-space:nowrap">${esc(T('tap_history'))}</span>`}</div>
      </div></div>`;
  }

  _listHtml() {
    const S = this._hass.states[this._ids.top5];
    const at = S.attributes;
    const T = (k, v) => this._T(k, v);
    const LOC = this._labels().locale || 'en-GB';
    const all = Array.isArray(at.stations) ? at.stations : [];
    const maxAge = at.max_age_days != null ? Number(at.max_age_days) : 1;
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const fresh = all.filter((s) => this._age(s, today) <= maxAge);
    const list = fresh.slice(0, this._n);
    const cp = this._compact;
    const prices = list.map((s) => Number(s.price)).filter((p) => !isNaN(p));
    const min = prices.length ? Math.min(...prices) : null;
    const unit = at.unit_of_measurement || 'Kč/l';
    const fp = (p) => Number(p).toFixed(2);
    const n = min === null ? 0 : fresh.filter((s) => Number(s.price) === min).length;
    const sub = min === null ? T('no_recent') : T('cheapest_price', { p: fp(min), unit }) + (n > 1 ? ' · ' + T('stations_same', { n }) : '');
    const head = `<div style="display:flex;align-items:center;gap:12px;width:100%;padding-bottom:${cp ? 6 : 12}px">
      <div style="width:${cp ? 36 : 44}px;height:${cp ? 36 : 44}px;border-radius:14px;display:flex;align-items:center;justify-content:center;background:rgba(245,177,76,0.16);flex-shrink:0">
        <ha-icon icon="mdi:gas-station" style="--mdc-icon-size:22px;color:#f5b14c"></ha-icon></div>
      <div style="flex:1 1 auto;display:flex;flex-direction:column;gap:2px;text-align:left;min-width:0">
        <span style="font-size:15px;font-weight:700;color:#eef0f3">${esc(at.fuel_label || this._config.fuel)} · ${esc(at.city_name || '')}</span>
        <span style="font-size:13px;color:#9aa1ad">${esc(sub)}</span></div>
      <div style="display:flex;flex-direction:column;align-items:flex-end;flex-shrink:0">
        <span style="font-size:${cp ? 22 : 28}px;font-weight:800;letter-spacing:-0.02em;line-height:1;color:${min === null ? '#5b6270' : '#5fd39a'}">${min === null ? '—' : fp(min)}</span>
        <span style="font-size:11px;color:#9aa1ad;font-weight:600">${esc(unit)}</span></div></div>`;
    const rows = list.map((s, i) => {
      const best = Number(s.price) === min;
      const diff = Number(s.price) - min;
      const name = s.name || '—';
      const a0 = s.address || '';
      const addr = a0.startsWith(name) ? a0.slice(name.length).trim() : a0;
      const tr = this._arrow((s.trends || {})['1']);
      const age = this._age(s, today);
      const when = age <= 0 ? T('today') : `<span style="color:#f5c26b">${esc(age === 1 ? T('yesterday') : (s.updated || '—'))}</span>`;
      const home = s.home ? `<ha-icon icon="mdi:home" title="${esc(T('my_station'))}" style="--mdc-icon-size:14px;color:#4cc3d9;margin-left:6px"></ha-icon>` : '';
      return `<div class="row" data-maps="${esc(s.maps)}">
        ${this._avatar(s, i + 1, best)}
        <div style="flex:1 1 auto;display:flex;flex-direction:column;gap:2px;text-align:left;min-width:0">
          <span style="font-size:15px;font-weight:700;color:#eef0f3;${cp ? 'white-space:nowrap;overflow:hidden;text-overflow:ellipsis' : ''}">${esc(name)}${cp ? ` <span style="font-size:11px;font-weight:500;color:#9aa1ad">${esc(addr)}</span>` : ''}${home}</span>
          ${cp ? '' : `<span style="font-size:12px;color:#9aa1ad;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(addr)} · ${when}</span>`}</div>
        <div style="display:flex;flex-direction:column;align-items:center;flex-shrink:0;width:40px" title="${esc(T('vs_yesterday'))}">
          <ha-icon icon="${tr.icon}" style="--mdc-icon-size:18px;color:${tr.color}"></ha-icon>
          <span style="font-size:10px;font-weight:700;color:${tr.color}">${tr.txt}</span></div>
        <div style="display:flex;flex-direction:column;align-items:flex-end;flex-shrink:0;gap:1px">
          <span style="font-size:18px;font-weight:800;color:${best ? '#5fd39a' : '#eef0f3'}">${fp(s.price)}</span>
          <span style="font-size:11px;font-weight:600;color:${best ? '#5fd39a' : '#9aa1ad'}">${esc(best ? T('cheapest_badge') : '+' + fp(diff))}</span></div>
        <ha-icon icon="mdi:chevron-right" style="--mdc-icon-size:18px;color:#5b6270;flex-shrink:0"></ha-icon></div>`;
    }).join('');
    // footer
    const now = new Date();
    const hm = (d) => d.toLocaleTimeString(LOC, { hour: '2-digit', minute: '2-digit' });
    const when = (d) => (d.toDateString() === now.toDateString() ? hm(d) : d.toLocaleString(LOC, { weekday: 'short', hour: '2-digit', minute: '2-digit' }));
    const fa = at.fetched_at ? new Date(at.fetched_at) : null;
    const la = at.last_attempt ? new Date(at.last_attempt) : null;
    const nu = at.next_update ? new Date(at.next_update) : null;
    const hidden = (at.excluded || 0) + (all.length - fresh.length);
    const lines = [`<span style="font-size:13px;color:#d6dae1;font-weight:600">${esc(T('table_updated', { t: fa ? when(fa) : '—', n: nu ? when(nu) : '—' }))}</span>`];
    if (at.fetch_error) lines.push(`<span style="font-size:12px;color:#f5c26b">${esc(T('refresh_failed', { at: la ? T('at') + when(la) : '', err: at.fetch_error }))}</span>`);
    if (at.city_total) lines.push(`<span style="font-size:12px;color:#9aa1ad">${esc(T('hidden', { h: hidden, t: at.city_total, age: maxAge >= 1 ? T('yesterday_l') : T('today_l') }))}</span>`);
    lines.push(`<span style="font-size:11px;color:#9aa1ad">${esc(T('arrows'))} · <span style="color:#5fd39a">▼ ${esc(T('down'))}</span> · <span style="color:#f5c26b">— ${esc(T('stable'))}</span> · <span style="color:#ff7a6b">▲ ${esc(T('up'))}</span> · ${esc(T('longpress'))}</span>`);
    lines.push(`<span style="font-size:11px;color:#5b6270">mBenzin.cz · ${esc(at.fuel_label || '')}${at.fuel === 'n95' ? ' ' + esc(T('e10_note')) : ''} · ${esc(T('tap_station'))}</span>`);
    const foot = !this._footer ? `<div style="padding-top:6px;font-size:11px;color:#5b6270;text-align:left">mBenzin.cz${at.fetch_error ? ' · ' + esc(T('refresh_failed', { at: '', err: at.fetch_error })) : ''}</div>` : `<div style="display:flex;flex-direction:column;gap:3px;text-align:left;border-top:1px solid #23272f;padding-top:12px">${lines.join('')}</div>`;
    return `<div class="card${cp ? ' compact' : ''}" data-more-info="${esc(this._ids.home || this._ids.top5)}">${head}${rows}${foot}</div>`;
  }

  // ---------------------------------------------------------------- interaction
  _entityId(e) {
    const t = e.composedPath ? e.composedPath().find((n) => n.dataset && (n.dataset.maps || n.dataset.moreInfo)) : null;
    return t || null;
  }

  _down(e) {
    const t = this._entityId(e);
    this._long = false;
    clearTimeout(this._timer);
    if (t && t.dataset.maps) {
      this._timer = setTimeout(() => {
        this._long = true;
        this._moreInfo(this._ids.home || this._ids.top5);
      }, 550);
    }
  }

  _click(e) {
    const t = this._entityId(e);
    if (!t) return;
    if (this._long) { this._long = false; return; }
    if (t.dataset.maps) window.open(t.dataset.maps, '_blank', 'noopener');
    else if (t.dataset.moreInfo && !e.composedPath().some((n) => n.dataset && n.dataset.maps)) this._moreInfo(t.dataset.moreInfo);
  }

  _moreInfo(entityId) {
    this.dispatchEvent(new CustomEvent('hass-more-info', { bubbles: true, composed: true, detail: { entityId } }));
  }
}


// ------------------------------------------------------------------ visual editor
const EDITOR_TEXT = {
  en: {
    fuel: 'Fuel', show: 'Parts to show', layout: 'Layout', stations: 'Stations in the list', compact: 'Compact', show_footer: 'Show update times and legend',
    map_height: 'Map height in px (0 = automatic)', logo_path: 'Folder of your own logos (leave empty for the logo pack)',
    home: 'My station', list: 'Cheapest stations', map: 'Map', graph: '30-day graph',
    auto: 'Automatic: 2 columns when the card is wide', columns: 'Always 2 columns', stack: 'Always 1 column',
  },
  cs: {
    fuel: 'Palivo', show: 'Zobrazené části', layout: 'Rozvržení', stations: 'Počet stanic v seznamu', compact: 'Kompaktní', show_footer: 'Zobrazit časy aktualizace a legendu',
    map_height: 'Výška mapy v px (0 = automaticky)', logo_path: 'Složka s vlastními logy (prázdné = balíček log)',
    home: 'Moje stanice', list: 'Nejlevnější stanice', map: 'Mapa', graph: 'Graf za 30 dní',
    auto: 'Automaticky: 2 sloupce, je-li karta široká', columns: 'Vždy 2 sloupce', stack: 'Vždy 1 sloupec',
  },
};

class CenyPalivCardEditor extends HTMLElement {
  setConfig(config) { this._config = config; this._render(); }
  set hass(hass) { this._hass = hass; this._render(); }

  _render() {
    if (!this._hass || !this._config) return;
    if (!this._form) {
      this._form = document.createElement('ha-form');
      this._form.addEventListener('value-changed', (e) => {
        const config = Object.assign({}, this._config, e.detail.value);
        for (const k of Object.keys(config)) {
          const v = config[k];
          if (v === undefined || v === null || v === '' || (Array.isArray(v) && !v.length) || (k === 'map_height' && !v)) delete config[k];
        }
        this.dispatchEvent(new CustomEvent('config-changed', { detail: { config }, bubbles: true, composed: true }));
      });
      this.appendChild(this._form);
    }
    const lang = ((this._hass.language || 'en').split('-')[0] in EDITOR_TEXT) ? this._hass.language.split('-')[0] : 'en';
    const L = EDITOR_TEXT[lang];
    const options = CenyPalivCard.fuels(this._hass);
    this._form.hass = this._hass;
    this._form.data = Object.assign({ show: PARTS, layout: 'auto', stations: 5, compact: false, show_footer: !this._config.compact, map_height: 0 }, this._config);
    this._form.schema = [
      { name: 'fuel', required: true, selector: { select: { options, mode: 'dropdown' } } },
      { name: 'show', selector: { select: { multiple: true, mode: 'list', options: PARTS.map((p) => ({ value: p, label: L[p] })) } } },
      { name: 'layout', selector: { select: { mode: 'dropdown', options: ['auto', 'columns', 'stack'].map((p) => ({ value: p, label: L[p] })) } } },
      { name: 'stations', selector: { number: { min: 1, max: 5, step: 1, mode: 'slider' } } },
      { name: 'compact', selector: { boolean: {} } },
      { name: 'show_footer', selector: { boolean: {} } },
      { name: 'map_height', selector: { number: { min: 0, max: 800, step: 10, mode: 'box', unit_of_measurement: 'px' } } },
      { name: 'logo_path', selector: { text: {} } },
    ];
    this._form.computeLabel = (schema) => L[schema.name] || schema.name;
  }
}
if (!customElements.get('ceny-paliv-card-editor')) customElements.define('ceny-paliv-card-editor', CenyPalivCardEditor);

if (!customElements.get('ceny-paliv-card')) customElements.define('ceny-paliv-card', CenyPalivCard);
window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === 'ceny-paliv-card')) {
  window.customCards.push({
    type: 'ceny-paliv-card',
    name: 'Ceny paliv',
    description: 'Czech fuel prices: cheapest stations of your city, your favourite station, map and 30-day graph (data from mBenzin.cz).',
  });
}
console.info(`%c Ceny paliv card %c ${CARD_VERSION} `, 'color:#fff;background:#f5b14c;font-weight:700', 'color:#f5b14c;background:#171a20');
